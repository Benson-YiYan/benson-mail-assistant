"""Estimate input size and read optional limits from the configured model provider."""
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
import threading
import time
import urllib.error
import urllib.request


FALLBACK_INPUT_TOKENS = {'api': 24000, 'codex': 32000, 'deepseek_harness': 32000}
MAX_METADATA_BYTES = 2 * 1024 * 1024
_PARTS = re.compile(r'[A-Za-z]+|[0-9]{1,3}|[ \t]+|[^\x20\t]')
_CONTEXT_CODES = {
    'context_length_exceeded', 'context_window_exceeded', 'context_length_error',
    'input_too_long', 'prompt_too_long', 'max_context_length_exceeded',
    'max_input_tokens_exceeded',
}
_CONTEXT_MESSAGE = re.compile(
    r'(?:maximum|max) context (?:length|window) (?:is|of)\b'
    r'|context (?:length|window)(?: limit)? (?:is )?exceeded\b'
    r'|(?:input|prompt) (?:tokens?|length) (?:exceeds?|exceeded) (?:the )?(?:max(?:imum)?|context)\b'
    r'|(?:input|prompt) (?:is )?too long\b',
    re.IGNORECASE,
)
_cache = {}
_cache_lock = threading.Lock()


class ContextLengthError(RuntimeError):
    def __init__(self, message, *, safe_to_retry=True):
        super().__init__(message)
        self.safe_to_retry = safe_to_retry


def is_context_error(payload):
    """Recognize context rejection without retaining or displaying provider text."""
    if not isinstance(payload, dict) or 'error' not in payload:
        return False
    error = payload['error']
    if isinstance(error, dict):
        if any(isinstance(error.get(field), str) and error[field].lower() in _CONTEXT_CODES
               for field in ('code', 'type')):
            return True
        message = error.get('message')
    else:
        message = error
    return isinstance(message, str) and bool(_CONTEXT_MESSAGE.search(message[:2048]))


def estimate_text(text):
    """A conservative approximation that accounts for CJK and structured text."""
    tokens = 0
    cjk = 0
    for match in _PARTS.finditer(text):
        part = match[0]
        ch = ord(part[0])
        if ch < 128:
            if part[0] in ' \t':
                tokens += len(part) // 4
            else:
                tokens += (len(part) + 3) // 4
        elif (0x2E80 <= ch <= 0x9FFF or 0xAC00 <= ch <= 0xD7AF
              or 0xF900 <= ch <= 0xFAFF or 0x20000 <= ch <= 0x323AF):
            cjk += 1
        else:
            tokens += (len(part.encode('utf-8', errors='replace')) + 1) // 2
    return tokens + (3 * cjk + 1) // 2


def estimate_messages(messages, provider='api'):
    if provider in ('codex', 'deepseek_harness'):
        # CLI adapters wrap the turns in JSON and add their own instructions.
        return 1024 + estimate_text(json.dumps({'conversation': messages}, ensure_ascii=False))
    return 16 + sum(8 + estimate_text(message['content']) for message in messages)


def _limit(value):
    if isinstance(value, str) and value.isascii() and value.isdigit() and len(value) <= 8:
        value = int(value)
    return value if type(value) is int and 128 <= value <= 16_000_000 else None


def _advertised_input(model):
    top = model.get('top_provider')
    rows = (model, top) if isinstance(top, dict) else (model,)

    def values(names):
        return [limit for row in rows for name in names if (limit := _limit(row.get(name)))]

    windows = values(('context_length', 'context_window', 'max_context_length', 'max_context_tokens'))
    inputs = values(('max_input_tokens', 'input_token_limit', 'prompt_token_limit'))
    outputs = values(('max_output_tokens', 'max_completion_tokens', 'output_token_limit'))
    if windows:
        window = min(windows)
        # Keep room for a reply and for provider-side prompt framing.
        reserve = max(64, min(4096, window // 8, min(outputs, default=4096)))
        inputs.append(max(64, window - reserve))
    return min(inputs) if inputs else None


def _metadata_budget(root, config, ai_api, url, model):
    key = ai_api.saved_api_key(root, config)
    if not key:
        return None
    request = urllib.request.Request(url, headers={
        'Authorization': 'Bearer ' + key.strip(),
        'Accept': 'application/json',
        'User-Agent': 'BensonMail/1.1',
    })
    handlers = [ai_api.NoRedirect()]
    if url.startswith('https://') and hasattr(ai_api, 'tls_context'):
        handlers.append(urllib.request.HTTPSHandler(context=ai_api.tls_context()))
    with urllib.request.build_opener(*handlers).open(request, timeout=4) as response:
        body = response.read(MAX_METADATA_BYTES + 1)
    if len(body) > MAX_METADATA_BYTES:
        return None
    payload = json.loads(body)
    rows = payload.get('data') if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        return None
    for row in rows:
        if isinstance(row, dict) and row.get('id') == model:
            return _advertised_input(row)
    return None


def _cache_path(root):
    return Path(root) / 'chat-model-limit.json'


def _read_disk_cache(path, fingerprint):
    try:
        with path.open('rb') as handle:
            data = handle.read(1025)
        value = json.loads(data) if len(data) <= 1024 else None
        if (isinstance(value, dict) and value.get('model_key') == fingerprint
                and type(value.get('expires')) in (int, float)
                and 0 < value['expires'] - time.time() <= 3600):
            limit = value.get('input_tokens')
            if limit is None or (type(limit) is int and 64 <= limit <= 16_000_000):
                return (time.monotonic() + value['expires'] - time.time(), limit)
    except (OSError, ValueError):
        pass
    return None


def _write_disk_cache(path, fingerprint, advertised, ttl):
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, delete=False, mode='w', encoding='utf-8') as handle:
            temporary = Path(handle.name)
            json.dump({'model_key': fingerprint, 'expires': time.time() + ttl,
                       'input_tokens': advertised}, handle)
        os.replace(temporary, path)
    except OSError:
        pass
    finally:
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass


def input_budget(root, config):
    provider = config.get('ai_provider', 'codex')
    fallback = FALLBACK_INPUT_TOKENS.get(provider, 24000)
    if provider != 'api':
        return fallback

    if __package__:
        from . import ai_api
    else:
        import ai_api
    model = config.get('api_model')
    if not isinstance(model, str) or not model.strip() or not isinstance(config.get('api_base'), str):
        return fallback
    try:
        endpoint = ai_api.endpoint(config['api_base'])
    except ValueError:
        return fallback
    model = model.strip()
    url = endpoint.removesuffix('/chat/completions') + '/models'
    cache_key = (str(root), url, model)
    started = time.monotonic()
    with _cache_lock:
        cached = _cache.get(cache_key)
        if cached and cached[0] > started:
            return cached[1] or fallback
    # Mac starts one worker per turn; share the most recently used budget across
    # worker processes. This cache contains no URL, model name, or credential.
    disk_path = _cache_path(root)
    fingerprint = hashlib.sha256(json.dumps((url, model)).encode('utf-8')).hexdigest()
    cached = _read_disk_cache(disk_path, fingerprint)
    if not cached:
        try:
            advertised = _metadata_budget(root, config, ai_api, url, model)
        except urllib.error.HTTPError as error:
            error.close()
            advertised = None
        except (OSError, ValueError, RuntimeError):
            advertised = None
        ttl = 3600 if advertised else 300
        cached = time.monotonic() + ttl, advertised
        _write_disk_cache(disk_path, fingerprint, advertised, ttl)
    with _cache_lock:
        if len(_cache) >= 128:
            _cache.pop(next(iter(_cache)))
        _cache[cache_key] = cached
    return cached[1] or fallback
