"""Private original-mail records, separate from user-facing report documents."""
import hashlib
import json
import os
from pathlib import Path
import tempfile

MAX_METADATA = 4 * 1024 * 1024


def _linked(path):
    path = Path(path)
    junction = getattr(path, 'is_junction', None)
    return path.is_symlink() or (junction is not None and junction())


def _safe(path, root):
    path, root = Path(path), Path(root)
    if not path.is_relative_to(root):
        raise ValueError('Metadata path is outside the application data directory.')
    for item in (path, *path.parents):
        if item == root.parent:
            break
        if _linked(item):
            raise ValueError('Original mail metadata does not follow symbolic links or junctions.')


def metadata_path(home, report):
    canonical = os.path.normcase(str(Path(report).expanduser().resolve()))
    return Path(home).expanduser().resolve() / 'report_metadata' / (hashlib.sha256(canonical.encode()).hexdigest() + '.json')


def _read(path):
    if _linked(path):
        raise ValueError('Original mail metadata does not follow symbolic links or junctions.')
    if path.stat().st_size > MAX_METADATA:
        raise ValueError('Original mail metadata exceeds the 4 MB limit; nothing was sent to AI.')
    value = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(value, dict):
        raise ValueError('Original mail metadata must be an object.')
    return value


def read_metadata(home, report):
    """Prefer the private record, retaining read compatibility with old exports."""
    internal = metadata_path(home, report)
    _safe(internal, internal.parent.parent)
    if internal.exists() or _linked(internal):
        return _read(internal)
    return _read(Path(report).with_suffix('.mail.json'))


def write_metadata(home, report, message, *, replace=True):
    """Write a complete private record; migration never replaces an existing record."""
    if not isinstance(message, dict):
        raise ValueError('Original mail metadata must be an object.')
    path = metadata_path(home, report)
    _safe(path, path.parent.parent)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if not replace and path.exists():
        if _read(path) != message:
            raise ValueError('Private original-mail data differs; both records were retained.')
        return path
    data = json.dumps(message, ensure_ascii=False, indent=2).encode('utf-8')
    if len(data) > MAX_METADATA:
        raise ValueError('Original mail metadata exceeds the 4 MB limit.')
    fd, temporary = tempfile.mkstemp(prefix='.report-metadata-', suffix='.tmp', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        if replace:
            os.replace(temporary, path)
        elif os.name == 'nt':
            try:
                os.rename(temporary, path)
            except FileExistsError:
                if _read(path) != message:
                    raise ValueError('Private original-mail data differs; both records were retained.')
        else:
            try:
                os.link(temporary, path)
            except FileExistsError:
                if _read(path) != message:
                    raise ValueError('Private original-mail data differs; both records were retained.')
    finally:
        Path(temporary).unlink(missing_ok=True)
    return path


def remove_metadata(home, report):
    path = metadata_path(home, report)
    _safe(path, path.parent.parent)
    path.unlink(missing_ok=True)


def migrate_metadata(home, output):
    """Relocate matching legacy sidecars only after verified, exclusive private writes."""
    output = Path(output).expanduser()
    result = {'moved': 0, 'skipped': 0, 'errors': []}
    if not output.is_dir() or _linked(output):
        return result
    for directory, directories, files in os.walk(output, followlinks=False):
        directories[:] = [name for name in directories if not name.startswith('.') and not _linked(Path(directory) / name)]
        for name in files:
            if not name.endswith('.mail.json'):
                continue
            sidecar = Path(directory) / name
            if _linked(sidecar):
                result['skipped'] += 1
                continue
            stem = name[:-len('.mail.json')]
            reports = [sidecar.with_name(stem + suffix) for suffix in ('.md', '.txt')]
            reports = [p for p in reports if p.is_file() and not _linked(p)]
            if not reports:
                result['skipped'] += 1
                continue
            try:
                message = _read(sidecar)
                original_bytes = sidecar.read_bytes()
                for report in reports:
                    write_metadata(home, report, message, replace=False)
                    if read_metadata(home, report) != message:
                        raise ValueError('Private original-mail verification failed; original was retained.')
                # Do not remove a sidecar changed concurrently by an old app instance.
                if sidecar.read_bytes() != original_bytes:
                    raise ValueError('Original-mail data changed during migration; original was retained.')
                sidecar.unlink()
                result['moved'] += 1
            except (OSError, ValueError, TypeError) as error:
                result['errors'].append({'source': str(sidecar), 'error': type(error).__name__ + ': ' + str(error)[:300]})
    return result
