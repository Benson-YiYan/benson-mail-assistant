"""Provider presets and a validated, read-only IMAP transport."""
import base64
import hashlib
import imaplib
import ipaddress
import re
import ssl
import socket
import json
import urllib.parse

IMAP_ERROR = imaplib.IMAP4.error

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

class MailConnectionError(RuntimeError):
    """Sanitized connection diagnostic safe for the UI and background status."""


def redact_mail_error(error, secret, username=''):
    text = str(error)
    if secret:
        raw = secret.encode('utf-8')
        payloads = [raw, f"user={username}\x01auth=Bearer {secret}\x01\x01".encode(),
                    f"\0{username}\0{secret}".encode(), f"{username}\0{username}\0{secret}".encode()]
        variants = {secret, secret.replace('\\', '\\\\').replace('"', '\\"'),
                    json.dumps(secret, ensure_ascii=True)[1:-1], urllib.parse.quote(secret, safe='')}
        for payload in payloads:
            encoded = base64.b64encode(payload).decode()
            variants.update((encoded, encoded.rstrip('='), base64.urlsafe_b64encode(payload).decode().rstrip('='), repr(payload)[2:-1]))
        for variant in sorted(variants, key=len, reverse=True):
            if variant: text = text.replace(variant, '[已隐藏凭据]')
    text = re.sub(r'(?i)(bearer\s+|(?:password|passwd|secret|token|authorization|authcode)\s*[=:]\s*)[^\s,;]+',
                  r'\1[已隐藏凭据]', text)
    return ' '.join(text.split())[:1200]


def mail_error(error, value, secret, stage, language='zh'):
    detail = redact_mail_error(error, secret, value['username'])
    lowered = detail.casefold()
    if isinstance(error, ssl.SSLCertVerificationError):
        hint = 'TLS 证书验证失败；请检查系统时间、代理及服务器证书。不会跳过证书验证。'
    elif isinstance(error, ssl.SSLError):
        hint = 'TLS 加密协商失败；请核对端口和 SSL/TLS 或 STARTTLS 设置。'
    elif isinstance(error, socket.gaierror):
        hint = 'DNS 域名解析失败；请核对 IMAP 域名和网络 DNS。'
    elif isinstance(error, (TimeoutError, socket.timeout)):
        hint = '连接或读取超时（单次最长等待 25 秒）；请检查网络、代理和服务器可达性。'
    elif 'unsafe login' in lowered or '不安全登录' in lowered:
        hint = '服务器判定登录不安全并拒绝访问；请查看邮箱网页中的安全提醒或服务商说明，不能据此判断授权码错误。'
    elif any(term in lowered for term in ('imap disabled', 'imap is disabled', 'imap not enabled', 'imap is not enabled', 'imap未开启', 'imap 未开启', 'imap未开通', 'imap服务未开启')):
        hint = '服务器明确提示 IMAP 未开启；请在邮箱网页设置中启用 IMAP。'
    elif any(term in lowered for term in ('authenticationfailed', 'authentication failed', 'login failed', 'invalid credentials', '认证失败', '授权失败')):
        hint = '服务器拒绝认证；请核对账号、授权码或 OAuth2 令牌及邮箱服务设置。具体拒绝原因以服务器响应为准。'
    elif isinstance(error, ConnectionRefusedError):
        hint = '服务器拒绝连接；请核对 IMAP 地址、端口及网络或代理设置。'
    else:
        hint = '邮箱操作失败；请结合下方阶段和服务器响应检查设置，尚不能确定原因。'
    error_type = ('IMAP4.' + type(error).__name__) if isinstance(error, IMAP_ERROR) else type(error).__name__
    if language == 'en':
        hints = {
            'TLS 证书验证失败；请检查系统时间、代理及服务器证书。不会跳过证书验证。': 'TLS certificate verification failed. Check the system clock, proxy and server certificate. Certificate verification remains enabled.',
            'TLS 加密协商失败；请核对端口和 SSL/TLS 或 STARTTLS 设置。': 'TLS negotiation failed. Check the port and SSL/TLS or STARTTLS settings.',
            'DNS 域名解析失败；请核对 IMAP 域名和网络 DNS。': 'DNS lookup failed. Check the IMAP hostname and network DNS settings.',
            '连接或读取超时（单次最长等待 25 秒）；请检查网络、代理和服务器可达性。': 'Connection or read timed out (25 seconds per operation). Check the network, proxy and server availability.',
            '服务器判定登录不安全并拒绝访问；请查看邮箱网页中的安全提醒或服务商说明，不能据此判断授权码错误。': 'The server rejected this as an unsafe login. Check webmail security notices or provider instructions; this does not establish that the authorization code is wrong.',
            '服务器明确提示 IMAP 未开启；请在邮箱网页设置中启用 IMAP。': 'The server explicitly reports that IMAP is disabled. Enable IMAP in webmail settings.',
            '服务器拒绝认证；请核对账号、授权码或 OAuth2 令牌及邮箱服务设置。具体拒绝原因以服务器响应为准。': 'The server rejected authentication. Check the account, authorization code or OAuth2 token and mailbox service settings. The server response below provides the reported reason.',
            '服务器拒绝连接；请核对 IMAP 地址、端口及网络或代理设置。': 'The server refused the connection. Check the IMAP hostname, port, network and proxy settings.',
            '邮箱操作失败；请结合下方阶段和服务器响应检查设置，尚不能确定原因。': 'The mailbox operation failed. Check the stage and server response below; the cause is not yet established.'}
        stages = {'SSL/TLS 连接':'SSL/TLS connection', 'TCP 连接':'TCP connection', 'STARTTLS 加密协商':'STARTTLS negotiation',
                  'XOAUTH2 认证':'XOAUTH2 authentication', 'LOGIN 认证':'LOGIN authentication',
                  'CAPABILITY 登录后能力协商':'CAPABILITY after authentication', 'ID 客户端标识协商':'ID client identification',
                  'SELECT 只读打开邮件文件夹':'SELECT read-only mailbox',
                  'UIDVALIDITY 读取邮件文件夹标识':'UIDVALIDITY mailbox identity', 'UID SEARCH 检查邮件编号':'UID SEARCH message identifiers'}
        return MailConnectionError(f"Mailbox connection failed: {hints[hint]}\nServer: {value['host']}:{value['port']} ({value['security']})\nStage: {stages.get(stage, stage)}\nCause: {error_type}: {detail}")
    return MailConnectionError(f"邮箱连接失败：{hint}\n服务器：{value['host']}:{value['port']} ({value['security']})\n阶段：{stage}\n具体原因：{error_type}: {detail}")


