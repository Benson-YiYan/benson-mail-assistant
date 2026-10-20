"""Destructive checks operate only on a dedicated temporary package copy."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time

root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root))
from benson_mail import platform_windows as platform

import pefile
import pythoncom
import win32gui
import win32process
from win32com.shell import shell

program = Path(sys.argv[1]).resolve()
result = Path(sys.argv[2]).resolve()
for binary in (next(program.glob('BensonMail-*.exe')), next(program.glob('Uninstall-BensonMail-*.exe'))):
    with pefile.PE(str(binary)) as pe:
        resource_ids = {entry.id for entry in pe.DIRECTORY_ENTRY_RESOURCE.entries}
        assert {3, 14} <= resource_ids, 'Envelope icon resources missing from EXE'

fixture = Path(tempfile.mkdtemp(prefix='BensonMail-uninstall-fixture-')).resolve()
copied = fixture / program.name
startup_name = 'BensonMail-UninstallFixture'
try:
    shutil.copytree(program, copied)
    (fixture / '.benson-uninstall-fixture').write_text('synthetic data only', encoding='utf-8')
    data = fixture / 'user-data'
    data.mkdir()
    reports = fixture / 'reports'
    day = reports / '2026-10-16'
    day.mkdir(parents=True)
    report = day / 'test-16-30.txt'
    report.write_text('synthetic report', encoding='utf-8')
    metadata = report.with_suffix('.mail.json')
    metadata.write_text(json.dumps({'subject': 'test', 'sender': 'fixture', 'received': '2026-10-16'}), encoding='utf-8')
    unrelated = reports / '用户自己的文件.txt'
    unrelated.write_text('keep', encoding='utf-8')
    (data / 'config.json').write_text(json.dumps({'output_dir': str(reports)}), encoding='utf-8')
    (data / 'secret.bin').write_bytes(b'SYNTHETIC-ENCRYPTED-FIXTURE')
    shortcuts = fixture / 'shortcuts'
    shortcuts.mkdir()
    owned = shortcuts / '邮件小秘书.lnk'
    link = pythoncom.CoCreateInstance(shell.CLSID_ShellLink, None, pythoncom.CLSCTX_INPROC_SERVER,
                                     shell.IID_IShellLink)
    link.SetPath(str(next(copied.glob('BensonMail-*.exe'))))
    link.QueryInterface(pythoncom.IID_IPersistFile).Save(str(owned), 1)
    other = shortcuts / '其他文件.lnk'
    link = pythoncom.CoCreateInstance(shell.CLSID_ShellLink, None, pythoncom.CLSCTX_INPROC_SERVER,
                                     shell.IID_IShellLink)
    link.SetPath(str(unrelated))
    link.QueryInterface(pythoncom.IID_IPersistFile).Save(str(other), 1)
    platform.set_autostart(True, startup_name)
    uninstaller = next(copied.glob('Uninstall-BensonMail-*.exe'))
    process = subprocess.Popen([str(uninstaller), '--e2e-test', str(result), '--delete-reports'],
                               cwd=tempfile.gettempdir())
    # Observe actual top-level windows, not just the helper's self-report.
    # Staging stays invisible and the helper owns one continuous visible window.
    observed_windows = set()
    deadline = time.monotonic() + 150
    while time.monotonic() < deadline and not result.exists():
        def observe(hwnd, _):
            if (win32gui.IsWindowVisible(hwnd) and win32gui.GetWindowText(hwnd)
                    in {'卸载邮件小秘书', 'Uninstall Email Assistant', 'Desinstalar Asistente de correo electrónico'}):
                pid = win32process.GetWindowThreadProcessId(hwnd)[1]
                assert pid != process.pid, 'Installed launcher showed a window before staging'
                observed_windows.add((pid, hwnd))
        win32gui.EnumWindows(observe, None)
        time.sleep(.05)
    assert result.exists(), 'Independent uninstaller did not finish within 150 seconds'
    evidence = json.loads(result.read_text(encoding='utf-8'))
    assert evidence['ok'], evidence
    assert evidence['initialProcess'] == evidence['finalProcess']
    assert evidence['initialWindow'] == evidence['finalWindow'] != 0
    assert observed_windows == {(evidence['finalProcess'], evidence['finalWindow'])}, observed_windows
    assert not copied.exists() and not data.exists()
    assert not report.exists() and not metadata.exists()
    assert unrelated.exists() and other.exists() and not owned.exists()
    assert not platform.has_autostart(startup_name)
    helper = Path(evidence['helper'])
    deadline = time.monotonic() + 45
    while time.monotonic() < deadline and helper.exists():
        time.sleep(.2)
    assert not helper.exists(), 'Temporary helper was not cleaned up'
    evidence['checks'] += ['Externally observed one uninterrupted visible uninstaller HWND/PID; installed launcher stayed hidden',
                           'EXE envelope icon resources present',
                           'registry startup value removed',
                           'owned shortcut removed and unrelated shortcut preserved',
                           'reports removed and unrelated files preserved',
                           'temporary helper removes itself after exit']
    result.write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding='utf-8')
    process.wait(timeout=10)
    # Reinstall the package copy, preserve real current-user DPAPI ciphertext, then reopen it.
    shutil.copytree(program, copied)
    data.mkdir()
    config = {'account': 'synthetic@example.invalid', 'host': 'imap.example.invalid',
              'output_dir': str(reports), 'api_base': 'https://example.invalid/v1', 'api_model': 'fixture'}
    (data / 'config.json').write_text(json.dumps(config), encoding='utf-8')
    platform.save_secret(data / 'secret.bin', config['account'], 'SYNTHETIC-MAIL-CODE')
    api_dir = data / 'api-keys'
    api_dir.mkdir()
    platform.save_secret(api_dir / 'fixture.bin', config['api_base'], 'SYNTHETIC-AI-KEY')
    (data / 'state').mkdir()
    (data / 'state/mail.json').write_text('SYNTHETIC-CACHED-BODY')
    preserved = result.with_name(result.stem + '-preserved.json')
    process = subprocess.Popen([str(next(copied.glob('Uninstall-BensonMail-*.exe'))),
                                '--e2e-test', str(preserved), '--keep-configuration'],
                               cwd=tempfile.gettempdir())
    deadline = time.monotonic() + 150
    while time.monotonic() < deadline and not preserved.exists():
        time.sleep(.2)
    assert preserved.exists(), 'Preserve configuration uninstall timed out'
    assert json.loads(preserved.read_text(encoding='utf-8'))['ok']
    assert not copied.exists() and data.exists() and not (data / 'state').exists()
    assert json.loads((data / 'config.json').read_text(encoding='utf-8')) == config
    assert platform.load_secret(data / 'secret.bin', config['account']) == 'SYNTHETIC-MAIL-CODE'
    assert platform.load_secret(api_dir / 'fixture.bin', config['api_base']) == 'SYNTHETIC-AI-KEY'
    assert unrelated.exists()
    # Controller uses exactly this same directory on a subsequent installation.
    from benson_mail.bridge import Controller
    reinstalled = Controller(data, lambda _: None)
    assert reinstalled.secret() == 'SYNTHETIC-MAIL-CODE'
    evidence['checks'].append('optional preservation reopens mailbox and AI configuration with decryptable DPAPI credentials; cached mail removed')
    result.write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding='utf-8')
    process.wait(timeout=10)
finally:
    platform.set_autostart(False, startup_name)
    shutil.rmtree(fixture, ignore_errors=True)
