"""Folder migration retains original reports, conversations, and cached job links."""
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

WINDOWS = Path(__file__).resolve().parents[1].name == "windows"
if WINDOWS:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from benson_mail import report_layout as layout
    from benson_mail.mailbox_config import mailbox_id
else:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "Runtime"))
    import report_layout as layout
    from mailbox_config import mailbox_id


class ReportLayoutTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.output = self.root / "reports"
        self.output.mkdir()
        self.connection = {"account": "owner@example.com", "host": "imap.example.com"}
        self.config = {"output_dir": str(self.output), "mailboxes": [
            self.connection if WINDOWS else {"connection": self.connection}]}
        self.message = {"mailbox_key": mailbox_id(self.connection), "uid": 42,
                        "from": "Sender Name <sender@example.org>",
                        "received_at": "2026-10-21T03:53:00+00:00", "subject": "example"}

    def test_unconfigured_startup_does_not_scan_default_directory(self):
        with patch.object(layout, "report_files", side_effect=AssertionError("must not scan")):
            self.assertEqual(layout.migrate_reports(self.root, {}), {"moved": 0, "skipped": 0, "errors": []})
        self.assertFalse((self.root / "report-layout-migration.json").exists())

    def tearDown(self):
        self.temp.cleanup()

    def legacy(self):
        path = self.output / "2026-10-21" / "example-11-53.md"
        path.parent.mkdir()
        path.write_text("## Report\n\nOriginal content.\n", encoding="utf-8")
        path.with_suffix(".mail.json").write_text(json.dumps(self.message), encoding="utf-8")
        return path

    def expected(self):
        return self.output / "owner@example.com/2026-10-21/From sender@example.org/example-11-53.md"

    def test_folder_uses_receiving_account_sender_address_and_beijing_day(self):
        message = dict(self.message, mailbox_account="Owner@Example.com")
        self.assertEqual(layout.report_folder(message, self.output),
                         self.expected().parent)
        other = dict(message, mailbox_account="second@example.com")
        self.assertNotEqual(layout.report_folder(message, self.output),
                            layout.report_folder(other, self.output))

    def test_old_report_without_sidecar_recovers_exact_cached_mail_and_archive_reference(self):
        source = self.output / "2026-10-21/example-11-53.txt"
        source.parent.mkdir()
        body = "邮件编号：42\n邮箱标识：" + self.message["mailbox_key"] + "\n## Original report\n"
        source.write_text(body, encoding="utf-8")
        for base, path, metadata in [
            ("mail_watch/42", str(source), self.message),
            # Reusing the same UID from another saved report must not be selected.
            ("mailboxes/other/mail_watch/42", str(self.output / "other.txt"),
             dict(self.message, sender="wrong@example.org", mailbox_key="wrong")),
            ("mailbox-archives/old/mail_watch/42", str(source), self.message),
        ]:
            folder = self.root / base
            folder.mkdir(parents=True)
            (folder / "saved.json").write_text(json.dumps({"saved": path}), encoding="utf-8")
            (folder / "mail.json").write_text(json.dumps(metadata), encoding="utf-8")
        result = layout.migrate_reports(self.root, self.config)
        target = self.expected().with_suffix(".txt")
        self.assertEqual(result["moved"], 1)
        self.assertEqual(target.read_text(encoding="utf-8"), body)
        recovered = json.loads(target.with_suffix(".mail.json").read_text(encoding="utf-8"))
        self.assertEqual(recovered["from"], self.message["from"])
        self.assertEqual(recovered["mailbox_account"], "owner@example.com")
        archived = self.root / "mailbox-archives/old/mail_watch/42/saved.json"
        self.assertEqual(json.loads(archived.read_text(encoding="utf-8"))["saved"], str(target))

    def test_recognized_marker_without_metadata_retains_body_with_unknown_sender(self):
        source = self.output / "2026-10-21/example-11-53.md"
        source.parent.mkdir()
        body = "邮件编号：42\n## Original report\nThe sender may be fake@example.org in AI output."
        source.write_text(body, encoding="utf-8")
        other = self.root / "mail_watch/42"
        other.mkdir(parents=True)
        # Exact UID with a different saved path is not evidence for this report.
        (other / "saved.json").write_text(json.dumps({"saved": str(self.output / "different.md")}), encoding="utf-8")
        (other / "mail.json").write_text(json.dumps(self.message), encoding="utf-8")
        self.assertEqual(layout.migrate_reports(self.root, self.config)["moved"], 1)
        target = self.output / "owner@example.com/2026-10-21/From unknown-sender/example-11-53.md"
        self.assertEqual(target.read_text(encoding="utf-8"), body)
        metadata = json.loads(target.with_suffix(".mail.json").read_text(encoding="utf-8"))
        self.assertTrue(metadata["unavailable"])
        self.assertEqual(metadata["uid"], "42")
        self.assertEqual(metadata["received_at"], "2026-10-21T11:53:00+08:00")
        self.assertEqual(layout.sender_address(metadata), "")

    def test_unrelated_text_and_nonnumeric_identity_are_not_migrated(self):
        day = self.output / "2026-10-21"
        day.mkdir()
        for name, text in [("contract.txt", "This is a personal contract."),
                           ("pretend.md", "邮件编号：not-a-uid\nDo not move."),
                           ("later-marker.txt", "Personal notes\n邮件编号：42\n")]:
            (day / name).write_text(text, encoding="utf-8")
        result = layout.migrate_reports(self.root, self.config)
        self.assertEqual(result["moved"], 0)
        self.assertEqual(len(list(day.iterdir())), 3)

    def test_unsafe_or_long_components_do_not_escape_or_collide(self):
        for value in ("../../escape", r"a\\b", "CON", "a"*300, "a\x00b"):
            result = layout.component(value, "unknown")
            self.assertLessEqual(len(result.encode()), 180)
            self.assertNotIn("/", result)
            self.assertNotIn("\\", result)
            self.assertNotIn("\x00", result)
        self.assertNotEqual(layout.component("a/b", "unknown"), layout.component("a\\b", "unknown"))

    def test_migration_keeps_chat_draft_and_job_references(self):
        source = self.legacy()
        target = self.expected()
        old_hash = hashlib.sha256(os.path.normcase(str(source)).encode()).hexdigest()
        chats = self.root / "mail_chats"
        chats.mkdir()
        history = {"schema_version": 1, "report": str(source), "messages": [
            {"role": "user", "content": "What does the original mail mean?"}],
            "summary": "Earlier context", "summarized_count": 0}
        (chats / (old_hash + ".json")).write_text(json.dumps(history), encoding="utf-8")
        draft = self.root / "reply_drafts/draft.json"
        draft.parent.mkdir()
        draft.write_text(json.dumps({"report": str(source), "draft": "Draft content"}), encoding="utf-8")
        job = self.root / "mailboxes/id/mail_watch/42/saved.json"
        job.parent.mkdir(parents=True)
        job.write_text(json.dumps({"saved": str(source)}), encoding="utf-8")
        before = source.read_bytes()
        result = layout.migrate_reports(self.root, self.config, windows=WINDOWS)
        self.assertEqual(result["moved"], 1)
        self.assertFalse(source.exists())
        self.assertEqual(target.read_bytes(), before)
        self.assertEqual(json.loads(target.with_suffix(".mail.json").read_text(encoding="utf-8"))["mailbox_account"], "owner@example.com")
        new_hash = hashlib.sha256(os.path.normcase(str(target)).encode()).hexdigest()
        migrated = json.loads((chats / (new_hash + ".json")).read_text(encoding="utf-8"))
        self.assertEqual(migrated["messages"], history["messages"])
        self.assertEqual(migrated["summary"], "Earlier context")
        self.assertEqual(migrated["report"], str(target))
        self.assertEqual(json.loads(job.read_text(encoding="utf-8"))["saved"], str(target))
        self.assertEqual(json.loads(draft.read_text(encoding="utf-8"))["draft"], "Draft content")
        self.assertEqual(json.loads(draft.read_text(encoding="utf-8"))["report"], str(target))
        self.assertEqual(layout.migrate_reports(self.root, self.config)["moved"], 0)

    def test_restart_finishes_interrupted_reference_update_without_duplicate(self):
        source = self.legacy()
        with patch.object(layout, "_rewrite_references", side_effect=OSError("synthetic interruption")):
            result = layout.migrate_reports(self.root, self.config)
            self.assertEqual(len(result["errors"]), 1)
        self.assertTrue(source.is_file())
        self.assertTrue(self.expected().is_file())
        self.assertEqual(layout.migrate_reports(self.root, self.config)["moved"], 1)
        self.assertEqual(list(layout.report_files(self.output)), [self.expected()])

    def test_failed_write_never_exposes_partial_final_report(self):
        target = self.output / "partial.md"
        with patch.object(layout.os, "fsync", side_effect=OSError("synthetic full disk")):
            with self.assertRaises(OSError):
                layout._create_complete_file(target, b"Complete report")
        self.assertFalse(target.exists())
        self.assertEqual(list(self.output.iterdir()), [])

    def test_corrupt_chat_preserves_original_and_other_reports_still_migrate(self):
        source = self.legacy()
        second = source.with_name("another-11-53.md")
        second.write_text("Second report", encoding="utf-8")
        second.with_suffix(".mail.json").write_text(json.dumps(dict(self.message, uid=43)), encoding="utf-8")
        chats = self.root / "mail_chats"
        chats.mkdir()
        old_hash = hashlib.sha256(os.path.normcase(str(source)).encode()).hexdigest()
        chat = chats / (old_hash + ".json")
        chat.write_text("{corrupt", encoding="utf-8")
        result = layout.migrate_reports(self.root, self.config)
        self.assertEqual(result["moved"], 1)
        self.assertEqual(len(result["errors"]), 1)
        self.assertTrue(source.is_file())
        self.assertFalse(second.exists())
        self.assertEqual(chat.read_text(encoding="utf-8"), "{corrupt")

    def test_corrupt_journal_is_retained_without_blocking_startup(self):
        source = self.legacy()
        journal = self.root / "report-layout-migration.json"
        journal.write_text("{corrupt", encoding="utf-8")
        result = layout.migrate_reports(self.root, self.config)
        self.assertEqual(result["moved"], 0)
        self.assertEqual(len(result["errors"]), 1)
        self.assertTrue(source.exists())
        self.assertEqual(journal.read_text(encoding="utf-8"), "{corrupt")

    def test_collision_and_unowned_files_are_retained(self):
        source = self.legacy()
        target = self.expected()
        target.parent.mkdir(parents=True)
        target.write_text("Do not overwrite", encoding="utf-8")
        note = source.parent / "notes.md"
        note.write_text("Unrelated notes", encoding="utf-8")
        result = layout.migrate_reports(self.root, self.config)
        self.assertEqual(result["moved"], 1)
        self.assertEqual(target.read_text(encoding="utf-8"), "Do not overwrite")
        self.assertTrue(target.with_stem(target.stem + "-migrated-1").exists())
        self.assertEqual(note.read_text(encoding="utf-8"), "Unrelated notes")

    def test_multiple_accounts_do_not_guess_missing_identity(self):
        self.config["mailboxes"].append(
            {"account": "second@example.com", "host": "imap.example.com"} if WINDOWS else
            {"connection": {"account": "second@example.com", "host": "imap.example.com"}})
        self.assertEqual(layout.account_for(self.message, self.config), "owner@example.com")
        self.assertEqual(layout.account_for({"mailbox_key": "unknown"}, self.config), "")

    @unittest.skipIf(os.name == "nt", "Symlinks need developer mode on Windows")
    def test_symlink_folder_is_not_traversed_or_used_as_destination(self):
        source = self.legacy()
        outside = self.root / "outside"
        outside.mkdir()
        (self.output / "owner@example.com").symlink_to(outside, target_is_directory=True)
        result = layout.migrate_reports(self.root, self.config)
        self.assertEqual(result["moved"], 0)
        self.assertTrue(source.exists())
        self.assertEqual(list(outside.iterdir()), [])

    def test_junctions_are_not_discovered_read_patched_or_used_as_destinations(self):
        source = self.legacy()
        linked_reports = self.output / "linked"
        linked_reports.mkdir()
        foreign = linked_reports / "foreign.md"; foreign.write_text("Foreign document")
        linked_cache = self.root / "mail_watch/42"
        linked_cache.mkdir(parents=True)
        (linked_cache / "saved.json").write_text(json.dumps({"saved": str(source)}))
        (linked_cache / "mail.json").write_text(json.dumps(self.message))
        linked_refs = self.root / "reply_drafts/linked"
        linked_refs.mkdir(parents=True)
        reference = linked_refs / "draft.json"
        original = json.dumps({"report": str(source)})
        reference.write_text(original)
        linked_destination = self.output / "owner@example.com"
        linked_destination.mkdir()
        blocked = {linked_reports, linked_cache, linked_refs, linked_destination}
        # Simulate Windows reparse points on any test host without real junctions.
        with patch.object(Path, "is_junction", new=lambda path: path in blocked, create=True):
            self.assertEqual(list(layout.report_files(self.output)), [source])
            self.assertEqual(list(layout.report_files(linked_reports)), [])
            self.assertEqual(layout._cached_report_metadata(self.root), {})
            layout._rewrite_references(self.root, {str(source): str(self.expected())})
            self.assertEqual(reference.read_text(), original)
            with self.assertRaises(ValueError):
                layout._safe(self.expected(), self.output)
            self.assertEqual(layout.migrate_reports(self.root, self.config)["moved"], 0)
        self.assertTrue(source.is_file())
        self.assertEqual(foreign.read_text(), "Foreign document")
        self.assertEqual(list(linked_destination.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
