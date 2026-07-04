from __future__ import annotations

from pathlib import Path

from hub.connectors.base import AuthError

GOOGLE_SCOPES = [
    "https://www.googleapis.com/auth/analytics.readonly",
    "https://www.googleapis.com/auth/webmasters.readonly",
    "https://www.googleapis.com/auth/yt-analytics.readonly",
    "https://www.googleapis.com/auth/adwords",
]


def get_credentials(secrets_dir: str | Path, scopes: list[str] | None = None):
    """Return google.oauth2 Credentials. First run opens a browser consent flow."""
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials

    secrets_dir = Path(secrets_dir)
    scopes = scopes or GOOGLE_SCOPES
    token_path = secrets_dir / "google_token.json"
    client_path = secrets_dir / "google_client.json"

    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), scopes)
        if creds.valid:
            return creds
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            token_path.write_text(creds.to_json(), encoding="utf-8")
            return creds

    if not client_path.exists():
        raise AuthError(
            "No Google credentials found.",
            hint=("Create an OAuth client (Desktop app) in Google Cloud Console under "
                  "APIs & Services > Credentials, download the JSON, and save it as "
                  f"{client_path}. Then run: hub doctor"))

    from google_auth_oauthlib.flow import InstalledAppFlow

    flow = InstalledAppFlow.from_client_secrets_file(str(client_path), scopes)
    creds = flow.run_local_server(port=0)
    secrets_dir.mkdir(parents=True, exist_ok=True)
    token_path.write_text(creds.to_json(), encoding="utf-8")
    return creds
