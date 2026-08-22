from __future__ import annotations

from datetime import date

# Expected reporting lag per source, in days - how far behind "today" is
# NORMAL/healthy for that API, before a gap means something's actually
# wrong. A bare "latest synced: Aug 18" next to "today: Aug 21" is
# unreadable on its own - GSC's routine 2-3 day lag looks identical to a
# real 3-day outage without this context, which is exactly why "is this
# broken or normal?" kept having to be answered by asking a human.
EXPECTED_LAG_DAYS = {
    "ga4": 1,        # can be same-day; treat yesterday as fully healthy
    "gsc": 3,        # Google's own documented search-data reporting lag
    "youtube": 1,
    "google_ads": 1,
    "meta_ads": 1,
}
_DEFAULT_LAG_DAYS = 2


def interpret_freshness(source: str, latest_date: date | None,
                        today: date | None = None) -> dict:
    """Turn a raw 'latest synced date' into a status a human (or an LLM)
    can act on without knowing each API's quirks: 'current' or 'N day(s)
    behind expected'. `today` is injectable for tests; defaults to today."""
    today = today or date.today()
    if latest_date is None:
        return {"status": "no_data", "label": "no data yet", "days_behind": None}
    actual_lag = (today - latest_date).days
    expected = EXPECTED_LAG_DAYS.get(source, _DEFAULT_LAG_DAYS)
    behind = max(0, actual_lag - expected)
    if behind == 0:
        return {"status": "current", "label": "current", "days_behind": 0}
    return {"status": "stale",
            "label": f"{behind} day(s) behind expected",
            "days_behind": behind}
