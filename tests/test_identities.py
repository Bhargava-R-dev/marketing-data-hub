"""Multi-Google-account (identity) support across auth, connectors, config."""
import json

import pytest

from hub.connectors.base import group_by_identity
from hub.connectors.ga4 import GA4Connector
from hub.connectors.google_auth import (GOOGLE_SCOPES, get_credentials,
                                        list_identities, token_path_for)
from hub.connectors.gsc import SearchConsoleConnector
from hub.core.config import ConnectorSettings


def make_token(tmp_path, identity=None):
    token = {
        "token": f"tok-{identity or 'default'}", "refresh_token": "def",
        "client_id": "x", "client_secret": "y",
        "token_uri": "https://oauth2.googleapis.com/token",
        "scopes": GOOGLE_SCOPES,
        "expiry": "2099-01-01T00:00:00Z",
    }
    token_path_for(tmp_path, identity).write_text(json.dumps(token), encoding="utf-8")


# ---- token file naming --------------------------------------------------


def test_token_path_default_and_named(tmp_path):
    assert token_path_for(tmp_path).name == "google_token.json"
    assert token_path_for(tmp_path, "default").name == "google_token.json"
    assert token_path_for(tmp_path, "personal").name == "google_token_personal.json"


def test_token_path_rejects_unsafe_names(tmp_path):
    with pytest.raises(ValueError):
        token_path_for(tmp_path, "../evil")


def test_list_identities(tmp_path):
    assert list_identities(tmp_path) == []
    make_token(tmp_path)
    make_token(tmp_path, "personal")
    make_token(tmp_path, "client_x")
    assert list_identities(tmp_path) == ["default", "client_x", "personal"]


def test_get_credentials_loads_named_identity(tmp_path):
    make_token(tmp_path, "personal")
    creds = get_credentials(tmp_path, identity="personal")
    assert creds.token == "tok-personal"


# ---- identity grouping ---------------------------------------------------


def test_group_by_identity_defaults_unmapped():
    groups = group_by_identity(["111", "222", "333"],
                               {"identities": {"222": "personal"}})
    assert groups == {"default": ["111", "333"], "personal": ["222"]}


def test_group_by_identity_no_map():
    assert group_by_identity(["a"], {}) == {"default": ["a"]}


# ---- connectors authenticate per identity --------------------------------


def test_ga4_authenticates_each_identity(tmp_path, monkeypatch):
    seen = []
    monkeypatch.setattr("hub.connectors.ga4.get_credentials",
                        lambda sd, identity=None: seen.append(identity) or f"creds-{identity}")
    conn = GA4Connector(ConnectorSettings(options={
        "property_ids": ["111", "222", "333"],
        "identities": {"333": "personal"}}), tmp_path)
    conn.authenticate()
    assert sorted(seen, key=str) == ["default", "personal"]
    assert conn._groups == {"default": ["111", "222"], "personal": ["333"]}
    assert conn._creds["personal"] == "creds-personal"


def test_gsc_authenticates_each_identity(tmp_path, monkeypatch):
    monkeypatch.setattr("hub.connectors.gsc.get_credentials",
                        lambda sd, identity=None: f"creds-{identity}")
    conn = SearchConsoleConnector(ConnectorSettings(options={
        "site_urls": ["https://a.example/", "https://b.example/"],
        "identities": {"https://b.example/": "clientlogin"}}), tmp_path)
    conn.authenticate()
    assert conn._groups == {"default": ["https://a.example/"],
                            "clientlogin": ["https://b.example/"]}


# ---- config writing records identity ------------------------------------


def test_add_accounts_records_identity(tmp_path):
    from hub.core.accounts import add_accounts
    from hub.core.config import load_config

    p = tmp_path / "config.yaml"
    p.write_text("connectors:\n  ga4:\n    options: {property_ids: ['111']}\n",
                 encoding="utf-8")
    add_accounts(p, "ga4", [{"id": "999", "name": "Other Login Prop"}],
                 identity="personal")
    cfg = load_config(p)
    assert cfg.connectors["ga4"].options["identities"] == {"999": "personal"}
    # default identity adds must NOT create an identities entry
    add_accounts(p, "ga4", [{"id": "555", "name": "Main"}])
    cfg = load_config(p)
    assert "555" not in cfg.connectors["ga4"].options["identities"]
