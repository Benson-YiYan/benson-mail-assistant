"""OAuth authorization-code + PKCE for Gmail API and Outlook IMAP OAuth.

The returned credential bundle is deliberately plain data so the platform
frontends can store it in Keychain/DPAPI.  This module never writes, prints, or
copies tokens.  Legacy raw access tokens remain accepted by ``access_token``.
"""
import base64
import hashlib
import hmac
import http.server
import http.client
import io
import json
import re
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser


# Gmail uses the official API so access can be limited to read-only mail
# retrieval and user-confirmed sending. Other providers keep their transports.
GOOGLE_READ_SCOPE = "https://www.googleapis.com/auth/gmail.readonly"
GOOGLE_SEND_SCOPE = "https://www.googleapis.com/auth/gmail.send"
GOOGLE_SCOPE = f"openid email {GOOGLE_READ_SCOPE} {GOOGLE_SEND_SCOPE}"
MICROSOFT_IMAP_SCOPE = "https://outlook.office.com/IMAP.AccessAsUser.All"
MICROSOFT_SMTP_SCOPE = "https://outlook.office.com/SMTP.Send"
MICROSOFT_SCOPE = f"offline_access {MICROSOFT_IMAP_SCOPE} {MICROSOFT_SMTP_SCOPE}"
GOOGLE_REQUIRED_SCOPE = GOOGLE_READ_SCOPE
GOOGLE_REQUIRED_SCOPES = (GOOGLE_READ_SCOPE, GOOGLE_SEND_SCOPE)
# Keep the single-scope metadata field for older callers; token validation
# requires both delegated permissions via MICROSOFT_REQUIRED_SCOPES.
MICROSOFT_REQUIRED_SCOPE = MICROSOFT_IMAP_SCOPE
MICROSOFT_REQUIRED_SCOPES = (MICROSOFT_IMAP_SCOPE, MICROSOFT_SMTP_SCOPE)
_MICROSOFT_SCOPE_ALIASES = (
    frozenset({MICROSOFT_IMAP_SCOPE.casefold(), "https://outlook.office365.com/imap.accessasuser.all", "imap.accessasuser.all"}),
    frozenset({MICROSOFT_SMTP_SCOPE.casefold(), "https://outlook.office365.com/smtp.send", "smtp.send"}),
)
GOOGLE_AUTHORIZE = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO = "https://openidconnect.googleapis.com/v1/userinfo"
MICROSOFT_AUTHORITY = "https://login.microsoftonline.com"
MICROSOFT_IMAP_HOST = "outlook.office365.com"
CALLBACK_PATH = "/oauth/callback"
CALLBACK_TIMEOUT = 300
REFRESH_SKEW_SECONDS = 120


_SAFE_ERRORS = {
    "access_denied", "authorization_declined", "invalid_client",
    "invalid_grant", "invalid_request", "invalid_scope", "login_required",
    "interaction_required", "temporarily_unavailable", "server_error",
    "unauthorized_client", "unsupported_response_type",
}


def _safe_error(value):
    return value if value in _SAFE_ERRORS else "authorization_failed"


