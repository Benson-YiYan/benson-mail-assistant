import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "Runtime"))
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
from mailbox_config import PRESETS, normalize, mailbox_id, state_identity, connect, folder_name

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
    def test_ssl_uses_custom_port_username_and_readonly_folder(self):
        client = Mock(capabilities=(b'IMAP4rev1',))
        client.login.return_value = ('OK', [])
        client.capability.return_value = ('OK', [b'IMAP4rev1'])
        client.select.return_value = ('OK', [b'0'])
        context = Mock()
        with patch('mailbox_config.imaplib.IMAP4_SSL', return_value=client) as ssl:
            connect(self.config(port=1993, username='login-user', mail_folder='Archive'), 'SYNTHETIC', context)
        ssl.assert_called_once_with('imap.example.invalid', 1993, ssl_context=context, timeout=25)
        client.login.assert_called_once_with('login-user', 'SYNTHETIC')
        client.select.assert_called_once_with('"Archive"', readonly=True)
        client._simple_command.assert_not_called()
    def test_starttls_precedes_login_and_failure_never_sends_credentials(self):
        events = []
        client = Mock(capabilities=())
        client.capability.return_value = ('OK', [b'IMAP4rev1'])
        client.select.return_value = ('OK', [])
        client.starttls.side_effect = lambda **kwargs: (events.append('tls') or ('OK', []))
        client.login.side_effect = lambda *args: (events.append('login') or ('OK', []))
        with patch('mailbox_config.imaplib.IMAP4', return_value=client):
            connect(self.config(security='starttls', port=143), 'SYNTHETIC', Mock())
        self.assertEqual(events, ['tls', 'login'])
        client.login.reset_mock()
        client.starttls.side_effect = OSError('synthetic TLS failure')
        with patch('mailbox_config.imaplib.IMAP4', return_value=client), self.assertRaises(RuntimeError):
            connect(self.config(security='starttls'), 'SYNTHETIC', Mock())
        client.login.assert_not_called()
        client.logout.assert_called()
    def test_oauth2_is_sasl_xoauth2_not_password_login(self):
        client = Mock(capabilities=(b'AUTH=XOAUTH2',))
        client.authenticate.return_value = ('OK', [])
        client.capability.return_value = ('OK', [b'IMAP4rev1'])
        client.select.return_value = ('OK', [])
        with patch('mailbox_config.imaplib.IMAP4_SSL', return_value=client):
            connect(self.config(mail_auth='oauth2'), 'SYNTHETIC_TOKEN', Mock())
        client.login.assert_not_called()
        mechanism, callback = client.authenticate.call_args.args
        self.assertEqual(mechanism, 'XOAUTH2')
        self.assertEqual(callback(b''), b'user=demo@example.invalid\x01auth=Bearer SYNTHETIC_TOKEN\x01\x01')
        self.assertEqual(callback(b'error-challenge'), b'')
