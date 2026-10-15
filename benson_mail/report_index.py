"""Local report display/search; never contacts mail or AI services."""
import json
import re
from datetime import datetime
from pathlib import Path
from .core import BEIJING

def report_entry(path):
    path=Path(path)
    try: metadata=json.loads(path.with_suffix('.mail.json').read_text(encoding='utf-8'))
    except (OSError,ValueError): metadata={}
    stem=path.stem
    suffix=re.search(r'-(\d{2})-(\d{2})(?:-UID\d+(?:-\d+)?)?$',stem)
    title=metadata.get('subject') or (stem[:suffix.start()] if suffix else stem)
    day=path.parent.name
    timestamp=day+(' '+suffix[1]+':'+suffix[2] if suffix else '')
    try:
        received=datetime.fromisoformat(metadata['received']).astimezone(BEIJING)
        day=received.strftime('%Y-%m-%d'); timestamp=received.strftime('%Y-%m-%d %H:%M')
    except (KeyError,ValueError,TypeError): pass
    try: text=path.read_text(encoding='utf-8')
    except (OSError,UnicodeError): text=''
    attachments=metadata.get('attachments')
    sender=metadata.get('sender','')
    searchable='\n'.join([title,sender,metadata.get('body',''),text]+[a.get('name','') for a in (attachments or [])]).casefold()
    return dict(path=path,title=title,sender=sender,day=day,time=timestamp,
                attachments=None if attachments is None else bool(attachments),searchable=searchable)

def matches(entry,query='',sender='',start='',end='',attachments='全部'):
    if start and entry['day']<start: return False
    if end and entry['day']>end: return False
    if sender.casefold() not in entry['sender'].casefold(): return False
    if attachments=='有附件' and entry['attachments'] is not True: return False
    if attachments=='无附件' and entry['attachments'] is not False: return False
    return all(term in entry['searchable'] for term in query.casefold().split())
