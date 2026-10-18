"""Update/uninstall must refuse active work without cancelling AI or report writes."""
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import Mock
from benson_mail.bridge import Controller
from benson_mail.core import Service


class ExitPreparationTests(unittest.TestCase):
    def test_all_mailboxes_are_checked_before_any_is_stopped(self):
        with tempfile.TemporaryDirectory() as directory:
            controller = Controller(directory, lambda _: None)
            idle = Mock(thread=None, activity=threading.Lock())
            busy = Mock(thread=None, activity=threading.Lock())
            controller.services = {'idle': idle, 'busy': busy}
            busy.activity.acquire()
            try:
                with self.assertRaisesRegex(ValueError, '没有中断任务'):
                    controller.command('prepare_exit', {})
                idle.stop.assert_not_called(); busy.stop.assert_not_called()
                self.assertFalse(controller.prepared_exit)
                self.assertTrue(idle.activity.acquire(False)); idle.activity.release()
            finally:
                busy.activity.release()
            result = controller.command('prepare_exit', {})
            self.assertTrue(result['prepared'])
            idle.stop.assert_called_once(); busy.stop.assert_called_once()
            with self.assertRaisesRegex(ValueError, '正在准备退出'):
                controller.command('check', {})
            controller.command('resume_after_exit_cancel', {'resume': False})
            self.assertFalse(controller.prepared_exit)

    def test_busy_report_finishes_and_is_written_before_exit_can_prepare(self):
        class Box:
            uids = []
            def snapshot(self): return 'fixture', self.uids
            def fetch(self, uid):
                from datetime import datetime, timezone
                return b'Subject: Synthetic\r\nFrom: fixture@example.invalid\r\n\r\nBody', datetime.now(timezone.utc)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); entered = threading.Event(); finish = threading.Event()
            def analyze(message, cancel):
                entered.set(); self.assertTrue(finish.wait(5)); self.assertFalse(cancel.is_set())
                return 'Synthetic complete report'
            box = Box()
            service = Service({'account': 'fixture@example.invalid', 'output_dir': str(root/'reports')},
                'synthetic', root/'state', lambda _: None, mailbox=box, analyzer=analyze)
            service.check_once(); box.uids = [1]
            service.thread = threading.Thread(target=service.check_once)
            controller = Controller(root/'config', lambda _: None); controller.service = service
            service.thread.start()
            try:
                self.assertTrue(entered.wait(3))
                with self.assertRaises(ValueError): controller.command('prepare_exit', {})
                self.assertFalse(service.cancel.is_set())
            finally:
                finish.set(); service.thread.join(5)
            reports = list((root/'reports').rglob('*.md'))
            self.assertEqual(len(reports), 1)
            self.assertEqual(reports[0].read_text(), 'Synthetic complete report')
            self.assertTrue(controller.command('prepare_exit', {})['prepared'])
            self.assertTrue(service.cancel.is_set())
