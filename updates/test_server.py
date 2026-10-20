import http.client
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest import mock
import base64
import subprocess
import server


class ReleaseServerTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.directory = Path(self.temporary.name)
        self.catalog = {}
        for platform, extension in server.PLATFORMS.items():
            name = platform + extension
            (self.directory / name).write_bytes(b"0123456789")
            self.catalog[platform] = {"file": name, "version": "202610181010", "notes": "test"}
        self.state = server.State(self.directory)
        self.state.catalog = server.validate_catalog(self.catalog, self.directory)
        self.state.hostname = "https://example.trycloudflare.com"
        self.http = server.http.server.ThreadingHTTPServer(("127.0.0.1", 0), server.make_handler(self.state))
        threading.Thread(target=self.http.serve_forever, daemon=True).start()

    def tearDown(self):
        self.http.shutdown()
        self.http.server_close()
        self.temporary.cleanup()

    def request(self, path, method="GET", headers=None):
        connection = http.client.HTTPConnection("127.0.0.1", self.http.server_port)
        connection.request(method, path, headers=headers or {})
        response = connection.getresponse()
        result = response.status, dict(response.headers), response.read()
        connection.close()
        return result

    def test_range_head_and_full(self):
        self.assertEqual(self.request("/downloads/windows-x64.exe")[2], b"0123456789")
        status, headers, body = self.request("/downloads/windows-x64.exe", headers={"Range": "bytes=3-6"})
        self.assertEqual((status, body, headers["Content-Range"]), (206, b"3456", "bytes 3-6/10"))
        self.assertEqual(self.request("/downloads/windows-x64.exe", headers={"Range": "bytes=-3"})[2], b"789")
        status, headers, body = self.request("/downloads/windows-x64.exe", "HEAD")
        self.assertEqual((status, headers["Content-Length"], body), (200, "10", b""))
        self.assertEqual(self.request("/downloads/windows-x64.exe", headers={"Range": "bytes=99-"})[0], 416)
        self.assertEqual(self.request("/downloads/windows-x64.exe", headers={"Range": "bytes=0-1,3-4"})[0], 416)

    def test_no_directory_other_files_or_traversal(self):
        (self.directory / "private.txt").write_text("never served")
        for path in ("/", "/downloads/", "/downloads/private.txt", "/downloads/../private.txt",
                     "/downloads/%2e%2e/private.txt", "/downloads/windows-x64.exe%2f..%2fprivate.txt"):
            self.assertEqual(self.request(path)[0], 404, path)

    def test_symlink_replacement_refused(self):
        target = self.directory / "windows-x64.exe"
        target.unlink()
        target.symlink_to(self.directory / "macos-arm64.dmg")
        self.assertEqual(self.request("/downloads/windows-x64.exe")[0], 404)
        with self.assertRaises(ValueError):
            server.validate_catalog(self.catalog, self.directory)

    def test_manifest_is_public_fields_only(self):
        status, _, body = self.request("/manifest.json")
        manifest = json.loads(body)
        self.assertEqual(status, 200)
        self.assertEqual(set(manifest["platforms"]), set(server.PLATFORMS))
        self.assertNotIn(str(self.directory), body.decode())
        for entry in manifest["platforms"].values():
            self.assertNotIn("file", entry)
            self.assertEqual(len(entry["sha256"]), 64)

    def test_wait_for_complete_catalog_and_hostname(self):
        self.state.hostname = None
        self.assertEqual(self.request("/manifest.json")[0], 503)
        self.assertFalse(self.state.manifest())

    def test_same_size_modified_package_is_rejected(self):
        (self.directory / "windows-x64.exe").write_bytes(b"ABCDEFGHIJ")
        self.assertEqual(self.request("/downloads/windows-x64.exe")[0], 409)

    def test_github_downloads_work_without_mac_tunnel(self):
        for entry in self.catalog.values():
            entry["download_url"] = (
                "https://github.com/Benson-YiYan/benson-mail-assistant/releases/download/v20261018/" + entry["file"])
        self.state.catalog = server.validate_catalog(self.catalog, self.directory)
        self.state.hostname = None
        manifest = self.state.manifest()
        self.assertTrue(manifest)
        for platform, entry in manifest["platforms"].items():
            self.assertEqual(entry["url"], self.catalog[platform]["download_url"])
            self.assertEqual(entry["sha256"], self.state.catalog[platform]["sha256"])
            self.assertNotIn("download_url", entry)
        del self.state.catalog["windows-x64"]["download_url"]
        self.assertIsNone(self.state.manifest())

    def test_reject_wrong_host_or_different_github_asset(self):
        entry = self.catalog["windows-x64"]
        for url in ("http://github.com/Benson-YiYan/benson-mail-assistant/releases/download/v1/windows-x64.exe",
                    "https://github.com.evil.invalid/Benson-YiYan/benson-mail-assistant/releases/download/v1/windows-x64.exe",
                    "https://github.com/Benson-YiYan/benson-mail-assistant/releases/download/v1/another.exe",
                    "https://github.com/Benson-YiYan/benson-mail-assistant/releases/download/v1/windows-x64.exe?token=secret"):
            entry["download_url"] = url
            with self.assertRaises(ValueError):
                server.validate_catalog(self.catalog, self.directory)

    def test_mirror_keeps_mac_primary_and_checked_artifact_identity(self):
        entry = self.catalog["windows-x64"]
        url = "https://github.com/Benson-YiYan/benson-mail-assistant/releases/download/v20261018/" + entry["file"]
        entry["mirrors"] = [url, url]
        self.state.catalog = server.validate_catalog(self.catalog, self.directory)
        manifest = self.state.manifest()
        published = manifest["platforms"]["windows-x64"]
        self.assertTrue(published["url"].startswith(self.state.hostname + "/downloads/"))
        self.assertEqual(published["mirrors"], [url])
        self.assertEqual(published["sha256"], self.state.catalog["windows-x64"]["sha256"])
        for invalid in ("https://example.invalid/file", [url.replace("https:", "http:")]):
            entry["mirrors"] = invalid
            with self.assertRaises(ValueError):
                server.validate_catalog(self.catalog, self.directory)