def _validate_email(email):
    value = str(email or "").strip()
    if (len(value) > 254 or "\r" in value or "\n" in value or
            not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", value)):
        raise ValueError("Enter a valid email address.")
    return value


def _validate_client_id(provider, client_id):
    value = str(client_id or "").strip()
    if not value or len(value) > 512 or any(ord(char) < 33 for char in value):
        raise ValueError("OAuth client ID is missing or invalid.")
    if provider == "microsoft":
        import uuid
        try:
            uuid.UUID(value)
        except (ValueError, AttributeError):
            raise ValueError("Microsoft OAuth client ID must be an application ID.") from None
    elif not value.endswith(".apps.googleusercontent.com"):
        raise ValueError("Google OAuth client ID is invalid.")
    return value


def _validate_client_secret(client_secret):
    if not isinstance(client_secret, str):
        raise ValueError("Google OAuth client secret is invalid.")
    value = client_secret.strip()
    if (len(value) > 512 or any(not 33 <= ord(char) <= 126 for char in value)):
        raise ValueError("Google OAuth client secret is invalid.")
    return value


def _b64url(value):
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def create_pkce_pair():
    """Return an RFC 7636 verifier and S256 challenge."""
    verifier = _b64url(secrets.token_bytes(32))
    challenge = _b64url(hashlib.sha256(verifier.encode("ascii")).digest())
    return verifier, challenge


def _provider_config(provider, tenant="common"):
    if provider == "google":
        return {
            "authorize": GOOGLE_AUTHORIZE,
            "token": GOOGLE_TOKEN,
            "scope": GOOGLE_SCOPE,
            "required_scope": GOOGLE_REQUIRED_SCOPE,
            "required_scopes": GOOGLE_REQUIRED_SCOPES,
            "redirect_host": "127.0.0.1",
        }
    if provider == "microsoft":
        if (not re.fullmatch(r"[A-Za-z0-9.-]{1,255}", str(tenant))
                or any(not label for label in str(tenant).split("."))):
            raise ValueError("Microsoft tenant must be an ID or domain.")
        base = f"{MICROSOFT_AUTHORITY}/{tenant}/oauth2/v2.0"
        return {
            "authorize": base + "/authorize",
            "token": base + "/token",
            "scope": MICROSOFT_SCOPE,
            "required_scope": MICROSOFT_REQUIRED_SCOPE,
            "required_scopes": MICROSOFT_REQUIRED_SCOPES,
            "redirect_host": "localhost",
        }
    raise ValueError("Choose Google or Microsoft sign-in.")


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """An OAuth credential request may only reach its original endpoint."""

    def redirect_request(self, *_args, **_kwargs):
        return None


def _open_credentials_request(request, timeout, proxy=None):
    if not proxy:
        return urllib.request.build_opener(_NoRedirect()).open(request, timeout=timeout)
    import ssl
    import io
    if __package__:
        from .mailbox_config import proxy_socket
    else:
        from mailbox_config import proxy_socket
    parsed = urllib.parse.urlsplit(request.full_url)
    sock = proxy_socket(proxy, parsed.hostname, parsed.port or 443, timeout=timeout)
    with ssl.create_default_context().wrap_socket(sock, server_hostname=parsed.hostname) as secure:
        secure.settimeout(timeout)
        body = request.data or b''
        method = request.get_method().encode('ascii')
        target = (parsed.path or '/') + (('?' + parsed.query) if parsed.query else '')
        secure.sendall(method + b' ' + target.encode('ascii') + b' HTTP/1.1\r\n')
        headers = {key: value for key, value in request.header_items()}
        headers['Host'] = parsed.hostname
        headers['Connection'] = 'close'
        if body or method in (b'POST', b'PUT', b'PATCH'):
            headers['Content-Length'] = str(len(body))
        for key, value in headers.items(): secure.sendall(f'{key}: {value}\r\n'.encode('latin-1'))
        secure.sendall(b'\r\n' + body)
        received = bytearray()
        while True:
            chunk = secure.recv(65536)
            if not chunk: break
            received.extend(chunk)
    response = http.client.HTTPResponse(_OAuthBytesSocket(bytes(received))); response.begin()
    if response.status >= 400:
        raise urllib.error.HTTPError(request.full_url, response.status, 'OAuth error', response.headers, None)
    return response


def _post_json(url, values, timeout=30, proxy=None):
    request = urllib.request.Request(
        url,
        data=urllib.parse.urlencode(values).encode("ascii"),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        with _open_credentials_request(request, timeout, proxy=proxy) as response:
            value = json.load(response)
    except urllib.error.HTTPError as error:
        status = error.code
        try:
            with error:
                body = json.load(error)
            code = _safe_error(str(body.get("error", ""))) if isinstance(body, dict) else "authorization_failed"
        except (ValueError, OSError, TypeError):
            body = {}
            code = "authorization_failed"
        if (url == GOOGLE_TOKEN and "client_secret" not in values and isinstance(body, dict)
                and re.search(r"client_secret\s+is\s+missing", str(body.get("error_description", "")), re.I)):
            raise RuntimeError(
                "Google requires this desktop app's OAuth client secret. Enter it and sign in again."
            ) from None
        raise RuntimeError(f"OAuth token request failed (HTTP {status}, {code}).") from None
    except (urllib.error.URLError, TimeoutError, OSError):
        raise RuntimeError("OAuth token request failed due to a network error.") from None
    except ValueError:
        raise RuntimeError("OAuth token endpoint returned an invalid response.") from None
    if not isinstance(value, dict):
        raise RuntimeError("OAuth token endpoint returned an invalid response.")
    if value.get("error"):
        raise RuntimeError("OAuth token request failed (" + _safe_error(str(value["error"])) + ").")
    return value


def _get_json(url, access_token, timeout=30, proxy=None):
    request = urllib.request.Request(
        url, headers={"Authorization": "Bearer " + access_token},
    )
    try:
        with _open_credentials_request(request, timeout, proxy=proxy) as response:
            value = json.load(response)
    except urllib.error.HTTPError as error:
        raise RuntimeError(f"OAuth identity verification failed (HTTP {error.code}).") from None
    except (urllib.error.URLError, TimeoutError, OSError):
        raise RuntimeError("OAuth identity verification failed due to a network error.") from None
    except ValueError:
        raise RuntimeError("OAuth identity endpoint returned an invalid response.") from None
    if not isinstance(value, dict):
        raise RuntimeError("OAuth identity endpoint returned an invalid response.")
    return value


class _CallbackServer(http.server.HTTPServer):
    allow_reuse_address = False

    def __init__(self, address, state, callback_path=CALLBACK_PATH):
        self.state = state
        self.callback_path = callback_path
        self.result = None
        super().__init__(address, _CallbackHandler)
        self.timeout = 0.5

    def get_request(self):
        connection, address = super().get_request()
        # A speculative browser connection must not stall the callback loop.
        connection.settimeout(2)
        return connection, address


class _CallbackHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urllib.parse.urlsplit(self.path)
        if parsed.path != self.server.callback_path:
            self._respond(404, "This sign-in callback is not available.")
            return
        query = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)
        states = query.get("state", [])
        if (len(states) != 1 or not states[0].isascii()
                or not hmac.compare_digest(states[0], self.server.state)):
            self._respond(400, "The sign-in response could not be verified. Return to the app and try again.")
            return
        errors = query.get("error", [])
        codes = query.get("code", [])
        if errors and not codes:
            if len(errors) != 1:
                self._respond(400, "The sign-in response was invalid.")
                return
            self.server.result = {"error": _safe_error(errors[0])}
            self._respond(200, "Sign-in was not completed. You can return to the app.")
        elif not errors and len(codes) == 1 and codes[0] and len(codes[0]) <= 8192:
            self.server.result = {"code": codes[0]}
            self._respond(200, "Authorization received. Return to Email Assistant to finish signing in.")
        else:
            self._respond(400, "The sign-in response was incomplete. Return to the app and try again.")

    def _respond(self, status, message):
        body = (
            "<!doctype html><meta charset=utf-8><title>Mail Secretary</title>"
            "<p>" + message + "</p>"
        ).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Pragma", "no-cache")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", "default-src 'none'; frame-ancestors 'none'")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args):
        return


