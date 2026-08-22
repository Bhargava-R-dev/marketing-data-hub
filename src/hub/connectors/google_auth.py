from __future__ import annotations

import json
import os
import re
from pathlib import Path

from hub.connectors.base import AuthError

# Google always adds 'openid' to the granted scopes when 'userinfo.email' is
# requested. oauthlib treats any granted-vs-requested scope difference as a
# fatal error unless this is set. The library's own run_local_server sets it
# internally; since we run the token exchange ourselves, we set it here too.
os.environ.setdefault("OAUTHLIB_RELAX_TOKEN_SCOPE", "1")

GOOGLE_SCOPES = [
    "https://www.googleapis.com/auth/analytics.readonly",
    "https://www.googleapis.com/auth/webmasters.readonly",
    "https://www.googleapis.com/auth/yt-analytics.readonly",
    "https://www.googleapis.com/auth/adwords",
    "https://www.googleapis.com/auth/userinfo.email",
]

_LABELS_FILE = "identity_labels.json"
# an unattended run (the daily scheduled sync) has nobody to complete a
# browser consent flow - without a bound, a token needing re-consent hangs
# the process for hours until something force-kills it mid-blocking-socket-
# call, which corrupts CPython's interpreter state (a "Fatal Python error",
# not a catchable exception). Bounding it makes that same situation fail
# cleanly and fast instead. Generous enough for a real person to read an
# unfamiliar multi-scope consent screen and pick an account (120s proved too
# tight in practice), while still far short of the "hours" that caused the
# original crash.
_LOGIN_TIMEOUT_SECONDS = 300

_IDENTITY_RE = re.compile(r"^[A-Za-z0-9_-]+$")


def token_path_for(secrets_dir: str | Path, identity: str | None = None) -> Path:
    """Token file for one Google login. The unnamed/default identity keeps the
    original google_token.json; named identities (a second gmail, a client's
    own login, ...) live side by side as google_token_<name>.json."""
    secrets_dir = Path(secrets_dir)
    if not identity or identity == "default":
        return secrets_dir / "google_token.json"
    if not _IDENTITY_RE.match(identity):
        raise ValueError(f"invalid identity name {identity!r} "
                         "(letters, digits, - and _ only)")
    return secrets_dir / f"google_token_{identity}.json"


def list_identities(secrets_dir: str | Path) -> list[str]:
    """Names of every Google login that has a saved token ('default' first)."""
    secrets_dir = Path(secrets_dir)
    out = []
    if (secrets_dir / "google_token.json").exists():
        out.append("default")
    for p in sorted(secrets_dir.glob("google_token_*.json")):
        out.append(p.stem.removeprefix("google_token_"))
    return out


def get_identity_labels(secrets_dir: str | Path) -> dict[str, str]:
    """Map of identity slug -> real Google account email, for display.

    Identities connected before this feature (or that failed to fetch their
    email) are simply absent — callers show a 'needs re-auth' state for those."""
    path = Path(secrets_dir) / _LABELS_FILE
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def set_identity_label(secrets_dir: str | Path, identity: str, email: str) -> None:
    secrets_dir = Path(secrets_dir)
    labels = get_identity_labels(secrets_dir)
    labels[identity or "default"] = email
    (secrets_dir / _LABELS_FILE).write_text(json.dumps(labels, indent=2), encoding="utf-8")


def verify_identity_email(secrets_dir: str | Path, identity: str | None,
                          expected_email: str | None, target_label: str) -> None:
    """Refuse to proceed if the Google account currently behind `identity`
    isn't the one this target was configured for.

    This is the guard for the exact incident that happened in the field:
    reconnecting 'default' and 'personal' silently swapped which real
    account each slot held. Config still pointed by SLOT NAME ('default'),
    so every brand kept querying - just against the wrong account now,
    surfacing as confusing 403s far from the actual cause. Skips silently
    when there's nothing to check against: no expected_email was ever
    pinned (accounts added before this existed), or the current identity
    has no known label yet (e.g. still needs_reauth) - this check narrows
    an existing mismatch, it never blocks a previously-working setup."""
    if not expected_email:
        return
    current = get_identity_labels(secrets_dir).get(identity or "default")
    if current and current != expected_email:
        raise AuthError(
            f"{target_label!r} is configured for the Google account "
            f"{expected_email!r}, but identity {identity or 'default'!r} "
            f"currently holds {current!r}.",
            hint="A re-login likely picked a different Google account than "
                 f"before. Run 'hub login {identity or 'default'}' again and "
                 "choose the right account - or if this is intentional (the "
                 "account genuinely moved), delete the old pin under "
                 "identity_emails in config.yaml.")


