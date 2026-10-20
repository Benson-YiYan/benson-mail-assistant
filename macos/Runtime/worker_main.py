"""Standalone bundled worker. Never requires system Python or developer tools."""
import json
import os
from pathlib import Path
import runpy
import sys

def main():
    args = sys.argv[1:]
    # These arguments precede the selected operation in launchd and tests.
    for option, variable in [('--home', 'BENSON_MAIL_HOME'), ('--app', 'BENSON_MAIL_APP')]:
        if option in args:
            index = args.index(option)
            os.environ[variable] = args[index + 1]
            del args[index:index + 2]
    operation = args.pop(0) if args else '--daemon'
    if operation == '--render-markdown':
        from markdown_render import render
        print(render(sys.stdin.read()), end='')
        return
    from runtime_paths import data_home
    home = data_home()
    home.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.umask(0o077)
    # Bundle a trusted CA store and also honor the user's macOS trust store.
    import certifi
    import truststore
    os.environ.setdefault('SSL_CERT_FILE', certifi.where())
    truststore.inject_into_ssl()
    if operation in ('--assistant-tools', '--assistant-features'):
        from assistant_tools import dispatch
        try:
            request = json.loads(Path(args[0]).read_text(encoding='utf-8'))
            print(json.dumps({'ok': True, **dispatch(home, request)}, ensure_ascii=False))
        except Exception as error:
            try:
                from assistant_tools import record_diagnostic
                record_diagnostic(home, locals().get('request', {}).get('action') or locals().get('request', {}).get('op') or operation.lstrip('-'), error)
            except Exception: pass
            detail = str(error) if isinstance(error, (ValueError, RuntimeError)) else type(error).__name__ + ': operation failed'
            print(json.dumps({'ok': False, 'error': detail}, ensure_ascii=False))
            raise SystemExit(1)
        return
    if operation == '--mail-policy':
        from mail_policy import policy_status, policy_save, policy_remove_records, policy_summarize_records
        try:
            if not args:
                raise ValueError('Missing policy request')
            request = json.loads(Path(args[0]).read_text(encoding='utf-8'))
            action = request.get('action')
            if action == 'status':
                result = policy_status(home)
            elif action == 'save':
                result = policy_save(home, request.get('policy'))
            elif action == 'remove_records':
                result = policy_remove_records(home, request.get('ids'))
            elif action == 'summarize_records':
                result = policy_summarize_records(home, request.get('ids'))
                (home / 'mail_watch').mkdir(parents=True, exist_ok=True, mode=0o700)
                (home / 'mail_watch' / 'check.request').touch()
            else:
                raise ValueError('Unknown policy action')
            print(json.dumps({'ok': True, **result}, ensure_ascii=False))
        except Exception as error:
            try:
                from assistant_tools import record_diagnostic
                record_diagnostic(home, locals().get('request', {}).get('action') or locals().get('request', {}).get('op') or operation.lstrip('-'), error)
            except Exception: pass
            detail = str(error) if isinstance(error, (ValueError, RuntimeError)) else type(error).__name__ + ': operation failed'
            print(json.dumps({'ok': False, 'error': detail}, ensure_ascii=False))
            raise SystemExit(1)
        return
    if operation in ('--report-retry', '--chat-history', '--chat-send'):
        from mail_chat import report_retry, chat_history, chat_send
        try:
            if operation == '--chat-send':
                if not args:
                    raise ValueError('Missing chat request')
                request = json.loads(Path(args[0]).read_text(encoding='utf-8'))
                result = chat_send(home, request['path'], request.get('text', ''), request.get('files', []))
            else:
                if not args:
                    raise ValueError('Missing report path')
                result = (report_retry if operation == '--report-retry' else chat_history)(home, args[0])
            print(json.dumps({'ok': True, **result}, ensure_ascii=False))
        except Exception as error:
            try:
                from assistant_tools import record_diagnostic
                record_diagnostic(home, locals().get('request', {}).get('action') or locals().get('request', {}).get('op') or operation.lstrip('-'), error)
            except Exception: pass
            detail = str(error) if isinstance(error, (ValueError, RuntimeError)) else type(error).__name__ + ': operation failed'
            print(json.dumps({'ok': False, 'error': detail}, ensure_ascii=False))
            raise SystemExit(1)
        return
    if operation in ('--language-status', '--download-language'):
        from language_packs import status, download, LanguagePackError
        try:
            result = status(home, 'macos') if operation == '--language-status' else download(home, args[0] if args else '', 'macos')
            print(json.dumps(result, ensure_ascii=False))
        except (LanguagePackError, OSError) as error:
            print(json.dumps({'ok': False, 'error': str(error)}, ensure_ascii=False))
            raise SystemExit(1)
        return
    modules = {'--daemon': 'mail_daemon', '--reader': 'mail_watch',
               '--mail_watch': 'mail_watch', '--mail_export': 'mail_export',
               '--test-api': 'ai_runner'}
    if operation == '--diagnose':
        from pypdf import PdfReader
        from zoneinfo import ZoneInfo
        print(json.dumps({'ok': True, 'frozen': bool(getattr(sys, 'frozen', False)),
                          'home': str(home), 'pdf': PdfReader.__name__,
                          'timezone': str(ZoneInfo('Asia/Shanghai'))}))
        return
    if operation == '--harness-fixture':
        from harness_smoke import fixture
        fixture()
        return
    if operation == '--harness-self-test':
        from harness_smoke import run
        print(json.dumps(run()))
        return
    if operation == '--self-test':
        from worker_selftest import run
        run()
        return
    if operation == '--update-install':
        from update_install import main as update_main
        raise SystemExit(update_main(args))
    if operation == '--outlook-token':
        from outlook_token import main as token_main
        token_main()
        return
    if operation == '--test-mail':
        from mail_connection_io import test
        test()
        return
    if operation not in modules:
        raise SystemExit('Unknown worker operation')
    sys.argv = [modules[operation], *args]
    runpy.run_module(modules[operation], run_name='__main__')

if __name__ == '__main__':
    main()
