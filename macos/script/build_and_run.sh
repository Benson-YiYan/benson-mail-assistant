#!/bin/bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"
MODE="${1:-run}"
TARGET_ARCH="${2:-arm64}"
case "$TARGET_ARCH" in
  arm64)
    DIST_DIR="$ROOT_DIR/dist"
    SWIFT_BUILD_DIR="$ROOT_DIR/.build"
    PYTHON_RUN=("$ROOT_DIR/.package-venv/bin/python")
    ;;
  x86_64)
    DIST_DIR="$ROOT_DIR/dist-intel"
    SWIFT_BUILD_DIR="$ROOT_DIR/.build-intel"
    # Universal2 Python lets PyInstaller select x86_64 while host lipo stays native.
    PYTHON_RUN=("$ROOT_DIR/.package-venv-intel/bin/python")
    ;;
  *) echo "Unsupported architecture: $TARGET_ARCH" >&2; exit 2 ;;
esac
APP_NAME="BensonMailMac"
APP_BUNDLE="$DIST_DIR/邮件小秘书.app"
swift build -c release --arch "$TARGET_ARCH" --scratch-path "$SWIFT_BUILD_DIR"
BUILD_BINARY="$(swift build -c release --arch "$TARGET_ARCH" --scratch-path "$SWIFT_BUILD_DIR" --show-bin-path)/$APP_NAME"
mkdir -p "$APP_BUNDLE/Contents/MacOS"
mkdir -p "$APP_BUNDLE/Contents/Resources"
cp Resources/ui-en.json "$APP_BUNDLE/Contents/Resources/ui-en.json"
cp Resources/Mail-account-setup-zh.txt Resources/Mail-account-setup-en.txt "$APP_BUNDLE/Contents/Resources/"
cp Resources/Quick-start-zh.txt Resources/Quick-start-en.txt "$APP_BUNDLE/Contents/Resources/"
cp Resources/Get-Outlook-Token.command "$APP_BUNDLE/Contents/Resources/"
cp Resources/MailIcon.icns "$APP_BUNDLE/Contents/Resources/MailIcon.icns"
cp "$BUILD_BINARY" "$APP_BUNDLE/Contents/MacOS/$APP_NAME"
cp Info.plist "$APP_BUNDLE/Contents/Info.plist"
if [[ ! -x "${PYTHON_RUN[${#PYTHON_RUN[@]}-1]}" ]]; then
  echo "Build environment missing for $TARGET_ARCH. Install requirements-build.txt in its packaging venv." >&2
  exit 1
fi
PYTHONPATH=Runtime "${PYTHON_RUN[@]}" -c 'import json; from mailbox_config import PRESETS; print(json.dumps(PRESETS, ensure_ascii=False))' > "$APP_BUNDLE/Contents/Resources/mail-presets.json"
PYINSTALLER_CONFIG_DIR="$ROOT_DIR/build/cache-$TARGET_ARCH" "${PYTHON_RUN[@]}" -m PyInstaller --noconfirm --clean --onedir --console \
  --target-arch "$TARGET_ARCH" --distpath "$DIST_DIR" \
  --workpath "$ROOT_DIR/build/$TARGET_ARCH" --specpath "$ROOT_DIR/build/spec-$TARGET_ARCH" \
  --name MailWorker --paths Runtime --hidden-import mail_daemon \
  --hidden-import mail_watch --hidden-import mail_export --hidden-import ai_runner \
  --hidden-import markdown_render --collect-all markdown_it --collect-all mdurl \
  --hidden-import update_install --hidden-import outlook_token --hidden-import worker_selftest --hidden-import harness_smoke \
  --collect-all pypdf --collect-all certifi --collect-all truststore \
  --collect-all tzdata \
  Runtime/worker_main.py
rm -rf "$APP_BUNDLE/Contents/Resources/worker"
cp -R "$DIST_DIR/MailWorker" "$APP_BUNDLE/Contents/Resources/worker"
VERSION="$(TZ=Asia/Shanghai date +%Y%m%d%H%M)"
/usr/libexec/PlistBuddy -c "Set :CFBundleVersion $VERSION" "$APP_BUNDLE/Contents/Info.plist"
codesign --force --deep --sign - "$APP_BUNDLE"
case "$MODE" in
  --build-only) ;;
  run) open "$APP_BUNDLE" ;;
  --verify) open "$APP_BUNDLE"; sleep 2; pgrep -x "$APP_NAME" >/dev/null ;;
  --debug) lldb -- "$APP_BUNDLE/Contents/MacOS/$APP_NAME" ;;
  --logs) open "$APP_BUNDLE"; /usr/bin/log stream --info --style compact --predicate 'process == "BensonMailMac"' ;;
  --telemetry) open "$APP_BUNDLE"; /usr/bin/log stream --info --style compact --predicate 'subsystem == "com.benson.mail-ui"' ;;
  *) echo "usage: $0 [run|--build-only|--verify|--debug|--logs|--telemetry] [arm64|x86_64]" >&2; exit 2 ;;
esac
