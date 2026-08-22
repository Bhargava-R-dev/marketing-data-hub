import asyncio
from datetime import date

from hub.core.config import ConnectorSettings, HubConfig
from hub.core.models import UnifiedRow
from hub.core.storage import Storage
from hub.mcp.server import build_mcp


def make_config(tmp_path):
    # build_mcp() reloads config.yaml fresh on every tool call (see server.py's
    # _cfg()) - a config object that only ever lived in memory would make every
    # test here silently fall through to this repo's OWN real config.yaml the
    # moment that fix landed, since the default config_path="config.yaml" and
    # pytest's cwd is the repo root. Write a real file so tests stay isolated.
    db_path = (tmp_path / "t.duckdb").as_posix()
    (tmp_path / "config.yaml").write_text(
        f"db_path: {db_path}\nconnectors:\n  gsc:\n    options: {{site_url: x}}\n",
        encoding="utf-8")
    return HubConfig(
        db_path=db_path,
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
    mcp = build_mcp(cfg, config_path=str(tmp_path / "config.yaml"))
    # installed fastmcp (3.x) exposes async list_tools() -> Sequence[Tool],
    # not the 2.x get_tools() -> dict[str, Tool] the plan assumed.
    tools = asyncio.run(mcp.list_tools())
    names = {t.name for t in tools}
    assert {"list_sources", "list_fields", "query_metrics", "trigger_sync",
            "sync_status"} <= names


def test_query_metrics_tool_logic(tmp_path):
    cfg = make_config(tmp_path)
    seed(cfg)
    mcp = build_mcp(cfg, config_path=str(tmp_path / "config.yaml"))
    result = asyncio.run(mcp._call_query_metrics(  # exposed for tests
        fields=["date", "clicks"], date_preset="last_7d"))
    assert result["rows"][0]["clicks"] == 19  # both seeded brands aggregated


def test_query_metrics_brand_filter_fuzzy(tmp_path):
    cfg = make_config(tmp_path)
    seed(cfg)
    mcp = build_mcp(cfg, config_path=str(tmp_path / "config.yaml"))
    result = asyncio.run(mcp._call_query_metrics(
        fields=["date", "clicks"], date_preset="last_7d", brand="vetrotec"))
    assert result["matched_brands"] == ["Vetrotech"]
    assert len(result["rows"]) == 1
    assert result["rows"][0]["clicks"] == 12
    assert result["rows"][0]["account_name"] == "Vetrotech"


def test_query_metrics_unknown_brand_lists_available(tmp_path):
    cfg = make_config(tmp_path)
    seed(cfg)
    mcp = build_mcp(cfg, config_path=str(tmp_path / "config.yaml"))
    result = asyncio.run(mcp._call_query_metrics(
        fields=["date", "clicks"], date_preset="last_7d", brand="nike"))
    assert "error" in result
    assert result["available_brands"] == ["Sharekhan", "Vetrotech"]


def test_list_brands_tool(tmp_path):
    cfg = make_config(tmp_path)
    seed(cfg)
    mcp = build_mcp(cfg, config_path=str(tmp_path / "config.yaml"))
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
    mcp = build_mcp(cfg, config_path=str(tmp_path / "config.yaml"))
    result = asyncio.run(mcp._call_trigger_sync(source="all"))
    assert result["status"] == "already_running"


def test_sync_status_reports_last_runs(tmp_path):
    cfg = make_config(tmp_path)
    seed(cfg)
    store = Storage(cfg.db_path)
    run_id = store.start_sync("gsc", date.today(), date.today())
    store.finish_sync(run_id, 5, "success")
    store.close()
    mcp = build_mcp(cfg, config_path=str(tmp_path / "config.yaml"))
    result = asyncio.run(mcp._call_sync_status())
    assert result["runs"]["gsc"]["status"] == "success"
    assert result["runs"]["gsc"]["rows_written"] == 5
    assert result["sync_in_progress"] is False


def test_query_metrics_readable_error_while_db_locked(tmp_path):
    cfg = make_config(tmp_path)
    seed(cfg)
    mcp = build_mcp(cfg, config_path=str(tmp_path / "config.yaml"))
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
    mcp = build_mcp(cfg, config_path=str(tmp_path / "config.yaml"))
    asyncio.run(mcp._call_query_metrics(fields=["date", "clicks"], date_preset="last_7d"))
    # write connection must be obtainable now — would raise if MCP held its RO handle
    store = Storage(cfg.db_path)
    store.close()


def seed_reports(cfg):
    store = Storage(cfg.db_path)
    d = date.today()
    store.replace_rows("gsc", d, d, [
        UnifiedRow(date=d, source="gsc", account_id="x", account_name="Vetrotech",
                   clicks=5, extras={"query": "vetrotech fire glass"}),
        UnifiedRow(date=d, source="gsc", account_id="x", account_name="Vetrotech",
                   clicks=3, extras={"query": "fire rated glass"})], report="queries")
    store.close()


def test_new_tools_registered(tmp_path):
    cfg = make_config(tmp_path)
    seed(cfg)
    mcp = build_mcp(cfg, config_path=str(tmp_path / "config.yaml"))
    names = {t.name for t in asyncio.run(mcp.list_tools())}
    assert {"list_reports", "query_ga4_live", "query_gsc_live"} <= names


def test_query_metrics_report_param(tmp_path):
    cfg = make_config(tmp_path)
    seed(cfg)
    seed_reports(cfg)
    mcp = build_mcp(cfg, config_path=str(tmp_path / "config.yaml"))
    result = asyncio.run(mcp._call_query_metrics(
        fields=["date", "query", "clicks"], date_preset="last_7d",
        source="gsc", report="queries"))
    queries = {r["query"]: r["clicks"] for r in result["rows"]}
    assert queries == {"vetrotech fire glass": 5, "fire rated glass": 3}
    # core stays clean: breakdown rows must not leak into default queries
    core = asyncio.run(mcp._call_query_metrics(
        fields=["date", "clicks"], date_preset="last_7d"))
    assert core["rows"][0]["clicks"] == 19


def test_query_metrics_compare_prev_period(tmp_path):
    cfg = make_config(tmp_path)
    store = Storage(cfg.db_path)
    store.replace_rows("gsc", date(2026, 5, 1), date(2026, 5, 31), [
        UnifiedRow(date=date(2026, 5, 10), source="gsc", account_id="x",
                   account_name="Vetrotech", clicks=80)])
    store.replace_rows("gsc", date(2026, 6, 1), date(2026, 6, 30), [
        UnifiedRow(date=date(2026, 6, 10), source="gsc", account_id="x",
                   account_name="Vetrotech", clicks=100)])
    store.close()
    mcp = build_mcp(cfg, config_path=str(tmp_path / "config.yaml"))
    result = asyncio.run(mcp._call_query_metrics(
        fields=["date", "clicks"], date_from="2026-06-01", date_to="2026-06-30",
        compare="prev_month"))
    assert result["compare_date_from"] == "2026-05-01"
    assert result["compare_date_to"] == "2026-05-30"
    assert "note" in result  # date was dropped
    r = result["rows"][0]
    assert r["clicks"] == 100 and r["clicks_prev"] == 80
    assert r["clicks_change_pct"] == 25.0


def test_query_metrics_compare_handles_missing_previous(tmp_path):
    cfg = make_config(tmp_path)
    seed(cfg)  # data only in current window
    mcp = build_mcp(cfg, config_path=str(tmp_path / "config.yaml"))
    result = asyncio.run(mcp._call_query_metrics(
        fields=["clicks"], date_preset="last_7d", compare="prev_year"))
    r = result["rows"][0]
    assert r["clicks"] == 19
    assert r["clicks_prev"] is None
    assert r["clicks_change_pct"] is None


def test_query_metrics_compare_unknown_mode(tmp_path):
    cfg = make_config(tmp_path)
    seed(cfg)
    mcp = build_mcp(cfg, config_path=str(tmp_path / "config.yaml"))
    result = asyncio.run(mcp._call_query_metrics(
        fields=["clicks"], date_preset="last_7d", compare="bogus"))
    assert "error" in result and "available_modes" in result


def test_query_metrics_extras_filter(tmp_path):
    cfg = make_config(tmp_path)
    seed(cfg)
    seed_reports(cfg)
    mcp = build_mcp(cfg, config_path=str(tmp_path / "config.yaml"))
    result = asyncio.run(mcp._call_query_metrics(
        fields=["query", "clicks"], date_preset="last_7d", source="gsc",
        report="queries", filters={"query": "fire rated glass"}))
    assert result["rows"] == [{"query": "fire rated glass", "clicks": 3}]


def test_config_edits_after_build_mcp_take_effect_immediately(tmp_path):
    """The actual regression: build_mcp() used to capture one HubConfig object
    for the server's whole lifetime. Fixing an account's identity mapping (or
    adding a brand) via 'hub setup'/'hub accounts' while the MCP server keeps
    running - exactly what happened in the field - was invisible until Claude
    Desktop restarted. _cfg() must reload config.yaml fresh on every call."""
    cfg = make_config(tmp_path)
    seed(cfg)
    cfg_path = tmp_path / "config.yaml"
    mcp = build_mcp(cfg, config_path=str(cfg_path))

    # nothing mapped yet -> falls back to the default identity
    assert mcp._identity_for(mcp._cfg(), "gsc", "https://vetrotech.com/") is None

    # simulate a live fix: someone edits config.yaml WHILE this server is
    # still the one running (no rebuild, no restart)
    cfg_path.write_text(
        f"db_path: {cfg.db_path}\n"
        "connectors:\n  gsc:\n    options: {site_url: x, "
        "identities: {'https://vetrotech.com/': personal}}\n",
        encoding="utf-8")

    assert mcp._identity_for(mcp._cfg(), "gsc", "https://vetrotech.com/") == "personal"


def test_resolve_target_sees_newly_added_brand_without_rebuild(tmp_path):
    cfg = make_config(tmp_path)
    seed(cfg)
    cfg_path = tmp_path / "config.yaml"
    mcp = build_mcp(cfg, config_path=str(cfg_path))

    result = mcp._resolve_target(mcp._cfg(), "gsc", "site_urls", None, "newsite")
    assert "error" in result  # not configured yet

    cfg_path.write_text(
        f"db_path: {cfg.db_path}\n"
        "connectors:\n  gsc:\n    options: {site_urls: ['https://newsite.com/'], "
        "labels: {'https://newsite.com/': NewSite}}\n",
        encoding="utf-8")

    result = mcp._resolve_target(mcp._cfg(), "gsc", "site_urls", None, "newsite")
    assert result == "https://newsite.com/"


# ---- completeness signal: a partial sum must never look like a full one --

def test_query_metrics_flags_incomplete_range(tmp_path):
    """seed() only writes today's date - querying a wider range must flag
    the missing days instead of silently returning a partial sum."""
    cfg = make_config(tmp_path)
    seed(cfg)
    mcp = build_mcp(cfg, config_path=str(tmp_path / "config.yaml"))
    result = asyncio.run(mcp._call_query_metrics(
        fields=["clicks"], date_from="2020-01-01", date_to="2020-01-10"))
    assert result["complete"] is False
    assert result["days_requested"] == 10
    assert len(result["incomplete_accounts"]) == 2  # Vetrotech + Sharekhan
    assert "warning" in result and "INCOMPLETE" in result["warning"]


def test_query_metrics_complete_when_range_fully_covered(tmp_path):
    cfg = make_config(tmp_path)
    seed(cfg)
    mcp = build_mcp(cfg, config_path=str(tmp_path / "config.yaml"))
    from datetime import date as _date
    today = _date.today().isoformat()
    result = asyncio.run(mcp._call_query_metrics(
        fields=["clicks"], date_from=today, date_to=today))
    assert result["complete"] is True
    assert "incomplete_accounts" not in result
    assert "warning" not in result


def test_query_metrics_completeness_scoped_to_matched_brand_only(tmp_path):
    """Filtering to one brand must only report that brand's completeness,
    not every account's."""
    cfg = make_config(tmp_path)
    seed(cfg)
    mcp = build_mcp(cfg, config_path=str(tmp_path / "config.yaml"))
    result = asyncio.run(mcp._call_query_metrics(
        fields=["clicks"], date_from="2020-01-01", date_to="2020-01-05",
        brand="vetrotec"))
    assert result["complete"] is False
    assert [a["account_name"] for a in result["incomplete_accounts"]] == ["Vetrotech"]


def test_date_gaps_reports_missing_dates(tmp_path):
    from hub.core.storage import Storage

    store = Storage(str(tmp_path / "t.duckdb"))
    d = date.today()
    store.replace_rows("gsc", d, d, [
        UnifiedRow(date=d, source="gsc", account_id="x", account_name="A", clicks=1)])
    gaps = store.date_gaps("gsc", date(2020, 1, 1), date(2020, 1, 5), account_id="x")
    assert gaps == {"days_requested": 5, "days_with_data": 0,
                    "missing_dates": ["2020-01-01", "2020-01-02", "2020-01-03",
                                      "2020-01-04", "2020-01-05"]}
    store.close()


def test_date_gaps_no_gaps_when_fully_covered(tmp_path):
    from hub.core.storage import Storage

    store = Storage(str(tmp_path / "t.duckdb"))
    d = date(2026, 6, 1)
    store.replace_rows("gsc", d, d, [
        UnifiedRow(date=d, source="gsc", account_id="x", account_name="A", clicks=1)])
    gaps = store.date_gaps("gsc", d, d, account_id="x")
    assert gaps == {"days_requested": 1, "days_with_data": 1, "missing_dates": []}
    store.close()
