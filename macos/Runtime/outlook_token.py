"""User initiated Microsoft device authorization. No token is logged or saved."""
import json
import re
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

SCOPE = 'https://outlook.office.com/IMAP.AccessAsUser.All https://outlook.office.com/SMTP.Send offline_access'

def post(url, values):
    request = urllib.request.Request(url, data=urllib.parse.urlencode(values).encode(), headers={'Content-Type': 'application/x-www-form-urlencoded'})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        if error.code != 400:
            raise RuntimeError('Microsoft HTTP ' + str(error.code)) from None
        with error:
            return json.load(error)


def acquire(client, tenant, show, request=post, sleep=time.sleep, clock=time.monotonic):
    # Restrict tenant to an identifier; it cannot redirect a request to another host.
    uuid.UUID(client)
    if not re.fullmatch(r'[A-Za-z0-9.-]{1,255}', tenant):
        raise ValueError('Invalid tenant identifier')
    base = 'https://login.microsoftonline.com/' + tenant + '/oauth2/v2.0/'
    device = request(base + 'devicecode', {'client_id': client, 'scope': SCOPE})
    if 'error' in device:
        raise RuntimeError('Microsoft error: ' + safe_error(device['error']))
    uri = device['verification_uri']
    parsed = urllib.parse.urlsplit(uri)
    if parsed.scheme != 'https' or parsed.hostname not in {'microsoft.com', 'www.microsoft.com', 'login.microsoftonline.com'}:
        raise RuntimeError('Unexpected Microsoft sign-in address')
    show(uri, device['user_code'])
    interval = max(1, int(device.get('interval', 5)))
    deadline = clock() + max(1, int(device['expires_in']))
    while clock() < deadline:
        sleep(min(interval, max(0, deadline-clock())))
        if clock() >= deadline:
            break
        value = request(base + 'token', {'grant_type': 'urn:ietf:params:oauth:grant-type:device_code', 'client_id': client, 'device_code': device['device_code']})
        if value.get('access_token'):
            return value['access_token']
        error = value.get('error', '')
        if error == 'authorization_pending':
            continue
        if error == 'slow_down':
            interval += 5
            continue
        raise RuntimeError('Microsoft error: ' + safe_error(error))
    raise RuntimeError('Microsoft error: expired_token')


def safe_error(value):
    # Never include response descriptions: these may contain account identifiers.
    known = {'authorization_declined', 'expired_token', 'bad_verification_code', 'invalid_client', 'unauthorized_client', 'invalid_grant', 'invalid_scope', 'access_denied', 'interaction_required', 'authorization_pending', 'slow_down'}
    return value if value in known else 'authorization_failed'


def main():
    from runtime_paths import data_home
    try:
        language = json.loads((data_home() / 'settings.json').read_text()).get('ui_language', 'zh')
    except (OSError, ValueError):
        language = 'zh'
    en = language == 'en'
    def text(zh, english):
        return english if en else zh
    print(text('微软邮箱 OAuth2 取令牌工具\n请先按教程注册自己的应用并启用公共客户端流程。此工具只负责登录取令牌。', 'Microsoft mail OAuth2 token helper\nFirst register your own application and enable public client flows as explained in the guide.'))
    try:
        client = input(text('应用程序(客户端) ID：', 'Application (client) ID: ')).strip()
        tenant = input(text('租户（个人账户直接回车使用 consumers）：', 'Tenant (press Enter for personal accounts: consumers): ')).strip() or 'consumers'
        def show(uri, code):
            print(text('请在浏览器打开以下微软官方网址，输入一次性代码并登录：', 'Open this official Microsoft address in your browser, enter the one-time code and sign in:'))
            print(uri)
            print(text('一次性代码：', 'One-time code: ') + code)
        token = acquire(client, tenant, show)
        subprocess.run(['/usr/bin/pbcopy'], input=token.encode(), check=True)
        token = None
        print(text('已复制访问令牌！回到邮件小秘书，粘贴到 OAuth2 访问令牌框，保存并测试。令牌会过期，本软件不自动续期。', 'Access token copied! Paste it into Mail Secretary\'s OAuth2 access token field, save and test. Tokens expire; the app does not refresh them automatically.'))
    except (EOFError, KeyboardInterrupt):
        print(text('已取消。', 'Cancelled.'))
    except ValueError:
        print(text('客户端 ID 必须为应用注册页中的 UUID，租户须为 ID 或域名。', 'Client ID must be the UUID from app registration; tenant must be an ID or domain.'))
    except (RuntimeError, OSError, KeyError, TypeError) as error:
        # Only locally generated controlled messages, never raw HTTP bodies or tokens.
        detail = str(error) if isinstance(error, RuntimeError) else type(error).__name__
        print(text('未取得令牌。请检查网络、应用注册、公共客户端流程及管理员授权。错误：', 'No token obtained. Check network, app registration, public client flows and administrator approval. Error: ') + detail)
    try:
        input(text('按回车关闭此窗口。', 'Press Enter to close this window.'))
    except (EOFError, KeyboardInterrupt):
        pass
