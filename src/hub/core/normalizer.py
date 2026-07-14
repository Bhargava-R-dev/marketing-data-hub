from __future__ import annotations

from typing import Iterable

from hub.core.models import CORE_FIELDS, UnifiedRow


def normalize(source: str, raw_rows: Iterable[dict],
              report: str = "core") -> list[UnifiedRow]:
    """Split connector output into core columns + extras and validate."""
    out: list[UnifiedRow] = []
    for raw in raw_rows:
        raw_source = raw.get("source")
        if raw_source is not None and raw_source != source:
            raise ValueError(
                f"row source {raw_source!r} does not match connector {source!r}")
        # the connector id/report always win; both are excluded from core and extras
        core = {k: v for k, v in raw.items()
                if k in CORE_FIELDS and k not in ("source", "report")}
        extras = {k: v for k, v in raw.items()
                  if k not in CORE_FIELDS and k != "report"}
        out.append(UnifiedRow(source=source, report=report, extras=extras, **core))
    return out
