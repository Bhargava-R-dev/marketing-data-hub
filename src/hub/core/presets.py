from __future__ import annotations

from calendar import monthrange
from datetime import date, timedelta

_RELATIVE = {"last_7d": 7, "last_30d": 30, "last_90d": 90}

COMPARE_MODES = ("prev_period", "prev_day", "prev_week", "prev_month", "prev_year")


def _shift_months(d: date, months: int) -> date:
    """Shift by calendar months, clamping the day (Jan 31 -1mo -> Dec 31,
    Mar 31 -1mo -> Feb 28/29)."""
    total = d.year * 12 + (d.month - 1) + months
    year, month = divmod(total, 12)
    month += 1
    return date(year, month, min(d.day, monthrange(year, month)[1]))


def shift_range(date_from: date, date_to: date, mode: str) -> tuple[date, date]:
    """Return the comparison range for a given range and compare mode.

    prev_period: the equal-length range immediately before (generic MoM/WoW
    when the range is a calendar month/week). prev_day/week/month/year:
    same range shifted back one day/7 days/calendar month/calendar year —
    keeps weekday and month-day alignment for like-for-like comparisons."""
    if mode == "prev_period":
        length = (date_to - date_from).days + 1
        return date_from - timedelta(days=length), date_to - timedelta(days=length)
    if mode == "prev_day":
        return date_from - timedelta(days=1), date_to - timedelta(days=1)
    if mode == "prev_week":
        return date_from - timedelta(days=7), date_to - timedelta(days=7)
    if mode == "prev_month":
        return _shift_months(date_from, -1), _shift_months(date_to, -1)
    if mode == "prev_year":
        return _shift_months(date_from, -12), _shift_months(date_to, -12)
    raise ValueError(f"unknown compare mode: {mode!r} (use one of {COMPARE_MODES})")


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
