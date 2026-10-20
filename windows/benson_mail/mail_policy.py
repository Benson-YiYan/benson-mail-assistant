"""Local sender policy and durable skipped-mail queue. Never modifies server mail."""
from .runtime_i18n import text as _t, localized, localized_method, localized_from_root
from contextlib import contextmanager
from datetime import datetime, timezone
from email.utils import parseaddr
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
import threading

DEFAULT = {'mode': 'blacklist', 'addresses': [], 'skip_spam': False}
_THREAD_LOCK = threading.RLock()

def sender_address(value):
    return parseaddr(str(value or ''))[1].strip().casefold()

def validate_policy(value):
    if not isinstance(value, dict): raise ValueError(_t('屏蔽规则无效。'))
    mode = value.get('mode', 'blacklist')
    if mode not in ('blacklist', 'whitelist'): raise ValueError(_t('请选择黑名单或白名单。'))
    raw = value.get('addresses', [])
    if not isinstance(raw, list) or len(raw) > 10000: raise ValueError(_t('邮箱地址列表无效。'))
    addresses = []
    for item in raw:
        address = sender_address(item)
        if not re.fullmatch(r'[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+', address) or len(address) > 254:
            raise ValueError(_t('请输入完整的邮箱地址：') + str(item)[:100])
        if address not in addresses: addresses.append(address)
    skip = value.get('skip_spam', False)
    if not isinstance(skip, bool): raise ValueError(_t('垃圾邮件选项无效。'))
    return {'mode': mode, 'addresses': addresses, 'skip_spam': skip}

@contextmanager
def _store(root):
    folder = Path(root) / 'blocked_mail'
    folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    with _THREAD_LOCK, (folder / 'state.lock').open('a+b') as lock:
        if os.name == 'nt':
            import msvcrt
            lock.seek(0); lock.write(b'\0'); lock.flush(); lock.seek(0)
            msvcrt.locking(lock.fileno(), msvcrt.LK_LOCK, 1)
        else:
            import fcntl
            fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            path = folder / 'state.json'
            value = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {'records': {}}
            value.setdefault('records', {})
            yield value
            fd, temporary = tempfile.mkstemp(prefix='.state-', dir=folder)
            try:
                with os.fdopen(fd, 'w', encoding='utf-8') as stream:
                    json.dump(value, stream, ensure_ascii=False); stream.flush(); os.fsync(stream.fileno())
                os.replace(temporary, path)
            finally:
                Path(temporary).unlink(missing_ok=True)
        finally:
            if os.name == 'nt':
                lock.seek(0); msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
            else: fcntl.flock(lock, fcntl.LOCK_UN)

def _policy(root, state):
    if 'policy' in state: return validate_policy(state['policy'])
    for name in ('config.json', 'settings.json'):
        path = Path(root) / name
        if path.exists():
            config = json.loads(path.read_text(encoding='utf-8'))
            if 'mail_policy' in config: return validate_policy(config['mail_policy'])
    return copy.deepcopy(DEFAULT)

@localized_from_root
def policy_status(root):
    with _store(root) as state:
        records = [{key: value for key, value in record.items() if key not in ('message', 'answer', 'new_notified')}
                   for record in state['records'].values() if record.get('state') != 'summarized']
        records.sort(key=lambda value: value.get('received', ''), reverse=True)
        return {'policy': _policy(root, state), 'records': records, 'count': len(records),
                'senders': sorted({record['sender'] for record in records if record.get('sender')})}

@localized_from_root
def policy_save(root, data):
    validated = validate_policy(data)
    with _store(root) as state: state['policy'] = validated
    return policy_status(root)

@localized_from_root
def policy_remove_records(root, ids):
    if not isinstance(ids, list): raise ValueError(_t('请选择邮件记录。'))
    with _store(root) as state:
        for identifier in ids:
            record = state['records'].get(str(identifier))
            if record and record.get('state') == 'processing': raise ValueError(_t('邮件正在总结，请完成后再删除记录。'))
        for identifier in ids: state['records'].pop(str(identifier), None)
    # Cached attachment files are intentionally retained: existing reports may reference them.
    return policy_status(root)

