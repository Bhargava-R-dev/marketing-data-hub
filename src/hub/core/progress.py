"""Live per-account sync status, written to a JSON file after every account so
the wizard and dashboard can show it without touching DuckDB (which is
write-locked while a sync runs)."""
from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from hub.connectors.base import resolve_targets
from hub.core.config import HubConfig

# plural / singular option keys per source (mirrors hub.core.accounts.SOURCE_KEYS)
_TARGET_KEYS = {
    "ga4": ("property_ids", "property_id"),
    "gsc": ("site_urls", "site_url"),
    "google_ads": ("customer_ids", "customer_id"),
    "meta_ads": ("ad_account_ids", "ad_account_id"),
}


def progress_path(config: HubConfig) -> Path:
    return Path(config.home) / "logs" / "sync_progress.json"


def configured_accounts(config: HubConfig, sources: list[str] | None = None) -> list[dict]:
    out: list[dict] = []
    for source, settings in config.connectors.items():
        if sources and source not in sources:
            continue
        keys = _TARGET_KEYS.get(source)
        opts = settings.options
        if keys:
            try:
                targets = resolve_targets(opts, *keys)
            except Exception:  # noqa: BLE001 - nothing configured yet
                targets = []
        else:
            targets = [str(opts.get("channel_id", "mine"))]
        labels = opts.get("labels", {})
        identities = opts.get("identities", {})
        for t in targets:
            out.append({"source": source, "account_id": t,
                        "label": labels.get(t, t),
                        "identity": identities.get(t, "default")})
    return out


class SyncProgress:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self._state: dict = {"started_at": None, "finished_at": None, "accounts": []}

    def begin(self, accounts: list[dict]) -> None:
        self._state = {
            "run_id": uuid4().hex,
            "started_at": datetime.now().isoformat(timespec="seconds"),
            "finished_at": None,
            "accounts": [{**a, "status": "pending", "rows": 0,
                          "reports_done": 0, "error": None} for a in accounts],
        }
        self._write()

    def account_update(self, source: str, account_id: str, rows: int,
                       reports_total: int) -> None:
        a = self._find(source, account_id)
        if a is None:
            return
        a["rows"] += rows
        a["reports_done"] += 1
        a["status"] = "done" if a["reports_done"] >= reports_total else "running"
        self._write()

    def account_error(self, source: str, account_id: str, error: str) -> None:
        """One account failed on its own (e.g. a permission error specific to
        that property) - record it against just that account, leaving every
        other account's status untouched so a single bad site can't make
        unrelated, never-attempted accounts look like they failed too."""
        a = self._find(source, account_id)
        if a is None:
            return
        a["status"] = "error"
        a["error"] = error
        self._write()

    def source_error(self, source: str, error: str) -> None:
        for a in self._state["accounts"]:
            if a["source"] == source and a["status"] != "done":
                a["status"] = "error"
                a["error"] = error
        self._write()

    def finish(self) -> None:
        self._state["finished_at"] = datetime.now().isoformat(timespec="seconds")
        self._write()

    @staticmethod
    def read(path: str | Path) -> dict | None:
        path = Path(path)
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None

    def _find(self, source: str, account_id: str) -> dict | None:
        for a in self._state["accounts"]:
            if a["source"] == source and a["account_id"] == account_id:
                return a
        return None

    def _write(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self._state, indent=1), encoding="utf-8")
        os.replace(tmp, self.path)  # atomic on Windows and POSIX
