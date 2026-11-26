"""Headless entry point shipped with the native WinUI app; no legacy GUI imports."""
import argparse
import json
from pathlib import Path
import sys


def _private_oauth_input(stream, maximum=8192):
    payload = stream.read(maximum + 1)
    if not isinstance(payload, bytes) or len(payload) > maximum:
        raise ValueError('OAuth private input is too large or invalid.')
    try:
        def unique_object(pairs):
            value = {}
            for key, item in pairs:
                if key in value:
                    raise ValueError('OAuth private input contains duplicate fields.')
                value[key] = item
            return value
        value = json.loads(payload.decode('utf-8', errors='strict'), object_pairs_hook=unique_object)
    except (UnicodeError, json.JSONDecodeError):
        raise ValueError('OAuth private input is not valid UTF-8 JSON.') from None
    if not isinstance(value, dict) or set(value) != {'client_secret', 'mailbox_proxy'}:
        raise ValueError('OAuth private input has unexpected fields.')
    client_secret = value['client_secret']
    proxy = value['mailbox_proxy']
    if not isinstance(client_secret, str) or not isinstance(proxy, dict) or set(proxy) != {
        'proxy_mode', 'proxy_host', 'proxy_port'
    }:
        raise ValueError('OAuth private input has invalid fields.')
    from benson_mail.mailbox_config import normalize_proxy
    normalized = normalize_proxy(proxy)
    return client_secret, normalized


def main():
    if '--delete-installer' in sys.argv:
        from benson_mail.installer_cleanup import cli
        return cli()
    if '--uninstall-native' in sys.argv:
        from benson_mail.uninstall import native_cli
        return native_cli()
    if '--harness-fixture' in sys.argv:
        from benson_mail.harness_smoke import fixture
        fixture()
        return 0
    if '--oauth-login' in sys.argv:
        from benson_mail.oauth_client import authorize
        index = sys.argv.index('--oauth-login')
        parser = argparse.ArgumentParser(prog='oauth-login')
        parser.add_argument('provider', choices=('google', 'microsoft'))
        parser.add_argument('email')
        parser.add_argument('client_id')
        parser.add_argument('--tenant', default='common')
        parser.add_argument('--private-input', action='store_true', required=True)
        values = parser.parse_args(sys.argv[index + 1:])
        try:
            client_secret, mailbox_proxy = _private_oauth_input(sys.stdin.buffer)
            credential = authorize(
                values.provider, values.email, values.client_id,
                tenant=values.tenant, client_secret=client_secret,
                mailbox_proxy=mailbox_proxy,
            )
            print(json.dumps(credential, ensure_ascii=False, separators=(',', ':')))
            return 0
        except Exception as error:
            message = str(error) if isinstance(error, (ValueError, RuntimeError)) else 'OAuth sign-in failed.'
            print(json.dumps({
                'ok': False,
                'error': message,
            }, ensure_ascii=False))
            return 1
    if '--harness-self-test' in sys.argv:
        from benson_mail.harness_smoke import run
        Path(sys.argv[sys.argv.index('--harness-self-test') + 1]).write_text(json.dumps(run()), encoding='utf-8')
        return 0
    if '--runtime-self-test' in sys.argv:
        from benson_mail.worker_smoke import run
        Path(sys.argv[sys.argv.index('--runtime-self-test') + 1]).write_text(json.dumps(run()), encoding='utf-8')
        return 0
    if '--language-status' in sys.argv or '--download-language' in sys.argv:
        from benson_mail.language_packs import status, download, LanguagePackError
        from benson_mail.platform_windows import app_dir
        try:
            root = Path(sys.argv[sys.argv.index('--home') + 1]) if '--home' in sys.argv else app_dir()
            result = (download(root, sys.argv[sys.argv.index('--download-language') + 1], 'windows')
                      if '--download-language' in sys.argv else status(root, 'windows'))
            print(json.dumps(result, ensure_ascii=False))
            return 0
        except (LanguagePackError, OSError, IndexError) as error:
            print(json.dumps({'ok': False, 'error': str(error)}, ensure_ascii=False))
            return 1
    parser = argparse.ArgumentParser()
    parser.add_argument('--bridge', action='store_true', required=True)
    parser.add_argument('--launcher')
    parser.add_argument('--fixture')
    args = parser.parse_args()
    from benson_mail.bridge import run
    run(args.launcher, args.fixture)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
