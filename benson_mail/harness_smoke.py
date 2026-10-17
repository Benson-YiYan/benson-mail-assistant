"""Local-only synthetic smoke check for the bundled official Harness runtime."""
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import threading
from .deepseek_harness_ai import complete

def run():
    requests = []
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            requests.append((self.path, body))
            chunks = [
                {'id': 'chatcmpl_test', 'object': 'chat.completion.chunk', 'model': 'deepseek-v4-flash',
                 'choices': [{'index': 0, 'delta': {'role': 'assistant', 'content': '六项邮件报告完成'}, 'finish_reason': None}]},
                {'id': 'chatcmpl_test', 'object': 'chat.completion.chunk', 'model': 'deepseek-v4-flash',
                 'choices': [{'index': 0, 'delta': {}, 'finish_reason': 'stop'}],
                 'usage': {'prompt_tokens': 10, 'completion_tokens': 10, 'total_tokens': 20}},
            ]
            data = (''.join('data: ' + json.dumps(value) + '\n\n' for value in chunks)
                    + 'data: [DONE]\n\n').encode()
            self.send_response(200)
            self.send_header('Content-Type', 'text/event-stream')
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        result = complete(f'http://127.0.0.1:{server.server_port}',
                          'deepseek-v4-flash', 'synthetic-key',
                          [{'role': 'system', 'content': '原提示词逐字保持'},
                           {'role': 'user', 'content': '模拟邮件正文'}])
        assert result == '六项邮件报告完成'
        assert requests
        path, request = requests[0]
        assert path.endswith('/chat/completions'), path
        assert not request.get('tools'), 'Mail analysis must not enable agent tools'
        assert '原提示词逐字保持' in json.dumps(request['messages'], ensure_ascii=False)
        assert '模拟邮件正文' in json.dumps(request['messages'], ensure_ascii=False)
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
    return {"ok": True, "checks": ["bundled official Harness process and streaming response", "original prompt and body preserved", "agent tools disabled; synthetic localhost endpoint only"]}
