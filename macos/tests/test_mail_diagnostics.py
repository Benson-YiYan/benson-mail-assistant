import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"Runtime"))
"""Offline mailbox boundary diagnostics: never contact mail or AI services."""
import base64
import imaplib
import json
import socket
import ssl
import tempfile
import threading
import unittest
import contextlib
import io
import runpy
import os
from unittest.mock import Mock, patch
from mailbox_config import connect, MailConnectionError, redact_mail_error

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
        with patch('mailbox_config.imaplib.IMAP4_SSL', return_value=remote):
            with self.assertRaises(MailConnectionError) as caught:
                connect(config or CONFIG, SECRET, Mock())
        remote.logout.assert_called_once()
        return str(caught.exception)

    def test_auth_rejection_safe_response_and_bridge_visibility(self):
        diagnostic = self.failing(imaplib.IMAP4.error('[AUTHENTICATIONFAILED] invalid credentials '+SECRET))
        for expected in ('LOGIN', 'imap.example.invalid:993', 'error:', 'AUTHENTICATIONFAILED', '拒绝认证'):
            self.assertIn(expected, diagnostic)
        self.assertNotIn(SECRET, diagnostic)
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
        with patch('mailbox_config.imaplib.IMAP4_SSL', return_value=remote):
            self.assertIs(connect(CONFIG, SECRET, Mock()), remote)
        self.assertNotIn(b'ID',remote.capabilities)
        remote.capability.assert_called_once(); remote._simple_command.assert_called_once()
        remote=client(); remote.capability.return_value=('OK',[b'IMAP4rev1'])
        remote.capabilities=(b'IMAP4rev1',b'ID')
        with patch('mailbox_config.imaplib.IMAP4_SSL', return_value=remote):
            connect(CONFIG,SECRET,Mock())
        remote._simple_command.assert_not_called()
        self.assertIn('ID', self.failing(imaplib.IMAP4.error('ID rejected'), '_simple_command'))
        for operation, expected in (('_simple_command','ID 客户端'), ('select','SELECT 只读'), ('capability','CAPABILITY')):
            remote=client(); getattr(remote,operation).return_value=('NO',[b'Permission denied'])
            with patch('mailbox_config.imaplib.IMAP4_SSL', return_value=remote), self.assertRaises(MailConnectionError) as caught:
                connect(CONFIG, SECRET, Mock())
            self.assertIn(expected,str(caught.exception)); self.assertIn('Permission denied',str(caught.exception))
            remote.logout.assert_called_once()

    def test_dns_timeout_and_tls_diagnostics(self):
        for error, expected in ((socket.gaierror(-2,'name not known'),'DNS'), (TimeoutError('timed out'),'25 秒'), (ssl.SSLCertVerificationError(1,'certificate verify failed'),'证书验证'), (ssl.SSLError('wrong version number'),'加密协商')):
            with patch('mailbox_config.imaplib.IMAP4_SSL', side_effect=error), self.assertRaises(MailConnectionError) as caught:
                connect(CONFIG, SECRET, Mock())
            text=str(caught.exception); self.assertIn(expected,text); self.assertIn('SSL/TLS 连接',text)
        remote=client(); remote.starttls.side_effect=ssl.SSLError('TLS handshake refused')
        with patch('mailbox_config.imaplib.IMAP4',return_value=remote), self.assertRaisesRegex(MailConnectionError,'STARTTLS'):
            connect({**CONFIG,'security':'starttls','port':143},SECRET,Mock())
        remote.login.assert_not_called()

    def test_mac_manual_test_and_reader_preserve_sanitized_diagnostic(self):
        import mail_connection_io
        diagnostic = self.failing(imaplib.IMAP4.error('LOGIN failed '+SECRET))
        for operation in ('manual', 'reader'):
            with tempfile.TemporaryDirectory(prefix='BensonMail-diagnostic-fixture-') as root:
                output=io.StringIO()
                with patch.dict(os.environ,{'BENSON_MAIL_HOME':root}), patch('mail_connection_io.load',return_value=(CONFIG,SECRET)), contextlib.redirect_stdout(output):
                    if operation == 'manual':
                        with patch('mail_connection_io.connect',side_effect=MailConnectionError(diagnostic)), self.assertRaises(SystemExit):
                            mail_connection_io.test()
                        self.assertIn('LOGIN',output.getvalue());self.assertIn('imap.example.invalid:993',output.getvalue())
                    else:
                        with patch('mailbox_config.connect',side_effect=MailConnectionError(diagnostic)), patch.object(sys,'argv',['mail_watch']), self.assertRaises(SystemExit):
                            runpy.run_path(str(Path(__file__).resolve().parents[1]/'Runtime/mail_watch.py'),run_name='__main__')
                        result=json.loads(output.getvalue())
                        self.assertEqual(result['error'],'MailConnectionError')
                        self.assertEqual(result['detail'],diagnostic)
                self.assertNotIn(SECRET,output.getvalue())

    def test_english_diagnostic_uses_same_safe_boundary(self):
        result=self.failing(imaplib.IMAP4.error('AUTHENTICATIONFAILED '+SECRET),config={**CONFIG,'ui_language':'en'})
        self.assertIn('Mailbox connection failed:',result)
        self.assertIn('Stage: LOGIN authentication',result)
        self.assertIn('IMAP4.error: AUTHENTICATIONFAILED',result)
        self.assertNotIn(SECRET,result)

    def test_post_login_uidvalidity_and_search_errors_are_sanitized(self):
        from mailbox_config import normalize
        for stage in ('response','uid'):
            remote=Mock()
            remote.response.return_value=('UIDVALIDITY',[b'42'])
            getattr(remote,stage).side_effect=imaplib.IMAP4.error('snapshot refused '+SECRET)
            with tempfile.TemporaryDirectory(prefix='BensonMail-diagnostic-fixture-') as root:
                output=io.StringIO()
                with patch.dict(os.environ,{'BENSON_MAIL_HOME':root}),patch('mail_connection_io.load',return_value=(normalize(CONFIG),SECRET)),patch('mailbox_config.connect',return_value=remote),patch.object(sys,'argv',['mail_watch']),contextlib.redirect_stdout(output),self.assertRaises(SystemExit):
                    runpy.run_path(str(Path(__file__).resolve().parents[1]/'Runtime/mail_watch.py'),run_name='__main__')
                value=json.loads(output.getvalue())
                self.assertEqual(value['error'],'MailConnectionError')
                self.assertIn('UIDVALIDITY' if stage == 'response' else 'UID SEARCH',value['detail'])
                self.assertIn('snapshot refused',value['detail'])
                self.assertNotIn(SECRET,value['detail'])
