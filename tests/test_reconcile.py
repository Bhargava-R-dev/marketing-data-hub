"""Reconciliation: catch a breakdown report OVER-counting against core -
the exact class of bug (GA4's '(other)' rows) that inflated Sharekhan's
numbers by 38% for weeks before anyone noticed."""
from datetime import date

import pytest

from hub.core.models import UnifiedRow
from hub.core.reconcile import find_over_counts
from hub.core.storage import Storage


@pytest.fixture()
def store(tmp_path):
    return Storage(str(tmp_path / "t.duckdb"))


def row(source, day, sessions=None, clicks=None, extras=None):
    return UnifiedRow(date=day, source=source, account_id="a1", account_name="Vetrotech",
                      sessions=sessions, clicks=clicks, extras=extras or {})


def test_finds_ga4_overcount(store):
    d1, d2 = date(2026, 7, 1), date(2026, 7, 31)
    store.replace_rows("ga4", d1, d2, [row("ga4", d1, sessions=100)])
    # a breakdown report claiming MORE sessions than core - the (other) bug
    store.replace_rows("ga4", d1, d2, [row("ga4", d1, sessions=138)], report="channels")

    findings = find_over_counts(store, d1, d2)
    assert len(findings) == 1
    f = findings[0]
    assert f["source"] == "ga4" and f["report"] == "channels"
    assert f["core_total"] == 100 and f["report_total"] == 138
    assert f["overcount_pct"] == 38.0


def test_no_finding_when_breakdown_undercounts(store):
    """Undercounting is expected/documented (anonymisation, unattributed
    sessions) and must never be flagged - only overcounting is a bug."""
    d1, d2 = date(2026, 7, 1), date(2026, 7, 31)
    store.replace_rows("gsc", d1, d2, [row("gsc", d1, clicks=100)])
    store.replace_rows("gsc", d1, d2, [row("gsc", d1, clicks=60)], report="queries")

    assert find_over_counts(store, d1, d2) == []


def test_no_finding_when_within_tolerance(store):
    d1, d2 = date(2026, 7, 1), date(2026, 7, 31)
    store.replace_rows("gsc", d1, d2, [row("gsc", d1, clicks=1000)])
    store.replace_rows("gsc", d1, d2, [row("gsc", d1, clicks=1005)], report="queries")  # 0.5%

    assert find_over_counts(store, d1, d2) == []


def test_pages_and_events_are_never_checked_for_ga4():
    """report='pages'/'events' are page-view/event scoped, a different
    attribution model than core's session scope - would never reconcile
    even when working correctly, so must not be in the reconcilable set."""
    from hub.core.reconcile import RECONCILABLE_REPORTS
    assert "pages" not in RECONCILABLE_REPORTS["ga4"]
    assert "events" not in RECONCILABLE_REPORTS["ga4"]


def test_gsc_pages_is_excluded_too():
    """Confirmed live in the field: GSC's own page-dimension breakdown
    genuinely overcounts core by 2-9.5% (a real Google API characteristic,
    reproduced on a single unpaginated call, not this codebase's
    pagination) - including it here would flag every single account as
    'broken' permanently, a false positive, not a real bug."""
    from hub.core.reconcile import RECONCILABLE_REPORTS
    assert "pages" not in RECONCILABLE_REPORTS["gsc"]


def test_source_filter_restricts_to_one_connector(store):
    d1, d2 = date(2026, 7, 1), date(2026, 7, 31)
    store.replace_rows("ga4", d1, d2, [row("ga4", d1, sessions=100)])
    store.replace_rows("ga4", d1, d2, [row("ga4", d1, sessions=200)], report="channels")
    store.replace_rows("gsc", d1, d2, [row("gsc", d1, clicks=50)])
    store.replace_rows("gsc", d1, d2, [row("gsc", d1, clicks=999)], report="queries")

    findings = find_over_counts(store, d1, d2, source="ga4")
    assert len(findings) == 1 and findings[0]["source"] == "ga4"


def test_missing_breakdown_report_is_skipped_not_an_error(store):
    d1, d2 = date(2026, 7, 1), date(2026, 7, 31)
    store.replace_rows("ga4", d1, d2, [row("ga4", d1, sessions=100)])
    # no 'channels' report synced at all - must not crash or false-positive
    assert find_over_counts(store, d1, d2, source="ga4") == []


def test_run_sync_prints_warning_on_overcount(tmp_path, capsys):
    from hub.connectors.base import BaseConnector, FieldRegistry, FieldSpec
    from hub.core.config import ConnectorSettings
    from hub.core.sync import run_sync

    class Fake(BaseConnector):
        id = "ga4"
        fields = FieldRegistry([FieldSpec("date", "date", dimension=True),
                               FieldSpec("sessions", "sessions")])
        reports = {"channels": FieldRegistry([
            FieldSpec("date", "date", dimension=True),
            FieldSpec("channel", "channel", dimension=True),
            FieldSpec("sessions", "sessions")])}

        def __init__(self):
            super().__init__(ConnectorSettings(options={}), ".")

        def authenticate(self):
            pass

        def extract(self, date_from, date_to):
            return [{"date": date_from.isoformat(), "account_id": "a1", "sessions": 100}]

        def extract_report(self, report, date_from, date_to):
            if report == "core":
                return self.extract(date_from, date_to)
            return [{"date": date_from.isoformat(), "account_id": "a1",
                     "channel": "x", "sessions": 999}]  # deliberately overcounts

    store = Storage(str(tmp_path / "t.duckdb"))
    run_sync(store, Fake(), date_from=date(2026, 7, 1), date_to=date(2026, 7, 1))
    captured = capsys.readouterr()
    assert "[WARN] reconciliation" in captured.out
    assert "OVER core" in captured.out
    store.close()


def test_run_sync_stays_quiet_when_reconciled(tmp_path, capsys):
    from hub.connectors.base import BaseConnector, FieldRegistry, FieldSpec
    from hub.core.config import ConnectorSettings
    from hub.core.sync import run_sync

    class Fake(BaseConnector):
        id = "ga4"
        fields = FieldRegistry([FieldSpec("date", "date", dimension=True),
                               FieldSpec("sessions", "sessions")])

        def __init__(self):
            super().__init__(ConnectorSettings(options={}), ".")

        def authenticate(self):
            pass

        def extract(self, date_from, date_to):
            return [{"date": date_from.isoformat(), "account_id": "a1", "sessions": 100}]

        def extract_report(self, report, date_from, date_to):
            return self.extract(date_from, date_to)

    store = Storage(str(tmp_path / "t.duckdb"))
    run_sync(store, Fake(), date_from=date(2026, 7, 1), date_to=date(2026, 7, 1))
    assert "[WARN]" not in capsys.readouterr().out
    store.close()
