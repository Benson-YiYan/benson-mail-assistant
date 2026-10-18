import json
from pathlib import Path
import tempfile
import unittest
import importlib.util
import sys
from unittest.mock import patch

RUNTIME = Path(__file__).resolve().parents[1] / 'Runtime'
sys.path.insert(0, str(RUNTIME))
from mailbox_config import mailbox_id, normalize


class MultipleMailTests(unittest.TestCase):
    def test_independent_progress_failure_isolation_pause_and_legacy_migration(self):
        with tempfile.TemporaryDirectory() as temporary, patch.dict('os.environ', {'BENSON_MAIL_HOME': temporary}):
            spec = importlib.util.spec_from_file_location('multi_daemon_fixture', RUNTIME / 'mail_daemon.py')
            daemon = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(daemon)
            root = Path(temporary)
            first = normalize({'account': 'one@example.invalid', 'host': 'imap.example.invalid'})
            second = normalize({'account': 'two@example.invalid', 'host': 'imap.second.invalid'})
            profiles = [{'connection': first, 'enabled': True}, {'connection': second, 'enabled': True}]
            value = {'enabled': True, 'mailboxes': profiles}
            daemon.SETTINGS.write_text(json.dumps(value))
            legacy = {'uidvalidity': '42', 'next_uid': 99, 'pending': [98], 'mailbox_key': mailbox_id(first)}
            (daemon.CONTROL / 'state.json').write_text(json.dumps(legacy))
            seen = []
            def read():
                connection = json.loads((daemon.ACTIVE_HOME / 'settings.json').read_text())['mailbox']
                seen.append(connection['account'])
                if connection['account'] == first['account']:
                    self.assertEqual(json.loads((daemon.DATA / 'state.json').read_text()), legacy)
                    raise RuntimeError('synthetic secret MUST NOT BE SHOWN')
                (daemon.DATA / 'state.json').write_text('{"pending":[],"next_uid":5}')
                return {'pending_messages': 0}
            with patch.object(daemon, 'run_reader', read), patch.object(daemon, 'analyze') as ai:
                failures, _, count = daemon.check_profiles()
                self.assertEqual(count, 2)
                self.assertEqual(seen, [first['account'], second['account']])
                self.assertEqual(len(failures), 1)
                self.assertNotIn('MUST NOT', failures[0])
                ai.assert_not_called()
                profiles[0]['enabled'] = False
                daemon.SETTINGS.write_text(json.dumps(value))
                seen.clear()
                daemon.check_profiles()
                self.assertEqual(seen, [second['account']])
            self.assertEqual(daemon.DATA, daemon.CONTROL)
            self.assertIsNone(daemon.ACTIVE_ID)
            one = root / 'mailboxes' / mailbox_id(first) / 'mail_watch/state.json'
            two = root / 'mailboxes' / mailbox_id(second) / 'mail_watch/state.json'
            self.assertEqual(json.loads(one.read_text())['pending'], [98])
            self.assertEqual(json.loads(two.read_text())['next_uid'], 5)
