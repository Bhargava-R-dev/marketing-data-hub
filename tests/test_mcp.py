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
        UnifiedRow(date=d, source="gsc", account_id="x", clicks=12, impressions=300)])
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
    assert result["rows"][0]["clicks"] == 12
