import json
import ssl
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import trustme
from benson_mail.ai_api import complete, tls_context


class TLSTests(unittest.TestCase):
    def test_bundle_has_roots_and_verification_stays_enabled(self):
        context = tls_context()
        self.assertTrue(context.check_hostname)
        self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)
        self.assertGreaterEqual(context.minimum_version, ssl.TLSVersion.TLSv1_2)

    def test_https_valid_chain_untrusted_chain_and_hostname(self):
        ca = trustme.CA()
        intermediate = ca.create_child_ca()
        certificate = intermediate.issue_cert('localhost')
        requests = []

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_):
                pass

            def do_POST(self):
                requests.append(json.loads(self.rfile.read(int(self.headers['Content-Length']))))
                self.send_response(200)
                self.end_headers()
                self.wfile.write(json.dumps({'choices': [{'message': {'content': 'TLS 报告'}}]}).encode())

        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        certificate.configure_cert(context)
        server.socket = context.wrap_socket(server.socket, server_side=True)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            url = f'https://localhost:{server.server_port}/v1'
            with self.assertRaisesRegex(RuntimeError, '证书'):
                complete(url, 'synthetic', 'synthetic-key', [])
            self.assertEqual(requests, [], 'No API payload may reach an untrusted server')
            with tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary) / 'ca.pem'
                ca.cert_pem.write_to_path(root)
                with patch('certifi.where', return_value=str(root)):
                    self.assertEqual(complete(url, 'synthetic', 'synthetic-key', []), 'TLS 报告')
                    with self.assertRaisesRegex(RuntimeError, '证书'):
                        complete(f'https://127.0.0.1:{server.server_port}/v1', 'synthetic', 'synthetic-key', [])
                self.assertEqual(len(requests), 1)
        finally:
            server.shutdown()
            server.server_close()
            worker.join()
