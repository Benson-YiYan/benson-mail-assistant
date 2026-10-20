"""Official balance endpoints are allowlisted and never invoke paid completions."""
import io
import json
from pathlib import Path
import socket
import ssl
import sys
import unittest
from unittest.mock import Mock, patch
import urllib.error

WINDOWS = Path(__file__).resolve().parents[1].name == 'windows'
if WINDOWS:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from benson_mail import upstream_billing as billing
else:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'Runtime'))
    import upstream_billing as billing


class UpstreamBillingTests(unittest.TestCase):
    def setUp(self):
        self.config = {'ai_provider': 'api', 'api_base': 'https://api.deepseek.com/v1'}
        self.key = 'PRIVATE_API_SECRET'
        self.ai, self.chat = billing._modules()
        self.fixture = {'balance_infos': [{'currency': 'CNY', 'total_balance': '12.50',
            'granted_balance': '2.50', 'topped_up_balance': '10.00'}]}

    def request(self, value=None, error=None, raw=None, config=None):
        response = Mock()
        response.read.return_value = raw if raw is not None else json.dumps(value).encode()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        opener = Mock()
        opener.open.side_effect = error
        opener.open.return_value = response
        with patch.object(billing.urllib.request, 'build_opener', return_value=opener) as build, \
                patch.object(self.ai, 'tls_context', create=True, return_value=ssl.create_default_context()), \
                patch.object(self.ai, 'complete') as complete:
            result = billing.query_balance(config or self.config, self.key)
        complete.assert_not_called()
        self.assertNotIn(self.key, json.dumps(result))
        return result, opener, build

    def test_deepseek_fields_and_fixed_get_destination(self):
        result, opener, build = self.request(self.fixture)
        self.assertEqual(result['status'], 'ok')
        self.assertEqual(result['provider'], 'deepseek')
        self.assertEqual(result['balances'], self.fixture['balance_infos'])
        request = opener.open.call_args.args[0]
        self.assertEqual(request.full_url, 'https://api.deepseek.com/user/balance')
        self.assertEqual(request.get_method(), 'GET')
        self.assertIsNone(request.data)
        self.assertEqual(request.get_header('Authorization'), 'Bearer ' + self.key)
        self.assertEqual(opener.open.call_args.kwargs['timeout'], 25)
        self.assertTrue(any(isinstance(item, self.ai.NoRedirect) for item in build.call_args.args))

    def test_official_complete_endpoints_map_to_fixed_balance_endpoint(self):
        cases = [('https://api.deepseek.com/chat/completions', 'deepseek'),
                 ('https://api.deepseek.com/v1/chat/completions/', 'deepseek'),
                 ('https://openrouter.ai/api/v1/chat/completions', 'openrouter')]
        for base, provider in cases:
            with self.subTest(base=base):
                value = self.fixture if provider == 'deepseek' else {'data':{'total_credits':10,'total_usage':2}}
                result, opener, _ = self.request(value, config={'ai_provider':'api','api_base':base})
                self.assertEqual(result['status'],'ok')
                self.assertEqual(result['provider'],provider)
                expected = 'https://api.deepseek.com/user/balance' if provider == 'deepseek' else 'https://openrouter.ai/api/v1/credits'
                self.assertEqual(opener.open.call_args.args[0].full_url,expected)

    def test_openrouter_returns_account_remaining_credit_in_usd(self):
        config = {'ai_provider': 'api', 'api_base': 'https://openrouter.ai/api/v1/'}
        result, opener, _ = self.request({'data': {'total_credits': 100.25, 'total_usage': 10.20}}, config=config)
        self.assertEqual(result['balances'], [{'currency': 'USD', 'total_balance': '90.05'}])
        self.assertEqual(opener.open.call_args.args[0].full_url, 'https://openrouter.ai/api/v1/credits')
        self.assertNotIn('estimated_cost', result)

    def test_openrouter_rejects_missing_negative_or_nonfinite_counters(self):
        config = {'ai_provider': 'api', 'api_base': 'https://openrouter.ai/api/v1'}
        for data in [{}, {'total_credits': 1}, {'total_credits': -1, 'total_usage': 0},
                {'total_credits': 1, 'total_usage': float('inf')},
                {'total_credits': True, 'total_usage': 0}, {'total_credits': 1, 'total_usage': -1}]:
            with self.subTest(data=data):
                result, _, _ = self.request({'data':data}, config=config)
                self.assertEqual(result['error_code'],'invalid_response')

    def test_unknown_and_nonapi_destinations_never_touch_network(self):
        bases = ['http://api.deepseek.com', 'https://api.deepseek.com.evil.invalid',
            'https://api.deepseek.com@evil.invalid', 'https://evil.invalid/api.deepseek.com',
            'https://api.deepseek.com/v2', 'https://api.deepseek.com/v1?key=secret',
            'https://api.deepseek.com/#secret', 'https://api.deepseek.com:444/v1',
            'https://openrouter.ai/api/v1/credits', 'https://openrouter.ai/v1',
            'https://api.deepseek.com:invalid', 'https://api.deepseek.com/%76%31']
        with patch.object(billing.urllib.request, 'build_opener') as network:
            for base in bases:
                with self.subTest(base=base):
                    self.assertEqual(billing.query_balance({'ai_provider':'api','api_base':base}, self.key)['status'], 'unsupported')
            self.assertEqual(billing.query_balance({'ai_provider':'codex','api_base':bases[0]}, self.key)['status'], 'not_api')
        network.assert_not_called()

    def test_invalid_json_schema_and_numbers_are_not_exposed(self):
        values = [None, [], {}, {'balance_infos': []}, {'balance_infos': [self.key]},
            {'balance_infos':[dict(self.fixture['balance_infos'][0], total_balance=True)]},
            {'balance_infos':[dict(self.fixture['balance_infos'][0], total_balance='NaN')]},
            {'balance_infos':[dict(self.fixture['balance_infos'][0], total_balance='1e100000')]},
            {'balance_infos':[dict(self.fixture['balance_infos'][0], currency=self.key)]}]
        for value in values:
            with self.subTest(value=value):
                result, _, _ = self.request(value)
                self.assertEqual(result['error_code'], 'invalid_response')
        for raw in [b'not json PRIVATE_API_SECRET', b'\xff']:
            result, _, _ = self.request(raw=raw)
            self.assertEqual(result['error_code'], 'invalid_response')
        result, _, _ = self.request(raw=b'x' * (billing.MAX_RESPONSE+1))
        self.assertEqual(result['error_code'], 'response_too_large')

    def test_http_errors_and_redirects_use_finite_private_codes(self):
        for code, expected in [(301,'redirect'),(307,'redirect'),(401,'authentication'),(403,'permission'),(429,'rate_limit'),(503,'server'),(404,'http')]:
            error = urllib.error.HTTPError('https://secret.invalid/' + self.key, code, self.key, {}, io.BytesIO(self.key.encode()))
            result, _, _ = self.request(error=error)
            self.assertEqual(result['error_code'], expected)
            self.assertTrue(error.closed)
        handler = self.ai.NoRedirect()
        self.assertIsNone(handler.redirect_request(None,None,302,'Found',{},'https://evil.invalid'))

    def test_network_errors_never_return_exception_message(self):
        for error, expected in [(TimeoutError(self.key),'timeout'),(socket.gaierror(self.key),'dns'),
                (ssl.SSLError(self.key),'tls'),(ConnectionRefusedError(self.key),'network')]:
            result, _, _ = self.request(error=urllib.error.URLError(error))
            self.assertEqual(result['error_code'], expected)

    def test_missing_or_invalid_key_never_connects(self):
        with patch.object(billing.urllib.request, 'build_opener') as network:
            for key, expected in [('', 'missing_key'), (' ', 'missing_key'), ('secret\r\nInjected: x', 'invalid_key')]:
                self.assertEqual(billing.query_balance(self.config,key)['error_code'], expected)
        network.assert_not_called()

    def test_saved_configuration_uses_shared_secret_helper(self):
        with patch.object(self.chat,'_config',return_value=self.config), \
                patch.object(self.ai,'saved_api_key',create=True,return_value=self.key) as saved, \
                patch.object(billing,'query_balance',return_value={'status':'ok'}) as query:
            self.assertEqual(billing.balance(Path('/fixture')), {'status':'ok'})
        saved.assert_called_once_with(Path('/fixture'),self.config)
        query.assert_called_once_with(self.config,self.key)

    def test_unsupported_saved_configuration_does_not_read_secret(self):
        with patch.object(self.chat,'_config',return_value={'ai_provider':'api','api_base':'https://third-party.invalid/v1'}), \
                patch.object(self.ai,'saved_api_key',create=True) as saved:
            self.assertEqual(billing.balance('/fixture')['status'],'unsupported')
        saved.assert_not_called()

    def test_secret_storage_exception_is_redacted(self):
        with patch.object(self.chat,'_config',return_value=self.config), \
                patch.object(self.ai,'saved_api_key',create=True,side_effect=RuntimeError(self.key)):
            result=billing.balance('/fixture')
        self.assertEqual(result['error_code'],'credentials')
        self.assertNotIn(self.key,json.dumps(result))

if __name__ == '__main__':
    unittest.main()
