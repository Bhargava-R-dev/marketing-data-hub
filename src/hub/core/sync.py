from __future__ import annotations

import time
from datetime import date, timedelta

from hub.connectors.base import BaseConnector
from hub.core.normalizer import normalize
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
    for attempt in range(retries):
        try:
            connector.authenticate()
            raw = list(connector.extract(date_from, date_to))
            rows = normalize(connector.id, raw)
            n = storage.replace_rows(connector.id, date_from, date_to, rows)
            storage.finish_sync(run_id, n, "success")
            return n
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
    date_to = date_to or date.today()
    total = 0
    for start, end in backfill_chunks(date_from, date_to):
        total += run_sync(storage, connector, date_from=start, date_to=end)
    return total
