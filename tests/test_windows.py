import sys
import tempfile
import unittest
from pathlib import Path
from benson_mail import platform_windows as platform

@unittest.skipUnless(sys.platform=='win32','Windows platform adapters')
class WindowsTests(unittest.TestCase):
    def test_dpapi_account_binding(self):
        encrypted=platform.crypt(b'synthetic', 'one@example.invalid')
        self.assertNotIn(b'synthetic',encrypted)
        self.assertEqual(platform.crypt(encrypted,'one@example.invalid',True),b'synthetic')
        with self.assertRaises(OSError): platform.crypt(encrypted,'two@example.invalid',True)
    def test_documents_and_unicode(self):
        self.assertTrue(platform.documents_dir().is_absolute())
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'中文路径'; path.mkdir(); (path/'测试.txt').write_text('内容',encoding='utf-8'); self.assertEqual((path/'测试.txt').read_text(encoding='utf-8'),'内容')
    def test_startup_cleanup(self):
        name='BensonMail-UnitTest'
        try:
            platform.set_autostart(True,name); self.assertTrue(platform.has_autostart(name))
            platform.set_autostart(False,name); self.assertFalse(platform.has_autostart(name))
        finally: platform.set_autostart(False,name)
    def test_single_instance(self):
        first=platform.SingleInstance(); second=platform.SingleInstance()
        try: self.assertTrue(second.already_running)
        finally: second.close(); first.close()
    def test_desktop_shortcut_creation_upgrade_collision_and_uninstall(self):
        import pythoncom
        from win32com.shell import shell
        from benson_mail.uninstall import remove_shortcuts
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            desktop = root / '桌面'
            first = root / '旧版本' / 'BensonMail-202610170900.exe'
            second = root / '新版本' / 'BensonMail-202610171300.exe'
            other = root / 'other.exe'
            for target in (first, second, other):
                target.parent.mkdir(exist_ok=True)
                target.write_bytes(b'synthetic target')
            original = platform.create_desktop_shortcut(other, desktop=desktop)
            created = platform.create_desktop_shortcut(first, desktop=desktop)
            self.assertNotEqual(original, created)
            updated = platform.create_desktop_shortcut(second, previous=first, desktop=desktop)
            self.assertEqual(created, updated)
            pythoncom.CoInitialize()
            try:
                link = pythoncom.CoCreateInstance(shell.CLSID_ShellLink, None, pythoncom.CLSCTX_INPROC_SERVER,
                                                 shell.IID_IShellLink)
                link.QueryInterface(pythoncom.IID_IPersistFile).Load(str(updated))
                self.assertEqual(Path(link.GetPath(shell.SLGP_RAWPATH)[0]).resolve(), second.resolve())
                self.assertEqual(link.GetArguments(), '')
                self.assertEqual(Path(link.GetWorkingDirectory()).resolve(), second.parent.resolve())
            finally:
                pythoncom.CoUninitialize()
            remove_shortcuts(second.parent, [desktop])
            self.assertFalse(created.exists())
            self.assertTrue(original.exists())

class DiscoveryTests(unittest.TestCase):
    def test_reject_gui_and_cmd_without_runtime(self):
        from unittest.mock import patch
        import subprocess
        with patch('subprocess.run',return_value=subprocess.CompletedProcess([],0,b'GUI app',b'')):
            self.assertFalse(platform.verify_codex(['Codex.exe']))
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'codex.cmd'; path.write_text('echo ignored')
            self.assertIsNone(platform.resolve_cli(path))
    def test_dpapi_no_plaintext_fallback(self):
        if sys.platform!='win32':
            with self.assertRaises(RuntimeError): platform.crypt(b'secret','demo')
