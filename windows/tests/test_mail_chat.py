"""Offline report/chat behavior; never contacts email, AI, or real credential stores."""
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'windows'))
from benson_mail import mail_chat as windows
spec = importlib.util.spec_from_file_location('mac_mail_chat_tests', ROOT / 'macos/Runtime/mail_chat.py')
mac = importlib.util.module_from_spec(spec); spec.loader.exec_module(mac)
sys.path.insert(0, str(ROOT / 'macos/Runtime'))

class MailChatTests(unittest.TestCase):
    def fixture(self, module, language='en'):
        temporary = tempfile.TemporaryDirectory(); self.addCleanup(temporary.cleanup)
        root = Path(temporary.name); output = root / 'reports'; output.mkdir()
        config = {'output_dir': str(output), 'ui_language': language, 'ai_provider': 'api', 'api_base': 'https://example.invalid/v1', 'api_model': 'fixture-model'}
        configfile = root / ('config.json' if module is windows else 'settings.json')
        configfile.write_text(json.dumps(config))
        report = output / 'fixture.md'; report.write_text('ORIGINAL REPORT')
        report.with_suffix('.mail.json').write_text(json.dumps({'subject': 'Synthetic only', 'sender': 'fixture@example.invalid', 'body': 'Original mail fact 42', 'attachments': [{'name': 'original.txt', 'text': 'Original attachment fact'}]}))
        return root, report, config

    def test_retry_current_language_original_data_and_failure(self):
        for module in (windows, mac):
            for language, snippet in [('zh', '中文'), ('en', 'English'), ('es', 'español')]:
                with self.subTest(platform=module.__name__, language=language):
                    root, report, _ = self.fixture(module, language)
                    with patch.object(module, '_complete', return_value='## New report') as provider:
                        result = module.report_retry(root, report)
                    self.assertEqual(report.read_text(), result['text'])
                    messages = provider.call_args.args[2]
                    self.assertIn(snippet, messages[0]['content'])
                    self.assertIn('Original mail fact 42', messages[1]['content'])
                    self.assertIn('Original attachment fact', messages[1]['content'])
                    before = report.read_bytes()
                    with patch.object(module, '_complete', side_effect=RuntimeError('offline provider failed')):
                        with self.assertRaises(RuntimeError): module.report_retry(root, report)
                    self.assertEqual(report.read_bytes(), before)

    def test_missing_original_retry_errors_chat_discloses_and_boundaries(self):
        for module in (windows, mac):
            root, report, _ = self.fixture(module)
            report.with_suffix('.mail.json').unlink()
            with patch.object(module, '_complete', return_value='Discussing existing report only') as provider:
                with self.assertRaisesRegex(ValueError, 'Original mail data'): module.report_retry(root, report)
                self.assertFalse(provider.called)
                module.chat_send(root, report, 'What is known?', [])
                context = provider.call_args.args[2][1]['content']
                self.assertIn('original_mail_available', context); self.assertIn('false', context)
                self.assertIn('ORIGINAL REPORT', context)
            outside = root / 'outside.md'; outside.write_text('outside')
            with self.assertRaises(ValueError): module.chat_history(root, outside)

    def test_files_history_and_per_mail_isolation(self):
        for module in (windows, mac):
            root, report, _ = self.fixture(module)
            attachment = root / 'selected.txt'; attachment.write_text('User file fact 99')
            with patch.object(module, '_complete', return_value='Answer') as provider:
                first = module.chat_send(root, report, 'Compare these', [str(attachment)])
                self.assertIn('User file fact 99', provider.call_args.args[2][-1]['content'])
                self.assertEqual(first['messages'][0]['files'][0]['name'], 'selected.txt')
                self.assertEqual(attachment.read_text(), 'User file fact 99')
            saved = module.chat_history(root, report)
            self.assertEqual(len(saved['messages']), 2)
            other = report.with_name('other.md'); other.write_text('Other report')
            self.assertEqual(module.chat_history(root, other)['messages'], [])
            unsupported = root / 'binary.exe'; unsupported.write_bytes(b'not executable')
            with patch.object(module, '_complete') as provider:
                with self.assertRaisesRegex(ValueError, 'Could not read file'): module.chat_send(root, report, 'Read', [str(unsupported)])
                self.assertFalse(provider.called)
            self.assertEqual(module.chat_history(root, report)['messages'], saved['messages'])

    def test_compression_keeps_full_history_recent_turns_and_summary(self):
        for module in (windows, mac):
            root, report, _ = self.fixture(module)
            location = module._history_path(root, report.resolve())
            state = module._load_history(location, report.resolve())
            state['messages'] = [{'role': 'user' if i % 2 == 0 else 'assistant', 'content': f'Unique turn {i} ' + 'x'*600} for i in range(12)]
            module._save_history(location, state)
            with patch.object(module, 'MAX_CONTEXT', 8000), patch.object(module, '_complete', side_effect=['Compressed decisions remain', 'Final answer']) as provider:
                result = module.chat_send(root, report, 'Q'*1600, [])
            self.assertTrue(result['compressed']); self.assertEqual(len(result['messages']), 14)
            self.assertEqual(result['messages'][0]['content'], state['messages'][0]['content'])
            final = provider.call_args.args[2]
            transcript = '\n'.join(m['content'] for m in final)
            self.assertIn('Compressed decisions remain', transcript)
            for i in range(6,12): self.assertIn(f'Unique turn {i} ', transcript)
            self.assertNotIn('Unique turn 0 ', transcript)
            self.assertEqual(module.chat_history(root, report)['summary'], 'Compressed decisions remain')

    def test_compression_failure_does_not_change_full_history(self):
        for module in (windows, mac):
            root, report, _ = self.fixture(module)
            location = module._history_path(root, report.resolve()); state = module._load_history(location, report.resolve())
            state['messages'] = [{'role': 'user' if i % 2 == 0 else 'assistant', 'content': str(i)+'x'*600} for i in range(12)]
            module._save_history(location, state); before = location.read_bytes()
            with patch.object(module, 'MAX_CONTEXT', 8000), patch.object(module, '_complete', side_effect=RuntimeError('compression failed')):
                with self.assertRaises(RuntimeError): module.chat_send(root, report, 'Q'*1600, [])
            self.assertEqual(location.read_bytes(), before)

    def test_provider_adapters_preserve_messages_and_configuration(self):
        from benson_mail import ai_api, deepseek_harness_ai, platform_windows
        root, report, config = self.fixture(windows)
        keypath = root / 'api-keys' / (windows.hashlib.sha256(ai_api.identity(config['api_base']).encode()).hexdigest()+'.bin')
        keypath.parent.mkdir(); keypath.write_bytes(b'fake protected fixture')
        messages = [{'role':'system','content':'Policy'}, {'role':'user','content':'Question'}, {'role':'assistant','content':'Earlier answer'}, {'role':'user','content':'Followup'}]
        with patch.object(platform_windows, 'load_secret', return_value='synthetic-key'), patch.object(ai_api, 'complete', return_value='API answer') as transport:
            self.assertEqual(windows._complete(root, config, messages), 'API answer')
            self.assertEqual(transport.call_args.args[:4], (config['api_base'], config['api_model'], 'synthetic-key', messages))
        with patch.object(deepseek_harness_ai, 'complete', return_value='Harness answer') as transport:
            windows._complete(root, {**config,'ai_provider':'deepseek_harness','harness_path':'fixture-dsh'}, messages)
            self.assertEqual(transport.call_args.kwargs['cli_path'], 'fixture-dsh')
            self.assertEqual(json.loads(transport.call_args.args[3][1]['content'])['conversation'], messages[1:])
        def codex_run(args, **kwargs):
            self.assertIn('--sandbox', args); self.assertIn('read-only', args)
            self.assertEqual(json.loads(kwargs['input'])['conversation'], messages)
            Path(args[args.index('-o')+1]).write_text('Codex answer')
            return type('Result',(),{'returncode':0})()
        with patch.object(windows.subprocess,'run',side_effect=codex_run):
            self.assertEqual(windows._complete(root,{**config,'ai_provider':'codex','codex_command':['fixture-codex']},messages),'Codex answer')

if __name__ == '__main__': unittest.main()
