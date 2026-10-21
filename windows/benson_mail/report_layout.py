"""Shared report paths and restartable migration; never contacts mail or AI."""
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from email.utils import parseaddr, parsedate_to_datetime
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
import time
import unicodedata

BEIJING = timezone(timedelta(hours=8))
PATH_KEYS = {"report", "saved", "target", "latest_report", "path"}


def component(value, fallback):
    value = unicodedata.normalize("NFC", str(value or "")).strip()
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f\x7f]', "_", value).strip(" .")
    if not cleaned:
        return fallback
    reserved = cleaned.split(".")[0].upper() in (
        ["CON", "PRN", "AUX", "NUL"] + [f"{p}{n}" for p in ("COM", "LPT") for n in range(1, 10)])
    if reserved:
        cleaned = "_" + cleaned
    if cleaned != value or len(cleaned.encode("utf-8")) > 180:
        while len(cleaned.encode("utf-8")) > 160:
            cleaned = cleaned[:-1]
        cleaned += "-" + hashlib.sha256(value.encode()).hexdigest()[:10]
    return cleaned


def mailbox_account(message):
    return str(message.get("mailbox_account") or message.get("recipient_account") or "").strip().lower()


def sender_address(message):
    raw = str(message.get("sender") or message.get("from") or "")
    address = parseaddr(raw)[1].strip().lower()
    return address if "@" in address else ""


def received_datetime(message, fallback=None):
    for name in ("received_at", "received", "date"):
        value = message.get(name)
        if not value:
            continue
        try:
            stamp = datetime.fromisoformat(str(value))
        except ValueError:
            try:
                stamp = parsedate_to_datetime(str(value))
            except (ValueError, TypeError, OverflowError):
                continue
        if stamp is not None:
            return (stamp.replace(tzinfo=BEIJING) if stamp.tzinfo is None else stamp).astimezone(BEIJING)
    if fallback:
        return datetime.fromisoformat(str(fallback)).replace(tzinfo=BEIJING)
    raise ValueError("The original mail has no valid received date.")


def report_folder(message, root, fallback_date=None):
    return (Path(root) / component(mailbox_account(message), "unknown-account")
            / received_datetime(message, fallback_date).strftime("%Y-%m-%d")
            / ("From " + component(sender_address(message), "unknown-sender")))


def report_files(root):
    """Read old and new layouts without traversing symbolic-link directories."""
    root = Path(root)
    if not root.is_dir():
        return
    for folder, directories, files in os.walk(root, followlinks=False):
        directories[:] = [name for name in directories if not (Path(folder) / name).is_symlink()
                          and not name.startswith(".")]
        for name in files:
            path = Path(folder) / name
            if path.suffix.lower() in (".md", ".txt") and not path.is_symlink():
                yield path


def account_for(message, config):
    account = mailbox_account(message)
    if account:
        return account
    try:
        if __package__:
            from .mailbox_config import mailbox_id
        else:
            from mailbox_config import mailbox_id
        profiles = config.get("mailboxes") or [config.get("mailbox") or config]
        accounts = set()
        for profile in profiles:
            connection = profile.get("connection") or profile
            value = str(connection.get("account") or "").strip().lower()
            if not value:
                continue
            accounts.add(value)
            if message.get("mailbox_key") and mailbox_id(connection) == message["mailbox_key"]:
                return value
        if len(accounts) == 1:
            return next(iter(accounts))
    except (ValueError, KeyError, TypeError):
        pass
    return ""


def _atomic(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".report-layout-", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


@contextmanager
def _migration_lock(home):
    home.mkdir(parents=True, exist_ok=True)
    with (home / "report-layout.lock").open("a+b") as stream:
        stream.seek(0)
        stream.write(b"0")
        stream.flush()
        stream.seek(0)
        deadline = time.monotonic() + 30
        while True:
            try:
                if os.name == "nt":
                    import msvcrt
                    msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError:
                if time.monotonic() >= deadline:
                    raise RuntimeError("Report folder migration is still running.")
                time.sleep(.1)
        try:
            yield
        finally:
            stream.seek(0)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream, fcntl.LOCK_UN)


