import datetime
import email.utils
import json
import os
import pathlib
import re
import sys
import unicodedata
from zoneinfo import ZoneInfo
from runtime_paths import data_home
from report_layout import report_folder, account_for, migrate_reports
from report_metadata import read_metadata, write_metadata
os.umask(0o077)
BASE = data_home()

def destination():
    config = BASE / 'settings.json'
    value = json.loads(config.read_text(encoding='utf-8')) if config.exists() else {}
    return pathlib.Path(value.get('output_dir') or str(pathlib.Path.home() / 'Documents' / '邮件')).expanduser()

def report_path(message, root=None):
    root = destination() if root is None else root
    stamp = message.get('received_at')
    received = datetime.datetime.fromisoformat(stamp) if stamp else email.utils.parsedate_to_datetime(message['date'])
    if received.tzinfo is None:
        received = received.replace(tzinfo=ZoneInfo('Asia/Shanghai'))
    received = received.astimezone(ZoneInfo('Asia/Shanghai'))
    title = unicodedata.normalize('NFC', message.get('subject') or '无主题')
    title = re.sub(r'[\\/:\x00-\x1f\x7f]', '＿', title).strip(' .')[:80] or '无主题'
    return report_folder(message, root) / (title + '-' + received.strftime('%H-%M') + '.md')

def export(message, answer):
    config_path = BASE / 'settings.json'
    config = json.loads(config_path.read_text(encoding='utf-8')) if config_path.exists() else {}
    message = dict(message)
    account = account_for(message, config)
    if account:
        message['mailbox_account'] = account
    migrate_reports(BASE, config)
    target = report_path(message)
    target.parent.mkdir(parents=True, exist_ok=True)
    identity = '邮件编号：' + str(message['uid']) + '\n'
    if message.get('mailbox_key'):
        identity += '邮箱标识：' + message['mailbox_key'] + '\n'
    original = target
    count = 0
    def conflicts(candidate):
        for existing in (candidate, candidate.with_suffix('.txt')):
            if existing.exists() and not existing.read_text(encoding='utf-8').startswith(identity):
                return True
        try:
            saved = read_metadata(BASE, candidate)
            return str(saved.get('uid')) != str(message['uid']) or saved.get('mailbox_key', '') != message.get('mailbox_key', '')
        except FileNotFoundError:
            return False
        except (ValueError, OSError):
            return True
    while conflicts(target):
        count += 1
        suffix = '-' + str(message['uid']) + ('-' + str(count) if count > 1 else '')
        target = original.with_stem(original.stem + suffix)
    legacy = target.with_suffix('.txt')
    if legacy.exists() and legacy.read_text(encoding='utf-8').startswith(identity) and not target.exists():
        return legacy
    temp = target.with_suffix('.md.tmp')
    temp.write_text(identity + answer.strip() + '\n', encoding='utf-8')
    temp.replace(target)
    write_metadata(BASE, target, message)
    return target

if __name__ == '__main__':
    message = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding='utf-8'))
    answer = pathlib.Path(sys.argv[2]).read_text(encoding='utf-8')
    print(json.dumps({'saved': str(export(message, answer))}, ensure_ascii=False))