def require_ok(result, operation):
    status, data = result
    if status != 'OK':
        raise IMAP_ERROR(f'{operation}: {status} {data!r}')
    return data


def connect(config, secret, context=None):
    value = normalize(config)
    context = context or ssl.create_default_context()
    client = None
    stage = 'SSL/TLS 连接' if value['security'] == 'ssl' else 'TCP 连接'
    try:
        if value['security'] == 'ssl':
            client = imaplib.IMAP4_SSL(value['host'], value['port'], ssl_context=context, timeout=25)
        else:
            client = imaplib.IMAP4(value['host'], value['port'], timeout=25)
            stage = 'STARTTLS 加密协商'
            require_ok(client.starttls(ssl_context=context), 'STARTTLS')
        if value['mail_auth'] == 'oauth2':
            stage = 'XOAUTH2 认证'
            if any(c in secret for c in '\r\n\x01'):
                raise ValueError('OAuth2 访问令牌格式无效。')
            token = f"user={value['username']}\x01auth=Bearer {secret}\x01\x01".encode()
            require_ok(client.authenticate('XOAUTH2', lambda challenge: token if not challenge else b''), 'AUTHENTICATE')
        else:
            stage = 'LOGIN 认证'
            require_ok(client.login(value['username'], secret), 'LOGIN')
        # imaplib caches pre-auth capabilities; login/authenticate do not refresh them.
        # Ask again after authentication, when extensions such as ID may change.
        stage = 'CAPABILITY 登录后能力协商'
        advertised = require_ok(client.capability(), 'CAPABILITY')
        capabilities = set()
        for item in advertised:
            if item: capabilities.update((item.decode('ascii', 'replace') if isinstance(item, bytes) else str(item)).upper().split())
        if 'ID' in capabilities:
            stage = 'ID 客户端标识协商'
            imaplib.Commands.setdefault('ID', ('AUTH', 'SELECTED'))
            require_ok(client._simple_command('ID', '("name" "BensonMail" "version" "2.0" "vendor" "Benson")'), 'ID')
        stage = 'SELECT 只读打开邮件文件夹'
        require_ok(client.select(folder_name(value['mail_folder']), readonly=True), 'SELECT')
        return client
    except Exception as error:
        if client is not None:
            try: client.logout()
            except Exception: pass
        raise mail_error(error, value, secret, stage, config.get('ui_language', 'zh')) from None
