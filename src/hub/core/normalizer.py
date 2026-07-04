from __future__ import annotations

from typing import Iterable

from hub.core.models import CORE_FIELDS, UnifiedRow


def normalize(source: str, raw_rows: Iterable[dict]) -> list[UnifiedRow]:
    """Split connector output into core columns + extras and validate."""
    out: list[UnifiedRow] = []
    for raw in raw_rows:
        core = {k: v for k, v in raw.items() if k in CORE_FIELDS and k != "source"}
        extras = {k: v for k, v in raw.items() if k not in CORE_FIELDS}
        out.append(UnifiedRow(source=source, extras=extras, **core))
    return out
