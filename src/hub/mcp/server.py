from __future__ import annotations

import subprocess
import sys
from datetime import date
from pathlib import Path

from fastmcp import FastMCP

from hub.connectors.catalog import connector_class
from hub.core.config import HubConfig
from hub.core.presets import resolve_dates
from hub.core.status import source_statuses
from hub.core.storage import Storage


def build_mcp(config: HubConfig, config_path: str = "config.yaml") -> FastMCP:
    mcp = FastMCP("marketing-data-hub")

    if not Path(config.db_path).exists():
        Storage(config.db_path).close()  # create schema so read-only open works
    storage = Storage(config.db_path, read_only=True)

    def _query_metrics(fields: list[str], date_preset: str | None = None,
                       date_from: str | None = None, date_to: str | None = None,
                       source: str | None = None, campaign: str | None = None) -> dict:
        df, dt = resolve_dates(
            date_preset,
            date.fromisoformat(date_from) if date_from else None,
            date.fromisoformat(date_to) if date_to else None)
        filters = {"campaign": campaign} if campaign else None
        rows = storage.query(fields, df, dt,
                             sources=[source] if source else None, filters=filters)
        return {"date_from": df.isoformat(), "date_to": dt.isoformat(),
                "rows": [{k: (v.isoformat() if isinstance(v, date) else v)
                          for k, v in r.items()} for r in rows]}

    # exposed for tests
    async def _call_query_metrics(**kwargs) -> dict:
        return _query_metrics(**kwargs)
    mcp._call_query_metrics = _call_query_metrics  # type: ignore[attr-defined]

    @mcp.tool()
    def list_sources() -> list[dict]:
        """List marketing data sources with sync status, row counts, freshness."""
        return source_statuses(config, storage)

    @mcp.tool()
    def list_fields(source: str) -> list[dict]:
        """List queryable fields for one source (ga4, gsc, youtube, google_ads, meta_ads)."""
        return connector_class(source).fields.to_dict()

    @mcp.tool()
    def query_metrics(fields: list[str], date_preset: str | None = None,
                      date_from: str | None = None, date_to: str | None = None,
                      source: str | None = None, campaign: str | None = None) -> dict:
        """Query unified marketing metrics, e.g. fields=["date","source","clicks","spend"]
        with date_preset one of last_7d/last_30d/last_90d/this_month/last_month/ytd."""
        try:
            return _query_metrics(fields, date_preset, date_from, date_to, source, campaign)
        except Exception as exc:  # noqa: BLE001 - return readable errors to the model
            return {"error": str(exc)}

    @mcp.tool()
    def trigger_sync(source: str) -> str:
        """Run a sync now for one source (or 'all'). Uses the CLI so this
        process stays read-only."""
        proc = subprocess.run(
            [sys.executable, "-m", "hub.cli", "sync", source, "--config", config_path],
            capture_output=True, text=True, timeout=900)
        return (proc.stdout + proc.stderr).strip()

    return mcp
