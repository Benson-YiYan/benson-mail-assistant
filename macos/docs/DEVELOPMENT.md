# Mac development and release builds

This document covers the `macos/` project in the public [Mail Secretary repository](https://github.com/Benson-YiYan/benson-mail-assistant). See the root [English guide](../../README.en.md) or [Chinese guide](../../README.md) for the whole project. End users can download DMGs from [Releases](https://github.com/Benson-YiYan/benson-mail-assistant/releases/latest); they do not need these tools.

From the cloned repository root, first enter the Mac project:

```sh
cd macos
```

Run every command below from `macos/`, including environment creation, builds, tests and packaging. Paths such as `Sources`, `Runtime`, `script` and `dist` are relative to that directory.

## Prerequisites

- macOS 14 or later, with Xcode Command Line Tools and a Swift 5.9 or newer toolchain.
- Python with `venv` and pip. The build script expects the exact environment directory names shown below.
- For an Intel package built on Apple silicon, use a **universal2 Python containing both arm64 and x86_64**, and install Rosetta to run Intel package tests. An arm64-only Homebrew Python cannot produce the Intel worker.
- A logged-in macOS desktop session for native UI and disposable launchd tests.

The released builds were produced on Apple silicon using Python 3.12.14 arm64 for ARM and Python 3.14.6 universal2 for Intel. Intel tests run through Rosetta; they do not replace testing on a physical Intel Mac. Dependency versions in `requirements-build.txt` use ranges, so these steps reproduce the build process, not byte-identical binaries.

Check the tools:

```sh
xcode-select -p
swift --version
python3 --version
```

If Command Line Tools are missing, run `xcode-select --install` and complete the system installer. On Apple silicon, install Rosetta through the macOS prompt when first opening an Intel executable.

## Python environments

### Apple silicon

Use an arm64 Python:

```sh
python3 -m venv .package-venv
.package-venv/bin/python -m pip install --upgrade pip
.package-venv/bin/python -m pip install -r requirements-build.txt
file .package-venv/bin/python
```

### Intel package from Apple silicon

Install a universal2 Python from python.org. The following path matches the Python 3.14 framework layout used for the release; substitute the installed version if different:

```sh
/Library/Frameworks/Python.framework/Versions/3.14/bin/python3.14 -m venv .package-venv-intel
.package-venv-intel/bin/python -m pip install --upgrade pip
.package-venv-intel/bin/python -m pip install -r requirements-build.txt
lipo -archs .package-venv-intel/bin/python
arch -x86_64 .package-venv-intel/bin/python --version
```

The `lipo` output must include `x86_64`. On a physical Intel Mac, an x86_64 Python can be used for this environment; that host path has not been verified by the current release process.

## Build

```sh
bash script/build_and_run.sh --build-only
bash script/build_and_run.sh --build-only x86_64
```

Outputs:

| Target | Application |
| --- | --- |
| Apple silicon | `dist/邮件小秘书.app` |
| Intel | `dist-intel/邮件小秘书.app` |

The script compiles Swift, freezes the Python worker with PyInstaller, bundles guides, presets and dependencies, sets the version to the actual Beijing time (`yyyyMMddHHmm`), and applies a local ad hoc signature. It does not perform Developer ID signing or Apple notarization.

Running the script without `--build-only` also opens the application. That is a normal application launch and can use existing local settings.

## Verification gates

Backend tests use the environment with installed build dependencies, rather than an unrelated system Python:

```sh
.package-venv/bin/python -m unittest discover -s tests -v
```

Run desktop and package tests **sequentially** in the logged-in session. They use synthetic messages, credentials and AI responses; they do not connect to a real mailbox or send requests to an external AI service.

```sh
python3 script/test_ui.py evidence/ui-arm 'dist/邮件小秘书.app'
python3 script/test_ui.py evidence/ui-intel 'dist-intel/邮件小秘书.app'
python3 script/check_package.py 'dist/邮件小秘书.app' evidence/runtime-arm
python3 script/check_package.py 'dist-intel/邮件小秘书.app' evidence/runtime-intel
```

- UI tests exercise the actual app, first-run setup, native input edits, navigation and unsaved draft retention, Markdown rendering, language switching and existing actions. Inspect `result.json` and generated native window snapshots.
- Package tests check bundled binary architecture and macOS compatibility, TLS/runtime dependencies, a local synthetic API and attachment pipeline, and disposable launchd start/restart/cleanup. They leave the user's application service and credentials untouched.
- Require `ok: true` in each result; a screenshot alone is not a passing test.

## Create and verify DMGs

Final deliverables for this project go in `/Users/apple/Documents/CodexMade`:

```sh
python3 script/package_release.py /Users/apple/Documents/CodexMade 'dist/邮件小秘书.app'
python3 script/package_release.py /Users/apple/Documents/CodexMade 'dist-intel/邮件小秘书.app'
```

The scripts print the exact generated DMG paths, using the version in each application's `Info.plist`. Do not substitute an earlier timestamp. For each generated image, run:

```sh
python3 script/check_update_package.py 'dist/邮件小秘书.app' '/absolute/path/to/AppleSilicon-generated.dmg' evidence/update-arm
python3 script/check_update_package.py 'dist-intel/邮件小秘书.app' '/absolute/path/to/Intel-generated.dmg' evidence/update-intel
hdiutil verify '/absolute/path/to/AppleSilicon-generated.dmg'
hdiutil verify '/absolute/path/to/Intel-generated.dmg'
shasum -a 256 '/absolute/path/to/AppleSilicon-generated.dmg' '/absolute/path/to/Intel-generated.dmg'
```

Replace the example DMG paths with the actual printed paths. Update-package tests verify integrity rejection, read-only mounting, architecture/version/signature checks, independent helper execution and cleanup against a disposable synthetic installation.

Record each final image's version, size and SHA256 for release metadata. Publish and verify the new release before removing superseded delivery files.

## Local installation

For a normal install, open the DMG and drag the app into Applications.

`script/install_standalone.py` is a maintainer upgrade helper: it installs the ARM build into `~/Applications/邮件小秘书.app`, preserves and verifies existing settings, and confirms registration of the newly bundled worker. It changes the real local installation and may wait for ongoing work; it is not an isolated test.

`script/install_local.py` migrates Benson's earlier development service. It assumes an existing service/data layout and is **not** a general installation or fresh-clone setup step.

Build folders, packaging environments and test evidence are ignored by Git. Before publishing source, inspect `git status` and stage explicit source/document paths; never include mailbox data, Keychain exports or local credentials.
