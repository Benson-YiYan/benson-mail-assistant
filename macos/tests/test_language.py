"""Language changes select future prompts; cached reports never call AI again."""
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
RUNTIME = Path(__file__).resolve().parents[1] / 'Runtime'
sys.path.insert(0, str(RUNTIME))
import ai_runner
from mail_prompt import ANALYSIS_PROMPT, ENGLISH_ANALYSIS_PROMPT, SPANISH_ANALYSIS_PROMPT, analysis_prompt
class ReportLanguageTests(unittest.TestCase):
    def test_defaults_and_six_english_requirements(self):
        for code in (None, '', 'zh', 'invalid'):
            self.assertEqual(analysis_prompt(code), ANALYSIS_PROMPT)
        self.assertEqual(analysis_prompt('en'), ENGLISH_ANALYSIS_PROMPT)
        for number in range(1, 7): self.assertIn(f'\n{number}. ', ENGLISH_ANALYSIS_PROMPT)
        self.assertIn('explanation in English', ENGLISH_ANALYSIS_PROMPT)
        self.assertIn("incoming message's language", ENGLISH_ANALYSIS_PROMPT)
        self.assertIn('## 1. New email', ENGLISH_ANALYSIS_PROMPT)
        self.assertIn('## 1. 新邮件提醒', ANALYSIS_PROMPT)
    def test_api_and_installed_harness_receive_selected_prompt(self):
        for provider in ('api', 'deepseek_harness'):
            target = 'ai_runner.complete' if provider == 'api' else 'deepseek_harness_ai.complete'
            with self.subTest(provider=provider), tempfile.TemporaryDirectory() as temporary:
                message = {'subject': '原始中文主题', 'attachments': []}
                with patch.object(ai_runner, 'api_config', return_value=({'ai_provider': provider, 'ui_language': 'en'}, 'synthetic')), patch(target, return_value='English report') as call:
                    ai_runner.analyze_api(message, Path(temporary))
                messages = call.call_args.args[3]
                self.assertEqual(messages[0]['content'], ENGLISH_ANALYSIS_PROMPT)
                self.assertEqual(json.loads(messages[1]['content'])['subject'], '原始中文主题')
    def test_codex_uses_english_and_cached_report_survives_language_change(self):
        spec = importlib.util.spec_from_file_location('language_daemon', RUNTIME / 'mail_daemon.py')
        daemon = importlib.util.module_from_spec(spec); spec.loader.exec_module(daemon)
        with tempfile.TemporaryDirectory() as temporary:
            daemon.DATA = Path(temporary)
            message = {'uid': 101, 'subject': '中文主题', 'attachments': []}
            def generate(args, **kwargs):
                self.assertEqual(args[-1], ENGLISH_ANALYSIS_PROMPT)
                Path(args[args.index('-o') + 1]).write_text('English six-section report')
                return type('Result', (), {'returncode': 0})()
            with patch.object(daemon, 'settings', return_value={'ui_language': 'en'}), patch.object(daemon, 'publish'), patch.object(daemon, 'notify'), patch.object(daemon, 'log'), patch.object(daemon, 'run_reader'), patch.object(daemon, 'export_report', return_value='fixture.txt'), patch.object(daemon, 'codex_executable', return_value='synthetic-codex'), patch.object(daemon.subprocess, 'run', side_effect=generate) as run:
                daemon.analyze(message)
                self.assertEqual(run.call_count, 1)
            with patch.object(daemon, 'publish'), patch.object(daemon, 'notify'), patch.object(daemon, 'log'), patch.object(daemon, 'run_reader'), patch.object(daemon, 'export_report', return_value='fixture.txt'), patch.object(daemon.subprocess, 'run') as run:
                daemon.analyze(message)
                run.assert_not_called()
            self.assertEqual((daemon.DATA / '101/answer.txt').read_text(), 'English six-section report')

    def test_spanish_prompt_and_future_api_language_preserve_original_mail(self):
        self.assertEqual(analysis_prompt('es'), SPANISH_ANALYSIS_PROMPT)
        for number in range(1,7): self.assertIn(f'\n{number}. ',SPANISH_ANALYSIS_PROMPT)
        self.assertIn('explicación en español',SPANISH_ANALYSIS_PROMPT)
        self.assertIn('idioma del mensaje recibido',SPANISH_ANALYSIS_PROMPT)
        for provider in ('api','deepseek_harness'):
            target='ai_runner.complete' if provider=='api' else 'deepseek_harness_ai.complete'
            with tempfile.TemporaryDirectory() as temporary, patch.object(ai_runner,'api_config',return_value=({'ai_provider':provider,'ui_language':'es'},'synthetic')), patch(target,return_value='Informe en español') as call:
                ai_runner.analyze_api({'subject':'原始中文主题','attachments':[]},Path(temporary))
                self.assertEqual(call.call_args.args[3][0]['content'],SPANISH_ANALYSIS_PROMPT)
                self.assertEqual(json.loads(call.call_args.args[3][1]['content'])['subject'],'原始中文主题')

    def test_unavailable_mail_report_and_notifications_follow_selected_language_without_ai(self):
        spec = importlib.util.spec_from_file_location('unavailable_language_daemon', RUNTIME / 'mail_daemon.py')
        daemon = importlib.util.module_from_spec(spec); spec.loader.exec_module(daemon)
        for code, first_heading, notification in (
            ('zh', '## 1. 新邮件提醒', '你有一封新邮件'),
            ('en', '## 1. New email', 'You have a new email'),
            ('es', '## 1. Correo nuevo', 'Tienes un correo nuevo'),
        ):
            with self.subTest(language=code), tempfile.TemporaryDirectory() as temporary:
                daemon.DATA = Path(temporary)
                message = {'uid': 202, 'subject': '原始主题保持', 'from': 'sender@example.invalid', 'unavailable': True}
                settings = {'ui_language': code, 'ai_provider': 'api'}
                with patch.object(daemon, 'settings', return_value=settings), patch.object(daemon, 'publish'), \
                     patch.object(daemon, 'notify') as notify, patch.object(daemon, 'log'), \
                     patch.object(daemon, 'run_reader') as ack, \
                     patch.object(daemon, 'export_report', return_value='/synthetic/report.md'), \
                     patch.object(daemon.subprocess, 'run') as process, patch.object(ai_runner, 'analyze_api') as analyze:
                    daemon.analyze(message)
                    answer = daemon.DATA / '202/answer.txt'
                    before = answer.read_bytes()
                    text = before.decode()
                    self.assertTrue(text.startswith(first_heading))
                    self.assertEqual(text.count('\n\n## '), 5)
                    self.assertEqual(notify.call_args_list[0].args[1], notification)
                    self.assertIn('sender@example.invalid', notify.call_args_list[0].args[0])
                    self.assertIn('原始主题保持', notify.call_args_list[0].args[0])
                    if code == 'es':
                        self.assertIn('revisa el archivo o la papelera', text)
                        self.assertEqual(notify.call_args_list[-1].args[1], '✅ Informe Markdown del correo listo')
                    ack.assert_called_with('ack', '202')
                    settings['ui_language'] = 'en' if code != 'en' else 'es'
                    daemon.analyze(message)
                    self.assertEqual(answer.read_bytes(), before)
                    analyze.assert_not_called(); process.assert_not_called()
