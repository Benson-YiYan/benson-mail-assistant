"""Load only the selected mailbox credential from macOS Keychain."""
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from runtime_paths import data_home
from mailbox_config import normalize, connect, MailConnectionError, mail_error, redact_mail_error


def load_managed_credential(config):
    service = str(config.get('secret_service', 'BensonMail-IMAP'))
    account = str(config.get('secret_account', ''))
    if service not in ('Codex-Mail-163', 'BensonMail-IMAP') or not account:
        raise ValueError('OAuth 邮箱没有有效的钥匙串绑定，请重新登录。')
    return read_mailbox_credential(service, account)


def read_mailbox_credential(service, account):
    helper = _keychain_helper()
    if helper is None:
        raise RuntimeError('缺少钥匙串组件，请重新安装完整应用。')
    background = os.environ.get('BENSON_MAIL_BACKGROUND') == '1'
    mode = '--read-background' if background else '--read'
    result = subprocess.run([str(helper), mode, service, account],
                            capture_output=True, text=True, timeout=25)
    if result.returncode or not result.stdout.strip():
        raise MailConnectionError('无法读取邮箱凭据。请打开「邮箱与检查」，选中该邮箱并测试连接，在钥匙串提示中授权。')
    return result.stdout.rstrip('\n')


def load(home=None, *, mailbox_identity=None):
    path = Path(home or data_home()) / 'settings.json'
    settings = json.loads(path.read_text()) if path.exists() else {}
    mailbox = settings.get('mailbox')
    selected = mailbox
    if mailbox_identity:
        from mailbox_config import mailbox_id
        saved = [item['connection'] for item in settings.get('mailboxes') or []]
        selected = next((item for item in (saved or ([mailbox] if mailbox else []))
                         if mailbox_id(item) == mailbox_identity), None)
        if selected is None:
            raise ValueError('找不到所选邮箱，请先保存邮箱设置。')
    if not selected and settings.get('mailboxes'):
        active_id = str(os.environ.get('BENSON_MAIL_ACCOUNT') or settings.get('active_mailbox_id') or '').casefold()
        selected = next((item.get('connection') for item in settings['mailboxes']
                         if item.get('connection', {}).get('account', '').casefold() == active_id), None)
        if selected is None:
            selected = settings['mailboxes'][0].get('connection')
    if selected:
        mailbox = selected
        connection = normalize(mailbox)
        service = mailbox.get('secret_service', 'BensonMail-IMAP')
        key_account = mailbox.get('secret_account', '')
    else:
        service, key_account = 'Codex-Mail-163', ''
        result = subprocess.run(['/usr/bin/security', 'find-generic-password', '-s', service],
                                capture_output=True, text=True, timeout=20)
        match = re.search(r'"acct"<blob>="([^"]+)"', result.stdout)
        if result.returncode or not match:
            raise ValueError('请先在设置中保存邮箱连接和授权码。')
        key_account = match.group(1)
        connection = normalize({'account': key_account, 'host': 'imap.163.com'})
    if service not in ('Codex-Mail-163', 'BensonMail-IMAP'):
        raise ValueError('邮箱凭据来源无效，请重新保存邮箱设置。')
    secret = read_mailbox_credential(service, key_account)
    keychain_config = {**connection, 'secret_service': service, 'secret_account': key_account}
    if connection.get('oauth_mode') == 'managed':
        keychain_config['_oauth_secret_provider'] = lambda: load_managed_credential(keychain_config)
    from mail_policy import validate_policy
    mail_policy = validate_policy(settings.get('mail_policy', {}))
    return {**keychain_config,
            'mailboxes': settings.get('mailboxes') or [],
            'active_mailbox_id': settings.get('active_mailbox_id', ''),
            'mailbox': mailbox,
            'read_all_mail': bool(mailbox.get('read_all_mail', False)) if mailbox else False,
            'spam_folders': mail_policy['spam_folders'],
            'ui_language': settings.get('ui_language', 'zh')}, secret


def _keychain_helper():
    candidates = []
    app = os.environ.get('BENSON_MAIL_APP', '')
    if app:
        candidates.append(Path(app) / 'Contents' / 'Resources' / 'SaveKeychainSecret')
    executable = Path(sys.executable).resolve()
    candidates.extend(parent / 'SaveKeychainSecret' for parent in executable.parents)
    return next((path for path in candidates if path.is_file() and os.access(path, os.X_OK)), None)


def save_managed_credential(config, bundle):
    """Atomically replace a refreshed OAuth bundle in the matching Keychain item."""
    service = str(config.get('secret_service', 'BensonMail-IMAP'))
    account = str(config.get('secret_account', ''))
    if service not in ('Codex-Mail-163', 'BensonMail-IMAP') or not account:
        raise ValueError('OAuth refresh cannot be saved because this mailbox has no exact Keychain binding. Sign in again.')
    from oauth_client import credential_json
    payload = credential_json(bundle)
    helper = _keychain_helper()
    if helper is None:
        raise RuntimeError('The secure Keychain refresh helper is missing. Reinstall the complete app.')
    mode = ['--write-background'] if os.environ.get('BENSON_MAIL_BACKGROUND') == '1' else []
    result = subprocess.run([str(helper), *mode, service, account], input=payload, capture_output=True,
                            text=True, timeout=20)
    if result.returncode:
        raise RuntimeError('OAuth token renewal succeeded, but the refreshed credential could not be saved to Keychain.')
    return payload

def test(mailbox_identity=None):
    value, secret = None, ''
    try:
        value, secret = load(mailbox_identity=mailbox_identity)
        client = connect(value, secret)
        try:
            if value.get('mail_provider') == 'gmail' and value.get('mail_auth') == 'oauth2':
                client.verify_messages()
        finally:
            client.logout()
        print('邮箱连接正常（只读连接，不修改邮件）。')
    except MailConnectionError as error:
        print(str(error))
        raise SystemExit(1)
    except ValueError as error:
        print(redact_mail_error(error, secret))
        raise SystemExit(1)
    except Exception as error:
        stage = 'Email connection test' if value and value.get('ui_language') in ('en', 'chinglish') else '邮箱连接测试'
        print(str(mail_error(error, value, secret, stage, value.get('ui_language', 'zh'))) if value else '无法读取邮箱连接配置（' + type(error).__name__ + '），请重新保存邮箱设置。')
        raise SystemExit(1)
