from datetime import date

import pytest
from fastapi.testclient import TestClient

from hub.api.app import create_app
from hub.core.config import ConnectorSettings, HubConfig
from hub.core.models import UnifiedRow
from hub.core.storage import Storage

KEY = "test-key"


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("HUB_API_KEY", KEY)
    store = Storage(str(tmp_path / "t.duckdb"))
    d = date(2026, 7, 1)
    store.replace_rows("ga4", d, d, [
        UnifiedRow(date=d, source="ga4", account_id="p1", campaign="summer",
                   sessions=100, conversions=5)])
    store.replace_rows("gsc", d, d, [
        UnifiedRow(date=d, source="gsc", account_id="s1", clicks=30, impressions=900,
                   extras={"position": 12.0})])
    config = HubConfig(connectors={
        "ga4": ConnectorSettings(options={"property_id": "p1"}),
        "gsc": ConnectorSettings(options={"site_url": "s1"})})
    app = create_app(config, storage=store)
    return TestClient(app)


def auth(params=None):
    return {"params": params or {}, "headers": {"X-API-Key": KEY}}


def test_requires_api_key(client):
    assert client.get("/connectors").status_code == 401
    assert client.get("/connectors", headers={"X-API-Key": KEY}).status_code == 200


def test_list_connectors(client):
    body = client.get("/connectors", headers={"X-API-Key": KEY}).json()
    by_source = {c["source"]: c for c in body}
    assert by_source["ga4"]["status"] == "active"
    assert by_source["ga4"]["rows"] == 1
    assert by_source["meta_ads"]["status"] == "inactive"


def test_fields_endpoint(client):
    body = client.get("/connectors/gsc/fields", headers={"X-API-Key": KEY}).json()
    names = [f["name"] for f in body]
    assert "position" in names and "clicks" in names


def test_data_endpoint_all_sources(client):
    r = client.get("/connectors/all/data", headers={"X-API-Key": KEY},
                   params={"fields": "date,source,clicks,sessions",
                           "date_from": "2026-07-01", "date_to": "2026-07-01"})
    assert r.status_code == 200
    rows = r.json()["data"]
    assert {r["source"] for r in rows} == {"ga4", "gsc"}


def test_data_endpoint_single_source_with_preset(client):
    r = client.get("/connectors/gsc/data", headers={"X-API-Key": KEY},
                   params={"fields": "date,clicks,position", "date_preset": "ytd"})
    assert r.status_code == 200
    assert r.json()["data"][0]["clicks"] == 30


def test_data_endpoint_rejects_unknown_field(client):
    r = client.get("/connectors/gsc/data", headers={"X-API-Key": KEY},
                   params={"fields": "date,bogus_metric"})
    assert r.status_code == 400
    assert "bogus_metric" in r.json()["detail"]


def test_csv_format(client):
    r = client.get("/connectors/gsc/data", headers={"X-API-Key": KEY},
                   params={"fields": "date,clicks", "date_preset": "ytd",
                           "format": "csv"})
    assert r.headers["content-type"].startswith("text/csv")
    assert r.text.splitlines()[0] == "date,clicks"


def test_reports_endpoint(client):
    body = client.get("/connectors/gsc/reports", headers={"X-API-Key": KEY}).json()
    names = {r["report"] for r in body}
    assert {"core", "queries", "pages", "devices", "countries"} <= names
    queries = next(r for r in body if r["report"] == "queries")
    assert "query" in queries["dimensions"]


def test_fields_endpoint_per_report(client):
    body = client.get("/connectors/ga4/fields", headers={"X-API-Key": KEY},
                      params={"report": "channels"}).json()
    assert "channel" in [f["name"] for f in body]
    r = client.get("/connectors/ga4/fields", headers={"X-API-Key": KEY},
                   params={"report": "bogus"})
    assert r.status_code == 404


def test_data_endpoint_report_param(client, tmp_path):
    # breakdown rows must only be reachable via their report, never via core
    r = client.get("/connectors/gsc/data", headers={"X-API-Key": KEY},
                   params={"fields": "date,query,clicks", "date_preset": "ytd",
                           "report": "queries"})
    assert r.status_code == 200
    assert r.json()["data"] == []  # nothing synced into 'queries' in this fixture
    r = client.get("/connectors/gsc/data", headers={"X-API-Key": KEY},
                   params={"fields": "date,clicks", "date_preset": "ytd"})
    assert r.json()["data"][0]["clicks"] == 30  # core totals unaffected


def test_report_fields_accepted_by_validation(client):
    # 'channel' only exists in the ga4 channels report registry
    r = client.get("/connectors/ga4/data", headers={"X-API-Key": KEY},
                   params={"fields": "date,channel,sessions", "date_preset": "ytd",
                           "report": "channels"})
    assert r.status_code == 200