def _receive_authorization_response(server, timeout):
    deadline = time.monotonic() + timeout
    while server.result is None and time.monotonic() < deadline:
        server.handle_request()
    if server.result is None:
        raise RuntimeError("Sign-in timed out. Start the sign-in again.")
    if "error" in server.result:
        raise RuntimeError("Sign-in was not completed (" + server.result["error"] + ").")
    return server.result["code"]


def _verify_google_identity(access_token, requested_email, get_json):
    profile = get_json(GOOGLE_USERINFO, access_token)
    returned_email = str(profile.get("email", "")).strip()
    if not returned_email:
        raise RuntimeError("The provider did not return an email address; the account was not saved.")
    if profile.get("email_verified") is not True:
        raise RuntimeError("Google did not verify the signed-in email address.")
    if returned_email.casefold() != requested_email.casefold():
        raise RuntimeError("The signed-in email does not match the address entered in the app.")
    return returned_email


def _verify_microsoft_mailbox(access_token, requested_email, mailbox_proxy):
    # Microsoft Graph UserInfo requires a Graph token. Test this IMAP token on
    # its own resource, with the exact requested mailbox as the XOAUTH2 user.
    if __package__:
        from .mailbox_config import connect
    else:
        from mailbox_config import connect
    settings = {
        "account": requested_email, "host": MICROSOFT_IMAP_HOST, "port": 993,
        "security": "ssl", "mail_folder": "INBOX", "mail_provider": "outlook",
        "mail_auth": "oauth2", "oauth_mode": "manual",
        **{key: mailbox_proxy[key] for key in ("proxy_mode", "proxy_host", "proxy_port") if key in mailbox_proxy},
    }
    try:
        connection = connect(settings, access_token)
    except Exception:
        raise RuntimeError(
            "Microsoft could not verify IMAP access to the entered mailbox. "
            "Check the address, enable IMAP in Outlook, and check the network or mailbox proxy."
        ) from None
    try:
        connection.logout()
    except Exception:
        pass
    return requested_email


