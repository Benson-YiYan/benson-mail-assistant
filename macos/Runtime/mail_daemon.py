"""Check mailbox cheaply; analyze new mail in a nonpersistent AI session."""
import datetime
import fcntl
import json
import os
import pathlib
import subprocess
import sys
import time
import uuid
from mail_prompt import analysis_prompt
from runtime_paths import data_home, child_command, codex_executable
from mailbox_config import mailbox_id, normalize, MailConnectionError
os.umask(0o077)
BASE = data_home()
DATA = BASE / 'mail_watch'
CONTROL = DATA
ACTIVE_HOME = BASE
ACTIVE_ID = None
READER = BASE / 'mail_watch.py'
EXPORTER = BASE / 'mail_export.py'
CODEX = '/Applications/ChatGPT.app/Contents/Resources/codex-cli/CodexCLI.app/Contents/MacOS/codex'
PYTHON = sys.executable
STATUS = DATA / 'service.json'
SETTINGS = BASE / 'settings.json'
CHECK_REQUEST = DATA / 'check.request'
NOTIFICATIONS = BASE / 'notifications' / 'pending'
APP = pathlib.Path(os.environ.get('BENSON_MAIL_APP', str(pathlib.Path.home() / 'Applications' / '邮件小秘书.app')))
DATA.mkdir(parents=True, exist_ok=True)

def settings():
    return json.loads(SETTINGS.read_text(encoding='utf-8')) if SETTINGS.exists() else {}

def runtime_text(zh, en, es):
    """Keep daemon-created notifications and fallback reports in the selected UI language."""
    try:
        language = settings().get('ui_language')
    except (OSError, ValueError, AttributeError):
        language = None  # Reporting a damaged settings file must not crash the error notification path.
    return {'en': en, 'es': es}.get(language, zh)


def unavailable_report(language=None):
    reports = {
        'zh': ('新邮件提醒', '这封邮件在读取前已移出收件箱或删除。', '谁发的', '未知。', '说了啥', '无法读取。',
               '我要干什么', '如需查看，请检查归档或垃圾箱。', '附件里有什么', '未知。', '我该怎么回Ta', '无法建议。'),
        'en': ('New email', 'This message was moved out of the inbox or deleted before it could be read.', 'Sender', 'Unknown.', 'Summary', 'Unavailable.',
               'What I need to do', 'Check the archive or trash if you need to read it.', 'Attachments', 'Unknown.', 'Suggested reply', 'Cannot suggest a reply.'),
        'es': ('Correo nuevo', 'Este mensaje se movió fuera de la bandeja de entrada o se eliminó antes de que pudiera leerse.', 'Remitente', 'Desconocido.', 'Resumen', 'No se puede leer.',
               'Qué debo hacer', 'Si necesitas consultarlo, revisa el archivo o la papelera.', 'Adjuntos', 'Desconocidos.', 'Respuesta sugerida', 'No es posible sugerir una respuesta.')
    }
    parts = reports.get(language, reports['zh'])
    return '\n\n'.join(f'## {number + 1}. {parts[number * 2]}\n\n{parts[number * 2 + 1]}' for number in range(6))


def enabled():
    value = settings()
    if not value.get('enabled', True):
        return False
    if ACTIVE_ID is not None and value.get('mailboxes') is not None:
        return any(mailbox_id(p['connection']) == ACTIVE_ID and p.get('enabled', True)
                   for p in value['mailboxes'])
    return True

def check_interval():
    value = settings().get('interval_seconds', 60)
    return max(10, min(86400, int(value)))

def publish(phase, **extra):
    previous = json.loads(STATUS.read_text()) if STATUS.exists() else {}
    previous.update({'running': True, 'mode': 'automatic-txt', 'phase': phase,
                     'heartbeat': datetime.datetime.now().astimezone().isoformat(), **extra})
    atomic(STATUS, json.dumps(previous, ensure_ascii=False))

def log(message):
    print(datetime.datetime.now().astimezone().isoformat(), message, flush=True)