def fetch_account_email(creds) -> str | None:
    """The email of the Google account behind these credentials, or None if
    it can't be determined (e.g. the token predates the email scope)."""
    try:
        from googleapiclient.discovery import build

        service = build("oauth2", "v2", credentials=creds, cache_discovery=False)
        return service.userinfo().get().execute().get("email")
    except Exception:  # noqa: BLE001 - missing scope / network issue -> no label yet
        return None


def backfill_identity_labels(secrets_dir: str | Path) -> dict[str, str]:
    """Opportunistically fill in labels for identities whose token is already
    valid and already carries the email scope (e.g. label file was lost, or
    this feature landed after the token was issued) — never opens a browser.
    Identities still on old, narrower scopes are left alone; the wizard shows
    those as needing one manual re-auth click."""
    from google.oauth2.credentials import Credentials

    secrets_dir = Path(secrets_dir)
    labels = get_identity_labels(secrets_dir)
    for identity in list_identities(secrets_dir):
        if identity in labels:
            continue
        try:
            creds = Credentials.from_authorized_user_file(
                str(token_path_for(secrets_dir, identity)))
        except (ValueError, OSError):
            continue
        email_scope = "https://www.googleapis.com/auth/userinfo.email"
        if email_scope not in (creds.scopes or []) or not creds.valid:
            continue
        email = fetch_account_email(creds)
        if email:
            labels[identity] = email
            set_identity_label(secrets_dir, identity, email)
    return labels


def get_credentials(secrets_dir: str | Path, scopes: list[str] | None = None,
                    identity: str | None = None):
    """Return google.oauth2 Credentials for one identity (Google login).
    First run for an identity opens a browser consent flow."""
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials

    secrets_dir = Path(secrets_dir)
    scopes = scopes or GOOGLE_SCOPES
    token_path = token_path_for(secrets_dir, identity)
    client_path = secrets_dir / "google_client.json"

    diagnostic_hint = None
    if token_path.exists():
        from google.auth.exceptions import RefreshError

        try:
            creds = Credentials.from_authorized_user_file(str(token_path))
            # a token cached with older, narrower scopes must trigger re-consent,
            # otherwise API calls fail later with opaque 403s
            if set(scopes) - set(creds.scopes or []):
                creds = None
            elif creds.valid:
                return creds
            elif creds.expired and creds.refresh_token:
                creds.refresh(Request())
                token_path.write_text(creds.to_json(), encoding="utf-8")
                return creds
        except (ValueError, RefreshError) as exc:
            creds = None  # corrupt token file or revoked refresh token -> re-consent
            # surface the SPECIFIC cause instead of a bare "needs re-consent" -
            # invalid_grant almost always means the OAuth app is stuck in
            # Testing mode (7-day refresh token expiry), which took real
            # manual debugging (calling creds.refresh() directly and reading
            # the raw exception) to work out once already
            if "invalid_grant" in str(exc):
                diagnostic_hint = _INVALID_GRANT_HINT

    if not client_path.exists():
        raise AuthError(
            "No Google credentials found.",
            hint=("Create an OAuth client (Desktop app) in Google Cloud Console under "
                  "APIs & Services > Credentials, download the JSON, and save it as "
                  f"{client_path}. Then run: hub doctor"
                  " If this worked before, delete the token file and re-authorize."))

    return login(secrets_dir, identity=identity, scopes=scopes,
                _diagnostic_hint=diagnostic_hint)


def _is_oauth_callback(path: str) -> bool:
    """True only for the real OAuth redirect (carries ?code= or ?error=).
    Browsers fire spurious requests to the loopback callback first - favicon,
    connectivity probes, preconnects - which must be ignored, or they get
    mistaken for the callback and the real auth code is lost."""
    import urllib.parse

    params = urllib.parse.parse_qs(urllib.parse.urlparse(path).query)
    return "code" in params or "error" in params


def _wait_for_oauth_code(server, timeout_seconds: int) -> str:
    """Serve the loopback callback, ignoring junk requests, until the real
    OAuth redirect arrives or the deadline passes. Returns the request path
    (with the ?code=...). Robust replacement for the library's single-shot
    handle_request(), which takes whatever request lands first."""
    import time

    server.timeout = 1  # poll interval so we can re-check the deadline
    deadline = time.monotonic() + timeout_seconds
    while server.captured_path is None:
        if time.monotonic() > deadline:
            raise TimeoutError(f"no OAuth callback within {timeout_seconds}s")
        server.handle_request()  # returns on a handled request OR on timeout
    return server.captured_path


