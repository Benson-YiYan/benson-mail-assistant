"""Inject desktop application OAuth configuration without logging its value."""
import argparse
import json
import os
from pathlib import Path
import plistlib


def main():
    parser = argparse.ArgumentParser()
    targets = parser.add_mutually_exclusive_group(required=True)
    targets.add_argument('--windows', type=Path)
    targets.add_argument('--macos', type=Path)
    args = parser.parse_args()
    secret = os.environ.get('MAILASSISTANT_GOOGLE_CLIENT_SECRET', '').strip()
    if args.windows:
        # Always replace the file so a subsequent unconfigured build cannot
        # accidentally reuse credentials from a previous build.
        args.windows.write_text(json.dumps({'google_client_secret': secret}), encoding='utf-8')
    else:
        info = plistlib.loads(args.macos.read_bytes())
        info['BensonMailGoogleOAuthClientSecret'] = secret
        args.macos.write_bytes(plistlib.dumps(info))
    print('OAuth build configuration prepared; configured=' + str(bool(secret)))


if __name__ == '__main__':
    main()
