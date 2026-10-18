import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'Runtime'))
import threading
import unittest
from unittest.mock import patch
from deepseek_harness_ai import complete, discover

class HarnessTests(unittest.TestCase):
    def test_external_process_preserves_prompt_and_extracts_final(self):
        from harness_smoke import run
        self.assertTrue(run()['ok'])

    def test_cancel_does_not_launch_or_discover(self):
        stop = threading.Event(); stop.set()
        with patch('deepseek_harness_ai.command') as launcher:
            with self.assertRaisesRegex(RuntimeError, '分析已停止'):
                complete(messages=[], stop=stop)
            launcher.assert_not_called()

    def test_missing_explicit_install_does_not_fallback_or_download(self):
        with self.assertRaisesRegex(RuntimeError, '未找到已安装'):
            discover('/nonexistent/BensonMail-test-dsh')

    def test_failure_does_not_echo_stderr_or_key(self):
        import sys
        with patch('deepseek_harness_ai.command', return_value=[sys.executable, '-c',
                'import sys;sys.stderr.write("synthetic-secret");sys.exit(7)']):
            with self.assertRaisesRegex(RuntimeError, '退出码 7') as error:
                complete(messages=[{'role': 'user', 'content': 'synthetic-email'}])
            self.assertNotIn('synthetic-secret', str(error.exception))
            self.assertNotIn('synthetic-email', str(error.exception))
