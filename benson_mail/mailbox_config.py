"""Provider presets and a validated, read-only IMAP transport."""
import base64
import hashlib
import imaplib
import ipaddress
import re
import ssl

PRESETS = [
    {'id': '163', 'name': '网易163', 'host': 'imap.163.com'},
    {'id': '126', 'name': '网易126', 'host': 'imap.126.com'},
    {'id': 'yeah', 'name': '网易Yeah', 'host': 'imap.yeah.net'},
    {'id': 'qq', 'name': 'QQ / Foxmail', 'host': 'imap.qq.com'},
    {'id': 'exmail', 'name': '腾讯企业邮箱', 'host': 'imap.exmail.qq.com'},
    {'id': 'gmail', 'name': 'Gmail', 'host': 'imap.gmail.com'},
    {'id': 'outlook', 'name': 'Outlook / Microsoft 365', 'host': 'outlook.office365.com', 'mail_auth': 'oauth2'},
    {'id': 'icloud', 'name': 'iCloud', 'host': 'imap.mail.me.com'},
    {'id': 'yahoo', 'name': 'Yahoo', 'host': 'imap.mail.yahoo.com'},
    {'id': 'custom', 'name': '其他邮箱（自定义 IMAP）', 'host': ''},
]

def normalize(raw):
    value = raw.get('mailbox') or raw
    account = str(value.get('account', '')).strip().lower()
    if len(account) > 254 or not re.fullmatch(r'[^\s@\x00-\x1f]+@[^\s@/\\\x00-\x1f]+\.[^\s@/\\\x00-\x1f]+', account):
        raise ValueError('请输入完整的邮箱地址，例如 name@example.com。')
    host = str(value.get('host', 'imap.163.com')).strip().lower()
    try:
        ipaddress.ip_address(host)
    except ValueError:
        try: host = host.encode('idna').decode('ascii')
        except UnicodeError: raise ValueError('IMAP 服务器地址无效。') from None
        if len(host) > 253 or not all(re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?', part) for part in host.split('.')):
            raise ValueError('IMAP 服务器只填写域名或 IP，不要包含 https://、端口或路径。')
    try:
        if isinstance(value.get('port'), bool): raise ValueError()
        port = int(value.get('port', 993))
        if str(value.get('port', 993)).strip() != str(port) or not 1 <= port <= 65535: raise ValueError()
    except (TypeError, ValueError):
        raise ValueError('IMAP 端口应为1至65535的整数。') from None
    security = value.get('security', 'ssl')
    auth = value.get('mail_auth', 'password')
    if security not in ('ssl', 'starttls'): raise ValueError('请选择 SSL/TLS 或 STARTTLS 加密。')
    if auth not in ('password', 'oauth2'): raise ValueError('请选择密码／授权码或 OAuth2 访问令牌。')
    username = str(value.get('username') or account).strip()
    folder = str(value.get('mail_folder') or 'INBOX').strip()
    if not username or any(ord(c) < 32 or ord(c) == 127 for c in username + folder):
        raise ValueError('登录用户名和邮件文件夹不能包含换行或控制字符。')
    return {'account': account, 'username': username, 'host': host, 'port': port,
            'security': security, 'mail_folder': folder, 'mail_auth': auth,
            'mail_provider': str(value.get('mail_provider', 'custom'))}

def mailbox_id(config):
    config = normalize(config)
    return hashlib.sha256('\x1f'.join(str(config[k]) for k in
        ('account', 'username', 'host', 'port', 'security', 'mail_folder', 'mail_auth')).encode()).hexdigest()

def state_identity(config):
    value = normalize(config)
    # Preserve existing Windows progress for the original default connection.
    if (value['username'] == value['account'] and value['port'] == 993 and value['security'] == 'ssl'
            and value['mail_folder'] == 'INBOX' and value['mail_auth'] == 'password'):
        return hashlib.sha256((value['account'] + '|' + value['host']).encode()).hexdigest()[:24]
    return mailbox_id(config)[:24]

def folder_name(value):
    """IMAP modified UTF-7, so custom non-ASCII folder names work too."""
    result, pending = [], []
    def flush():
        if pending:
            result.append('&' + base64.b64encode(''.join(pending).encode('utf-16-be')).decode().rstrip('=').replace('/', ',') + '-')
            pending.clear()
    for char in value:
        if 0x20 <= ord(char) <= 0x7e:
            flush(); result.append('&-' if char == '&' else char)
        else: pending.append(char)
    flush()
    return '"' + ''.join(result).replace('\\', '\\\\').replace('"', '\\"') + '"'

def connect(config, secret, context=None):
    value = normalize(config)
    context = context or ssl.create_default_context()
    client = None
    try:
        if value['security'] == 'ssl':
            client = imaplib.IMAP4_SSL(value['host'], value['port'], ssl_context=context, timeout=25)
        else:
            client = imaplib.IMAP4(value['host'], value['port'], timeout=25)
            client.starttls(ssl_context=context)
        if value['mail_auth'] == 'oauth2':
            if any(c in secret for c in '\r\n\x01'):
                raise ValueError('OAuth2 访问令牌格式无效。')
            token = f"user={value['username']}\x01auth=Bearer {secret}\x01\x01".encode()
            client.authenticate('XOAUTH2', lambda challenge: token if not challenge else b'')
        else:
            client.login(value['username'], secret)
        capabilities = {c.decode().upper() if isinstance(c, bytes) else c.upper() for c in client.capabilities}
        if 'ID' in capabilities:
            imaplib.Commands.setdefault('ID', ('AUTH', 'SELECTED'))
            client._simple_command('ID', '("name" "BensonMail" "version" "2.0" "vendor" "Benson")')
        status, _ = client.select(folder_name(value['mail_folder']), readonly=True)
        if status != 'OK': raise ValueError('无法读取指定邮件文件夹，请检查文件夹名称和 IMAP 权限。')
        return client
    except Exception:
        if client is not None:
            try: client.logout()
            except Exception: pass
        raise
