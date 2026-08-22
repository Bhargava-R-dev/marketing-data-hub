"""Dashboard: data assembly, standalone app, wizard-mounted route."""
import os
from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from hub.core.config import ConnectorSettings, HubConfig
from hub.core.models import UnifiedRow
from hub.core.storage import Storage
from hub.dashboard import build_dashboard, create_dashboard_app


def seeded_config(tmp_path):
    db = tmp_path / "hub.duckdb"
    store = Storage(str(db))
    d1, d2 = date(2026, 6, 1), date(2026, 6, 30)
    store.replace_rows("ga4", d1, d2, [
        UnifiedRow(date=d1, source="ga4", account_id="p1", account_name="Vetrotech",
                   sessions=100),
        UnifiedRow(date=d2, source="ga4", account_id="p2", account_name="Fevicreate",
                   sessions=50)])
    store.replace_rows("gsc", d1, d1, [
        UnifiedRow(date=d1, source="gsc", account_id="s1", account_name="Vetrotech",
                   clicks=10)])
    run_id = store.start_sync("ga4", d1, d2)
    store.finish_sync(run_id, 2, "success")
    store.close()
    return HubConfig(db_path=str(db), secrets_dir=str(tmp_path / "secrets"),
                     connectors={
                         "ga4": ConnectorSettings(options={
                             "property_ids": ["p1", "p2"],
                             "identities": {"p2": "personal"}}),
                         "gsc": ConnectorSettings(options={"site_urls": ["s1"]})})


def test_build_dashboard_groups_by_source_and_identity(tmp_path):
    cfg = seeded_config(tmp_path)
    data = build_dashboard(cfg)
    assert data["busy"] is False
    by_source = {g["source"]: g for g in data["groups"]}
    assert set(by_source) == {"ga4", "gsc"}

    ga4 = by_source["ga4"]
    assert ga4["last_sync"]["status"] == "success"
    names_to_identity = {a["account_name"]: a["identity"] for a in ga4["accounts"]}
    assert names_to_identity == {"Vetrotech": "default", "Fevicreate": "personal"}

    gsc = by_source["gsc"]
    assert gsc["last_sync"] is None  # never synced (only ga4 has a sync_runs row)
    assert gsc["accounts"][0]["account_name"] == "Vetrotech"


def test_build_dashboard_uses_real_email_label_when_available(tmp_path):
    from hub.connectors.google_auth import set_identity_label

    cfg = seeded_config(tmp_path)
    os.makedirs(cfg.secrets_dir, exist_ok=True)
    set_identity_label(cfg.secrets_dir, "personal", "me@example.com")
    data = build_dashboard(cfg)
    ga4 = next(g for g in data["groups"] if g["source"] == "ga4")
    labels = {a["account_name"]: a["identity"] for a in ga4["accounts"]}
    assert labels["Fevicreate"] == "me@example.com"
    assert labels["Vetrotech"] == "default"  # no label saved -> falls back to slug


def test_build_dashboard_empty_db_returns_no_groups(tmp_path):
    cfg = HubConfig(db_path=str(tmp_path / "empty.duckdb"),
                    secrets_dir=str(tmp_path / "secrets"))
    Storage(cfg.db_path).close()  # create schema, no rows
    data = build_dashboard(cfg)
    assert data == {"groups": [], "busy": False}


def test_build_dashboard_reports_busy_on_missing_db(tmp_path):
    cfg = HubConfig(db_path=str(tmp_path / "does_not_exist" / "x.duckdb"),
                    secrets_dir=str(tmp_path / "secrets"))
    # a nonexistent parent dir makes read_only open fail -> reported as busy,
    # not a crash (mirrors 'sync in progress' UX)
    data = build_dashboard(cfg)
    assert data["busy"] is True


def test_dashboard_app_page_and_data_endpoint(tmp_path):
    cfg_path = tmp_path / "config.yaml"
    cfg = seeded_config(tmp_path)
    cfg_path.write_text(
        f"db_path: {cfg.db_path}\nsecrets_dir: {cfg.secrets_dir}\n"
        "connectors:\n  ga4:\n    options: {property_ids: ['p1','p2'], "
        "identities: {p2: personal}}\n  gsc:\n    options: {site_urls: ['s1']}\n",
        encoding="utf-8")
    client = TestClient(create_dashboard_app(cfg_path))
    assert "Your Data" in client.get("/dashboard").text
    assert "Your Data" in client.get("/").text
    body = client.get("/api/dashboard-data").json()
    assert {g["source"] for g in body["groups"]} == {"ga4", "gsc"}


def test_dashboard_mounted_inside_wizard(tmp_path):
    from hub.setup_wizard import create_setup_app

    cfg_path = tmp_path / "config.yaml"
    cfg = seeded_config(tmp_path)
    cfg_path.write_text(
        f"db_path: {cfg.db_path}\nsecrets_dir: {cfg.secrets_dir}\n"
        "connectors:\n  ga4:\n    options: {property_ids: ['p1','p2']}\n",
        encoding="utf-8")
    client = TestClient(create_setup_app(cfg_path))
    # dashboard routes work WITHOUT the wizard's setup token (read-only, no gate)
    r = client.get("/api/dashboard-data")
    assert r.status_code == 200
    # reflects what's actually IN THE DB (both sources, from seeded_config),
    # not just what this particular config.yaml happens to list
    assert {g["source"] for g in r.json()["groups"]} == {"ga4", "gsc"}


def test_build_dashboard_includes_per_account_freshness(tmp_path):
    """Freshness is per-account, not just per-source - a source-wide date
    range can look healthy while one specific brand has quietly gone stale."""
    cfg = seeded_config(tmp_path)  # Fevicreate's ga4 row is dated 2026-06-30
    data = build_dashboard(cfg)
    ga4 = next(g for g in data["groups"] if g["source"] == "ga4")
    fevicreate = next(a for a in ga4["accounts"] if a["account_name"] == "Fevicreate")
    assert fevicreate["freshness"]["status"] == "stale"
    assert fevicreate["freshness"]["days_behind"] > 0


def test_build_dashboard_includes_per_account_gap_days(tmp_path):
    """A hole in the MIDDLE of an account's range (not just at the end) -
    freshness alone can't catch this since latest_date still looks recent."""
    db = tmp_path / "hub.duckdb"
    store = Storage(str(db))
    store.replace_rows("gsc", date(2026, 5, 1), date(2026, 5, 1), [
        UnifiedRow(date=date(2026, 5, 1), source="gsc", account_id="s1",
                   account_name="Vetrotech", clicks=1)])
    store.replace_rows("gsc", date(2026, 5, 5), date(2026, 5, 5), [
        UnifiedRow(date=date(2026, 5, 5), source="gsc", account_id="s1",
                   account_name="Vetrotech", clicks=1)])
    store.close()
    cfg = HubConfig(db_path=str(db), secrets_dir=str(tmp_path / "secrets"),
                    connectors={"gsc": ConnectorSettings(options={"site_urls": ["s1"]})})
    data = build_dashboard(cfg)
    gsc = next(g for g in data["groups"] if g["source"] == "gsc")
    assert gsc["accounts"][0]["gap_days"] == 3  # May 2,3,4 missing
