import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
from benson_mail.mailbox_config import PRESETS, normalize, mailbox_id, state_identity, connect, folder_name, parse_list_folders
from benson_mail.bridge import Controller

class MailConnectionTests(unittest.TestCase):
    def config(self, **values):
        return {'account': 'demo@example.invalid', 'host': 'imap.example.invalid', **values}
    def test_presets_and_custom_configuration(self):
        self.assertEqual(len({p['id'] for p in PRESETS}), len(PRESETS))
        self.assertTrue({'qq', 'gmail', 'outlook', 'icloud', 'custom'} <= {p['id'] for p in PRESETS})
        c = normalize(self.config(username='corporate\\demo', port=1993, mail_folder='客户 & 合同'))
        self.assertEqual(c['port'], 1993)
        self.assertEqual(c['username'], 'corporate\\demo')
        self.assertIn('&-', folder_name(c['mail_folder']))
        self.assertTrue(folder_name(c['mail_folder']).isascii())
    def test_validation_rejects_invalid_server_and_unencrypted_login(self):
        for field, value in [('host', 'https://imap.example.com/a'), ('host', 'bad..host'),
                             ('port', 0), ('port', 65536), ('port', '993.5'), ('port', True),
                             ('security', 'plain'), ('mail_auth', 'guess'), ('username', 'u\nx')]:
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                normalize(self.config(**{field: value}))
    def test_progress_isolated_by_connection_and_legacy_progress_preserved(self):
        old = self.config(host='imap.163.com')
        expected = hashlib.sha256(b'demo@example.invalid|imap.163.com').hexdigest()[:24]
        self.assertEqual(state_identity(old), expected)
        base = mailbox_id(old)
        for field, value in [('host', 'mail.example.invalid'), ('port', 1993),
                             ('security', 'starttls'), ('username', 'alternate'),
                             ('mail_folder', 'Archive'), ('mail_auth', 'oauth2')]:
            self.assertNotEqual(mailbox_id({**old, field: value}), base)
            self.assertNotEqual(state_identity({**old, field: value}), expected)
    def test_all_folder_list_parser_skips_unselectable_and_decodes_names(self):
        rows = [
            b'(\\HasNoChildren) "/" "INBOX"',
            b'(\\HasNoChildren \\Sent) "/" "Sent"',
            b'(\\Noselect) "/" "Root"',
            b'(\\HasNoChildren) "/" "&U,BTFw-"',
            (b'(\\HasNoChildren) "/" {7}', b'Archive'),
        ]
        folders = parse_list_folders(rows)
        self.assertEqual([item['name'] for item in folders], ['Archive', 'INBOX', 'Sent', '台北'])
        self.assertIn('\\Sent', next(item['flags'] for item in folders if item['name'] == 'Sent'))
    def test_ssl_uses_custom_port_username_and_readonly_folder(self):
        client = Mock(capabilities=(b'IMAP4rev1',))
        client.login.return_value = ('OK', [])
        client.authenticate.return_value = ('OK', [])
        client.capability.return_value = ('OK', [b'IMAP4rev1'])
        client.select.return_value = ('OK', [b'0'])
        context = Mock()
        with patch('benson_mail.mailbox_config.imaplib.IMAP4_SSL', return_value=client) as ssl:
            connect(self.config(port=1993, username='login-user', mail_folder='Archive'), 'SYNTHETIC', context)
        ssl.assert_called_once_with('imap.example.invalid', 1993, ssl_context=context, timeout=25)
        client.login.assert_called_once_with('login-user', 'SYNTHETIC')
        client.select.assert_called_once_with('"Archive"', readonly=True)
        client._simple_command.assert_not_called()
    def test_starttls_precedes_login_and_failure_never_sends_credentials(self):
        events = []
        client = Mock(capabilities=())
        client.login.return_value = ('OK', [])
        client.authenticate.return_value = ('OK', [])
        client.capability.return_value = ('OK', [b'IMAP4rev1'])
        client.select.return_value = ('OK', [])
        client.starttls.side_effect = lambda **kwargs: (events.append('tls') or ('OK', []))
        client.login.side_effect = lambda *args: (events.append('login') or ('OK', []))
        with patch('benson_mail.mailbox_config.imaplib.IMAP4', return_value=client):
            connect(self.config(security='starttls', port=143), 'SYNTHETIC', Mock())
        self.assertEqual(events, ['tls', 'login'])
        client.login.reset_mock()
        client.starttls.side_effect = OSError('synthetic TLS failure')
        with patch('benson_mail.mailbox_config.imaplib.IMAP4', return_value=client), self.assertRaises(RuntimeError):
            connect(self.config(security='starttls'), 'SYNTHETIC', Mock())
        client.login.assert_not_called()
        client.logout.assert_called()
    def test_oauth2_is_sasl_xoauth2_not_password_login(self):
        client = Mock(capabilities=(b'AUTH=XOAUTH2',))
        client.login.return_value = ('OK', [])
        client.authenticate.return_value = ('OK', [])
        client.capability.return_value = ('OK', [b'IMAP4rev1'])
        client.select.return_value = ('OK', [])
        with patch('benson_mail.mailbox_config.imaplib.IMAP4_SSL', return_value=client):
            connect(self.config(mail_auth='oauth2'), 'SYNTHETIC_TOKEN', Mock())
        client.login.assert_not_called()
        mechanism, callback = client.authenticate.call_args.args
        self.assertEqual(mechanism, 'XOAUTH2')
        self.assertEqual(callback(b''), b'user=demo@example.invalid\x01auth=Bearer SYNTHETIC_TOKEN\x01\x01')
        self.assertEqual(callback(b'error-challenge'), b'')
    def test_managed_oauth_refresh_is_persisted_before_imap_auth(self):
        client = Mock(capabilities=(b'AUTH=XOAUTH2',))
        client.authenticate.return_value = ('OK', [])
        client.capability.return_value = ('OK', [b'IMAP4rev1'])
        client.select.return_value = ('OK', [b'0'])
        old_secret = json.dumps({
            'schema': 1, 'provider': 'google', 'email': 'demo@example.invalid',
            'client_id': 'demo.apps.googleusercontent.com',
            'access_token': 'EXPIRED_ACCESS', 'refresh_token': 'OLD_REFRESH',
            'expires_at': 1,
        })
        updated = {
            'schema': 1, 'provider': 'google', 'email': 'demo@example.invalid',
            'client_id': 'demo.apps.googleusercontent.com',
            'access_token': 'NEW_ACCESS', 'refresh_token': 'ROTATED_REFRESH',
            'expires_at': 9999999999, 'scope': 'https://mail.google.com/',
            'token_type': 'Bearer',
        }
        persisted = []
        events = []
        client.authenticate.side_effect = lambda mechanism, callback: (
            events.append('authenticate'), ('OK', [callback(b'')])
        )[1]
        config = self.config(
            host='imap.gmail.com', port=993, security='ssl',
            mail_provider='gmail', mail_auth='oauth2', oauth_mode='managed',
            oauth_client_id='demo.apps.googleusercontent.com',
            _oauth_secret_update=lambda secret: (events.append('persist'), persisted.append(secret)),
        )
        with patch('benson_mail.mailbox_config.imaplib.IMAP4_SSL', return_value=client), \
             patch('benson_mail.oauth_client.access_token', return_value=('NEW_ACCESS', updated)):
            connect(config, old_secret, Mock())
        self.assertEqual(events, ['persist', 'authenticate'])
        self.assertEqual(json.loads(persisted[0]), updated)
        mechanism, callback = client.authenticate.call_args.args
        self.assertEqual(mechanism, 'XOAUTH2')
        self.assertIn(b'Bearer NEW_ACCESS', callback(b''))
        self.assertNotIn(b'ROTATED_REFRESH', callback(b''))

    def test_legacy_oauth_token_is_not_rewritten(self):
        client = Mock(capabilities=(b'AUTH=XOAUTH2',))
        client.authenticate.return_value = ('OK', [])
        client.capability.return_value = ('OK', [b'IMAP4rev1'])
        client.select.return_value = ('OK', [b'0'])
        persist = Mock()
        with patch('benson_mail.mailbox_config.imaplib.IMAP4_SSL', return_value=client):
            connect(self.config(mail_auth='oauth2', _oauth_secret_update=persist), 'LEGACY_ACCESS_TOKEN', Mock())
        persist.assert_not_called()
    def test_rotated_secret_storage_failure_stops_before_auth_and_redacts_error(self):
        client = Mock(capabilities=(b'AUTH=XOAUTH2',))
        persist = Mock(side_effect=OSError('ROTATED_REFRESH_PRIVATE'))
        updated = {
            'schema': 1, 'provider': 'google', 'email': 'demo@example.invalid',
            'client_id': 'demo.apps.googleusercontent.com',
            'access_token': 'NEW_ACCESS_PRIVATE', 'refresh_token': 'ROTATED_REFRESH_PRIVATE',
            'expires_at': 9999999999,
        }
        with patch('benson_mail.mailbox_config.imaplib.IMAP4_SSL', return_value=client), \
             patch('benson_mail.oauth_client.access_token', return_value=('NEW_ACCESS_PRIVATE', updated)), \
             self.assertRaises(RuntimeError) as error:
            connect(self.config(
                host='imap.gmail.com', port=993, security='ssl',
                mail_provider='gmail', mail_auth='oauth2', oauth_mode='managed',
                oauth_client_id='demo.apps.googleusercontent.com',
                _oauth_secret_update=persist,
            ), 'SYNTHETIC_BUNDLE', Mock())
        persist.assert_called_once()
        client.authenticate.assert_not_called()
        self.assertNotIn('ROTATED_REFRESH_PRIVATE', str(error.exception))
        self.assertNotIn('NEW_ACCESS_PRIVATE', str(error.exception))

    def test_managed_oauth_refresh_lock_reloads_rotated_bundle_for_concurrent_checks(self):
        from concurrent.futures import ThreadPoolExecutor
        from threading import Barrier
        import time
        from benson_mail.mailbox_config import managed_oauth_token

        updated = {
            'schema': 1, 'provider': 'google', 'email': 'demo@example.invalid',
            'client_id': 'demo.apps.googleusercontent.com',
            'access_token': 'ACCESS_ONE', 'refresh_token': 'ROTATED_REFRESH',
            'expires_at': 9999999999, 'token_type': 'Bearer',
        }
        state = {'secret': 'INITIAL_BUNDLE'}
        observed = []
        persisted = []
        barrier = Barrier(3)

        def access_token(secret, _options):
            observed.append(secret)
            if secret == 'INITIAL_BUNDLE':
                time.sleep(0.03)
                return 'ACCESS_ONE', updated
            return 'ACCESS_TWO', None

        def persist(secret):
            persisted.append(secret)
            state['secret'] = secret

        config = self.config(
            host='imap.gmail.com', port=993, security='ssl',
            mail_provider='gmail', mail_auth='oauth2', oauth_mode='managed',
            oauth_client_id='demo.apps.googleusercontent.com',
            secret_binding='mailbox:concurrent-refresh-test',
            _oauth_secret_provider=lambda: state['secret'],
            _oauth_secret_update=persist,
        )

        def refresh():
            barrier.wait()
            return managed_oauth_token(config, 'STALE_FALLBACK')

        with patch('benson_mail.oauth_client.access_token', side_effect=access_token):
            with ThreadPoolExecutor(max_workers=2) as pool:
                futures = [pool.submit(refresh) for _ in range(2)]
                barrier.wait()
                results = [future.result(timeout=5) for future in futures]

        self.assertCountEqual(results, ['ACCESS_ONE', 'ACCESS_TWO'])
        self.assertEqual(len(persisted), 1)
        self.assertEqual(len(observed), 2)
        self.assertEqual(observed[0], 'INITIAL_BUNDLE')
        self.assertEqual(json.loads(observed[1])['refresh_token'], 'ROTATED_REFRESH')
        self.assertEqual(state['secret'], persisted[0])

    def test_managed_oauth_refresh_fails_closed_without_secure_writer(self):
        from benson_mail.mailbox_config import managed_oauth_token

        updated = {
            'schema': 1, 'provider': 'google', 'email': 'demo@example.invalid',
            'client_id': 'demo.apps.googleusercontent.com',
            'access_token': 'ACCESS_PRIVATE', 'refresh_token': 'ROTATED_PRIVATE',
            'expires_at': 9999999999,
        }
        config = self.config(
            host='imap.gmail.com', port=993, security='ssl',
            mail_provider='gmail', mail_auth='oauth2', oauth_mode='managed',
            oauth_client_id='demo.apps.googleusercontent.com',
            _oauth_secret_provider=lambda: 'INITIAL_BUNDLE',
        )
        with patch('benson_mail.oauth_client.access_token',
                   return_value=('ACCESS_PRIVATE', updated)), self.assertRaisesRegex(
                       RuntimeError, 'secure storage is unavailable'
                   ) as error:
            managed_oauth_token(config, 'STALE_FALLBACK')
        self.assertNotIn('ROTATED_PRIVATE', str(error.exception))
        self.assertNotIn('ACCESS_PRIVATE', str(error.exception))

class MailSecretBindingTests(unittest.TestCase):
    def test_endpoint_change_requires_new_secret_and_keeps_previous_encrypted_file(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); controller = Controller(root, lambda _: None)
            old = {'account': 'demo@163.com', 'host': 'imap.163.com', 'output_dir': str(root/'reports')}
            controller.config.update(old)
            (root/'secret.bin').write_bytes(b'LEGACY_ENCRYPTED')
            with patch('benson_mail.bridge.platform.load_secret', return_value='SYNTHETIC'):
                with self.assertRaisesRegex(ValueError, '重新填写'):
                    controller.command('save_mail', {**old, 'host': 'new.example.invalid', 'secret': ''})
            with patch('benson_mail.bridge.platform.save_secret') as save, patch('benson_mail.bridge.platform.set_autostart'):
                controller.command('save_mail', {**old, 'host': 'new.example.invalid', 'secret': 'NEW_SYNTHETIC'})
            self.assertEqual((root/'secret.bin').read_bytes(), b'LEGACY_ENCRYPTED')
            self.assertTrue(save.call_args.args[1].startswith('mailbox:'))
            self.assertNotIn('NEW_SYNTHETIC', (root/'config.json').read_text())
            self.assertEqual(controller.config['host'], 'new.example.invalid')
