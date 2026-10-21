#!/usr/bin/env python3
"""Narrow, allowlisted release download server and temporary tunnel supervisor."""
import argparse
import base64
import hashlib
import http.server
import json
import logging
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import tempfile
import threading
import time
import uuid
from urllib.request import Request, urlopen
from urllib.parse import quote, unquote, urlsplit

HOME = Path.home()
APP = HOME / "Library/Application Support/BensonMailUpdates"
DOWNLOADS = HOME / "Documents/CodexMade"
TUNNEL = APP / "runtime/cloudflared"
REPOSITORY = "Benson-YiYan/benson-mail-assistant"
COMPATIBILITY_REPOSITORY = "Benson-YiYan/benson-mail-updates"
MANIFEST_TARGETS = (
    (REPOSITORY, "distribution/manifest.json"),
    (COMPATIBILITY_REPOSITORY, "manifest.json"),
)
PLATFORMS = {"windows-x64": ".exe", "macos-arm64": ".dmg", "macos-x86_64": ".dmg"}
LOG = logging.getLogger("mail-updates")


def atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def digest_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_github_url(url, name):
    if not isinstance(url, str):
        raise ValueError("Download URL must be text")
    parsed = urlsplit(url)
    prefix = "/Benson-YiYan/benson-mail-assistant/releases/download/"
    suffix = parsed.path[len(prefix):].split("/")
    if (parsed.scheme != "https" or parsed.netloc != "github.com"
            or parsed.query or parsed.fragment
            or not parsed.path.startswith(prefix)
            or len(suffix) != 2 or not all(suffix)
            or unquote(parsed.path.rsplit("/", 1)[-1]) != name):
        raise ValueError("Download URL must identify this package in the public GitHub release")
    return url


def validate_catalog(data, directory=DOWNLOADS):
    """No recursive paths, symlinks or anything outside the three release roles."""
    if set(data) != set(PLATFORMS):
        raise ValueError("Catalog must specify exactly windows-x64, macos-arm64 and macos-x86_64")
    result = {}
    for platform, entry in data.items():
        name = entry.get("file", "")
        if not name or name != Path(name).name or "/" in name or "\\" in name or name in {".", ".."}:
            raise ValueError("Invalid release filename")
        if Path(name).suffix.lower() != PLATFORMS[platform]:
            raise ValueError("Release extension does not match platform")
        path = directory / name
        if path.is_symlink() or not path.is_file() or path.resolve().parent != directory.resolve():
            raise ValueError("Release must be a regular file directly inside CodexMade")
        if not re.fullmatch(r"\d{12}", str(entry.get("version", ""))):
            raise ValueError("Release version must have 12 digits")
        checksum = digest_file(path)
        if entry.get("sha256") and entry["sha256"].lower() != checksum:
            raise ValueError("Release checksum mismatch")
        notes = entry.get("notes", "")
        if not isinstance(notes, (str, dict)):
            raise ValueError("Release notes must be text or a language dictionary")
        result[platform] = {
            "file": name, "version": str(entry["version"]), "sha256": checksum,
            "size": path.stat().st_size, "notes": notes,
        }
        if "download_url" in entry:
            result[platform]["download_url"] = validate_github_url(entry["download_url"], name)
        mirrors = entry.get("mirrors", [])
        if not isinstance(mirrors, list) or len(mirrors) > 3:
            raise ValueError("Mirrors must be a list with at most three URLs")
        if mirrors:
            result[platform]["mirrors"] = list(dict.fromkeys(validate_github_url(url, name) for url in mirrors))
    if len({entry["file"] for entry in result.values()}) != 3:
        raise ValueError("Each platform needs its own installation package")
    return result


def validate_language_catalog(data, directory=DOWNLOADS):
    expected = {platform + '-' + code for platform in ('windows', 'macos') for code in ('zh', 'en', 'es')}
    if set(data) != expected: raise ValueError('Exactly six platform/language packs are required')
    result = {}
    for key, item in data.items():
        name = item.get('file', '')
        if not re.fullmatch(r'BensonMail-Language-' + re.escape(key) + r'-[0-9]{12}\.json', name):
            raise ValueError('Invalid language-pack filename')
        path = directory / name
        if path.is_symlink() or not path.is_file() or not 0 < path.stat().st_size <= 2 * 1024 * 1024:
            raise ValueError('Invalid language-pack file')
        content = json.loads(path.read_text())
        platform, code = key.split('-')
        if content.get('schema_version') != 1 or content.get('language') != code or content.get('platform') != platform:
            raise ValueError('Language pack identity mismatch')
        digest, size = digest_file(path), path.stat().st_size
        if digest != item.get('sha256') or size != item.get('size'):
            raise ValueError('Language pack digest or size mismatch')
        mirrors = [validate_github_url(url, name) for url in item.get('mirrors', [])]
        if not mirrors: raise ValueError('A GitHub language-pack mirror is required')
        result[key] = {'file': name, 'version': item['version'], 'sha256': digest, 'size': size, 'mirrors': mirrors}
    return result


