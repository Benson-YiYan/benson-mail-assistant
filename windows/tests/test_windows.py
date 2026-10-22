import sys
import json
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

    def test_four_portable_links_migrate_upgrade_and_user_deletion(self):
        import json
        import pythoncom
        from win32com.shell import shell
        from benson_mail.uninstall import remove_shortcuts
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); desktop = root / 'Desktop'; programs = root / 'Programs'
            desktop.mkdir(); programs.mkdir()
            first = root / 'old' / 'BensonMail-202610170900.exe'
            second = root / 'new' / 'BensonMail-202610171300.exe'
            for main in (first, second):
                main.parent.mkdir(); main.write_bytes(b'app')
                (main.parent / main.name.replace('BensonMail-', 'Uninstall-BensonMail-')).write_bytes(b'uninstaller')
            unrelated = root / 'other.exe'; unrelated.write_bytes(b'other')
            collision = platform.create_shortcut(unrelated, '邮件小秘书', desktop)
            legacy = platform.create_desktop_shortcut(first, desktop=desktop)
            marker = root / 'desktop-shortcut.json'
            marker.write_text(json.dumps({'launcher': str(first.resolve())}))
            self.assertTrue(platform.ensure_portable_shortcuts(first, marker, desktop, programs))
            recorded = json.loads(marker.read_text(encoding='utf-8'))
            self.assertEqual(len(recorded['links']), 4)
            self.assertEqual(len(list(desktop.glob('*.lnk'))), 3)
            self.assertEqual(len(list(programs.glob('*.lnk'))), 2)
            Path(recorded['links'][0]).unlink()
            self.assertFalse(platform.ensure_portable_shortcuts(first, marker, desktop, programs))
            self.assertFalse(Path(recorded['links'][0]).exists())
            self.assertTrue(platform.ensure_portable_shortcuts(second, marker, desktop, programs))
            pythoncom.CoInitialize()
            try:
                for index, path in enumerate(json.loads(marker.read_text(encoding='utf-8'))['links']):
                    link = pythoncom.CoCreateInstance(shell.CLSID_ShellLink, None, pythoncom.CLSCTX_INPROC_SERVER, shell.IID_IShellLink)
                    link.QueryInterface(pythoncom.IID_IPersistFile).Load(path)
                    expected = second if index % 2 == 0 else platform.matching_uninstaller(second)
                    self.assertEqual(Path(link.GetPath(shell.SLGP_RAWPATH)[0]).resolve(), expected.resolve())
            finally:
                pythoncom.CoUninitialize()
            corrupt = programs / 'unrelated-broken.lnk'; corrupt.write_bytes(b'not a shortcut')
            legacy_folder = programs / '邮件小秘书'; legacy_folder.mkdir()
            platform.create_shortcut(second, '邮件小秘书', legacy_folder)
            remove_shortcuts(second.parent, [desktop, programs])
            self.assertFalse(legacy_folder.exists())
            self.assertTrue(corrupt.exists() and collision.exists() and desktop.exists() and programs.exists())
            self.assertEqual(list(desktop.glob('*.lnk')), [collision])
            self.assertEqual(list(programs.glob('*.lnk')), [corrupt])

    def test_installed_apps_registration_belongs_to_matching_installation(self):
        import winreg
        name = 'BensonMail-UninstallRegistrationUnitTest'
        path = r'Software\Microsoft\Windows\CurrentVersion\Uninstall' + '\\' + name
        with tempfile.TemporaryDirectory() as temporary:
            old = Path(temporary) / 'old'; new = Path(temporary) / 'new'
            try:
                with winreg.CreateKey(winreg.HKEY_CURRENT_USER, path) as key:
                    winreg.SetValueEx(key, 'InstallLocation', 0, winreg.REG_SZ, str(new))
                platform.remove_uninstall_registration(old, name)
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path):
                    pass
                platform.remove_uninstall_registration(new, name)
                with self.assertRaises(FileNotFoundError):
                    winreg.OpenKey(winreg.HKEY_CURRENT_USER, path)
            finally:
                try: winreg.DeleteKey(winreg.HKEY_CURRENT_USER, path)
                except FileNotFoundError: pass

class DiscoveryTests(unittest.TestCase):
    def test_installer_marker_prevents_all_automatic_shortcuts(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); launcher = root / 'BensonMail-202610171300.exe'
            launcher.write_bytes(b'app'); (root / '.benson-installed.json').write_text('{"installed":true}')
            with patch.object(platform, 'create_shortcut') as create:
                self.assertFalse(platform.ensure_portable_shortcuts(launcher, root / 'marker.json'))
                create.assert_not_called()
            self.assertFalse((root / 'marker.json').exists())

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

