"""Exercise bundled worker and a disposable launchd service, without real mail."""
import json
import os
from pathlib import Path
import plistlib
import re
import subprocess
import sys
import tempfile
import time
import uuid

project = Path(__file__).resolve().parents[1]
app = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else project / 'dist/邮件小秘书.app'
evidence = Path(sys.argv[2]).resolve() if len(sys.argv) > 2 else project / 'evidence/standalone'
evidence.mkdir(parents=True, exist_ok=True)
worker = app / 'Contents/Resources/worker/MailWorker'
checks = []
tls = subprocess.run([str(worker), '--test-tls'], capture_output=True, text=True, timeout=30, check=True)
assert json.loads(tls.stdout)['ok']
checks.append('packaged default TLS context initializes with certificate verification enabled')
architecture = set(subprocess.check_output(
    ['/usr/bin/lipo', '-archs', str(app / 'Contents/MacOS/BensonMailMac')], text=True).split())
if architecture not in ({'arm64'}, {'x86_64'}):
    raise RuntimeError('Expected one supported Mac architecture')
machos = 0
for file in app.rglob('*'):
    if file.is_symlink() or not file.is_file():
        continue
    with file.open('rb') as stream:
        magic = stream.read(4)
    if magic not in (b'\xcf\xfa\xed\xfe', b'\xfe\xed\xfa\xcf', b'\xca\xfe\xba\xbe', b'\xbe\xba\xfe\xca'):
        continue
    slices = set(subprocess.check_output(['/usr/bin/lipo', '-archs', str(file)], text=True).split())
    if not architecture.issubset(slices):
        raise RuntimeError('Incompatible bundled binary: ' + file.name)
    load = subprocess.check_output(['/usr/bin/otool', '-l', str(file)], text=True)
    for block in re.split(r'Load command \d+', load):
        match = re.search(r'\bminos\s+(\d+)\.(\d+)', block) if 'LC_BUILD_VERSION' in block else (
            re.search(r'\bversion\s+(\d+)\.(\d+)', block) if 'LC_VERSION_MIN_MACOSX' in block else None)
        if match and tuple(map(int, match.groups())) > (14, 0):
            raise RuntimeError('Bundled binary requires newer than macOS 14: ' + file.name)
    machos += 1
checks.append(f'all {machos} bundled Mach-O binaries support {next(iter(architecture))} and macOS 14')
with tempfile.TemporaryDirectory(prefix='BensonMail-package-test-') as temporary:
    base = Path(temporary)
    env = dict(os.environ, PATH='/usr/bin:/bin', BENSON_MAIL_HOME=temporary)
    for operation in ['--diagnose', '--self-test', '--harness-self-test']:
        result = subprocess.run([str(worker), operation], env=env, capture_output=True, text=True, timeout=70)
        if result.returncode:
            raise RuntimeError(operation + ' failed: ' + result.stderr[-2000:])
        value = json.loads(result.stdout.strip().splitlines()[-1])
        assert value['ok']
        (evidence / (operation[2:] + '.json')).write_text(json.dumps(value, ensure_ascii=False, indent=2))
    checks.append('standalone runtime and synthetic API/attachment/report pipeline with developer tools absent from PATH')
    # Remove only synthetic mail data before testing a paused background service.
    (base / 'settings.json').write_text(json.dumps({'enabled': False, 'interval_seconds': 60}))
    label = 'com.benson.mail-package-test.' + uuid.uuid4().hex
    agent = base / (label + '.plist')
    agent.write_bytes(plistlib.dumps({
        'Label': label, 'ProgramArguments': [str(worker), '--home', temporary, '--app', str(app), '--daemon'],
        'RunAtLoad': True, 'KeepAlive': True, 'ThrottleInterval': 1,
        'StandardOutPath': str(base / 'test.log'), 'StandardErrorPath': str(base / 'test-error.log'),
    }))
    target = 'gui/' + str(os.getuid()) + '/' + label
    try:
        subprocess.run(['/bin/launchctl', 'bootstrap', 'gui/' + str(os.getuid()), str(agent)], check=True)
        for _ in range(50):
            status = base / 'mail_watch/service.json'
            if status.exists() and json.loads(status.read_text()).get('phase') == 'paused': break
            time.sleep(.2)
        else: raise RuntimeError('bundled launch-agent did not reach paused state')
        subprocess.run(['/bin/launchctl', 'kickstart', '-k', target], check=True)
        time.sleep(1)
        assert json.loads(status.read_text())['phase'] == 'paused'
        checks.append('fresh launchd bootstrap and forced restart preserve paused state; no AI or mailbox requests')
    finally:
        subprocess.run(['/bin/launchctl', 'bootout', target], capture_output=True)
    for _ in range(25):
        absent = subprocess.run(['/bin/launchctl', 'print', target], capture_output=True).returncode != 0
        if absent: break
        time.sleep(.2)
    assert absent
    checks.append('disposable background service removed; existing user agent and credentials untouched')
(evidence / 'package-result.json').write_text(json.dumps({'ok': True, 'checks': checks}, ensure_ascii=False, indent=2))
print(json.dumps({'ok': True, 'checks': checks}, ensure_ascii=False))
