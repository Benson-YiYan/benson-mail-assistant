"""Read-only Gmail API mailbox adapter for the app's IMAP-shaped consumers."""
import base64
import datetime
import email
import email.policy
import email.parser
import http.client
import json
import ssl
import zlib
import re
import urllib.error
import urllib.parse
import urllib.request

API = 'https://gmail.googleapis.com/gmail/v1/users/me'


class GmailAPIError(RuntimeError):
    def __init__(self, status):
        self.status = int(status)
        super().__init__(f'Gmail API request failed (HTTP {self.status}).')


class _ProxyHTTPSConnection(http.client.HTTPSConnection):
    def __init__(self, host, *, proxy, **kwargs):
        super().__init__(host, **kwargs)
        self.proxy = proxy

    def connect(self):
        from .mailbox_config import proxy_socket
        raw = proxy_socket(self.proxy, self.host, self.port, self.timeout)
        self.sock = self._context.wrap_socket(raw, server_hostname=self.host)


def _request(token, path, params=None, *, method='GET', body=None, proxy=None, context=None):
    url = API + path
    if params:
        url += '?' + urllib.parse.urlencode(params, doseq=True)
    data = json.dumps(body).encode() if body is not None else None
    headers = {
        'Authorization': 'Bearer ' + token,
        'Accept': 'application/json',
        **({'Content-Type': 'application/json'} if data is not None else {}),
    }
    parsed = urllib.parse.urlsplit(url)
    tls = context or ssl.create_default_context()
    connection = (_ProxyHTTPSConnection(parsed.hostname, port=parsed.port or 443, proxy=proxy,
                                        timeout=30, context=tls)
                  if proxy else http.client.HTTPSConnection(parsed.hostname, parsed.port or 443,
                                                            timeout=30, context=tls))
    try:
        connection.request(method, urllib.parse.urlunsplit(('', '', parsed.path or '/', parsed.query, '')),
                           body=data, headers=headers)
        response = connection.getresponse()
        if not 200 <= response.status < 300:
            # Never include Google response bodies; they may echo user data.
            status = response.status
            response.read(65536)
            raise GmailAPIError(status)
        return json.loads(response.read(4 * 1024 * 1024 + 1))
    except GmailAPIError:
        raise
    except (http.client.HTTPException, ValueError, UnicodeDecodeError):
        raise RuntimeError('Gmail API returned an invalid response.') from None
    except (TimeoutError, OSError):
        raise RuntimeError('Gmail API network request failed.') from None
    finally:
        connection.close()


def _decode(data):
    if not data:
        return b''
    return base64.urlsafe_b64decode(data + '=' * ((4 - len(data) % 4) % 4))


def _headers(payload):
    return {str(item.get('name', '')).lower(): str(item.get('value', ''))
            for item in payload.get('headers', []) if isinstance(item, dict)}


def _walk(payload):
    yield payload
    for child in payload.get('parts', []) or []:
        yield from _walk(child)


def _raw_message(item):
    return _decode(item.get('raw'))