class CodexDiscoveryRegressionTests(unittest.TestCase):
    def test_store_install_location_finds_nested_cli_without_enumerating_windowsapps(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)/'OpenAI.Codex'; cli=root/'app/resources/codex.exe'
            cli.parent.mkdir(parents=True); cli.write_bytes(b'CLI')
            with patch.object(platform,'codex_store_locations',return_value=[root]), patch.object(platform.shutil,'which',return_value=None), patch.object(platform,'verify_codex',side_effect=lambda c: c==[str(cli)]):
                self.assertEqual(platform.discover_codex(),[str(cli)])

    def test_npm_user_directory_is_searched_without_path(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary); shim=root/'npm/codex.cmd'; shim.parent.mkdir(); shim.write_text('npm')
            cli=root/'npm/node_modules/@openai/codex-win32-x64/vendor/x86_64-pc-windows-msvc/codex/codex.exe'
            cli.parent.mkdir(parents=True); cli.write_bytes(b'CLI')
            with patch.dict(platform.os.environ,{'APPDATA':str(root)}), patch.object(platform.shutil,'which',return_value=None), patch.object(platform,'codex_store_locations',return_value=[]), patch.object(platform,'verify_codex',side_effect=lambda c: c==[str(cli)]):
                self.assertEqual(platform.discover_codex(),[str(cli)])

    def test_gui_selection_resolves_cli_and_gui_never_executes(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary); gui=root/'Codex.exe'; gui.write_bytes(b'GUI')
            resources=root/'resources'; resources.mkdir(); (resources/'app.asar').write_bytes(b'GUI')
            cli=resources/'codex.exe'; cli.write_bytes(b'CLI')
            self.assertEqual(platform.resolve_cli(gui),[str(cli)])
            self.assertEqual(platform.resolve_cli(root),[str(cli)])
            with patch.object(platform.subprocess,'run') as run:
                self.assertFalse(platform.verify_codex([str(gui)])); run.assert_not_called()

    def test_store_registry_output_is_parsed_without_launching_codex(self):
        from unittest.mock import patch
        import subprocess
        output=json.dumps(['C:/Program Files/WindowsApps/OpenAI.Codex'])
        with patch.object(platform.sys,'platform','win32'), patch.object(platform.subprocess,'run',return_value=subprocess.CompletedProcess([],0,output,'')) as run:
            self.assertEqual(platform.codex_store_locations(),[Path('C:/Program Files/WindowsApps/OpenAI.Codex')])
            self.assertEqual(run.call_args.args[0][0],'powershell.exe')
            self.assertIn('Get-AppxPackage',run.call_args.args[0][-1])

    def test_node_fallback_selection_keeps_npm_shim_for_save(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary); shim=root/'codex.cmd'; shim.write_text('npm')
            script=root/'node_modules/@openai/codex/bin/codex.js'; script.parent.mkdir(parents=True); script.write_text('js')
            self.assertEqual(platform.codex_selection_path(['node.exe',str(script)]),str(shim))

    def test_registered_custom_install_on_arbitrary_directory(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as temporary:
            custom=Path(temporary)/'another-drive/custom/AI tools'; cli=custom/'resources/codex.exe'
            cli.parent.mkdir(parents=True); cli.write_bytes(b'CLI')
            with patch.object(platform,'codex_registered_locations',return_value=[custom]), patch.object(platform,'codex_store_locations',return_value=[]), patch.object(platform.shutil,'which',return_value=None), patch.object(platform,'verify_codex',side_effect=lambda c: c==[str(cli)]):
                self.assertEqual(platform.discover_codex(),[str(cli)])
            self.assertEqual(platform.resolve_cli(custom),[str(cli)])

    def test_uninstall_registry_reads_custom_location_and_icon_from_both_views(self):
        from unittest.mock import patch, MagicMock
        registry=MagicMock()
        registry.HKEY_CURRENT_USER='user'; registry.HKEY_LOCAL_MACHINE='machine'
        registry.KEY_READ=1; registry.KEY_WOW64_64KEY=2; registry.KEY_WOW64_32KEY=4
        parent=MagicMock(); key=MagicMock()
        def opened(hive,path,*args):
            handle=parent if path.endswith('Uninstall') else key
            context=MagicMock(); context.__enter__.return_value=handle
            return context
        registry.OpenKey.side_effect=opened
        registry.QueryInfoKey.return_value=(1,0,0); registry.EnumKey.return_value='CustomCodex'
        values={'DisplayName':'OpenAI Codex','InstallLocation':'Z:/Other Apps/Codex','DisplayIcon':'"Z:/Other Apps/Codex/Codex.exe",0'}
        registry.QueryValueEx.side_effect=lambda handle,name:(values[name],1)
        with patch.object(platform.sys,'platform','win32'), patch.dict(sys.modules,{'winreg':registry}):
            self.assertEqual(platform.codex_registered_locations(),[Path('Z:/Other Apps/Codex')])
        for hive in ('user','machine'):
            for view in (3,5):
                registry.OpenKey.assert_any_call(hive,r'Software\Microsoft\Windows\CurrentVersion\Uninstall',0,view)
