"""A rejected or failed settings-page save cannot partially install draft values."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
from benson_mail.bridge import Controller
from benson_mail import settings_page
from benson_mail.ai_api import identity

class SettingsPageTests(unittest.TestCase):
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory();self.addCleanup(self.temporary.cleanup)
        self.root=Path(self.temporary.name)
        self.controller=Controller(self.root,lambda event:None,launcher='C:/Mail/App.exe')
        self.controller.config={'account':'old@example.invalid','host':'imap.example.invalid','ai_provider':'api','api_base':'https://example.invalid/v1','api_model':'old-model','autostart':False,'interval':60,'notifications_enabled':True}
        self.controller.persist()
        self.before=self.controller.path.read_bytes()
    def mail(self,**extra):
        return {'account':'new@example.invalid','host':'imap.new.invalid','secret':'NEW_SECRET','output_dir':str(self.root/'new-reports'),'autostart':True,**extra}
    def test_invalid_interval_after_valid_mail_fields_changes_nothing(self):
        with patch('benson_mail.settings_page.platform.save_secret') as secret,patch('benson_mail.settings_page.platform.set_autostart') as registry:
            with self.assertRaises(ValueError): self.controller.command('save_settings_page',{'page':'mail','values':self.mail(seconds='bad')})
        secret.assert_not_called();registry.assert_not_called()
        self.assertEqual(self.controller.path.read_bytes(),self.before)
        self.assertFalse((self.root/'new-reports').exists());self.assertFalse((self.root/'mail-secrets').exists())
    def test_invalid_policy_after_mail_and_interval_does_not_commit_anything(self):
        with patch('benson_mail.settings_page.platform.save_secret') as secret,patch('benson_mail.settings_page.platform.set_autostart') as registry:
            with self.assertRaises(ValueError): self.controller.command('save_settings_page',{'page':'mail','values':self.mail(seconds=180,mail_policy={'mode':'bad'})})
        secret.assert_not_called();registry.assert_not_called();self.assertEqual(self.controller.path.read_bytes(),self.before)
    def test_readonly_validation_does_not_return_credentials_or_create_folders(self):
        with patch('benson_mail.settings_page.platform.save_secret') as secret,patch('benson_mail.settings_page.platform.set_autostart') as registry:
            result=self.controller.command('validate_settings_page',{'page':'mail','values':self.mail(seconds=180)})
        self.assertEqual(result,{'valid':True,'page':'mail'})
        self.assertNotIn('NEW_SECRET',json.dumps(result));secret.assert_not_called();registry.assert_not_called()
        self.assertEqual(self.controller.path.read_bytes(),self.before);self.assertFalse((self.root/'new-reports').exists())
    def test_complete_mail_page_commits_interval_policy_and_connection(self):
        def save_secret(path,binding,secret): path.write_bytes(b'encrypted-'+secret.encode())
        with patch('benson_mail.settings_page.platform.save_secret',side_effect=save_secret),patch('benson_mail.settings_page.platform.set_autostart') as registry:
            result=self.controller.command('save_settings_page',{'page':'mail','values':self.mail(seconds=180,mail_policy={'mode':'blacklist','addresses':['skip@example.invalid'],'skip_spam':True})})
        self.assertTrue(result['saved']);value=json.loads(self.controller.path.read_text())
        self.assertEqual(value['interval'],180);self.assertEqual(value['account'],'new@example.invalid')
        self.assertEqual(value['mail_policy']['addresses'],['skip@example.invalid'])
        self.assertEqual(json.loads((self.root/'blocked_mail'/'state.json').read_text())['policy'],value['mail_policy'])
        self.assertTrue((self.root/value['mail_secret_file']).is_file());registry.assert_called_once()
        self.assertNotIn('NEW_SECRET',self.controller.path.read_text())
    def test_invalid_ai_rates_cannot_save_new_key_or_model(self):
        data={'ai_provider':'api','api_base':'https://new.invalid/v1','api_model':'new-model','key':'NEW_KEY','rates':{'input_per_million':-1}}
        with patch('benson_mail.settings_page.platform.save_secret') as secret:
            with self.assertRaises(ValueError):self.controller.command('save_settings_page',{'page':'ai','values':data})
        secret.assert_not_called();self.assertEqual(self.controller.path.read_bytes(),self.before)
        self.assertFalse((self.root/'usage-rates.json').exists());self.assertFalse((self.root/'api-keys').exists())
    def test_ai_config_and_new_model_rates_commit_together(self):
        data={'ai_provider':'api','api_base':'https://new.invalid/v1','api_model':'new-model','key':'NEW_KEY','rates':{'input_per_million':2,'output_per_million':4,'currency':'CNY'}}
        with patch('benson_mail.settings_page.platform.save_secret',side_effect=lambda path,binding,key:path.write_bytes(b'encrypted')):
            self.controller.command('save_settings_page',{'page':'ai','values':data})
        from benson_mail.assistant_tools import _rates
        self.assertEqual(_rates(self.root)['model'],'new-model');self.assertEqual(_rates(self.root)['input_per_million'],2)
        self.assertEqual(json.loads(self.controller.path.read_text())['api_model'],'new-model')
    def test_persist_failure_restores_overwritten_secret_config_and_rates(self):
        path=self.controller.key_path('https://example.invalid/v1');path.parent.mkdir();path.write_bytes(b'OLD_ENCRYPTED_KEY')
        rates=self.root/'usage-rates.json';rates.write_text('{"rates":{}}');rates_before=rates.read_bytes()
        original_config=copy.deepcopy(self.controller.config)
        data={'ai_provider':'api','api_base':'https://example.invalid/v1','api_model':'new-model','key':'NEW_KEY','rates':{'input_per_million':2}}
        with patch('benson_mail.settings_page.platform.save_secret',side_effect=lambda path,binding,key:path.write_bytes(b'NEW_ENCRYPTED_KEY')),patch.object(self.controller,'persist',side_effect=OSError('disk full')):
            with self.assertRaises(OSError):self.controller.command('save_settings_page',{'page':'ai','values':data})
        self.assertEqual(path.read_bytes(),b'OLD_ENCRYPTED_KEY');self.assertEqual(rates.read_bytes(),rates_before)
        self.assertEqual(self.controller.path.read_bytes(),self.before);self.assertEqual(self.controller.config,original_config)
    def test_invalid_quiet_hours_do_not_save_other_general_controls(self):
        data={'notifications_enabled':False,'autostart':True,'quiet_hours':{'enabled':True,'start':'99:99','end':'08:00'}}
        with patch('benson_mail.settings_page.platform.set_autostart') as registry:
            with self.assertRaises(ValueError):self.controller.command('save_settings_page',{'page':'general','values':data})
        registry.assert_not_called();self.assertEqual(self.controller.path.read_bytes(),self.before)
    def profiles(self):
        from benson_mail.mailbox_config import normalize,mailbox_id
        profiles=[{**normalize({'account':account,'host':'imap.example.invalid'}),'monitor_enabled':True} for account in ('old@example.invalid','second@example.invalid')]
        self.controller.config['mailboxes']=profiles
        self.controller.config.update(profiles[0]);self.controller.persist()
        return profiles,[mailbox_id(profile) for profile in profiles]
    def test_multimail_add_remove_disable_policy_and_interval_commit_once(self):
        profiles,ids=self.profiles()
        drafts=[{'id':ids[0],'monitor_enabled':False},{'client_id':'NEW','account':'new@example.invalid','host':'imap.new.invalid','secret':'NEW_SECRET','monitor_enabled':True}]
        data={'mailboxes':drafts,'selected_mailbox_id':'NEW','seconds':180,'mail_policy':{'mode':'blacklist','addresses':['skip@example.invalid']}}
        with patch('benson_mail.settings_page.platform.save_secret',side_effect=lambda path,binding,secret:path.write_bytes(b'encrypted')),patch.object(self.controller,'persist',wraps=self.controller.persist) as persisted:
            result=self.controller.command('save_settings_page',{'page':'mail','values':data})
        self.assertEqual(persisted.call_count,1)
        value=json.loads(self.controller.path.read_text())
        self.assertEqual([profile['account'] for profile in value['mailboxes']],['old@example.invalid','new@example.invalid'])
        self.assertFalse(value['mailboxes'][0]['monitor_enabled']);self.assertEqual(value['interval'],180)
        self.assertEqual(value['account'],'new@example.invalid');self.assertEqual(value['mail_policy']['addresses'],['skip@example.invalid'])
        from benson_mail.mailbox_config import mailbox_id
        self.assertEqual(result['selected_mailbox_id'],mailbox_id(value))
        self.assertNotIn(ids[1],json.dumps(value))
    def test_ai_codex_path_is_validated_before_prices_and_saved_with_page(self):
        data={'ai_provider':'codex','codex_path':'C:/Codex/codex.exe','rates':{'input_per_million':0}}
        with patch('benson_mail.settings_page.platform.resolve_cli',return_value=['C:/Codex/codex.exe']) as resolve,patch('benson_mail.settings_page.platform.verify_codex',return_value=True):
            self.controller.command('save_settings_page',{'page':'ai','values':data})
        self.assertEqual(self.controller.config['codex_command'],['C:/Codex/codex.exe']);resolve.assert_called_once()
    def test_invalid_later_mailbox_does_not_save_first_new_secret_or_removals(self):
        _,ids=self.profiles();before=self.controller.path.read_bytes()
        data={'mailboxes':[{'client_id':'NEW','account':'new@example.invalid','host':'imap.new.invalid','secret':'NEW_SECRET'}, {'client_id':'BAD','account':'broken','host':'imap.invalid'}],'seconds':180}
        with patch('benson_mail.settings_page.platform.save_secret') as secret:
            with self.assertRaises(ValueError):self.controller.command('save_settings_page',{'page':'mail','values':data})
        secret.assert_not_called();self.assertEqual(self.controller.path.read_bytes(),before)
        self.assertEqual(len(self.controller.config['mailboxes']),2)
    def test_multimail_remove_all_clears_selected_connection_without_deleting_reports(self):
        self.profiles();reports=self.root/'reports';reports.mkdir();(reports/'saved.md').write_text('old report')
        self.controller.command('save_settings_page',{'page':'mail','values':{'mailboxes':[],'seconds':120}})
        self.assertEqual(self.controller.config['mailboxes'],[]);self.assertNotIn('account',self.controller.config)
        self.assertEqual((reports/'saved.md').read_text(),'old report')
    def test_general_output_directory_and_notifications_commit_as_one_page(self):
        directory=self.root/'new-general-output'
        self.controller.command('save_settings_page',{'page':'general','values':{'output_dir':str(directory),'notifications_enabled':False,'quiet_hours':{'enabled':False}}})
        self.assertEqual(self.controller.config['output_dir'],str(directory));self.assertTrue(directory.is_dir())
        self.assertFalse(self.controller.config['notifications_enabled'])
    def test_invalid_general_notifications_cannot_create_draft_output_directory(self):
        directory=self.root/'never-created-output';before=self.controller.path.read_bytes()
        with self.assertRaises(ValueError):self.controller.command('save_settings_page',{'page':'general','values':{'output_dir':str(directory),'quiet_hours':{'enabled':True,'start':'99:99'}}})
        self.assertFalse(directory.exists());self.assertEqual(self.controller.path.read_bytes(),before)
    def test_duplicate_mailbox_drafts_rejected_even_if_original_entry_edited_twice(self):
        _,ids=self.profiles();before=self.controller.path.read_bytes()
        data={'mailboxes':[{'id':ids[0],'monitor_enabled':False},{'id':ids[0],'account':'new@example.invalid','secret':'NEW_SECRET'}]}
        with self.assertRaises(ValueError):self.controller.command('save_settings_page',{'page':'mail','values':data})
        self.assertEqual(self.controller.path.read_bytes(),before)
    def test_general_settings_apply_to_live_service_only_after_commit(self):
        service=Mock();service.config={'notifications_enabled':True};service.analyzer.config={}
        self.controller.service=service
        data={'notifications_enabled':False,'quiet_hours':{'enabled':True,'start':'22:00','end':'08:00'}}
        self.controller.command('save_settings_page',{'page':'general','values':data})
        self.assertFalse(service.config['notifications_enabled'])
        self.assertFalse(json.loads(self.controller.path.read_text())['notifications_enabled'])
        service.stop.assert_not_called();service.start.assert_not_called()
