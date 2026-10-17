"""Exercise the real installer on a disposable Windows runner, with synthetic data."""
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from benson_mail import platform_windows as platform
from benson_mail.uninstall import cleanup_installation, remove_shortcuts


REGISTRATION = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\BensonMail"
TASKS = ("desktopapp", "desktopuninstall", "startapp", "startuninstall")


def registration():
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REGISTRATION) as key:
            values = {}
            index = 0
            while True:
                try:
                    name, value, _ = winreg.EnumValue(key, index)
                except OSError:
                    break
                values[name] = value
                index += 1
            return values
    except FileNotFoundError:
        return None


def wait_until(predicate, seconds, description):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(.2)
    raise AssertionError(description)


def inspect_link(path, expected):
    import pythoncom
    from win32com.shell import shell
    pythoncom.CoInitialize()
    try:
        link = pythoncom.CoCreateInstance(shell.CLSID_ShellLink, None, pythoncom.CLSCTX_INPROC_SERVER,
                                         shell.IID_IShellLink)
        link.QueryInterface(pythoncom.IID_IPersistFile).Load(str(path))
        assert Path(link.GetPath(shell.SLGP_RAWPATH)[0]).resolve() == expected.resolve(), str(path)
        assert link.GetArguments() == "", f"Unexpected shortcut arguments: {path}"
        assert Path(link.GetWorkingDirectory()).resolve() == expected.parent.resolve(), str(path)
    finally:
        pythoncom.CoUninitialize()


def run_first_start_worker(program, fixture):
    """Use the packaged first-start bridge with isolated settings and no email/AI requests."""
    environment = os.environ.copy()
    environment["LOCALAPPDATA"] = str(fixture / "isolated-localappdata")
    launcher = next(program.glob("BensonMail-*.exe"))
    requests = "\n".join(json.dumps(value) for value in (
        {"id": 1, "command": "config"}, {"id": 2, "command": "shutdown"})) + "\n"
    process = subprocess.run(
        [str(program / "MailWorker.exe"), "--bridge", "--launcher", str(launcher)],
        input=requests, text=True, encoding="utf-8", capture_output=True, env=environment,
        cwd=tempfile.gettempdir(), timeout=45, creationflags=subprocess.CREATE_NO_WINDOW)
    assert process.returncode == 0, "Packaged first-start worker failed"
    responses = [json.loads(line) for line in process.stdout.splitlines() if line.strip()]
    assert all(any(row.get("id") == number and row.get("ok") for row in responses) for number in (1, 2))
    assert not (fixture / "isolated-localappdata/BensonMail/desktop-shortcut.json").exists(), \
        "Installed first start must not create its own shortcut marker"


