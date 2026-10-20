"""Tools preserve mailbox state and never export credentials or guess unknown usage."""
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch
import zipfile

WINDOWS = Path(__file__).resolve().parents[1].name == 'windows'
if WINDOWS:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from benson_mail import assistant_tools as tools, mail_chat as chat, attachment_reader as reader
else:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'Runtime'))
    import assistant_tools as tools
    import mail_chat as chat
    import attachment_reader as reader

class AssistantToolTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.output = self.root / 'reports'; self.output.mkdir()
        self.report = self.output / 'mail.md'; self.report.write_text('Original saved report')
        self.config = {'output_dir': str(self.output), 'ui_language': 'en', 'ai_provider': 'api', 'account':'owner@example.invalid', 'host':'imap.example.invalid'}
        self.config_path = self.root / ('config.json' if WINDOWS else 'settings.json')
        self.save_config()
        self.mail = {'uid':'8','uidvalidity':'12','mailbox_key':'fixture', 'subject':'Question', 'sender':'Sender <sender@example.invalid>', 'body':'Original body fact.', 'attachments':[{'name':'document.pdf','text':'[page:1]\nFirst page fact.\n[page:2]\nSecond page fact.'}]}
        self.report.with_suffix('.mail.json').write_text(json.dumps(self.mail))
    def save_config(self): self.config_path.write_text(json.dumps(self.config))
    def tearDown(self): self.temporary.cleanup()
    def test_usage_unknown_is_not_zero_and_configured_prices_apply_prospectively(self):
        tools.record_usage('api', 'sample', {'prompt_tokens':100,'completion_tokens':50}, root=self.root)
        before = tools.usage_summary(self.root)
        self.assertIsNone(before['estimated_cost'])
        tools.usage_rates(self.root, {'input_per_million':2,'output_per_million':6,'currency':'USD'})
        tools.record_usage('api', 'sample', {'prompt_tokens':1000000,'completion_tokens':500000}, root=self.root)
        tools.record_usage('codex', '', root=self.root)
        after = tools.usage_summary(self.root)
        self.assertEqual(after['calls'],3); self.assertEqual(after['unknown_usage_calls'],1)
        self.assertEqual(after['estimated_cost'],5)
        self.assertEqual(len(after['groups']),2)
        self.assertIsNone(after['records'][0]['input_tokens'])
        self.assertEqual(json.loads(self.config_path.read_text()),self.config)
    def test_rates_bind_to_configured_provider_base_and_model(self):
        self.config.update(api_model='model-A',api_base='https://api-A.invalid/v1');self.save_config()
        tools.usage_rates(self.root,{'input_per_million':2,'output_per_million':6,'currency':'USD'})
        tools.record_usage('api','model-A',{'prompt_tokens':1000000,'completion_tokens':0},root=self.root,base='https://api-A.invalid/v1')
        tools.record_usage('api','model-B',{'prompt_tokens':1000000,'completion_tokens':0},root=self.root,base='https://api-A.invalid/v1')
        tools.record_usage('api','model-A',{'prompt_tokens':1000000,'completion_tokens':0},root=self.root,base='https://api-B.invalid/v1')
        result=tools.usage_summary(self.root)
        self.assertEqual(result['estimated_cost'],2)
        self.assertIsNone(result['records'][0]['cost']);self.assertIsNone(result['records'][1]['cost'])
    def test_api_records_actual_tokens_without_request_or_response_content(self):
        if WINDOWS:
            from benson_mail import ai_api
        else:
            import ai_api
        response=Mock();response.read.return_value=json.dumps({'choices':[{'message':{'content':'PRIVATE_RESPONSE'}}], 'usage':{'prompt_tokens':12,'completion_tokens':4}}).encode()
        response.__enter__=Mock(return_value=response);response.__exit__=Mock(return_value=False)
        opener=Mock();opener.open.return_value=response
        with patch.object(tools,'_root',return_value=self.root),patch.object(ai_api.urllib.request,'build_opener',return_value=opener):
            result=ai_api.complete('http://localhost/v1','sample','PRIVATE_KEY',[{'role':'user','content':'PRIVATE_BODY'}])
        self.assertEqual(result,'PRIVATE_RESPONSE')
        usage=tools.usage_summary(self.root)
        self.assertEqual(usage['input_tokens'],12);self.assertEqual(usage['output_tokens'],4)
        database=(self.root/'usage.sqlite3').read_bytes()
        for private in (b'PRIVATE_KEY',b'PRIVATE_BODY',b'PRIVATE_RESPONSE'): self.assertNotIn(private,database)
    def test_usage_rejects_negative_nan_and_currency(self):
        for rate in (-1, float('nan'), float('inf'), True, 'bad'):
            with self.subTest(rate=rate), self.assertRaises(ValueError): tools.usage_rates(self.root, {'input_per_million':rate})
        with self.assertRaises(ValueError): tools.usage_rates(self.root, {'currency':'private-code'})
    def test_usage_does_not_sum_different_currencies(self):
        for currency in ('CNY','USD'):
            tools.usage_rates(self.root, {'input_per_million':1,'currency':currency})
            tools.record_usage('api','sample',{'prompt_tokens':1000000,'completion_tokens':0},root=self.root)
        result=tools.usage_summary(self.root)
        self.assertIsNone(result['estimated_cost']); self.assertEqual(len(result['by_currency']),2)
    def test_reply_draft_is_saved_locally_without_changing_mail_or_report(self):
        report_before = self.report.read_bytes(); metadata_before=self.report.with_suffix('.mail.json').read_bytes()
        with patch.object(chat,'_complete',return_value='Dear Sender,\nThank you.') as complete:
            result=tools.dispatch(self.root, {'action':'reply_draft','path':str(self.report),'tone':'brief','language':'es'})
        self.assertFalse(result['sent']);self.assertEqual(result['recipient'],'sender@example.invalid')
        self.assertEqual(result['subject'],'Re: Question'); self.assertTrue(Path(result['path']).is_file())
        system=complete.call_args.args[2][0]['content']
        self.assertIn('Spanish',system);self.assertIn('Never send',system)
        self.assertEqual(self.report.read_bytes(),report_before);self.assertEqual(self.report.with_suffix('.mail.json').read_bytes(),metadata_before)
    def test_edited_reply_draft_persists_but_cannot_write_arbitrary_files(self):
        with patch.object(chat,'_complete',return_value='Initial draft'):
            draft=tools.reply_draft(self.root,{'path':str(self.report)})
        result=tools.draft_save(self.root,{'draft_path':draft['path'],'draft':'Edited reply'})
        self.assertEqual(result['draft'],'Edited reply');self.assertFalse(result['sent'])
        self.assertEqual(json.loads(Path(draft['path']).read_text())['draft'],'Edited reply')
        with self.assertRaises(ValueError): tools.draft_save(self.root,{'draft_path':str(self.config_path),'draft':'cannot overwrite config'})
    def test_reply_missing_original_and_oversized_context_do_not_call_ai(self):
        self.report.with_suffix('.mail.json').unlink()
        with patch.object(chat,'_complete') as complete, self.assertRaises(ValueError): tools.reply_draft(self.root, {'path':str(self.report)})
        complete.assert_not_called()
        self.mail['body']='x'*61000;self.report.with_suffix('.mail.json').write_text(json.dumps(self.mail))
        with patch.object(chat,'_complete') as complete, self.assertRaises(ValueError): tools.reply_draft(self.root, {'path':str(self.report)})
        complete.assert_not_called()
    def test_sources_have_real_pages_and_translated_labels(self):
        for language, expected in (('zh','原邮件正文'),('en','Original email body'),('es','Cuerpo del correo original')):
            self.config['ui_language']=language;self.save_config()
            result=tools.report_sources(self.root,str(self.report))
            self.assertEqual(result['sources'][0]['label'],expected)
            self.assertEqual([source['id'] for source in result['sources']],['mail.body','attachment.1.p1','attachment.1.p2'])
            self.assertIn('Second page fact',result['sources'][2]['text'])
            self.assertIn('document.pdf',result['sources'][2]['label'])
    def test_question_context_uses_original_and_never_generated_report(self):
        self.report.write_text('WRONG_GENERATED_REPORT: invoice is 9999')
        self.mail['body']='Original invoice is 1500'
        self.report.with_suffix('.mail.json').write_text(json.dumps(self.mail))
        with patch.object(chat,'_complete',return_value='1500 [mail.body]') as complete:
            result=chat.chat_send(self.root,str(self.report),'What is the invoice amount?')
        messages=complete.call_args.args[2]
        supplied=json.dumps(messages)
        self.assertIn('Original invoice is 1500',supplied)
        self.assertNotIn('WRONG_GENERATED_REPORT',supplied)
        self.assertEqual(result['answer'],'1500 [mail.body]')
    def test_source_missing_original_requires_retrieval_not_report_fallback(self):
        self.report.with_suffix('.mail.json').unlink()
        result=tools.report_sources(self.root,str(self.report))
        self.assertFalse(result['available']);self.assertEqual(result['sources'],[])
        self.assertIn('Retrieve the original email',result['limitation'])
        self.assertNotIn('can be discussed',result['limitation'])
    def test_resummary_preserves_original_sidecar_and_unread_attachment_limits(self):
        self.mail['attachments']=[{'name':'scan.pdf','text':'[page:1]\n[Scanned page: no text layer. OCR unavailable; contents were not read.]'}]
        sidecar=self.report.with_suffix('.mail.json');sidecar.write_text(json.dumps(self.mail));before=sidecar.read_bytes()
        with patch.object(chat,'_complete',return_value='New report [mail.body]') as complete:
            chat.report_retry(self.root,str(self.report))
        self.assertEqual(sidecar.read_bytes(),before)
        prompt=complete.call_args.args[2]
        self.assertIn('contents were not read',json.dumps(prompt))
        self.assertIn('Never fabricate',prompt[0]['content'])
    def test_empty_diagnostic_destination_does_not_create_cwd_export(self):
        for destination in ('','   '):
            with self.assertRaises(ValueError): tools.diagnostics_export(self.root,destination)
    def test_question_without_original_never_calls_ai(self):
        self.report.with_suffix('.mail.json').unlink()
        with patch.object(chat,'_complete') as complete, self.assertRaises(ValueError):
            chat.chat_send(self.root,str(self.report),'What does the original say?')
        complete.assert_not_called()
    def test_report_sources_reject_outside_paths(self):
        outside=self.root/'outside.md';outside.write_text('private')
        with self.assertRaises(ValueError): tools.report_sources(self.root,str(outside))
    def test_diagnostic_export_has_version_and_safe_structured_error_not_sensitive_content(self):
        self.config.update(api_key='PRIVATE_API_KEY',api_base='https://PRIVATE_HOST.invalid',mailboxes=[{'account':'PRIVATE_ACCOUNT'}]);self.save_config()
        (self.root/'log.txt').write_text('PRIVATE_MAIL_BODY PRIVATE_KEY')
        tools.record_diagnostic(self.root,'mail_check',TimeoutError('PRIVATE_ACCOUNT PRIVATE_TOKEN timed out /private/path'))
        result=tools.diagnostics_export(self.root,str(self.root/'export.zip'))
        self.assertEqual(Path(result['path']).resolve(),(self.root/'export.zip').resolve())
        with zipfile.ZipFile(result['path']) as archive:
            combined=''.join(archive.read(name).decode() for name in archive.namelist())
            summary=json.loads(archive.read('diagnostics.json'))
        for marker in ('PRIVATE_', 'sender@example.invalid', 'Original body fact', 'First page fact'):
            self.assertNotIn(marker,combined)
        self.assertIn('app_version',summary);self.assertEqual(summary['last_error']['category'],'timeout')
        self.assertEqual(summary['last_error']['type'],'TimeoutError')
    def test_diagnostic_export_revalidates_every_cached_error_value(self):
        private='PRIVATE_SECRET_TOKEN'
        (self.root/'last-diagnostic.json').write_text(json.dumps({'at':private,'stage':private,'type':private,'category':private,'http_code':private,'extra':private}))
        result=tools.diagnostics_export(self.root,str(self.root/'safe.zip'))
        with zipfile.ZipFile(result['path']) as archive:
            text=archive.read('diagnostics.json').decode()
        self.assertNotIn(private,text)
        value=json.loads(text)['last_error']
        self.assertEqual(value,{'stage':'operation','type':'Error','category':'other','http_code':None})
    def test_diagnostic_export_never_overwrites_existing_file(self):
        target=self.root/'existing.zip';target.write_bytes(b'existing')
        with self.assertRaises(FileExistsError): tools.diagnostics_export(self.root,str(target))
        self.assertEqual(target.read_bytes(),b'existing')
    def mailbox(self):
        client=Mock();client.response.return_value=('UIDVALIDITY',[b'12']);client.uid.return_value=('OK',[b'7 8 9'])
        return client
    def test_history_preview_count_has_no_ai_or_body_fetch_then_queue_is_confirmed(self):
        client=self.mailbox()
        profile={'account':'owner@example.invalid','host':'imap.example.invalid'}
        identifier='fixture'
        if WINDOWS:
            from benson_mail.mailbox_config import mailbox_id
            identifier=mailbox_id(profile);self.mail['mailbox_key']=identifier
            self.report.with_suffix('.mail.json').write_text(json.dumps(self.mail))
        with patch.object(tools,'_mailbox',return_value=(identifier,client)),patch.object(chat,'_complete') as complete:
            preview=tools.history_preview(self.root,{'from':'2026-10-01','to':'2026-10-10'})
            self.assertEqual(preview['count'],2);self.assertEqual(preview['already_summarized'],1)
            self.assertFalse((self.root/'history_queue'/f'{identifier}.json').exists())
            result=tools.history_start(self.root,{'preview_id':preview['preview_id']})
            complete.assert_not_called()
            self.assertEqual(result['queued'],2)
        self.assertTrue(all(call.args[0]=='search' for call in client.uid.call_args_list))
        saved=[]
        tools.consume_history(self.root,identifier,'12',lambda uids:saved.extend(uids))
        self.assertEqual(saved,[7,9]);self.assertFalse((self.root/'history_queue'/f'{identifier}.json').exists())
    def test_legacy_history_dedup_compares_contents_never_just_filename(self):
        original=dict(self.mail, received='2026-10-01T10:00:00+08:00')
        original.pop('uid',None);original.pop('uidvalidity',None);original.pop('mailbox_key',None)
        self.report.with_suffix('.mail.json').write_text(json.dumps(original))
        incoming=dict(original,historical=True,uid='8',uidvalidity='12',mailbox_key='fixture')
        self.assertEqual(Path(tools.existing_history_report(self.root,incoming)),self.report)
        incoming['body']='Different source body with same subject and timestamp'
        self.assertIsNone(tools.existing_history_report(self.root,incoming))
    def test_history_uidvalidity_change_cannot_queue_old_messages(self):
        client=self.mailbox()
        with patch.object(tools,'_mailbox',return_value=('fixture',client)):
            preview=tools.history_preview(self.root,{'from':'2026-10-01','to':'2026-10-10'})
            client.response.return_value=('UIDVALIDITY',[b'13'])
            with self.assertRaises(ValueError): tools.history_start(self.root,{'preview_id':preview['preview_id']})
        self.assertFalse((self.root/'history_queue').exists())
    def test_history_queue_retained_if_pending_progress_cannot_be_persisted(self):
        target=self.root/'history_queue'/'fixture.json';target.parent.mkdir();target.write_text('{"uidvalidity":"12","uids":[7]}')
        with self.assertRaises(OSError): tools.consume_history(self.root,'fixture','12',Mock(side_effect=OSError('disk full')))
        self.assertTrue(target.is_file())
    def test_history_reversed_dates_and_path_token_cannot_read_arbitrary_files(self):
        with patch.object(tools,'_mailbox') as mailbox, self.assertRaises(ValueError): tools.history_preview(self.root,{'from':'2026-10-10','to':'2026-10-01'})
        mailbox.assert_not_called()
        with self.assertRaises(ValueError): tools.history_start(self.root,{'preview_id':'../../config'})
    def test_pdf_actual_text_has_page_markers_and_scanned_pages_are_explicit(self):
        from pypdf import PdfWriter
        writer=PdfWriter();writer.add_blank_page(width=100,height=100)
        buffer=io.BytesIO();writer.write(buffer)
        with patch.object(reader,'_native_ocr',return_value=None),patch.object(reader,'_executable',return_value=None):
            result=reader.enhanced_text('scan.pdf',buffer.getvalue())
        self.assertIn('[page:1]',result);self.assertIn('no text layer',result)
    def test_image_uses_native_ocr_and_cannot_execute_attachments(self):
        with patch.object(reader,'_native_ocr',return_value='[OCR text; recognition may contain errors]\nHello') as native:
            result=reader.enhanced_text('photo.png',b'synthetic-image')
        self.assertIn('[image:1]',result);self.assertIn('Hello',result);native.assert_called_once()
        self.assertIsNone(reader.enhanced_text('program.exe',b'MZ'))

if __name__=='__main__': unittest.main()
