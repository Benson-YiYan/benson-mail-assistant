"""Minimal OpenAI-compatible chat client. Never logs keys or response bodies."""
from .runtime_i18n import text as _t, localized, localized_method, localized_from_root
import json
import re
import socket
import ssl
import sys
import hashlib
from pathlib import Path
import certifi
import urllib.error
import urllib.parse
import urllib.request

from .runtime_i18n import _LANGUAGE

MAX_RESPONSE = 4 * 1024 * 1024

def tls_context():
    """Use native Windows chain building plus bundled public trust roots."""
    if sys.platform == 'win32':
        import truststore
        context = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    else:
        context = ssl.create_default_context()
    context.load_verify_locations(cafile=certifi.where())
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.check_hostname = True
    context.verify_mode = ssl.CERT_REQUIRED
    return context

@localized
def connection_error(error, key):
    reason = error.reason if isinstance(error, urllib.error.URLError) else error
    code = 'AI_NETWORK'
    if isinstance(reason, FileNotFoundError):
        code = 'AI_LOCAL_FILE_MISSING'
        hint = {'en': 'A required local runtime or certificate file is missing. Reinstall the latest complete app.', 'es': 'Falta un archivo local de ejecución o certificados. Reinstala la aplicación completa.'}.get(_LANGUAGE.get(), '本地运行组件或证书文件缺失，请重新安装最新版完整应用')
    elif isinstance(reason, PermissionError):
        code = 'AI_LOCAL_PERMISSION'
        hint = {'en': 'Local runtime file access denied. Check app permissions.', 'es': 'Acceso a un archivo local denegado. Revisa los permisos.'}.get(_LANGUAGE.get(), '本地运行文件访问被拒绝，请检查应用权限')
    elif isinstance(reason, ssl.SSLCertVerificationError):
        code = 'AI_TLS_CERTIFICATE'
        hint = _t('TLS 证书验证失败，请检查电脑时间、代理或服务商证书')
    elif isinstance(reason, socket.gaierror):
        code = 'AI_DNS'
        hint = _t('DNS 解析失败，请检查域名和 DNS 设置')
    elif isinstance(reason, (TimeoutError, socket.timeout)):
        code = 'AI_TIMEOUT'
        hint = _t('连接或读取超时（最长等待 120 秒）')
    elif isinstance(reason, ConnectionRefusedError):
        code = 'AI_CONNECTION_REFUSED'
        hint = _t('服务器或代理拒绝连接，请检查地址、端口及代理是否运行')
    else:
        hint = _t('连接失败，请检查网络、代理和基础地址')
    detail = str(reason).replace(key.strip(), _t('[已隐藏密钥]'))
    detail = re.sub(r'https?://\S+', _t('[地址已隐藏]'), detail)
    detail = re.sub(r'(?i)(bearer\s+|(?:api[_-]?key|token|authorization)\s*[=:]\s*)\S+',
                    _t(r'\1[已隐藏]'), detail)
    detail = ' '.join(detail.split())[:500]
    native = getattr(reason, 'errno', None)
    suffix = f' [{code}' + (f'; OS={native}' if native is not None else '') + ']'
    return (_t('AI 接口%s。\n具体原因：%s: %s') % (hint, type(reason).__name__, detail)) + suffix

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
    from .platform_windows import load_secret
    binding = identity(config.get('api_base', ''))
    key_path = Path(root) / 'api-keys' / (hashlib.sha256(binding.encode()).hexdigest() + '.bin')
    return load_secret(key_path, binding) if key_path.exists() else ''

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
        handlers = [NoRedirect()]
        if url.startswith('https://'):
            handlers.append(urllib.request.HTTPSHandler(context=tls_context()))
        with urllib.request.build_opener(*handlers).open(request, timeout=120) as response:
            raw = response.read(MAX_RESPONSE + 1)
        if len(raw) > MAX_RESPONSE:
            raise RuntimeError(_t('AI 返回内容过大，邮件保留待重试。'))
        value = json.loads(raw)
    except urllib.error.HTTPError as error:
        code = error.code
        error.close()
        hints = {401: _t('API Key 无效或已过期'), 403: _t('API Key 没有权限'),
                 404: _t('基础地址或模型名不正确'), 429: _t('额度不足或请求过于频繁')}
        raise RuntimeError((_t('AI 接口错误（HTTP %s）：%s。') % (code, hints.get(code, _t('请检查服务商状态和接口配置')))) + f' [AI_HTTP_{code}]') from None
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        raise RuntimeError(connection_error(error, key)) from None
    except (ValueError, UnicodeError):
        raise RuntimeError(_t('AI 接口返回的不是有效 JSON，请检查基础地址。')) from None
    try:
        from .assistant_tools import record_usage
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
