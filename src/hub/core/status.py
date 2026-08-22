from __future__ import annotations

from hub.connectors.catalog import ALL_CONNECTORS
from hub.core.config import HubConfig
from hub.core.freshness import interpret_freshness
from hub.core.storage import Storage


def source_statuses(config: HubConfig, storage: Storage) -> list[dict]:
    counts = storage.row_counts()
    runs = storage.last_runs()
    out = []
    for source in ALL_CONNECTORS:
        configured = source in config.connectors
        latest_date = counts.get(source, {}).get("latest_date")
        entry = {
            "source": source,
            "status": "active" if configured else "inactive",
            "rows": counts.get(source, {}).get("rows", 0),
            "latest_date": latest_date,
            "last_sync": runs.get(source),
            "freshness": interpret_freshness(source, latest_date) if configured else None,
        }
        out.append(entry)
    return out
