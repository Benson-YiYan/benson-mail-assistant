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
from .report_index import report_entry, matches, report_paths
from .report_metadata import read_metadata, write_metadata
from .mailbox_config import PRESETS, normalize, mailbox_id
MAIL_FIELDS = ('account', 'username', 'host', 'port', 'security', 'mail_folder', 'mail_auth',
               'mail_provider', 'secret_binding', 'mail_secret_file', 'proxy_mode', 'proxy_host', 'proxy_port')


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
        from .report_layout import migrate_reports
        try:
            self.report_migration = migrate_reports(self.root, self.config, windows=True)
        except Exception as error:
            # Failed migration must never prevent mailbox settings or old
            # reports from opening. Keep source files intact and show a warning.
            self.report_migration = {'moved': 0, 'skipped': 0,
                                     'errors': [{'source': self.config.get('output_dir', ''),
                                                 'error': type(error).__name__}]}
        self.emit = emit
        self.launcher = launcher
        self.service = None
        self.services = {}
        self.shutting_down = False
        self.prepared_exit = False
        self.config_lock = threading.Lock()
        self.fixture = False
        self.report_entry_cache = {}

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
        if name == 'report_view':
            path = self.root / 'view-preferences.json'
            with self.config_lock:
                try: preferences = json.loads(path.read_text(encoding='utf-8'))
                except (OSError, ValueError): preferences = {}
                if not isinstance(preferences, dict): preferences = {}
                if 'report_tree' in data:
                    if not isinstance(data['report_tree'], bool): raise ValueError('Invalid report tree preference.')
                    preferences['report_tree'] = data['report_tree']
                    save_json(path, preferences)
                return {'report_tree': bool(preferences.get('report_tree', False))}
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
        if name in ('assistant_features', 'reply_draft', 'usage_summary', 'usage_rates', 'usage_balance', 'diagnostics_export', 'history_preview', 'history_start', 'report_sources'):
            from .assistant_tools import dispatch
            request = data if name == 'assistant_features' else {**data, 'action': name}
            if self.fixture and request.get('action') not in ('usage', 'usage_summary', 'usage_rates', 'usage_balance', 'sources', 'report_sources', 'diagnostics', 'diagnostics_export', 'draft_save'):
                raise ValueError('模拟测试禁止访问真实邮件或 AI。')
            return dispatch(self.root, request, self)
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
                    'report_migration': self.report_migration,
                    'has_mail_secret': bool(self.config.get('account')) and self.secret_path().exists()}
        if name in ('policy_status', 'policy_save', 'policy_remove_records', 'policy_summarize_records'):
            from .mail_policy import policy_status, policy_save, policy_remove_records, policy_summarize_records, sender_address
            if name == 'policy_save':
                result = policy_save(self.root, data)
                self.config['mail_policy'] = result['policy']
                self.persist()
                for service in self.all_services():
                    service.config['mail_policy'] = result['policy']
            elif name == 'policy_remove_records':
                result = policy_remove_records(self.root, data.get('ids', []))
            elif name == 'policy_summarize_records':
                # The policy worker drains these durable requests before contacting IMAP.
                # A synthetic fixture can queue records, but never starts a real service.
                result = policy_summarize_records(self.root, data.get('ids', []))
                if not self.fixture:
                    for service in self.all_services():
                        if service.thread and service.thread.is_alive() and not service.cancel.is_set():
                            service.request_check()
            else:
                result = policy_status(self.root)
            senders = set(result.get('senders', []))
            output = self.config.get('output_dir')
            if output:
                for report in report_paths(output):
                    try:
                        message = read_metadata(self.root, report)
                        address = sender_address(message.get('sender') or message.get('from'))
                        if address: senders.add(address)
                    except (OSError, ValueError, AttributeError):
                        continue
            result['senders'] = sorted(senders)
            return result
        if name in ('language_status', 'download_language'):
            from .language_packs import status, download
            if name == 'language_status':
                return status(self.root, 'windows')
            return download(self.root, data.get('code'), 'windows')
        if name in ('validate_settings_page', 'save_settings_page'):
            from .settings_page import validate, commit
            page = data.get('page'); values = data.get('values', {})
            if name == 'validate_settings_page':
                validate(self, page, values)
                return {'valid': True, 'page': page}
            return commit(self, page, values)
        if name == 'save_notifications':
            from .notification_policy import normalize_preferences
            preferences = normalize_preferences({
                'notifications_enabled': data.get('notifications_enabled', self.config.get('notifications_enabled', True)),
                'quiet_hours': data.get('quiet_hours', self.config.get('quiet_hours', {}))})
            self.config.update({key: preferences[key] for key in ('notifications_enabled', 'quiet_hours')})
            self.persist()
            for service in self.all_services():
                service.config.update({key: preferences[key] for key in ('notifications_enabled', 'quiet_hours')})
            return {key: preferences[key] for key in ('notifications_enabled', 'quiet_hours')}
        if name == 'save_language':
            language = data.get('ui_language')
            if language not in ('zh', 'en', 'es'):
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
            from .settings_page import commit
            commit(self, 'mail', data)
            return '邮箱设置已保存。'
        if name == 'harness_detect':
            from .deepseek_harness_ai import discover
            return discover(data.get('path', ''))
        if name == 'save_ai':
            from .settings_page import commit
            commit(self, 'ai', data)
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
        if name == 'codex_detect':
            command = platform.resolve_cli(data['path']) if data.get('path') else platform.discover_codex()
            if not command or not platform.verify_codex(command):
                raise ValueError('未找到可用的 Codex 命令行程序，请选择 resources 下的 codex.exe。')
            return platform.codex_selection_path(command)
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
        if name == 'test_mail_draft':
            # Test the selected UI draft in memory. This path never commits the
            # page, writes a credential, or changes the live monitor settings.
            values = data.get('values', data)
            drafts = values.get('mailboxes')
            selected = values.get('selected_mailbox_id') or values.get('selected_id') or ''
            if not isinstance(drafts, list) or not isinstance(selected, str) or not selected:
                raise ValueError('请选择要测试的邮箱。')
            draft = next((item for item in drafts if isinstance(item, dict) and
                          selected in (item.get('id'), item.get('client_id'), item.get('original_id'))), None)
            if draft is None:
                raise ValueError('找不到当前选中的邮箱草稿。')
            from .mailbox_config import normalize
            connection = normalize({key: value for key, value in draft.items() if key in MAIL_FIELDS})
            secret = draft.get('secret', '')
            if not isinstance(secret, str):
                raise ValueError('邮箱凭据无效。')
            secret = secret.strip()
            if not secret:
                source_id = draft.get('original_id') or draft.get('id') or ''
                # A saved credential is tied to one exact connection identity.
                # If the user edits the account, server, login name, folder or
                # authentication settings, require a new credential instead
                # of silently trying the old one.
                if not source_id or mailbox_id(connection) != source_id:
                    raise ValueError('连接设置已变更；新邮箱草稿请填写密码、授权码或 OAuth2 访问令牌。')
                saved_profiles = self.config.get('mailboxes')
                if saved_profiles is None:
                    saved_profiles = [{**{key: self.config[key] for key in MAIL_FIELDS if key in self.config},
                                       'monitor_enabled': True}] if self.config.get('account') else []
                saved = next((profile for profile in saved_profiles
                              if source_id and mailbox_id(profile) == source_id), None)
                if saved is None:
                    raise ValueError('新邮箱草稿请填写密码、授权码或 OAuth2 访问令牌。')
                secret = self.mailbox_secret(saved)
            if not secret:
                raise ValueError('无法读取该邮箱已保存的凭据；请填写密码、授权码或 OAuth2 访问令牌。')
            connection['ui_language'] = self.config.get('ui_language', 'zh')
            if self.fixture:
                # Fixture UI tests validate selection and staged parsing only;
                # they never access a real network or mailbox.
                return '模拟测试：邮箱草稿已验证，未连接真实邮箱。'
            mailbox = IMAPMailbox(connection, secret)
            try:
                mailbox.snapshot()
            finally:
                mailbox.close()
            return '邮箱连接正常。设置尚未保存。'
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
            paths = sorted(report_paths(output), key=lambda p: p.stat().st_mtime,
                           reverse=True) if output else []
            entries = []
            live = set(paths)
            self.report_entry_cache = {p: v for p, v in self.report_entry_cache.items() if p in live}
            cached_bytes = sum(len(row[1].get('searchable', '')) * 4 for row in self.report_entry_cache.values())
            from .report_metadata import metadata_path
            def stamp(file):
                try:
                    value = file.stat()
                    return (value.st_mtime_ns, value.st_size, value.st_ctime_ns)
                except OSError:
                    return None
            for path in paths:
                signature = (stamp(path), stamp(metadata_path(self.root, path)), stamp(path.with_suffix('.mail.json')))
                cached = self.report_entry_cache.get(path)
                if cached is not None and cached[0] == signature:
                    entry = cached[1]
                else:
                    entry = report_entry(path, self.root)
                    # Bound retained search text; large mailboxes still work without caching every report.
                    previous = self.report_entry_cache.pop(path, None)
                    if previous is not None: cached_bytes -= len(previous[1].get('searchable', '')) * 4
                    cost = len(entry.get('searchable', '')) * 4
                    if len(self.report_entry_cache) < 500 and cached_bytes + cost <= 8 * 1024 * 1024:
                        self.report_entry_cache[path] = (signature, entry)
                        cached_bytes += cost
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
        if name in ('report_retry', 'chat_history', 'chat_send'):
            path = Path(data.get('path', '')).resolve()
            output = Path(self.config.get('output_dir') or self.root / 'reports').resolve()
            if not path.is_relative_to(output) or path.suffix.lower() not in ('.txt', '.md') or not path.is_file():
                raise ValueError('请选择报告列表中的文件。')
            if self.fixture:
                return self.fixture_conversation(name, path, data)
            from .mail_chat import report_retry, chat_history, chat_send
            if name == 'report_retry':
                acquired = []
                try:
                    for service in self.all_services():
                        if not service.activity.acquire(blocking=False):
                            raise ValueError('正在检查或分析邮件，请等当前任务完成后再重新总结。')
                        acquired.append(service.activity)
                    result = report_retry(self.root, path)
                    for service in self.all_services():
                        changed = False
                        for job in service.state.get('pending', {}).values():
                            if job.get('target') and Path(job['target']).resolve() == path:
                                job['answer'] = result['text']
                                changed = True
                        if changed:
                            service.persist()
                    return result
                finally:
                    for lock in reversed(acquired):
                        lock.release()
            if name == 'chat_history':
                return chat_history(self.root, path)
            return chat_send(self.root, path, data.get('text', ''), data.get('files', []))
        raise ValueError('未知操作。')

    def fixture_conversation(self, name, path, data):
        """Exercise the real UI protocol using isolated data, never a model or credentials."""
        language = self.config.get('ui_language', 'zh')
        if name == 'report_retry':
            answer = {'zh': '## 1. 新邮件提醒\n模拟邮件重新总结\n## 2. 谁发的\n演示发件人\n## 3. 说了啥\n模拟内容\n## 4. 我要干什么\n核对\n## 5. 附件里有什么\n模拟合同\n## 6. 建议回复\n收到，谢谢。',
                      'en': '## 1. New email\nSynthetic email summarized again\n## 2. Sender\nDemo\n## 3. Summary\nSynthetic content\n## 4. Actions\nReview\n## 5. Attachments\nSynthetic contract\n## 6. Suggested reply\nReceived, thank you.',
                      'es': '## 1. Correo nuevo\nResumen sintético actualizado\n## 2. Remitente\nDemostración\n## 3. Resumen\nContenido sintético\n## 4. Acciones\nRevisar\n## 5. Adjuntos\nContrato sintético\n## 6. Respuesta sugerida\nRecibido, gracias.'}.get(language, '')
            path.write_text(answer, encoding='utf-8')
            return {'path': str(path), 'text': answer}
        state_path = self.root / 'fixture-chats' / (hashlib.sha256(str(path).encode()).hexdigest() + '.json')
        history = json.loads(state_path.read_text(encoding='utf-8')) if state_path.exists() else {'messages': [], 'compressed': False}
        if name == 'chat_history':
            return history
        text, files = data.get('text', ''), data.get('files', [])
        if not text.strip() and not files:
            raise ValueError('请输入问题或添加文件。')
        for file in files:
            if not Path(file).is_file():
                raise ValueError('附件文件不存在。')
        answer = {'zh': '模拟回答：已参考当前邮件、历史对话和所附文件。',
                  'en': 'Synthetic answer: current email, conversation history and attached files were considered.',
                  'es': 'Respuesta sintética: se han considerado el correo, el historial y los archivos adjuntos.'}.get(language, '')
        history['messages'].extend([{'role': 'user', 'content': text, 'files': [Path(file).name for file in files]},
                                    {'role': 'assistant', 'content': answer}])
        save_json(state_path, history)
        return {**history, 'answer': answer}


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
    controller.fixture = bool(fixture)
    if not fixture and launcher:
        try:
            platform.ensure_portable_shortcuts(launcher, root / 'desktop-shortcut.json')
        except Exception:
            emit({'event': {'detail': '快捷方式创建失败，请检查桌面和开始菜单写入权限；软件仍可正常使用。'}})
    if fixture:
        # Explicit offline-test mode only. No real account or production network access.
        import os
        fixture_packs = os.environ.get('BENSON_MAIL_TEST_LANGUAGE_PACKS')
        if fixture_packs:
            from .language_packs import validate_pack
            directory = root / 'languages'; directory.mkdir(exist_ok=True)
            for code in ('zh', 'en', 'es'):
                data = (Path(fixture_packs) / (code + '.json')).read_bytes()
                validate_pack(data, code, 'windows')
                (directory / (code + '.json')).write_bytes(data)
        # Fixture saves use real validation, persistence and protected synthetic credentials,
        # but must never touch the signed-in user's startup registration.
        platform.set_autostart = lambda *args, **kwargs: None
        output = root / '报告' / '2026-10-17'
        output.mkdir(parents=True, exist_ok=True)
        report = output / '模拟合同检查-09-15.txt'
        report.write_text('1 新邮件提醒\n收到模拟邮件\n2 发件人\n妈妈 <demo@example.invalid>\n'
                          '3 中文摘要\n请检查合同。\n4 具体待办及截止时间\n周五检查并回复。\n'
                          '5 附件实际内容\n合同.pdf：模拟附件文字。\n6 建议回复\n收到，我会检查。', encoding='utf-8')
        write_metadata(root, report, {'subject': '模拟合同检查', 'sender': 'demo@example.invalid',
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
                if fixture and command not in ('validate_settings_page', 'save_settings_page', 'assistant_features', 'config', 'report_view', 'reports', 'read_report', 'report_retry', 'chat_history', 'chat_send', 'policy_status', 'policy_save', 'policy_remove_records', 'policy_summarize_records', 'interval', 'shutdown', 'runtime_info', 'mail_presets', 'select_mail', 'save_mail', 'save_language', 'save_notifications', 'language_status', 'prepare_exit', 'resume_after_exit_cancel', 'test_mail_draft'):
                    raise ValueError('模拟测试禁止访问真实邮件或 AI。')
                result = controller.command(command, request.get('data', {}))
                emit({'id': request['id'], 'ok': True, 'result': result})
                if command == 'shutdown':
                    break
            except Exception as error:
                from .assistant_tools import record_diagnostic
                try: record_diagnostic(controller.root, command, error)
                except Exception: pass
                # Network errors from the API client are already sanitized. Do not echo input.
                detail = str(error) if isinstance(error, (ValueError, RuntimeError)) else f'{type(error).__name__}：操作失败，请检查设置与文件权限。'
                emit({'id': request.get('id'), 'ok': False, 'error': detail})
    finally:
        controller.shutting_down = True
        for service in controller.all_services():
            service.stop()
        for service in controller.all_services():
            service.join()