def _validate_scopes(provider, token_response, config):
    response_scope = token_response.get("scope")
    if response_scope is None:
        return
    granted = set(str(response_scope).split())
    if provider == "microsoft":
        granted_folded = {scope.casefold() for scope in granted}
        valid = all(any(alias in granted_folded for alias in aliases) for aliases in _MICROSOFT_SCOPE_ALIASES)
    else:
        valid = all(scope in granted for scope in config.get("required_scopes", (config["required_scope"],)))
    if not valid:
        raise RuntimeError("The provider did not grant the required mail access permission.")


def authorize(provider, email, client_id, *, tenant="common", client_secret="", mailbox_proxy=None,
              open_browser=None, post_json=None, get_json=None, timeout=CALLBACK_TIMEOUT):
    """Open the provider consent page and return a refreshable credential bundle.

    The caller owns secure storage of the returned bundle. No token is printed,
    persisted to disk, or placed on the clipboard by this module.
    """
    requested_email = _validate_email(email)
    client_id = _validate_client_id(provider, client_id)
    config = _provider_config(provider, tenant)
    google_secret = _validate_client_secret(client_secret) if provider == "google" else ""
    if mailbox_proxy is not None and not isinstance(mailbox_proxy, dict):
        raise ValueError("Mailbox proxy settings are invalid.")
    mailbox_proxy = mailbox_proxy or {}
    try:
        if __package__:
            from .mailbox_config import resolve_proxy
        else:
            from mailbox_config import resolve_proxy
        resolved_proxy = resolve_proxy(mailbox_proxy)
    except Exception:
        raise ValueError("Mailbox proxy settings are invalid or unavailable.") from None
    mailbox_proxy = {**mailbox_proxy, 'resolved_proxy': resolved_proxy}
    post_json = post_json or (lambda url, payload, timeout=30: _post_json(
        url, payload, timeout, proxy=resolved_proxy))
    get_json = get_json or (lambda url, token, timeout=30: _get_json(
        url, token, timeout, proxy=resolved_proxy))
    open_browser = open_browser or webbrowser.open
    verifier, challenge = create_pkce_pair()
    state = _b64url(secrets.token_bytes(32))
    callback_path = "/"
    server = _CallbackServer(("127.0.0.1", 0), state, callback_path)
    try:
        # Desktop OAuth clients use the bare loopback URI. Google requires its
        # ephemeral port; Microsoft ignores the localhost port when matching.
        redirect_uri = f"http://{config['redirect_host']}:{server.server_port}"
        query = {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": config["scope"],
            "state": state,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "login_hint": requested_email,
            "prompt": "consent",
        }
        if provider == "google":
            query["access_type"] = "offline"
        else:
            query["response_mode"] = "query"
        authorization_url = config["authorize"] + "?" + urllib.parse.urlencode(query)
        try:
            opened = open_browser(authorization_url)
        except Exception:
            raise RuntimeError("Could not open the provider sign-in page.") from None
        if opened is False:
            raise RuntimeError("Could not open the provider sign-in page.")
        code = _receive_authorization_response(server, timeout)
        exchange = {
            "grant_type": "authorization_code",
            "client_id": client_id,
            "code": code,
            "redirect_uri": redirect_uri,
            "code_verifier": verifier,
        }
        if google_secret:
            exchange["client_secret"] = google_secret
        token_response = post_json(config["token"], exchange)
        access_token = token_response.get("access_token")
        refresh_token = token_response.get("refresh_token")
        if not _valid_token(access_token) or not _valid_token(refresh_token):
            raise RuntimeError("The provider did not return an access and refresh token. Sign-in again and approve offline access.")
        _validate_scopes(provider, token_response, config)
        try:
            lifetime = int(token_response.get("expires_in", 0))
        except (TypeError, ValueError):
            lifetime = 0
        if lifetime <= 0:
            raise RuntimeError("The provider returned an invalid token lifetime.")
        verified_email = (_verify_google_identity(access_token, requested_email, get_json)
                          if provider == "google" else _verify_microsoft_mailbox(access_token, requested_email, mailbox_proxy))
        return {
            "schema": 1,
            "provider": provider,
            "email": verified_email,
            "client_id": client_id,
            **({"tenant": tenant} if provider == "microsoft" else {}),
            **({"client_secret": google_secret} if google_secret else {}),
            "access_token": access_token,
            "refresh_token": refresh_token,
            "expires_at": int(time.time()) + lifetime,
            "scope": str(token_response.get("scope") or config["scope"]),
            "token_type": str(token_response.get("token_type") or "Bearer"),
        }
    finally:
        server.server_close()


