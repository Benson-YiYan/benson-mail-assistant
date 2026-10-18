"""Synthetic packaged-worker integration test. No mailbox or real AI/keychain."""
import hashlib
import json
import os
from pathlib import Path
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from unittest.mock import patch
import contextlib
import io
import runpy
import sys
from email.message import EmailMessage

def reader_test(home):
    """Execute the actual reader with synthetic IMAP and keychain boundaries."""
    from mailbox_config import mailbox_id
    connection = {'account': 'demo@example.invalid', 'host': 'mail.example.invalid',
                  'port': 1993, 'security': 'ssl', 'username': 'synthetic-login',
                  'mail_folder': 'Archive', 'mail_auth': 'password'}
    class Box:
        uids = [1]
        def response(self, name): return name, [b'42']
        def uid(self, command, *args):
            if command == 'search': return 'OK', [' '.join(map(str, self.uids)).encode()]
            message = EmailMessage()
            message['From'] = 'synthetic@example.invalid'; message['Subject'] = '模拟其他邮箱'
            message.set_content('SYNTHETIC_IMAP_BODY')
            return 'OK', [(b'2 (INTERNALDATE "17-Oct-2026 08:00:00 +0800")', message.as_bytes())]
        def logout(self): pass
    box = Box()
    base = home / 'reader-fixture'
    def execute(*args):
        output = io.StringIO()
        with patch.object(sys, 'argv', ['mail_watch', *args]), contextlib.redirect_stdout(output):
            code = 0
            try: runpy.run_module('mail_watch', run_name='__main__')
            except SystemExit as error: code = error.code or 0
        return code, json.loads(output.getvalue().strip())
    with patch.dict(os.environ, {'BENSON_MAIL_HOME': str(base)}), \
         patch('mail_connection_io.load', return_value=(connection, 'SYNTHETIC')), \
         patch('mailbox_config.connect', return_value=box) as transport:
        code, result = execute()
        assert code == 0 and result['initialized']
        assert transport.call_args.args[0]['host'] == 'mail.example.invalid'
        box.uids = [1, 2]
        code, result = execute()
        assert code == 0 and result['pending_messages'] == 1
        message = json.loads(Path(result['report']).read_text())[0]
        assert message['mailbox_key'] == mailbox_id(connection)
        assert 'SYNTHETIC_IMAP_BODY' in message['bodies'][0]['text']
        code, result = execute('ack', '2')
        assert code == 0 and json.loads((base/'mail_watch/state.json').read_text())['pending'] == []
        before = (base/'mail_watch/state.json').read_bytes()
        connection['mail_folder'] = 'Different-folder'
        code, result = execute()
        assert code == 1 and '不匹配' in result['detail']
        assert (base/'mail_watch/state.json').read_bytes() == before

def run():
    from runtime_paths import data_home
    from mail_prompt import ANALYSIS_PROMPT, ENGLISH_ANALYSIS_PROMPT
    import mail_daemon as daemon
    import ai_runner
    from pypdf import PdfWriter
    home = data_home()
    assert home.name.startswith('BensonMail-package-test-'), 'isolated fixture required'
    checks = []
    assert '## 1. 新邮件提醒' in ANALYSIS_PROMPT
    for number in range(1, 7): assert f'\n{number}. ' in ANALYSIS_PROMPT
    checks.append('Markdown format selected and original six report requirements retained')
    reader_test(home)
    checks.append('actual frozen reader baselines a custom mailbox, detects new UID, reads body, acknowledges and rejects mixed mailbox state')
    folder = home / 'mail_watch/101'
    folder.mkdir(parents=True, exist_ok=True)
    attachment = folder / 'contract.txt'
    attachment.write_text('SYNTHETIC_ATTACHMENT_TEXT_101', encoding='utf-8')
    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    pdf = folder / 'blank.pdf'
    writer.write(pdf)
    assert '扫描PDF' in ai_runner.attachment_text(pdf, folder)
    checks.append('bundled PDF reader available without external PDF tools')
    requests = []
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            requests.append(json.loads(self.rfile.read(int(self.headers['Content-Length']))))
            answer = '1 新邮件提醒\n2 发件人：演示\n3 摘要：模拟合同\n4 待办：核对\n5 附件：模拟文字\n6 建议回复：收到'
            body = json.dumps({'choices': [{'message': {'content': answer}, 'finish_reason': 'stop'}]}).encode()
            self.send_response(200); self.end_headers(); self.wfile.write(body)
        def log_message(self, *args): pass
    server = HTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    output = home / 'reports'
    config = {'enabled': True, 'ai_provider': 'api', 'api_base': f'http://127.0.0.1:{server.server_port}/v1',
              'api_model': 'synthetic', 'output_dir': str(output)}
    (home / 'settings.json').write_text(json.dumps(config))
    (home / 'mail_watch/state.json').write_text('{"pending":[101]}')
    message = {'uid': 101, 'subject': '模拟独立安装邮件', 'from': 'demo@example.invalid',
               'received_at': '2026-10-17T00:00:00+00:00',
               'bodies': [{'type': 'text/plain', 'text': 'SYNTHETIC_BODY'}],
               'attachments': [{'filename': 'contract.txt', 'path': str(attachment)}]}
    try:
        with patch.object(ai_runner, 'api_config', return_value=(config, 'SYNTHETIC_KEY')), \
             patch.object(daemon, 'run_reader', return_value={}) as ack, \
             patch.object(daemon, 'notify'):
            daemon.analyze(message)
            assert ack.call_args.args == ('ack', '101')
            daemon.analyze(message)
        assert len(requests) == 1
        assert requests[0]['messages'][0]['content'] == ANALYSIS_PROMPT
        assert 'SYNTHETIC_ATTACHMENT_TEXT_101' in requests[0]['messages'][1]['content']
        report = output / '2026-10-17/模拟独立安装邮件-08-00.md'
        assert report.exists() and '6 建议回复' in report.read_text()
        checks.append('packaged API pipeline extracts real attachment text and preserves six-part prompt')
        checks.append('frozen exporter subprocess writes date folders and Markdown; cached retries avoid duplicate AI')
        before = report.read_bytes()
        config['ui_language'] = 'en'
        (home / 'settings.json').write_text(json.dumps(config))
        with patch.object(ai_runner, 'api_config', return_value=(config, 'SYNTHETIC_KEY')), patch.object(daemon, 'run_reader', return_value={}), patch.object(daemon, 'notify'):
            daemon.analyze(message)
            assert len(requests) == 1 and report.read_bytes() == before
            ai_runner.analyze_api(message, folder)
        assert len(requests) == 2 and requests[-1]['messages'][0]['content'] == ENGLISH_ANALYSIS_PROMPT
        assert 'SYNTHETIC_ATTACHMENT_TEXT_101' in requests[-1]['messages'][1]['content']
        checks.append('frozen English prompt follows persisted language; cached existing report is unchanged with no AI recall')

    finally:
        server.shutdown(); server.server_close()
    print(json.dumps({'ok': True, 'checks': checks}, ensure_ascii=False))
