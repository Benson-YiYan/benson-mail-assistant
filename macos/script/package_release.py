"""Create a drag-to-Applications disk image, with no user settings or secrets."""
from pathlib import Path
import plistlib
import shutil
import subprocess
import sys
import tempfile

project = Path(__file__).resolve().parents[1]
def write_install_guides(stage, version, platform_name):
    """Keep disk-image help synchronized with the reviewed platform guides."""
    processor = {
        'AppleSilicon': {'zh': 'Apple 芯片 Mac', 'en': 'Apple silicon Mac', 'es': 'Mac con chip de Apple'},
        'Intel': {'zh': 'Intel Mac', 'en': 'Intel Mac', 'es': 'Mac con Intel'},
    }[platform_name]
    names = {'zh': '安装与使用.txt', 'en': 'Read me - English.txt', 'es': 'Léeme - Español.txt'}
    titles = {'zh': '邮件小秘书 Mac', 'en': 'Email Assistant for Mac', 'es': 'Asistente de correo electrónico para Mac'}
    requirements = {
        'zh': '适用：{processor}，macOS 14 或以上。',
        'en': 'For {processor}, macOS 14 or later.',
        'es': 'Para {processor}, macOS 14 o posterior.',
    }
    for code in ('zh', 'en', 'es'):
        body = (project / 'Resources' / f'Quick-start-{code}.txt').read_text(encoding='utf-8')
        header = f"{titles[code]} {version}\n\n" + requirements[code].format(processor=processor[code]) + "\n\n"
        (stage / names[code]).write_text(header + body, encoding='utf-8')


app = Path(sys.argv[2]).resolve() if len(sys.argv) > 2 else project / 'dist/邮件小秘书.app'
info = plistlib.loads((app / 'Contents/Info.plist').read_bytes())
version = info['CFBundleVersion']
destination = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else project / 'dist'
destination.mkdir(parents=True, exist_ok=True)
architectures = set(subprocess.check_output(
    ['/usr/bin/lipo', '-archs', str(app / 'Contents/MacOS/BensonMailMac')], text=True).split())
worker_architectures = set(subprocess.check_output(
    ['/usr/bin/lipo', '-archs', str(app / 'Contents/Resources/worker/MailWorker')], text=True).split())
if architectures == {'x86_64'}:
    platform_name, supported = 'Intel', 'Intel 芯片 Mac'
elif architectures == {'arm64'}:
    platform_name, supported = 'AppleSilicon', 'Apple 芯片 Mac（M1/M2/M3/M4 等）'
else:
    raise RuntimeError('Unsupported application architectures')
if not architectures.issubset(worker_architectures):
    raise RuntimeError('Application and bundled worker architectures do not match')
target = destination / f'BensonMail-Mac-{platform_name}-{version}.dmg'
subprocess.run(['/usr/bin/codesign', '--verify', '--deep', '--strict', str(app)], check=True)
for file in app.rglob('*'):
    if file.name in {'settings.json', 'state.json', 'secret.bin', 'mail.json', 'message.eml'}:
        raise RuntimeError('User data must not be packaged')
with tempfile.TemporaryDirectory(prefix='BensonMail-dmg-') as temporary:
    stage = Path(temporary)
    shutil.copytree(app, stage / app.name, symlinks=True)
    (stage / 'Applications').symlink_to('/Applications')
    write_install_guides(stage, version, platform_name)
    subprocess.run(['/usr/bin/hdiutil', 'create', '-volname', '邮件小秘书-' + version,
                    '-srcfolder', str(stage), '-ov', '-format', 'UDZO', str(target)], check=True)
print(target)