def notify(message, title, report=None):
    from notification_policy import notifications_allowed, read_preferences
    if not notifications_allowed(read_preferences(SETTINGS)):
        return
    try:
        NOTIFICATIONS.mkdir(parents=True, exist_ok=True, mode=0o700)
        identifier = str(uuid.uuid4())
        atomic(NOTIFICATIONS / (identifier + '.json'), json.dumps({
            'id': identifier, 'title': title[:100], 'body': message[:500],
            'created': time.time(), 'report': report,
        }, ensure_ascii=False))
        if APP.exists():
            running = subprocess.run(['/usr/bin/pgrep', '-x', 'BensonMailMac'], capture_output=True, timeout=5)
            if running.returncode:
                subprocess.run(['/usr/bin/open', '-g', '-j', str(APP), '--args', '--background'],
                               capture_output=True, timeout=10, check=True)
    except (OSError, subprocess.SubprocessError):
        log('Native notification queued or unavailable; report retained')

def atomic(path, text):
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(text, encoding='utf-8')
    temp.replace(path)

def run_reader(*args):
    command = child_command('mail_watch', *args) if getattr(sys, 'frozen', False) else [PYTHON, str(READER), *args]
    environment = {**os.environ, 'BENSON_MAIL_HOME': str(ACTIVE_HOME)}
    result = subprocess.run(command, capture_output=True, text=True, timeout=180, env=environment)
    try:
        value = json.loads(result.stdout)
    except ValueError:
        raise RuntimeError('Mailbox reader returned no valid result')
    if result.returncode:
        if value.get('error') == 'MailConnectionError':
            raise MailConnectionError(value.get('detail', '')[:2000])
        raise RuntimeError(value.get('error', 'MailboxError') + ': ' + value.get('detail', '')[:1200])
    return value

def export_report(folder):
    command = child_command('mail_export', folder / 'mail.json', folder / 'answer.txt') if getattr(sys, 'frozen', False) else [PYTHON, str(EXPORTER), str(folder / 'mail.json'), str(folder / 'answer.txt')]
    result = subprocess.run(command, capture_output=True, text=True, timeout=30)
    if result.returncode:
        raise RuntimeError(runtime_text('报告保存失败，请检查所选文件夹的访问权限；AI 结果已缓存。', 'Report could not be saved. Check access to the selected folder; the AI result has been cached.', 'No se pudo guardar el informe. Revisa los permisos de la carpeta seleccionada; el resultado de la IA está guardado en caché.'))
    target = json.loads(result.stdout)['saved']
    atomic(folder / 'saved.json', json.dumps({'saved': target}, ensure_ascii=False))
    return target

def analyze(message):
    uid = str(message['uid'])
    publish('analyzing', current_subject=message.get('subject', runtime_text('无主题', 'No subject', 'Sin asunto')), error=None)
    folder = (BASE / 'blocked_mail' / message['_policy_record_id'] / 'work') if message.get('_policy_record_id') else DATA / uid
    folder.mkdir(parents=True, exist_ok=True)
    # Cached manual records are deliberately independent from current mailbox UID state.
    folder.mkdir(exist_ok=True)
    atomic(folder / 'mail.json', json.dumps(message, ensure_ascii=False, indent=2))
    answer = folder / 'answer.txt'
    marker = folder / 'notified'
    if not marker.exists():
        notice = runtime_text('发件人：', 'Sender: ', 'Remitente: ') + message.get('from', '')
        notice += '\n' + runtime_text('主题：', 'Subject: ', 'Asunto: ') + message.get('subject', '')
        notice += '\n' + runtime_text('正在整理六项内容，完成后自动保存 Markdown。', 'Preparing the six sections; the Markdown report will be saved automatically.', 'Preparando las seis secciones; el informe Markdown se guardará automáticamente.')
        notify(notice, runtime_text('你有一封新邮件', 'You have a new email', 'Tienes un correo nuevo'))
        atomic(marker, datetime.datetime.now().astimezone().isoformat())
    if not answer.exists() or not answer.read_text(encoding='utf-8').strip():
        if message.get('unavailable'):
            fallback = unavailable_report(settings().get('ui_language'))
            atomic(answer, fallback)
            message['date'] = datetime.datetime.now(datetime.timezone.utc).strftime('%a, %d %b %Y %H:%M:%S %z')
            atomic(folder / 'mail.json', json.dumps(message, ensure_ascii=False))
        else:
            prompt = analysis_prompt(settings().get('ui_language'))
            temp = folder / 'answer.generated.txt'
            temp.unlink(missing_ok=True)
            if settings().get('ai_provider', 'codex') in ('api', 'deepseek_harness'):
                from ai_runner import analyze_api
                atomic(temp, analyze_api(message, folder, language=settings().get('ui_language', 'zh')))
                failed = False
            else:
                with (folder / 'analysis.log').open('w', encoding='utf-8') as out:
                    result = subprocess.run([codex_executable(), 'exec', '--ephemeral', '--skip-git-repo-check', '-s', 'read-only', '--color', 'never', '-C', str(folder), '-o', str(temp), prompt], stdout=out, stderr=subprocess.STDOUT, timeout=900)
                failed = result.returncode != 0
            if failed or not temp.exists() or not temp.read_text(encoding='utf-8').strip():
                raise RuntimeError('AI analysis failed for UID ' + uid + '; message retained')
            if settings().get('ai_provider', 'codex') == 'codex':
                from assistant_tools import record_usage
                try: record_usage('codex', '', root=BASE)
                except Exception: pass
            temp.replace(answer)
    target = export_report(folder)
    if not message.get('_policy_record_id'):
        run_reader('ack', uid)
    notify(runtime_text('六项报告已保存：\n', 'Six-section report saved:\n', 'Informe de seis secciones guardado:\n') + target, runtime_text('✅ 新邮件 Markdown 已完成', '✅ New email Markdown report ready', '✅ Informe Markdown del correo listo'), report=target)
    log('report saved for UID ' + uid + ': ' + target)
    publish('idle', latest_report=target, current_subject=None)