def _safe(path, root):
    path, root = Path(path), Path(root)
    if not path.is_relative_to(root):
        raise ValueError("Report migration path is outside the selected folder.")
    for candidate in [path, *path.parents]:
        if candidate == root.parent:
            break
        if candidate.is_symlink():
            raise ValueError("Report migration does not follow symbolic links.")


def _patch_paths(value, mapping):
    if isinstance(value, dict):
        return {key: mapping.get(item, item) if key in PATH_KEYS and isinstance(item, str)
                else _patch_paths(item, mapping) for key, item in value.items()}
    if isinstance(value, list):
        return [_patch_paths(item, mapping) for item in value]
    return value


def _rewrite_references(home, mapping):
    for directory in ("mail_watch", "mailboxes", "state", "blocked_mail", "reply_drafts", "notifications"):
        folder = home / directory
        if not folder.is_dir():
            continue
        for parent, directories, files in os.walk(folder, followlinks=False):
            directories[:] = [name for name in directories if not (Path(parent) / name).is_symlink()]
            for name in files:
                path = Path(parent) / name
                if path.suffix != ".json" or path.is_symlink():
                    continue
                # Do not read original messages, attachment text, or credential configuration.
                if name in ("mail.json", "pending.json", "settings.json", "config.json"):
                    continue
                try:
                    value = json.loads(path.read_text(encoding="utf-8"))
                except (ValueError, UnicodeError):
                    continue
                changed = _patch_paths(value, mapping)
                if changed != value:
                    _atomic(path, changed)
    chats = home / "mail_chats"
    for old, new in mapping.items():
        old_id = hashlib.sha256(os.path.normcase(old).encode()).hexdigest()
        new_id = hashlib.sha256(os.path.normcase(new).encode()).hexdigest()
        source, target = chats / (old_id + ".json"), chats / (new_id + ".json")
        if not source.is_file() or source.is_symlink():
            continue
        value = json.loads(source.read_text(encoding="utf-8"))
        changed = _patch_paths(value, {old: new})
        if target.exists() and json.loads(target.read_text(encoding="utf-8")) != changed:
            raise ValueError("A conversation already exists at the new report location; originals were retained.")
        _atomic(target, changed)
        source.unlink()


