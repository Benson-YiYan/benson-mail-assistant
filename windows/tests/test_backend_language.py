"""Runtime notices localize fixed labels while preserving original user/mail data."""
import json
from pathlib import Path
import tempfile
import unittest
from datetime import datetime, timezone
from email.message import EmailMessage
from benson_mail import ai_api
from benson_mail.core import Service, attachment_text
from benson_mail.mail_policy import policy_save

class BackendLanguageTests(unittest.TestCase):
    def test_chinglish_summaries_are_phonetic_and_keep_original_data(self):
        from benson_mail.mail_chat import _language, _chat_system
        from benson_mail.core import analysis_prompt
        from benson_mail.runtime_i18n import text, using_language
        self.assertEqual(_language({'ui_language': 'chinglish'}), 'en')
        self.assertIn('Answer in English', _chat_system(_language({'ui_language': 'chinglish'})))
        prompt = analysis_prompt('chinglish')
        self.assertIn('Output language for this report: Chinglish', prompt)
        self.assertIn('喵·瑞泼特斯', prompt)
        self.assertIn('Preserve exact email addresses', prompt)
        self.assertIn('copyable suggested email reply must remain', prompt)
        for code in ('zh', 'en', 'es'):
            self.assertNotIn('Output language for this report: Chinglish', analysis_prompt(code))
        self.assertIn('Custom summary prompt:', analysis_prompt('chinglish', '用户要求保持原样'))
        self.assertIn('用户要求保持原样', analysis_prompt('chinglish', '用户要求保持原样'))
        with using_language('chinglish'):
            self.assertEqual(text('AI 连接正常。'), 'AI connection successful.')
            self.assertEqual(text('原始邮件正文'), '原始邮件正文')

    def test_chinglish_language_pack_identity_and_catalog_are_supported(self):
        from benson_mail.language_packs import validate_pack, CODES
        payload = {'schema_version': 1, 'platform': 'windows', 'language': 'chinglish',
                   'exact': {'邮件报告': '喵·瑞泼特斯'}, 'templates': [],
                   'guides': {'mail_account': '阿康特', 'quick_start': '盖德'}}
        self.assertIn('chinglish', CODES)
        self.assertEqual(validate_pack(json.dumps(payload).encode(), 'chinglish', 'windows'), payload)

    def test_live_notifications_follow_language_and_keep_subject(self):
        class Box:
            messages={1:None}
            def snapshot(self): return '1',sorted(self.messages)
            def fetch(self,uid):
                message=EmailMessage();message['Subject']='原始中文主题';message['From']='sender@example.com';message.set_content('原始中文正文')
                return message.as_bytes(),datetime.now(timezone.utc)
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);events=[];box=Box();box.messages={1:None}
            service=Service({'account':'synthetic@example.com','output_dir':str(root/'reports'),'ui_language':'en'},'',root/'state',events.append,mailbox=box,analyzer=lambda msg,stop:'report')
            service.check_once();box.messages[2]=None;service.check_once()
            notices=[v['notification'] for v in events if 'notification'in v]
            self.assertIn('mail',notices[0]['title'])
            self.assertIn('原始中文主题',notices[0]['message']);self.assertIn('English',notices[0]['message'])
            service.config['ui_language']='es';events.clear();box.messages[3]=None;service.check_once()
            notice=next(v['notification'] for v in events if 'notification'in v)
            self.assertIn('correo',notice['title'].lower());self.assertIn('español',notice['message'])
            self.assertIn('原始中文主题',notice['message'])
    def test_policy_errors_use_persisted_ui_language(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            for language,expected in [('en','blocklist'),('es','lista')]:
                (root/'config.json').write_text(json.dumps({'ui_language':language}))
                with self.assertRaisesRegex(ValueError,expected): policy_save(root,{'mode':'invalid'})
    def test_api_errors_remain_specific_and_secret_free(self):
        for language,expected in [('en','Cause:'),('es','Causa:')]:
            text=ai_api.connection_error(TimeoutError('synthetic-secret at https://example.invalid/private'), 'synthetic-secret',language=language)
            self.assertIn(expected,text);self.assertIn('TimeoutError',text)
            self.assertNotIn('synthetic-secret',text);self.assertNotIn('https://example',text)
            self.assertNotIn('具体原因',text)
    def test_attachment_notes_localize_without_translating_content(self):
        self.assertIn('Not read',attachment_text('file.exe',b'unknown',language='en'))
        self.assertIn('No leído',attachment_text('file.exe',b'unknown',language='es'))
        self.assertEqual(attachment_text('readme.txt','用户输入不翻译'.encode(),language='es'),'用户输入不翻译')
