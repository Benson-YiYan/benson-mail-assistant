import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from benson_mail.bridge import Controller
from benson_mail.mailbox_config import mailbox_id
from benson_mail.uninstall import clear_user_data


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
