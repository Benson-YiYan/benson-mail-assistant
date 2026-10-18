"""Offline mailbox boundary diagnostics: never contact mail or AI services."""
import base64
import imaplib
import json
import socket
import ssl
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch
from benson_mail.mailbox_config import connect, MailConnectionError, redact_mail_error
from benson_mail.core import Service
from benson_mail.bridge import Controller

CONFIG = {'account':'demo@example.invalid', 'host':'imap.example.invalid'}
SECRET = 'SYNTHETIC-pA\\ss"密钥'


def client():
    result = Mock(capabilities=(b'IMAP4rev1',))
    for name in ('login', 'authenticate', 'starttls', 'select', '_simple_command'):
        getattr(result, name).return_value = ('OK', [b'done'])
    result.capability.return_value = ('OK', [b'IMAP4rev1 ID'])
    return result


class MailDiagnosticTests(unittest.TestCase):
    def failing(self, error, method='login', config=None):
        remote = client(); getattr(remote, method).side_effect = error
        with patch('benson_mail.mailbox_config.imaplib.IMAP4_SSL', return_value=remote):
            with self.assertRaises(MailConnectionError) as caught:
                connect(config or CONFIG, SECRET, Mock())
        remote.logout.assert_called_once()
        return str(caught.exception)

    def test_auth_rejection_safe_response_and_bridge_visibility(self):
        diagnostic = self.failing(imaplib.IMAP4.error('[AUTHENTICATIONFAILED] invalid credentials '+SECRET))
        for expected in ('LOGIN', 'imap.example.invalid:993', 'IMAP4.error:', 'AUTHENTICATIONFAILED', '拒绝认证'):
            self.assertIn(expected, diagnostic)
        self.assertNotIn(SECRET, diagnostic)
        with tempfile.TemporaryDirectory() as root:
            controller = Controller(root, lambda _:None); controller.config.update(CONFIG)
            with patch.object(controller, 'secret', return_value=SECRET), patch('benson_mail.bridge.IMAPMailbox', side_effect=MailConnectionError(diagnostic)):
                with self.assertRaisesRegex(RuntimeError, 'AUTHENTICATIONFAILED'):
                    controller.command('test_mail', {})

    def test_english_diagnostic_keeps_safe_server_response(self):
        diagnostic=self.failing(imaplib.IMAP4.error('[AUTHENTICATIONFAILED] login failed '+SECRET),config={**CONFIG,'ui_language':'en'})
        for expected in ('Mailbox connection failed', 'Server: imap.example.invalid:993', 'Stage: LOGIN authentication', 'IMAP4.error', '[AUTHENTICATIONFAILED]'):
            self.assertIn(expected,diagnostic)
        self.assertNotIn(SECRET,diagnostic)

    def test_credential_variants_never_exposed(self):
        raw = SECRET.encode()
        oauth = f'user=demo@example.invalid\x01auth=Bearer {SECRET}\x01\x01'.encode()
        variants = [SECRET, repr(raw), base64.b64encode(raw).decode(), base64.b64encode(oauth).decode(), json.dumps(SECRET)[1:-1], SECRET.replace('\\','\\\\').replace('"','\\"')]
        for variant in variants:
            with self.subTest(variant=variant):
                cleaned = self.failing(imaplib.IMAP4.error('server echo '+variant))
                self.assertNotIn(variant, cleaned)
                self.assertNotIn(SECRET, cleaned)
                self.assertIn('已隐藏凭据', cleaned)

    def test_unsafe_imap_disabled_and_unknown_not_guessed(self):
        self.assertIn('判定登录不安全', self.failing(imaplib.IMAP4.error('SELECT Unsafe Login!'), 'select'))
        self.assertIn('IMAP 未开启', self.failing(imaplib.IMAP4.error('IMAP is disabled')))
        unknown=self.failing(imaplib.IMAP4.error('unclassified server refusal'))
        self.assertIn('尚不能确定原因',unknown); self.assertIn('unclassified server refusal',unknown)

    def test_post_auth_capability_id_and_select_failures(self):
        remote=client()
        with patch('benson_mail.mailbox_config.imaplib.IMAP4_SSL', return_value=remote):
            self.assertIs(connect(CONFIG, SECRET, Mock()), remote)
        self.assertNotIn(b'ID',remote.capabilities)
        remote.capability.assert_called_once(); remote._simple_command.assert_called_once()
        remote=client(); remote.capability.return_value=('OK',[b'IMAP4rev1'])
        remote.capabilities=(b'IMAP4rev1',b'ID')
        with patch('benson_mail.mailbox_config.imaplib.IMAP4_SSL', return_value=remote):
            connect(CONFIG,SECRET,Mock())
        remote._simple_command.assert_not_called()
        self.assertIn('ID', self.failing(imaplib.IMAP4.error('ID rejected'), '_simple_command'))
        for operation, expected in (('_simple_command','ID 客户端'), ('select','SELECT 只读'), ('capability','CAPABILITY')):
            remote=client(); getattr(remote,operation).return_value=('NO',[b'Permission denied'])
            with patch('benson_mail.mailbox_config.imaplib.IMAP4_SSL', return_value=remote), self.assertRaises(MailConnectionError) as caught:
                connect(CONFIG, SECRET, Mock())
            self.assertIn(expected,str(caught.exception)); self.assertIn('Permission denied',str(caught.exception))
            remote.logout.assert_called_once()

    def test_dns_timeout_and_tls_diagnostics(self):
        for error, expected in ((socket.gaierror(-2,'name not known'),'DNS'), (TimeoutError('timed out'),'25 秒'), (ssl.SSLCertVerificationError(1,'certificate verify failed'),'证书验证'), (ssl.SSLError('wrong version number'),'加密协商')):
            with patch('benson_mail.mailbox_config.imaplib.IMAP4_SSL', side_effect=error), self.assertRaises(MailConnectionError) as caught:
                connect(CONFIG, SECRET, Mock())
            text=str(caught.exception); self.assertIn(expected,text); self.assertIn('SSL/TLS 连接',text)
        remote=client(); remote.starttls.side_effect=ssl.SSLError('TLS handshake refused')
        with patch('benson_mail.mailbox_config.imaplib.IMAP4',return_value=remote), self.assertRaisesRegex(MailConnectionError,'STARTTLS'):
            connect({**CONFIG,'security':'starttls','port':143},SECRET,Mock())
        remote.login.assert_not_called()

    def test_test_mail_snapshot_failure_preserves_sanitized_diagnostic(self):
        with tempfile.TemporaryDirectory() as root:
            controller=Controller(root,lambda _:None); controller.config.update(CONFIG)
            cases=[(('UIDVALIDITY',[b'123']), imaplib.IMAP4.error('SEARCH refused '+SECRET), 'UID SEARCH'),
                   (('UIDVALIDITY',[None]), None, 'UIDVALIDITY'),
                   (('UIDVALIDITY',[b'123']), ('NO',[b'Search unavailable']), 'UID SEARCH')]
            for identity, search, stage in cases:
                remote=client(); remote.response.return_value=identity
                if isinstance(search,Exception): remote.uid.side_effect=search
                else: remote.uid.return_value=search
                with patch.object(controller,'secret',return_value=SECRET), patch('benson_mail.core.connect',return_value=remote), self.assertRaises(MailConnectionError) as caught:
                    controller.command('test_mail',{})
                text=str(caught.exception)
                self.assertIn(stage,text); self.assertIn('IMAP4.error',text)
                self.assertNotIn(SECRET,text); self.assertIn('imap.example.invalid:993',text)
                if search is not None and not isinstance(search,Exception): self.assertIn('Search unavailable',text)
                remote.logout.assert_called_once()

    def test_background_preserves_only_sanitized_mail_diagnostic(self):
        with tempfile.TemporaryDirectory() as root:
            events=[]; service=Service(CONFIG,SECRET,root,events.append)
            diagnostic=MailConnectionError('safe connection diagnostic')
            def fail():
                service.cancel.set(); raise diagnostic
            with patch.object(service,'check_once',side_effect=fail): service.run()
            self.assertEqual(events[1]['detail'],'safe connection diagnostic')
            service.cancel.clear(); events.clear()
            def ai_fail():
                service.cancel.set(); raise RuntimeError('unsanitized synthetic upstream text')
            with patch.object(service,'check_once',side_effect=ai_fail): service.run()
            self.assertNotIn('upstream',events[1]['detail'])
