"""Headless entry point shipped with the native WinUI app; no legacy GUI imports."""
import argparse
import json
from pathlib import Path
import sys


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
