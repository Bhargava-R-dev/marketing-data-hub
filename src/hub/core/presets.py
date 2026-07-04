from __future__ import annotations

from datetime import date, timedelta

_RELATIVE = {"last_7d": 7, "last_30d": 30, "last_90d": 90}


def resolve_dates(preset: str | None = None, date_from: date | None = None,
                  date_to: date | None = None, today: date | None = None) -> tuple[date, date]:
    today = today or date.today()
    if date_from is not None and date_to is not None:
        return date_from, date_to
    if date_from is not None:
        return date_from, today          # open-ended range runs to today
    if date_to is not None:
        raise ValueError("date_from is required when date_to is given")
    if preset is None:
        return today - timedelta(days=30), today
    if preset in _RELATIVE:
        return today - timedelta(days=_RELATIVE[preset]), today
    if preset == "this_month":
        return today.replace(day=1), today
    if preset == "last_month":
        first_this = today.replace(day=1)
        last_prev = first_this - timedelta(days=1)
        return last_prev.replace(day=1), last_prev
    if preset == "ytd":
        return today.replace(month=1, day=1), today
    raise ValueError(f"unknown date_preset: {preset!r}")
