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
    assert {"list_sources", "list_fields", "query_metrics", "trigger_sync"} <= names


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


def test_connection_released_between_calls(tmp_path):
    cfg = make_config(tmp_path)
    seed(cfg)
    mcp = build_mcp(cfg)
    asyncio.run(mcp._call_query_metrics(fields=["date", "clicks"], date_preset="last_7d"))
    # write connection must be obtainable now — would raise if MCP held its RO handle
    store = Storage(cfg.db_path)
    store.close()
