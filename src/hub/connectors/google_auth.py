from __future__ import annotations

import re
from pathlib import Path

from hub.connectors.base import AuthError

GOOGLE_SCOPES = [
    "https://www.googleapis.com/auth/analytics.readonly",
    "https://www.googleapis.com/auth/webmasters.readonly",
    "https://www.googleapis.com/auth/yt-analytics.readonly",
    "https://www.googleapis.com/auth/adwords",
]

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
    token. Sign in with WHICHEVER Google account should own this identity."""
    from google_auth_oauthlib.flow import InstalledAppFlow

    secrets_dir = Path(secrets_dir)
    scopes = scopes or GOOGLE_SCOPES
    client_path = secrets_dir / "google_client.json"
    if not client_path.exists():
        raise AuthError(
            "No Google OAuth client found.",
            hint=f"Save your OAuth client JSON as {client_path} first.")
    flow = InstalledAppFlow.from_client_secrets_file(str(client_path), scopes)
    creds = flow.run_local_server(port=0)
    secrets_dir.mkdir(parents=True, exist_ok=True)
    token_path_for(secrets_dir, identity).write_text(creds.to_json(), encoding="utf-8")
    return creds
