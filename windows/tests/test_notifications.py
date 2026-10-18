import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock,patch
from benson_mail.core import Service
from test_core import Mailbox,mail

class NotificationTests(unittest.TestCase):
    def test_persist_new_and_completed_across_retries_and_restarts(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); config={'account':'synthetic@example.invalid','output_dir':str(root/'reports')}
            box=Mailbox(); box.messages={1:mail()}; events=[]
            def create(analyzer): return Service(config,'synthetic',root/'state',events.append,mailbox=box,analyzer=analyzer)
            create(lambda *args:'report').check_once(); box.messages[2]=mail()
            def fail(*args): raise RuntimeError('simulated AI failure')
            for _ in range(2):
                with self.assertRaises(RuntimeError): create(fail).check_once()
            notices=[event['notification'] for event in events if 'notification' in event]
            self.assertEqual([n['title'] for n in notices],['收到新邮件'])
            with patch('benson_mail.core.export_report',side_effect=OSError('simulated save failure')):
                with self.assertRaises(OSError): create(lambda *args:'report').check_once()
            create(fail).check_once(); create(fail).check_once()
            notices=[event['notification'] for event in events if 'notification' in event]
            self.assertEqual([n['title'] for n in notices],['收到新邮件','邮件报告已完成'])
            self.assertEqual(len(set(n['id'] for n in notices)),2)
            self.assertIn('completed_notifications',create(fail).state)
    def test_actual_dispatch_calls_notify_once_without_tk_window(self):
        # Mac system Python can lack Tk; Windows CI always executes this test.
        if importlib.util.find_spec('tkinter') is None: self.skipTest('Tkinter not installed')
        try: from benson_mail.ui import Application
        except ImportError: self.skipTest('Tkinter native library not installed')
        app=Application.__new__(Application); app.notified=set(); app.tray=Mock(); app.tray_ready=Mock(); app.tray_ready.is_set.return_value=True; app.detail=Mock()
        notice={'id':'same:uid:new','title':'收到新邮件','message':'测试标题'}
        app.notify(notice); app.notify(notice)
        app.tray.notify.assert_called_once_with('测试标题','收到新邮件')
        app.tray.notify.side_effect=RuntimeError('notification unavailable')
        app.notify(dict(notice,id='same:uid:complete')); app.detail.set.assert_called_once()
