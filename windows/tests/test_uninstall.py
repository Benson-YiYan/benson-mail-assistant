import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from benson_mail.uninstall import report_files, remove_reports, installation, copy_runtime, cleanup_installation, remove_empty_archive_wrapper, clear_user_data


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

    def test_remove_empty_owned_dates_and_keep_selected_report_root(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / 'chosen'; root.mkdir()
            (root / '2026-10-17').mkdir()
            (root / 'other-empty-user-folder').mkdir()
            self.assertEqual(remove_reports(root), 0)
            self.assertFalse((root / '2026-10-17').exists())
            self.assertTrue(root.exists() and (root / 'other-empty-user-folder').exists())

    def test_remove_only_empty_same_version_explorer_wrapper(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            wrapper = root / 'BensonMail-Windows-x64-202610171300'; wrapper.mkdir()
            self.assertTrue(remove_empty_archive_wrapper(wrapper / 'BensonMail-202610171300'))
            wrapper.mkdir(); unrelated = wrapper / 'keep.txt'; unrelated.write_text('keep')
            self.assertFalse(remove_empty_archive_wrapper(wrapper / 'BensonMail-202610171300'))
            self.assertTrue(unrelated.exists())
            unrelated.unlink()
            self.assertFalse(remove_empty_archive_wrapper(wrapper / 'BensonMail-202610171301'))
            self.assertTrue(wrapper.exists())
            for name in ('Desktop', 'Downloads', 'Documents'):
                selected = root / name; selected.mkdir()
                self.assertFalse(remove_empty_archive_wrapper(selected / 'BensonMail-202610171300'))
                self.assertTrue(selected.exists())

    def test_keep_configuration_prunes_empty_owned_directories(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / 'data'; root.mkdir()
            (root / 'config.json').write_text('{"ui_language":"en"}')
            (root / 'api-keys').mkdir(); (root / 'mail-secrets').mkdir()
            clear_user_data(root, True)
            self.assertEqual({p.name for p in root.iterdir()}, {'config.json'})
            (root / 'config.json').unlink()
            clear_user_data(root, True)
            self.assertFalse(root.exists())

    def test_refuses_arbitrary_program_directory(self):
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaises(ValueError):
                installation(temporary)
            program = Path(temporary) / 'BensonMail-202610161600'
            program.mkdir()
            with self.assertRaises(ValueError):
                installation(program)

    def test_installed_marker_authorizes_custom_installation_folder(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary) / '自选安装位置'; (folder / '_internal').mkdir(parents=True)
            marker = folder / '.benson-installed.json'
            for contents in ('broken', '{"installed":false}', '[]'):
                marker.write_text(contents)
                with self.assertRaises(ValueError): installation(folder)
            marker.write_text('{"installed":true}')
            self.assertEqual(installation(folder), folder.resolve())

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
