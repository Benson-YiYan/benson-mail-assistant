"""Controlled app replacement; never reads or writes mailbox/AI configuration."""
import json
import hashlib
import os
from pathlib import Path
import plistlib
import re
import shutil
import signal
import struct
import subprocess
import sys
import time
import uuid

BUNDLE_ID = 'com.benson.mail-ui'

def command(args):
    result = subprocess.run(args, capture_output=True, text=True, timeout=180)
    if result.returncode:
        raise RuntimeError(Path(args[0]).name + ': ' + (result.stderr.strip() or 'exit ' + str(result.returncode))[-1500:])
    return result.stdout

def architectures(binary):
    with binary.open('rb') as stream:
        header = stream.read(8)
        if len(header) != 8: raise RuntimeError('Incomplete Mach-O header')
        magic = header[:4]
        if magic in {b'\xcf\xfa\xed\xfe', b'\xce\xfa\xed\xfe', b'\xfe\xed\xfa\xcf', b'\xfe\xed\xfa\xce'}:
            endian = '<' if magic[0] in {0xcf, 0xce} else '>'
            cpu = struct.unpack(endian+'I', header[4:])[0]
            return {0x100000c:'arm64',0x1000007:'x86_64'}.get(cpu, 'unsupported').split()
        if magic not in {b'\xca\xfe\xba\xbe', b'\xca\xfe\xba\xbf', b'\xbe\xba\xfe\xca', b'\xbf\xba\xfe\xca'}:
            raise RuntimeError('Not a Mach-O executable')
        endian = '>' if magic[0] == 0xca else '<'
        count = struct.unpack(endian+'I', header[4:])[0]
        if count > 32: raise RuntimeError('Invalid Mach-O architecture count')
        width = 32 if magic in {b'\xca\xfe\xba\xbf', b'\xbf\xba\xfe\xca'} else 20
        found=[]
        for _ in range(count):
            record=stream.read(width)
            if len(record)!=width: raise RuntimeError('Incomplete universal Mach-O header')
            found.append({0x100000c:'arm64',0x1000007:'x86_64'}.get(struct.unpack(endian+'I',record[:4])[0],'unsupported'))
        return found

def validate(app, version, arch):
    info = plistlib.loads((app / 'Contents/Info.plist').read_bytes())
    if info.get('CFBundleIdentifier') != BUNDLE_ID or info.get('CFBundleVersion') != version:
        raise RuntimeError('App bundle identifier or target version mismatch')
    name = info.get('CFBundleExecutable')
    if name != 'BensonMailMac':
        raise RuntimeError('Unexpected application executable')
    if arch not in architectures(app / 'Contents/MacOS' / name):
        raise RuntimeError('App architecture does not match this Mac')
    command(['/usr/bin/codesign', '--verify', '--deep', '--strict', str(app)])

def prepare(request):
    workspace = Path(request['workspace']).resolve()
    previous = workspace / 'install-plan.json'
    if previous.exists():
        cleanup_staging(json.loads(previous.read_text()))
    target = Path(request['target']).resolve()
    if target.suffix != '.app' or str(target).startswith('/Volumes/') or '/AppTranslocation/' in str(target):
        raise RuntimeError('Install the app in a writable Applications folder before updating')
    if not target.is_dir() or not os.access(target.parent, os.W_OK):
        raise RuntimeError('Application installation folder is not writable: ' + str(target.parent))
    probe = target.parent / ('.BensonMail-probe-' + uuid.uuid4().hex)
    try:
        probe.mkdir(); probe.rmdir()
    except OSError:
        raise RuntimeError('No permission to replace the application in: ' + str(target.parent)) from None
    version, arch = request['version'], request['arch']
    if not re.fullmatch(r'\d{12}', version) or arch not in {'arm64', 'x86_64'}:
        raise RuntimeError('Invalid update identity')
    image = Path(request['dmg'])
    expected_hash = request['sha256']
    if not re.fullmatch(r'[a-fA-F0-9]{64}', expected_hash): raise RuntimeError('Invalid expected SHA256')
    digest = hashlib.sha256()
    with image.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024*1024), b''): digest.update(chunk)
    if digest.hexdigest() != expected_hash.lower(): raise RuntimeError('DMG SHA256 mismatch before mounting')
    if request.get('size') is not None and image.stat().st_size != request['size']: raise RuntimeError('DMG size mismatch before mounting')
    mount = workspace / 'mount'; mount.mkdir(exist_ok=True)
    stage = target.parent / ('.BensonMail-update-' + uuid.uuid4().hex + '.app')
    runtime = workspace / 'helper-runtime'
    plan_file = workspace / 'install-plan.json'
    def discard_preparation():
        if stage.exists(): shutil.rmtree(stage)
        if runtime.exists(): shutil.rmtree(runtime)
        plan_file.unlink(missing_ok=True)
    attached = False
    try:
        command(['/usr/bin/hdiutil', 'attach', '-readonly', '-nobrowse', '-plist', '-mountpoint', str(mount), request['dmg']])
        attached = True
        apps = [p for p in mount.iterdir() if p.suffix == '.app' and p.is_dir() and not p.is_symlink()]
        if len(apps) != 1:
            raise RuntimeError('Update image must contain exactly one application')
        validate(apps[0], version, arch)
        shutil.copytree(apps[0], stage, symlinks=True)
        validate(stage, version, arch)
        if runtime.exists(): shutil.rmtree(runtime)
        shutil.copytree(Path(sys.executable).parent, runtime, symlinks=True)
        plan = dict(target=str(target), stage=str(stage), workspace=str(workspace), version=version, arch=arch,
                    parent_pid=request['parent_pid'], marker=request['marker'], nonce=uuid.uuid4().hex, receipt=str(workspace/'startup-receipt.json'),
                    backup=str(target.parent / ('.BensonMail-backup-' + uuid.uuid4().hex + '.app')))
        plan_file.write_text(json.dumps(plan), encoding='utf-8')
        return dict(helper=str(runtime / Path(sys.executable).name), plan=str(plan_file))
    except Exception:
        discard_preparation()
        raise
    finally:
        if attached:
            detach_error = None
            for _ in range(2):
                try:
                    command(['/usr/bin/hdiutil', 'detach', str(mount)])
                    detach_error = None
                    break
                except Exception as error:
                    detach_error = error
            if detach_error is not None:
                discard_preparation()
                raise RuntimeError('Could not detach update image after two attempts; preparation cancelled and staging removed: ' + str(detach_error)) from detach_error

