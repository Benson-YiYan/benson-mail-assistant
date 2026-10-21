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
    def test_report_layout_uses_monitored_account_not_message_to_or_login(self):
        self.config['username'] = 'custom-server-login'
        self.service().check_once()
        message = EmailMessage()
        message['Subject'] = 'Example'; message['From'] = 'Sender <sender@example.com>'
        message['To'] = 'other-recipient@example.com'; message.set_content('Original body')
        self.mb.messages[2] = message.as_bytes(), datetime(2026, 10, 21, 3, 53, tzinfo=timezone.utc)
        self.service().check_once()
        reports = list((self.root / '报告').rglob('*.md'))
        self.assertEqual(len(reports), 1)
        self.assertEqual(reports[0].relative_to(self.root / '报告').as_posix(),
                         'synthetic@example.com/2026-10-21/From sender@example.com/Example-11-53.md')
        self.assertEqual(self.calls[0]['mailbox_account'], 'synthetic@example.com')
    def test_validity_reset_baselines(self):
        self.service().check_once(); self.mb.validity='2'; self.mb.messages={10: mail()}; self.service().check_once(); self.assertEqual(self.calls,[])
    def test_account_independent(self):
        self.service().check_once(); self.config['account']='second@example.com'; self.mb.messages[2]=mail(); self.service().check_once(); self.assertEqual(self.calls,[])
    def test_filename_collision_and_date(self):
        message=extract_message(*mail('CON:/标题?'))
        p=export_report(self.root,message,'answer',1); q=export_report(self.root,message,'different',2)
        self.assertNotEqual(p,q); self.assertEqual(p.read_text(encoding='utf-8'),'answer'); self.assertIn('09-02',p.name); self.assertEqual(p.parent.parent.name,'2026-10-14'); self.assertEqual(p.parent.name,'From demo@example.com')
    def test_cancellation_and_monotonic_highwater(self):
        self.service().check_once(); self.mb.messages[2]=mail()
        def cancel(message,stop): stop.set(); return 'discarded'
        self.service(cancel).check_once(); self.assertFalse(list((self.root/'报告').rglob('*.md')))
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
        self.service().check_once(); self.assertEqual(len(self.calls),1); self.assertEqual(len(list((self.root/'报告').rglob('*.md'))),1)
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

class SpreadsheetTests(unittest.TestCase):
    def test_shared_inline_sparse_numeric_formula_and_workbook_names(self):
        import io,zipfile
        from benson_mail.core import attachment_text
        data=io.BytesIO()
        ns='http://schemas.openxmlformats.org/spreadsheetml/2006/main'
        with zipfile.ZipFile(data,'w') as archive:
            archive.writestr('xl/sharedStrings.xml',f'<sst xmlns="{ns}"><si><t>客户</t></si><si><r><t>张</t></r><r><t>女士</t></r></si></sst>')
            archive.writestr('xl/workbook.xml',f'<workbook xmlns="{ns}" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="合同清单" sheetId="1" r:id="rId1"/></sheets></workbook>')
            archive.writestr('xl/_rels/workbook.xml.rels','<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Target="worksheets/sheet1.xml"/></Relationships>')
            archive.writestr('xl/worksheets/sheet1.xml',f'''<worksheet xmlns="{ns}"><sheetData>
            <row r="1"><c r="A1" t="s"><v>0</v></c><c r="C1" t="inlineStr"><is><t>金额</t></is></c></row>
            <row r="2"><c r="A2" t="s"><v>1</v></c><c r="C2"><v>1200.50</v></c><c r="D2"><f>C2*2</f><v>2401</v></c><c r="E2"><f>NOW()</f></c><c r="F2" t="b"><v>1</v></c></row>
            <row r="3"><c r="A3" t="s"><v>999</v></c></row></sheetData></worksheet>''')
        text=attachment_text('客户.xlsx',data.getvalue())
        for expected in ('工作表：合同清单','行 1：A1=客户 | C1=金额','行 2：A2=张女士 | C2=1200.50','D2=2401【公式缓存值','E2=【公式未计算','F2=TRUE','无效共享字符串索引','日期/金额样式'):
            self.assertIn(expected,text)
    def test_expanded_zip_bound(self):
        import io,zipfile
        from unittest.mock import patch
        from benson_mail.core import attachment_text
        data=io.BytesIO()
        with zipfile.ZipFile(data,'w',compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr('xl/sharedStrings.xml','x'*4096)
        with patch('benson_mail.core.MAX_ATTACHMENT',1024):
            self.assertIn('未读取',attachment_text('big.xlsx',data.getvalue()))
