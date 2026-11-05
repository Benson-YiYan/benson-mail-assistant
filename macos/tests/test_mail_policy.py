"""Mac daemon policy regressions, using cached mail and no network or credentials."""
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

RUNTIME = Path(__file__).resolve().parents[1] / 'Runtime'
sys.path.insert(0, str(RUNTIME))
from mail_policy import policy_status, policy_save, policy_summarize_records, intercept, queued_records, spam_metadata
from runtime_i18n import text as runtime_text
from mailbox_config import mailbox_id

class MacPolicyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.root = Path(self.temp.name)
        with patch.dict('os.environ', {'BENSON_MAIL_HOME': str(self.root)}):
            spec = importlib.util.spec_from_file_location('policy_daemon_fixture', RUNTIME / 'mail_daemon.py')
            self.daemon = importlib.util.module_from_spec(spec); spec.loader.exec_module(self.daemon)
        self.daemon.SETTINGS.write_text(json.dumps({'enabled':True,'ai_provider':'api','ui_language':'en'}))
        self.message={'uid':2,'uidvalidity':'7','mailbox_key':'account-a','from':'GitHub <notifications@github.com>',
            'subject':'build failed','received_at':'2026-10-20T03:00:00+00:00', 'bodies':[{'type':'text/plain','text':'body'}], 'attachments':[]}
        self.state=self.daemon.DATA/'state.json'; self.state.write_text(json.dumps({'pending':[2],'mailbox_key':'account-a'}))
        self.pending=self.daemon.DATA/'pending.json'; self.pending.write_text(json.dumps([self.message]))
        self.acks=[]
    def tearDown(self): self.temp.cleanup()
    def reader(self,*args):
        if args:
            self.assertEqual(args,('ack','2')); self.acks.append(args)
            self.state.write_text(json.dumps({'pending':[],'mailbox_key':'account-a'}))
            return {'acknowledged':['2']}
        return {'pending_messages':len(json.loads(self.state.read_text())['pending']), 'report':str(self.pending)}
    def block(self):
        policy_save(self.root,{'mode':'blacklist','addresses':['notifications@github.com'],'skip_spam':False})
    def test_block_durably_before_ack_and_no_ai(self):
        self.block()
        original=self.reader
        def reader(*args):
            if args: self.assertEqual(policy_status(self.root)['count'],1)
            return original(*args)
        with patch.object(self.daemon,'run_reader',reader),patch.object(self.daemon,'analyze') as analyze:
            self.assertEqual(self.daemon.check_profiles()[0],[])
            self.assertEqual(self.daemon.check_profiles()[0],[])
            analyze.assert_not_called()
        self.assertEqual(len(self.acks),1); self.assertEqual(policy_status(self.root)['count'],1)
    def test_historical_backfill_bypasses_all_sender_and_spam_rules(self):
        self.block()
        historical = dict(self.message, historical=True)
        self.pending.write_text(json.dumps([historical]))
        with patch.object(self.daemon,'run_reader',self.reader), patch.object(self.daemon,'analyze') as analyze:
            self.assertEqual(self.daemon.check_profiles()[0],[])
            analyze.assert_called_once()
        self.assertEqual(policy_status(self.root)['count'],0)

        policy_save(self.root,{'mode':'blacklist','addresses':['notifications@github.com'],'skip_spam':True})
        spam = dict(historical, is_spam=True)
        self.pending.write_text(json.dumps([spam]))
        self.state.write_text(json.dumps({'pending':[2],'mailbox_key':'account-a','historical_pending':[2]}))
        self.acks.clear()
        with patch.object(self.daemon,'run_reader',self.reader), patch.object(self.daemon,'analyze') as analyze:
            self.assertEqual(self.daemon.check_profiles()[0],[])
            analyze.assert_called_once()
        self.assertEqual(policy_status(self.root)['count'],0)
        # analyze is mocked here; production analyze owns the reader ack.
        self.assertEqual(len(self.acks),0)
    def test_historical_worker_applies_policy_when_requested(self):
        self.block()
        historical = dict(self.message, historical=True, apply_mail_policy=True)
        self.pending.write_text(json.dumps([historical]))
        with patch.object(self.daemon,'run_reader',self.reader), patch.object(self.daemon,'analyze') as analyze:
            self.assertEqual(self.daemon.check_profiles()[0],[])
            analyze.assert_not_called()
        self.assertEqual(len(self.acks),1)
        self.assertEqual(policy_status(self.root)['count'],1)
    def test_queue_uses_cached_mail_and_no_ack_for_manual_original(self):
        self.block(); intercept(self.root,self.message,'account-a','7',2)
        record=policy_status(self.root)['records'][0]; policy_summarize_records(self.root,[record['id']])
        self.state.write_text(json.dumps({'pending':[],'mailbox_key':'account-a'}))
        seen=[]
        def analyze(message):
            seen.append(message.copy())
            self.assertEqual(message['_policy_record_id'],record['id'])
            self.assertEqual(message['uidvalidity'],'7')
        with patch.object(self.daemon,'run_reader',self.reader),patch.object(self.daemon,'analyze',analyze):
            self.assertEqual(self.daemon.check_profiles()[0],[])
            self.assertEqual(self.daemon.check_profiles()[0],[])
        self.assertEqual(len(seen),1); self.assertEqual(self.acks,[]); self.assertEqual(policy_status(self.root)['count'],0)
    def test_manual_export_failure_reuses_answer_and_separate_workdir(self):
        self.block(); intercept(self.root,self.message,'account-a','7',2)
        record=policy_status(self.root)['records'][0]; policy_summarize_records(self.root,[record['id']])
        self.state.write_text(json.dumps({'pending':[],'mailbox_key':'account-a'}))
        existing=self.daemon.DATA/'2'; existing.mkdir(); (existing/'answer.txt').write_text('unrelated pending answer')
        with patch.object(self.daemon,'run_reader',self.reader),patch.object(self.daemon,'notify'),patch.object(self.daemon,'log'),\
             patch('ai_runner.analyze_api',return_value='cached actual answer') as ai,\
             patch.object(self.daemon,'export_report',side_effect=[OSError('disk full'),'/tmp/synthetic-report.md']) as export:
            self.assertEqual(len(self.daemon.check_profiles()[0]),1)
            self.assertEqual(policy_status(self.root)['records'][0]['state'],'error')
            self.assertEqual(self.daemon.check_profiles()[0],[])
            self.daemon.check_profiles()
            self.assertEqual(ai.call_count,1); self.assertEqual(export.call_count,2)
        self.assertEqual((existing/'answer.txt').read_text(),'unrelated pending answer')
        self.assertEqual(self.acks,[]); self.assertEqual(policy_status(self.root)['count'],0)
    def test_spam_metadata_and_false_positive_protection(self):
        self.assertTrue(spam_metadata({},'FLAGS ($Junk)')['is_spam'])
        self.assertTrue(spam_metadata({},'FLAGS (\\Junk)')['is_spam'])
        self.assertTrue(spam_metadata({},'X-GM-LABELS (\\Spam)')['is_spam'])
        self.assertFalse(spam_metadata({},'FLAGS ($NotJunk)')['is_spam'])
        self.assertFalse(spam_metadata({'Subject':'spam'})['is_spam'])
        self.assertTrue(spam_metadata({},folder='Junk Email')['is_spam'])
        self.assertTrue(spam_metadata({},folder='Custom Spam',spam_folders=['Custom Spam'])['is_spam'])
        self.assertTrue(spam_metadata({},folder='custom spam',spam_folders=['Custom Spam'])['is_spam'])
        self.assertFalse(spam_metadata({},folder='Custom Spam Archive',spam_folders=['Custom Spam'])['is_spam'])
        self.assertFalse(spam_metadata({},folder='Ordinary',spam_folders=[])['is_spam'])
    def test_spam_folder_list_validation_and_legacy_defaults(self):
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
        saved=policy_save(self.root,{'mode':'blacklist','addresses':[],'skip_spam':True,
                                     'spam_folders':['垃圾箱'],
                                     'spam_folder_options':['Custom Spam',' custom spam ','垃圾箱']})
        self.assertEqual(saved['policy']['spam_folders'],['垃圾箱'])
        self.assertEqual(saved['policy']['spam_folder_options'],['Custom Spam','垃圾箱'])
        self.assertTrue(spam_metadata({},folder='垃圾箱',spam_folders=saved['policy']['spam_folders'])['is_spam'])
        self.assertFalse(spam_metadata({},folder='Custom Spam',spam_folders=saved['policy']['spam_folders'])['is_spam'])
        with self.assertRaises(ValueError):
            policy_save(self.root,{'mode':'blacklist','addresses':[],'skip_spam':True,'spam_folders':['']})
        self.assertEqual(policy_status(self.root)['policy']['spam_folders'],['垃圾箱'])
        self.assertEqual(policy_status(self.root)['policy']['spam_folder_options'],['Custom Spam','垃圾箱'])
        self.assertEqual(runtime_text('垃圾邮件文件夹列表无效。','en'),'The spam folder list is invalid.')
        self.assertEqual(runtime_text('垃圾邮件文件夹列表无效。','es'),'La lista de carpetas de correo no deseado no es válida.')
        options_only=policy_save(self.root,{'mode':'blacklist','addresses':[],'skip_spam':True,
                                            'spam_folder_options':['Custom Spam']})['policy']
        self.assertEqual(options_only['spam_folder_options'],['Custom Spam'])
        self.assertEqual(options_only['spam_folders'],['Custom Spam'])
    def test_all_folder_profiles_keep_independent_progress_ids_and_discover_dynamically(self):
        connection={'account':'demo@example.invalid','host':'imap.example.invalid','port':993,'security':'ssl',
                    'username':'','mail_folder':'INBOX','mail_auth':'password','read_all_mail':True}
        profile={'connection':connection,'enabled':True}
        self.daemon._FOLDER_CACHE.clear()
        client=type('Client',(),{'logout':lambda self:None})()
        with patch.object(self.daemon,'activate_profile'), patch('mail_connection_io.load',return_value=(connection,'SYNTHETIC')), \
             patch.object(self.daemon,'connect',return_value=client), patch.object(self.daemon,'selectable_folders',return_value=['INBOX','Sent']):
            expanded=self.daemon.scan_profiles([profile],{})
        self.assertEqual([item[0]['connection']['mail_folder'] for item in expanded],['INBOX','Sent'])
        self.assertTrue(all(item[0]['connection']['read_all_mail'] for item in expanded))
        ids=[mailbox_id(item[0]['connection']) for item in expanded]
        self.assertEqual(len(set(ids)),2)
        self.assertTrue(all(item[1] is None for item in expanded))
