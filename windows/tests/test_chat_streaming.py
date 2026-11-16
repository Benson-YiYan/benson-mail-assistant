import sys
from benson_mail.ai_api import read_stream

import io
import json
import unittest

class StreamTests(unittest.TestCase):
    def events(self, *values):
        return io.BytesIO(b''.join(b'data: ' + (v if isinstance(v, bytes) else json.dumps(v, ensure_ascii=False).encode()) + b'\n\n' for v in values))

    def test_deltas_are_delivered_before_stream_finishes_and_reasoning_is_hidden(self):
        seen = []
        source = self.events(
            {'choices': [{'delta': {'reasoning_content': 'private reasoning'}}]},
            {'choices': [{'delta': {'content': '# 标题\n'}}]},
            {'choices': [{'delta': {'content': '| A | B |'}, 'finish_reason': 'stop'}]},
            {'choices': [], 'usage': {'prompt_tokens': 9, 'completion_tokens': 4}}, b'[DONE]')
        value = read_stream(source, seen.append)
        self.assertEqual(seen, ['# 标题\n', '| A | B |'])
        self.assertEqual(value['choices'][0]['message']['content'], ''.join(seen))
        self.assertEqual(value['usage']['prompt_tokens'], 9)

    def test_truncated_stream_reports_error_after_delivering_partial_text(self):
        seen = []
        with self.assertRaisesRegex(RuntimeError, 'AI_STREAM_INCOMPLETE'):
            read_stream(self.events({'choices': [{'delta': {'content': 'partial'}}]}), seen.append)
        self.assertEqual(seen, ['partial'])

    def test_stream_provider_error_never_exposes_response_body(self):
        with self.assertRaisesRegex(RuntimeError, 'AI_STREAM_PROVIDER') as failure:
            read_stream(self.events({'error': {'message': 'secret-provider-body'}}), lambda _: None)
        self.assertNotIn('secret-provider-body', str(failure.exception))

    def test_callback_runs_while_response_still_has_unread_events(self):
        source = self.events({'choices': [{'delta': {'content': 'first'}}]}, b'[DONE]')
        positions = []
        read_stream(source, lambda _: positions.append(source.tell()))
        self.assertEqual(len(positions), 1)
        self.assertLess(positions[0], len(source.getvalue()))

    def test_multiline_sse_event_and_comments(self):
        source = io.BytesIO(b': heartbeat\r\ndata: {"choices":\r\ndata: [{"delta":{"content":"hello"},"finish_reason":"stop"}]}\r\n\r\ndata: [DONE]\r\n\r\n')
        seen = []
        value = read_stream(source, seen.append)
        self.assertEqual(seen, ['hello'])
        self.assertEqual(value['choices'][0]['finish_reason'], 'stop')

    def test_oversized_line_is_bounded_before_allocation(self):
        from unittest.mock import patch
        module = sys.modules[read_stream.__module__]
        source = io.BytesIO(b'data: ' + b'x' * 1000)
        with patch.object(module, 'MAX_RESPONSE', 64):
            with self.assertRaisesRegex(RuntimeError, 'AI_STREAM_LIMIT'):
                read_stream(source, lambda _: None)
        self.assertEqual(source.tell(), 65)

    def test_cancel_does_not_consume_or_deliver_more_content(self):
        import threading
        stop = threading.Event()
        stop.set()
        source = self.events({'choices': [{'delta': {'content': 'never'}}]}, b'[DONE]')
        with self.assertRaisesRegex(RuntimeError, 'AI_CANCELLED'):
            read_stream(source, lambda _: self.fail('unexpected content'), stop)
        self.assertEqual(source.tell(), 0)

    def test_malformed_events_have_safe_error_code(self):
        for raw in (b'{secret-provider-body', b'[]', b'{"choices":null}'):
            with self.subTest(raw=raw):
                with self.assertRaisesRegex(RuntimeError, 'AI_STREAM_INVALID') as failure:
                    read_stream(self.events(raw), lambda _: None)
                self.assertNotIn('secret-provider-body', str(failure.exception))

    def test_content_parts_and_nonzero_choice_are_filtered(self):
        seen = []
        value = read_stream(self.events({'choices': [
            {'index': 1, 'delta': {'content': 'other choice'}},
            {'index': 0, 'delta': {'content': [{'type': 'text', 'text': 'public'}, {'type': 'text', 'text': None}]}, 'finish_reason': 'stop'}]}, b'[DONE]'), seen.append)
        self.assertEqual(seen, ['public'])
        self.assertEqual(value['choices'][0]['message']['content'], 'public')

    def test_complete_stream_request_preserves_usage_without_second_request(self):
        import importlib
        from unittest.mock import Mock, patch
        api = sys.modules[read_stream.__module__]
        tools = importlib.import_module((api.__package__ + '.' if api.__package__ else '') + 'assistant_tools')
        usage = {'prompt_tokens': 9, 'completion_tokens': 4}
        data = self.events(
            {'choices': [{'index': 0, 'delta': {'content': 'first'}}]},
            {'choices': [{'index': 0, 'delta': {'content': ' second'}, 'finish_reason': 'stop'}]},
            {'choices': [], 'usage': usage}, b'[DONE]').getvalue()
        source = io.BytesIO(data)
        source.headers = {'Content-Type': 'text/event-stream; charset=utf-8'}
        opener = Mock()
        opener.open.return_value = source
        seen = []
        def receive(chunk):
            self.assertFalse(source.closed)
            self.assertLess(source.tell(), len(data))
            seen.append(chunk)
        with patch.object(api.urllib.request, 'build_opener', return_value=opener), patch.object(tools, 'record_usage') as record:
            answer = api.complete('https://example.invalid/v1', 'model', 'synthetic-key',
                                  [{'role': 'user', 'content': 'question'}], on_delta=receive)
        self.assertEqual(answer, 'first second')
        self.assertEqual(seen, ['first', ' second'])
        opener.open.assert_called_once()
        request = opener.open.call_args.args[0]
        payload = json.loads(request.data)
        self.assertTrue(payload['stream'])
        self.assertEqual(payload['stream_options'], {'include_usage': True})
        self.assertEqual(request.get_header('Accept'), 'text/event-stream')
        record.assert_called_once_with('api', 'model', usage, base='https://example.invalid/v1')

    def test_nonstream_request_omits_stream_options(self):
        import importlib
        from unittest.mock import Mock, patch
        api = sys.modules[read_stream.__module__]
        tools = importlib.import_module((api.__package__ + '.' if api.__package__ else '') + 'assistant_tools')
        source = io.BytesIO(json.dumps({'choices': [{'message': {'content': 'answer'}}]}).encode())
        opener = Mock()
        opener.open.return_value = source
        with patch.object(api.urllib.request, 'build_opener', return_value=opener), patch.object(tools, 'record_usage'):
            self.assertEqual(api.complete('https://example.invalid/v1', 'model', 'synthetic-key', []), 'answer')
        payload = json.loads(opener.open.call_args.args[0].data)
        self.assertFalse(payload['stream'])
        self.assertNotIn('stream_options', payload)
        opener.open.assert_called_once()
