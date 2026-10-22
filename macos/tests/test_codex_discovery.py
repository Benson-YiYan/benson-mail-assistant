import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import runtime_paths

class CodexDiscoveryTests(unittest.TestCase):
    def test_saved_path_is_used_outside_shell_path(self):
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp)
            cli = home / 'custom codex'; cli.write_text('#!/bin/sh\n'); cli.chmod(0o700)
            (home / 'settings.json').write_text(json.dumps({'codex_path': str(cli)}))
            with patch.dict(os.environ, {'BENSON_MAIL_HOME': temp, 'BENSON_CODEX_PATH': ''}):
                self.assertEqual(runtime_paths.codex_executable(), str(cli))
    def test_explicit_path_precedes_saved_path(self):
        with tempfile.TemporaryDirectory() as temp:
            cli = Path(temp) / 'codex'; cli.touch(); cli.chmod(0o700)
            with patch.dict(os.environ, {'BENSON_MAIL_HOME': temp}):
                self.assertEqual(runtime_paths.codex_executable(str(cli)), str(cli))

    def test_custom_app_bundle_can_be_selected(self):
        with tempfile.TemporaryDirectory() as temp:
            app = Path(temp) / 'External disk' / 'Renamed Codex.app'
            cli = app / 'Contents/Resources/codex'; cli.parent.mkdir(parents=True); cli.touch(); cli.chmod(0o700)
            with patch.dict(os.environ, {'BENSON_MAIL_HOME': temp}):
                self.assertEqual(runtime_paths.codex_executable(str(app)), str(cli))

    def test_invalid_explicit_selection_does_not_use_another_install(self):
        with self.assertRaises(RuntimeError):
            runtime_paths.codex_executable('/nonexistent/custom-codex')

    def test_spotlight_finds_app_on_another_volume(self):
        from types import SimpleNamespace
        with tempfile.TemporaryDirectory() as temp:
            app = Path(temp) / 'Other Volume' / 'Renamed.app'
            cli = app / 'Contents/Resources/codex-cli/bin/codex'
            cli.parent.mkdir(parents=True); cli.touch(); cli.chmod(0o700)
            with patch.dict(os.environ, {'BENSON_MAIL_HOME': temp, 'BENSON_CODEX_PATH': ''}), patch('runtime_paths.shutil.which', return_value=None), patch('subprocess.run', return_value=SimpleNamespace(returncode=0, stdout=str(app)+'\n')):
                # Homebrew may be installed on the test machine; hide its candidates.
                original = runtime_paths.os.access
                with patch('runtime_paths.os.access', side_effect=lambda p, mode: str(p) == str(cli) and original(p, mode)):
                    self.assertEqual(runtime_paths.codex_executable(), str(cli))
