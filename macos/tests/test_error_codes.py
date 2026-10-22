"""Stable classifications must distinguish local failures from network faults."""
import importlib.util
from pathlib import Path
import socket
import ssl
import sys
import unittest

RUNTIME = Path(__file__).resolve().parents[1] / 'Runtime'
sys.path.insert(0, str(RUNTIME))
from ai_api import connection_error
from runtime_i18n import using_language

class ErrorCodes(unittest.TestCase):
    def test_categories_and_secret_redaction_in_all_languages(self):
        cases = [(FileNotFoundError(2, 'missing'), 'AI_LOCAL_FILE_MISSING'),
                 (PermissionError(13, 'denied'), 'AI_LOCAL_PERMISSION'),
                 (TimeoutError('secret-token'), 'AI_TIMEOUT'),
                 (socket.gaierror(-2, 'lookup failed'), 'AI_DNS'),
                 (ConnectionRefusedError(61, 'refused'), 'AI_CONNECTION_REFUSED'),
                 (ssl.SSLCertVerificationError('certificate'), 'AI_TLS_CERTIFICATE')]
        for language in ['zh', 'en', 'es']:
            with using_language(language):
                for error, code in cases:
                    with self.subTest(language=language, code=code):
                        text = connection_error(error, 'secret-token')
                        self.assertIn(code, text)
                        self.assertNotIn('secret-token', text)
                        if language != 'zh' and code.startswith('AI_LOCAL_'):
                            self.assertNotRegex(text.split('\n')[0], r'[\u3400-\u9fff]')
