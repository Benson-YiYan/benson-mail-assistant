"""Exercise the actual JSON worker entry point without contacting mail or AI."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

RUNTIME = Path(__file__).resolve().parents[1] / 'Runtime'


class PolicyWorkerTests(unittest.TestCase):
    def test_policy_persists_and_manual_queue_wakes_correct_listener(self):
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)
            request = home / 'request.json'
            def call(value):
                request.write_text(json.dumps(value))
                result = subprocess.run(
                    [sys.executable, str(RUNTIME / 'worker_main.py'), '--home', str(home),
                     '--mail-policy', str(request)],
                    capture_output=True, text=True, timeout=15)
                return result.returncode, json.loads(result.stdout)
            code, result = call({'action': 'save', 'policy': {
                'mode': 'blacklist', 'addresses': ['Blocked@Example.com'], 'skip_spam': True}})
            self.assertEqual(code, 0)
            self.assertEqual(result['policy']['addresses'], ['blocked@example.com'])
            self.assertTrue(call({'action': 'status'})[1]['policy']['skip_spam'])
            self.assertFalse((home / 'mail_watch/check.request').exists())
            code, result = call({'action': 'summarize_records', 'ids': []})
            self.assertEqual(code, 0)
            self.assertTrue(result['ok'])
            self.assertTrue((home / 'mail_watch/check.request').exists())
            code, result = call({'action': 'unknown'})
            self.assertEqual(code, 1)
            self.assertFalse(result['ok'])

