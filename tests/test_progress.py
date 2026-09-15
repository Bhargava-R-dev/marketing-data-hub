import json

from hub.core.config import HubConfig
from hub.core.progress import SyncProgress, configured_accounts, progress_path


def test_configured_accounts_lists_every_target_with_labels():
    cfg = HubConfig(connectors={
        "ga4": {"options": {"property_ids": ["1", "2"], "labels": {"1": "Brand A"},
                            "identities": {"2": "personal"}}},
        "gsc": {"options": {"site_url": "https://a.example/"}},
    })
    rows = configured_accounts(cfg)
    assert rows == [
        {"source": "ga4", "account_id": "1", "label": "Brand A", "identity": "default"},
        {"source": "ga4", "account_id": "2", "label": "2", "identity": "personal"},
        {"source": "gsc", "account_id": "https://a.example/",
         "label": "https://a.example/", "identity": "default"},
    ]
    assert configured_accounts(cfg, ["gsc"])[0]["source"] == "gsc"


def test_progress_path_sits_in_home_logs(tmp_path):
    from hub.core.config import load_config
    (tmp_path / "config.yaml").write_text("db_path: hub.duckdb\nconnectors: {}\n", encoding="utf-8")
    cfg = load_config(tmp_path / "config.yaml")
    # beside the config file, regardless of where db_path points
    assert progress_path(cfg) == tmp_path / "logs" / "sync_progress.json"


def test_progress_lifecycle_writes_atomically(tmp_path):
    path = tmp_path / "logs" / "sync_progress.json"
    p = SyncProgress(path)
    p.begin([{"source": "ga4", "account_id": "1", "label": "A", "identity": "default"},
             {"source": "ga4", "account_id": "2", "label": "B", "identity": "default"}])
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["finished_at"] is None
    assert [a["status"] for a in data["accounts"]] == ["pending", "pending"]

    p.account_update("ga4", "1", rows=10, reports_total=2)
    assert SyncProgress.read(path)["accounts"][0] == {
        "source": "ga4", "account_id": "1", "label": "A", "identity": "default",
        "status": "running", "rows": 10, "reports_done": 1, "error": None}
    p.account_update("ga4", "1", rows=5, reports_total=2)
    assert SyncProgress.read(path)["accounts"][0]["status"] == "done"
    assert SyncProgress.read(path)["accounts"][0]["rows"] == 15

    p.source_error("ga4", "boom")
    accts = SyncProgress.read(path)["accounts"]
    assert accts[0]["status"] == "done"
    assert accts[1] == {"source": "ga4", "account_id": "2", "label": "B",
                        "identity": "default", "status": "error", "rows": 0,
                        "reports_done": 0, "error": "boom"}

    p.finish()
    assert SyncProgress.read(path)["finished_at"] is not None
    assert not list(tmp_path.glob("logs/*.tmp"))


def test_read_missing_returns_none(tmp_path):
    assert SyncProgress.read(tmp_path / "nope.json") is None


def test_account_error_marks_only_that_account(tmp_path):
    path = tmp_path / "p.json"
    p = SyncProgress(path)
    p.begin([{"source": "gsc", "account_id": "1", "label": "A", "identity": "default"},
             {"source": "gsc", "account_id": "2", "label": "B", "identity": "default"}])
    p.account_error("gsc", "1", "no permission")
    state = SyncProgress.read(path)
    assert state["accounts"][0] == {"source": "gsc", "account_id": "1", "label": "A",
                                    "identity": "default", "status": "error",
                                    "rows": 0, "reports_done": 0, "error": "no permission"}
    assert state["accounts"][1]["status"] == "pending"  # untouched


def test_account_error_ignores_unknown_account(tmp_path):
    p = SyncProgress(tmp_path / "p.json")
    p.begin([])
    p.account_error("gsc", "missing", "x")  # must not raise