@localized_from_root
def policy_summarize_records(root, ids):
    if not isinstance(ids, list): raise ValueError(_t('请选择邮件记录。'))
    with _store(root) as state:
        for identifier in ids:
            record = state['records'].get(str(identifier))
            if record and record.get('state') not in ('processing', 'summarized'):
                record['state'] = 'queued'; record.pop('last_error', None)
    return policy_status(root)

def spam_metadata(message, flags='', folder=''):
    """Only explicit provider metadata; never guesses from subject or body text."""
    headers = message if hasattr(message, 'get') else {}
    reasons = []
    for header in ('X-Spam-Flag', 'X-Spam-Status', 'X-Junk-Status'):
        if re.match(r'^\s*(yes|true|spam|junk)(?:\b|;)', str(headers.get(header, '')), re.I): reasons.append(header)
    if re.search(r'(?:^|[\s(])(?:\\?Junk|\$Junk|\\Spam)(?:$|[\s)])', str(flags), re.I): reasons.append('IMAP flag')
    if re.search(r'\\Spam\b', str(flags), re.I): reasons.append('Gmail spam label')
    if str(folder).casefold() in {'spam', 'junk', 'junk email', 'junk e-mail', '[gmail]/spam', '垃圾邮件', '垃圾箱'}: reasons.append('junk folder')
    return {'is_spam': bool(reasons), 'spam_evidence': reasons}

def block_reason(policy, message):
    if policy['skip_spam'] and message.get('is_spam'): return 'spam'
    address = sender_address(message.get('sender') or message.get('from'))
    listed = address in policy['addresses']
    if policy['mode'] == 'blacklist' and listed: return 'blacklist'
    if policy['mode'] == 'whitelist' and not listed: return 'not_whitelisted'
    return None

def intercept(root, message, mailbox_key, validity, uid):
    """Durably save a blocked original before caller acknowledges its local pending UID."""
    with _store(root) as state:
        reason = block_reason(_policy(root, state), message)
        if not reason: return False
        identifier = hashlib.sha256(f'{mailbox_key}\0{validity}\0{uid}'.encode()).hexdigest()
        if identifier not in state['records']:
            cached = copy.deepcopy(message)
            folder = Path(root) / 'blocked_mail' / identifier
            folder.mkdir(exist_ok=True, mode=0o700)
            for number, attachment in enumerate(cached.get('attachments', [])):
                if attachment.get('path'):
                    source = Path(attachment['path'])
                    target = folder / f'attachment-{number}{source.suffix}'
                    shutil.copyfile(source, target); target.chmod(0o600)
                    attachment['path'] = str(target)
            state['records'][identifier] = {'id': identifier, 'sender': sender_address(cached.get('sender') or cached.get('from')),
                'subject': cached.get('subject', ''), 'received': cached.get('received') or cached.get('received_at') or cached.get('date', ''),
                'uid': str(uid), 'mailbox_key': str(mailbox_key), 'uidvalidity': str(validity), 'reason': reason,
                'state': 'blocked', 'message': cached, 'created_at': datetime.now(timezone.utc).isoformat()}
        return True

def queued_records(root, mailbox_key):
    with _store(root) as state:
        return [copy.deepcopy(record) for record in state['records'].values()
                if record.get('mailbox_key') == str(mailbox_key) and record.get('state') in ('queued', 'error', 'processing')]

def update_record(root, identifier, status, error=None, report=None):
    with _store(root) as state:
        record = state['records'].get(identifier)
        if record:
            record['state'] = status
            if error is not None: record['last_error'] = str(error)[:1000]
            elif status == 'summarized': record.pop('last_error', None)
            if report: record['report'] = str(report)

def cache_record(root, identifier, job):
    with _store(root) as state:
        record = state['records'].get(identifier)
        if record:
            for key in ('answer', 'target', 'new_notified'):
                if key in job: record[key] = job[key]
