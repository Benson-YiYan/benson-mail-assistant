import threading
import unittest
from unittest.mock import patch
from benson_mail.deepseek_harness_ai import complete, discover

class HarnessTests(unittest.TestCase):
    def test_external_process_preserves_prompt_and_extracts_final(self):
        from benson_mail.harness_smoke import run
        self.assertTrue(run()['ok'])

    def test_cancel_does_not_launch_or_discover(self):
        stop = threading.Event(); stop.set()
        with patch('benson_mail.deepseek_harness_ai.command') as launcher:
            with self.assertRaisesRegex(RuntimeError, '分析已停止'):
                complete(messages=[], stop=stop)
            launcher.assert_not_called()

    def test_missing_explicit_install_does_not_fallback_or_download(self):
        with self.assertRaisesRegex(RuntimeError, '未找到已安装'):
            discover('/nonexistent/BensonMail-test-dsh')

    def test_failure_does_not_echo_stderr_or_key(self):
        import sys
        with patch('benson_mail.deepseek_harness_ai.command', return_value=[sys.executable, '-c',
                'import sys;sys.stderr.write("synthetic-secret");sys.exit(7)']):
            with self.assertRaisesRegex(RuntimeError, '退出码 7') as error:
                complete(messages=[{'role': 'user', 'content': 'synthetic-email'}])
            self.assertNotIn('synthetic-secret', str(error.exception))
            self.assertNotIn('synthetic-email', str(error.exception))

    @unittest.skipUnless(__import__('os').name == 'nt', 'Windows cmd launcher')
    def test_windows_installed_cmd_path_with_spaces_and_ampersand(self):
        import sys, tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory(prefix='BensonMail CLI & test ') as temporary:
            root = Path(temporary)
            fixture = root / 'fixture.py'
            fixture.write_text('import sys,json; assert sys.stdin.buffer.read().decode("utf-8") == "synthetic input"; print(json.dumps({"type":"final","text":"OK"}))', encoding='utf-8')
            launcher = root / 'dsh.cmd'
            launcher.write_text('@echo off\n"' + sys.executable + '" "' + str(fixture) + '" %*\n', encoding='utf-8')
            self.assertEqual(complete(messages=[{'role':'user','content':'synthetic input'}], cli_path=str(launcher)), 'OK')