def _create_complete_file(path, data):
    """Commit a complete file without replacing anything another process created."""
    if path.exists():
        if path.read_bytes() != data:
            raise ValueError("Report migration destination is occupied; originals were retained.")
        return
    fd, name = tempfile.mkstemp(prefix=".report-layout-", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        if os.name == "nt":
            os.rename(name, path)  # Windows rename refuses an existing destination.
        else:
            os.link(name, path)  # Atomic, exclusive creation of the completed file.
    finally:
        Path(name).unlink(missing_ok=True)


def _move_report(home, output, configured_output, item):
    source, target = Path(item["source"]), Path(item["target"])
    if not source.is_relative_to(output) or not target.is_relative_to(output):
        return False
    old_meta, new_meta = source.with_suffix(".mail.json"), target.with_suffix(".mail.json")
    for path in (source, target, old_meta, new_meta):
        _safe(path, output)
    mapping = {str(source): str(target), str(configured_output / source.relative_to(output)): str(target)}
    if not source.exists() and target.is_file() and new_meta.is_file():
        # Recover a crash after deleting the source but before committing the journal.
        _rewrite_references(home, mapping)
        if old_meta.is_file():
            metadata = json.loads(old_meta.read_text(encoding="utf-8"))
            if item["account"]:
                metadata["mailbox_account"] = item["account"]
            if json.loads(new_meta.read_text(encoding="utf-8")) != metadata:
                raise ValueError("Original metadata changed; both copies were retained.")
            old_meta.unlink()
        return True
    if not source.is_file() or not old_meta.is_file():
        return False
    target.parent.mkdir(parents=True, exist_ok=True)
    metadata = json.loads(old_meta.read_text(encoding="utf-8"))
    if item["account"]:
        metadata["mailbox_account"] = item["account"]
    _create_complete_file(target, source.read_bytes())
    _create_complete_file(new_meta, json.dumps(metadata, ensure_ascii=False, indent=2).encode("utf-8"))
    _rewrite_references(home, mapping)
    source.unlink()
    old_meta.unlink()
    return True


def migrate_reports(home, config, windows=False):
    """Only migrate recognized legacy reports; journal every move before touching data."""
    # Unconfigured startup must not touch the real default report directory.
    if not config.get("output_dir") and not any(config.get(key) for key in ("mailboxes", "mailbox", "account", "connection")):
        return {"moved": 0, "skipped": 0, "errors": []}
    home = Path(home).expanduser().resolve()
    configured_output = Path(config.get("output_dir") or Path.home() / "Documents" / "邮件").expanduser().absolute()
    output = configured_output.resolve()
    if not output.is_dir():
        return {"moved": 0, "skipped": 0, "errors": []}
    with _migration_lock(home):
        journal = home / "report-layout-migration.json"
        try:
            state = json.loads(journal.read_text()) if journal.exists() else {"schema_version": 1, "moves": []}
            moves = state["moves"]
            if state.get("schema_version") != 1 or not isinstance(moves, list):
                raise ValueError("Invalid migration journal")
            for item in moves:
                if not all(isinstance(item.get(key), str) for key in ("source", "target", "status", "account")):
                    raise ValueError("Invalid migration entry")
        except (OSError, ValueError, TypeError, KeyError, AttributeError) as error:
            return {"moved": 0, "skipped": 0, "errors": [
                {"source": str(journal), "error": type(error).__name__ + ": migration journal retained"}]}
        known = {item["source"] for item in moves}
        skipped = 0
        for source in sorted(report_files(output)):
            relative = source.relative_to(output)
            if len(relative.parts) > 2 or str(source) in known:
                continue
            sidecar = source.with_suffix(".mail.json")
            if not sidecar.is_file() or sidecar.is_symlink():
                skipped += 1
                continue
            try:
                message = json.loads(sidecar.read_text(encoding="utf-8"))
                account = account_for(message, config)
                if account:
                    message["mailbox_account"] = account
                day = source.parent.name if re.fullmatch(r"\d{4}-\d{2}-\d{2}", source.parent.name) else None
                folder = report_folder(message, output, day)
                target = folder / source.name
                count = 0
                while (target.exists() or target.with_suffix(".mail.json").exists()
                       or any(item["target"] == str(target) for item in moves)):
                    count += 1
                    target = folder / (source.stem + f"-migrated-{count}" + source.suffix)
                _safe(source, output)
                _safe(target, output)
                moves.append({"source": str(source), "target": str(target), "account": account, "status": "pending"})
                known.add(str(source))
            except (OSError, ValueError, TypeError, KeyError):
                skipped += 1
        try:
            _atomic(journal, state)
        except OSError as error:
            return {"moved": 0, "skipped": skipped, "errors": [
                {"source": str(journal), "error": type(error).__name__ + ": no reports moved"}]}
        moved = 0
        errors = []
        for item in moves:
            if item["status"] == "done":
                continue
            try:
                if _move_report(home, output, configured_output, item):
                    item["status"] = "done"
                    item.pop("error", None)
                    moved += 1
                    source = Path(item["source"])
                    try:
                        if source.parent != output:
                            source.parent.rmdir()
                    except OSError:
                        pass
                else:
                    skipped += 1
            except (OSError, ValueError, TypeError, KeyError) as error:
                item["error"] = type(error).__name__ + ": " + str(error)[:300]
                errors.append({"source": item["source"], "error": item["error"]})
            try:
                _atomic(journal, state)
            except OSError as error:
                errors.append({"source": str(journal), "error": type(error).__name__ + ": progress retained on disk"})
                break
        return {"moved": moved, "skipped": skipped, "errors": errors}
