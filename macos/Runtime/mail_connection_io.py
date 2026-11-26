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
    result = subprocess.run(
        ['/usr/bin/security', 'find-generic-password', '-s', service, '-a', account, '-w'],
        capture_output=True, text=True, timeout=20,
    )
    if result.returncode or not result.stdout.strip():
        raise ValueError('OAuth 邮箱凭据不可用，请重新登录。')
    return result.stdout.rstrip('\n')


def load(home=None):
    path = Path(home or data_home()) / 'settings.json'
    settings = json.loads(path.read_text()) if path.exists() else {}
    mailbox = settings.get('mailbox')
    if mailbox:
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
    command = ['/usr/bin/security', 'find-generic-password', '-s', service]
    if key_account: command.extend(['-a', key_account])
    result = subprocess.run(command + ['-w'], capture_output=True, text=True, timeout=20)
    if result.returncode or not result.stdout.strip():
        raise ValueError('无法读取该邮箱的钥匙串凭据，请在设置中重新保存。')
    keychain_config = {**connection, 'secret_service': service, 'secret_account': key_account}
    if connection.get('oauth_mode') == 'managed':
        keychain_config['_oauth_secret_provider'] = lambda: load_managed_credential(keychain_config)
    from mail_policy import validate_policy
    mail_policy = validate_policy(settings.get('mail_policy', {}))
    return {**keychain_config,
            'read_all_mail': bool(mailbox.get('read_all_mail', False)) if mailbox else False,
            'spam_folders': mail_policy['spam_folders'],
            'ui_language': settings.get('ui_language', 'zh')}, result.stdout.rstrip('\n')


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
    result = subprocess.run([str(helper), service, account], input=payload, capture_output=True,
                            text=True, timeout=20)
    if result.returncode:
        raise RuntimeError('OAuth token renewal succeeded, but the refreshed credential could not be saved to Keychain.')
    return payload

def test():
    value, secret = None, ''
    try:
        value, secret = load()
        client = connect(value, secret)
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
