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
from .mailbox_config import PRESETS, normalize, mailbox_id
MAIL_FIELDS = ('account', 'username', 'host', 'port', 'security', 'mail_folder', 'mail_auth',
               'mail_provider', 'secret_binding', 'mail_secret_file')


class Controller:
    def __init__(self, directory, emit, launcher=None):
        self.root = Path(directory)
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / 'config.json'
        self.config = json.loads(self.path.read_text(encoding='utf-8')) if self.path.exists() else {}
        self.config.setdefault('ai_provider', 'codex' if self.config.get('codex_command') else 'api')
        self.config.setdefault('interval', 60)
        if not self.config.get('account') and self.config.get('mailboxes'):
            self.config.update({k: self.config['mailboxes'][0][k] for k in MAIL_FIELDS if k in self.config['mailboxes'][0]})
        self.emit = emit
        self.launcher = launcher
        self.service = None
        self.services = {}
        self.shutting_down = False
        self.prepared_exit = False
        self.config_lock = threading.Lock()

    def persist(self):
        with self.config_lock:
            save_json(self.path, dict(self.config))

    def active(self):
        return any(s.thread and s.thread.is_alive() for s in self.all_services())

    def all_services(self):
        return list({id(s): s for s in [self.service, *self.services.values()] if s is not None}.values())

    def profiles(self):
        if 'mailboxes' not in self.config:
            self.config['mailboxes'] = (
                [{**{k: self.config[k] for k in MAIL_FIELDS if k in self.config}, 'monitor_enabled': True}]
                if self.config.get('account') else [])
        return self.config['mailboxes']

    def mailbox_secret(self, config):
        path = self.root / config.get('mail_secret_file', 'secret.bin')
        if not path.resolve().is_relative_to(self.root.resolve()):
            raise ValueError('邮箱密钥路径无效。')
        return platform.load_secret(path, config.get('secret_binding') or config['account']) if path.exists() else ''

    def start_profile(self, profile, key):
        identifier = mailbox_id(profile)
        existing = self.services.get(identifier)
        if existing and existing.thread and existing.thread.is_alive():
            if existing.cancel.is_set():
                raise ValueError('监听正在停止，请稍候再开始。')
            return
        config = {**self.config, **profile}
        secret = self.mailbox_secret(config)
        if not secret:
            raise ValueError('请先保存该邮箱的登录凭据。')
        def event(value):
            value = {**value, 'mailbox_id': identifier, 'account': profile['account']}
            if value.get('detail'):
                value['detail'] = profile['account'] + ' · ' + value['detail']
            if value.get('status') == '已暂停' and any(
                    key != identifier and s.thread and s.thread.is_alive() and not s.cancel.is_set()
                    for key, s in self.services.items()):
                value['status'] = '运行中'
            self.emit({'event': value})
        service = Service(config, secret, self.root / 'state', event, api_key=key)
        self.services[identifier] = service
        self.service = service
        service.start()

    def paused(self):
        if self.active():
            raise ValueError('请先暂停监听，等当前邮件处理完成后再保存设置。')

    def key_path(self, base):
        return self.root / 'api-keys' / (hashlib.sha256(identity(base).encode()).hexdigest() + '.bin')

    def secret(self):
        account = self.config.get('account', '')
        path = self.secret_path()
        return platform.load_secret(path, self.config.get('secret_binding') or account) if account and path.exists() else ''

    def secret_path(self):
        path = self.root / self.config.get('mail_secret_file', 'secret.bin')
        if not path.resolve().is_relative_to(self.root.resolve()):
            raise ValueError('邮箱密钥路径无效。')
        return path

    def api_key(self):
        path = self.key_path(self.config.get('api_base', ''))
        return platform.load_secret(path, identity(self.config['api_base'])) if path.exists() else ''

    def event(self, event):
        if event.get('status') == '已暂停' and not self.shutting_down:
            self.config['enabled'] = False
            self.persist()
        self.emit({'event': event})

    def command(self, name, data):
        if self.prepared_exit and name not in ('shutdown', 'resume_after_exit_cancel', 'config', 'reports', 'read_report', 'runtime_info'):
            raise ValueError('正在准备退出，请稍候。')
        if name == 'prepare_exit':
            services = self.all_services()
            acquired = []
            resume = self.active()
            try:
                for service in services:
                    if not service.activity.acquire(blocking=False):
                        raise ValueError('正在检查或分析邮件，请等当前任务完成后再更新或卸载。没有中断任务，也没有启动安装程序。')
                    acquired.append(service.activity)
                # All activity locks are held before stopping any service. A new check cannot race this gate.
                self.shutting_down = True
                for service in services: service.stop()
                self.prepared_exit = True
            finally:
                for lock in reversed(acquired): lock.release()
            for service in services: service.join()
            return {'prepared': True, 'resume': resume}
        if name == 'resume_after_exit_cancel':
            self.prepared_exit = False
            self.shutting_down = False
            return self.command('start', {}) if data.get('resume') else '已取消退出。'
        if name == 'runtime_info':
            import ctypes
            from ctypes import wintypes
            ctypes.windll.kernel32.GetConsoleWindow.restype = wintypes.HWND
            ctypes.windll.user32.IsWindowVisible.argtypes = [wintypes.HWND]
            console = ctypes.windll.kernel32.GetConsoleWindow()
            return {'console_visible': bool(console and ctypes.windll.user32.IsWindowVisible(console))}
        if name == 'config':
            if self.launcher and self.config.get('autostart'):
                platform.set_autostart(True, launcher=self.launcher)
            return {**self.config, 'mailboxes': [{**p, 'id': mailbox_id(p)} for p in self.profiles()], 'running': self.active(),
                    'selected_mailbox_id': mailbox_id(self.config) if self.config.get('account') else '',
                    'output_dir': self.config.get('output_dir') or str(platform.documents_dir() / '邮件'),
                    'has_mail_secret': bool(self.config.get('account')) and self.secret_path().exists()}
        if name == 'save_language':
            language = data.get('ui_language')
            if language not in ('zh', 'en'):
                raise ValueError('Invalid interface language')
            self.config['ui_language'] = language
            self.persist()
            for service in self.all_services():
                service.config['ui_language'] = language
                if hasattr(service.analyzer, 'config'):
                    service.analyzer.config['ui_language'] = language
            return language
        if name == 'mail_presets':
            return PRESETS
        if name == 'select_mail':
            profiles = self.profiles()
            selected = next((p for p in profiles if mailbox_id(p) == data.get('id')), None)
            if data.get('id') and selected is None:
                raise ValueError('找不到此邮箱。')
            for field in MAIL_FIELDS:
                self.config.pop(field, None)
            if selected:
                self.config.update({k: selected[k] for k in MAIL_FIELDS if k in selected})
            self.persist()
            return '已选择邮箱。' if selected else '请填写新邮箱；已有邮箱继续保留。'
        if name in ('mail_enabled', 'remove_mail'):
            profile = next((p for p in self.profiles() if mailbox_id(p) == data.get('id')), None)
            if profile is None:
                raise ValueError('找不到此邮箱。')
            identifier = mailbox_id(profile)
            service = self.services.get(identifier)
            if service:
                service.stop()
                service.join()
            if name == 'remove_mail':
                self.config['mailboxes'].remove(profile)
                if self.config.get('account') and mailbox_id(self.config) == identifier:
                    for field in MAIL_FIELDS:
                        self.config.pop(field, None)
                    if self.profiles():
                        self.config.update({k: self.profiles()[0][k] for k in MAIL_FIELDS if k in self.profiles()[0]})
            else:
                profile['monitor_enabled'] = bool(data['enabled'])
                if profile['monitor_enabled'] and self.config.get('enabled'):
                    key = self.api_key() if self.config.get('ai_provider') == 'api' else ''
                    self.start_profile(profile, key)
            self.persist()
            return '已移除邮箱，历史报告保留。' if name == 'remove_mail' else '已更新此邮箱监听状态。'
        if name == 'save_mail':
            self.paused()
            profiles = self.profiles()
            previous_id = mailbox_id(self.config) if self.config.get('account') else None
            connection = normalize(data)
            if any(mailbox_id(p) == mailbox_id(connection) and mailbox_id(p) != previous_id for p in profiles):
                raise ValueError('这个邮箱连接已存在，请从已添加邮箱中选择。')
            account = connection['account']
            secret = data.get('secret', '')
            changed = not self.config.get('account') or mailbox_id(connection) != mailbox_id(self.config)
            if not secret and (changed or not self.secret()):
                raise ValueError('新邮箱或连接设置变更后，请重新填写密码、授权码或 OAuth2 访问令牌。')
            output = data.get('output_dir', '').strip()
            if not output:
                raise ValueError('请选择报告保存文件夹。')
            Path(output).mkdir(parents=True, exist_ok=True)
            if secret:
                binding = 'mailbox:' + mailbox_id(connection)
                relative = 'mail-secrets/' + mailbox_id(connection) + '.bin'
                path = self.root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                platform.save_secret(path, binding, secret)
                self.config['secret_binding'] = binding
                self.config['mail_secret_file'] = relative
            platform.set_autostart(bool(data.get('autostart')), launcher=self.launcher)
            self.config.update(**connection, output_dir=output,
                               autostart=bool(data.get('autostart')))
            was_enabled = next((p.get('monitor_enabled', True) for p in profiles if mailbox_id(p) == previous_id), True)
            saved = {**{k: self.config[k] for k in MAIL_FIELDS if k in self.config}, 'monitor_enabled': was_enabled}
            self.config['mailboxes'] = [p for p in profiles if mailbox_id(p) != previous_id] + [saved]
            self.persist()
            return '邮箱设置已保存。'
        if name == 'harness_detect':
            from .deepseek_harness_ai import discover
            return discover(data.get('path', ''))
        if name == 'save_ai':
            self.paused()
            provider = data.get('ai_provider')
            if provider not in ('api', 'codex', 'deepseek_harness'):
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
            if provider == 'deepseek_harness':
                from .deepseek_harness_ai import discover
                discover(data.get('harness_path', ''))
            self.config.update(ai_provider=provider, api_base=base, api_model=model, harness_path=data.get('harness_path', '').strip())
            self.persist()
            return 'AI 设置已保存，六项总结提示词保持原样。'
        if name == 'interval':
            seconds = int(data['seconds'])
            if not 10 <= seconds <= 86400:
                raise ValueError('检查间隔应为10至86400秒。')
            self.config['interval'] = seconds
            for service in self.all_services():
                service.set_interval(seconds)
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
            if self.config.get('ai_provider') == 'deepseek_harness':
                from .deepseek_harness_ai import complete as harness_complete
                harness_complete(messages=[{'role': 'user', 'content': 'Reply OK.'}], cli_path=self.config.get('harness_path', ''))
            elif self.config.get('ai_provider') == 'api':
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
                if self.service.cancel.is_set():
                    raise ValueError('监听正在停止，请稍候再开始。')
                return '监听已在运行。'
            profiles = [p for p in self.profiles() if p.get('monitor_enabled', True)]
            if not profiles or not self.config.get('output_dir'):
                raise ValueError('请先保存邮箱授权码并选择报告文件夹。')
            key = self.api_key() if self.config.get('ai_provider') == 'api' else ''
            if not key and self.config.get('ai_provider') == 'api':
                raise ValueError('请先配置 AI。')
            if self.config.get('ai_provider') == 'deepseek_harness':
                from .deepseek_harness_ai import discover
                discover(self.config.get('harness_path', ''))
            if self.config.get('ai_provider') == 'codex' and not self.config.get('codex_command'):
                raise ValueError('请先选择 Codex 命令行程序。')
            for profile in profiles:
                if not self.mailbox_secret(profile):
                    raise ValueError('请补充所有启用邮箱的登录凭据。')
            self.config['enabled'] = True
            self.persist()
            for profile in profiles:
                self.start_profile(profile, key)
            return '已开始监听。'
        if name in ('pause', 'shutdown'):
            self.shutting_down = name == 'shutdown'
            for service in self.all_services():
                service.stop()
            if name == 'shutdown':
                for service in self.all_services():
                    service.join()
            if name == 'pause':
                self.config['enabled'] = False
            self.persist()
            return '正在停止…' if self.active() else '已暂停'
        if name == 'check':
            if not self.active():
                raise ValueError('请先开始监听。')
            for service in self.all_services():
                if not service.cancel.is_set():
                    service.request_check()
            return '已请求立即检查。'
        if name == 'reports':
            output = self.config.get('output_dir')
            paths = sorted((p for p in Path(output).glob('*/*') if p.suffix.lower() in ('.txt', '.md')), key=lambda p: p.stat().st_mtime,
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
            if not path.is_relative_to(output) or path.suffix.lower() not in ('.txt', '.md'):
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
    if not fixture and launcher:
        try:
            platform.ensure_portable_shortcuts(launcher, root / 'desktop-shortcut.json')
        except Exception:
            emit({'event': {'detail': '快捷方式创建失败，请检查桌面和开始菜单写入权限；软件仍可正常使用。'}})
    if fixture:
        # Fixture saves use real validation, persistence and protected synthetic credentials,
        # but must never touch the signed-in user's startup registration.
        platform.set_autostart = lambda *args, **kwargs: None
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
        fixture_profiles = [normalize({'account': 'first@example.invalid', 'host': 'imap.first.invalid'}),
                            normalize({'account': 'second@example.invalid', 'host': 'imap.second.invalid'})]
        controller.config.update(mailboxes=[{**p, 'monitor_enabled': True} for p in fixture_profiles],
                                 **fixture_profiles[0])
    try:
        for line in sys.stdin:
            request = {}
            try:
                request = json.loads(line)
                command = request['command']
                if fixture and command not in ('config', 'reports', 'read_report', 'interval', 'shutdown', 'runtime_info', 'mail_presets', 'select_mail', 'save_mail', 'save_language', 'prepare_exit', 'resume_after_exit_cancel'):
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
        controller.shutting_down = True
        for service in controller.all_services():
            service.stop()
        for service in controller.all_services():
            service.join()
