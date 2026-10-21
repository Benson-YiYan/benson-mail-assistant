import importlib.util
import json
import pathlib
import tempfile
import unittest
import sys
from unittest.mock import patch

RUNTIME = pathlib.Path(__file__).resolve().parents[1] / 'Runtime'
sys.path.insert(0, str(RUNTIME))

def load(name):
    spec = importlib.util.spec_from_file_location(name, RUNTIME / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

class Done(BaseException):
    pass

class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='BensonMail-runtime-test-')
        self.root = pathlib.Path(self.temp.name)
        self.daemon = load('mail_daemon')
        self.daemon.BASE = self.root
        self.daemon.DATA = self.root / 'mail_watch'
        self.daemon.DATA.mkdir()
        self.daemon.CONTROL = self.daemon.DATA
        self.daemon.ACTIVE_HOME = self.root
        self.daemon.SETTINGS = self.root / 'settings.json'
        self.daemon.STATUS = self.daemon.DATA / 'service.json'
        self.daemon.CHECK_REQUEST = self.daemon.DATA / 'check.request'
        self.daemon.NOTIFICATIONS = self.root / 'notifications/pending'
        self.daemon.APP = self.root / '邮件小秘书.app'
        (self.daemon.DATA / 'state.json').write_text('{"pending": []}')
        self.clock = 0
    def tearDown(self):
        self.temp.cleanup()
    def run_loop(self, seconds, reader, on_sleep=None):
        def sleep(duration):
            self.clock += duration
            if on_sleep: on_sleep()
            if self.clock >= seconds: raise Done()
        with patch.object(self.daemon.time, 'sleep', sleep), patch.object(self.daemon.time, 'monotonic', lambda: self.clock), patch.object(self.daemon, 'run_reader', reader):
            with self.assertRaises(Done): self.daemon.main()
    def test_empty_minute_checks_never_analyze(self):
        from unittest.mock import Mock
        reader = Mock(return_value={'pending_messages': 0})
        with patch.object(self.daemon, 'analyze') as analyze:
            self.run_loop(65, reader)
        self.assertEqual(reader.call_count, 2)
        analyze.assert_not_called()

    def test_sanitized_connection_detail_reaches_background_status(self):
        from mailbox_config import MailConnectionError
        from unittest.mock import Mock
        message='邮箱连接失败：safe diagnostic\n服务器：imap.example.invalid:993 (ssl)\n阶段：LOGIN 认证\n具体原因：error: AUTHENTICATIONFAILED [已隐藏凭据]'
        reader=Mock(side_effect=MailConnectionError(message))
        with patch.object(self.daemon,'notify'),patch.object(self.daemon,'log'):
            self.run_loop(2,reader)
        detail=json.loads(self.daemon.STATUS.read_text())['error']
        self.assertIn(message,detail)
        self.assertNotIn('请测试邮箱和 AI',detail)
        response=Mock(returncode=1,stdout=json.dumps({'error':'MailConnectionError','detail':message}))
        with patch.object(self.daemon.subprocess,'run',return_value=response),self.assertRaises(MailConnectionError) as caught:
            self.daemon.run_reader()
        self.assertEqual(str(caught.exception),message)
    def test_notification_queues_native_app_event_without_applescript(self):
        with patch.object(self.daemon.subprocess, 'run') as run:
            self.daemon.notify('模拟正文', '模拟标题', report='/tmp/synthetic.txt')
        run.assert_not_called()
        files = list(self.daemon.NOTIFICATIONS.glob('*.json'))
        self.assertEqual(len(files), 1)
        event = json.loads(files[0].read_text())
        self.assertEqual(event['body'], '模拟正文')
        self.assertEqual(event['report'], '/tmp/synthetic.txt')
        self.assertEqual(event['id'], files[0].stem)
    def test_notification_relaunches_own_app_in_background(self):
        import subprocess
        self.daemon.APP.mkdir()
        with patch.object(self.daemon.subprocess, 'run', return_value=subprocess.CompletedProcess([], 1)) as run:
            self.daemon.notify('模拟正文', '模拟标题')
        self.assertEqual(run.call_count, 2)
        self.assertEqual(run.call_args_list[0].args[0][0], '/usr/bin/pgrep')
        command = run.call_args_list[1].args[0]
        self.assertEqual(command, ['/usr/bin/open', '-g', '-j', str(self.daemon.APP), '--args', '--background'])
    def test_pause_survives_restart_and_never_checks(self):
        from unittest.mock import Mock
        self.daemon.SETTINGS.write_text('{"enabled": false}')
        reader = Mock()
        self.run_loop(4, reader)
        reader.assert_not_called()
        self.assertEqual(json.loads(self.daemon.STATUS.read_text())['phase'], 'paused')
    def test_custom_interval_applies_live(self):
        from unittest.mock import Mock
        self.daemon.SETTINGS.write_text('{"interval_seconds": 60}')
        reader = Mock(return_value={'pending_messages': 0})
        def change():
            if self.clock == 5: self.daemon.SETTINGS.write_text('{"interval_seconds": 10}')
        with patch.object(self.daemon, 'analyze') as analyze:
            self.run_loop(25, reader, change)
        self.assertEqual(reader.call_count, 3)
        analyze.assert_not_called()
    def test_long_interval_keeps_live_heartbeat_without_mail_checks(self):
        from unittest.mock import Mock
        self.daemon.SETTINGS.write_text('{"interval_seconds": 86400}')
        reader = Mock(return_value={'pending_messages': 0})
        with patch.object(self.daemon, 'publish', wraps=self.daemon.publish) as publish:
            self.run_loop(45, reader)
        self.assertEqual(reader.call_count, 1)
        self.assertGreaterEqual(sum(call.args[0] == 'idle' for call in publish.call_args_list), 3)
    def test_manual_check_wakes_wait_without_extra_ai(self):
        from unittest.mock import Mock
        reader = Mock(return_value={'pending_messages': 0})
        def request():
            if self.clock == 4: self.daemon.CHECK_REQUEST.touch()
        with patch.object(self.daemon, 'analyze') as analyze:
            self.run_loop(8, reader, request)
        self.assertEqual(reader.call_count, 2)
        self.assertFalse(self.daemon.CHECK_REQUEST.exists())
        analyze.assert_not_called()
    def test_pause_finishes_current_and_preserves_remaining(self):
        from unittest.mock import Mock
        report = self.root / 'synthetic.json'
        report.write_text('[{"uid": 10}, {"uid": 11}]')
        (self.daemon.DATA / 'state.json').write_text('{"pending": [10,11]}')
        reader = Mock(return_value={'pending_messages': 2, 'report': str(report)})
        seen = []
        def analyze(message):
            seen.append(message['uid'])
            self.daemon.SETTINGS.write_text('{"enabled": false}')
        with patch.object(self.daemon, 'analyze', analyze): self.run_loop(3, reader)
        self.assertEqual(seen, [10])
        self.assertEqual(json.loads((self.daemon.DATA / 'state.json').read_text())['pending'], [10,11])
    def test_custom_folder_applies_without_worker_restart(self):
        exporter = load('mail_export')
        exporter.BASE = self.root
        one, two = self.root / 'folder-one', self.root / '中文自定义目录'
        message = {'uid': 10, 'subject': '模拟来信', 'received_at': '2026-10-15T08:03:00+00:00'}
        for folder in (one, two):
            (self.root / 'settings.json').write_text(json.dumps({'output_dir': str(folder)}))
            path = exporter.export(message, '六项模拟报告')
            self.assertEqual(path.parent, folder / 'unknown-account' / '2026-10-15' / 'From unknown-sender')
            self.assertIn('16-03', path.name)
            self.assertIn('六项模拟报告', path.read_text())

if __name__ == '__main__': unittest.main()
