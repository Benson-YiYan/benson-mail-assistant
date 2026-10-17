import importlib.util
import threading
import unittest

from benson_mail.deepseek_harness_ai import complete


@unittest.skipUnless(importlib.util.find_spec('deepseek_harness'), 'Official Harness SDK required')
class HarnessTests(unittest.TestCase):
    def test_actual_runtime_messages_original_prompt_and_no_tools(self):
        from benson_mail.harness_smoke import run
        self.assertTrue(run()["ok"])

    def test_cancel_before_start_and_url_validation(self):
        stop = threading.Event()
        stop.set()
        with self.assertRaisesRegex(RuntimeError, '分析已停止'):
            complete('https://example.invalid', 'model', 'key', [], stop)
        with self.assertRaises(ValueError):
            complete('http://example.invalid', 'model', 'key', [])

    def test_errors_keep_status_without_echoing_credentials(self):
        from unittest.mock import patch
        class Failing:
            def __init__(self, **kwargs): pass
            def __enter__(self): raise RuntimeError('HTTP 401 secret=synthetic-private-key')
            def __exit__(self, *args): pass
        with patch('benson_mail.deepseek_harness_ai._sdk', return_value=Failing):
            with self.assertRaisesRegex(RuntimeError, 'HTTP 401') as caught:
                complete('https://example.invalid', 'model', 'synthetic-private-key', [])
        self.assertNotIn('synthetic-private-key', str(caught.exception))
