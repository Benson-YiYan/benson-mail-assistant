import json
from pathlib import Path
import tempfile
import unittest
from email.message import EmailMessage
from datetime import datetime, timezone
from benson_mail.mail_policy import (policy_status, policy_save, policy_remove_records,
    policy_summarize_records, intercept, queued_records, spam_metadata, block_reason)
from benson_mail.runtime_i18n import text as runtime_text
from benson_mail.core import Service

class Box:
    def __init__(self): self.messages = {1: self.mail()}
    @staticmethod
    def mail(sender='GitHub <NOTIFICATIONS@GITHUB.COM>', spam=False):
        message = EmailMessage(); message['From'] = sender; message['Subject'] = 'A build failed'
        if spam: message['X-Spam-Flag'] = 'YES'
        message.set_content('body')
        return message.as_bytes(), datetime.now(timezone.utc)
    def snapshot(self): return '1', sorted(self.messages)
    def fetch(self, uid): return self.messages[uid]

class PolicyTests(unittest.TestCase):
    def setUp(self): self.temp=tempfile.TemporaryDirectory(); self.root=Path(self.temp.name)
    def tearDown(self): self.temp.cleanup()
    def config(self, **extra): return {'mode':'blacklist','addresses':['notifications@github.com'],'skip_spam':False,**extra}
    def test_validation_and_exact_match(self):
        saved=policy_save(self.root,self.config(addresses=['GitHub <NOTIFICATIONS@github.com>','notifications@github.com']))
        self.assertEqual(saved['policy']['addresses'],['notifications@github.com'])
        self.assertEqual(block_reason(saved['policy'],{'from':'notifications@github.com'}),'blacklist')
        self.assertIsNone(block_reason(saved['policy'],{'from':'other@github.com'}))
        with self.assertRaises(ValueError): policy_save(self.root,self.config(addresses=['not address']))
        self.assertEqual(policy_status(self.root)['policy'],saved['policy'])
    def test_service_skips_without_ai_and_manual_override_survives_restart(self):
        box=Box(); calls=[]
        config={'account':'a@example.com','output_dir':str(self.root/'reports')}
        def service(): return Service(config,'unused',self.root/'state',lambda event:None,mailbox=box,
            analyzer=lambda message,stop: calls.append(message) or 'report')
        policy_save(self.root,self.config())
        service().check_once(); box.messages[2]=box.mail(); service().check_once()
        self.assertEqual(calls,[])
        status=policy_status(self.root); self.assertEqual(status['count'],1)
        record=status['records'][0]; self.assertNotIn('message',record)
        service().check_once(); self.assertEqual(policy_status(self.root)['count'],1)
        policy_summarize_records(self.root,[record['id']]); service().check_once()
        self.assertEqual(len(calls),1); self.assertEqual(policy_status(self.root)['count'],0)
        service().check_once(); self.assertEqual(len(calls),1)
        self.assertEqual(policy_status(self.root)['policy']['addresses'],['notifications@github.com'])
        self.assertEqual(len(list((self.root/'reports').rglob('*.md'))),1)
    def test_delete_local_record_does_not_touch_cached_or_server(self):
        policy_save(self.root,self.config())
        self.assertTrue(intercept(self.root,{'sender':'notifications@github.com','subject':'test'},'account','v1',2))
        record=policy_status(self.root)['records'][0]
        folder=self.root/'blocked_mail'/record['id']; (folder/'retained.txt').write_text('original')
        policy_remove_records(self.root,[record['id']]); self.assertTrue((folder/'retained.txt').exists())
        self.assertEqual(policy_status(self.root)['count'],0)
    def test_uid_identity_and_whitelist(self):
        policy_save(self.root,self.config(mode='whitelist',addresses=[]))
        for mailbox,validity in [('a','1'),('a','2'),('b','1')]:
            intercept(self.root,{'sender':'x@example.com'},mailbox,validity,2)
        self.assertEqual(policy_status(self.root)['count'],3)
        self.assertTrue(all(r['reason']=='not_whitelisted' for r in policy_status(self.root)['records']))
    def test_historical_backfill_bypasses_sender_and_spam_rules(self):
        policy_save(self.root,self.config(skip_spam=True))
        ordinary={'sender':'notifications@github.com','subject':'selected historical mail'}
        self.assertFalse(intercept(self.root,ordinary,'account','v1',1,bypass_sender_rules=True))
        spam={**ordinary,'is_spam':True}
        self.assertFalse(intercept(self.root,spam,'account','v1',2,bypass_sender_rules=True))
        self.assertEqual(policy_status(self.root)['count'],0)
    def test_spam_uses_explicit_metadata_only(self):
        message=EmailMessage(); message['Subject']='SPAM junk buy now'
        self.assertFalse(spam_metadata(message)['is_spam'])
        message['X-Spam-Flag']='YES'; self.assertTrue(spam_metadata(message)['is_spam'])
        self.assertTrue(spam_metadata({},flags='FLAGS (\\Seen $Junk)')['is_spam'])
        self.assertTrue(spam_metadata({},folder='[Gmail]/Spam')['is_spam'])
        self.assertFalse(spam_metadata({},flags='FLAGS (\\Seen $NotJunk)')['is_spam'])
        policy=policy_save(self.root,self.config(addresses=[],skip_spam=True))['policy']
        self.assertEqual(block_reason(policy,{'is_spam':True}),'spam')
    def test_custom_spam_folder_names_are_exact_and_case_insensitive(self):
        self.assertTrue(spam_metadata({},folder='Custom Spam',spam_folders=['Custom Spam'])['is_spam'])
        self.assertTrue(spam_metadata({},folder='custom spam',spam_folders=['Custom Spam'])['is_spam'])
        self.assertFalse(spam_metadata({},folder='Custom Spam Archive',spam_folders=['Custom Spam'])['is_spam'])
        self.assertFalse(spam_metadata({},folder='Ordinary',spam_folders=[])['is_spam'])
    def test_spam_folder_list_validation_legacy_defaults_and_restore_value(self):
        defaults=['Spam','Junk','Junk Email','Junk E-mail','[Gmail]/Spam','垃圾邮件','垃圾箱']
        legacy=self.root/'blocked_mail'; legacy.mkdir()
        (legacy/'state.json').write_text(json.dumps({'policy': {'mode':'blacklist','addresses':[],'skip_spam':True},
                                                     'records':{}}))
        legacy_policy=policy_status(self.root)['policy']
        self.assertEqual(legacy_policy['spam_folders'],defaults)
        self.assertEqual(legacy_policy['spam_folder_options'],defaults)
        self.assertTrue(legacy_policy['skip_spam'])
        (legacy/'state.json').write_text(json.dumps({'policy': {'mode':'blacklist','addresses':[],
            'skip_spam':True,'spam_folders':['Legacy Custom']},'records':{}}))
        migrated=policy_status(self.root)['policy']
        self.assertEqual(migrated['spam_folders'],['Legacy Custom'])
        self.assertEqual(migrated['spam_folder_options'],['Legacy Custom'])
        saved=policy_save(self.root,self.config(skip_spam=True,spam_folders=['垃圾箱'],
            spam_folder_options=['Custom Spam',' custom spam ','垃圾箱']))
        self.assertEqual(saved['policy']['spam_folders'],['垃圾箱'])
        self.assertEqual(saved['policy']['spam_folder_options'],['Custom Spam','垃圾箱'])
        self.assertTrue(spam_metadata({},folder='垃圾箱',spam_folders=saved['policy']['spam_folders'])['is_spam'])
        self.assertFalse(spam_metadata({},folder='Custom Spam',spam_folders=saved['policy']['spam_folders'])['is_spam'])
        with self.assertRaises(ValueError):
            policy_save(self.root,self.config(spam_folders=['']))
        self.assertEqual(policy_status(self.root)['policy']['spam_folders'],['垃圾箱'])
        self.assertEqual(policy_status(self.root)['policy']['spam_folder_options'],['Custom Spam','垃圾箱'])
        restored=policy_save(self.root,self.config(spam_folders=defaults,spam_folder_options=defaults))
        self.assertEqual(restored['policy']['spam_folders'],defaults)
        self.assertEqual(restored['policy']['spam_folder_options'],defaults)
        self.assertEqual(runtime_text('垃圾邮件文件夹列表无效。','en'),'The spam folder list is invalid.')
        self.assertEqual(runtime_text('垃圾邮件文件夹列表无效。','es'),'La lista de carpetas de correo no deseado no es válida.')
        options_only=policy_save(self.root,self.config(skip_spam=True,spam_folder_options=['Custom Spam']))['policy']
        self.assertEqual(options_only['spam_folder_options'],['Custom Spam'])
        self.assertEqual(options_only['spam_folders'],['Custom Spam'])
    def test_manual_failed_export_uses_cached_ai(self):
        from unittest.mock import patch
        box=Box(); calls=[]
        config={'account':'a@example.com','output_dir':str(self.root/'reports')}
        def service(): return Service(config,'unused',self.root/'state',lambda event:None,mailbox=box,
            analyzer=lambda message,stop: calls.append(message) or 'report')
        policy_save(self.root,self.config()); service().check_once(); box.messages[2]=box.mail(); service().check_once()
        record=policy_status(self.root)['records'][0]; policy_summarize_records(self.root,[record['id']])
        with patch('benson_mail.core.export_report',side_effect=OSError('disk full')):
            with self.assertRaises(OSError): service().check_once()
        service().check_once(); self.assertEqual(len(calls),1)
    def test_attachments_copied_before_original_ack(self):
        policy_save(self.root,self.config()); source=self.root/'original.txt'; source.write_text('attachment')
        intercept(self.root,{'from':'notifications@github.com','attachments':[{'path':str(source)}]},'a','1',3)
        record=policy_status(self.root)['records'][0]; policy_summarize_records(self.root,[record['id']])
        source.unlink(); queued=queued_records(self.root,'a')[0]
        self.assertEqual(Path(queued['message']['attachments'][0]['path']).read_text(),'attachment')