class GmailMailbox:
    """Expose a constrained subset of IMAP calls; all Gmail operations stay read-only."""
    def __init__(self, token, folder='INBOX', proxy=None, context=None):
        self.token = token
        self.folder = folder
        self.proxy = proxy
        self.context = context or ssl.create_default_context()
        self.selected = None
        self._ids = {}
        self._validity = None
        self._label_ids = {}

    def verify(self):
        _request(self.token, '/profile', proxy=self.proxy, context=self.context)

    def list(self):
        labels = _request(self.token, '/labels', proxy=self.proxy, context=self.context).get('labels', [])
        rows = []
        for label in labels:
            name = label.get('name', '')
            if not name:
                continue
            # Mark labels that can be selected as folders.
            rows.append((b'() "/" "' + name.replace('"', '\\"').encode('utf-8') + b'"', b''))
        return 'OK', rows

    def select(self, folder='INBOX', readonly=True):
        if not readonly:
            raise ValueError('Gmail mailbox must be opened read-only.')
        labels = _request(self.token, '/labels', proxy=self.proxy, context=self.context).get('labels', [])
        label = next((x for x in labels if x.get('name') == folder or x.get('id') == folder), None)
        if not label:
            return 'NO', [b'Unknown Gmail label']
        self.selected = label['id']
        self._validity = str(zlib.crc32(self.selected.encode('utf-8')) & 0x7fffffff or 1)
        return 'OK', [b'0']

    def response(self, name):
        if name.upper() == 'UIDVALIDITY':
            return name, [self._validity.encode() if self._validity else b'1']
        return name, [None]

    def uid(self, command, *args):
        command = command.lower()
        if command == 'search':
            query = ''
            if len(args) >= 2 and str(args[1]).upper() == 'SINCE':
                since = datetime.datetime.strptime(args[2], '%d-%b-%Y').date()
                query += ' after:' + since.isoformat()
            if len(args) >= 4 and str(args[3]).upper() == 'BEFORE':
                before = datetime.datetime.strptime(args[4], '%d-%b-%Y').date()
                query += ' before:' + before.isoformat()
            ids, page = [], None
            while True:
                params = {'labelIds': [self.selected], 'maxResults': 500}
                if query:
                    params['q'] = query
                if page:
                    params['pageToken'] = page
                data = _request(self.token, '/messages', params, proxy=self.proxy, context=self.context)
                ids.extend(item['id'] for item in data.get('messages', []))
                page = data.get('nextPageToken')
                if not page:
                    break
            # Gmail message IDs are hexadecimal and remain stable across searches,
            # unlike an ordinal generated from the current message list.
            self._ids = {str(int(value, 16)): value for value in ids if re.fullmatch(r'[0-9a-fA-F]+', value)}
            self._label_ids = {str(int(value, 16)): value for value in ids if re.fullmatch(r'[0-9a-fA-F]+', value)}
            return 'OK', [' '.join(self._ids).encode()]
        if command == 'fetch':
            sequence = str(args[0])
            fields = str(args[1]) if len(args) > 1 else ''
            header_only = 'HEADER.FIELDS' in fields.upper()
            requested = []
            for part in sequence.split(','):
                if ':' in part:
                    start, end = part.split(':', 1)
                    requested.extend(str(i) for i in range(int(start), int(end) + 1))
                else:
                    requested.append(part)
            rows = []
            for uid in requested:
                message_id = self._ids.get(uid)
                if not message_id:
                    continue
                params = {'format': 'metadata', 'metadataHeaders': [
                    'Subject', 'From', 'Date', 'X-Spam-Flag', 'X-Spam-Status', 'X-Junk-Status']}
                if not header_only:
                    params = {'format': 'raw'}
                item = _request(self.token, '/messages/' + urllib.parse.quote(message_id), params,
                                proxy=self.proxy, context=self.context)
                raw = _raw_message(item)
                parsed = email.parser.BytesParser(policy=email.policy.default).parsebytes(raw) if raw else None
                hdr = ({key.lower(): str(parsed.get(key, '')) for key in
                        ('Subject', 'From', 'Date', 'X-Spam-Flag', 'X-Spam-Status', 'X-Junk-Status')}
                       if parsed is not None else _headers(item.get('payload', {})))
                internal = datetime.datetime.fromtimestamp(int(item.get('internalDate', 0)) / 1000, datetime.timezone.utc)
                flags = [b'\\Seen'] if 'UNREAD' not in item.get('labelIds', []) else []
                meta = (f'{uid} UID {uid} FLAGS ('.encode() + b' '.join(flags) + b') INTERNALDATE "' +
                        internal.strftime('%d-%b-%Y %H:%M:%S %z').encode() + b'"')
                if header_only:
                    header = email.message.EmailMessage(policy=email.policy.default)
                    for key in ('subject', 'from', 'date', 'x-spam-flag', 'x-spam-status', 'x-junk-status'):
                        if hdr.get(key):
                            header[key] = hdr[key]
                    rows.append((meta, header.as_bytes()))
                elif 'BODY.PEEK[]' in fields.upper() or 'RFC822' in fields.upper():
                    rows.append((meta, raw))
                else:
                    rows.append((meta, b''))
            return 'OK', rows
        return 'BAD', [b'Unsupported read-only Gmail operation']

    def logout(self):
        return 'OK', [b'LOGOUT completed']


def send_message(token, account, recipient, subject, body, proxy=None, context=None):
    message = email.message.EmailMessage()
    message['From'] = account
    message['To'] = recipient
    message['Subject'] = subject
    message['Auto-Submitted'] = 'auto-generated'
    message.set_content(body)
    encoded = base64.urlsafe_b64encode(message.as_bytes()).decode().rstrip('=')
    return _request(token, '/messages/send', method='POST', body={'raw': encoded}, proxy=proxy, context=context)
