"""Upgrade Benson's existing app after package tests, preserving mailbox state."""
import datetime
import hashlib
import json
import os
from pathlib import Path
import plistlib
import shutil
import subprocess
import time

project = Path(__file__).resolve().parents[1]
source = project / 'dist/邮件小秘书.app'
target = Path.home() / 'Applications/邮件小秘书.app'
base = Path.home() / 'Library/Application Support/BensonMail'
settings = base / 'settings.json'
before = json.loads(settings.read_text()) if settings.exists() else None
status = base / 'mail_watch/service.json'
deadline = time.monotonic() + 920
while status.exists() and json.loads(status.read_text()).get('phase') in {'checking', 'analyzing'}:
    # A normal app quit unloads the worker; its last status can remain in flight.
    if subprocess.run(
        ['/bin/launchctl', 'print', f'gui/{os.getuid()}/com.benson.codex-mail-163'],
        capture_output=True,
    ).returncode != 0:
        break
    if time.monotonic() > deadline:
        raise RuntimeError('Current email operation still running; upgrade deferred.')
    time.sleep(.5)
target.parent.mkdir(exist_ok=True)
stage = target.parent / '.邮件小秘书-update.app'
if stage.exists(): shutil.rmtree(stage)
shutil.copytree(source, stage, symlinks=True)
subprocess.run(['/usr/bin/codesign', '--verify', '--deep', '--strict', str(stage)], check=True)
subprocess.run(['/usr/bin/pkill', '-x', 'BensonMailMac'], check=False)
for _ in range(20):
    if subprocess.run(['/usr/bin/pgrep', '-x', 'BensonMailMac'], capture_output=True).returncode:
        break
    time.sleep(.25)
else:
    raise RuntimeError('Previous app did not exit; installation has not been replaced.')
if target.exists():
    backup = project.parent / 'mac-app-backups' / datetime.datetime.now().strftime('%Y%m%d-%H%M%S')
    backup.mkdir(parents=True)
    shutil.move(str(target), backup / target.name)
stage.rename(target)
for _ in range(10):
    # A recently terminated application can remain briefly in LaunchServices.
    opened = subprocess.run(['/usr/bin/open', '-n', str(target)], capture_output=True)
    if not opened.returncode:
        break
    time.sleep(.5)
else:
    raise RuntimeError('Installed app could not be opened; launch it from Applications.')
version = plistlib.loads((source / 'Contents/Info.plist').read_bytes())['CFBundleVersion']
expected = str(target / 'Contents/Resources/worker/MailWorker') + '|' + version
for _ in range(80):
    marker = base / 'worker-installation.json'
    if marker.exists() and marker.read_text() == expected:
        break
    time.sleep(.5)
else:
    raise RuntimeError('New service registration not confirmed; inspect app error before continuing.')
agent = Path.home() / 'Library/LaunchAgents/com.benson.codex-mail-163.plist'
arguments = plistlib.loads(agent.read_bytes())['ProgramArguments']
assert arguments[0] == str(target / 'Contents/Resources/worker/MailWorker')
if before is not None:
    after = json.loads(settings.read_text())
    expected_settings = dict(before)
    if 'ui_language' not in expected_settings:
        expected_settings['ui_language'] = after.get('ui_language')
    assert after == expected_settings, 'settings unexpectedly changed beyond language migration'
print('Installed standalone app; launch-agent uses bundled worker; existing settings preserved.')
