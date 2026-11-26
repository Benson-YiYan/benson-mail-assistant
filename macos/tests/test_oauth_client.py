import http.client
import http.server
import io
import json
import sys
import threading
import time
import unittest
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "Runtime"))
import mail_connection_io
import mailbox_config
import oauth_client


class OAuthClientTests(unittest.TestCase):
    def test_pkce_pair_is_s256(self):
        verifier, challenge = oauth_client.create_pkce_pair()
        self.assertGreaterEqual(len(verifier), 43)
        self.assertRegex(verifier, r"^[A-Za-z0-9_-]+$")
        expected = oauth_client._b64url(
            __import__("hashlib").sha256(verifier.encode("ascii")).digest()
        )
        self.assertEqual(challenge, expected)

    def test_imap_scopes_are_provider_specific(self):
        google = oauth_client._provider_config("google")
        microsoft = oauth_client._provider_config("microsoft", "consumers")
        self.assertIn("https://mail.google.com/", google["scope"])
        self.assertEqual(google["required_scope"], "https://mail.google.com/")
        self.assertIn("https://outlook.office.com/IMAP.AccessAsUser.All", microsoft["scope"])
        self.assertIn("https://outlook.office.com/SMTP.Send", microsoft["scope"])
        self.assertIn("offline_access", microsoft["scope"])
        self.assertNotIn("openid", microsoft["scope"])
        self.assertEqual(microsoft["required_scopes"], oauth_client.MICROSOFT_REQUIRED_SCOPES)

    def test_legacy_raw_token_never_refreshes(self):
        post = Mock(side_effect=AssertionError("raw token must not call network"))
        token, updated = oauth_client.access_token("legacy-access-token", {}, post_json=post)
        self.assertEqual(token, "legacy-access-token")
        self.assertIsNone(updated)
        post.assert_not_called()

    def test_managed_token_with_lifetime_returns_without_network(self):
        bundle = {
            "schema": 1,
            "provider": "google",
            "email": "owner@example.com",
            "client_id": "client.apps.googleusercontent.com",
            "access_token": "access-now",
            "refresh_token": "refresh-secret",
            "expires_at": 5000,
        }
        post = Mock(side_effect=AssertionError("fresh token must not refresh"))
        token, updated = oauth_client.access_token(
            json.dumps(bundle), {"provider": "google", "client_id": bundle["client_id"]},
            now=1000, post_json=post,
        )
        self.assertEqual(token, "access-now")
        self.assertIsNone(updated)
        post.assert_not_called()

    def test_managed_token_can_refresh_before_smtp_send(self):
        bundle = {
            "schema": 1, "provider": "microsoft", "email": "owner@example.com",
            "client_id": "11111111-2222-3333-4444-555555555555", "tenant": "consumers",
            "access_token": "access-old", "refresh_token": "refresh-old", "expires_at": 5000,
            "scope": "https://outlook.office.com/IMAP.AccessAsUser.All",
        }
        post = Mock(return_value={
            "access_token": "access-smtp", "refresh_token": "refresh-next", "expires_in": 3600,
            "scope": "https://outlook.office.com/IMAP.AccessAsUser.All https://outlook.office.com/SMTP.Send",
        })
        token, updated = oauth_client.access_token(
            bundle, {"provider": "microsoft", "client_id": bundle["client_id"], "tenant": "consumers"},
            force_refresh=True, post_json=post,
        )
        self.assertEqual(token, "access-smtp")
        self.assertEqual(updated["refresh_token"], "refresh-next")
        self.assertIn("SMTP.Send", post.call_args.args[1]["scope"])
        post.assert_called_once()

    def test_expired_managed_token_refreshes_and_rotates_refresh_token(self):
        bundle = {
            "schema": 1,
            "provider": "microsoft",
            "tenant": "consumers",
            "email": "owner@example.com",
            "client_id": "11111111-2222-3333-4444-555555555555",
            "access_token": "access-old",
            "refresh_token": "refresh-old",
            "expires_at": 100,
        }
        calls = []

        def post(url, values):
            calls.append((url, values))
            return {
                "access_token": "access-new",
                "refresh_token": "refresh-new",
                "expires_in": 3600,
                "scope": "https://outlook.office365.com/IMAP.AccessAsUser.All https://outlook.office365.com/SMTP.Send",
            }

        token, updated = oauth_client.access_token(
            bundle,
            {"provider": "microsoft", "client_id": bundle["client_id"], "tenant": "consumers"},
            now=1000,
            post_json=post,
        )
        self.assertEqual(token, "access-new")
        self.assertEqual(updated["refresh_token"], "refresh-new")
        self.assertEqual(updated["client_id"], bundle["client_id"])
        self.assertEqual(updated["tenant"], "consumers")
        self.assertEqual(calls[0][1]["grant_type"], "refresh_token")
        self.assertEqual(calls[0][1]["refresh_token"], "refresh-old")
        self.assertNotIn("client_secret", calls[0][1])

    def test_google_desktop_secret_is_used_only_at_the_google_token_endpoint_on_refresh(self):
        client_id = "demo.apps.googleusercontent.com"
        base = {"schema": 1, "provider": "google", "email": "owner@example.com",
                "client_id": client_id, "access_token": "access-old", "refresh_token": "refresh-old",
                "expires_at": 100}
        for client_secret in ("", "SYNTHETIC_GOOGLE_SECRET"):
            with self.subTest(secret_set=bool(client_secret)):
                bundle = {**base, **({"client_secret": client_secret} if client_secret else {})}
                post = Mock(return_value={"access_token": "access-new", "expires_in": 3600})
                token, updated = oauth_client.access_token(bundle, now=1000, post_json=post)
                expected = {"grant_type": "refresh_token", "client_id": client_id, "refresh_token": "refresh-old"}
                if client_secret:
                    expected["client_secret"] = client_secret
                post.assert_called_once_with(oauth_client.GOOGLE_TOKEN, expected)
                self.assertEqual(token, "access-new")
                self.assertEqual(updated["refresh_token"], "refresh-old")
                self.assertEqual(updated.get("client_secret", ""), client_secret)

    def test_saved_bundle_is_bound_to_config_even_when_not_expired(self):
        bundle = {
            "schema": 1, "provider": "microsoft", "email": "owner@example.com",
            "client_id": "11111111-2222-3333-4444-555555555555", "tenant": "consumers",
            "access_token": "access-now", "refresh_token": "refresh-old", "expires_at": 5000,
        }
        post = Mock(side_effect=AssertionError("wrong mailbox must not refresh"))
        for config in ({"email": "wrong@example.com"}, {"provider": "google"}, {"tenant": "organizations"},
                       {"client_id": "22222222-2222-3333-4444-555555555555"}):
            with self.subTest(config=config):
                with self.assertRaisesRegex(ValueError, "do not match"):
                    oauth_client.access_token(bundle, config, now=1000, post_json=post)
        self.assertEqual(oauth_client.access_token(bundle, {"email": "OWNER@example.com"}, now=1000),
                         ("access-now", None))
        post.assert_not_called()

    def test_credential_json_does_not_change_bundle(self):
        bundle = {
            "schema": 1,
            "provider": "google",
            "email": "owner@example.com",
            "access_token": "access",
            "refresh_token": "refresh",
            "expires_at": int(time.time()) + 3600,
        }
        encoded = oauth_client.credential_json(bundle)
        self.assertEqual(json.loads(encoded), bundle)

    def test_refreshed_bundle_is_sent_to_keychain_helper_stdin(self):
        bundle = {
            "schema": 1,
            "provider": "google",
            "email": "owner@example.com",
            "client_id": "client.apps.googleusercontent.com",
            "access_token": "SYNTHETIC_ACCESS",
            "refresh_token": "SYNTHETIC_REFRESH",
            "expires_at": int(time.time()) + 3600,
        }
        runner = Mock(return_value=Mock(returncode=0))
        with patch.object(mail_connection_io, "_keychain_helper", return_value=Path("/trusted/SaveKeychainSecret")), \
             patch.object(mail_connection_io.subprocess, "run", runner):
            saved = mail_connection_io.save_managed_credential(
                {"secret_service": "BensonMail-IMAP", "secret_account": "mailbox-id"},
                bundle,
            )
        self.assertEqual(json.loads(saved), bundle)
        args, kwargs = runner.call_args
        self.assertEqual(args[0], ["/trusted/SaveKeychainSecret", "BensonMail-IMAP", "mailbox-id"])
        self.assertNotIn("SYNTHETIC_ACCESS", " ".join(args[0]))
        self.assertEqual(json.loads(kwargs["input"]), bundle)

    def test_invalid_provider_client_and_email_are_rejected(self):
        with self.assertRaises(ValueError):
            oauth_client._provider_config("other")
        with self.assertRaises(ValueError):
            oauth_client._validate_client_id("microsoft", "not-a-guid")
        with self.assertRaises(ValueError):
            oauth_client._validate_client_id("google", "not-google")
        with self.assertRaises(ValueError):
            oauth_client._validate_email("not-an-email")

    def test_callback_rejects_wrong_state_and_accepts_matching_state(self):
        server = oauth_client._CallbackServer(("127.0.0.1", 0), "state-expected")
        thread = threading.Thread(target=server.handle_request, daemon=True)
        thread.start()
        connection = http.client.HTTPConnection(*server.server_address, timeout=3)
        connection.request("GET", "/oauth/callback?state=wrong&code=secret")
        self.assertEqual(connection.getresponse().status, 400)
        thread.join(3)
        self.assertIsNone(server.result)
        server.server_close()

        server = oauth_client._CallbackServer(("127.0.0.1", 0), "state-expected")
        thread = threading.Thread(target=server.handle_request, daemon=True)
        thread.start()
        connection = http.client.HTTPConnection(*server.server_address, timeout=3)
        connection.request("GET", "/oauth/callback?state=state-expected&code=secret")
        self.assertEqual(connection.getresponse().status, 200)
        thread.join(3)
        self.assertEqual(server.result, {"code": "secret"})
        server.server_close()

    def test_identity_mismatch_is_rejected(self):
        with self.assertRaisesRegex(RuntimeError, "does not match"):
            oauth_client._verify_google_identity(
                "access", "owner@example.com",
                lambda _url, _token: {"email": "other@example.com", "email_verified": True},
            )
        with self.assertRaisesRegex(RuntimeError, "did not verify"):
            oauth_client._verify_google_identity(
                "access", "owner@example.com",
                lambda _url, _token: {"email": "owner@example.com"},
            )

    def test_authorize_uses_loopback_pkce_and_returns_bundle(self):
        client_id = "demo.apps.googleusercontent.com"
        seen = {}
        callbacks = []

        def browser(url):
            query = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)
            seen.update(query)
            callback = urllib.parse.urlsplit(query["redirect_uri"][0])
            def send_callback():
                connection = http.client.HTTPConnection(callback.hostname, callback.port, timeout=3)
                connection.request("GET", (callback.path or "/") + "?" + urllib.parse.urlencode({
                    "state": query["state"][0],
                    "code": "synthetic-code",
                }))
                response = connection.getresponse()
                response.read()
                self.assertEqual(response.status, 200)
                connection.close()
            callback_thread = threading.Thread(target=send_callback, daemon=True)
            callback_thread.start()
            callbacks.append(callback_thread)
            return True

        def post(url, values):
            self.assertEqual(url, oauth_client.GOOGLE_TOKEN)
            self.assertEqual(values["grant_type"], "authorization_code")
            self.assertEqual(values["client_id"], client_id)
            self.assertEqual(values["client_secret"], "SYNTHETIC_GOOGLE_SECRET")
            self.assertEqual(values["code"], "synthetic-code")
            self.assertEqual(
                oauth_client._b64url(
                    __import__("hashlib").sha256(values["code_verifier"].encode()).digest()
                ),
                seen["code_challenge"][0],
            )
            return {
                "access_token": "synthetic-access",
                "refresh_token": "synthetic-refresh",
                "expires_in": 3600,
                "scope": oauth_client.GOOGLE_SCOPE,
            }

        def get_json(url, token):
            self.assertEqual(url, oauth_client.GOOGLE_USERINFO)
            self.assertEqual(token, "synthetic-access")
            return {"email": "owner@example.com", "email_verified": True}

        bundle = oauth_client.authorize(
            "google",
            "owner@example.com",
            client_id,
            client_secret="SYNTHETIC_GOOGLE_SECRET",
            open_browser=browser,
            post_json=post,
            get_json=get_json,
            timeout=3,
        )
        callbacks[0].join(3)
        self.assertFalse(callbacks[0].is_alive())
        self.assertEqual(bundle["provider"], "google")
        self.assertEqual(bundle["email"], "owner@example.com")
        self.assertEqual(bundle["client_id"], client_id)
        self.assertEqual(bundle["client_secret"], "SYNTHETIC_GOOGLE_SECRET")
        self.assertEqual(bundle["access_token"], "synthetic-access")
        self.assertEqual(bundle["refresh_token"], "synthetic-refresh")
        self.assertGreater(bundle["expires_at"], int(time.time()))
        self.assertEqual(seen["code_challenge_method"], ["S256"])
        self.assertEqual(seen["scope"][0], oauth_client.GOOGLE_SCOPE)
        self.assertNotIn("client_secret", seen)
        self.assertNotIn("include_granted_scopes", seen)
        self.assertIn(urllib.parse.urlsplit(seen["redirect_uri"][0]).path, ("", "/"))

    def test_microsoft_verifies_requested_mailbox_with_imap_not_graph(self):
        email = "owner@shared.example.com"
        client_id = "11111111-2222-3333-4444-555555555555"
        connection = Mock()
        get_json = Mock(side_effect=AssertionError("Outlook tokens cannot authenticate to Graph"))
        post = Mock(return_value={"access_token": "outlook-access", "refresh_token": "outlook-refresh",
                                  "expires_in": 3600,
                                  "scope": "IMAP.AccessAsUser.All SMTP.Send"})
        browser = Mock(return_value=True)
        with patch.object(mailbox_config, "connect", return_value=connection) as connect, \
             patch.object(oauth_client, "_receive_authorization_response", return_value="synthetic-code") as callback:
            bundle = oauth_client.authorize(
                "microsoft", email, client_id, tenant="consumers", client_secret="IGNORED_FOR_MICROSOFT",
                mailbox_proxy={"proxy_mode": "socks5", "proxy_host": "127.0.0.1", "proxy_port": 10808,
                               "host": "not-a-provider.example", "security": "starttls", "username": "wrong@example.com"},
                open_browser=browser, post_json=post, get_json=get_json,
            )
        self.assertEqual(callback.call_args.args[0].server_address[0], "127.0.0.1")
        query = urllib.parse.parse_qs(urllib.parse.urlsplit(browser.call_args.args[0]).query)
        self.assertEqual(urllib.parse.urlsplit(query["redirect_uri"][0]).hostname, "localhost")
        self.assertEqual(query["scope"], [oauth_client.MICROSOFT_SCOPE])
        token_endpoint, exchange = post.call_args.args
        self.assertEqual(token_endpoint, "https://login.microsoftonline.com/consumers/oauth2/v2.0/token")
        self.assertNotIn("client_secret", query)
        self.assertNotIn("client_secret", exchange)
        self.assertNotIn("client_secret", bundle)
        self.assertEqual(bundle["email"], email)
        get_json.assert_not_called()
        connect.assert_called_once_with(
            {"account": email, "host": "outlook.office365.com", "port": 993, "security": "ssl",
             "mail_folder": "INBOX", "mail_provider": "outlook", "mail_auth": "oauth2", "oauth_mode": "manual",
             "proxy_mode": "socks5", "proxy_host": "127.0.0.1", "proxy_port": 10808},
            "outlook-access",
        )
        connection.logout.assert_called_once()
        with patch.object(mailbox_config, "connect", side_effect=OSError("outlook-access failed")):
            with self.assertRaisesRegex(RuntimeError, "could not verify IMAP access") as caught:
                oauth_client._verify_microsoft_mailbox("outlook-access", email, {})
        self.assertNotIn("outlook-access", str(caught.exception))

    def test_microsoft_does_not_accept_graph_or_wrong_resource_scope(self):
        config = oauth_client._provider_config("microsoft")
        for grant in (
            "https://graph.microsoft.com/Mail.Read",
            "https://graph.microsoft.com/Mail.Send",
            "https://wrong.example/IMAP.AccessAsUser.All",
            "https://outlook.office.com/IMAP.AccessAsUser.All",
            "https://outlook.office.com/IMAP.AccessAsUser.All https://graph.microsoft.com/Mail.Send",
        ):
            with self.subTest(grant=grant):
                with self.assertRaisesRegex(RuntimeError, "required mail access"):
                    oauth_client._validate_scopes("microsoft", {"scope": grant}, config)

    def test_google_missing_desktop_secret_error_excludes_upstream_details(self):
        description = b'{"error":"invalid_request","error_description":"client_secret is missing: INTERNAL_DETAIL"}'
        error = urllib.error.HTTPError(oauth_client.GOOGLE_TOKEN, 400, "Bad Request", {}, io.BytesIO(description))
        with patch.object(oauth_client, "_open_credentials_request", side_effect=error):
            with self.assertRaisesRegex(RuntimeError, "requires this desktop app's OAuth client secret") as caught:
                oauth_client._post_json(oauth_client.GOOGLE_TOKEN, {})
        self.assertNotIn("INTERNAL_DETAIL", str(caught.exception))

    def test_credential_request_does_not_follow_redirect(self):
        received = []

        class Redirect(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                received.append(self.path)
                self.send_response(302 if self.path == "/start" else 200)
                if self.path == "/start":
                    self.send_header("Location", "/untrusted")
                self.end_headers()

            def log_message(self, *_args):
                pass

        with http.server.HTTPServer(("127.0.0.1", 0), Redirect) as server:
            thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": .02}, daemon=True)
            thread.start()
            try:
                request = urllib.request.Request(
                    f"http://127.0.0.1:{server.server_port}/start",
                    headers={"Authorization": "Bearer SYNTHETIC_BEARER"},
                )
                with patch.object(urllib.request, "getproxies", return_value={}):
                    with self.assertRaises(urllib.error.HTTPError) as caught:
                        oauth_client._open_credentials_request(request, 3)
                self.assertEqual(caught.exception.code, 302)
                caught.exception.close()
            finally:
                server.shutdown()
                thread.join(3)
        self.assertEqual(received, ["/start"])


if __name__ == "__main__":
    unittest.main()
