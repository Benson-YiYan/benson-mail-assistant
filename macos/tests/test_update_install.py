import hashlib
import json
from pathlib import Path
import plistlib
import sys
import struct
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'Runtime'))
import update_install as updater

class InstallationTests(unittest.TestCase):
    def fixture(self, root):
        target=root/'Mail.app'; stage=root/'.BensonMail-update-test.app'; backup=root/'.backup.app'
        for app,text in [(target,'old'),(stage,'new')]:
            app.mkdir(); (app/'identity').write_text(text)
        config=root/'config.json'; config.write_text('keep-secret-configuration')
        return dict(target=str(target),stage=str(stage),backup=str(backup),version='202610181200',arch='arm64'),config

    def test_success_replaces_and_removes_backup(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);plan,config=self.fixture(root); launched=[]
            updater.swap(plan,launched.append,lambda app:True,validate_app=lambda *args:None)
            self.assertEqual((Path(plan['target'])/'identity').read_text(),'new')
            self.assertFalse(Path(plan['backup']).exists());self.assertFalse(Path(plan['stage']).exists())
            self.assertEqual(config.read_text(),'keep-secret-configuration')

    def test_failed_start_rolls_back(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);plan,config=self.fixture(root); launched=[]
            with self.assertRaisesRegex(RuntimeError,'confirm startup'):
                updater.swap(plan,launched.append,lambda app:False,validate_app=lambda *args:None)
            self.assertEqual((Path(plan['target'])/'identity').read_text(),'old')
            self.assertEqual(len(launched),2);self.assertEqual(config.read_text(),'keep-secret-configuration')

    def test_failed_stage_rename_rolls_back(self):
        with tempfile.TemporaryDirectory() as directory:
            plan,config=self.fixture(Path(directory)); real_move=updater.os.rename
            def move(source,target):
                if Path(source)==Path(plan['stage']):raise OSError('fixture move failure')
                real_move(source,target)
            with self.assertRaises(OSError):updater.swap(plan,lambda app:None,lambda app:True,validate_app=lambda *args:None,move=move)
            self.assertEqual((Path(plan['target'])/'identity').read_text(),'old')

    def test_image_hash_mismatch_blocks_mount(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);plan,_=self.fixture(root);workspace=root/'workspace';workspace.mkdir()
            image=workspace/'update.dmg';image.write_bytes(b'fixture')
            request=dict(workspace=str(workspace),target=plan['target'],version=plan['version'],arch='arm64',dmg=str(image),sha256='0'*64)
            with patch.object(updater,'command',side_effect=AssertionError('must not mount')):
                with self.assertRaisesRegex(RuntimeError,'SHA256 mismatch'):updater.prepare(request)
            request['sha256']=hashlib.sha256(b'fixture').hexdigest();request['size']=100
            with self.assertRaisesRegex(RuntimeError,'size mismatch'):updater.prepare(request)

    def test_validate_identity_version_arch_and_signature(self):
        with tempfile.TemporaryDirectory() as directory:
            app=Path(directory)/'app';(app/'Contents').mkdir(parents=True)
            info=dict(CFBundleIdentifier=updater.BUNDLE_ID,CFBundleVersion='202610181200',CFBundleExecutable='BensonMailMac')
            (app/'Contents/Info.plist').write_bytes(plistlib.dumps(info))
            (app/'Contents/MacOS').mkdir()
            (app/'Contents/MacOS/BensonMailMac').write_bytes(b'\xcf\xfa\xed\xfe'+struct.pack('<I',0x100000c))
            with patch.object(updater,'command',return_value='') as call:
                updater.validate(app,info['CFBundleVersion'],'arm64')
                self.assertEqual(call.call_args_list[-1].args[0][:4],['/usr/bin/codesign','--verify','--deep','--strict'])
            with self.assertRaisesRegex(RuntimeError,'version mismatch'):updater.validate(app,'202610181201','arm64')
            with patch.object(updater,'architectures',return_value=['x86_64']):
                with self.assertRaisesRegex(RuntimeError,'architecture'):updater.validate(app,info['CFBundleVersion'],'arm64')

    def test_failed_detach_removes_prepared_files_and_preserves_original(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);plan,config=self.fixture(root)
            workspace=root/'workspace';workspace.mkdir()
            image=workspace/'update.dmg';image.write_bytes(b'fixture')
            runtime=root/'original-worker';runtime.mkdir();(runtime/'worker').write_text('fixture runtime')
            def command(args):
                if 'attach' in args:
                    payload=workspace/'mount/Payload.app';payload.mkdir()
                    (payload/'identity').write_text('new app')
                    return ''
                if 'detach' in args: raise RuntimeError('fixture image busy')
                raise AssertionError(args)
            request=dict(workspace=str(workspace),target=plan['target'],version=plan['version'],arch='arm64',
                dmg=str(image),sha256=hashlib.sha256(b'fixture').hexdigest(),parent_pid=123,marker=str(root/'marker'))
            with patch.object(updater,'command',side_effect=command) as calls,patch.object(updater,'validate'),patch.object(updater.sys,'executable',str(runtime/'worker')):
                with self.assertRaisesRegex(RuntimeError,'two attempts.*staging removed'):
                    updater.prepare(request)
            self.assertEqual(sum('detach' in call.args[0] for call in calls.call_args_list),2)
            self.assertFalse((workspace/'helper-runtime').exists())
            self.assertFalse((workspace/'install-plan.json').exists())
            self.assertEqual(list(root.glob('.BensonMail-update-*.app')),[Path(plan['stage'])])
            self.assertEqual((Path(plan['target'])/'identity').read_text(),'old')
            self.assertEqual(config.read_text(),'keep-secret-configuration')

    def test_parent_timeout_never_changes_original(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);plan,config=self.fixture(root);plan.update(workspace=str(root),parent_pid=123)
            with patch.object(updater,'alive',return_value=True),patch.object(updater.time,'monotonic',side_effect=[0,121]),patch.object(updater,'swap',side_effect=AssertionError('must not swap')):
                self.assertEqual(updater.install(plan),1)
            self.assertEqual((Path(plan['target'])/'identity').read_text(),'old')
            self.assertEqual(config.read_text(),'keep-secret-configuration')

if __name__=='__main__':unittest.main()
