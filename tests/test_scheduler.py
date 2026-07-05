from hub.core.config import ConnectorSettings, HubConfig
from hub.core.storage import Storage
from hub.scheduler.runner import build_scheduler


def test_one_job_per_configured_connector(tmp_path):
    cfg = HubConfig(
        db_path=str(tmp_path / "t.duckdb"),
        connectors={
            "ga4": ConnectorSettings(schedule="0 6 * * *", options={"property_id": "1"}),
            "gsc": ConnectorSettings(schedule="30 6 * * *", options={"site_url": "x"}),
        })
    storage = Storage(cfg.db_path)
    scheduler = build_scheduler(cfg, storage)
    jobs = {j.id for j in scheduler.get_jobs()}
    assert jobs == {"sync_ga4", "sync_gsc"}


def test_no_connectors_no_jobs(tmp_path):
    cfg = HubConfig(db_path=str(tmp_path / "t.duckdb"))
    scheduler = build_scheduler(cfg, Storage(cfg.db_path))
    assert scheduler.get_jobs() == []
