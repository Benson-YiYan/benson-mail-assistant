"""JSON-lines transport for the native desktop UI. Never returns credentials."""
import hashlib
import json
import re
import sys
import threading
from pathlib import Path

from . import platform_windows as platform
from .ai_api import complete, identity
from .core import Service, IMAPMailbox, save_json
from .report_index import report_entry, matches


class Controller:
    def __init__(self, directory, emit, launcher=None):
        self.root = Path(directory)
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / 'config.json'
        self.config = json.loads(self.path.read_text(encoding='utf-8')) if self.path.exists() else {}
        self.config.setdefault('ai_provider', 'codex' if self.config.get('codex_command') else 'api')
        self.config.setdefault('interval', 60)
        self.emit = emit
        self.launcher = launcher
        self.service = None
        self.shutting_down = False

    def persist(self):
        save_json(self.path, self.config)

    def active(self):
        return bool(self.service and self.service.thread and self.service.thread.is_alive())

    def paused(self):
        if self.active():
            raise ValueError('请先暂停监听，等当前邮件处理完成后再保存设置。')

    def key_path(self, base):
        return self.root / 'api-keys' / (hashlib.sha256(identity(base).encode()).hexdigest() + '.bin')

    def secret(self):
        account = self.config.get('account', '')
        path = self.root / 'secret.bin'
        return platform.load_secret(path, account) if account and path.exists() else ''

    def api_key(self):
        path = self.key_path(self.config.get('api_base', ''))
        return platform.load_secret(path, identity(self.config['api_base'])) if path.exists() else ''

    def event(self, event):
        if event.get('status') == '已暂停' and not self.shutting_down:
            self.config['enabled'] = False
            self.persist()
        self.emit({'event': event})

    def command(self, name, data):
        if name == 'config':
            if self.launcher and self.config.get('autostart'):
                platform.set_autostart(True, launcher=self.launcher)
            return {**self.config, 'running': self.active(),
                    'output_dir': self.config.get('output_dir') or str(platform.documents_dir() / '邮件'),
                    'has_mail_secret': (self.root / 'secret.bin').exists()}
        if name == 'save_mail':
            self.paused()
            account = data.get('account', '').strip().lower()
            if not re.fullmatch(r'[a-z0-9._%+\-]+@163\.com', account):
                raise ValueError('请输入完整的163邮箱地址，例如 name@163.com。')
            secret = data.get('secret', '')
            if not secret and (account != self.config.get('account') or not self.secret()):
                raise ValueError('请填写 POP3/IMAP/SMTP 授权码。')
            output = data.get('output_dir', '').strip()
            if not output:
                raise ValueError('请选择报告保存文件夹。')
            Path(output).mkdir(parents=True, exist_ok=True)
            if secret:
                platform.save_secret(self.root / 'secret.bin', account, secret)
            platform.set_autostart(bool(data.get('autostart')), launcher=self.launcher)
            self.config.update(account=account, host='imap.163.com', output_dir=output,
                               autostart=bool(data.get('autostart')))
            self.persist()
            return '邮箱设置已保存。'
        if name == 'save_ai':
            self.paused()
            provider = data.get('ai_provider')
            if provider not in ('api', 'codex'):
                raise ValueError('请选择分析方式。')
            base, model = data.get('api_base', '').strip(), data.get('api_model', '').strip()
            if provider == 'api':
                binding = identity(base)
                if not model:
                    raise ValueError('请填写模型名。')
                path = self.key_path(base)
                if data.get('key', '').strip():
                    path.parent.mkdir(parents=True, exist_ok=True)
                    platform.save_secret(path, binding, data['key'].strip())
                elif not path.exists() or not platform.load_secret(path, binding):
                    raise ValueError('请填写此基础地址的 API Key。')
            self.config.update(ai_provider=provider, api_base=base, api_model=model)
            self.persist()
            return 'AI 设置已保存，六项总结提示词保持原样。'
        if name == 'interval':
            seconds = int(data['seconds'])
            if not 10 <= seconds <= 86400:
                raise ValueError('检查间隔应为10至86400秒。')
            self.config['interval'] = seconds
            if self.service:
                self.service.set_interval(seconds)
            self.persist()
            return f'已设置每{seconds}秒检查；无新邮件不调用 AI。'
        if name == 'codex':
            self.paused()
            command = platform.resolve_cli(data['path']) if data.get('path') else platform.discover_codex()
            if not platform.verify_codex(command):
                raise ValueError('未找到可用的 Codex 命令行程序，请选择 resources 下的 codex.exe。')
            self.config['codex_command'] = command
            self.persist()
            return '已配置 Codex 命令行程序。'
        if name == 'test_mail':
            mailbox = IMAPMailbox(self.config, self.secret())
            try:
                mailbox.snapshot()
            finally:
                mailbox.close()
            return '邮箱连接正常。'
        if name == 'test_ai':
            if self.config.get('ai_provider') == 'api':
                complete(self.config['api_base'], self.config['api_model'], self.api_key(),
                         [{'role': 'user', 'content': 'Reply OK.'}])
            else:
                import subprocess
                command = self.config.get('codex_command', [])
                if not platform.verify_codex(command):
                    raise ValueError('请先选择 Codex 命令行程序。')
                result = subprocess.run(command + ['login', 'status'], capture_output=True,
                                        timeout=20, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
                if result.returncode:
                    raise ValueError('请先打开 Codex 并登录。')
            return 'AI 连接正常。'
        if name == 'start':
            if self.active():
                return '监听已在运行。'
            secret = self.secret()
            if not secret or not self.config.get('output_dir'):
                raise ValueError('请先保存邮箱授权码并选择报告文件夹。')
            key = self.api_key() if self.config.get('ai_provider') == 'api' else ''
            if not key and self.config.get('ai_provider') == 'api':
                raise ValueError('请先配置 AI。')
            if self.config.get('ai_provider') == 'codex' and not self.config.get('codex_command'):
                raise ValueError('请先选择 Codex 命令行程序。')
            self.service = Service(dict(self.config), secret, self.root / 'state', self.event, api_key=key)
            self.config['enabled'] = True
            self.persist()
            self.service.start()
            return '已开始监听。'
        if name in ('pause', 'shutdown'):
            self.shutting_down = name == 'shutdown'
            if self.service:
                self.service.stop()
                if name == 'shutdown':
                    self.service.join()
            if name == 'pause':
                self.config['enabled'] = False
            self.persist()
            return '正在停止…' if self.active() else '已暂停'
        if name == 'check':
            if not self.active():
                raise ValueError('请先开始监听。')
            self.service.request_check()
            return '已请求立即检查。'
        if name == 'reports':
            output = self.config.get('output_dir')
            paths = sorted(Path(output).glob('*/*.txt'), key=lambda p: p.stat().st_mtime,
                           reverse=True) if output else []
            entries = []
            for path in paths:
                entry = report_entry(path)
                if matches(entry, data.get('query', ''), data.get('sender', ''),
                           data.get('start', ''), data.get('end', ''), data.get('attachments', '全部')):
                    entries.append({k: str(v) if isinstance(v, Path) else v for k, v in entry.items()
                                    if k != 'searchable'})
            return entries
        if name == 'read_report':
            path = Path(data['path']).resolve()
            output = Path(self.config['output_dir']).resolve()
            if not path.is_relative_to(output) or path.suffix != '.txt':
                raise ValueError('请选择报告列表中的文件。')
            return path.read_text(encoding='utf-8')
        raise ValueError('未知操作。')


def run(launcher=None, fixture=None):
    # PyInstaller console mode provides real redirected pipes.
    sys.stdin.reconfigure(encoding='utf-8')
    sys.stdout.reconfigure(encoding='utf-8')
    lock = threading.Lock()
    def emit(message):
        with lock:
            print(json.dumps(message, ensure_ascii=False), flush=True)
    root = Path(fixture) if fixture else platform.app_dir()
    controller = Controller(root, emit, launcher)
    if fixture:
        output = root / '报告' / '2026-10-17'
        output.mkdir(parents=True, exist_ok=True)
        report = output / '模拟合同检查-09-15.txt'
        report.write_text('1 新邮件提醒\n收到模拟邮件\n2 发件人\n妈妈 <demo@example.invalid>\n'
                          '3 中文摘要\n请检查合同。\n4 具体待办及截止时间\n周五检查并回复。\n'
                          '5 附件实际内容\n合同.pdf：模拟附件文字。\n6 建议回复\n收到，我会检查。', encoding='utf-8')
        save_json(report.with_suffix('.mail.json'), {'subject': '模拟合同检查', 'sender': 'demo@example.invalid',
                  'body': '请检查合同正文', 'received': '2026-10-17T01:15:00+00:00',
                  'attachments': [{'name': '合同.pdf'}]})
        controller.config.update(output_dir=str(output.parent), interval=60)
    try:
        for line in sys.stdin:
            request = {}
            try:
                request = json.loads(line)
                command = request['command']
                if fixture and command not in ('config', 'reports', 'read_report', 'interval', 'shutdown'):
                    raise ValueError('模拟测试禁止访问真实邮件或 AI。')
                result = controller.command(command, request.get('data', {}))
                emit({'id': request['id'], 'ok': True, 'result': result})
                if command == 'shutdown':
                    break
            except Exception as error:
                # Network errors from the API client are already sanitized. Do not echo input.
                detail = str(error) if isinstance(error, (ValueError, RuntimeError)) else f'{type(error).__name__}：操作失败，请检查设置与文件权限。'
                emit({'id': request.get('id'), 'ok': False, 'error': detail})
    finally:
        if controller.service:
            controller.shutting_down = True
            controller.service.stop()
            controller.service.join()
