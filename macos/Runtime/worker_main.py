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
