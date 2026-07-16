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
    assert body["identities"] == ["default", "personal"]


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
