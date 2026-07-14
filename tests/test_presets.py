from datetime import date

import pytest

from hub.core.presets import resolve_dates

TODAY = date(2026, 7, 4)


def test_last_7d():
    assert resolve_dates("last_7d", today=TODAY) == (date(2026, 6, 27), TODAY)


def test_this_month_and_last_month():
    assert resolve_dates("this_month", today=TODAY) == (date(2026, 7, 1), TODAY)
    assert resolve_dates("last_month", today=TODAY) == (date(2026, 6, 1), date(2026, 6, 30))


def test_ytd():
    assert resolve_dates("ytd", today=TODAY) == (date(2026, 1, 1), TODAY)


def test_explicit_range_wins():
    assert resolve_dates(None, date_from=date(2026, 1, 5), date_to=date(2026, 1, 9)) == (
        date(2026, 1, 5), date(2026, 1, 9))


def test_unknown_preset_raises():
    with pytest.raises(ValueError):
        resolve_dates("last_fortnight", today=TODAY)


def test_no_args_defaults_to_last_30d():
    df, dt = resolve_dates(None, today=TODAY)
    assert (dt - df).days == 30 and dt == TODAY


def test_date_from_alone_runs_to_today():
    assert resolve_dates(None, date_from=date(2026, 6, 1), today=TODAY) == (
        date(2026, 6, 1), TODAY)


def test_date_to_alone_raises():
    with pytest.raises(ValueError, match="date_from"):
        resolve_dates(None, date_to=date(2026, 6, 1), today=TODAY)


# ---- compare-range shifting --------------------------------------------

from hub.core.presets import shift_range  # noqa: E402


def test_shift_prev_period_equal_length():
    assert shift_range(date(2026, 6, 1), date(2026, 6, 30), "prev_period") == (
        date(2026, 5, 2), date(2026, 5, 31))


def test_shift_prev_day_and_week():
    assert shift_range(date(2026, 7, 14), date(2026, 7, 14), "prev_day") == (
        date(2026, 7, 13), date(2026, 7, 13))
    assert shift_range(date(2026, 7, 7), date(2026, 7, 13), "prev_week") == (
        date(2026, 6, 30), date(2026, 7, 6))


def test_shift_prev_month_calendar_aligned():
    # calendar month vs calendar month, not "30 days back"
    assert shift_range(date(2026, 6, 1), date(2026, 6, 30), "prev_month") == (
        date(2026, 5, 1), date(2026, 5, 30))
    # day clamping: Mar 31 -> Feb 28
    assert shift_range(date(2026, 3, 31), date(2026, 3, 31), "prev_month") == (
        date(2026, 2, 28), date(2026, 2, 28))


def test_shift_prev_year():
    assert shift_range(date(2026, 6, 1), date(2026, 6, 30), "prev_year") == (
        date(2025, 6, 1), date(2025, 6, 30))


def test_shift_unknown_mode():
    with pytest.raises(ValueError):
        shift_range(date(2026, 6, 1), date(2026, 6, 30), "bogus")
