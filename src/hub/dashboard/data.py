from __future__ import annotations

from datetime import date

from hub.core.config import HubConfig
from hub.core.freshness import interpret_freshness
from hub.core.storage import Storage


def build_dashboard(config: HubConfig) -> dict:
    """Assemble the 'what's in my hub' summary: one group per source, each
    with its last sync status and a per-brand row (login, date range, rows).

    Read-only, safe to call repeatedly (e.g. from a polling frontend) —
    opens a short-lived read-only connection so it never blocks a sync."""
    try:
        storage = Storage(config.db_path, read_only=True)
    except Exception as exc:  # noqa: BLE001 - db missing or locked by a sync
        return {"groups": [], "busy": True, "error": str(exc)}

    try:
        accounts = storage.accounts()
        last_runs = storage.last_runs()
    finally:
        storage.close()

    from hub.connectors.google_auth import get_identity_labels

    identity_labels = get_identity_labels(config.secrets_dir)

    labels_by_source: dict[str, dict] = {}
    for source, settings in config.connectors.items():
        labels_by_source[source] = {
            "identities": settings.options.get("identities", {}),
        }

    by_source: dict[str, list[dict]] = {}
    for a in accounts:
        source = a["source"]
        identity = labels_by_source.get(source, {}).get("identities", {}).get(
            a["account_id"], "default")
        latest: date | None = a["latest_date"]
        by_source.setdefault(source, []).append({
            "account_name": a["account_name"],
            "identity": identity_labels.get(identity, identity),
            "first_date": a["first_date"].isoformat() if a["first_date"] else None,
            "latest_date": latest.isoformat() if latest else None,
            "rows": a["rows"],
            # per-account, not just per-source: one brand quietly falling
            # behind (an auth outage, a broken property) must not hide
            # behind a source-wide date range that still looks healthy
            "freshness": interpret_freshness(source, latest),
        })

    groups = []
    for source in sorted(set(by_source) | set(last_runs)):
        run = last_runs.get(source)
        groups.append({
            "source": source,
            "last_sync": None if not run else {
                "status": run["status"],
                "started_at": run["started_at"].isoformat() if run["started_at"] else None,
                "finished_at": run["finished_at"].isoformat() if run["finished_at"] else None,
                "error": run["error_message"],
            },
            "accounts": sorted(by_source.get(source, []),
                              key=lambda r: r["account_name"]),
        })
    return {"groups": groups, "busy": False}