def main():
    assert sys.platform == "win32", "This integration test requires Windows"
    from win32com.shell import shell, shellcon
    setup = Path(sys.argv[1]).resolve()
    evidence = Path(sys.argv[2]).resolve()
    evidence.mkdir(parents=True, exist_ok=True)
    result = evidence / "installer-result.json"
    match = re.fullmatch(r"BensonMail-Windows-x64-Setup-(\d{12})\.exe", setup.name)
    assert match and setup.is_file(), "Installer filename must contain its actual build version"
    version = match.group(1)
    desktop = Path(shell.SHGetFolderPath(0, shellcon.CSIDL_DESKTOPDIRECTORY, None, 0))
    programs = Path(shell.SHGetFolderPath(0, shellcon.CSIDL_PROGRAMS, None, 0))
    places = (desktop, programs)
    def shortcut_paths(language):
        name, uninstall = ('邮件小秘书', '卸载邮件小秘书') if language == 'chinesesimp' else ('Mail Secretary', 'Uninstall Mail Secretary')
        return {
            'desktopapp': desktop / (name + '.lnk'),
            'desktopuninstall': desktop / (uninstall + '.lnk'),
            'startapp': programs / (name + '.lnk'),
            'startuninstall': programs / (uninstall + '.lnk'),
        }
    all_links = {*shortcut_paths('english').values(), *shortcut_paths('chinesesimp').values()}
    assert registration() is None, "Use a disposable runner without an existing Mail Secretary installation"
    assert not platform.has_autostart(), "Use a runner without a real Mail Secretary startup entry"
    assert not any(path.exists() for path in all_links), "Existing user shortcuts must be left untouched"
    checks = []
    cases = []
    fixture = Path(tempfile.mkdtemp(prefix="BensonMail-uninstall-fixture-")).resolve()
    (fixture / ".benson-uninstall-fixture").write_text("synthetic installer tests", encoding="utf-8")
    program = fixture / "BensonMail"
    try:
        selections = [TASKS, *((task,) for task in TASKS), ()]
        for number, selected in enumerate(selections):
            label = "all" if len(selected) == 4 else selected[0] if selected else "none"
            language = "chinesesimp" if number == 0 else "english"
            links = shortcut_paths(language)
            log = evidence / f"installer-{label}.log"
            process = subprocess.run([
                str(setup), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/SP-",
                "/LANG=" + language, "/DIR=" + str(program), "/TASKS=" + ",".join(selected),
                "/LOG=" + str(log),
            ], cwd=tempfile.gettempdir(), timeout=180)
            assert process.returncode == 0, f"Installer failed for {label}: {process.returncode}"
            launcher = program / f"BensonMail-{version}.exe"
            uninstaller = program / f"Uninstall-BensonMail-{version}.exe"
            assert launcher.is_file() and uninstaller.is_file() and (program / "MailWorker.exe").is_file()
            assert (program / "_internal").is_dir()
            marker = json.loads((program / ".benson-installed.json").read_text(encoding="utf-8-sig"))
            assert marker.get("installed") is True
            installed = registration()
            assert installed and Path(installed["InstallLocation"]).resolve() == program.resolve()
            assert installed["DisplayVersion"] == version
            assert installed["DisplayName"] == ("邮件小秘书" if language == "chinesesimp" else "Mail Secretary")
            assert installed["UninstallString"] in (str(uninstaller), f'"{uninstaller}"')
            for task, path in links.items():
                assert path.is_file() == (task in selected), f"{label}: wrong shortcut selection {task}"
                if task in selected:
                    inspect_link(path, uninstaller if "uninstall" in task else launcher)
            run_first_start_worker(program, fixture)
            for task, path in links.items():
                assert path.is_file() == (task in selected), f"First start overrode selected task {task}"
            cases.append({"tasks": list(selected), "language": language, "installed": True, "shortcuts": True,
                          "first_start_preserves_choices": True})
            if number == 0:
                # Reinstall into the same directory with all four choices cancelled,
                # including a language change: old Chinese links must disappear.
                reinstall = subprocess.run([
                    str(setup), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/SP-",
                    "/LANG=english", "/DIR=" + str(program), "/TASKS=",
                    "/LOG=" + str(evidence / "installer-reinstall-none.log"),
                ], cwd=tempfile.gettempdir(), timeout=180)
                assert reinstall.returncode == 0
                assert not any(path.exists() for path in all_links), "Reinstall kept shortcuts cancelled by user"
                run_first_start_worker(program, fixture)
                assert not any(path.exists() for path in all_links)
                checks.append("Reinstall with every choice cancelled removes old shortcuts across UI languages")
            data = fixture / "user-data"
            data.mkdir(exist_ok=True)
            (data / "config.json").write_text('{"ui_language":"en"}', encoding="utf-8")
            if number == 0:
                native_result = evidence / "installer-native-uninstall-result.json"
                native_result.unlink(missing_ok=True)
                child = subprocess.Popen([str(uninstaller), "--e2e-test", str(native_result)],
                                         cwd=tempfile.gettempdir())
                wait_until(native_result.exists, 180, "Native uninstall of actual installed payload timed out")
                native = json.loads(native_result.read_text(encoding="utf-8-sig"))
                assert native["ok"], native
                assert not program.exists() and not data.exists()
                child.wait(timeout=15)
                helper = Path(native["helper"])
                wait_until(lambda: not helper.exists(), 60, "Native uninstall helper was left behind")
                # Fixture mode deliberately confines shortcut/registry cleanup to fixture locations.
                # Check the real installed targets with the same production cleanup functions.
                remove_shortcuts(program, places)
                platform.remove_uninstall_registration(program)
                checks.append("Actual installed payload removed by independent native uninstaller; helper self-cleaned")
            else:
                cleanup_installation(program, data, False, lambda _: None, shortcut_places=places)
            assert not program.exists() and not data.exists()
            assert registration() is None
            assert not any(path.exists() for path in all_links)
            assert all(place.is_dir() for place in places), "Shared Desktop/Programs folders must remain"
        checks += [
            "Silent installer installs its versioned app, uninstaller, worker and ownership marker",
            "All four Desktop/Start menu choices tested independently, together and all disabled",
            "Created shortcuts resolve to matching versioned executables with no arguments and correct working directory",
            "Actual packaged first start honors installer choices without recreating unselected shortcuts",
            "Installed Apps registration contains matching install location, version and native uninstall command",
            "Target-based cleanup removes owned shortcuts and matching registration while preserving shared roots",
        ]
        result.write_text(json.dumps({"ok": True, "version": version, "checks": checks, "cases": cases},
                                     ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as error:
        result.write_text(json.dumps({"ok": False, "version": version, "checks": checks, "cases": cases,
                                     "error": f"{type(error).__name__}: {error}"},
                                    ensure_ascii=False, indent=2), encoding="utf-8")
        raise
    finally:
        remove_shortcuts(program, places)
        platform.remove_uninstall_registration(program)
        shutil.rmtree(fixture, ignore_errors=True)


if __name__ == "__main__":
    main()
