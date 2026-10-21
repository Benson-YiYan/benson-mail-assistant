"""Private metadata preserves original mail without JSON clutter beside reports."""
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

WINDOWS = Path(__file__).resolve().parents[1].name == 'windows'
if WINDOWS:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from benson_mail import report_metadata as metadata, report_layout as layout, mail_chat
else:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'Runtime'))
    import report_metadata as metadata
    import report_layout as layout
    import mail_chat


class PrivateMetadataTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.home = Path(self.temp.name).resolve()
        self.output = self.home / 'reports'
        self.report = self.output / 'owner@example.org/2026-10-21/From sender@example.org/example-11-53.md'
        self.report.parent.mkdir(parents=True)
        self.report.write_text('Generated summary, never the original mail.', encoding='utf-8')
        self.message = {'uid': 12, 'mailbox_account': 'owner@example.org', 'from': 'sender@example.org',
                        'subject': 'Example', 'received_at': '2026-10-21T03:53:00+00:00',
                        'body': 'Original fact 42', 'bodies': [{'text': 'Original fact 42'}], 'attachments': []}

    def tearDown(self):
        self.temp.cleanup()

    def sidecar(self):
        path = self.report.with_suffix('.mail.json')
        path.write_text(json.dumps(self.message), encoding='utf-8')
        return path

    def test_private_path_hash_is_canonical_and_write_has_no_sibling(self):
        expected = hashlib.sha256(os.path.normcase(str(self.report.resolve())).encode()).hexdigest()
        self.assertEqual(metadata.metadata_path(self.home, self.report).name, expected + '.json')
        path = metadata.write_metadata(self.home, self.report, self.message)
        self.assertEqual(metadata.read_metadata(self.home, self.report), self.message)
        self.assertEqual(list(self.output.rglob('*.json')), [])
        if os.name != 'nt':
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(path.parent.stat().st_mode & 0o777, 0o700)

    def test_existing_nested_sidecar_relocates_without_modifying_report_or_context(self):
        sidecar = self.sidecar(); before = self.report.read_bytes()
        result = layout.migrate_reports(self.home, {'output_dir': str(self.output)})
        self.assertEqual(result['metadata_moved'], 1)
        self.assertFalse(result['errors'])
        self.assertFalse(sidecar.exists())
        self.assertEqual(self.report.read_bytes(), before)
        context = mail_chat._mail_context(self.home, self.report, {}, require_original=True)
        self.assertEqual(context['original_mail']['subject'], 'Example')
        self.assertIn('Original fact 42', json.dumps(context))
        self.assertNotIn('Generated summary', json.dumps(context))
        self.assertEqual(layout.migrate_reports(self.home, {'output_dir': str(self.output)})['metadata_moved'], 0)

    def test_corrupt_internal_record_never_falls_back_to_old_record(self):
        self.sidecar()
        path = metadata.metadata_path(self.home, self.report);path.parent.mkdir()
        path.write_text('{corrupt', encoding='utf-8')
        with self.assertRaises(ValueError):metadata.read_metadata(self.home, self.report)
        result = metadata.migrate_metadata(self.home, self.output)
        self.assertEqual(len(result['errors']), 1)
        self.assertTrue(self.report.with_suffix('.mail.json').is_file())
        self.assertEqual(path.read_text(encoding='utf-8'), '{corrupt')

    def test_conflicting_internal_record_and_unrelated_json_are_retained(self):
        sidecar = self.sidecar()
        metadata.write_metadata(self.home, self.report, dict(self.message, subject='Different original'))
        unrelated = self.report.parent / 'notes.json';unrelated.write_text('{"private":"notes"}', encoding='utf-8')
        orphan = self.report.parent / 'orphan.mail.json';orphan.write_text(json.dumps(self.message), encoding='utf-8')
        result = metadata.migrate_metadata(self.home, self.output)
        self.assertEqual(len(result['errors']), 1)
        self.assertTrue(sidecar.is_file());self.assertTrue(unrelated.is_file());self.assertTrue(orphan.is_file())
        self.assertEqual(metadata.read_metadata(self.home, self.report)['subject'], 'Different original')

    def test_interrupted_private_write_retains_original_and_exposes_no_partial_record(self):
        sidecar = self.sidecar()
        with patch.object(metadata.os, 'fsync', side_effect=OSError('synthetic disk full')):
            result = metadata.migrate_metadata(self.home, self.output)
        self.assertEqual(len(result['errors']), 1)
        self.assertTrue(sidecar.is_file())
        self.assertFalse(metadata.metadata_path(self.home, self.report).exists())
        self.assertEqual(metadata.migrate_metadata(self.home, self.output)['moved'], 1)

    def test_legacy_sidecar_is_still_readable_before_migration(self):
        self.sidecar()
        self.assertEqual(metadata.read_metadata(self.home, self.report), self.message)

    def test_directory_junction_is_not_followed(self):
        sidecar = self.sidecar()
        with patch.object(Path, 'is_junction', new=lambda p: p == self.report.parent, create=True):
            self.assertEqual(metadata.migrate_metadata(self.home, self.output)['moved'], 0)
        self.assertTrue(sidecar.exists())

    def test_old_pending_journal_recovers_completed_report_and_old_sidecar(self):
        source = self.output / '2026-10-21/example-11-53.md';source.parent.mkdir()
        source.with_suffix('.mail.json').write_text(json.dumps(self.message), encoding='utf-8')
        self.sidecar()
        (self.home/'report-layout-migration.json').write_text(json.dumps({'schema_version':1,'moves':[
            {'source':str(source),'target':str(self.report),'account':'owner@example.org','status':'pending'}]}),encoding='utf-8')
        result=layout.migrate_reports(self.home,{'output_dir':str(self.output)})
        self.assertEqual(result['moved'],1);self.assertFalse(result['errors'])
        self.assertEqual(list(self.output.rglob('*.json')),[])
        self.assertEqual(metadata.read_metadata(self.home,self.report),self.message)


if __name__ == '__main__':unittest.main()
