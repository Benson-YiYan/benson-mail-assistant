import tempfile
import unittest
from pathlib import Path
from datetime import datetime, timezone
from email.message import EmailMessage
from benson_mail.core import Service, export_report, extract_message

class Mailbox:
    validity = '1'
    messages = {}
    def snapshot(self): return self.validity, sorted(self.messages)
    def fetch(self, uid): return self.messages[uid]
    def close(self): pass

def mail(subject='测试'):
    m = EmailMessage(); m['Subject'] = subject; m['From'] = 'demo@example.com'; m.set_content('请周五回复')
    return m.as_bytes(), datetime(2026, 10, 14, 1, 2, tzinfo=timezone.utc)

class CoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.root = Path(self.tmp.name); self.mb = Mailbox(); self.mb.messages = {1: mail()}; self.calls = []
        self.config = {'account': 'synthetic@example.com', 'output_dir': str(self.root/'报告')}
    def tearDown(self): self.tmp.cleanup()
    def service(self, analyzer=None):
        return Service(self.config, 'synthetic', self.root/'state', lambda event: None, mailbox=self.mb, analyzer=analyzer or self.analyze)
    def analyze(self, message, stop): self.calls.append(message); return '新邮件提醒\n发件人\n中文摘要\n具体待办及截止时间\n附件实际内容\n建议回复'
    def test_baseline_empty_and_restart_gap(self):
        s=self.service(); s.check_once(); s.check_once(); self.assertEqual(self.calls, [])
        self.mb.messages[2]=mail(); self.service().check_once(); self.assertEqual(len(self.calls),1)
        self.service().check_once(); self.assertEqual(len(self.calls),1)
    def test_failure_and_cancel_remain_pending(self):
        s=self.service(); s.check_once(); self.mb.messages[2]=mail()
        def fail(*args): raise RuntimeError('fake')
        with self.assertRaises(RuntimeError): self.service(fail).check_once()
        self.service().check_once(); self.assertEqual(len(self.calls),1)
    def test_cache_export_retry(self):
        s=self.service(); s.check_once(); self.mb.messages[2]=mail()
        import unittest.mock as mock
        with mock.patch('benson_mail.core.export_report', side_effect=OSError('fake')):
            with self.assertRaises(OSError): s.check_once()
        self.service().check_once(); self.assertEqual(len(self.calls),1)
    def test_validity_reset_baselines(self):
        self.service().check_once(); self.mb.validity='2'; self.mb.messages={10: mail()}; self.service().check_once(); self.assertEqual(self.calls,[])
    def test_account_independent(self):
        self.service().check_once(); self.config['account']='second@example.com'; self.mb.messages[2]=mail(); self.service().check_once(); self.assertEqual(self.calls,[])
    def test_filename_collision_and_date(self):
        message=extract_message(*mail('CON:/标题?'))
        p=export_report(self.root,message,'answer',1); q=export_report(self.root,message,'different',2)
        self.assertNotEqual(p,q); self.assertEqual(p.read_text(encoding='utf-8'),'answer'); self.assertIn('09-02',p.name); self.assertEqual(p.parent.name,'2026-10-14')
    def test_cancellation_and_monotonic_highwater(self):
        self.service().check_once(); self.mb.messages[2]=mail()
        def cancel(message,stop): stop.set(); return 'discarded'
        self.service(cancel).check_once(); self.assertFalse(list((self.root/'报告').glob('*/*.txt')))
        self.mb.messages.pop(1); self.service().check_once(); self.assertEqual(len(self.calls),1)
        self.mb.messages={}; self.service().check_once(); self.mb.messages={2:mail()}; self.service().check_once(); self.assertEqual(len(self.calls),1)
    def test_export_recovery_after_written_before_commit(self):
        from unittest.mock import patch
        s=self.service(); s.check_once(); self.mb.messages[2]=mail()
        original=s.persist
        def fail_final():
            if not s.state['pending']: raise OSError('simulated crash after export')
            original()
        with patch.object(s,'persist',side_effect=fail_final):
            with self.assertRaises(OSError): s.check_once()
        self.service().check_once(); self.assertEqual(len(self.calls),1); self.assertEqual(len(list((self.root/'报告').glob('*/*.txt'))),1)
    def test_office_attachment_and_limits(self):
        import io,zipfile
        from benson_mail.core import attachment_text
        content=io.BytesIO()
        with zipfile.ZipFile(content,'w') as archive:
            archive.writestr('word/document.xml','<document><t>合同附件内容</t></document>')
        self.assertIn('合同附件内容',attachment_text('contract.docx',content.getvalue()))
        self.assertIn('未读取',attachment_text('broken.docx',b'broken'))
        self.assertIn('部分读取',attachment_text('long.txt',b'x'*100001))
        self.assertIn('未读取',attachment_text('macro.exe',b'unknown'))
    def test_attachment_content(self):
        m=EmailMessage(); m.set_content('正文'); m.add_attachment('附件内容'.encode(), maintype='text',subtype='plain',filename='测试.txt')
        result=extract_message(m.as_bytes(),datetime.now(timezone.utc)); self.assertIn('附件内容',result['attachments'][0]['text'])
