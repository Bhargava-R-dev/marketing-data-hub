"""Setup wizard: API endpoints, security token, config writing."""
import json

import pytest
from fastapi.testclient import TestClient

from hub.core.accounts import set_connector_options
from hub.core.config import load_config
from hub.setup_wizard import create_setup_app


@pytest.fixture()
def wizard(tmp_path):
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        "db_path: data/t.duckdb\nsecrets_dir: secrets\nexports_dir: exports\n"
        "connectors:\n  gsc:\n    options: {site_urls: ['https://a.example/'],\n"
        "      labels: {'https://a.example/': 'Site A'}}\n",
        encoding="utf-8")
    app = create_setup_app(cfg)
    client = TestClient(app)
    # fish the per-run token out of the served page (as the browser would)
    page = client.get("/").text
    token = page.split('const TOKEN = "')[1].split('"')[0]
    return client, {"X-Setup-Token": token}, cfg


def test_page_serves_and_embeds_config_path(wizard):
    client, _, cfg = wizard
    page = client.get("/").text
    assert "Marketing Data Hub" in page
    assert "api/state" in page


def test_state_requires_token(wizard):
    client, headers, _ = wizard
    assert client.get("/api/state").status_code == 403
    assert client.get("/api/state", headers={"X-Setup-Token": "wrong"}).status_code == 403
    r = client.get("/api/state", headers=headers)
    assert r.status_code == 200
    body = r.json()
    assert body["connectors"]["gsc"]["accounts"] == [
        {"id": "https://a.example/", "label": "Site A"}]


def test_state_reports_identities(wizard, tmp_path):
    client, headers, cfg = wizard
    secrets = tmp_path / "secrets"
    secrets.mkdir()
    (secrets / "google_token.json").write_text("{}", encoding="utf-8")
    (secrets / "google_token_personal.json").write_text("{}", encoding="utf-8")
    body = client.get("/api/state", headers=headers).json()
    idents = {i["identity"]: i for i in body["identities"]}
    assert set(idents) == {"default", "personal"}
    # invalid/placeholder token content -> no label yet, needs one re-auth click
    assert all(i["needs_reauth"] and i["label"] is None for i in idents.values())


def test_state_shows_real_email_label_when_available(wizard, tmp_path):
    from hub.connectors.google_auth import set_identity_label

    client, headers, cfg = wizard
    secrets = tmp_path / "secrets"
    secrets.mkdir()
    (secrets / "google_token.json").write_text("{}", encoding="utf-8")
    set_identity_label(secrets, "default", "seoteam@example.com")
    body = client.get("/api/state", headers=headers).json()
    default = next(i for i in body["identities"] if i["identity"] == "default")
    assert default["label"] == "seoteam@example.com"
    assert default["needs_reauth"] is False


