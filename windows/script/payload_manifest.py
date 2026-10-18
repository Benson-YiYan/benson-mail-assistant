"""Build exact legacy fingerprints and a bounded, hash-checked migration list."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil


def fingerprint(root):
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob('*')) if p.is_file()}


def snapshot(root, output, fixtures):
    files = fingerprint(root)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(files, indent=2), encoding='utf-8')
    fixtures.mkdir(parents=True, exist_ok=True)
    # Actual old build products; never execute them. Retain only these offline upgrade samples.
    candidates = ['System.Windows.Forms.dll', 'PresentationFramework.dll']
    for prefix in ('_internal/_tk_data/', '_internal/_tcl_data/', '_internal/PIL/'):
        candidates.append(next(name for name in files if name.startswith(prefix)))
    for name in candidates:
        target = fixtures / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(root / name, target)


def migration(root, baseline):
    previous = json.loads(baseline.read_text(encoding='utf-8'))
    current = fingerprint(root)
    remaining = {name.casefold() for name in current}
    obsolete = []
    for name, digest in previous.items():
        if name.casefold() in remaining or re.fullmatch(r'(?:Uninstall-)?BensonMail-\d{12}\.exe', name):
            continue
        if '..' in name or ':' in name or '\\' in name or name.startswith('/') or not re.fullmatch('[0-9a-f]{64}', digest):
            raise ValueError('Unsafe baseline manifest entry')
        obsolete.append(digest + '\t' + name)
    (root / '.benson-obsolete-files.tsv').write_text('\n'.join(obsolete), encoding='utf-8')
    (root / '.benson-payload.json').write_text(json.dumps(current, indent=2), encoding='utf-8')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=('snapshot', 'migration'))
    parser.add_argument('root', type=Path)
    parser.add_argument('manifest', type=Path)
    parser.add_argument('--fixtures', type=Path)
    args = parser.parse_args()
    if args.mode == 'snapshot': snapshot(args.root, args.manifest, args.fixtures)
    else: migration(args.root, args.manifest)
