"""Record exact bytes from the last self-contained release on a Windows runner.

The pinned installer runs only against an isolated temporary installation.
No mailbox, credentials or AI are used. Its native runtime samples allow the
real update integration test to check their removal after upgrading.
"""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import urllib.request

from payload_manifest import fingerprint

ROOT = Path(__file__).resolve().parent.parent
NAME = 'BensonMail-Windows-x64-Setup-202610181752.exe'
SHA256 = 'c0553133ccac0bfdde5c03df67380b33369f8d13ddbcc567c901b1089a214c77'
URL = 'https://github.com/Benson-YiYan/benson-mail-assistant/releases/download/v20261018.2/' + NAME
KEY = r'Software\Microsoft\Windows\CurrentVersion\Uninstall\BensonMail'


def main():
    if sys.platform != 'win32' or os.environ.get('GITHUB_ACTIONS') != 'true':
        raise RuntimeError('Shared-runtime migration capture requires a disposable Windows CI runner')
    import winreg
    evidence = ROOT / 'evidence'
    evidence.mkdir(exist_ok=True)
    # Avoid disturbing an existing registration on developer machines.
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, KEY):
            raise RuntimeError('Capture requires a clean disposable Windows user')
    except FileNotFoundError:
        pass
    fixture = Path(tempfile.mkdtemp(prefix='BensonMail-runtime-baseline-'))
    program = fixture / 'BensonMail'
    setup = fixture / NAME
    try:
        request = urllib.request.Request(URL, headers={'User-Agent': 'MailSecretary-migration-capture'})
        with urllib.request.urlopen(request, timeout=90) as response, setup.open('wb') as output:
            if not response.url.startswith('https://'):
                raise RuntimeError('Legacy installer redirected outside HTTPS')
            shutil.copyfileobj(response, output)
        with setup.open('rb') as source:
            if hashlib.file_digest(source, 'sha256').hexdigest() != SHA256:
                raise RuntimeError('Legacy installer SHA256 mismatch')
        subprocess.run([str(setup), '/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART',
                        '/SP-', '/TASKS=', '/DIR=' + str(program)],
                       check=True, timeout=180, creationflags=subprocess.CREATE_NO_WINDOW)
        actual = fingerprint(program)
        # Ignore installation-generated markers and metadata. Only the exact
        # shipped payload recorded inside the verified installer is removable.
        files = json.loads((program / '.benson-payload.json').read_text(encoding='utf-8'))
        if not files or any(actual.get(name) != digest for name, digest in files.items()):
            raise RuntimeError('Installed baseline does not match its recorded payload')
        samples = ('coreclr.dll', 'Microsoft.ui.xaml.dll', 'System.Private.CoreLib.dll')
        for name in samples:
            if name not in files:
                raise RuntimeError('Missing self-contained baseline runtime: ' + name)
        (evidence / 'self-contained-payload-manifest.json').write_text(
            json.dumps(files, indent=2), encoding='utf-8')
        target = ROOT / 'dist' / 'legacy-migration-fixture'
        target.mkdir(parents=True, exist_ok=True)
        for name in samples:
            shutil.copy2(program / name, target / name)
        (evidence / 'self-contained-baseline-capture.json').write_text(json.dumps({
            'version': '202610181752', 'installer_sha256': SHA256,
            'runtime_samples': {name: files[name] for name in samples},
            'file_count': len(files), 'reads_mail': False, 'ai_calls': 0,
        }, indent=2), encoding='utf-8')
        print('Captured exact self-contained 202610181752 runtime fingerprints')
    finally:
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, KEY) as key:
                location = winreg.QueryValueEx(key, 'InstallLocation')[0]
            if os.path.normcase(os.path.abspath(location)) == os.path.normcase(str(program)):
                winreg.DeleteKey(winreg.HKEY_CURRENT_USER, KEY)
        except FileNotFoundError:
            pass
        shutil.rmtree(fixture, ignore_errors=True)


if __name__ == '__main__':
    main()