class LanguageReleaseServerTests(unittest.TestCase):
    setUp = ReleaseServerTests.setUp
    tearDown = ReleaseServerTests.tearDown
    request = ReleaseServerTests.request
    def test_six_language_packs_are_allowlisted_and_digest_checked(self):
        import hashlib
        entries={}
        for platform in ('windows','macos'):
            for code in ('zh','en','es'):
                name=f'BensonMail-Language-{platform}-{code}-202610200900.json'
                data=json.dumps({'schema_version':1,'platform':platform,'language':code}).encode()
                (self.directory/name).write_bytes(data)
                entries[platform+'-'+code]={'file':name,'version':'202610200900','size':len(data),'sha256':hashlib.sha256(data).hexdigest(),
                    'mirrors':['https://github.com/Benson-YiYan/benson-mail-assistant/releases/download/v20261020/'+name]}
        self.state.language_catalog=server.validate_language_catalog(entries,self.directory)
        manifest=json.loads(self.request('/manifest.json')[2])
        self.assertEqual(len(manifest['language_packs']),6)
        entry=entries['macos-es']
        self.assertEqual(self.request('/downloads/'+entry['file'])[0],200)
        self.assertEqual(self.request('/downloads/'+entry['file'],headers={'Range':'bytes=0-7'})[0],206)
        path=self.directory/entry['file']; path.write_bytes(b'X'*entry['size'])
        self.assertEqual(self.request('/downloads/'+entry['file'])[0],409)
        with self.assertRaises(ValueError): server.validate_language_catalog(entries,self.directory)


class ManifestPublicationTests(unittest.TestCase):
    manifest = {"schema_version": 1, "platforms": {"windows-x64": {"version": "202610201000"}}}

    def existing(self, manifest):
        return subprocess.CompletedProcess([], 0, json.dumps({
            "sha": "previous-sha",
            "content": base64.b64encode(json.dumps(manifest).encode()).decode(),
        }), "")

    def test_unchanged_canonical_and_compatibility_manifests_do_not_commit(self):
        with mock.patch.object(server.subprocess, "run", return_value=self.existing(self.manifest)) as run:
            outcomes = server.publish_manifests(self.manifest)
        self.assertTrue(all(outcomes.values()))
        self.assertEqual(run.call_count, 2)
        self.assertEqual([call.args[0][-1] for call in run.call_args_list], [
            "repos/Benson-YiYan/benson-mail-assistant/contents/distribution/manifest.json",
            "repos/Benson-YiYan/benson-mail-updates/contents/manifest.json",
        ])

    def test_canonical_failure_does_not_block_compatibility_publication(self):
        with mock.patch.object(server, "publish_manifest", side_effect=[RuntimeError("unavailable"), None]) as publish:
            with self.assertLogs(server.LOG, level="ERROR"):
                outcomes = server.publish_manifests(self.manifest)
        self.assertEqual(list(outcomes.values()), [False, True])
        self.assertEqual(publish.call_count, 2)

    def test_compatibility_failure_does_not_undo_canonical_publication(self):
        with mock.patch.object(server, "publish_manifest", side_effect=[None, subprocess.TimeoutExpired("gh", 45)]):
            with self.assertLogs(server.LOG, level="ERROR"):
                outcomes = server.publish_manifests(self.manifest)
        self.assertEqual(list(outcomes.values()), [True, False])

    def test_changed_compatibility_manifest_preserves_sha_and_exact_verified_content(self):
        requests = []
        def run(command, **kwargs):
            requests.append(command)
            if "--method" not in command:
                return self.existing({"schema_version": 1, "platforms": {}})
            payload = json.loads(Path(command[-1]).read_text(encoding="utf-8"))
            self.assertEqual(payload["sha"], "previous-sha")
            self.assertEqual(json.loads(base64.b64decode(payload["content"])), self.manifest)
            return subprocess.CompletedProcess(command, 0, "", "")
        with mock.patch.object(server.subprocess, "run", side_effect=run):
            server.publish_manifest(self.manifest, server.COMPATIBILITY_REPOSITORY, "manifest.json")
        self.assertEqual(len(requests), 2)
        self.assertEqual(requests[1][-3], "repos/Benson-YiYan/benson-mail-updates/contents/manifest.json")

    def test_missing_compatibility_manifest_is_created_without_sha(self):
        def run(command, **kwargs):
            if "--method" not in command:
                return subprocess.CompletedProcess(command, 1, "", "HTTP 404")
            payload = json.loads(Path(command[-1]).read_text(encoding="utf-8"))
            self.assertNotIn("sha", payload)
            self.assertEqual(json.loads(base64.b64decode(payload["content"])), self.manifest)
            return subprocess.CompletedProcess(command, 0, "", "")
        with mock.patch.object(server.subprocess, "run", side_effect=run) as api:
            server.publish_manifest(self.manifest, server.COMPATIBILITY_REPOSITORY, "manifest.json")
        self.assertEqual(api.call_count, 2)

if __name__ == "__main__":
    unittest.main()
