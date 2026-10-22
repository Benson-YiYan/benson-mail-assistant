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
    def test_codex_detect_does_not_save_or_require_pause(self):
        original=dict(self.controller.config)
        with patch('benson_mail.bridge.platform.discover_codex',return_value=['C:/Codex/resources/codex.exe']), patch('benson_mail.bridge.platform.verify_codex',return_value=True), patch.object(self.controller,'persist') as persist, patch.object(self.controller,'paused') as paused:
            self.assertEqual(self.controller.command('codex_detect',{}),'C:/Codex/resources/codex.exe')
            self.assertEqual(self.controller.config,original)
            persist.assert_not_called(); paused.assert_not_called()

    def test_migration_failure_keeps_controller_available_with_warning(self):
        with patch('benson_mail.report_layout.migrate_reports', side_effect=OSError('synthetic denied')):
            controller = Controller(self.root, lambda event: None)
        controller.config['output_dir'] = str(self.root / 'reports')
        result = controller.command('config', {})
        self.assertEqual(result['report_migration']['errors'][0]['error'], 'OSError')
        self.assertEqual(controller.command('reports', {}), [])

    def test_report_tree_view_preference_persists_without_saving_page_settings(self):
        before = self.controller.path.read_bytes() if self.controller.path.exists() else None
        self.assertFalse(self.controller.command('report_view', {})['report_tree'])
        self.assertTrue(self.controller.command('report_view', {'report_tree': True})['report_tree'])
        fresh = Controller(self.root, lambda event: None)
        self.assertTrue(fresh.command('report_view', {})['report_tree'])
        self.assertFalse(fresh.command('report_view', {'report_tree': False})['report_tree'])
        after = self.controller.path.read_bytes() if self.controller.path.exists() else None
        self.assertEqual(before, after)
        with self.assertRaises(ValueError): fresh.command('report_view', {'report_tree': 'yes'})

    def test_sender_policy_bridge_persists_global_settings_and_known_senders(self):
        service = Mock()
        service.config = {}
        self.controller.service = service
        day = self.root / 'reports' / 'day'
        day.mkdir(parents=True)
        from benson_mail.report_metadata import write_metadata
        report=day/'mail.md'; report.write_text('Synthetic report',encoding='utf-8')
        write_metadata(self.root,report,{'sender': 'Known Sender <known@example.invalid>'})
        self.controller.config['output_dir'] = str(day.parent)
        result = self.controller.command('policy_save', {'mode': 'whitelist', 'addresses': ['Benson <allowed@example.invalid>'], 'skip_spam': True})
        expected = {'mode': 'whitelist', 'addresses': ['allowed@example.invalid'], 'skip_spam': True}
        self.assertEqual(result['policy'], expected)
        self.assertEqual(self.controller.config['mail_policy'], expected)
        self.assertEqual(service.config['mail_policy'], expected)
        self.assertEqual(json.loads(self.controller.path.read_text())['mail_policy'], expected)
        self.assertIn('known@example.invalid', result['senders'])
        fresh = Controller(self.root, lambda event: None)
        self.assertEqual(fresh.command('policy_status', {})['policy'], expected)

    def test_sender_policy_bridge_queues_without_ai_and_deletes_only_local_records(self):
        from benson_mail.mail_policy import intercept
        self.controller.fixture = True
        self.controller.command('policy_save', {'mode': 'blacklist', 'addresses': ['skip@example.invalid'], 'skip_spam': False})
        self.assertTrue(intercept(self.root, {'subject': 'Synthetic skipped mail', 'sender': 'skip@example.invalid', 'attachments': []},
                                  'fixture-mailbox', 'fixture-validity', '1'))
        status = self.controller.command('policy_status', {})
        identifier = status['records'][0]['id']
        with patch('benson_mail.ai_api.complete') as complete, patch('benson_mail.bridge.IMAPMailbox') as mailbox:
            queued = self.controller.command('policy_summarize_records', {'ids': [identifier]})
            self.assertEqual(queued['records'][0]['state'], 'queued')
            removed = self.controller.command('policy_remove_records', {'ids': [identifier]})
            self.assertEqual(removed['records'], [])
            complete.assert_not_called()
            mailbox.assert_not_called()
        service = Mock()
        service.thread.is_alive.return_value = True
        service.cancel.is_set.return_value = False
        self.controller.service = service
        self.controller.fixture = False
        self.assertTrue(intercept(self.root, {'subject': 'Second synthetic skipped mail', 'sender': 'skip@example.invalid', 'attachments': []},
                                  'fixture-mailbox', 'fixture-validity', '2'))
        identifier = self.controller.command('policy_status', {})['records'][0]['id']
        with patch('benson_mail.ai_api.complete') as complete, patch('benson_mail.bridge.IMAPMailbox') as mailbox:
            self.controller.command('policy_summarize_records', {'ids': [identifier]})
            service.request_check.assert_called_once()
            complete.assert_not_called()
            mailbox.assert_not_called()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.controller = Controller(self.root, lambda event: None, launcher='C:/app/BensonMail.exe')

    def tearDown(self):
        self.temp.cleanup()

    def test_conversation_fixture_isolated_persistent_and_current_language(self):
        day = self.root / 'reports' / '2026-10-20'
        day.mkdir(parents=True)
        report = day / 'synthetic.md'
        report.write_text('original', encoding='utf-8')
        other = day / 'other.md'
        other.write_text('other report', encoding='utf-8')
        attachment = self.root / 'notes.txt'
        attachment.write_text('SYNTHETIC FILE', encoding='utf-8')
        self.controller.config.update(output_dir=str(day.parent), ui_language='es')
        self.controller.fixture = True
        updated = self.controller.command('report_retry', {'path': str(report)})
        self.assertIn('Correo nuevo', updated['text'])
        self.assertEqual(report.read_text(encoding='utf-8'), updated['text'])
        first = self.controller.command('chat_send', {'path': str(report), 'text': 'SYNTHETIC QUESTION', 'files': [str(attachment)]})
        self.assertEqual(len(first['messages']), 2)
        self.assertEqual(first['messages'][0]['files'], ['notes.txt'])
        self.assertIn('Respuesta sintética', first['answer'])
        self.assertEqual(self.controller.command('chat_history', {'path': str(report)})['messages'], first['messages'])
        self.assertEqual(self.controller.command('chat_history', {'path': str(other)})['messages'], [])
        for name in ('report_retry', 'chat_send', 'chat_history'):
            with self.assertRaises(ValueError):
                self.controller.command(name, {'path': str(attachment), 'text': 'bad'})

    def test_report_retry_waits_for_active_processing_and_updates_pending_cache(self):
        import threading
        report = self.root / 'reports' / 'day' / 'sample.md'
        report.parent.mkdir(parents=True)
        report.write_text('Original report', encoding='utf-8')
        self.controller.config['output_dir'] = str(report.parent.parent)
        service = Mock()
        service.activity = threading.Lock()
        service.state = {'pending': {'42': {'target': str(report), 'answer': 'old cached answer'}}}
        self.controller.service = service
        service.activity.acquire()
        try:
            with patch('benson_mail.mail_chat.report_retry') as retry:
                with self.assertRaisesRegex(ValueError, '当前任务'):
                    self.controller.command('report_retry', {'path': str(report)})
                retry.assert_not_called()
        finally:
            service.activity.release()
        with patch('benson_mail.mail_chat.report_retry', return_value={'path': str(report), 'text': 'new answer'}):
            result = self.controller.command('report_retry', {'path': str(report)})
        self.assertEqual(result['text'], 'new answer')
        self.assertEqual(service.state['pending']['42']['answer'], 'new answer')
        service.persist.assert_called_once()
        self.assertTrue(service.activity.acquire(blocking=False))
        service.activity.release()

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
        from benson_mail.report_metadata import write_metadata
        write_metadata(self.root,report,{
            'subject': '原始标题', 'sender': 'demo@example.invalid', 'body': '合同正文',
            'received': '2026-10-17T01:15:00+00:00', 'attachments': [{'name': '合同.pdf'}]})
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

    def test_edited_address_default_and_custom_login_persist_without_network(self):
        with patch('benson_mail.bridge.platform.save_secret'), patch('benson_mail.bridge.platform.set_autostart'):
            base={'secret':'SYNTHETIC', 'output_dir':str(self.root/'reports'), 'host':'imap.example.invalid'}
            self.controller.command('save_mail', {**base, 'account':'old@example.invalid', 'username':''})
            self.assertEqual(self.controller.config['username'], 'old@example.invalid')
            self.controller.command('save_mail', {**base, 'account':'new@example.invalid', 'username':''})
            self.assertEqual(self.controller.config['username'], 'new@example.invalid')
            self.controller.command('save_mail', {**base, 'account':'custom@example.invalid', 'username':r'DOMAIN\custom-user'})
            self.assertEqual(self.controller.config['username'], r'DOMAIN\custom-user')
            profiles=self.controller.profiles()
            self.assertEqual(len(profiles), 1)
            self.assertEqual(profiles[0]['account'], 'custom@example.invalid')
            self.assertEqual(profiles[0]['username'], r'DOMAIN\custom-user')

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
