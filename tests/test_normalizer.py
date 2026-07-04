from datetime import date

from hub.core.models import CORE_DIMENSIONS, CORE_METRICS, UnifiedRow
from hub.core.normalizer import normalize


def test_core_column_lists():
    assert "date" in CORE_DIMENSIONS and "campaign" in CORE_DIMENSIONS
    assert "spend" in CORE_METRICS and "conversions" in CORE_METRICS


def test_normalize_splits_core_and_extras():
    raw = [{
        "date": "2026-07-01", "account_id": "prop-1", "account_name": "My Site",
        "campaign": "summer", "clicks": "42", "spend": 3.5,
        "position": 12.3, "ctr": 0.04,
    }]
    rows = normalize("gsc", raw)
    assert len(rows) == 1
    r = rows[0]
    assert isinstance(r, UnifiedRow)
    assert r.source == "gsc"
    assert r.date == date(2026, 7, 1)
    assert r.clicks == 42           # coerced from string
    assert r.spend == 3.5
    assert r.extras == {"position": 12.3, "ctr": 0.04}
    assert r.impressions is None    # unset metric stays None


def test_normalize_requires_date_and_account():
    import pytest
    with pytest.raises(Exception):
        normalize("ga4", [{"clicks": 1}])