def _build_callback_server():
    from http.server import BaseHTTPRequestHandler, HTTPServer

    class _Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802 - stdlib naming
            if _is_oauth_callback(self.path):
                self.server.captured_path = self.path
                body = (b"Sign-in complete. You can close this tab and return "
                        b"to the terminal.")
                self.send_response(200)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            else:  # spurious (favicon / probe) - acknowledge, keep waiting
                self.send_response(204)
                self.end_headers()

        def log_message(self, *args):  # silence per-request stderr noise
            pass

    server = HTTPServer(("127.0.0.1", 0), _Handler)
    server.captured_path = None
    return server


_INVALID_GRANT_HINT = (
    "This traces back to Google's 'invalid_grant: Token has been expired or "
    "revoked' error. The most common cause: your OAuth app's Google Cloud "
    "Console consent screen is still in 'Testing' status - Google auto-"
    "expires refresh tokens issued under Testing after about 7 days, no "
    "matter how active the account is, so this can recur every ~week until "
    "fixed. Fix: Google Cloud Console > APIs & Services > OAuth consent "
    "screen > check Publishing status; if it says 'Testing', click "
    "'Publish App' to move to Production (no code changes, removes the "
    "7-day expiry for good).")


def login(secrets_dir: str | Path, identity: str | None = None,
          scopes: list[str] | None = None, open_browser: bool = True,
          _diagnostic_hint: str | None = None):
    """Run the interactive browser consent flow for one identity and save its
    token. Sign in with WHICHEVER Google account should own this identity.

    Uses our own loopback callback server (not the library's single-shot
    handler, which loses the auth code to a browser's stray first request)
    and is bounded by _LOGIN_TIMEOUT_SECONDS so an unattended run fails fast
    instead of hanging for hours.

    Refuses outright (no browser, no server, immediate AuthError) when
    HUB_UNATTENDED is set - the scheduled sync scripts set this, so a token
    needing re-consent no longer pops a real, visible browser window during
    an unattended run every single day; it just logs a clean [FAIL].

    _diagnostic_hint (internal - set by get_credentials): when the token
    needed re-consent because of a specific detected failure (e.g. Google's
    invalid_grant), that root cause is prepended to the error instead of a
    bare 'needs re-consent' that gives no clue why - this took real manual
    debugging to work out once already."""
    if os.environ.get("HUB_UNATTENDED"):
        hint = (f"Run 'hub login {identity or 'default'}' interactively "
               "(not from the scheduled task) to fix this once.")
        if _diagnostic_hint:
            hint = f"{_diagnostic_hint} {hint}"
        raise AuthError(
            f"Identity {identity or 'default'!r} needs re-consent, but this "
            "is an unattended run - refusing to open an interactive browser.",
            hint=hint)

    import webbrowser

    from google_auth_oauthlib.flow import InstalledAppFlow

    secrets_dir = Path(secrets_dir)
    scopes = scopes or GOOGLE_SCOPES
    client_path = secrets_dir / "google_client.json"
    if not client_path.exists():
        raise AuthError(
            "No Google OAuth client found.",
            hint=f"Save your OAuth client JSON as {client_path} first.")

    flow = InstalledAppFlow.from_client_secrets_file(str(client_path), scopes)
    server = _build_callback_server()
    flow.redirect_uri = f"http://127.0.0.1:{server.server_port}/"
    # prompt=consent + offline guarantees a refresh_token even when re-consenting
    # an already-authorized account (otherwise Google may omit it)
    auth_url, _ = flow.authorization_url(access_type="offline", prompt="consent")
    if open_browser:
        webbrowser.open(auth_url, new=1)
    print(f"If your browser didn't open, visit this URL to authorize:\n{auth_url}")

    try:
        callback_path = _wait_for_oauth_code(server, _LOGIN_TIMEOUT_SECONDS)
    except TimeoutError as exc:
        raise AuthError(
            f"Google sign-in for identity {identity or 'default'!r} was not "
            f"completed within {_LOGIN_TIMEOUT_SECONDS}s.",
            hint="If this ran unattended (a scheduled sync), the token needs "
                 f"re-consent - run 'hub login {identity or 'default'}' "
                 "interactively first. If you were signing in, just try again."
        ) from exc
    finally:
        server.server_close()

    # oauthlib requires https in the response URL even for loopback
    flow.fetch_token(authorization_response=f"https://127.0.0.1:{server.server_port}"
                                            f"{callback_path}")
    creds = flow.credentials
    secrets_dir.mkdir(parents=True, exist_ok=True)
    token_path_for(secrets_dir, identity).write_text(creds.to_json(), encoding="utf-8")
    email = fetch_account_email(creds)
    if email:
        set_identity_label(secrets_dir, identity or "default", email)
    return creds
