from __future__ import annotations

import json
import re
from pathlib import Path

from hub.connectors.base import AuthError

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
        except (ValueError, RefreshError):
            creds = None  # corrupt token file or revoked refresh token -> re-consent

    if not client_path.exists():
        raise AuthError(
            "No Google credentials found.",
            hint=("Create an OAuth client (Desktop app) in Google Cloud Console under "
                  "APIs & Services > Credentials, download the JSON, and save it as "
                  f"{client_path}. Then run: hub doctor"
                  " If this worked before, delete the token file and re-authorize."))

    return login(secrets_dir, identity=identity, scopes=scopes)


def login(secrets_dir: str | Path, identity: str | None = None,
          scopes: list[str] | None = None):
    """Run the interactive browser consent flow for one identity and save its
    token. Sign in with WHICHEVER Google account should own this identity.

    Bounded by _LOGIN_TIMEOUT_SECONDS: if nobody completes sign-in in time
    (e.g. this got triggered by an unattended scheduled sync instead of an
    interactive session), raises AuthError instead of blocking forever."""
    from google_auth_oauthlib.flow import InstalledAppFlow

    secrets_dir = Path(secrets_dir)
    scopes = scopes or GOOGLE_SCOPES
    client_path = secrets_dir / "google_client.json"
    if not client_path.exists():
        raise AuthError(
            "No Google OAuth client found.",
            hint=f"Save your OAuth client JSON as {client_path} first.")
    flow = InstalledAppFlow.from_client_secrets_file(str(client_path), scopes)
    try:
        creds = flow.run_local_server(port=0, timeout_seconds=_LOGIN_TIMEOUT_SECONDS)
    except Exception as exc:  # noqa: BLE001 - WSGITimeoutError isn't guaranteed importable
        raise AuthError(
            f"Google sign-in for identity {identity or 'default'!r} was not "
            f"completed within {_LOGIN_TIMEOUT_SECONDS}s.",
            hint="If this ran unattended (a scheduled sync), the token needs "
                 f"re-consent - run 'hub login {identity or 'default'}' "
                 "interactively first. If you were signing in, just try again."
        ) from exc
    secrets_dir.mkdir(parents=True, exist_ok=True)
    token_path_for(secrets_dir, identity).write_text(creds.to_json(), encoding="utf-8")
    email = fetch_account_email(creds)
    if email:
        set_identity_label(secrets_dir, identity or "default", email)
    return creds
