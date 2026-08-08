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


class FakeFlow:
    """Stand-in for InstalledAppFlow: captures redirect_uri, hands back an
    auth URL, and 'exchanges' whatever callback path login() feeds fetch_token."""
    def __init__(self):
        self.redirect_uri = None
        self.credentials = _FakeCreds()
        self.fetched_with = None

    def authorization_url(self, **kwargs):
        self.auth_kwargs = kwargs
        return ("https://accounts.google.com/o/oauth2/auth?fake=1", "state")

    def fetch_token(self, authorization_response=None):
        self.fetched_with = authorization_response


class _FakeCreds:
    def to_json(self):
        return "{}"


def _patch_login(monkeypatch, tmp_path, callback="/?code=abc123",
                 email="new@example.com"):
    """Wire login() up with a fake flow + a stubbed callback wait, so we can
    exercise everything except the real browser/localhost round-trip."""
    from hub.connectors import google_auth as ga

    (tmp_path / "google_client.json").write_text("{}", encoding="utf-8")
    flow = FakeFlow()
    monkeypatch.setattr(
        "google_auth_oauthlib.flow.InstalledAppFlow.from_client_secrets_file",
        lambda *a, **k: flow)
    monkeypatch.setattr(ga, "fetch_account_email", lambda creds: email)
    captured = {}

    def fake_wait(server, timeout_seconds):
        captured["timeout"] = timeout_seconds
        try:
            server.server_close()
        except Exception:
            pass
        if isinstance(callback, Exception):
            raise callback
        return callback

    monkeypatch.setattr(ga, "_wait_for_oauth_code", fake_wait)
    return flow, captured


def test_is_oauth_callback_discriminates_real_from_junk():
    from hub.connectors.google_auth import _is_oauth_callback
    assert _is_oauth_callback("/?code=abc&scope=x") is True
    assert _is_oauth_callback("/?error=access_denied") is True
    assert _is_oauth_callback("/favicon.ico") is False   # the request that broke it
    assert _is_oauth_callback("/") is False
    assert _is_oauth_callback("/?state=only") is False


def test_login_ignores_junk_request_then_captures_real_callback(tmp_path):
    """Integration: prove a favicon hit before the real redirect no longer
    steals the callback (the actual production bug)."""
    import threading
    import time
    import urllib.request

    from hub.connectors.google_auth import (_build_callback_server,
                                            _wait_for_oauth_code)

    server = _build_callback_server()
    port = server.server_port

    def client_traffic():
        time.sleep(0.2)
        try:  # spurious request first (this used to win and lose the code)
            urllib.request.urlopen(f"http://127.0.0.1:{port}/favicon.ico", timeout=2)
        except Exception:
            pass
        time.sleep(0.2)
        try:  # then the real OAuth redirect
            urllib.request.urlopen(f"http://127.0.0.1:{port}/?code=REALCODE&scope=x", timeout=2)
        except Exception:
            pass

    threading.Thread(target=client_traffic, daemon=True).start()
    path = _wait_for_oauth_code(server, timeout_seconds=10)
    server.server_close()
    assert "code=REALCODE" in path


def test_login_fetches_and_saves_label(tmp_path, monkeypatch):
    from hub.connectors import google_auth as ga

    flow, _ = _patch_login(monkeypatch, tmp_path)
    ga.login(tmp_path, identity="work", open_browser=False)
    assert get_identity_labels(tmp_path) == {"work": "new@example.com"}
    # login must have fed the captured callback path into the token exchange
    assert flow.fetched_with is not None and "code=abc123" in flow.fetched_with
    # and it requested offline+consent so a refresh_token is always returned
    assert flow.auth_kwargs.get("access_type") == "offline"
    assert flow.auth_kwargs.get("prompt") == "consent"


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


# ---- unattended-sync safety: bounded login timeout, not an infinite hang --

def test_login_passes_bounded_timeout_to_wait(tmp_path, monkeypatch):
    from hub.connectors import google_auth as ga

    _, captured = _patch_login(monkeypatch, tmp_path, email=None)
    ga.login(tmp_path, identity="work", open_browser=False)
    assert captured["timeout"] == ga._LOGIN_TIMEOUT_SECONDS
    assert captured["timeout"] is not None  # bounded, not an infinite hang


def test_login_timeout_raises_actionable_autherror_not_hanging(tmp_path, monkeypatch):
    from hub.connectors import google_auth as ga

    _patch_login(monkeypatch, tmp_path,
                 callback=TimeoutError("no OAuth callback within 300s"))
    with pytest.raises(AuthError) as exc:
        ga.login(tmp_path, identity="personal", open_browser=False)
    assert "personal" in str(exc.value)
    assert "hub login personal" in exc.value.hint


def test_oauthlib_scope_relaxation_is_enabled_on_import():
    """Google adds 'openid' to granted scopes with userinfo.email; without
    this relaxation, our own fetch_token() raises 'Scope has changed' and no
    token is saved (exactly the failure seen in the field)."""
    import os
    import hub.connectors.google_auth  # noqa: F401  (import applies the setdefault)
    assert os.environ.get("OAUTHLIB_RELAX_TOKEN_SCOPE") == "1"


# ---- unattended scheduled runs never pop a visible browser window --------

def test_login_refuses_immediately_when_unattended(tmp_path, monkeypatch):
    """The daily scheduled sync sets HUB_UNATTENDED - an identity needing
    re-consent must fail with a clean AuthError, not open a real browser
    window every day (the exact symptom reported in the field)."""
    from hub.connectors import google_auth as ga

    monkeypatch.setenv("HUB_UNATTENDED", "1")
    (tmp_path / "google_client.json").write_text("{}", encoding="utf-8")

    def must_not_be_called(*a, **k):
        raise AssertionError("must not touch the OAuth flow when unattended")
    monkeypatch.setattr(
        "google_auth_oauthlib.flow.InstalledAppFlow.from_client_secrets_file",
        must_not_be_called)

    with pytest.raises(AuthError) as exc:
        ga.login(tmp_path, identity="personal")
    assert "personal" in str(exc.value)
    assert "unattended" in str(exc.value).lower()
    assert "hub login personal" in exc.value.hint


def test_login_proceeds_normally_when_not_unattended(tmp_path, monkeypatch):
    """Sanity check: interactive use (no HUB_UNATTENDED) is unaffected."""
    from hub.connectors import google_auth as ga

    monkeypatch.delenv("HUB_UNATTENDED", raising=False)
    flow, _ = _patch_login(monkeypatch, tmp_path)
    ga.login(tmp_path, identity="work", open_browser=False)
    assert flow.fetched_with is not None
