import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from benson_mail.bridge import Controller
from benson_mail.mailbox_config import mailbox_id
from benson_mail.uninstall import clear_user_data, cleanup_installation


class FakeThread:
    def __init__(self): self.alive = False
    def is_alive(self): return self.alive


class FakeService:
    def __init__(self, config, secret, root, event, **kwargs):
        import threading
        self.config = config
        self.thread = FakeThread()
        self.cancel = threading.Event()
        self.checks = 0
    def start(self): self.thread.alive = True
    def stop(self): self.cancel.set(); self.thread.alive = False
    def join(self): pass
    def request_check(self): self.checks += 1
    def set_interval(self, value): self.config['interval'] = value


class MultipleMailTests(unittest.TestCase):
    def test_two_mailboxes_same_uid_and_subject_export_without_overwrite(self):
        from concurrent.futures import ThreadPoolExecutor
        from datetime import datetime, timezone
        from email.message import EmailMessage
        import threading
        from benson_mail.core import Service
        barrier = threading.Barrier(2)
        class Box:
            uids = [1]
            def __init__(self, account): self.account = account
            def snapshot(self): return 'same-validity', self.uids
            def fetch(self, uid):
                mail = EmailMessage()
                mail['From'] = self.account
                mail['Subject'] = '相同标题'
                mail.set_content('synthetic')
                return mail.as_bytes(), datetime(2026, 10, 17, 1, 0, tzinfo=timezone.utc)
        def analyze(message, _):
            barrier.wait(timeout=5)
            return '六项模拟报告 ' + message['sender']
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            services = []
            for account in ('first@example.invalid', 'second@example.invalid'):
                box = Box(account)
                service = Service({'account': account, 'output_dir': str(root / 'reports')},
                                  'synthetic', root / 'state', lambda _: None, mailbox=box, analyzer=analyze)
                service.check_once()
                box.uids = [1, 2]
                services.append(service)
            with ThreadPoolExecutor(max_workers=2) as pool:
                for future in [pool.submit(s.check_once) for s in services]:
                    future.result()
            paths = list((root / 'reports').glob('*/*.txt'))
            self.assertEqual(len(paths), 2)
            self.assertEqual({p.read_text(encoding='utf-8').split()[-1] for p in paths},
                             {'first@example.invalid', 'second@example.invalid'})
            self.assertEqual(len(list((root / 'state').glob('*.json'))), 2)

    def test_add_two_accounts_restart_toggle_and_check_without_mixing(self):
        with tempfile.TemporaryDirectory() as temporary, \
             patch('benson_mail.bridge.platform.save_secret', side_effect=lambda p, *_: p.write_bytes(b'encrypted')), \
             patch('benson_mail.bridge.platform.load_secret', return_value='SYNTHETIC'), \
             patch('benson_mail.bridge.platform.set_autostart'), \
             patch('benson_mail.bridge.Service', FakeService):
            root = Path(temporary)
            controller = Controller(root, lambda _: None)
            for account, host in [('one@example.invalid', 'imap.example.invalid'), ('two@qq.com', 'imap.qq.com')]:
                controller.command('select_mail', {'id': ''})
                controller.command('save_mail', {'account': account, 'host': host, 'secret': 'SYNTHETIC',
                    'output_dir': str(root / 'reports')})
            config = controller.command('config', {})
            self.assertEqual(len(config['mailboxes']), 2)
            self.assertNotIn('SYNTHETIC', (root / 'config.json').read_text())
            controller.config.update(ai_provider='codex', codex_command=['fixture'])
            controller.persist()
            # Reopening loads both saved accounts and their individual credentials.
            controller = Controller(root, lambda _: None)
            controller.command('start', {})
            self.assertEqual(len(controller.services), 2)
            self.assertEqual({s.config['account'] for s in controller.services.values()},
                             {'one@example.invalid', 'two@qq.com'})
            controller.command('check', {})
            self.assertEqual([s.checks for s in controller.services.values()], [1, 1])
            first, second = [p['id'] for p in config['mailboxes']]
            controller.command('mail_enabled', {'id': first, 'enabled': False})
            self.assertFalse(controller.services[first].thread.is_alive())
            self.assertTrue(controller.services[second].thread.is_alive())
            controller.command('select_mail', {'id': first})
            self.assertEqual(controller.config['account'], 'one@example.invalid')
            controller.command('mail_enabled', {'id': first, 'enabled': True})
            self.assertTrue(controller.services[first].thread.is_alive())
            controller.command('shutdown', {})
            self.assertFalse(controller.active())

    def test_preserve_only_configuration_and_encrypted_secrets(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / 'data'
            root.mkdir()
            original = b'{"account":"synthetic@example.invalid","api_model":"fixture"}'
            (root / 'config.json').write_bytes(original)
            for name in ['secret.bin', 'mail-secrets/hash.bin', 'api-keys/hash.bin']:
                path = root / name
                path.parent.mkdir(exist_ok=True)
                path.write_bytes(b'encrypted')
            (root / 'mail-secrets/cache.txt').write_text('remove')
            (root / 'state').mkdir()
            (root / 'state/mail.json').write_text('cached email body')
            clear_user_data(root, True)
            self.assertEqual((root / 'config.json').read_bytes(), original)
            self.assertEqual((root / 'mail-secrets/hash.bin').read_bytes(), b'encrypted')
            self.assertTrue((root / 'api-keys/hash.bin').exists())
            self.assertFalse((root / 'state').exists())
            self.assertFalse((root / 'mail-secrets/cache.txt').exists())
            clear_user_data(root, False)
            self.assertFalse(root.exists())

    def test_reports_inside_removed_data_are_relocated_and_retained_config_updated(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            program = root / 'BensonMail-202610171200'
            (program / '_internal').mkdir(parents=True)
            data = root / 'data'
            day = data / 'reports/2026-10-17'
            day.mkdir(parents=True)
            report = day / 'synthetic.txt'
            report.write_text('keep report')
            report.with_suffix('.mail.json').write_text(json.dumps(
                {'subject': 'synthetic', 'sender': 'fixture', 'received': '2026-10-17'}))
            (data / 'config.json').write_text(json.dumps({'output_dir': str(day.parent)}))
            documents = root / 'documents'
            documents.mkdir()
            with patch('benson_mail.platform_windows.set_autostart'), \
                 patch('benson_mail.platform_windows.documents_dir', return_value=documents), \
                 patch('benson_mail.uninstall.remove_shortcuts'):
                cleanup_installation(program, data, False, lambda _: None, keep_configuration=True)
            self.assertFalse(program.exists())
            saved = Path(json.loads((data / 'config.json').read_text(encoding='utf-8'))['output_dir'])
            self.assertTrue(saved.is_relative_to(documents))
            self.assertEqual((saved / '2026-10-17/synthetic.txt').read_text(), 'keep report')
