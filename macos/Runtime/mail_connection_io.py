"""Load only the selected mailbox credential from macOS Keychain."""
import json
import re
import subprocess
from runtime_paths import data_home
from mailbox_config import normalize, connect, MailConnectionError, mail_error, redact_mail_error

def load():
    path = data_home() / 'settings.json'
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
        connection = normalize({'account': match.group(1), 'host': 'imap.163.com'})
    if service not in ('Codex-Mail-163', 'BensonMail-IMAP'):
        raise ValueError('邮箱凭据来源无效，请重新保存邮箱设置。')
    command = ['/usr/bin/security', 'find-generic-password', '-s', service]
    if key_account: command.extend(['-a', key_account])
    result = subprocess.run(command + ['-w'], capture_output=True, text=True, timeout=20)
    if result.returncode or not result.stdout.strip():
        raise ValueError('无法读取该邮箱的钥匙串凭据，请在设置中重新保存。')
    return {**connection, 'ui_language': settings.get('ui_language', 'zh')}, result.stdout.rstrip('\n')

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
        stage = 'Email connection test' if value and value.get('ui_language') == 'en' else '邮箱连接测试'
        print(str(mail_error(error, value, secret, stage, value.get('ui_language', 'zh'))) if value else '无法读取邮箱连接配置（' + type(error).__name__ + '），请重新保存邮箱设置。')
        raise SystemExit(1)