class State:
    def __init__(self, directory=DOWNLOADS):
        self.directory = directory
        self.catalog = {}
        self.language_catalog = {}
        self.hostname = None
        self.published = False
        self.probe_token = uuid.uuid4().hex
        self.lock = threading.RLock()

    def manifest(self):
        with self.lock:
            if len(self.catalog) != 3 or (
                    not self.hostname and any(not entry.get("download_url") and not entry.get("mirrors")
                                              for entry in self.catalog.values())):
                return None
            manifest = {
                "schema_version": 1,
                "platforms": {
                    platform: {
                        key: value for key, value in {
                            **entry,
                            "url": entry.get("download_url") or (
                                self.hostname + "/downloads/" + quote(entry["file"], safe="")
                                if self.hostname else entry["mirrors"][0]),
                        }.items() if key not in {"file", "download_url"}
                    } for platform, entry in self.catalog.items()
                },
            }
            if self.language_catalog:
                manifest['language_packs'] = {
                    key: {**{field: value for field, value in entry.items() if field != 'file'},
                          'url': (self.hostname + '/downloads/' + quote(entry['file'], safe='')) if self.hostname else entry['mirrors'][0]}
                    for key, entry in self.language_catalog.items()}
            return manifest


def probe_public_tunnel(hostname, expected_token):
    """Verify the actual origin, not merely a live cloudflared process or edge page."""
    request = Request(hostname + "/health", headers={"Cache-Control": "no-cache"})
    with urlopen(request, timeout=8) as response:
        body = response.read(1025)
        if response.status != 200 or len(body) > 1024:
            raise ValueError("Unexpected tunnel health response")
        if json.loads(body) != {"service": "mail-updates", "probe": expected_token}:
            raise ValueError("Tunnel did not reach this origin")


def make_handler(state):
    class Handler(http.server.BaseHTTPRequestHandler):
        server_version = "MailRelease/1"
        sys_version = ""

        def log_message(self, *_):
            pass  # No client addresses or query strings in logs.

        def do_HEAD(self):
            self.serve(head=True)

        def do_GET(self):
            self.serve(head=False)

        def send_json(self, value, head=False, status=200):
            body = json.dumps(value, ensure_ascii=False).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            if not head:
                self.wfile.write(body)

        def serve(self, head):
            requested = unquote(urlsplit(self.path).path)
            if requested == "/health":
                return self.send_json({"service": "mail-updates", "probe": state.probe_token}, head)
            if requested == "/status":
                with state.lock:
                    return self.send_json({"status": "ready" if state.manifest() else "waiting-for-release",
                                           "published": state.published,
                                           "download_route": "mac-tunnel" if state.hostname else "github-fallback"}, head)
            if requested == "/manifest.json":
                manifest = state.manifest()
                return self.send_json(manifest or {"status": "not-published"}, head, 200 if manifest else 503)
            with state.lock:
                matches = [entry for entry in [*state.catalog.values(), *state.language_catalog.values()]
                           if requested == "/downloads/" + entry["file"]]
            if len(matches) != 1:
                return self.send_error(404)
            entry = matches[0]
            path = state.directory / entry["file"]
            # Recheck on each request; never follow a replacement symlink.
            try:
                fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
            except OSError:
                return self.send_error(404)
            with os.fdopen(fd, "rb") as stream:
                stat = os.fstat(stream.fileno())
                if stat.st_size != entry["size"]:
                    return self.send_error(409)
                checksum = hashlib.sha256()
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    checksum.update(chunk)
                if checksum.hexdigest() != entry["sha256"]:
                    return self.send_error(409)
                stream.seek(0)
                size, start, end, status = stat.st_size, 0, stat.st_size - 1, 200
                value = self.headers.get("Range")
                if value:
                    match = re.fullmatch(r"bytes=(\d*)-(\d*)", value)
                    if not match or not any(match.groups()):
                        return self.invalid_range(size)
                    left, right = match.groups()
                    if left:
                        start = int(left)
                        end = min(int(right), size - 1) if right else size - 1
                    else:
                        start = max(0, size - int(right))
                    if start >= size or start > end:
                        return self.invalid_range(size)
                    status = 206
                self.send_response(status)
                self.send_header("Content-Type", "application/octet-stream")
                self.send_header("Content-Disposition", "attachment; filename*=UTF-8''" + quote(entry["file"], safe=""))
                self.send_header("Content-Length", str(end - start + 1))
                self.send_header("Accept-Ranges", "bytes")
                self.send_header("ETag", '"' + entry["sha256"] + '"')
                self.send_header("X-Content-Type-Options", "nosniff")
                if status == 206:
                    self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
                self.end_headers()
                if not head:
                    remaining = end - start + 1
                    stream.seek(start)
                    try:
                        while remaining:
                            data = stream.read(min(1024 * 1024, remaining))
                            if not data:
                                break
                            self.wfile.write(data)
                            remaining -= len(data)
                    except (BrokenPipeError, ConnectionResetError):
                        pass

        def invalid_range(self, size):
            self.send_response(416)
            self.send_header("Content-Range", f"bytes */{size}")
            self.send_header("Content-Length", "0")
            self.end_headers()
    return Handler


