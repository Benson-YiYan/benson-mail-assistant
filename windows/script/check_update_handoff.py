"""Real Setup plus production native handoff, against a synthetic legacy installation."""
import ctypes
from ctypes import wintypes
import hashlib
import json
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
from benson_mail.uninstall import remove_shortcuts


def wait_until(predicate, seconds, message):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if predicate(): return
        time.sleep(.1)
    raise AssertionError(message)


def process_exit(pid):
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.OpenProcess.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD]; kernel.OpenProcess.restype=wintypes.HANDLE
    kernel.WaitForSingleObject.argtypes=[wintypes.HANDLE,wintypes.DWORD]
    kernel.GetExitCodeProcess.argtypes=[wintypes.HANDLE,ctypes.POINTER(wintypes.DWORD)]
    kernel.CloseHandle.argtypes=[wintypes.HANDLE]
    handle=kernel.OpenProcess(0x100000|0x1000,False,pid)
    if not handle: return 0  # Already exited after its confirmed installed marker.
    try:
        assert kernel.WaitForSingleObject(handle,120000)==0,'Setup did not finish'
        result=wintypes.DWORD(); assert kernel.GetExitCodeProcess(handle,ctypes.byref(result))
        return result.value
    finally: kernel.CloseHandle(handle)


def main():
    package=Path(sys.argv[1]).resolve(); setup=Path(sys.argv[2]).resolve(); evidence=Path(sys.argv[3]).resolve()
    version=re.fullmatch(r'BensonMail-Windows-x64-Setup-(\d{12})\.exe',setup.name).group(1)
    fixture=Path(tempfile.mkdtemp(prefix='BensonMail-uninstall-fixture-')).resolve()
    (fixture/'.benson-uninstall-fixture').write_text('Offline update fixture only')
    program=fixture/'BensonMail-200001010000'
    checks=[]
    try:
        shutil.copytree(package,program)
        (program/f'BensonMail-{version}.exe').rename(program/'BensonMail-200001010000.exe')
        (program/f'Uninstall-BensonMail-{version}.exe').rename(program/'Uninstall-BensonMail-200001010000.exe')
        (program/'build-version.txt').write_text('200001010000')
        (program/'.benson-installed.json').unlink(missing_ok=True)
        # Seed historical binary fixtures when provided by an isolated legacy build.
        legacy_samples=ROOT/'dist'/'legacy-migration-fixture'
        # Public source releases carry fingerprints, not duplicate legacy runtime binaries.
        # Replay actual binaries only when an isolated baseline rebuild supplied them.
        replayed_legacy_samples=legacy_samples.is_dir()
        obsolete=json.loads((ROOT/'evidence'/'legacy-payload-manifest.json').read_text())
        seeded=[]
        for source in legacy_samples.rglob('*'):
            if source.is_file():
                relative=source.relative_to(legacy_samples)
                target=program/relative
                assert not target.exists(), 'Sample is still required by current payload: '+str(relative)
                assert hashlib.sha256(source.read_bytes()).hexdigest()==obsolete[relative.as_posix()]
                target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,target);seeded.append(target)
        unrelated=program/'_internal'/'_tk_data'/'family-notes.txt'
        unrelated.parent.mkdir(parents=True,exist_ok=True);unrelated.write_text('Keep this unrelated user file')
        modified=program/'PresentationCore.dll'
        assert 'PresentationCore.dll' in obsolete
        modified.write_bytes(b'User-modified legacy filename must survive')
        data=fixture/'user-data';data.mkdir()
        config=data/'config.json';config.write_text('{"fixture":"preserve","enabled":false}')
        report=fixture/'reports'/'2026-10-18'/'Existing.md';report.parent.mkdir(parents=True);report.write_text('## Existing report')
        before=(config.read_bytes(),report.read_bytes())
        cache=fixture/'cache';cache.mkdir();cached=cache/setup.name;shutil.copy2(setup,cached)
        digest=hashlib.sha256(cached.read_bytes()).hexdigest()
        request=fixture/'request.json';result=fixture/'handoff.json'
        payload={'version':version,'sha256':digest,'installer':str(cached),'result':str(result)}
        launcher=program/'BensonMail-200001010000.exe'
        # Cancel only after a real Setup process starts, while its acknowledgment is deliberately delayed.
        request.write_text(json.dumps({**payload,'cancel':True}))
        cancelled=subprocess.run([str(launcher),'--install-update-fixture',str(request)],timeout=35,creationflags=subprocess.CREATE_NO_WINDOW)
        assert cancelled.returncode==0 and not result.exists(),'Cancelled handoff must not report success'
        cancel_attempt=json.loads((cache/'last-install-attempt.json').read_text())
        assert Path(cancel_attempt['status']).read_text().startswith('cancelled')
        process_exit(cancel_attempt['pid'])
        time.sleep(1)
        assert (program/'build-version.txt').read_text().strip()=='200001010000','Cancelled update ran after its parent exited'
        assert launcher.exists()
        checks.append('Cancellation waits for the actual uncommitted Setup process to exit; later app exit does not install anything')
        payload['relaunch']=str(fixture/'relaunch-result.json')
        request.write_text(json.dumps(payload))
        parent=subprocess.Popen([str(launcher),'--install-update-fixture',str(request)],creationflags=subprocess.CREATE_NO_WINDOW)
        assert parent.wait(timeout=35)==0,'Production handoff did not receive Setup acknowledgment'
        assert json.loads(result.read_text())['ok']
        attempt=json.loads((cache/'last-install-attempt.json').read_text())
        status=Path(attempt['status'])
        wait_until(lambda: status.exists() and status.read_text().startswith(('installed','failed')),150,'Setup completion was not reported')
        assert status.read_text().strip()=='installed\n'+version,status.read_text()
        assert process_exit(json.loads(result.read_text())['installer'])==0,'Setup returned a failure exit code'
        assert (program/'build-version.txt').read_text().strip()==version
        assert (program/f'BensonMail-{version}.exe').is_file()
        assert not launcher.exists(),'Old versioned executable was not replaced'
        relaunch=fixture/'relaunch-result.json'
        wait_until(relaunch.exists,30,'Setup did not reopen the newly installed executable')
        reopened=json.loads(relaunch.read_text())
        assert reopened['version']==version and Path(reopened['launcher']).resolve()==(program/f'BensonMail-{version}.exe').resolve()
        assert process_exit(reopened['pid'])==0
        assert all(not path.exists() for path in seeded), 'Obsolete legacy dependencies remained after upgrade'
        assert unrelated.read_text()=='Keep this unrelated user file'
        assert modified.read_bytes()==b'User-modified legacy filename must survive'
        if replayed_legacy_samples:
            checks.append('Actual legacy WinForms, WPF, Tcl/Tk and Pillow files removed only after matching their baseline SHA256; unrelated and modified files preserved')
        else:
            checks.append('Legacy binary removal replay not run: public source builds ship fingerprints only; actual binary replay evidence is packaging/update-handoff-result.json from 202610181547')
        checks.append('Unrelated files and modified obsolete runtime filenames preserved by the real upgrade')
        checks.append('Real Setup relaunches the newly installed native executable; its actual build version is verified without loading any accounts')
        assert before==(config.read_bytes(),report.read_bytes()),'Update changed config or report bytes'
        log=Path(attempt['log']);shutil.copy2(log,evidence/'update-handoff-setup.log')
        assert 'Update handoff acknowledged' in log.read_text(encoding='utf-8-sig')
        checks.append('Production native handoff waits for real Setup acknowledgment before the old application exits')
        checks.append('Silent native Setup upgrades the original versioned legacy folder from 200001010000 to '+version)
        checks.append('Setup success marker follows new executable and build-version verification; original config and report bytes preserved')
        # A rejected target must give an actionable error while the original app remains installed.
        blocked=fixture/'OccupiedFolder';blocked.mkdir();unrelated=blocked/'user-document.txt';unrelated.write_text('keep')
        payload.update(target=str(blocked));request.write_text(json.dumps(payload));result.unlink()
        failure=subprocess.run([str(program/f'BensonMail-{version}.exe'),'--install-update-fixture',str(request)],timeout=35,creationflags=subprocess.CREATE_NO_WINDOW)
        assert failure.returncode==2,'Rejected Setup incorrectly reported handoff success'
        attempt=json.loads((cache/'last-install-attempt.json').read_text());rejected=Path(attempt['status']).read_text()
        assert rejected.startswith('failed') and len(rejected)>10
        assert not result.exists() and unrelated.read_text()=='keep'
        assert (program/'build-version.txt').read_text().strip()==version
        checks.append('Real Setup rejection is returned through the production handoff; no false success, no user file deletion')
        (evidence/'update-handoff-result.json').write_text(json.dumps({'ok':True,'from_version':'200001010000','version':version,'checks':checks},indent=2))
    finally:
        remove_shortcuts(program)
        platform.remove_uninstall_registration(program)
        shutil.rmtree(fixture,ignore_errors=True)


if __name__=='__main__': main()
