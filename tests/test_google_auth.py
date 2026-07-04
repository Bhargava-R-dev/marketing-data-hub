import json

import pytest

from hub.connectors.base import AuthError
from hub.connectors.google_auth import GOOGLE_SCOPES, get_credentials


def test_missing_client_file_raises_actionable_error(tmp_path):
    with pytest.raises(AuthError) as exc:
        get_credentials(tmp_path)
    assert "google_client.json" in exc.value.hint


def test_existing_valid_token_is_loaded(tmp_path):
    token = {
        "token": "abc", "refresh_token": "def",
        "client_id": "x", "client_secret": "y",
        "token_uri": "https://oauth2.googleapis.com/token",
        "scopes": GOOGLE_SCOPES,
        "expiry": "2099-01-01T00:00:00Z",
    }
    (tmp_path / "google_token.json").write_text(json.dumps(token), encoding="utf-8")
    creds = get_credentials(tmp_path)
    assert creds.token == "abc"


def test_underscoped_token_triggers_reconsent_path(tmp_path):
    token = {
        "token": "abc", "refresh_token": "def",
        "client_id": "x", "client_secret": "y",
        "token_uri": "https://oauth2.googleapis.com/token",
        "scopes": GOOGLE_SCOPES[:1],  # narrower than currently required
        "expiry": "2099-01-01T00:00:00Z",
    }
    (tmp_path / "google_token.json").write_text(json.dumps(token), encoding="utf-8")
    with pytest.raises(AuthError):  # no client file -> re-consent path errors actionably
        get_credentials(tmp_path)


def test_corrupt_token_file_falls_back_actionably(tmp_path):
    (tmp_path / "google_token.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(AuthError):
        get_credentials(tmp_path)
