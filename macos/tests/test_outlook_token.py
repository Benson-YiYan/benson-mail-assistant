import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'Runtime'))
import outlook_token as helper

CLIENT = '11111111-2222-3333-4444-555555555555'

class TokenTests(unittest.TestCase):
    def test_pending_slow_down_success(self):
        results = [dict(verification_uri='https://microsoft.com/devicelogin', user_code='DEMO', device_code='device-secret', expires_in=100, interval=2),
                   dict(error='authorization_pending'), dict(error='slow_down'), dict(access_token='private-token')]
        calls, sleeps, shown = [], [], []
        def post(url, values):
            calls.append((url, values)); return results.pop(0)
        token = helper.acquire(CLIENT, 'consumers', lambda *args: shown.append(args), request=post, sleep=sleeps.append, clock=lambda: 0)
        self.assertEqual(token, 'private-token')
        self.assertEqual(sleeps, [2, 2, 7])
        self.assertEqual(shown, [('https://microsoft.com/devicelogin', 'DEMO')])
        self.assertEqual(calls[0], ('https://login.microsoftonline.com/consumers/oauth2/v2.0/devicecode', {'client_id': CLIENT, 'scope': helper.SCOPE}))
        self.assertEqual(calls[-1][1]['grant_type'], 'urn:ietf:params:oauth:grant-type:device_code')

    def test_rejection_and_untrusted_url(self):
        for response in [dict(error='access_denied'), dict(error='sensitive-token-text'), dict(verification_uri='https://attacker.invalid/',user_code='x',device_code='x',expires_in=10)]:
            shown=[]
            with self.assertRaises(RuntimeError) as error:
                helper.acquire(CLIENT, 'consumers', lambda *args: shown.append(args), request=lambda *args: response)
            self.assertNotIn('sensitive-token-text', str(error.exception))
            self.assertEqual(shown, [])
        with self.assertRaises(ValueError):
            helper.acquire(CLIENT, 'consumers/path', lambda *args: None, request=lambda *args: self.fail('must not request'))

    def test_expiration(self):
        now=[0]
        def sleep(seconds): now[0]+=seconds
        response=dict(verification_uri='https://microsoft.com/devicelogin', user_code='DEMO', device_code='private', expires_in=2, interval=5)
        with self.assertRaisesRegex(RuntimeError, 'expired_token'):
            helper.acquire(CLIENT,'consumers',lambda *args: None,request=lambda *args: response,sleep=sleep,clock=lambda: now[0])

    def test_main_copies_without_output_or_file_token(self):
        with tempfile.TemporaryDirectory() as directory:
            home=Path(directory)
            (home/'settings.json').write_text(json.dumps({'ui_language':'en'}))
            stream=io.StringIO()
            with patch('runtime_paths.data_home',return_value=home),patch('builtins.input',side_effect=[CLIENT,'','']),patch.object(helper,'acquire',return_value='private-token'),patch.object(helper.subprocess,'run') as run,contextlib.redirect_stdout(stream):
                helper.main()
            run.assert_called_once_with(['/usr/bin/pbcopy'],input=b'private-token',check=True)
            self.assertIn('Access token copied!',stream.getvalue())
            self.assertNotIn('private-token',stream.getvalue())
            self.assertEqual([p.name for p in home.iterdir()],['settings.json'])

if __name__=='__main__': unittest.main()
