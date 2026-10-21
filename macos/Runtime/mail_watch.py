import email
import email.policy
import datetime
import imaplib
import json
import pathlib
import re
import subprocess
import sys
from runtime_paths import data_home
from mail_connection_io import load
from mailbox_config import connect, mailbox_id, MailConnectionError, mail_error, redact_mail_error, require_ok

ROOT = data_home() / 'mail_watch'
STATE = ROOT / 'state.json'
ROOT.mkdir(parents=True, exist_ok=True, mode=0o700)

def save(value):
    temp = STATE.with_suffix('.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False))
    temp.chmod(0o600)
    temp.replace(STATE)

if len(sys.argv) > 1 and sys.argv[1] == 'ack':
    state = json.loads(STATE.read_text())
    ids = set(sys.argv[2:])
    state['pending'] = [u for u in state['pending'] if str(u) not in ids]
    save(state)
    print(json.dumps({'acknowledged': list(ids)}))
    sys.exit(0)

secret = ''
connection = None
stage = '连接邮箱'
try:
    connection, secret = load()
    client = connect(connection, secret)
    identity = mailbox_id(connection)
    stage = 'UIDVALIDITY 读取邮件文件夹标识'
    validity = client.response('UIDVALIDITY')[1][0].decode()
    stage = 'UID SEARCH 检查邮件编号'
    uid_data = require_ok(client.uid('search', None, 'ALL'), 'UID SEARCH')
    current_uids = {int(u) for u in uid_data[0].split()}
    stage = 'IMAP read-only retrieval or synchronization' if connection.get('ui_language') == 'en' else 'IMAP 只读读取或同步'
    next_uid = max(current_uids, default=0) + 1
    if not STATE.exists():
        save({'uidvalidity': validity, 'next_uid': next_uid, 'pending': [], 'mailbox_key': identity})
        print(json.dumps({'initialized': True, 'existing_messages': len(current_uids), 'new_messages': 0}))
    else:
        state = json.loads(STATE.read_text())
        if state.get('mailbox_key', identity) != identity:
            raise ValueError('邮箱连接与本地进度不匹配，请在应用内切换邮箱，避免混用邮件。')
        state['mailbox_key'] = identity
        if state['uidvalidity'] != validity:
            raise RuntimeError('Mailbox UIDVALIDITY changed; resynchronization required. State preserved.')
        available = current_uids
        fresh = sorted(u for u in available if u >= state['next_uid'])
        state['pending'] = sorted(set(state['pending']) | set(fresh))
        state['next_uid'] = max(state['next_uid'], next_uid)
        save(state)
        from assistant_tools import consume_history, _root
        def queue_history(uids):
            state['pending'] = sorted(set(state['pending']) | (set(uids) & available))
            save(state)
        consume_history(_root(), identity, validity, queue_history)
        messages = []
        for uid in state['pending']:
            if uid not in available:
                messages.append({'uid': uid, 'uidvalidity': validity, 'unavailable': True, 'mailbox_key': identity,
                                 'mailbox_account': connection['account']})
                continue
            status, data = client.uid('fetch', str(uid), '(INTERNALDATE BODY.PEEK[] FLAGS)')
            if status != 'OK':
                raise RuntimeError('Message fetch failed')
            fetched = next(item for item in data if isinstance(item, tuple))
            raw = fetched[1]
            internaldate = re.search(rb'INTERNALDATE "([^"]+)"', fetched[0])
            received_at = datetime.datetime.strptime(internaldate.group(1).decode(), '%d-%b-%Y %H:%M:%S %z').isoformat() if internaldate else datetime.datetime.now(datetime.timezone.utc).isoformat()
            folder = ROOT / str(uid)
            folder.mkdir(exist_ok=True, mode=0o700)
            raw_path = folder / 'message.eml'
            raw_path.write_bytes(raw)
            raw_path.chmod(0o600)
            msg = email.message_from_bytes(raw, policy=email.policy.default)
            bodies, attachments = [], []
            for index, part in enumerate(msg.walk()):
                if part.is_multipart():
                    continue
                filename = part.get_filename()
                if filename or part.get_content_disposition() == 'attachment':
                    name = filename or 'attachment'
                    extension = pathlib.Path(name).suffix
                    if not re.fullmatch(r'\.[A-Za-z0-9]{1,10}', extension):
                        extension = '.bin'
                    path = folder / ('attachment-' + str(index) + extension)
                    payload = part.get_payload(decode=True) or b''
                    path.write_bytes(payload)
                    path.chmod(0o600)
                    attachments.append({'filename': name, 'type': part.get_content_type(), 'bytes': len(payload), 'path': str(path)})
                elif part.get_content_type() in ('text/plain', 'text/html'):
                    try:
                        bodies.append({'type': part.get_content_type(), 'text': part.get_content()})
                    except Exception:
                        bodies.append({'type': part.get_content_type(), 'text': (part.get_payload(decode=True) or b'').decode('utf-8', errors='replace')})
            from mail_policy import spam_metadata
            metadata = spam_metadata(msg, fetched[0].decode('utf-8', errors='replace'), connection.get('mail_folder', 'INBOX'))
            messages.append({**metadata, 'uidvalidity': validity, 'uid': uid, 'mailbox_key': identity, 'mailbox_account': connection['account'], 'from': str(msg.get('From', '')), 'subject': str(msg.get('Subject', '')), 'date': str(msg.get('Date', '')), 'received_at': received_at, 'reply_to': str(msg.get('Reply-To', '')), 'bodies': bodies, 'attachments': attachments})
        report = ROOT / 'pending.json'
        report.write_text(json.dumps(messages, ensure_ascii=False, indent=2))
        report.chmod(0o600)
        print(json.dumps({'new_messages': len(fresh), 'pending_messages': len(messages), 'report': str(report)}, ensure_ascii=False))
    client.logout()
except Exception as error:
    if connection and isinstance(error, (imaplib.IMAP4.error, OSError)):
        error = mail_error(error, connection, secret, stage, connection.get('ui_language', 'zh'))
    print(json.dumps({'error': type(error).__name__, 'detail': str(error) if isinstance(error, MailConnectionError) else redact_mail_error(error, secret)}, ensure_ascii=False))
    sys.exit(1)
