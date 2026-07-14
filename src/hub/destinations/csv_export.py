from __future__ import annotations

import csv
from pathlib import Path

from hub.core.config import ExportConfig
from hub.core.presets import resolve_dates
from hub.core.storage import Storage


def run_export(storage: Storage, export: ExportConfig,
               exports_dir: str | Path) -> Path:
    exports_dir = Path(exports_dir)
    exports_dir.mkdir(parents=True, exist_ok=True)
    date_from, date_to = resolve_dates(export.date_preset)
    from hub.connectors.catalog import extra_metric_fields

    rows = storage.query(export.fields, date_from, date_to, sources=export.sources,
                         report=export.report,
                         extra_metrics=extra_metric_fields(export.report, export.sources))
    out_path = exports_dir / (export.filename or f"{export.name}.csv")
    with out_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=export.fields)
        writer.writeheader()
        writer.writerows(rows)
    return out_path
