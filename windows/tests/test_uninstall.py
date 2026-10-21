import json
import io
import os
import shutil
from unittest.mock import patch
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from benson_mail.uninstall import report_files, remove_reports, installation, copy_runtime, cleanup_installation, remove_empty_archive_wrapper, clear_user_data


class UninstallTests(unittest.TestCase):
    def test_nested_reports_remove_owned_leaves_without_following_links(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve() / 'reports'
            sender = root / 'receiver@example.invalid' / '2026-10-21' / 'From sender@example.invalid'
            sender.mkdir(parents=True)
            report = sender / 'Example-11-53.md'; report.write_text('report')
            metadata = report.with_suffix('.mail.json')
            metadata.write_text(json.dumps({'subject': 'Example', 'sender': 'sender@example.invalid', 'received': '2026-10-21'}))
            keep = root / 'other-user-files'; keep.mkdir(); (keep / 'contract.md').write_text('keep')
            outside = Path(temporary) / 'outside'; outside.mkdir()
            (outside / 'foreign.md').write_text('keep')
            try: (sender / 'linked').symlink_to(outside, target_is_directory=True)
            except OSError: pass
            self.assertEqual(set(report_files(root)), {report, metadata})
            self.assertEqual(remove_reports(root), 2)
            self.assertTrue((outside / 'foreign.md').exists())
            self.assertTrue((keep / 'contract.md').exists())
            self.assertTrue(root.exists())

    def test_private_metadata_identifies_reports_for_delete_and_preserve(self):
        from benson_mail.report_metadata import write_metadata, metadata_path, read_metadata
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary); data=root/'data'; output=root/'reports'
            report=output/'owner@example.invalid'/'2026-10-21'/'From sender@example.invalid'/'example-11-53.md'
            report.parent.mkdir(parents=True); report.write_text('Original report',encoding='utf-8')
            message={'subject':'Example','sender':'sender@example.invalid','received':'2026-10-21','body':'Original email'}
            private=write_metadata(data,report,message)
            (data/'secret.bin').write_bytes(b'synthetic-secret')
            self.assertEqual(report_files(output,data),[report.resolve()])
            clear_user_data(data,False,True)
            self.assertTrue(private.is_file());self.assertFalse((data/'secret.bin').exists())
            self.assertEqual(read_metadata(data,report),message)
            self.assertEqual(remove_reports(output,data),2)
            self.assertFalse(report.exists());self.assertFalse(private.exists());self.assertTrue(output.exists())

    def test_preserve_reports_moves_internal_output_and_rekeys_private_original(self):
        from benson_mail.report_metadata import write_metadata, metadata_path, read_metadata
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary); program=root/'BensonMail-202610211200'; (program/'_internal').mkdir(parents=True)
            data=root/'data'; output=data/'reports'; docs=root/'documents';docs.mkdir()
            report=output/'owner@example.invalid'/'2026-10-21'/'From sender@example.invalid'/'example-11-53.md'
            report.parent.mkdir(parents=True);report.write_text('Original report',encoding='utf-8')
            message={'subject':'Example','sender':'sender@example.invalid','received':'2026-10-21','body':'Original email'}
            private=write_metadata(data,report,message)
            (data/'config.json').write_text(json.dumps({'output_dir':str(output)}),encoding='utf-8')
            with patch('benson_mail.platform_windows.documents_dir',return_value=docs),patch('benson_mail.platform_windows.set_autostart'),patch('benson_mail.platform_windows.remove_uninstall_registration'),patch('benson_mail.uninstall.remove_shortcuts'):
                cleanup_installation(program,data,False,lambda _:None)
            moved=next(docs.rglob('*.md'))
            self.assertEqual(moved.read_text(encoding='utf-8'),'Original report')
            self.assertEqual(read_metadata(data,moved),message)
            self.assertFalse(private.exists());self.assertFalse((data/'config.json').exists());self.assertFalse(program.exists())
            self.assertEqual({p.name for p in data.iterdir()},{'report_metadata'})
            self.assertFalse(list(docs.rglob('*.json')))

    def test_native_preparation_is_non_destructive_while_application_runs(self):
        # Staging now precedes the UI's permission-to-exit prompt. It must not
        # acquire the main app mutex or change installation/configuration bytes.
        from benson_mail.uninstall import native_cli
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary) / 'BensonMail-202610191200'
            (folder / '_internal').mkdir(parents=True)
            name = 'Uninstall-BensonMail-202610191200.exe'
            (folder / name).write_bytes(b'synthetic launcher')
            settings = Path(temporary) / 'BensonMail'
            settings.mkdir()
            config = settings / 'config.json'
            config.write_text('{"account":"synthetic@example.invalid"}')
            captured = io.StringIO()
            with patch('sys.argv', ['worker', '--uninstall-native', 'prepare', '--target', str(folder), '--executable', name]), \
                    patch.dict(os.environ, {'LOCALAPPDATA': temporary}), \
                    patch('sys.stdout', captured), \
                    patch('benson_mail.platform_windows.SingleInstance', side_effect=AssertionError('Preparation must not lock the running app')):
                self.assertEqual(native_cli(), 0)
            rows = [json.loads(line) for line in captured.getvalue().splitlines()]
            helper = Path(next(row['result']['helper'] for row in rows if 'result' in row))
            try:
                self.assertTrue((helper.parent / '.benson-uninstall-helper').is_file())
                self.assertEqual(helper.read_bytes(), b'synthetic launcher')
                self.assertEqual((folder / name).read_bytes(), b'synthetic launcher')
                self.assertEqual(config.read_text(), '{"account":"synthetic@example.invalid"}')
            finally:
                shutil.rmtree(helper.parent)

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
