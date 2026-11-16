"""Offline Windows send regression: confirmation, credentials, TLS and duplicate safety."""
from pathlib import Path
import json
import smtplib
import ssl
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from benson_mail import assistant_tools as tools, mailbox_config

class ReplySendTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.profile={'account':'owner@example.invalid','host':'imap.163.com','enabled':False,'mail_secret_file':'secret.bin','secret_binding':'fixture-binding'}
        self.configure()
        folder=self.root/'reply_drafts';folder.mkdir();self.path=folder/'reply.json'
        self.value={'draft':'Reply body','recipient':'person@example.invalid','subject':'Re: Question','sent':False}
        self.path.write_text(json.dumps(self.value));self.request={**self.value,'confirmed':True,'draft_path':str(self.path),'mailbox_id':mailbox_config.mailbox_id(self.profile)}
        self.controller=Mock();self.controller.mailbox_secret.return_value='synthetic-secret'
        self.transport=Mock();self.transport.__enter__=Mock(return_value=self.transport);self.transport.__exit__=Mock(return_value=False)
    def configure(self):
        (self.root/'config.json').write_text(json.dumps({'mailboxes':[self.profile],'ui_language':'en'}))
    def tearDown(self):self.temp.cleanup()
    def send(self,**request):
        with patch.object(tools,'_proxy_smtp_classes',return_value=(Mock(return_value=self.transport),Mock(return_value=self.transport))):
            return tools.reply_send(self.root,{**self.request,**request},self.controller)
    def test_confirmation_and_saved_content_precede_secret_loading(self):
        with self.assertRaisesRegex(ValueError,'Confirm the sender'):self.send(confirmed=False)
        with self.assertRaisesRegex(ValueError,'Save the latest'):self.send(draft='Changed body')
        with self.assertRaisesRegex(ValueError,'existing local'):self.send(draft_path=str(self.root/'external.json'))
        self.controller.mailbox_secret.assert_not_called()
    def test_selected_paused_mailbox_exact_message_and_duplicate_guard(self):
        result=self.send();self.assertTrue(result['sent']);self.assertTrue(result['draft_status_saved'])
        self.controller.mailbox_secret.assert_called_once_with(self.profile)
        self.transport.login.assert_called_once_with('owner@example.invalid','synthetic-secret')
        message=self.transport.send_message.call_args.args[0]
        self.assertEqual(message['From'],'owner@example.invalid');self.assertEqual(message['To'],'person@example.invalid');self.assertEqual(message.get_content(),'Reply body\n')
        self.assertEqual(json.loads(self.path.read_text())['send_state'],'sent')
        with self.assertRaisesRegex(ValueError,'already sent'):self.send()
        with self.assertRaisesRegex(ValueError,'already sent'):tools.draft_save(self.root,self.request)
        self.assertEqual(self.transport.send_message.call_count,1)
    def test_starttls_uses_verified_tls_before_login(self):
        self.profile['host']='imap.gmail.com';self.configure();self.request['mailbox_id']=mailbox_config.mailbox_id(self.profile);self.send()
        context=self.transport.starttls.call_args.kwargs['context'];self.assertEqual(context.verify_mode,ssl.CERT_REQUIRED);self.assertTrue(context.check_hostname)
        names=[call[0] for call in self.transport.method_calls];self.assertLess(names.index('starttls'),names.index('login'))
    def test_ssl_wraps_proxy_socket_once_without_fallback(self):
        raw=Mock();secured=Mock();context=Mock();context.wrap_socket.return_value=secured
        with patch('benson_mail.mailbox_config.proxy_socket',return_value=raw) as proxy:
            _,cls=tools._proxy_smtp_classes({'kind':'http'},context)
            self.assertIs(object.__new__(cls)._get_socket('smtp.163.com',465,30),secured)
            proxy.assert_called_once_with({'kind':'http'},'smtp.163.com',465,30);context.wrap_socket.assert_called_once_with(raw,server_hostname='smtp.163.com')
        with patch('benson_mail.mailbox_config.proxy_socket',side_effect=OSError('unavailable')),patch.object(tools.socket,'create_connection') as direct:
            _,cls=tools._proxy_smtp_classes({'kind':'http'},context)
            with self.assertRaises(OSError):object.__new__(cls)._get_socket('smtp.163.com',465,30)
            direct.assert_not_called()
    def test_uncertain_result_is_sanitized_and_never_retried(self):
        self.transport.send_message.side_effect=TimeoutError('synthetic-secret person@example.invalid Reply body')
        with self.assertRaisesRegex(RuntimeError,'check Sent mail') as caught:self.send()
        self.assertNotIn('person@example.invalid',str(caught.exception));self.assertNotIn('synthetic-secret',str(caught.exception));self.assertEqual(json.loads(self.path.read_text())['send_state'],'unknown')
        with self.assertRaisesRegex(ValueError,'result is uncertain'):self.send()
        with self.assertRaisesRegex(ValueError,'result is uncertain'):tools.draft_save(self.root,self.request)
        self.assertEqual(self.transport.send_message.call_count,1)
    def test_auth_failure_does_not_submit_and_allows_corrected_retry(self):
        self.transport.login.side_effect=smtplib.SMTPAuthenticationError(535,b'secret')
        with self.assertRaisesRegex(RuntimeError,'authentication failed'):self.send()
        self.assertEqual(json.loads(self.path.read_text())['send_state'],'not_sent');self.transport.send_message.assert_not_called()
        self.transport.login.side_effect=None;self.assertTrue(self.send()['sent'])
    def test_final_disk_error_reports_success_and_blocks_duplicate(self):
        original=tools._chat()._atomic
        def write(path,text):
            if json.loads(text).get('sent'):raise OSError('disk unavailable')
            return original(path,text)
        with patch.object(tools._chat(),'_atomic',side_effect=write):result=self.send()
        self.assertTrue(result['sent']);self.assertFalse(result['draft_status_saved']);self.assertEqual(json.loads(self.path.read_text())['send_state'],'sending')
        with self.assertRaisesRegex(ValueError,'result is uncertain'):self.send()
    def test_oauth_auth_callback_is_text_not_bytes(self):
        transport=Mock()
        tools._smtp_auth(transport,{'account':'owner@example.invalid'},'token',True)
        self.assertEqual(transport.auth.call_args.args[0],'XOAUTH2')
        response=transport.auth.call_args.args[1](None)
        self.assertIsInstance(response,str);self.assertIn('auth=Bearer token',response)

    def test_dispatch_routes_send_without_extra_work(self):
        with patch.object(tools,'reply_send',return_value={'sent':True}) as send:
            self.assertTrue(tools.dispatch(self.root,{'action':'reply_send',**self.request},self.controller)['sent']);send.assert_called_once()
        with self.assertRaises(ValueError):self.send(recipient='bad@example.invalid\nInjected')
if __name__=='__main__':unittest.main()