def _valid_token(value):
    return isinstance(value, str) and bool(value) and all(33 <= ord(char) <= 126 for char in value)


def refresh(provider, credentials, client_id, *, tenant="common", post_json=None, proxy=None):
    """Refresh an expired access token, preserving a non-rotated refresh token."""
    client_id = _validate_client_id(provider, client_id)
    config = _provider_config(provider, tenant)
    if not isinstance(credentials, dict) or credentials.get("provider") != provider:
        raise ValueError("OAuth credentials do not match this provider.")
    refresh_token = credentials.get("refresh_token")
    if not _valid_token(refresh_token):
        raise ValueError("OAuth refresh token is missing; sign in again.")
    post_json = post_json or (lambda url, payload, timeout=30: _post_json(
        url, payload, timeout, proxy=proxy))
    request = {
        "grant_type": "refresh_token",
        "client_id": client_id,
        "refresh_token": refresh_token,
    }
    if provider == "google":
        google_secret = _validate_client_secret(credentials.get("client_secret", ""))
        if google_secret:
            request["client_secret"] = google_secret
    else:
        request["scope"] = config["scope"]
    token_response = post_json(config["token"], request)
    access_token = token_response.get("access_token")
    if not _valid_token(access_token):
        raise RuntimeError("The provider did not return a refreshed access token.")
    _validate_scopes(provider, token_response, config)
    try:
        lifetime = int(token_response.get("expires_in", 0))
    except (TypeError, ValueError):
        lifetime = 0
    if lifetime <= 0:
        raise RuntimeError("The provider returned an invalid token lifetime.")
    next_refresh_token = token_response.get("refresh_token") or refresh_token
    if not _valid_token(next_refresh_token):
        raise RuntimeError("The provider returned an invalid refresh token.")
    updated = dict(credentials)
    updated.update({
        "access_token": access_token,
        "refresh_token": next_refresh_token,
        "expires_at": int(time.time()) + lifetime,
        "scope": str(token_response.get("scope") or credentials.get("scope") or config["scope"]),
        "token_type": str(token_response.get("token_type") or "Bearer"),
    })
    return updated


