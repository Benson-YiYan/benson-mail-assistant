import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError


ROOT = Path(__file__).resolve().parents[1]
if (ROOT / 'Runtime').is_dir():
    sys.path.insert(0, str(ROOT / 'Runtime'))
    import ai_api
    import context_budget as budget
else:
    from benson_mail import ai_api
    from benson_mail import context_budget as budget


class ContextBudgetTests(unittest.TestCase):
    config = {'ai_provider': 'api', 'api_base': 'https://example.invalid/v1/chat/completions',
              'api_model': 'target'}

    def setUp(self):
        budget._cache.clear()

    def test_provider_budget_uses_exact_model_and_is_cached(self):
        payload = {'data': [{'id': 'different', 'context_length': 8000},
                            {'id': 'target', 'context_length': 100000,
                             'top_provider': {'context_length': 64000, 'max_completion_tokens': 2000}}]}
        opener = Mock()
        opener.open.return_value = io.BytesIO(json.dumps(payload).encode())
        with tempfile.TemporaryDirectory() as profile, \
                patch.object(ai_api, 'saved_api_key', return_value='test-key'), \
                patch.object(ai_api.urllib.request, 'build_opener', return_value=opener) as build:
            self.assertEqual(budget.input_budget(profile, self.config), 62000)
            self.assertEqual(budget.input_budget(profile, self.config), 62000)
            budget._cache.clear()  # Simulate the subprocess launched for the next Mac turn.
            self.assertEqual(budget.input_budget(profile, self.config), 62000)
            cached = (Path(profile) / 'chat-model-limit.json').read_text()
            self.assertNotIn('test-key', cached)
            self.assertNotIn('example.invalid', cached)
        opener.open.assert_called_once()
        request = opener.open.call_args.args[0]
        self.assertEqual(request.full_url, 'https://example.invalid/v1/models')
        self.assertEqual(request.get_header('Authorization'), 'Bearer test-key')
        handler = build.call_args.args[0]
        self.assertIsInstance(handler, ai_api.NoRedirect)
        self.assertIsNone(handler.redirect_request(request, None, 302, '', {}, 'https://other.invalid/'))

    def test_unavailable_metadata_and_cli_use_token_fallback(self):
        with patch.object(budget, '_metadata_budget', return_value=None) as lookup:
            result = budget.input_budget('synthetic-root', self.config)
            self.assertEqual(budget.input_budget('synthetic-root', self.config), result)
            self.assertEqual(result, budget.FALLBACK_INPUT_TOKENS['api'])
            budget.input_budget('synthetic-root', {'ai_provider': 'codex'})
        lookup.assert_called_once()

    def test_cjk_and_cli_framing_have_higher_estimations(self):
        self.assertGreater(budget.estimate_text('\u4e2d' * 100), budget.estimate_text('a' * 100))
        messages = [{'role': 'user', 'content': 'hello'}]
        self.assertGreater(budget.estimate_messages(messages, 'codex'), budget.estimate_messages(messages))

    def test_http_context_rejection_is_typed_and_does_not_reveal_error_body(self):
        body = io.BytesIO(b'{"error":{"code":"context_length_exceeded","message":"private"}}')
        opener = Mock()
        opener.open.side_effect = HTTPError('https://example.invalid', 400, 'too long', {}, body)
        with patch.object(ai_api.urllib.request, 'build_opener', return_value=opener):
            with self.assertRaises(budget.ContextLengthError) as failure:
                ai_api.complete(self.config['api_base'], 'target', 'test-key', [])
        self.assertTrue(failure.exception.safe_to_retry)
        self.assertNotIn('private', str(failure.exception))
        self.assertTrue(body.closed)

    def test_stream_context_rejection_only_retries_before_visible_output(self):
        rejection = b'data: {"error":{"code":"context_length_exceeded"}}\n\n'
        partial = b'data: {"choices":[{"delta":{"content":"part"}}]}\n\n'
        for body, seen in [(rejection, []), (partial + rejection, ['part'])]:
            actual = []
            with self.assertRaises(budget.ContextLengthError) as failure:
                ai_api.read_stream(io.BytesIO(body), actual.append)
            self.assertEqual(failure.exception.safe_to_retry, not seen)
            self.assertEqual(actual, seen)