def main():
    with (CONTROL / 'daemon.lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        monitor()

def mailbox_profiles(value):
    if value.get('mailboxes') is None:
        return [None]  # Legacy single-mailbox installation.
    profiles = value['mailboxes']
    identities = [mailbox_id(normalize(p['connection'])) for p in profiles]
    if len(identities) != len(set(identities)):
        raise ValueError(runtime_text('邮箱配置存在重复连接，请重新保存。', 'Duplicate mailbox connections found. Save the mailbox settings again.', 'Hay conexiones de correo duplicadas. Vuelve a guardar la configuración del buzón.'))
    return [p for p in profiles if p.get('enabled', True)]


def activate_profile(profile, value):
    global DATA, ACTIVE_HOME, ACTIVE_ID
    if profile is None:
        DATA, ACTIVE_HOME, ACTIVE_ID = CONTROL, BASE, None
        return
    connection = profile['connection']
    identifier = mailbox_id(normalize(connection))
    ACTIVE_ID = identifier
    ACTIVE_HOME = BASE / 'mailboxes' / identifier
    DATA = ACTIVE_HOME / 'mail_watch'
    DATA.mkdir(parents=True, exist_ok=True)
    # Preserve the original baseline and pending work when upgrading an existing mailbox.
    original = CONTROL / 'state.json'
    if original.exists() and not (DATA / 'state.json').exists():
        state = json.loads(original.read_text())
        legacy_id = state.get('mailbox_key')
        first = value.get('mailboxes', [{}])[0].get('connection', {})
        if legacy_id == identifier or (not legacy_id and first and mailbox_id(first) == identifier):
            for path in CONTROL.iterdir():
                if path.name in ('daemon.lock', 'service.json', 'check.request'):
                    continue
                target = DATA / path.name
                if not target.exists():
                    path.rename(target)
    archived = BASE / 'mailbox-archives' / identifier / 'mail_watch'
    if archived.exists() and not (DATA / 'state.json').exists():
        for path in archived.iterdir():
            if not (DATA / path.name).exists():
                path.rename(DATA / path.name)
    atomic(ACTIVE_HOME / 'settings.json', json.dumps({**value, 'mailbox': connection}, ensure_ascii=False))


def check_profiles():
    """Each account failure is isolated; all enabled accounts are checked in a cycle."""
    global DATA, ACTIVE_HOME, ACTIVE_ID
    value = settings()
    profiles = mailbox_profiles(value)
    failures = []
    pending = []
    for profile in profiles:
        if not settings().get('enabled', True):
            break
        try:
            activate_profile(profile, value)
            if not enabled():
                continue
            from mail_policy import queued_records, update_record
            profile_identity = ACTIVE_ID
            if profile_identity is None and (DATA / 'state.json').exists():
                profile_identity = json.loads((DATA / 'state.json').read_text()).get('mailbox_key')
            for record in queued_records(BASE, profile_identity):
                if not enabled(): break
                update_record(BASE, record['id'], 'processing')
                try:
                    cached = record['message']
                    cached['_policy_record_id'] = record['id']
                    analyze(cached)
                    update_record(BASE, record['id'], 'summarized')
                except Exception as error:
                    update_record(BASE, record['id'], 'error', error)
                    raise
            publish('checking', error=None, current_account=profile['connection']['account'] if profile else None)
            result = run_reader()
            if result.get('pending_messages', 0):
                for message in json.loads(pathlib.Path(result['report']).read_text(encoding='utf-8')):
                    if not enabled():
                        break
                    from mail_policy import intercept
                    if intercept(BASE, message, message.get('mailbox_key', ACTIVE_ID), message.get('uidvalidity', ''), message['uid']):
                        run_reader('ack', str(message['uid']))
                        continue
                    analyze(message)
            state = DATA / 'state.json'
            if state.exists():
                pending.extend(json.loads(state.read_text()).get('pending', []))
        except Exception as error:
            from assistant_tools import record_diagnostic
            try: record_diagnostic(BASE, 'mail_check', error)
            except Exception: pass
            label = profile['connection']['account'] if profile else runtime_text('邮箱', 'Mailbox', 'Buzón')
            detail = str(error) if isinstance(error, MailConnectionError) else type(error).__name__ + runtime_text('，请测试邮箱和 AI 连接；未完成邮件会重试。', ': test the mailbox and AI connections; unfinished messages will be retried.', ': prueba las conexiones del buzón y de la IA; se reintentará el procesamiento de los mensajes pendientes.')
            failures.append(label + '：' + detail)
    DATA, ACTIVE_HOME, ACTIVE_ID = CONTROL, BASE, None
    return failures, pending, len(profiles)


def monitor():
    from report_layout import migrate_reports
    try:
        migration = migrate_reports(BASE, settings())
        if migration.get('errors'):
            log('Report layout migration retained reports needing attention; see migration journal')
    except (OSError, ValueError, RuntimeError):
        log('Report layout migration unavailable; existing reports retained')
    last_error = None
    log('automatic Markdown monitor started; empty checks never invoke AI')
    next_check = 0
    last_started = None
    previous_interval = check_interval()
    last_heartbeat = 0
    while True:
        try:
            if not enabled():
                if time.monotonic() - last_heartbeat >= 15 or next_check != 0 or last_started is not None:
                    publish('paused', current_subject=None)
                    last_heartbeat = time.monotonic()
                time.sleep(1)
                next_check = 0
                last_started = None
                continue
            interval = check_interval()
            if interval != previous_interval:
                next_check = last_started + interval if last_started is not None else 0
                previous_interval = interval
            if time.monotonic() < next_check and not CHECK_REQUEST.exists():
                if time.monotonic() - last_heartbeat >= 15:
                    publish('error' if last_error else 'idle')
                    last_heartbeat = time.monotonic()
                time.sleep(1)
                continue
            CHECK_REQUEST.unlink(missing_ok=True)
            started = time.monotonic()
            last_started = started
            last_heartbeat = started
            failures, pending, count = check_profiles()
            detail = '\n'.join(failures) if failures else None
            publish(('error' if failures else 'idle') if enabled() else 'paused',
                    last_check=datetime.datetime.now().astimezone().isoformat(), pending=pending,
                    error=detail, current_subject=None, current_account=None, mailbox_count=count)
            if detail and detail != last_error:
                log(detail)
                notify(detail, runtime_text('邮件小秘书需要检查', 'Email Assistant needs attention', 'Asistente de correo electrónico necesita atención'))
            last_error = detail
            log('mailbox check succeeded')
            next_check = started + interval
        except Exception as error:
            detail = str(error)
            publish('error', error=detail, current_subject=None)
            log(detail)
            if detail != last_error:
                notify(detail, runtime_text('邮件小秘书需要检查', 'Email Assistant needs attention', 'Asistente de correo electrónico necesita atención'))
            last_error = detail
            next_check = time.monotonic() + check_interval()
            time.sleep(1)

if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == '--export-one':
        print(json.dumps({'saved': export_report(pathlib.Path(sys.argv[2]))}, ensure_ascii=False), flush=True)
    elif len(sys.argv) > 1 and sys.argv[1] == '--analyze-one':
        analyze(json.loads(pathlib.Path(sys.argv[2]).read_text(encoding='utf-8')))
    else:
        main()