def publish_manifest(manifest, repository=REPOSITORY, path="distribution/manifest.json"):
    gh = shutil.which("gh") or "/opt/homebrew/bin/gh"
    endpoint = f"repos/{repository}/contents/{path}"
    existing = subprocess.run([gh, "api", endpoint], capture_output=True, text=True, timeout=45)
    previous = None
    if existing.returncode == 0:
        previous = json.loads(existing.stdout)
        old = json.loads(base64.b64decode(previous["content"]))
        if old == manifest:
            return
    elif "404" not in existing.stderr:
        raise RuntimeError("GitHub manifest read failed; check gh authentication or connectivity")
    body = {"message": "Update installation package download links",
            "content": base64.b64encode((json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode()).decode()}
    if previous:
        body["sha"] = previous["sha"]
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".json") as payload:
        json.dump(body, payload)
        payload.flush()
        outcome = subprocess.run([gh, "api", "--method", "PUT", endpoint, "--input", payload.name],
                                 capture_output=True, text=True, timeout=60)
    if outcome.returncode:
        raise RuntimeError("GitHub manifest write failed; publication will retry in five minutes")


def publish_manifests(manifest):
    """Publish the same verified data to both addresses, attempting each independently."""
    outcomes = {}
    for repository, path in MANIFEST_TARGETS:
        target = repository + "/" + path
        try:
            publish_manifest(manifest, repository, path)
            outcomes[target] = True
        except (RuntimeError, OSError, subprocess.TimeoutExpired, ValueError):
            outcomes[target] = False
            LOG.error("Manifest publication failed for %s; retry in five minutes", target)
    return outcomes


