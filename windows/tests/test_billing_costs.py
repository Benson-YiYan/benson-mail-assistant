"""Billing records must retain provenance, currency and incomplete coverage."""
import json
import hashlib
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

WINDOWS = Path(__file__).resolve().parents[1].name == 'windows'
if WINDOWS:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from benson_mail import assistant_tools as tools, ai_api
else:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'Runtime'))
    import assistant_tools as tools
    import ai_api


class BillingCostTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.base = 'https://openrouter.ai/api/v1'
        config = {'api_base': self.base, 'api_model': 'model', 'ai_provider': 'api'}
        (self.root / ('config.json' if WINDOWS else 'settings.json')).write_text(json.dumps(config))

    def record(self, usage, base=None):
        tools.record_usage('api', 'model', usage, root=self.root, base=base or self.base)

    def test_actual_preferred_per_call_and_estimates_not_double_counted(self):
        tools.usage_rates(self.root, {'input_per_million': 2, 'output_per_million': 6, 'currency': 'CNY'})
        self.record({'prompt_tokens': 1000000, 'completion_tokens': 0, 'cost': 0.03})
        self.record({'prompt_tokens': 1000000, 'completion_tokens': 500000})
        self.record({})
        value = tools.usage_summary(self.root)
        self.assertEqual(value['actual_cost'], .03)
        self.assertEqual(value['actual_currency'], 'USD')
        self.assertEqual(value['actual_cost_calls'], 1)
        self.assertEqual(value['estimated_cost'], 5)
        self.assertEqual(value['currency'], 'CNY')
        self.assertEqual(value['estimated_cost_calls'], 1)
        self.assertEqual(value['unknown_cost_calls'], 1)
        self.assertEqual(sum(group['calls'] for group in value['groups']), 3)
        self.assertEqual(value['records'][-1]['cost_source'], 'openrouter_usage')

    def test_actual_zero_and_missing_tokens_are_independent(self):
        self.record({'cost': 0})
        result = tools.usage_summary(self.root)
        self.assertEqual(result['actual_cost'], 0)
        self.assertEqual(result['actual_cost_calls'], 1)
        self.assertEqual(result['unknown_cost_calls'], 0)
        self.assertEqual(result['unknown_usage_calls'], 1)
        self.assertIsNone(result['input_tokens'])
        self.assertIsNone(result['estimated_cost'])

    def test_generic_cost_requires_explicit_currency(self):
        base = 'https://gateway.example.invalid/v1'
        self.record({'cost': .4}, base)
        self.record({'cost': .7, 'cost_currency': 'eur'}, base)
        self.record({'cost': {'amount': '.2', 'currency': 'CNY'}}, base)
        result = tools.usage_summary(self.root)
        self.assertEqual(result['actual_cost_calls'], 2)
        self.assertEqual(result['unknown_cost_calls'], 1)
        self.assertIsNone(result['actual_cost'])
        self.assertIsNone(result['actual_currency'])
        self.assertEqual({item['currency'] for item in result['actual_by_currency']}, {'EUR', 'CNY'})

    def test_invalid_and_ambiguous_charges_stay_unknown(self):
        for cost in (None, True, -1, 'NaN', float('inf'), {}, [], 'not money', 10**20):
            with self.subTest(cost=cost):
                self.assertIsNone(tools._upstream_cost({'cost': cost}, self.base))
        for base in ('https://openrouter.ai.evil.invalid/api/v1', 'http://openrouter.ai/api/v1',
                     'https://openrouter.ai:8443/api/v1', 'https://user@openrouter.ai/api/v1',
                     'https://openrouter.ai/api/v1?api_key=private', 'https://openrouter.ai/other'):
            with self.subTest(base=base):
                self.assertIsNone(tools._upstream_cost({'cost': .1}, base))
        for currency in ('private-account', 'US', 'USD\n', None):
            self.assertIsNone(tools._upstream_cost({'cost': 1, 'cost_currency': currency}, 'https://gateway.invalid'))

    def test_existing_database_upgrades_without_repricing_history(self):
        connection = sqlite3.connect(self.root / 'usage.sqlite3')
        connection.execute('CREATE TABLE calls (at TEXT, provider TEXT, model TEXT, input_tokens INTEGER, output_tokens INTEGER, cost REAL, currency TEXT)')
        connection.execute("INSERT INTO calls VALUES ('old', 'api', 'model', 5, 6, 0.4, 'USD')")
        connection.commit()
        connection.close()
        self.record({'cost': .1, 'prompt_tokens': 7, 'completion_tokens': 8})
        result = tools.usage_summary(self.root)
        self.assertEqual(result['calls'], 2)
        self.assertEqual(result['actual_cost'], .1)
        self.assertEqual(result['estimated_cost'], .4)
        self.assertEqual(result['records'][-1]['at'], 'old')
        self.assertIsNone(result['records'][-1]['actual_cost'])

    def test_actual_usage_survives_api_adapter_without_content_or_key_storage(self):
        response = Mock()
        response.read.return_value = json.dumps({
            'choices': [{'message': {'content': 'PRIVATE_REPLY'}}],
            'usage': {'cost': .015, 'prompt_tokens': 30, 'completion_tokens': 4}
        }).encode()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        opener = Mock()
        opener.open.return_value = response
        with patch.object(tools, '_root', return_value=self.root), patch.object(ai_api.urllib.request, 'build_opener', return_value=opener):
            answer = ai_api.complete(self.base, 'model', 'PRIVATE_KEY', [{'role': 'user', 'content': 'PRIVATE_MAIL'}])
        self.assertEqual(answer, 'PRIVATE_REPLY')
        self.assertEqual(tools.usage_summary(self.root)['actual_cost'], .015)
        for secret in (b'PRIVATE_KEY', b'PRIVATE_MAIL', b'PRIVATE_REPLY'):
            self.assertNotIn(secret, (self.root / 'usage.sqlite3').read_bytes())

    def test_fixture_balance_never_reads_saved_credentials_or_network(self):
        with patch.object(tools, 'usage_balance') as balance:
            result = tools.dispatch(self.root, {'action': 'usage_balance'}, Mock(fixture=True))
        self.assertEqual(result['status'], 'unsupported')
        balance.assert_not_called()

    def test_balance_key_uses_existing_saved_endpoint_binding(self):
        config = {'api_base': self.base}
        binding = ai_api.identity(self.base)
        if WINDOWS:
            from benson_mail import platform_windows
            path = self.root / 'api-keys' / (hashlib.sha256(binding.encode()).hexdigest() + '.bin')
            path.parent.mkdir()
            path.write_bytes(b'synthetic encrypted secret')
            with patch.object(platform_windows, 'load_secret', return_value='synthetic') as read:
                self.assertEqual(ai_api.saved_api_key(self.root, config), 'synthetic')
            read.assert_called_once_with(path, binding)
        else:
            result = Mock(returncode=0, stdout='synthetic\n')
            with patch.object(ai_api.subprocess, 'run', return_value=result) as read:
                self.assertEqual(ai_api.saved_api_key(self.root, config), 'synthetic')
            arguments = read.call_args.args[0]
            self.assertEqual(arguments[0], '/usr/bin/security')
            self.assertEqual(arguments[arguments.index('-a') + 1], binding)
            self.assertEqual(arguments[arguments.index('-s') + 1], 'BensonMail-AI-API')


if __name__ == '__main__':
    unittest.main()
