import json
import hashlib
from datetime import datetime,timezone
from email.message import EmailMessage
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import threading
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch
import socket
import ssl
import urllib.error
from benson_mail.ai_api import complete, endpoint
from benson_mail.core import APIAnalyzer, ANALYSIS_PROMPT, Service

class APITests(unittest.TestCase):
    def test_connection_errors_are_specific_and_redacted(self):
        cases = [
            (socket.gaierror(11001, 'getaddrinfo failed'), 'DNS'),
            (ssl.SSLCertVerificationError(1, 'certificate verify failed'), '证书'),
            (TimeoutError('timed out'), '120 秒'),
            (ConnectionRefusedError(10061, 'connection refused'), '拒绝连接'),
            (OSError('proxy synthetic-secret https://host/?token=hidden'), '连接失败'),
        ]
        for reason, expected in cases:
            with self.subTest(reason=reason):
                with patch('urllib.request.OpenerDirector.open', side_effect=urllib.error.URLError(reason)):
                    with self.assertRaises(RuntimeError) as error:
                        complete(self.base, 'model', 'synthetic-secret', [])
                text = str(error.exception)
                self.assertIn(expected, text)
                self.assertIn(type(reason).__name__, text)
                self.assertNotIn('synthetic-secret', text)
                self.assertNotIn('token=hidden', text)
    def setUp(self):
        self.requests=[]; self.status=200; self.finish='stop'; self.redirect=False
        owner=self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*_): pass
            def do_POST(self):
                body=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                owner.requests.append((self.path,self.headers.get('Authorization'),body))
                self.send_response(owner.status)
                if owner.redirect: self.send_header('Location','http://127.0.0.1:1/key-must-not-be-forwarded')
                self.end_headers()
                self.wfile.write(json.dumps({'choices':[{'finish_reason':owner.finish,'message':{'content':'1 提醒\\n2 发件人\\n3 摘要\\n4 待办\\n5 附件\\n6 回复'}}],'error':'DO-NOT-LEAK-SERVER-RESPONSE'}).encode())
        self.server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True); self.thread.start()
        self.base='http://127.0.0.1:%d/v1'%self.server.server_port
    def tearDown(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join()
    def test_transport_and_original_prompt(self):
        message={'subject':'Synthetic','body':'请审阅','attachments':[{'name':'contract.txt','text':'付款100元'}]}
        answer=APIAnalyzer({'api_base':self.base,'api_model':'custom/model'},'synthetic-key')(message,threading.Event())
        self.assertIn('6 回复',answer)
        path,authorization,payload=self.requests[0]
        self.assertEqual(path,'/v1/chat/completions'); self.assertEqual(authorization,'Bearer synthetic-key')
        self.assertEqual(payload['model'],'custom/model')
        self.assertEqual(payload['messages'],[{'role':'user','content':ANALYSIS_PROMPT+json.dumps(message,ensure_ascii=False)}])
    def test_errors_redacted_and_no_redirect_or_truncation(self):
        for status in (401,404,429,500):
            self.status=status
            with self.assertRaises(RuntimeError) as error: complete(self.base,'model','synthetic-key',[])
            self.assertIn(str(status),str(error.exception)); self.assertNotIn('DO-NOT-LEAK',str(error.exception))
            self.assertNotIn('synthetic-key',str(error.exception))
        self.status=302; self.redirect=True
        with self.assertRaises(RuntimeError) as error: complete(self.base,'model','synthetic-key',[])
        self.assertIn('302',str(error.exception))
        self.status=200; self.redirect=False; self.finish='length'
        with self.assertRaisesRegex(RuntimeError,'截断'): complete(self.base,'model','synthetic-key',[])
    def test_empty_mailbox_never_calls_api(self):
        class Box:
            def snapshot(self): return 'fixture',[]
        with tempfile.TemporaryDirectory() as directory:
            service=Service({'account':'synthetic@163.com','ai_provider':'api','api_base':self.base,'api_model':'model'},'mail-key',directory,lambda _:None,mailbox=Box(),api_key='synthetic-api-key')
            service.check_once(); service.check_once()
            self.assertEqual(self.requests,[])
    def test_new_mail_api_report_export_and_retry_without_codex(self):
        message=EmailMessage(); message['Subject']='API synthetic'; message['From']='demo@example.invalid'
        message.set_content('请看附件'); message.add_attachment('合同100元'.encode(),maintype='text',subtype='plain',filename='contract.txt')
        class Box:
            uids=[]
            def snapshot(self): return 'fixture',self.uids
            def fetch(self,uid): return message.as_bytes(),datetime(2026,10,16,1,0,tzinfo=timezone.utc)
        box=Box()
        with tempfile.TemporaryDirectory() as directory:
            config={'account':'synthetic@163.com','ai_provider':'api','api_base':self.base,'api_model':'test','output_dir':str(Path(directory)/'reports')}
            service=Service(config,'mail-secret',Path(directory)/'state',lambda _:None,mailbox=box,api_key='synthetic-api-key')
            service.check_once(); box.uids=[1]; self.status=401
            with self.assertRaises(RuntimeError): service.check_once()
            self.assertIn('1',service.state['pending'])
            self.assertFalse(list(Path(config['output_dir']).glob('*/*.md')))
            self.status=200; service.check_once(); service.check_once()
            self.assertNotIn('1',service.state['pending'])
            reports=list(Path(config['output_dir']).glob('*/*.md'))
            self.assertEqual(len(reports),1); self.assertIn('6 回复',reports[0].read_text(encoding='utf-8'))
            self.assertIn('合同100元',self.requests[-1][2]['messages'][0]['content'])
            self.assertEqual(len(self.requests),2)
    def test_six_requirements_unchanged_before_markdown_format(self):
        self.assertEqual(hashlib.sha256((ANALYSIS_PROMPT.split('输出 Markdown')[0]+'\n').encode()).hexdigest(),
                         '8c9054046c397870c494a79e5b293fa013bd72c3efefe1291d9b0ced754aa07e')
    def test_endpoint_and_pre_cancel(self):
        self.assertEqual(endpoint(self.base+'/'),self.base+'/chat/completions')
        self.assertEqual(endpoint(self.base+'/chat/completions'),self.base+'/chat/completions')
        for invalid in ['http://remote.example/v1','https://key@host/v1','https://host/v1?key=secret','file:///tmp/api']:
            with self.assertRaises(ValueError): endpoint(invalid)
        stopped=threading.Event(); stopped.set()
        with self.assertRaisesRegex(RuntimeError,'停止'): complete(self.base,'m','key',[],stopped)
        self.assertFalse(self.requests)
