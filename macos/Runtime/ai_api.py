"""Minimal OpenAI-compatible chat client. Never logs keys or response bodies."""
from runtime_i18n import text as _t, localized, localized_method, localized_from_root
import json
import re
import socket
import ssl
import subprocess
import urllib.error
import urllib.parse
import urllib.request

MAX_RESPONSE = 4 * 1024 * 1024

@localized
def connection_error(error, key):
    """Keep network diagnostics useful without exposing request credentials or URLs."""
    reason = error.reason if isinstance(error, urllib.error.URLError) else error
    if isinstance(reason, ssl.SSLCertVerificationError):
        hint = _t('TLS 证书验证失败，请检查电脑时间、代理或服务商证书')
    elif isinstance(reason, socket.gaierror):
        hint = _t('DNS 解析失败，请检查域名和 DNS 设置')
    elif isinstance(reason, (TimeoutError, socket.timeout)):
        hint = _t('连接或读取超时（最长等待 120 秒）')
    elif isinstance(reason, ConnectionRefusedError):
        hint = _t('服务器或代理拒绝连接，请检查地址、端口及代理是否运行')
    else:
        hint = _t('连接失败，请检查网络、代理和基础地址')
    detail = str(reason)
    secret = key.strip()
    if secret:
        for value in (secret, urllib.parse.quote(secret, safe=''),
                      urllib.parse.quote_plus(secret), json.dumps(secret)[1:-1]):
            detail = detail.replace(value, _t('[已隐藏密钥]'))
    detail = re.sub(r'https?://\S+', _t('[地址已隐藏]'), detail)
    detail = re.sub(r'(?i)authorization\s*["\']?\s*[=:][^\r\n]*', _t('[授权头已隐藏]'), detail)
    detail = re.sub(r'(?i)(bearer\s+|(?:api[_-]?key|token|authorization)\s*["\']?\s*[=:]\s*["\']?)\S+',
                    _t(r'\1[已隐藏]'), detail)
    detail = ' '.join(detail.split())[:500]
    return _t('AI 接口%s。\n具体原因：%s: %s') % (hint, type(reason).__name__, detail)

@localized
def endpoint(base):
    base = base.strip().rstrip('/')
    parts = urllib.parse.urlsplit(base)
    local = parts.hostname in ('localhost', '127.0.0.1', '::1')
    if not parts.hostname or parts.username or parts.password or parts.query or parts.fragment:
        raise ValueError(_t('基础地址无效；请填写服务商提供的 API 地址，不含密钥或查询参数。'))
    if parts.scheme != 'https' and not (parts.scheme == 'http' and local):
        raise ValueError(_t('请使用 HTTPS 地址；本机 localhost 服务可使用 HTTP。'))
    return base if parts.path.endswith('/chat/completions') else base + '/chat/completions'

def identity(base, model=''):
    """Bind a saved key to its destination without storing the key."""
    return endpoint(base)

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, newurl):
        return None


def saved_api_key(root, config):
    """Use the same OS credential and endpoint binding as email analysis."""
    binding = identity(config.get('api_base', ''))
    result = subprocess.run(
        ['/usr/bin/security', 'find-generic-password', '-s', 'BensonMail-AI-API', '-a', binding, '-w'],
        capture_output=True, text=True, timeout=30)
    return result.stdout.strip() if result.returncode == 0 else ''

@localized
def complete(base, model, key, messages, stop=None):
    url = endpoint(base)
    if not model.strip() or not key.strip():
        raise ValueError(_t('请填写模型名和 API Key。'))
    if stop is not None and stop.is_set():
        raise RuntimeError(_t('分析已停止，邮件将在下次重试。'))
    payload = json.dumps({'model': model.strip(), 'messages': messages, 'stream': False}, ensure_ascii=False).encode()
    if len(payload) > 2 * 1024 * 1024:
        raise RuntimeError(_t('本封邮件及附件文字过大，尚未发送给 AI，请缩小附件后重试。'))
    request = urllib.request.Request(url, data=payload, headers={
        'Authorization': 'Bearer ' + key.strip(), 'Content-Type': 'application/json',
        'Accept': 'application/json', 'User-Agent': 'BensonMail/1.1'}, method='POST')
    try:
        with urllib.request.build_opener(NoRedirect()).open(request, timeout=120) as response:
            raw = response.read(MAX_RESPONSE + 1)
        if len(raw) > MAX_RESPONSE:
            raise RuntimeError(_t('AI 返回内容过大，邮件保留待重试。'))
        value = json.loads(raw)
    except urllib.error.HTTPError as error:
        code = error.code
        error.close()
        hints = {401: _t('API Key 无效或已过期'), 403: _t('API Key 没有权限'),
                 404: _t('基础地址或模型名不正确'), 429: _t('额度不足或请求过于频繁')}
        raise RuntimeError(_t('AI 接口错误（HTTP %s）：%s。') % (code, hints.get(code, _t('请检查服务商状态和接口配置')))) from None
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        raise RuntimeError(connection_error(error, key)) from None
    except (ValueError, UnicodeError):
        raise RuntimeError(_t('AI 接口返回的不是有效 JSON，请检查基础地址。')) from None
    try:
        from assistant_tools import record_usage
        record_usage('api', model, value.get('usage') if isinstance(value, dict) else None, base=base)
    except Exception:
        pass  # Storage errors must not invalidate an otherwise successful paid response.
    if stop is not None and stop.is_set():
        raise RuntimeError(_t('分析已停止，邮件将在下次重试。'))
    try:
        choice = value['choices'][0]
        if choice.get('finish_reason') == 'length':
            raise RuntimeError(_t('AI 返回内容被截断，邮件保留待重试；请检查模型输出限制。'))
        content = choice['message']['content']
        if isinstance(content, list):
            content = '\n'.join(part.get('text', '') for part in content if isinstance(part, dict))
        if not isinstance(content, str) or not content.strip():
            raise ValueError()
        return content.strip()
    except (KeyError, IndexError, TypeError, ValueError):
        raise RuntimeError(_t('AI 没有返回报告，请检查模型是否支持 Chat Completions。')) from None
