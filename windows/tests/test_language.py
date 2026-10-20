import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch
from benson_mail.bridge import Controller
from benson_mail.core import APIAnalyzer, CodexAnalyzer, ANALYSIS_PROMPT, ENGLISH_ANALYSIS_PROMPT, SPANISH_ANALYSIS_PROMPT, analysis_prompt

class LanguageTests(unittest.TestCase):
    def test_original_default_and_english_requirements(self):
        self.assertEqual(analysis_prompt(), ANALYSIS_PROMPT)
        self.assertEqual(analysis_prompt('zh'), ANALYSIS_PROMPT)
        self.assertEqual(analysis_prompt('en'), ENGLISH_ANALYSIS_PROMPT)
        self.assertIn('six numbered sections in English', ENGLISH_ANALYSIS_PROMPT)
        self.assertIn('English explanation', ENGLISH_ANALYSIS_PROMPT)
        self.assertIn("incoming message's language", ENGLISH_ANALYSIS_PROMPT)
    def test_both_transports_select_english_without_translating_input(self):
        for provider in ('api', 'deepseek_harness'):
            target = 'benson_mail.ai_api.complete' if provider == 'api' else 'benson_mail.deepseek_harness_ai.complete'
            analyzer = APIAnalyzer({'ai_provider': provider, 'ui_language': 'en'}, 'synthetic')
            with patch(target, return_value='English report') as transport:
                analyzer({'subject': '中文主题'}, threading.Event())
            prompt = transport.call_args.args[3][0]['content']
            self.assertTrue(prompt.startswith(ENGLISH_ANALYSIS_PROMPT))
            self.assertIn('中文主题', prompt)
    def test_language_persists_and_updates_running_analyzers_without_ai(self):
        with tempfile.TemporaryDirectory() as temporary:
            controller = Controller(temporary, lambda event: None)
            service = Mock(); service.config = {'ui_language': 'zh'}
            service.analyzer = APIAnalyzer({'ui_language': 'zh'}, 'synthetic')
            controller.service = service
            with patch('benson_mail.ai_api.complete') as complete:
                controller.command('save_language', {'ui_language': 'en'})
                complete.assert_not_called()
            self.assertEqual(service.config['ui_language'], 'en')
            self.assertEqual(service.analyzer.config['ui_language'], 'en')
            service.start.assert_not_called(); service.stop.assert_not_called()
            self.assertEqual(Controller(temporary, lambda event: None).config['ui_language'], 'en')
            with self.assertRaises(ValueError): controller.command('save_language', {'ui_language': 'invalid'})
    def test_codex_prompt_language_and_data_preserved(self):
        import io
        class Input(io.BytesIO):
            def close(self): self.saved = self.getvalue()
        process = Mock(); process.stdin = Input(); process.poll.return_value = 0; process.returncode = 0
        def launch(*args, **kwargs):
            kwargs['stdout'].write(b'English report'); return process
        with tempfile.TemporaryDirectory() as temporary, patch('benson_mail.core.subprocess.Popen', side_effect=launch):
            analyzer = CodexAnalyzer(['synthetic-codex'], temporary, {'ui_language': 'en'})
            self.assertEqual(analyzer({'subject': '中文主题'}, threading.Event()), 'English report')
            prompt = process.stdin.saved.decode()
            self.assertTrue(prompt.startswith(ENGLISH_ANALYSIS_PROMPT)); self.assertIn('中文主题', prompt)

    def test_spanish_prompts_and_language_persistence(self):
        self.assertEqual(analysis_prompt('es'),SPANISH_ANALYSIS_PROMPT)
        self.assertIn('seis secciones numeradas en español',SPANISH_ANALYSIS_PROMPT)
        self.assertIn('explicación en español',SPANISH_ANALYSIS_PROMPT)
        for provider in ('api','deepseek_harness'):
            target='benson_mail.ai_api.complete' if provider=='api' else 'benson_mail.deepseek_harness_ai.complete'
            with patch(target,return_value='Informe en español') as transport:
                APIAnalyzer({'ai_provider':provider,'ui_language':'es'},'synthetic')({'subject':'中文主题'},threading.Event())
            self.assertTrue(transport.call_args.args[3][0]['content'].startswith(SPANISH_ANALYSIS_PROMPT))
            self.assertIn('中文主题',transport.call_args.args[3][0]['content'])
        with tempfile.TemporaryDirectory() as temporary:
            Controller(temporary,lambda event:None).command('save_language',{'ui_language':'es'})
            self.assertEqual(Controller(temporary,lambda event:None).config['ui_language'],'es')