def _credential_bundle(secret):
    """Decode a managed bundle, returning ``None`` for a legacy raw token."""
    if isinstance(secret, dict):
        value = secret
    elif isinstance(secret, str) and secret.lstrip().startswith("{"):
        try:
            value = json.loads(secret)
        except (TypeError, ValueError):
            return None
    else:
        return None
    if not isinstance(value, dict) or value.get("schema") != 1:
        return None
    if not value.get("provider") or not value.get("access_token"):
        raise ValueError("OAuth credentials are incomplete; sign in again.")
    return dict(value)


def access_token(secret, config=None, *, now=None, post_json=None, force_refresh=False):
    """Return ``(access_token, updated_bundle_or_none)``.

    ``secret`` may be a legacy raw access token or the JSON bundle returned by
    :func:`authorize`.  Managed bundles refresh when expired or within
    ``REFRESH_SKEW_SECONDS``.  ``config`` must contain ``provider`` and
    ``client_id`` for refresh; ``tenant`` is optional for Microsoft.  A raw
    token is returned unchanged and never triggers network activity.
    """
    bundle = _credential_bundle(secret)
    if bundle is None:
        token = str(secret or "")
        if not token or any(char in token for char in "\r\n\x00"):
            raise ValueError("OAuth access token is missing or invalid.")
        return token, None
    config = dict(config or {})
    provider = str(config.get("provider") or bundle.get("provider") or "")
    client_id = str(config.get("client_id") or bundle.get("client_id") or "")
    tenant = str(config.get("tenant") or bundle.get("tenant") or "common")
    if provider not in ("google", "microsoft"):
        raise ValueError("OAuth provider is invalid.")
    if not client_id:
        raise ValueError("OAuth client ID is required to refresh this sign-in.")
    bound_id = str(bundle.get("client_id") or "")
    id_matches = (client_id.casefold() == bound_id.casefold() if provider == "microsoft" else client_id == bound_id)
    if (provider != bundle.get("provider") or not id_matches
            or (provider == "microsoft" and tenant.casefold() != str(bundle.get("tenant") or "common").casefold())
            or (config.get("email") and str(config["email"]).casefold() != str(bundle.get("email") or "").casefold())):
        raise ValueError("OAuth credentials do not match this mailbox configuration. Sign in again.")
    current = int(time.time() if now is None else now)
    try:
        expires_at = int(bundle.get("expires_at", 0))
    except (TypeError, ValueError):
        expires_at = 0
    if not force_refresh and expires_at > current + REFRESH_SKEW_SECONDS:
        if not _valid_token(bundle["access_token"]):
            raise ValueError("OAuth access token is missing or invalid.")
        return str(bundle["access_token"]), None
    proxy = config.get('proxy')
    updated = refresh(provider, bundle, client_id, tenant=tenant, post_json=post_json, proxy=proxy)
    updated["client_id"] = client_id
    if provider == "microsoft":
        updated["tenant"] = tenant
    return str(updated["access_token"]), updated


def credential_json(bundle):
    """Serialize a managed bundle for protected platform storage."""
    if not isinstance(bundle, dict) or bundle.get("schema") != 1:
        raise ValueError("OAuth credential bundle is invalid.")
    required = ("provider", "email", "access_token", "refresh_token", "expires_at")
    if any(not bundle.get(key) for key in required):
        raise ValueError("OAuth credential bundle is incomplete.")
    return json.dumps(bundle, ensure_ascii=False, separators=(",", ":"))
