"""Local report display/search; never contacts mail or AI services."""
import json
import os
import re
from datetime import datetime
from email.utils import parseaddr
from pathlib import Path
from .core import BEIJING
from .report_metadata import read_metadata

def report_paths(directory, suffixes=('.txt', '.md')):
    """Discover both old and nested layouts without following linked folders."""
    root = Path(directory)
    if not root.is_dir(): return []
    found = []
    for folder, directories, files in os.walk(root, followlinks=False):
        directories[:] = [name for name in directories
                          if not (Path(folder) / name).is_symlink()
                          and not (hasattr(Path(folder) / name, 'is_junction') and (Path(folder) / name).is_junction())]
        for name in files:
            path = Path(folder) / name
            if any(name.lower().endswith(suffix) for suffix in suffixes) and not path.is_symlink() and path.is_file():
                found.append(path)
    return found

def report_entry(path, home=None):
    path=Path(path)
    try: metadata=read_metadata(home, path) if home is not None else json.loads(path.with_suffix('.mail.json').read_text(encoding='utf-8'))
    except (OSError,ValueError): metadata={}
    stem=path.stem
    suffix=re.search(r'-(\d{2})-(\d{2})(?:-UID\d+(?:-\d+)?)?$',stem)
    title=metadata.get('subject') or (stem[:suffix.start()] if suffix else stem)
    day=next((parent.name for parent in path.parents if re.fullmatch(r'\d{4}-\d{2}-\d{2}', parent.name)), path.parent.name)
    timestamp=day+(' '+suffix[1]+':'+suffix[2] if suffix else '')
    try:
        received=datetime.fromisoformat(metadata['received']).astimezone(BEIJING)
        day=received.strftime('%Y-%m-%d'); timestamp=received.strftime('%Y-%m-%d %H:%M')
    except (KeyError,ValueError,TypeError): pass
    try: text=path.read_text(encoding='utf-8')
    except (OSError,UnicodeError): text=''
    attachments=metadata.get('attachments')
    sender=metadata.get('sender','') or (path.parent.name[5:] if path.parent.name.startswith('From ') else '')
    # Account is explicit in new metadata; older nested reports can recover it
    # from their layout. Legacy reports with no attribution remain visible.
    account=str(metadata.get('mailbox_account') or metadata.get('account') or metadata.get('account_email') or '')
    if not account and path.parent.name.startswith('From ') and re.fullmatch(r'\d{4}-\d{2}-\d{2}', path.parent.parent.name):
        account=path.parent.parent.parent.name
    sender_email=parseaddr(str(sender))[1].strip().casefold()
    if not sender_email and path.parent.name.startswith('From '):
        sender_email=path.parent.name[5:]
    searchable='\n'.join([title,sender,metadata.get('body',''),text]+[a.get('name','') for a in (attachments or [])]).casefold()
    return dict(path=path,title=title,sender=sender,day=day,time=timestamp,account=account,sender_email=sender_email,
                attachments=None if attachments is None else bool(attachments),searchable=searchable)

def matches(entry,query='',sender='',start='',end='',attachments='全部'):
    if start and entry['day']<start: return False
    if end and entry['day']>end: return False
    if sender.casefold() not in entry['sender'].casefold(): return False
    if attachments=='有附件' and entry['attachments'] is not True: return False
    if attachments=='无附件' and entry['attachments'] is not False: return False
    return all(term in entry['searchable'] for term in query.casefold().split())
