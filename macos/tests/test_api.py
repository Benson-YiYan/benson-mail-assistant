import hashlib
import importlib.util
import json
import io
from pathlib import Path
import sys
import socket
import ssl
import tempfile
import unittest
import urllib.error
import urllib.parse
from unittest.mock import patch

RUNTIME=Path(__file__).resolve().parents[1]/'Runtime'
sys.path.insert(0,str(RUNTIME))
import ai_runner
import ai_api
from mail_prompt import ANALYSIS_PROMPT

class APIMailTests(unittest.TestCase):
    def test_connection_failures_explain_the_cause_without_credentials(self):
        secret = 'synthetic-key/with+symbols'
        cases = [
            (socket.gaierror(8, 'nodename nor servname provided'), 'DNS'),
            (ssl.SSLCertVerificationError(1, 'certificate verify failed'), '证书'),
            (TimeoutError('The read operation timed out'), '120 秒'),
            (ConnectionRefusedError(61, 'Connection refused'), '拒绝连接'),
            (OSError('proxy unavailable'), '连接失败'),
        ]
        for reason, hint in cases:
            for wrapped in (reason, urllib.error.URLError(reason)):
                with self.subTest(reason=type(reason).__name__, wrapped=type(wrapped).__name__):
                    with patch('urllib.request.OpenerDirector.open', side_effect=wrapped) as opened:
                        with self.assertRaises(RuntimeError) as error:
                            ai_api.complete('https://example.invalid/v1', 'model', secret, [])
                    text = str(error.exception)
                    self.assertIn(hint, text)
                    self.assertIn(type(reason).__name__, text)
                    self.assertIn(str(reason), text)
                    self.assertNotIn(secret, text)
                    self.assertEqual(opened.call_args.kwargs['timeout'], 120)

    def test_connection_detail_redacts_raw_encoded_keys_and_urls(self):
        secret = 'synthetic-key/with+symbols'
        encoded = urllib.parse.quote(secret, safe='')
        reason = OSError('proxy %s encoded %s https://user:password@example.invalid/?token=private '
                         'Authorization: Bearer other-secret api_key="third-secret"' % (secret, encoded))
        with patch('urllib.request.OpenerDirector.open', side_effect=urllib.error.URLError(reason)):
            with self.assertRaises(RuntimeError) as error:
                ai_api.complete('https://example.invalid/v1', 'model', secret, [])
        text = str(error.exception)
        for private in (secret, encoded, 'password', 'token=private', 'other-secret', 'third-secret'):
            self.assertNotIn(private, text)
        self.assertIn('OSError', text)
        self.assertLessEqual(len(text.split('OSError: ', 1)[1]), 500)

    def test_http_failures_do_not_read_or_expose_response_bodies(self):
        body = io.BytesIO(b'PRIVATE_RESPONSE_BODY Authorization: Bearer private')
        failure = urllib.error.HTTPError('https://example.invalid', 401, 'Denied', {}, body)
        with patch('urllib.request.OpenerDirector.open', side_effect=failure):
            with self.assertRaises(RuntimeError) as error:
                ai_api.complete('https://example.invalid/v1', 'model', 'synthetic-key', [])
        self.assertIn('401', str(error.exception))
        self.assertNotIn('PRIVATE_RESPONSE_BODY', str(error.exception))
        self.assertNotIn('Bearer', str(error.exception))
        self.assertTrue(body.closed)

    def test_six_substantive_prompt_requirements_are_unchanged(self):
        requirements = '\n'.join(ANALYSIS_PROMPT.splitlines()[1:8])
        self.assertEqual(hashlib.sha256(requirements.encode()).hexdigest(),
                         'e5a02aa7cddaab5d0fe7bf4f4c473de11922a1206c8300bb1a85df544631a6fe')
    def test_api_gets_original_prompt_and_real_attachment_text(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder=Path(temporary)
            attachment=folder/'contract.txt'; attachment.write_text('合同金额：100元',encoding='utf-8')
            message={'uid':101,'subject':'模拟邮件','bodies':[{'text':'请审阅合同'}],
                     'attachments':[{'filename':'contract.txt','path':str(attachment)}]}
            with patch.object(ai_runner,'api_config',return_value=({'api_base':'https://example.invalid/v1','api_model':'test-model'},'synthetic-key')), patch.object(ai_runner,'complete',return_value='六项报告') as call:
                self.assertEqual(ai_runner.analyze_api(message,folder),'六项报告')
            args=call.call_args.args
            self.assertEqual(args[3][0],{'role':'system','content':ANALYSIS_PROMPT})
            payload=json.loads(args[3][1]['content'])
            self.assertIn('合同金额：100元',payload['attachments'][0]['text'])
            self.assertNotIn('path',payload['attachments'][0])
    def test_attachment_paths_are_scoped_and_unsupported_is_explicit(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder=Path(temporary)/'mail'; folder.mkdir()
            outside=Path(temporary)/'outside.txt'; outside.write_text('not-mail')
            self.assertIn('路径',ai_runner.attachment_text(outside,folder))
            picture=folder/'photo.jpg'; picture.write_bytes(b'not an image')
            self.assertIn('未读取',ai_runner.attachment_text(picture,folder))
    def test_api_daemon_uses_cached_answers_without_recalling_api(self):
        spec=importlib.util.spec_from_file_location('api_test_daemon',RUNTIME/'mail_daemon.py')
        daemon=importlib.util.module_from_spec(spec); spec.loader.exec_module(daemon)
        with tempfile.TemporaryDirectory() as temporary:
            daemon.DATA=Path(temporary)
            message={'uid':101,'subject':'synthetic','attachments':[]}
            folder=daemon.DATA/'101'; folder.mkdir(); (folder/'answer.txt').write_text('cached six sections')
            with patch.object(daemon,'publish'), patch.object(daemon,'notify'), patch.object(daemon,'log'), patch.object(daemon,'run_reader'), patch.object(daemon,'export_report',return_value='fixture.txt'), patch.object(ai_runner,'analyze_api') as analyze:
                daemon.analyze(message)
            analyze.assert_not_called()
