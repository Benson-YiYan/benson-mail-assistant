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
