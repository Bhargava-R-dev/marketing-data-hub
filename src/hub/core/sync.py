from __future__ import annotations

import time
from datetime import date, timedelta

from hub.connectors.base import AuthError, BaseConnector
from hub.core.normalizer import normalize
from hub.core.reconcile import find_over_counts
from hub.core.storage import Storage


def run_sync(storage: Storage, connector: BaseConnector,
             date_from: date | None = None, date_to: date | None = None,
             window_days: int = 30, retries: int = 3) -> int:
    """Sync one connector over a date range (default: rolling window ending today).

    Re-fetches and transactionally replaces the whole window because ad platforms
    restate conversions retroactively. Returns rows written."""
    date_to = date_to or date.today()
    date_from = date_from or date_to - timedelta(days=window_days)
    run_id = storage.start_sync(connector.id, date_from, date_to)
    last_exc: Exception | None = None
    for attempt in range(max(1, retries)):
        try:
            connector.authenticate()
            total = 0
            # each report replaces its own (source, report) slice, so a retry
            # after a mid-loop failure just re-replaces — idempotent
            for report in connector.enabled_reports():
                raw = list(connector.extract_report(report, date_from, date_to))
                rows = normalize(connector.id, raw, report=report)
                total += storage.replace_rows(connector.id, date_from, date_to,
                                              rows, report=report)
            storage.finish_sync(run_id, total, "success")
            # automatic reconciliation: catch a breakdown report silently
            # OVER-counting against core for THIS run's own range - exactly
            # the class of bug (GA4's '(other)' rows) that inflated one
            # brand's numbers by 38% for weeks before anyone noticed. Never
            # fails the sync itself - a bad number here is a data-quality
            # signal, not a reason to discard data that did load.
            try:
                for finding in find_over_counts(storage, date_from, date_to,
                                                source=connector.id):
                    print(f"[WARN] reconciliation: {finding['account_name']} "
                         f"({finding['source']}/{finding['report']}) is "
                         f"{finding['overcount_pct']}% OVER core's total "
                         f"({finding['report_total']} vs {finding['core_total']} "
                         f"{finding['metric']}) - run 'hub validate' for detail")
            except Exception:  # noqa: BLE001 - the check itself must never break a sync
                pass
            return total
        except AuthError as exc:
            # auth problems don't heal on retry, and retrying can re-open
            # the interactive consent flow — fail fast with the hint attached
            storage.finish_sync(run_id, 0, "error",
                                error=f"{exc} {exc.hint}".strip())
            raise
        except Exception as exc:  # noqa: BLE001 - anything from an API is retryable
            last_exc = exc
            if attempt < retries - 1:
                time.sleep(2 ** (attempt + 1))
    storage.finish_sync(run_id, 0, "error", error=str(last_exc))
    raise last_exc  # type: ignore[misc]


def backfill_chunks(date_from: date, date_to: date,
                    chunk_days: int = 90) -> list[tuple[date, date]]:
    chunks = []
    start = date_from
    while start <= date_to:
        end = min(start + timedelta(days=chunk_days - 1), date_to)
        chunks.append((start, end))
        start = end + timedelta(days=1)
    return chunks


def backfill(storage: Storage, connector: BaseConnector,
             date_from: date, date_to: date | None = None) -> int:
    """Sync a date range in chunks, oldest first.

    Aborts on the first chunk that fails all retries; completed chunks stay
    committed. Re-run with an adjusted date_from to resume. Uses more retries
    than a daily sync (backoff up to ~2 min total) so a brief network outage
    doesn't kill a multi-hour history load.
    """
    date_to = date_to or date.today()
    total = 0
    for start, end in backfill_chunks(date_from, date_to):
        total += run_sync(storage, connector, date_from=start, date_to=end,
                          retries=6)
    return total
