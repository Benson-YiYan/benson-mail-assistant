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
import win32com.client

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
    shell = win32com.client.Dispatch('WScript.Shell')
    owned = shortcuts / '邮件小秘书.lnk'
    link = shell.CreateShortcut(str(owned))
    link.TargetPath = str(next(copied.glob('BensonMail-*.exe')))
    link.Save()
    other = shortcuts / '其他文件.lnk'
    link = shell.CreateShortcut(str(other))
    link.TargetPath = str(unrelated)
    link.Save()
    platform.set_autostart(True, startup_name)
    uninstaller = next(copied.glob('Uninstall-BensonMail-*.exe'))
    process = subprocess.Popen([str(uninstaller), '--e2e-test', str(result), '--delete-reports'],
                               cwd=tempfile.gettempdir())
    deadline = time.monotonic() + 150
    while time.monotonic() < deadline and not result.exists():
        time.sleep(.2)
    assert result.exists(), 'Independent uninstaller did not finish within 150 seconds'
    evidence = json.loads(result.read_text(encoding='utf-8'))
    assert evidence['ok'], evidence
    assert not copied.exists() and not data.exists()
    assert not report.exists() and not metadata.exists()
    assert unrelated.exists() and other.exists() and not owned.exists()
    assert not platform.has_autostart(startup_name)
    helper = Path(evidence['helper'])
    deadline = time.monotonic() + 45
    while time.monotonic() < deadline and helper.exists():
        time.sleep(.2)
    assert not helper.exists(), 'Temporary helper was not cleaned up'
    evidence['checks'] += ['EXE envelope icon resources present',
                           'registry startup value removed',
                           'owned shortcut removed and unrelated shortcut preserved',
                           'reports removed and unrelated files preserved',
                           'temporary helper removes itself after exit']
    result.write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding='utf-8')
    process.wait(timeout=10)
finally:
    platform.set_autostart(False, startup_name)
    shutil.rmtree(fixture, ignore_errors=True)