def run():
    APP.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    state = State()
    try:
        server = http.server.ThreadingHTTPServer(("127.0.0.1", 18765), make_handler(state))
    except OSError as error:
        LOG.error("Cannot listen on local port 18765: %s", error)
        return 1
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True).start()
    stopping = threading.Event()
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: stopping.set())
    tunnel = None
    tunnel_retry_at = 0
    tunnel_failures = 0
    last_catalog_stamp = None
    last_language_stamp = None
    next_publication = 0
    last_manifest = None
    candidate_hostname = None
    next_probe = 0
    probe_failures = 0
    tunnel_started_at = 0

    def consume_tunnel(process):
        nonlocal candidate_hostname, next_probe
        for line in process.stdout:
            match = re.search(r"https://[a-z0-9-]+\.trycloudflare\.com", line)
            if match:
                with state.lock:
                    if process is not tunnel:
                        continue
                    candidate_hostname = match.group(0)
                    next_probe = 0
                LOG.info("Public download tunnel assigned; verifying origin: %s", match.group(0))
            elif "Registered tunnel connection" in line:
                LOG.info("Cloudflare transport connected")
            elif "ERR" in line:
                # Avoid logging arbitrary subprocess output or client information.
                LOG.warning("Cloudflare transport reported an error")

    LOG.info("Download service listening on 127.0.0.1:18765")
    try:
        while not stopping.wait(1):
            catalog_path = APP / "catalog.json"
            try:
                stamp = catalog_path.stat().st_mtime_ns
                if stamp != last_catalog_stamp:
                    catalog = validate_catalog(json.loads(catalog_path.read_text()))
                    with state.lock:
                        state.catalog = catalog
                        state.published = False
                    last_catalog_stamp = stamp
                    next_publication = 0
                    LOG.info("Validated three installation packages")
            except FileNotFoundError:
                pass
            except (OSError, ValueError, KeyError) as error:
                LOG.error("Release catalog rejected: %s", error)
                # Prevent per-second repeated error messages.
                if catalog_path.exists():
                    last_catalog_stamp = catalog_path.stat().st_mtime_ns
            language_path = APP / 'language-catalog.json'
            if language_path.exists():
                stamp = language_path.stat().st_mtime_ns
                if stamp != last_language_stamp:
                    try:
                        languages = validate_language_catalog(json.loads(language_path.read_text()))
                        with state.lock:
                            state.language_catalog = languages
                            state.published = False
                        next_publication = 0
                        LOG.info('Validated six language packs')
                    except (OSError, ValueError, KeyError):
                        LOG.error('Language catalog rejected; previous verified packs retained')
                    last_language_stamp = stamp
            if tunnel and tunnel.poll() is not None:
                LOG.warning("Download tunnel stopped; reconnecting with backoff")
                tunnel = None
                with state.lock:
                    state.hostname = None
                    state.published = False
                    candidate_hostname = None
                probe_failures = 0
                tunnel_failures += 1
                tunnel_retry_at = time.monotonic() + min(300, 30 * tunnel_failures)
            if tunnel is None and time.monotonic() >= tunnel_retry_at:
                try:
                    tunnel = subprocess.Popen([str(TUNNEL), "tunnel", "--url", "http://127.0.0.1:18765",
                                               "--no-autoupdate"],
                                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                              text=True, bufsize=1)
                    tunnel_started_at = time.monotonic()
                    threading.Thread(target=consume_tunnel, args=(tunnel,), daemon=True).start()
                except OSError:
                    LOG.error("Cloudflared runtime is unavailable; retrying in five minutes")
                    tunnel_retry_at = time.monotonic() + 300
            if tunnel and tunnel.poll() is None:
                with state.lock:
                    candidate = candidate_hostname
                if candidate and time.monotonic() >= next_probe:
                    try:
                        probe_public_tunnel(candidate, state.probe_token)
                    except (OSError, ValueError) as error:
                        probe_failures += 1
                        LOG.warning("Public origin probe failed (%s, %s/3)",
                                    type(error).__name__, probe_failures)
                        if probe_failures >= 3:
                            with state.lock:
                                state.hostname = None
                                state.published = False
                            LOG.warning("Rebuilding unresponsive tunnel; using verified GitHub mirrors")
                            tunnel.terminate()
                    else:
                        with state.lock:
                            if candidate == candidate_hostname:
                                if state.hostname != candidate:
                                    state.hostname = candidate
                                    state.published = False
                                    LOG.info("Public download origin verified")
                        probe_failures = 0
                        tunnel_failures = 0
                    next_probe = time.monotonic() + 60
                elif not candidate and time.monotonic() - tunnel_started_at > 120:
                    LOG.warning("Tunnel startup timed out; rebuilding")
                    tunnel.terminate()
            manifest = state.manifest()
            if manifest and manifest != last_manifest:
                next_publication = 0
                last_manifest = manifest
            if manifest and not state.published and time.monotonic() >= next_publication:
                outcomes = publish_manifests(manifest)
                with state.lock:
                    # A tunnel can reconnect while the GitHub requests are in flight.
                    state.published = all(outcomes.values()) and state.manifest() == manifest
                canonical_ready = outcomes[REPOSITORY + "/distribution/manifest.json"]
                try:
                    atomic_json(APP / "status.json", {
                        "status": "ready" if canonical_ready else "publication-pending",
                        "manifest": manifest, "publications": outcomes,
                    })
                except OSError:
                    LOG.error("Publication status could not be saved; retry in five minutes")
                    with state.lock:
                        state.published = False
                if state.published:
                    LOG.info("Stable public manifest updated")
                else:
                    next_publication = time.monotonic() + 300
    finally:
        server.shutdown()
        server.server_close()
        if tunnel and tunnel.poll() is None:
            tunnel.terminate()
            try:
                tunnel.wait(timeout=10)
            except subprocess.TimeoutExpired:
                tunnel.kill()
                tunnel.wait()
    return 0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--publish", metavar="CATALOG", help="validate three packages and atomically publish a release catalog")
    parser.add_argument("--publish-languages", metavar="CATALOG", help="validate six language packs and publish metadata")
    args = parser.parse_args()
    if args.publish_languages:
        catalog = validate_language_catalog(json.loads(Path(args.publish_languages).read_text(encoding='utf-8')))
        atomic_json(APP / 'language-catalog.json', catalog)
        print('Validated language catalog saved.')
        return
    if args.publish:
        catalog = validate_catalog(json.loads(Path(args.publish).read_text(encoding="utf-8")))
        atomic_json(APP / "catalog.json", catalog)
        print("Validated release catalog saved. The running service will publish its public manifest.")
        return 0
    return run()


if __name__ == "__main__":
    raise SystemExit(main())
