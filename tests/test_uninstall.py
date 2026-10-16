import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from benson_mail.uninstall import report_files, remove_reports, installation, copy_runtime, cleanup_installation


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
            other.write_text('保留', encoding='utf-8')
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
                installation(temporary)
            program = Path(temporary) / 'BensonMail-202610161600'
            program.mkdir()
            with self.assertRaises(ValueError):
                installation(program)

    def test_stage_runtime_outside_installation(self):
        with tempfile.TemporaryDirectory() as temporary:
            program = Path(temporary) / 'BensonMail-202610161600'
            (program / '_internal').mkdir(parents=True)
            (program / '_internal/python.dll').write_bytes(b'synthetic')
            name = 'Uninstall-BensonMail-202610161600.exe'
            (program / name).write_bytes(b'synthetic-helper')
            staged = copy_runtime(program, name)
            try:
                self.assertFalse(staged.is_relative_to(program.resolve()))
                self.assertEqual(staged.read_bytes(), b'synthetic-helper')
                self.assertTrue((staged.parent / '_internal/python.dll').is_file())
            finally:
                import shutil
                shutil.rmtree(staged.parent)

    @unittest.skipUnless(sys.platform == 'win32', 'Windows deletion helper')
    def test_native_cleanup_without_powershell(self):
        with tempfile.TemporaryDirectory(prefix="卸载测试 '& ") as temporary:
            program = Path(temporary) / 'BensonMail-202610161600'
            (program / '_internal').mkdir(parents=True)
            (program / 'Uninstall-BensonMail-202610161600.exe').write_bytes(b'synthetic')
            keep = Path(temporary) / '保留.txt'
            keep.write_text('keep')
            data = Path(temporary) / 'user-data'
            data.mkdir()
            (data / 'secret.bin').write_bytes(b'synthetic-encrypted')
            from benson_mail import platform_windows as platform
            name = 'BensonMail-UninstallUnitTest'
            platform.set_autostart(True, name)
            try:
                cleanup_installation(program, data, False, lambda _: None,
                                     registry_name=name, shortcut_places=[])
                self.assertFalse(platform.has_autostart(name))
            finally:
                platform.set_autostart(False, name)
            self.assertFalse(program.exists())
            self.assertFalse(data.exists())
            self.assertTrue(keep.exists())
