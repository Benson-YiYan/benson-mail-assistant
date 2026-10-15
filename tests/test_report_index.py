import json
from pathlib import Path
import tempfile
import threading
import unittest
from benson_mail.report_index import report_entry,matches
from benson_mail.core import Service

class LocalReportTests(unittest.TestCase):
    def test_subject_time_and_combined_search(self):
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/'2026-10-15'/'safe-title-09-02.txt'
            path.parent.mkdir(); path.write_text('六项报告',encoding='utf-8')
            path.with_suffix('.mail.json').write_text(json.dumps(dict(subject='主题-12-34',sender='Demo <demo@example.invalid>',received='2026-10-15T01:02:00+00:00',body='正文专用Zebra',attachments=[{'name':'付款明细.xlsx'}])),encoding='utf-8')
            entry=report_entry(path)
            self.assertEqual(entry['title'],'主题-12-34')
            self.assertEqual(entry['time'],'2026-10-15 09:02')
            for query in ['zebra','demo@example.invalid','付款明细.xlsx']:
                self.assertTrue(matches(entry,query,'Demo','2026-10-15','2026-10-15','有附件'))
            self.assertFalse(matches(entry,attachments='无附件'))
            self.assertFalse(matches(entry,start='2026-10-16'))
            self.assertEqual(path.name,'safe-title-09-02.txt')
    def test_legacy_and_missing_metadata(self):
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/'2026-10-14'/'test-19-02-UID15-2.txt'
            path.parent.mkdir(); path.write_text('正文',encoding='utf-8')
            entry=report_entry(path)
            self.assertEqual(entry['title'],'test'); self.assertEqual(entry['time'],'2026-10-14 19:02')
            self.assertTrue(matches(entry,'正文')); self.assertFalse(matches(entry,attachments='无附件'))
    def test_idle_manual_check_wakes_without_ai(self):
        with tempfile.TemporaryDirectory() as temporary:
            done=threading.Event(); calls=[]
            class Mailbox:
                def snapshot(self): calls.append(1); return 'test',[]
            def event(value):
                if value.get('check_done'): done.set()
            def analyze(*_): raise AssertionError('Empty check called AI')
            service=Service({'account':'demo@163.com','codex_command':[],'interval':86400},'synthetic',temporary,event,mailbox=Mailbox(),analyzer=analyze)
            try:
                service.start(); self.assertTrue(done.wait(2)); done.clear()
                service.request_check(); self.assertTrue(done.wait(2)); self.assertEqual(len(calls),2)
                done.clear(); service.set_interval(25); self.assertTrue(done.wait(2)); self.assertEqual(service.config['interval'],25)
            finally: service.stop(); service.join(2)
            self.assertFalse(service.thread.is_alive())