def test_google_connect_auto_assigns_identity_no_name_needed(wizard, monkeypatch, tmp_path):
    client, headers, cfg = wizard
    (tmp_path / "secrets").mkdir(exist_ok=True)
    (tmp_path / "secrets" / "google_client.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr("hub.connectors.google_auth.login", lambda *a, **k: None)
    r = client.post("/api/google/connect", headers=headers, json={})
    assert r.status_code == 200
    assert r.json()["identity"] == "default"  # first connection -> 'default'


def test_google_connect_second_call_gets_new_slug(wizard, monkeypatch, tmp_path):
    client, headers, cfg = wizard
    (tmp_path / "secrets").mkdir(exist_ok=True)
    (tmp_path / "secrets" / "google_client.json").write_text("{}", encoding="utf-8")
    (tmp_path / "secrets" / "google_token.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr("hub.connectors.google_auth.login", lambda *a, **k: None)
    r = client.post("/api/google/connect", headers=headers, json={})
    assert r.json()["identity"] == "account2"  # 'default' already taken


def test_accounts_endpoint_filters_by_source(wizard, monkeypatch, tmp_path):
    client, headers, cfg = wizard
    (tmp_path / "secrets").mkdir(exist_ok=True)
    (tmp_path / "secrets" / "google_token.json").write_text("{}", encoding="utf-8")
    captured = {}
    monkeypatch.setattr("hub.connectors.google_auth.get_credentials",
                        lambda sd, scopes=None, identity=None: "creds")

    def fake_discover(creds, source=None):
        captured["source"] = source
        return []
    monkeypatch.setattr("hub.core.accounts.discover_all", fake_discover)
    r = client.get("/api/accounts", headers=headers, params={"source": "ga4"})
    assert r.json() == []
    assert captured["source"] == "ga4"


def test_accounts_add_via_wizard(wizard, monkeypatch):
    client, headers, cfg = wizard
    monkeypatch.setattr("hub.connectors.google_auth.get_credentials",
                        lambda sd, scopes=None, identity=None: "creds")
    monkeypatch.setattr("hub.core.accounts.discover_all",
                        lambda creds, source=None: [
                            {"source": "ga4", "id": "777", "name": "New Prop",
                             "parent": "Acct"}])
    r = client.post("/api/accounts/add", headers=headers,
                    json={"source": "ga4", "ids": ["777"], "identity": "default"})
    assert r.json() == {"added": ["777"]}
    loaded = load_config(cfg)
    assert loaded.connectors["ga4"].options["property_ids"] == ["777"]
    assert loaded.connectors["ga4"].options["labels"]["777"] == "New Prop"


def test_accounts_add_rejects_unknown_id(wizard, monkeypatch):
    client, headers, _ = wizard
    monkeypatch.setattr("hub.connectors.google_auth.get_credentials",
                        lambda sd, scopes=None, identity=None: "creds")
    monkeypatch.setattr("hub.core.accounts.discover_all",
                        lambda creds, source=None: [])
    r = client.post("/api/accounts/add", headers=headers,
                    json={"source": "ga4", "ids": ["999"]})
    assert "not visible" in r.json()["error"]


def test_connector_options_meta(wizard):
    client, headers, cfg = wizard
    r = client.post("/api/connector/options", headers=headers, json={
        "source": "meta_ads",
        "options": {"access_token": "tok", "ad_account_ids": ["act_1", "act_2"]}})
    assert sorted(r.json()["saved"]) == ["access_token", "ad_account_ids"]
    loaded = load_config(cfg)
    assert loaded.connectors["meta_ads"].options["ad_account_ids"] == ["act_1", "act_2"]


def test_connector_options_rejects_unknown_keys(wizard):
    client, headers, _ = wizard
    r = client.post("/api/connector/options", headers=headers, json={
        "source": "meta_ads", "options": {"evil_key": "x"}})
    assert "unsupported" in r.json()["error"]
    r = client.post("/api/connector/options", headers=headers, json={
        "source": "ga4", "options": {"access_token": "x"}})
    assert "error" in r.json()


def test_connector_options_drops_empty_values(wizard):
    client, headers, cfg = wizard
    client.post("/api/connector/options", headers=headers, json={
        "source": "google_ads",
        "options": {"developer_token": "dev", "customer_ids": ["1"],
                    "login_customer_id": ""}})  # empty -> not written
    loaded = load_config(cfg)
    assert "login_customer_id" not in loaded.connectors["google_ads"].options


def test_set_connector_options_merges_and_preserves(tmp_path):
    p = tmp_path / "c.yaml"
    p.write_text("connectors:\n  meta_ads:\n    options: {access_token: old}\n",
                 encoding="utf-8")
    set_connector_options(p, "meta_ads", {"ad_account_ids": ["act_9"]})
    loaded = load_config(p)
    assert loaded.connectors["meta_ads"].options["access_token"] == "old"
    assert loaded.connectors["meta_ads"].options["ad_account_ids"] == ["act_9"]


# ---- login failures are surfaced, not silently swallowed -----------------

def test_state_reports_login_error(wizard, monkeypatch, tmp_path):
    import time

    client, headers, cfg = wizard
    (tmp_path / "secrets").mkdir(exist_ok=True)
    (tmp_path / "secrets" / "google_client.json").write_text("{}", encoding="utf-8")

    def boom(*a, **k):
        raise Exception("Google sign-in for identity 'default' was not completed within 300s.")
    monkeypatch.setattr("hub.connectors.google_auth.login", boom)

    r = client.post("/api/google/connect", headers=headers, json={})
    assert r.json()["identity"] == "default"
    for _ in range(50):
        body = client.get("/api/state", headers=headers).json()
        if body["login_errors"].get("default"):
            break
        time.sleep(0.05)
    assert "not completed within 300s" in body["login_errors"]["default"]


def test_retrying_connect_clears_previous_error(wizard, monkeypatch, tmp_path):
    import time

    client, headers, cfg = wizard
    (tmp_path / "secrets").mkdir(exist_ok=True)
    (tmp_path / "secrets" / "google_client.json").write_text("{}", encoding="utf-8")

    def boom(*a, **k):
        raise Exception("boom")
    monkeypatch.setattr("hub.connectors.google_auth.login", boom)
    client.post("/api/google/connect", headers=headers, json={})
    for _ in range(50):
        if client.get("/api/state", headers=headers).json()["login_errors"].get("default"):
            break
        time.sleep(0.05)

    monkeypatch.setattr("hub.connectors.google_auth.login", lambda *a, **k: None)
    client.post("/api/google/connect", headers=headers, json={"identity": "default"})
    body = client.get("/api/state", headers=headers).json()
    assert "default" not in body["login_errors"]
