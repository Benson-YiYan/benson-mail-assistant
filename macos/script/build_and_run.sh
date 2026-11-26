#!/bin/bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"
MODE="${1:-run}"
TARGET_ARCH="${2:-arm64}"
BUILD_ROOT="${MAILASSISTANT_BUILD_ROOT:-$ROOT_DIR}"
case "$TARGET_ARCH" in
  arm64)
    DIST_DIR="$BUILD_ROOT/dist"
    SWIFT_BUILD_DIR="$BUILD_ROOT/.build"
    PYTHON_RUN=("$ROOT_DIR/.package-venv/bin/python")
    ;;
  x86_64)
    DIST_DIR="$BUILD_ROOT/dist-intel"
    SWIFT_BUILD_DIR="$BUILD_ROOT/.build-intel"
    # Universal2 Python lets PyInstaller select x86_64 while host lipo stays native.
    PYTHON_RUN=("$ROOT_DIR/.package-venv-intel/bin/python")
    ;;
  *) echo "Unsupported architecture: $TARGET_ARCH" >&2; exit 2 ;;
esac
APP_NAME="BensonMailMac"
APP_BUNDLE="$DIST_DIR/邮件小秘书.app"
mkdir -p "$BUILD_ROOT"
SWIFT_BUILD_ARGS=()
if [[ "${MAILASSISTANT_NO_DEBUG_INFO:-0}" == "1" ]]; then
  SWIFT_BUILD_ARGS=(-Xswiftc -gnone)
fi
swift build -c release --arch "$TARGET_ARCH" --scratch-path "$SWIFT_BUILD_DIR" ${SWIFT_BUILD_ARGS[@]+"${SWIFT_BUILD_ARGS[@]}"}
BUILD_BINARY="$(swift build -c release --arch "$TARGET_ARCH" --scratch-path "$SWIFT_BUILD_DIR" ${SWIFT_BUILD_ARGS[@]+"${SWIFT_BUILD_ARGS[@]}"} --show-bin-path)/$APP_NAME"
mkdir -p "$APP_BUNDLE/Contents/MacOS"
mkdir -p "$APP_BUNDLE/Contents/Resources"
cp Resources/ui-en.json Resources/ui-es.json Resources/ui-chinglish.json "$APP_BUNDLE/Contents/Resources/"
python3 ../script/build_language_packs.py --output "$BUILD_ROOT/build/language-packs"
mkdir -p "$APP_BUNDLE/Contents/Resources/languages"
cp "$BUILD_ROOT/build/language-packs/macos/chinglish.json" "$APP_BUNDLE/Contents/Resources/languages/"
cp ../docs/Chinglish-lexicon-LICENSE.txt "$APP_BUNDLE/Contents/Resources/"
cp Resources/Mail-account-setup-zh.txt Resources/Mail-account-setup-en.txt Resources/Mail-account-setup-es.txt "$APP_BUNDLE/Contents/Resources/"
cp Resources/Quick-start-zh.txt Resources/Quick-start-en.txt Resources/Quick-start-es.txt "$APP_BUNDLE/Contents/Resources/"
cp Resources/Get-Outlook-Token.command "$APP_BUNDLE/Contents/Resources/"
cp -R Resources/zh-Hans.lproj Resources/en.lproj Resources/es.lproj "$APP_BUNDLE/Contents/Resources/"
cp Resources/MailIcon.icns "$APP_BUNDLE/Contents/Resources/MailIcon.icns"
cp "$BUILD_BINARY" "$APP_BUNDLE/Contents/MacOS/$APP_NAME"
swiftc -O -target "${TARGET_ARCH}-apple-macosx14.0" RuntimeSupport/MailOCR.swift -o "$APP_BUNDLE/Contents/Resources/MailOCR"
codesign --force --sign - "$APP_BUNDLE/Contents/Resources/MailOCR"
swiftc -O -target "${TARGET_ARCH}-apple-macosx14.0" RuntimeSupport/SaveKeychainSecret.swift \
  -framework Security -o "$APP_BUNDLE/Contents/Resources/SaveKeychainSecret"
codesign --force --sign - "$APP_BUNDLE/Contents/Resources/SaveKeychainSecret"
cp Info.plist "$APP_BUNDLE/Contents/Info.plist"
if [[ ! -x "${PYTHON_RUN[${#PYTHON_RUN[@]}-1]}" ]]; then
  echo "Build environment missing for $TARGET_ARCH. Install requirements-build.txt in its packaging venv." >&2
  exit 1
fi
PYTHONPATH=Runtime "${PYTHON_RUN[@]}" -c 'import json; from mailbox_config import PRESETS; print(json.dumps(PRESETS, ensure_ascii=False))' > "$APP_BUNDLE/Contents/Resources/mail-presets.json"
# Some managed Python distributions require this additional CA distrust bundle.
# Preserve the runtime's certificate policy in the standalone package.
CA_POLICY_FILE="$("${PYTHON_RUN[@]}" -c 'import ssl; from pathlib import Path; p=Path(ssl.__file__).with_name("codex-rejected-cas.pem"); print(p if p.is_file() else "")')"
CA_POLICY_ARGS=()
if [[ -n "$CA_POLICY_FILE" ]]; then CA_POLICY_ARGS=(--add-data "$CA_POLICY_FILE:."); fi
PYINSTALLER_CONFIG_DIR="$BUILD_ROOT/build/cache-$TARGET_ARCH" "${PYTHON_RUN[@]}" -m PyInstaller --noconfirm --clean --onedir --console \
  ${CA_POLICY_ARGS[@]+"${CA_POLICY_ARGS[@]}"} --target-arch "$TARGET_ARCH" --distpath "$DIST_DIR" \
  --workpath "$BUILD_ROOT/build/$TARGET_ARCH" --specpath "$BUILD_ROOT/build/spec-$TARGET_ARCH" \
  --name MailWorker --paths Runtime --hidden-import mail_daemon \
  --hidden-import mail_watch --hidden-import mail_export --hidden-import ai_runner \
  --hidden-import markdown_render --collect-all markdown_it --collect-all mdurl \
  --hidden-import assistant_tools --hidden-import upstream_billing --hidden-import attachment_reader --hidden-import notification_policy --hidden-import language_packs --hidden-import mail_chat --hidden-import mail_policy --hidden-import update_install --hidden-import outlook_token --hidden-import oauth_client --hidden-import worker_selftest --hidden-import harness_smoke \
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
