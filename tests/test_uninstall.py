import base64
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from benson_mail.uninstall import report_files, remove_reports, delete_command


class UninstallTests(unittest.TestCase):
    def test_reports_preserve_unrelated_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            day = root / '2026-10-16'
            day.mkdir()
            report = day / '测试-16-20.txt'
            report.write_text('测试', encoding='utf-8')
            meta = report.with_suffix('.mail.json')
            meta.write_text(json.dumps({'subject': '测试', 'sender': 'demo', 'received': '2026-10-16'}))
            other = day / '我的合同.txt'
            other.write_text('保留')
            outside = root / 'other'
            outside.mkdir()
            try:
                (root / '2026-10-17').symlink_to(outside, target_is_directory=True)
            except OSError:
                pass
            self.assertEqual(set(report_files(root)), {report, meta})
            self.assertEqual(remove_reports(root), 2)
            self.assertFalse(report.exists())
            self.assertFalse(meta.exists())
            self.assertTrue(other.exists())
            self.assertTrue(outside.exists())

    def test_refuses_arbitrary_program_directory(self):
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaises(ValueError):
                delete_command(temporary, 1)
            program = Path(temporary) / 'BensonMail-202610161600'
            program.mkdir()
            with self.assertRaises(ValueError):
                delete_command(program, 1)

    @unittest.skipUnless(sys.platform == 'win32', 'Windows deletion helper')
    def test_actual_deferred_program_deletion(self):
        with tempfile.TemporaryDirectory(prefix="卸载测试 '& ") as temporary:
            program = Path(temporary) / 'BensonMail-202610161600'
            (program / '_internal').mkdir(parents=True)
            (program / 'Uninstall-BensonMail-202610161600.exe').write_bytes(b'synthetic')
            keep = Path(temporary) / '保留.txt'
            keep.write_text('keep')
            script = delete_command(program, 2147483647, notify=False)
            encoded = base64.b64encode(script.encode('utf-16le')).decode('ascii')
            subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-EncodedCommand', encoded],
                           check=True, capture_output=True, timeout=20)
            self.assertFalse(program.exists())
            self.assertTrue(keep.exists())
