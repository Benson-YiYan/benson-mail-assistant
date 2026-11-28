"""Read-only Gmail API mailbox adapter for the app's IMAP-shaped consumers."""
import base64
import datetime
import email
import email.policy
import json
import zlib
import re
import urllib.error
import urllib.parse
import urllib.request
import ssl
import http.client
import io

API = 'https://gmail.googleapis.com/gmail/v1/users/me'


def _request(token, path, params=None, *, method='GET', body=None, proxy=None, context=None):
    url = API + path
    if params:
        url += '?' + urllib.parse.urlencode(params)
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(url, data=data, method=method, headers={
        'Authorization': 'Bearer ' + token,
        'Accept': 'application/json',
        **({'Content-Type': 'application/json'} if data is not None else {}),
    })
    try:
        context = context or ssl.create_default_context()
        if proxy:
            from mailbox_config import proxy_socket
            parsed = urllib.parse.urlsplit(url)
            sock = proxy_socket(proxy, parsed.hostname, parsed.port or 443, timeout=30)
            with context.wrap_socket(sock, server_hostname=parsed.hostname) as secured:
                secured.settimeout(30)
                target = parsed.path + (('?' + parsed.query) if parsed.query else '')
                secured.sendall(request.method.encode('ascii') + b' ' + target.encode('ascii') + b' HTTP/1.1\r\n')
                headers = dict(request.header_items())
                headers['Host'] = parsed.hostname
                if data is not None: headers['Content-Length'] = str(len(data))
                for key, value in headers.items(): secured.sendall(f'{key}: {value}\r\n'.encode('latin-1'))
                secured.sendall(b'\r\n')
                if data is not None: secured.sendall(data)
                response = http.client.HTTPResponse(secured)
                response.begin()
                raw = response.read(4 * 1024 * 1024 + 1)
            if response.status >= 400:
                raise urllib.error.HTTPError(url, response.status, 'Gmail API error', response.headers, None)
            return json.loads(raw)
        else:
            opener = urllib.request.build_opener(urllib.request.HTTPSHandler(context=context))
            response_context = opener.open(request, timeout=30)
        with response_context as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        status = error.code
        # Never include Google response bodies; they may echo user data.
        raise RuntimeError(f'Gmail API request failed (HTTP {status}).') from None
    except (urllib.error.URLError, TimeoutError, OSError):
        raise RuntimeError('Gmail API network request failed.') from None


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


class _BytesSocket:
    def __init__(self, value): self._stream = io.BytesIO(value)
    def makefile(self, *args, **kwargs): return self._stream


class GmailMailbox:
    """Expose a constrained subset of IMAP calls; all Gmail operations stay read-only."""
    def __init__(self, token, folder='INBOX', proxy=None, context=None):
        self.token = token
        self.proxy = proxy
        self.context = context or ssl.create_default_context()
        self.folder = folder
        self.selected = None
        self._ids = {}
        self._validity = None

    def verify(self):
        _request(self.token, '/profile', proxy=self.proxy, context=self.context)

    def verify_messages(self):
        _request(self.token, '/messages', {'q': 'labelId:' + self.selected, 'maxResults': 1},
                 proxy=self.proxy, context=self.context)

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
            query = 'labelId:' + self.selected
            if len(args) >= 2 and str(args[1]).upper() == 'SINCE':
                since = datetime.datetime.strptime(args[2], '%d-%b-%Y').date()
                query += ' after:' + since.isoformat()
            if len(args) >= 4 and str(args[3]).upper() == 'BEFORE':
                before = datetime.datetime.strptime(args[4], '%d-%b-%Y').date()
                query += ' before:' + before.isoformat()
            ids, page = [], None
            while True:
                params = {'q': query, 'maxResults': 500}
                if page:
                    params['pageToken'] = page
                data = _request(self.token, '/messages', params, proxy=self.proxy, context=self.context)
                ids.extend(item['id'] for item in data.get('messages', []))
                page = data.get('nextPageToken')
                if not page:
                    break
            # Gmail API message IDs are stable hexadecimal identifiers. Map
            # them to stable numeric UIDs so progress survives list reordering.
            self._ids = {str(int(value, 16)): value for value in ids if re.fullmatch(r'[0-9a-fA-F]+', value)}
            return 'OK', [' '.join(self._ids).encode()]
        if command == 'fetch':
            sequence = str(args[0])
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
                item = _request(self.token, '/messages/' + urllib.parse.quote(message_id), {'format': 'full'}, proxy=self.proxy, context=self.context)
                payload = item.get('payload', {})
                hdr = _headers(payload)
                raw = _raw_message(item)
                internal = datetime.datetime.fromtimestamp(int(item.get('internalDate', 0)) / 1000, datetime.timezone.utc)
                flags = [b'\\Seen'] if 'UNREAD' not in item.get('labelIds', []) else []
                meta = (f'{uid} UID {uid} FLAGS ('.encode() + b' '.join(flags) + b') INTERNALDATE "' +
                        internal.strftime('%d-%b-%Y %H:%M:%S %z').encode() + b'"')
                if 'BODY.PEEK[HEADER.FIELDS' in sequence.upper():
                    header = email.message.EmailMessage(policy=email.policy.default)
                    for key in ('subject', 'from', 'date', 'x-spam-flag', 'x-spam-status', 'x-junk-status'):
                        if hdr.get(key):
                            header[key] = hdr[key]
                    rows.append((meta, header.as_bytes()))
                elif 'BODY.PEEK[]' in sequence.upper() or 'RFC822' in sequence.upper():
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