def cleanup_staging(plan):
    target, stage = Path(plan['target']), Path(plan['stage'])
    if stage.parent == target.parent and stage.name.startswith('.BensonMail-update-') and stage.suffix == '.app' and not stage.is_symlink():
        if stage.exists(): shutil.rmtree(stage)


def alive(pid):
    try:
        os.kill(pid, 0); return True
    except ProcessLookupError:
        return False

def swap(plan, launch, wait_ready, validate_app=validate, move=os.rename):
    """Same-filesystem renames, rollback on replacement or launch failure."""
    target, stage, backup = map(Path, (plan['target'], plan['stage'], plan['backup']))
    if target.parent != stage.parent or target.parent != backup.parent or backup.exists():
        raise RuntimeError('Unsafe update replacement paths')
    validate_app(stage, plan['version'], plan['arch'])
    moved = False
    try:
        move(target, backup); moved = True
        move(stage, target)
        launch(target)
        if not wait_ready(target): raise RuntimeError('Updated app did not confirm startup')
    except Exception:
        if moved:
            if target.exists(): shutil.rmtree(target)
            move(backup, target)
            launch(target)
        raise
    else:
        shutil.rmtree(backup)

def cleanup_after_exit(workspace):
    script = workspace.parent / ('.cleanup-' + uuid.uuid4().hex + '.sh')
    script.write_text('#!/bin/sh\nwhile kill -0 "$2" 2>/dev/null; do /bin/sleep 0.5; done\n/bin/rm -rf -- "$1"\n/bin/rm -f -- "$0"\n')
    script.chmod(0o700)
    subprocess.Popen(['/bin/sh', str(script), str(workspace), str(os.getpid())], cwd=str(workspace.parent), stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)

def install(plan):
    workspace = Path(plan['workspace'])
    result = workspace / 'installation-result.json'
    try:
        deadline = time.monotonic() + 120
        while alive(int(plan['parent_pid'])):
            if time.monotonic() > deadline: raise RuntimeError('Current app did not exit; original app was not replaced')
            time.sleep(.2)
        launches = 0
        def launch(app):
            nonlocal launches
            launches += 1
            if launches == 1:
                command(['/usr/bin/open', '-n', str(app), '--args', '--update-receipt', plan['receipt'], '--update-nonce', plan['nonce']])
            else:
                result.write_text(json.dumps({'ok': False, 'error': 'Update rolled back; original app restored'}))
                command(['/usr/bin/open', '-n', str(app)])
        def ready(app):
            expected = str(app / 'Contents/Resources/worker/MailWorker') + '|' + plan['version']
            deadline = time.monotonic() + 120
            while time.monotonic() < deadline:
                try:
                    receipt = json.loads(Path(plan['receipt']).read_text())
                    if (receipt.get('nonce') == plan['nonce'] and receipt.get('version') == plan['version']
                        and alive(int(receipt.get('pid', 0))) and Path(plan['marker']).read_text() == expected): return True
                except (OSError, ValueError, TypeError): pass
                time.sleep(.5)
            # Only terminate a failed updated executable at the exact expected path before rollback.
            executable = str(app / 'Contents/MacOS/BensonMailMac')
            for line in command(['/bin/ps', '-axo', 'pid=,comm=']).splitlines():
                fields = line.strip().split(None, 1)
                if len(fields) == 2 and fields[1] == executable:
                    try: os.kill(int(fields[0]), signal.SIGKILL)
                    except ProcessLookupError: pass
            return False
        swap(plan, launch, ready)
        result.write_text(json.dumps({'ok': True}))
        cleanup_after_exit(workspace)
    except Exception as error:
        cleanup_staging(plan)
        result.write_text(json.dumps({'ok': False, 'error': str(error)}), encoding='utf-8')
        # The copied runtime remains available for diagnostics; no partial target is left behind.
        return 1
    return 0

def main(args):
    operation, request_file, *extra = args
    request = json.loads(Path(request_file).read_text())
    if operation == 'abort':
        cleanup_staging(request); return 0
    if operation == 'prepare':
        try: result = dict(ok=True, **prepare(request))
        except Exception as error: result = dict(ok=False, error=str(error))
        Path(extra[0]).write_text(json.dumps(result), encoding='utf-8')
        return 0 if result['ok'] else 1
    return install(request)
