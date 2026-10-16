import json
from pathlib import Path
import tempfile
import unittest
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch, Mock
from benson_mail.bridge import Controller


class BridgeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.controller = Controller(self.root, lambda event: None, launcher='C:/app/BensonMail.exe')

    def tearDown(self):
        self.temp.cleanup()

    def test_interval_persists_and_validates(self):
        self.controller.command('interval', {'seconds': 37})
        self.assertEqual(json.loads((self.root / 'config.json').read_text())['interval'], 37)
        with self.assertRaises(ValueError):
            self.controller.command('interval', {'seconds': 0})

    def test_reports_search_metadata_and_containment(self):
        day = self.root / 'reports' / '2026-10-17'
        day.mkdir(parents=True)
        report = day / '标题-09-15.txt'
        report.write_text('模拟六项报告', encoding='utf-8')
        report.with_suffix('.mail.json').write_text(json.dumps({
            'subject': '原始标题', 'sender': 'demo@example.invalid', 'body': '合同正文',
            'received': '2026-10-17T01:15:00+00:00', 'attachments': [{'name': '合同.pdf'}]}), encoding='utf-8')
        self.controller.config['output_dir'] = str(day.parent)
        entries = self.controller.command('reports', {'query': '合同.pdf', 'attachments': '有附件'})
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]['title'], '原始标题')
        self.assertEqual(entries[0]['time'], '2026-10-17 09:15')
        self.assertEqual(self.controller.command('reports', {'start': '2026-10-18'}), [])
        self.assertEqual(self.controller.command('read_report', {'path': str(report)}), '模拟六项报告')
        with self.assertRaises(ValueError):
            self.controller.command('read_report', {'path': str(self.root / 'config.txt')})

    def test_mail_secret_omitted_and_native_startup_used(self):
        with patch('benson_mail.bridge.platform.save_secret') as save, patch(
                'benson_mail.bridge.platform.set_autostart') as auto:
            self.controller.command('save_mail', {'account': 'synthetic@163.com', 'secret': 'DUMMY',
                'output_dir': str(self.root / 'reports'), 'autostart': True})
        save.assert_called_once()
        auto.assert_called_once_with(True, launcher='C:/app/BensonMail.exe')
        text = (self.root / 'config.json').read_text()
        self.assertNotIn('DUMMY', text)

    def test_endpoint_bound_api_key_and_no_plaintext(self):
        with patch('benson_mail.bridge.platform.save_secret') as save:
            self.controller.command('save_ai', {'ai_provider': 'api', 'api_base': 'https://example.invalid/v1',
                'api_model': 'synthetic', 'key': 'DUMMY-API'})
        self.assertEqual(save.call_args.args[1], 'https://example.invalid/v1/chat/completions')
        self.assertNotIn('DUMMY-API', (self.root / 'config.json').read_text())
        self.assertEqual(self.controller.config['api_model'], 'synthetic')

    def test_requires_pause_and_credentials(self):
        with self.assertRaises(ValueError):
            self.controller.command('start', {})
        with patch.object(self.controller, 'active', return_value=True):
            with self.assertRaises(ValueError):
                self.controller.command('save_ai', {'ai_provider': 'codex'})

    def test_start_waits_for_previous_worker_to_stop(self):
        self.controller.service = Mock()
        self.controller.service.thread.is_alive.return_value = True
        self.controller.service.cancel.is_set.return_value = True
        with self.assertRaisesRegex(ValueError, '正在停止'):
            self.controller.command('start', {})

    def test_pipe_protocol_with_fixture_and_error_recovery(self):
        requests = [
            {'id': 1, 'command': 'config'},
            {'id': 2, 'command': 'interval', 'data': {'seconds': 0}},
            {'id': 3, 'command': 'reports', 'data': {'query': '合同.pdf'}},
            {'id': 4, 'command': 'shutdown'}]
        process = subprocess.run([sys.executable, 'main.py', '--bridge', '--fixture', str(self.root)],
            input='\n'.join(json.dumps(request) for request in requests) + '\n',
            encoding='utf-8', capture_output=True, timeout=15,
            cwd=Path(__file__).resolve().parent.parent)
        self.assertEqual(process.returncode, 0, process.stderr)
        replies = [json.loads(line) for line in process.stdout.splitlines()]
        self.assertEqual([reply['id'] for reply in replies], [1, 2, 3, 4])
        self.assertFalse(replies[1]['ok'])
        self.assertEqual(replies[2]['result'][0]['title'], '模拟合同检查')

    def test_status_events_and_settings_can_persist_together(self):
        with ThreadPoolExecutor(max_workers=2) as pool:
            def status_events():
                for _ in range(25):
                    self.controller.event({'status': '已暂停'})
            future = pool.submit(status_events)
            for seconds in range(10, 35):
                self.controller.command('interval', {'seconds': seconds})
            future.result()
        config = json.loads(self.controller.path.read_text(encoding='utf-8'))
        self.assertEqual(config['interval'], 34)
        self.assertFalse(config['enabled'])
