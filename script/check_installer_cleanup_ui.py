"""Drive real Setup's completed page; exercise both unchecked and selected cleanup."""
import ctypes
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time

from pywinauto import Desktop
from pywinauto.keyboard import send_keys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from benson_mail.uninstall import cleanup_installation


def wait(predicate, seconds=90):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        value = predicate()
        if value:
            return value
        time.sleep(.2)
    raise AssertionError('Timed out waiting for installer UI')


def wizard_window():
    for window in Desktop(backend='win32').windows(class_name='TWizardForm', visible_only=True):
        return window


def main():
    setup, evidence = map(lambda x: Path(x).resolve(), sys.argv[1:3])
    result = {'ok': False, 'cases': []}
    fixture = Path(tempfile.mkdtemp(prefix='BensonMail-cleanup-ui-'))
    try:
        for selected in (False, True):
            folder = fixture / ('selected' if selected else 'default')
            folder.mkdir()
            # A renamed source also has to work: the original selected path owns the hash.
            source = folder / ('My Mail Installer.exe' if selected else setup.name)
            shutil.copy2(setup, source)
            app = folder / 'BensonMail'
            process = subprocess.Popen([str(source), '/SP-', '/LANG=english', '/DIR=' + str(app),
                '/TASKS=!desktopapp,!desktopuninstall,!startapp,!startuninstall', '/NORESTART'],
                cwd=tempfile.gettempdir())
            try:
                wizard = wait(wizard_window)
                deadline = time.monotonic() + 150
                while time.monotonic() < deadline:
                    buttons = {b.window_text().replace('&', '').strip(): b for b in
                        wizard.descendants(class_name='TNewButton') if b.is_visible() and b.is_enabled()}
                    if 'Finish' in buttons:
                        break
                    print('Installer buttons:', list(buttons), flush=True)
                    button = next((button for name, button in buttons.items() if name.startswith('Next') or name == 'Install'), None)
                    if button:
                        button.click()
                    time.sleep(.3)
                else:
                    wizard.capture_as_image().save(str(evidence / 'installer-cleanup-stuck.png'))
                    (evidence / 'installer-cleanup-stuck.json').write_text(json.dumps([(c.class_name(), c.window_text()) for c in wizard.descendants()], ensure_ascii=False, indent=2), encoding='utf-8')
                    raise AssertionError('Completed page never appeared')
                lists = [control for control in wizard.descendants(class_name='TNewCheckListBox') if control.is_visible()]
                assert len(lists) == 1, 'Expected the standard completed-page action list'
                actions = lists[0]
                assert actions.send_message(0x018B) == 2, 'Expected Open app and Delete installer actions'
                labels = []
                for index in range(2):
                    buffer = ctypes.create_unicode_buffer(1024)
                    ctypes.windll.user32.SendMessageW(actions.handle, 0x0189, index, buffer)
                    labels.append(buffer.value)
                assert any('Delete this installer' in text for text in labels), labels
                # Open app is selected by default; turn it off so UI tests never load accounts.
                actions.set_focus()
                send_keys('{HOME}{SPACE}')
                if selected:
                    send_keys('{DOWN}{SPACE}')
                assert source.exists(), 'Installer deleted while its completed page was still open'
                assert (app / 'MailWorker.exe').is_file()
                wizard.capture_as_image().save(str(evidence / ('installer-cleanup-selected.png' if selected else 'installer-cleanup-default.png')))
                buttons['Finish'].click()
                process.wait(timeout=30)
                if selected:
                    wait(lambda: not source.exists(), 45)
                else:
                    time.sleep(2)
                    assert source.exists(), 'Default unchecked action deleted the installer'
                assert (app / 'MailWorker.exe').is_file() and list(app.glob('BensonMail-*.exe'))
                assert (app / '_internal').is_dir(), 'Cleanup damaged the installed application'
                result['cases'].append({'selected': selected, 'installer_retained': source.exists(),
                    'installed_app_intact': True, 'source_present_before_finish': True})
            finally:
                if process.poll() is None:
                    process.terminate()
                    process.wait(timeout=20)
                if (app / '.benson-installed.json').exists():
                    cleanup_installation(app, folder / 'synthetic-data', False, lambda _: None)
        result['ok'] = True
    except Exception as error:
        result['error'] = repr(error)
        raise
    finally:
        (evidence / 'installer-cleanup-ui-result.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
        shutil.rmtree(fixture, ignore_errors=True)


if __name__ == '__main__':
    main()
