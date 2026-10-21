"""Manual account-balance lookup at supported official APIs; never invokes a model."""
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import json
import socket
import ssl
import urllib.error
import urllib.parse
import urllib.request

MAX_RESPONSE = 65536


def _modules():
    if __package__:
        from . import ai_api, mail_chat
    else:
        import ai_api, mail_chat
    return ai_api, mail_chat


def _target(config):
    if config.get('ai_provider', 'codex') != 'api':
        return 'not_api', None
    base = config.get('api_base', '')
    if not isinstance(base, str) or len(base) > 2048:
        return 'unsupported', None
    try:
        parts = urllib.parse.urlsplit(base.strip())
        if parts.scheme != 'https' or parts.username or parts.password or parts.query or parts.fragment or parts.port not in (None, 443):
            return 'unsupported', None
        host, path = parts.hostname, parts.path.rstrip('/')
        if host == 'api.deepseek.com' and path in ('', '/v1', '/chat/completions', '/v1/chat/completions'):
            return 'deepseek', 'https://api.deepseek.com/user/balance'
        if host == 'openrouter.ai' and path in ('/api/v1', '/api/v1/chat/completions'):
            return 'openrouter', 'https://openrouter.ai/api/v1/credits'
    except ValueError:
        pass
    return 'unsupported', None


def _result(status, provider, balances=None, error_code=None):
    result = {'status': status, 'provider': provider, 'balances': balances or [],
              'checked_at': datetime.now(timezone.utc).isoformat()}
    if error_code:
        result['error_code'] = error_code
    return result


def _number(value, nonnegative=False):
    if isinstance(value, bool) or not isinstance(value, (str, int, float)) or len(str(value)) > 128:
        raise ValueError('Invalid balance')
    try:
        number = Decimal(str(value))
    except InvalidOperation:
        raise ValueError('Invalid balance') from None
    if not number.is_finite() or abs(number) > Decimal('1e18') or (nonnegative and number < 0):
        raise ValueError('Invalid balance')
    return number


def _parse(provider, value):
    if not isinstance(value, dict):
        raise ValueError('Invalid response')
    if provider == 'openrouter':
        data = value['data']
        credits = _number(data['total_credits'], nonnegative=True)
        used = _number(data['total_usage'], nonnegative=True)
        return [{'currency': 'USD', 'total_balance': str(credits - used)}]
    entries = value['balance_infos']
    if not isinstance(entries, list) or not 1 <= len(entries) <= 10:
        raise ValueError('Invalid balances')
    balances = []
    seen = set()
    for entry in entries:
        currency = entry['currency']
        if currency not in ('CNY', 'USD') or currency in seen:
            raise ValueError('Invalid currency')
        seen.add(currency)
        balance = {'currency': currency}
        for field in ('total_balance', 'granted_balance', 'topped_up_balance'):
            balance[field] = str(_number(entry[field]))
        balances.append(balance)
    return balances


def _network_code(error):
    reason = error.reason if isinstance(error, urllib.error.URLError) else error
    if isinstance(reason, (TimeoutError, socket.timeout)):
        return 'timeout'
    if isinstance(reason, ssl.SSLError):
        return 'tls'
    if isinstance(reason, socket.gaierror):
        return 'dns'
    return 'network'


def query_balance(config, key):
    """Return account-wide upstream balance, not this application's usage/cost."""
    provider, url = _target(config)
    if not url:
        return _result(provider, None)
    if not isinstance(key, str) or not key.strip():
        return _result('error', provider, error_code='missing_key')
    if '\r' in key or '\n' in key or len(key) > 16384:
        return _result('error', provider, error_code='invalid_key')
    ai_api, _ = _modules()
    request = urllib.request.Request(url, headers={'Authorization': 'Bearer ' + key.strip(),
        'Accept': 'application/json', 'User-Agent': 'BensonMail/1.1'}, method='GET')
    try:
        handlers = [ai_api.NoRedirect()]
        if hasattr(ai_api, 'tls_context'):
            handlers.append(urllib.request.HTTPSHandler(context=ai_api.tls_context()))
        with urllib.request.build_opener(*handlers).open(request, timeout=25) as response:
            raw = response.read(MAX_RESPONSE + 1)
        if len(raw) > MAX_RESPONSE:
            return _result('error', provider, error_code='response_too_large')
        value = json.loads(raw)
        balances = _parse(provider, value)
    except urllib.error.HTTPError as error:
        code = error.code
        error.close()
        category = {401: 'authentication', 403: 'permission', 429: 'rate_limit'}.get(code)
        if category is None:
            category = 'redirect' if 300 <= code < 400 else 'server' if 500 <= code < 600 else 'http'
        return _result('error', provider, error_code=category)
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        return _result('error', provider, error_code=_network_code(error))
    except (ValueError, UnicodeError, KeyError, TypeError, OverflowError):
        return _result('error', provider, error_code='invalid_response')
    except Exception:
        return _result('error', provider, error_code='internal')
    return _result('ok', provider, balances)


def balance(root):
    """Read saved settings/key; unsupported providers never access credentials/network."""
    try:
        ai_api, mail_chat = _modules()
        config = mail_chat._config(root)
        provider, url = _target(config)
        if not url:
            return _result(provider, None)
        key = ai_api.saved_api_key(root, config)
    except Exception:
        return _result('error', None, error_code='credentials')
    return query_balance(config, key)
