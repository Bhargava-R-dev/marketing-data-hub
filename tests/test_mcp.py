import asyncio
from datetime import date

from hub.core.config import ConnectorSettings, HubConfig
from hub.core.models import UnifiedRow
from hub.core.storage import Storage
from hub.mcp.server import build_mcp


def make_config(tmp_path):
    return HubConfig(
        db_path=str(tmp_path / "t.duckdb"),
        connectors={"gsc": ConnectorSettings(options={"site_url": "x"})})


def seed(cfg):
    store = Storage(cfg.db_path)
    d = date.today()
    store.replace_rows("gsc", d, d, [
        UnifiedRow(date=d, source="gsc", account_id="x", account_name="Vetrotech",
                   clicks=12, impressions=300),
        UnifiedRow(date=d, source="gsc", account_id="y", account_name="Sharekhan",
                   clicks=7, impressions=100)])
    store.close()


def test_build_mcp_registers_tools(tmp_path):
    cfg = make_config(tmp_path)
    seed(cfg)
    mcp = build_mcp(cfg)
    # installed fastmcp (3.x) exposes async list_tools() -> Sequence[Tool],
    # not the 2.x get_tools() -> dict[str, Tool] the plan assumed.
    tools = asyncio.run(mcp.list_tools())
    names = {t.name for t in tools}
    assert {"list_sources", "list_fields", "query_metrics", "trigger_sync",
            "sync_status"} <= names


def test_query_metrics_tool_logic(tmp_path):
    cfg = make_config(tmp_path)
    seed(cfg)
    mcp = build_mcp(cfg)
    result = asyncio.run(mcp._call_query_metrics(  # exposed for tests
        fields=["date", "clicks"], date_preset="last_7d"))
    assert result["rows"][0]["clicks"] == 19  # both seeded brands aggregated


def test_query_metrics_brand_filter_fuzzy(tmp_path):
    cfg = make_config(tmp_path)
    seed(cfg)
    mcp = build_mcp(cfg)
    result = asyncio.run(mcp._call_query_metrics(
        fields=["date", "clicks"], date_preset="last_7d", brand="vetrotec"))
    assert result["matched_brands"] == ["Vetrotech"]
    assert len(result["rows"]) == 1
    assert result["rows"][0]["clicks"] == 12
    assert result["rows"][0]["account_name"] == "Vetrotech"


def test_query_metrics_unknown_brand_lists_available(tmp_path):
    cfg = make_config(tmp_path)
    seed(cfg)
    mcp = build_mcp(cfg)
    result = asyncio.run(mcp._call_query_metrics(
        fields=["date", "clicks"], date_preset="last_7d", brand="nike"))
    assert "error" in result
    assert result["available_brands"] == ["Sharekhan", "Vetrotech"]


def test_list_brands_tool(tmp_path):
    cfg = make_config(tmp_path)
    seed(cfg)
    mcp = build_mcp(cfg)
    tools = asyncio.run(mcp.list_tools())
    assert "list_brands" in {t.name for t in tools}


class FakeProc:
    def __init__(self, returncode=None):
        self.returncode = returncode  # None = still running

    def poll(self):
        return self.returncode


def test_trigger_sync_returns_immediately(tmp_path, monkeypatch):
    cfg = make_config(tmp_path)
    seed(cfg)
    spawned = {}

    def fake_popen(cmd, **kwargs):
        spawned["cmd"] = cmd
        return FakeProc(returncode=0)

    monkeypatch.setattr("hub.mcp.server.subprocess.Popen", fake_popen)
    mcp = build_mcp(cfg, config_path=str(tmp_path / "config.yaml"))
    result = asyncio.run(mcp._call_trigger_sync(source="all"))
    assert result["status"] == "started"
    assert "sync" in spawned["cmd"] and "all" in spawned["cmd"]


def test_trigger_sync_refuses_double_trigger_before_run_row_exists(tmp_path, monkeypatch):
    # the child takes ~1s to write its 'running' row; an immediate second
    # trigger must still be refused via the in-process child handle
    cfg = make_config(tmp_path)
    seed(cfg)
    monkeypatch.setattr("hub.mcp.server.subprocess.Popen",
                        lambda cmd, **kw: FakeProc(returncode=None))
    mcp = build_mcp(cfg, config_path=str(tmp_path / "config.yaml"))
    first = asyncio.run(mcp._call_trigger_sync(source="all"))
    second = asyncio.run(mcp._call_trigger_sync(source="all"))
    assert first["status"] == "started"
    assert second["status"] == "already_running"


def test_trigger_sync_refuses_while_sync_running(tmp_path, monkeypatch):
    cfg = make_config(tmp_path)
    seed(cfg)
    store = Storage(cfg.db_path)
    store.start_sync("gsc", date.today(), date.today())  # left in 'running'
    store.close()

    def explode(*args, **kwargs):
        raise AssertionError("must not spawn a second sync")

    monkeypatch.setattr("hub.mcp.server.subprocess.Popen", explode)
    mcp = build_mcp(cfg)
    result = asyncio.run(mcp._call_trigger_sync(source="all"))
    assert result["status"] == "already_running"


def test_sync_status_reports_last_runs(tmp_path):
    cfg = make_config(tmp_path)
    seed(cfg)
    store = Storage(cfg.db_path)
    run_id = store.start_sync("gsc", date.today(), date.today())
    store.finish_sync(run_id, 5, "success")
    store.close()
    mcp = build_mcp(cfg)
    result = asyncio.run(mcp._call_sync_status())
    assert result["runs"]["gsc"]["status"] == "success"
    assert result["runs"]["gsc"]["rows_written"] == 5
    assert result["sync_in_progress"] is False


def test_query_metrics_readable_error_while_db_locked(tmp_path):
    cfg = make_config(tmp_path)
    seed(cfg)
    mcp = build_mcp(cfg)
    writer = Storage(cfg.db_path)  # simulates a sync holding the write lock
    try:
        result = asyncio.run(mcp._call_query_metrics(
            fields=["date", "clicks"], date_preset="last_7d"))
    finally:
        writer.close()
    assert "sync" in result["error"]


def test_connection_released_between_calls(tmp_path):
    cfg = make_config(tmp_path)
    seed(cfg)
    mcp = build_mcp(cfg)
    asyncio.run(mcp._call_query_metrics(fields=["date", "clicks"], date_preset="last_7d"))
    # write connection must be obtainable now — would raise if MCP held its RO handle
    store = Storage(cfg.db_path)
    store.close()
