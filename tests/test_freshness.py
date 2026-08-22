"""Freshness interpretation: '✓ current' vs '⚠ N days behind expected'."""
from datetime import date

from hub.core.freshness import EXPECTED_LAG_DAYS, interpret_freshness


def test_no_data_yet():
    assert interpret_freshness("ga4", None) == {
        "status": "no_data", "label": "no data yet", "days_behind": None}


def test_ga4_within_expected_lag_is_current():
    today = date(2026, 8, 21)
    r = interpret_freshness("ga4", date(2026, 8, 20), today=today)  # 1 day lag
    assert r == {"status": "current", "label": "current", "days_behind": 0}


def test_gsc_within_its_longer_expected_lag_is_current():
    """GSC's normal 2-3 day search-data lag must not be flagged as broken -
    this is the exact ambiguity that made a real outage indistinguishable
    from routine lag before this fix existed."""
    today = date(2026, 8, 21)
    r = interpret_freshness("gsc", date(2026, 8, 18), today=today)  # 3 days
    assert r["status"] == "current"


def test_gsc_beyond_expected_lag_is_stale():
    today = date(2026, 8, 21)
    r = interpret_freshness("gsc", date(2026, 8, 10), today=today)  # 11 days
    assert r["status"] == "stale"
    assert r["days_behind"] == 11 - EXPECTED_LAG_DAYS["gsc"]
    assert "behind expected" in r["label"]


def test_unknown_source_uses_default_lag():
    today = date(2026, 8, 21)
    r = interpret_freshness("some_new_connector", date(2026, 8, 20), today=today)
    assert r["status"] == "current"  # 1 day lag, default allows 2


def test_exactly_at_expected_lag_boundary_is_current():
    today = date(2026, 8, 21)
    r = interpret_freshness("gsc", date(2026, 8, 18), today=today)  # exactly 3
    assert r["days_behind"] == 0
