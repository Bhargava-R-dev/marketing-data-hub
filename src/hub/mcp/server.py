from __future__ import annotations

import subprocess
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path

import duckdb
from fastmcp import FastMCP

from hub.connectors.catalog import connector_class
from hub.core.config import HubConfig
from hub.core.presets import resolve_dates
from hub.core.status import source_statuses
from hub.core.storage import Storage

_LOCK_RETRIES = 3
_LOCK_WAIT_S = 0.4
# a 'running' sync_runs row older than this is a crashed sync, not a live one
_STALE_RUNNING = timedelta(minutes=15)


def build_mcp(config: HubConfig, config_path: str = "config.yaml") -> FastMCP:
    mcp = FastMCP("marketing-data-hub")

    if not Path(config.db_path).exists():
        Storage(config.db_path).close()  # create schema so read-only open works

    def _open_read_only() -> Storage:
        """A running sync holds the DuckDB write lock, which blocks new read-only
        connections. Retry briefly, then fail with a message the model can act on."""
        last_exc: Exception | None = None
        for attempt in range(_LOCK_RETRIES):
            try:
                return Storage(config.db_path, read_only=True)
            except (duckdb.IOException, duckdb.ConnectionException) as exc:
                last_exc = exc
                if attempt < _LOCK_RETRIES - 1:
                    time.sleep(_LOCK_WAIT_S)
        raise RuntimeError(
            "database is busy - most likely a sync is holding the write lock; "
            f"wait for it to finish (check sync_status) and retry ({last_exc})")

    def _with_storage(fn):
        """Open a short-lived read-only connection so the DB lock is free
        between tool calls (lets trigger_sync's subprocess write)."""
        storage = _open_read_only()
        try:
            return fn(storage)
        finally:
            storage.close()

    def _query_metrics(storage, fields: list[str], date_preset: str | None = None,
                       date_from: str | None = None, date_to: str | None = None,
                       source: str | None = None, campaign: str | None = None,
                       brand: str | None = None) -> dict:
        df, dt = resolve_dates(
            date_preset,
            date.fromisoformat(date_from) if date_from else None,
            date.fromisoformat(date_to) if date_to else None)
        filters = {"campaign": campaign} if campaign else None

        matched_names: list[str] = []
        if brand:
            known = storage.accounts()
            matched_names = sorted({a["account_name"] for a in known
                                    if brand.lower() in a["account_name"].lower()})
            if not matched_names:
                return {"error": f"no brand matching {brand!r}",
                        "available_brands": sorted({a["account_name"] for a in known})}
            # group by account_name so we can filter the aggregated rows per brand
            if "account_name" not in fields:
                fields = [*fields, "account_name"]

        rows = storage.query(fields, df, dt,
                             sources=[source] if source else None, filters=filters)
        if matched_names:
            rows = [r for r in rows if r.get("account_name") in matched_names]
        result = {"date_from": df.isoformat(), "date_to": dt.isoformat(),
                  "rows": [{k: (v.isoformat() if isinstance(v, date) else v)
                            for k, v in r.items()} for r in rows]}
        if matched_names:
            result["matched_brands"] = matched_names
        return result

    def _query_metrics_safe(**kwargs) -> dict:
        try:
            return _with_storage(lambda s: _query_metrics(s, **kwargs))
        except Exception as exc:  # noqa: BLE001 - return readable errors to the model
            return {"error": str(exc)}

    # exposed for tests
    async def _call_query_metrics(**kwargs) -> dict:
        return _query_metrics_safe(**kwargs)
    mcp._call_query_metrics = _call_query_metrics  # type: ignore[attr-defined]

    @mcp.tool()
    def list_sources() -> list[dict]:
        """List marketing data sources (ga4, gsc, ...) with sync status, row counts,
        freshness. For the brands/websites inside each source, use list_brands."""
        return _with_storage(lambda s: source_statuses(config, s))

    @mcp.tool()
    def list_brands() -> list[dict]:
        """List every brand/account in the data (e.g. Vetrotech, Sharekhan,
        L&T Realty) with its source, row count, and date coverage. Call this
        first when the user asks about a specific brand or website."""
        return _with_storage(lambda s: [
            {**a,
             "first_date": a["first_date"].isoformat() if a["first_date"] else None,
             "latest_date": a["latest_date"].isoformat() if a["latest_date"] else None}
            for a in s.accounts()])

    @mcp.tool()
    def list_fields(source: str) -> list[dict]:
        """List queryable fields for one source (ga4, gsc, youtube, google_ads, meta_ads)."""
        return connector_class(source).fields.to_dict()

    @mcp.tool()
    def query_metrics(fields: list[str], date_preset: str | None = None,
                      date_from: str | None = None, date_to: str | None = None,
                      source: str | None = None, campaign: str | None = None,
                      brand: str | None = None) -> dict:
        """Query unified marketing metrics, e.g. fields=["date","source","clicks","spend"]
        with date_preset one of last_7d/last_30d/last_90d/this_month/last_month/ytd.

        To answer questions about a specific brand/website (e.g. "Vetrotech traffic
        last week"), pass brand="vetrotech" — it matches account_name
        case-insensitively and partially. Do NOT use the campaign filter for brand
        names; campaigns are ad-campaign names within a brand. If the brand doesn't
        match, the response lists available_brands to pick from.

        CAVEAT: Search Console (gsc) data has a 2-3 day reporting lag from Google,
        so the most recent days of any range will be missing for gsc metrics
        (clicks/impressions) — mention this when reporting recent gsc numbers.
        GA4 data (sessions/users/conversions) is current through yesterday/today."""
        return _query_metrics_safe(
            fields=fields, date_preset=date_preset, date_from=date_from,
            date_to=date_to, source=source, campaign=campaign, brand=brand)

    sync_log_path = Path(config_path).resolve().parent / "logs" / "mcp_sync.log"
    # a just-spawned sync takes ~1s to write its 'running' row, so the DB check
    # alone can't stop an immediate double-trigger — track our own child too
    last_spawned: dict = {"proc": None, "source": None}

    def _running_source(storage) -> str | None:
        for src, run in storage.last_runs().items():
            if (run["status"] == "running" and run["started_at"]
                    and datetime.now() - run["started_at"] < _STALE_RUNNING):
                return src
        return None

    def _trigger_sync(source: str) -> dict:
        proc = last_spawned["proc"]
        if proc is not None and proc.poll() is None:
            return {"status": "already_running",
                    "detail": f"a sync of {last_spawned['source']!r} started from "
                              "this session is still running - poll sync_status "
                              "until it finishes"}
        try:
            running = _with_storage(_running_source)
        except RuntimeError as exc:
            # can't even read the DB -> a sync already holds the write lock
            return {"status": "already_running", "detail": str(exc)}
        if running:
            return {"status": "already_running",
                    "detail": f"a sync of {running!r} is still running - "
                              "poll sync_status until it finishes"}
        sync_log_path.parent.mkdir(parents=True, exist_ok=True)
        with sync_log_path.open("a", encoding="utf-8") as log:
            log.write(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] "
                      f"MCP triggered sync {source!r}\n")
            log.flush()
            last_spawned["proc"] = subprocess.Popen(
                [sys.executable, "-m", "hub.cli", "sync", source,
                 "--config", config_path],
                stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                creationflags=(subprocess.CREATE_NO_WINDOW
                               if sys.platform == "win32" else 0))
            last_spawned["source"] = source
        return {"status": "started", "source": source, "log": str(sync_log_path),
                "note": "runs in the background - poll sync_status to see when it "
                        "finishes; queries may briefly report the database as busy "
                        "while the sync holds the write lock"}

    def _sync_status(storage) -> dict:
        runs = {}
        for src, run in storage.last_runs().items():
            runs[src] = {
                "status": run["status"],
                "started_at": run["started_at"].isoformat() if run["started_at"] else None,
                "finished_at": run["finished_at"].isoformat() if run["finished_at"] else None,
                "rows_written": run["rows_written"],
                "error_message": run["error_message"],
            }
        return {"runs": runs,
                "sync_in_progress": _running_source(storage) is not None}

    def _sync_status_safe() -> dict:
        try:
            return _with_storage(_sync_status)
        except Exception as exc:  # noqa: BLE001 - return readable errors to the model
            return {"error": str(exc), "sync_in_progress": True}

    # exposed for tests
    async def _call_trigger_sync(**kwargs) -> dict:
        return _trigger_sync(**kwargs)
    mcp._call_trigger_sync = _call_trigger_sync  # type: ignore[attr-defined]

    async def _call_sync_status() -> dict:
        return _sync_status_safe()
    mcp._call_sync_status = _call_sync_status  # type: ignore[attr-defined]

    @mcp.tool()
    def trigger_sync(source: str) -> dict:
        """Start a sync for one source (or 'all') in the background and return
        immediately. A full sync takes a few minutes - poll sync_status to see
        when it finishes, then query. Refuses to start if a sync is already
        running."""
        return _trigger_sync(source)

    @mcp.tool()
    def sync_status() -> dict:
        """Show each source's most recent sync run (status, timestamps, rows)
        and whether a sync is currently in progress. Call this after
        trigger_sync to know when fresh data is queryable."""
        return _sync_status_safe()

    return mcp
