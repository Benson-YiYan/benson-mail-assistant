import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
RUNTIME=Path(__file__).resolve().parents[1]/'Runtime'
sys.path.insert(0,str(RUNTIME))
import ai_api
import ai_runner
from mail_policy import policy_save

class BackendLanguageTests(unittest.TestCase):
    def test_api_specific_errors_localized_and_redacted(self):
        for language,label in [('en','Cause:'),('es','Causa:')]:
            text=ai_api.connection_error(TimeoutError('secret https://example.invalid/private'),'secret',language=language)
            self.assertIn(label,text);self.assertIn('TimeoutError',text)
            self.assertNotIn('secret',text);self.assertNotIn('https://example',text)
    def test_policy_errors_use_current_settings_language(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            for language,label in [('en','blocklist'),('es','lista')]:
                (root/'settings.json').write_text(json.dumps({'ui_language':language}))
                with self.assertRaisesRegex(ValueError,label): policy_save(root,{'mode':'invalid'})
    def test_attachment_notes_localize_and_original_text_is_preserved(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);bad=root/'file.exe';bad.write_bytes(b'data')
            self.assertIn('Not read',ai_runner.attachment_text(bad,root,language='en'))
            self.assertIn('No leído',ai_runner.attachment_text(bad,root,language='es'))
            text=root/'readme.txt';text.write_text('原始中文文件内容')
            self.assertEqual(ai_runner.attachment_text(text,root,language='es'),'原始中文文件内容')
    def test_cached_manual_attachment_is_read_and_prompt_language_unchanged(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);identifier='a'*64;folder=root/'blocked_mail'/identifier/'work';folder.mkdir(parents=True)
            attachment=folder.parent/'attachment-0.txt';attachment.write_text('原始附件内容')
            message={'_policy_record_id':identifier,'subject':'原始中文主题','attachments':[{'filename':'original.txt','path':str(attachment)}]}
            config={'ai_provider':'api','ui_language':'es','api_base':'https://example.invalid','api_model':'synthetic'}
            with patch.object(ai_runner,'BASE',root),patch.object(ai_runner,'api_config',return_value=(config,'fake')),patch.object(ai_runner,'complete',return_value='ok') as complete:
                ai_runner.analyze_api(message,folder)
            args=complete.call_args.args[3]
            self.assertIn('español',args[0]['content'])
            content=json.loads(args[1]['content']);self.assertEqual(content['subject'],'原始中文主题')
            self.assertEqual(content['attachments'][0]['text'],'原始附件内容')
