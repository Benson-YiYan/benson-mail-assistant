"""Install this UI on Benson's existing Mac service; preserve runtime and state."""
import datetime
import json
import os
from pathlib import Path
import plistlib
import shutil
import subprocess
import time

project = Path(__file__).resolve().parents[1]
base = Path.home() / 'Library/Application Support/BensonMail'
agent = Path.home() / 'Library/LaunchAgents/com.benson.codex-mail-163.plist'
domain = 'gui/' + str(os.getuid())
state = json.loads((base / 'mail_watch/state.json').read_text())
if state.get('pending'):
    raise RuntimeError('Pending mail exists. Finish current work before upgrading the daemon.')
backup = base / 'backups' / ('ui-' + datetime.datetime.now().strftime('%Y%m%d-%H%M%S'))
backup.mkdir(parents=True)
runtime_files = ('mail_daemon.py', 'mail_export.py', 'ai_api.py', 'ai_runner.py', 'mail_prompt.py')
for name in (*runtime_files, 'settings.json'):
    if (base / name).exists(): shutil.copy2(base / name, backup / name)
config_path = base / 'settings.json'
config = json.loads(config_path.read_text()) if config_path.exists() else {'enabled': True, 'output_dir': str(Path.home() / 'Documents/邮件'), 'interval_seconds': 60}
original_enabled = config.get('enabled', True)
def save():
    temporary = config_path.with_suffix('.tmp')
    temporary.write_text(json.dumps(config, ensure_ascii=False))
    temporary.chmod(0o600)
    temporary.replace(config_path)
def phase():
    return json.loads((base / 'mail_watch/service.json').read_text()).get('phase')

subprocess.run(['/bin/launchctl', 'bootout', domain, str(agent)], check=True)
try:
    for name in runtime_files:
        shutil.copy2(project / 'Runtime' / name, base / name)
    config['enabled'] = False
    save()
    subprocess.run(['/bin/launchctl', 'bootstrap', domain, str(agent)], check=True)
except BaseException:
    for name in runtime_files:
        if (backup / name).exists(): shutil.copy2(backup / name, base / name)
    config['enabled'] = original_enabled
    save()
    subprocess.run(['/bin/launchctl', 'bootstrap', domain, str(agent)], check=False)
    raise

try:
    for _ in range(20):
        if phase() == 'paused': break
        time.sleep(0.5)
    else: raise RuntimeError('New worker did not confirm paused state')
    print('Live worker: paused state confirmed; pending mail state preserved')
finally:
    config['enabled'] = original_enabled
    save()

app = Path.home() / 'Applications/邮件小秘书.app'
app.parent.mkdir(exist_ok=True)
if app.exists():
    subprocess.run(['/usr/bin/pkill', '-x', 'BensonMailMac'], check=False)
shutil.copytree(project / 'dist/邮件小秘书.app', app, dirs_exist_ok=True)
login = Path.home() / 'Library/LaunchAgents/com.benson.mail-ui.plist'
if not login.exists():
    login.write_bytes(plistlib.dumps({'Label': 'com.benson.mail-ui', 'ProgramArguments': ['/usr/bin/open', '-g', str(app), '--args', '--background'], 'RunAtLoad': True}))
    subprocess.run(['/bin/launchctl', 'bootstrap', domain, str(login)], check=True)
subprocess.run(['/usr/bin/open', str(app)], check=True)
print('Installed app:', app)
print('Runtime backup:', backup)
print('Worker interval:', config.get('interval_seconds', 60), 'seconds')
