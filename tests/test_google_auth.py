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


# ---- identity labels (real Google email, not internal slug) --------------

from hub.connectors.google_auth import (backfill_identity_labels,
                                        fetch_account_email,
                                        get_identity_labels, set_identity_label,
                                        token_path_for)


def make_token(tmp_path, identity=None):
    token = {
        "token": "abc", "refresh_token": "def",
        "client_id": "x", "client_secret": "y",
        "token_uri": "https://oauth2.googleapis.com/token",
        "scopes": GOOGLE_SCOPES,
        "expiry": "2099-01-01T00:00:00Z",
    }
    token_path_for(tmp_path, identity).write_text(json.dumps(token), encoding="utf-8")


def test_labels_empty_by_default(tmp_path):
    assert get_identity_labels(tmp_path) == {}


def test_set_and_get_label(tmp_path):
    set_identity_label(tmp_path, "default", "seoteam@example.com")
    set_identity_label(tmp_path, "personal", "me@example.com")
    assert get_identity_labels(tmp_path) == {
        "default": "seoteam@example.com", "personal": "me@example.com"}


def test_set_label_none_identity_uses_default(tmp_path):
    set_identity_label(tmp_path, None, "a@example.com")
    assert get_identity_labels(tmp_path) == {"default": "a@example.com"}


def test_get_labels_survives_corrupt_file(tmp_path):
    (tmp_path / "identity_labels.json").write_text("not json", encoding="utf-8")
    assert get_identity_labels(tmp_path) == {}


def test_fetch_account_email_success(monkeypatch):
    class FakeUserinfo:
        def get(self):
            return self

        def execute(self):
            return {"email": "person@example.com"}

    class FakeService:
        def userinfo(self):
            return FakeUserinfo()

    monkeypatch.setattr("googleapiclient.discovery.build", lambda *a, **k: FakeService())
    assert fetch_account_email(object()) == "person@example.com"


def test_fetch_account_email_missing_scope_returns_none(monkeypatch):
    def boom(*a, **k):
        raise Exception("insufficient scope")
    monkeypatch.setattr("googleapiclient.discovery.build", boom)
    assert fetch_account_email(object()) is None


def test_login_fetches_and_saves_label(tmp_path, monkeypatch):
    from hub.connectors import google_auth as ga

    (tmp_path / "google_client.json").write_text("{}", encoding="utf-8")

    class FakeCreds:
        def to_json(self):
            return "{}"

    class FakeFlow:
        def run_local_server(self, port):
            return FakeCreds()

    monkeypatch.setattr(
        "google_auth_oauthlib.flow.InstalledAppFlow.from_client_secrets_file",
        lambda *a, **k: FakeFlow())
    monkeypatch.setattr(ga, "fetch_account_email", lambda creds: "new@example.com")
    ga.login(tmp_path, identity="work")
    assert get_identity_labels(tmp_path) == {"work": "new@example.com"}


def test_backfill_skips_already_labelled(tmp_path):
    make_token(tmp_path, "personal")
    set_identity_label(tmp_path, "personal", "cached@example.com")
    labels = backfill_identity_labels(tmp_path)
    assert labels == {"personal": "cached@example.com"}


def test_backfill_fills_valid_unlabelled_token(tmp_path, monkeypatch):
    from hub.connectors import google_auth as ga

    make_token(tmp_path, "personal")  # has full GOOGLE_SCOPES incl. email scope
    monkeypatch.setattr(ga, "fetch_account_email", lambda creds: "found@example.com")
    labels = backfill_identity_labels(tmp_path)
    assert labels == {"personal": "found@example.com"}
    assert get_identity_labels(tmp_path) == {"personal": "found@example.com"}


def test_backfill_leaves_underscoped_token_unlabelled(tmp_path):
    token = {
        "token": "abc", "refresh_token": "def",
        "client_id": "x", "client_secret": "y",
        "token_uri": "https://oauth2.googleapis.com/token",
        "scopes": ["https://www.googleapis.com/auth/analytics.readonly"],  # no email scope
        "expiry": "2099-01-01T00:00:00Z",
    }
    token_path_for(tmp_path, "old").write_text(json.dumps(token), encoding="utf-8")
    assert backfill_identity_labels(tmp_path) == {}
    assert get_identity_labels(tmp_path) == {}
