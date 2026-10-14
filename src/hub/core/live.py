"""Live mode: answer queries from the APIs, not from whatever a past sync left.

Queries still run against the local DuckDB (so every aggregation, comparison
and breakdown stays exactly as before), but the database is a short-lived
cache. Before a query runs, ensure_fresh() finds the days in the requested
range that were never fetched or have outlived their freshness window,
fetches just those from the API, and records when. Old entries are evicted, so
the file stays small. If a refresh fails, whatever is cached is still served
and the failure is reported alongside it, never silently.
"""
from __future__ import annotations

import os
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

import duckdb

from hub.connectors.base import AuthError
from hub.connectors.catalog import build_connector
from hub.core.config import HubConfig
from hub.core.normalizer import normalize
from hub.core.storage import Storage
from hub.core.sync import backfill_chunks

# Newer days are restated by the APIs for a while (late events, conversion
# attribution), so they expire sooner. Older days are effectively final.
_TTL_TIERS: list[tuple[int, timedelta]] = [
    (1, timedelta(minutes=15)),
    (7, timedelta(hours=1)),
    (35, timedelta(hours=12)),
]
_TTL_OLD = timedelta(days=7)
# rows older than this that predate live mode (no fetch record) are trusted as
# history: GSC only serves ~16 months, so refetching could erase data the API
# can no longer give back
_LEGACY_TRUST_AGE_DAYS = 35
_LOCK_RETRIES = 20
_LOCK_WAIT_S = 0.5


def ttl_for(age_days: int) -> timedelta:
    for max_age, ttl in _TTL_TIERS:
        if age_days <= max_age:
            return ttl
    return _TTL_OLD


def stale_ranges(storage: Storage, source: str, report: str, date_from: date,
                 date_to: date, now: datetime | None = None,
                 today: date | None = None) -> list[tuple[date, date]]:
    """Contiguous date ranges (<=90 days each) that need a fetch."""
    now = now or datetime.now()
    today = today or now.date()
    date_to = min(date_to, today)  # nothing to fetch from the future
    if date_from > date_to:
        return []
    fetched = storage.cache_fetched(source, report, date_from, date_to)
    legacy = storage.days_with_rows(source, report, date_from, date_to)
    stale: list[date] = []
    day = date_from
    while day <= date_to:
        age = (today - day).days
        when = fetched.get(day)
        if when is not None:
            fresh = now - when < ttl_for(age)
        else:
            fresh = day in legacy and age > _LEGACY_TRUST_AGE_DAYS
        if not fresh:
            stale.append(day)
        day += timedelta(days=1)
    ranges: list[tuple[date, date]] = []
    for d in stale:
        if ranges and ranges[-1][1] == d - timedelta(days=1):
            ranges[-1] = (ranges[-1][0], d)
        else:
            ranges.append((d, d))
    out: list[tuple[date, date]] = []
    for a, b in ranges:
        out.extend(backfill_chunks(a, b))
    return out


@dataclass
class LiveResult:
    fetched_days: int = 0
    errors: dict[str, str] = field(default_factory=dict)  # source -> message
    skipped: list[str] = field(default_factory=list)       # out of time budget

    @property
    def ok(self) -> bool:
        return not self.errors and not self.skipped


@contextmanager
def _unattended():
    """A live query has nobody to finish a browser sign-in: fail with a clear
    message instead of opening a tab from inside the MCP server."""
    previous = os.environ.get("HUB_UNATTENDED")
    os.environ["HUB_UNATTENDED"] = "1"
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop("HUB_UNATTENDED", None)
        else:
            os.environ["HUB_UNATTENDED"] = previous


def _open_writable(db_path: str) -> Storage:
    last: Exception | None = None
    for attempt in range(_LOCK_RETRIES):
        try:
            return Storage(db_path)
        except (duckdb.IOException, duckdb.ConnectionException) as exc:
            last = exc
            if attempt < _LOCK_RETRIES - 1:
                time.sleep(_LOCK_WAIT_S)
    raise RuntimeError(f"database is busy ({last})")


def _fetch(storage: Storage, connector, source: str, report: str,
           a: date, b: date) -> int:
    run_id = storage.start_sync(source, a, b)
    try:
        raw = list(connector.extract_report(report, a, b))
        rows = normalize(source, raw, report=report)
        n = storage.replace_rows(source, a, b, rows, report=report)
        storage.mark_fetched(source, report, a, b)
        storage.finish_sync(run_id, n, "success")
        return n
    except Exception as exc:  # noqa: BLE001
        hint = getattr(exc, "hint", "")
        storage.finish_sync(run_id, 0, "error", error=f"{exc} {hint}".strip())
        raise


def ensure_fresh(config: HubConfig, sources: list[str] | None, report: str,
                 date_from: date, date_to: date,
                 budget_s: float = 45.0,
                 storage: Storage | None = None) -> LiveResult:
    """Fetch whatever part of [date_from, date_to] is missing or stale for the
    given sources (default: every configured connector that has this report).
    Never raises for an API problem: failures land in the result so the caller
    can still answer from cached data and say what went wrong. Pass `storage`
    when the caller already holds the write connection (the REST API, exports);
    otherwise a short-lived one is opened and closed here."""
    result = LiveResult()
    if config.mode != "live":
        return result
    wanted = [s for s in (sources or list(config.connectors))
              if s in config.connectors]
    if not wanted:
        return result
    started = time.monotonic()
    owned = storage is None
    if owned:
        try:
            storage = _open_writable(config.db_path)
        except RuntimeError as exc:
            result.errors["database"] = str(exc)
            return result
    try:
        with _unattended():
            for source in wanted:
                try:
                    connector = build_connector(source, config)
                    if report not in connector.get_reports():
                        continue
                    if report not in connector.enabled_reports():
                        continue
                    ranges = stale_ranges(storage, source, report,
                                          date_from, date_to)
                    if not ranges:
                        continue
                    connector.authenticate()
                    for a, b in ranges:
                        if time.monotonic() - started > budget_s:
                            result.skipped.append(source)
                            break
                        _fetch(storage, connector, source, report, a, b)
                        result.fetched_days += (b - a).days + 1
                except AuthError as exc:
                    result.errors[source] = f"{exc} {exc.hint}".strip()
                except Exception as exc:  # noqa: BLE001 - one source must not sink the rest
                    result.errors[source] = str(exc)
        try:
            storage.prune_cache(config.cache_retention_days)
        except Exception:  # noqa: BLE001 - housekeeping never fails a query
            pass
    finally:
        if owned:
            storage.close()
    return result


def describe(result: LiveResult) -> dict:
    """Fields to merge into a tool response so the model can tell the user
    what was fetched and what could not be refreshed."""
    out: dict = {"live": {"fetched_days": result.fetched_days}}
    if result.errors:
        out["live"]["refresh_errors"] = result.errors
        out["warning"] = (
            "COULD NOT REFRESH FROM THE API: "
            + "; ".join(f"{s}: {m}" for s, m in result.errors.items())
            + ". Numbers below come from previously cached data and may be "
              "out of date - say so when reporting them.")
    if result.skipped:
        out["live"]["not_fetched_in_time"] = result.skipped
        out.setdefault("warning", "")
        out["warning"] = (out["warning"] + " " if out["warning"] else "") + (
            "The requested range was too large to fetch in one request for: "
            + ", ".join(result.skipped)
            + ". Re-run the same query to continue loading it, or ask for a "
              "shorter range.")
    return out
