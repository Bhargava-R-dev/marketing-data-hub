"""source_statuses(): per-source row counts, sync status, and freshness."""
from datetime import date

from hub.core.config import ConnectorSettings, HubConfig
from hub.core.models import UnifiedRow
from hub.core.status import source_statuses
from hub.core.storage import Storage


def test_configured_source_includes_freshness(tmp_path):
    store = Storage(str(tmp_path / "t.duckdb"))
    d = date.today()
    store.replace_rows("gsc", d, d, [
        UnifiedRow(date=d, source="gsc", account_id="x", account_name="A", clicks=1)])
    cfg = HubConfig(db_path=str(tmp_path / "t.duckdb"),
                    connectors={"gsc": ConnectorSettings(options={"site_url": "x"})})
    out = {e["source"]: e for e in source_statuses(cfg, store)}
    assert out["gsc"]["status"] == "active"
    assert out["gsc"]["freshness"]["status"] == "current"
    store.close()


def test_unconfigured_source_has_no_freshness(tmp_path):
    store = Storage(str(tmp_path / "t.duckdb"))
    cfg = HubConfig(db_path=str(tmp_path / "t.duckdb"), connectors={})
    out = {e["source"]: e for e in source_statuses(cfg, store)}
    assert out["gsc"]["status"] == "inactive"
    assert out["gsc"]["freshness"] is None
    store.close()


def test_configured_but_never_synced_reports_no_data(tmp_path):
    store = Storage(str(tmp_path / "t.duckdb"))
    cfg = HubConfig(db_path=str(tmp_path / "t.duckdb"),
                    connectors={"ga4": ConnectorSettings(options={"property_id": "1"})})
    out = {e["source"]: e for e in source_statuses(cfg, store)}
    assert out["ga4"]["freshness"]["status"] == "no_data"
    store.close()
