import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'Runtime'))
import mail_export

class CrossMailboxExportTests(unittest.TestCase):
    def test_same_uid_subject_and_receipt_time_do_not_overwrite_other_mailbox(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root/'settings.json').write_text(json.dumps({'output_dir': str(root/'reports')}))
            message = {'uid': 101, 'subject': '同名合同', 'received_at': '2026-10-17T08:00:00+08:00',
                       'mailbox_key': 'a'*64, 'from': 'first@example.invalid'}
            with patch.object(mail_export, 'BASE', root):
                first = mail_export.export(message, 'FIRST_SYNTHETIC_REPORT')
                message.update(mailbox_key='b'*64, **{'from': 'second@example.invalid'})
                second = mail_export.export(message, 'SECOND_SYNTHETIC_REPORT')
                retry = mail_export.export(message, 'SECOND_SYNTHETIC_REPORT')
            self.assertNotEqual(first, second)
            self.assertEqual(second, retry)
            self.assertIn('FIRST_SYNTHETIC_REPORT', first.read_text())
            self.assertEqual(json.loads(first.with_suffix('.mail.json').read_text())['from'], 'first@example.invalid')
            self.assertEqual(json.loads(second.with_suffix('.mail.json').read_text())['from'], 'second@example.invalid')
            self.assertEqual(first.name, '同名合同-08-00.md')

    def test_legacy_txt_sidecar_is_retained_and_different_mailbox_gets_separate_markdown(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            (root/'settings.json').write_text(json.dumps({'output_dir':str(root/'reports')}))
            message={'uid':101,'subject':'Legacy','received_at':'2026-10-17T08:00:00+08:00','mailbox_key':'a'}
            old=root/'reports/2026-10-17/Legacy-08-00.txt';old.parent.mkdir(parents=True)
            old.write_text('邮件编号：101\n邮箱标识：a\nOriginal TXT')
            sidecar=old.with_suffix('.mail.json');sidecar.write_text(json.dumps(message))
            before=sidecar.read_bytes()
            with patch.object(mail_export,'BASE',root):
                migrated=mail_export.export(message,'Must not duplicate old report')
                self.assertEqual(migrated.name, old.name)
                self.assertIn('From unknown-sender', str(migrated))
                self.assertFalse(old.exists())
                new=mail_export.export(dict(message,mailbox_key='b'),'## 1. New email\n**Markdown**')
                again=mail_export.export(dict(message,mailbox_key='b'),'## 1. New email\n**Markdown**')
            self.assertEqual(new,again);self.assertNotEqual(new.stem,old.stem)
            self.assertEqual(new.suffix,'.md');self.assertEqual(json.loads(migrated.with_suffix('.mail.json').read_bytes()),json.loads(before))
            self.assertEqual(migrated.read_text(),'邮件编号：101\n邮箱标识：a\nOriginal TXT')
            self.assertEqual(len(list(migrated.parent.glob('*.md'))),1)
