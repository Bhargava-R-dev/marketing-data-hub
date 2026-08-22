"""Multi-report support: report-sliced storage, per-report sync, report registries."""
from datetime import date

import duckdb
import pytest

from hub.connectors.base import BaseConnector, FieldRegistry, FieldSpec
from hub.connectors.ga4 import GA4_REPORTS, GA4Connector, parse_ga4_report
from hub.connectors.gsc import GSC_REPORTS, SearchConsoleConnector, parse_gsc_response
from hub.connectors.youtube import YouTubeConnector
from hub.core.config import ConnectorSettings
from hub.core.models import UnifiedRow
from hub.core.normalizer import normalize
from hub.core.storage import Storage
from hub.core.sync import run_sync


@pytest.fixture()
def store(tmp_path):
    return Storage(str(tmp_path / "t.duckdb"))


def row(source, day, clicks, report_extras=None):
    return UnifiedRow(date=day, source=source, account_id="a1", account_name="Acct",
                      clicks=clicks, extras=report_extras or {})


# ---- storage ----------------------------------------------------------


def test_reports_are_isolated_slices(store):
    d = date(2026, 7, 1)
    store.replace_rows("gsc", d, d, [row("gsc", d, 100)])  # core totals
    store.replace_rows("gsc", d, d, [row("gsc", d, 60, {"query": "vetrotech"}),
                                     row("gsc", d, 30, {"query": "fire glass"})],
                       report="queries")
    # core query must not double count with the breakdown rows
    assert store.query(["date", "clicks"], d, d) == [{"date": d, "clicks": 100}]
    out = store.query(["date", "query", "clicks"], d, d, report="queries")
    assert {(r["query"], r["clicks"]) for r in out} == {("vetrotech", 60),
                                                        ("fire glass", 30)}


def test_replace_scoped_to_report(store):
    d = date(2026, 7, 1)
    store.replace_rows("gsc", d, d, [row("gsc", d, 100)])
    store.replace_rows("gsc", d, d, [row("gsc", d, 1)], report="queries")
    store.replace_rows("gsc", d, d, [row("gsc", d, 2)], report="queries")  # replaces
    assert store.query(["clicks"], d, d) == [{"clicks": 100}]  # core untouched
    assert store.query(["clicks"], d, d, report="queries") == [{"clicks": 2}]


def test_row_counts_and_accounts_count_core_only(store):
    d = date(2026, 7, 1)
    store.replace_rows("gsc", d, d, [row("gsc", d, 100)])
    store.replace_rows("gsc", d, d, [row("gsc", d, 60), row("gsc", d, 40)],
                       report="queries")
    assert store.row_counts()["gsc"]["rows"] == 1
    assert store.accounts()[0]["rows"] == 1


def test_report_coverage(store):
    d = date(2026, 7, 1)
    store.replace_rows("gsc", d, d, [row("gsc", d, 100)])
    store.replace_rows("gsc", d, d, [row("gsc", d, 60)], report="queries")
    cov = {(c["source"], c["report"]): c["rows"] for c in store.report_coverage()}
    assert cov == {("gsc", "core"): 1, ("gsc", "queries"): 1}


def test_migration_adds_report_column_to_old_db(tmp_path):
    db = str(tmp_path / "old.duckdb")
    conn = duckdb.connect(db)  # pre-multi-report schema, no report column
    conn.execute("""CREATE TABLE metrics (
        date DATE, source VARCHAR, account_id VARCHAR, account_name VARCHAR,
        campaign_id VARCHAR, campaign VARCHAR,
        impressions BIGINT, clicks BIGINT, spend DOUBLE, conversions DOUBLE,
        conversion_value DOUBLE, sessions BIGINT, users BIGINT, extras JSON)""")
    conn.execute("""INSERT INTO metrics VALUES (DATE '2026-07-01', 'gsc', 'a', 'A',
        NULL, NULL, 10, 5, NULL, NULL, NULL, NULL, NULL, '{}')""")
    conn.close()
    store = Storage(db)
    d = date(2026, 7, 1)
    assert store.query(["clicks"], d, d) == [{"clicks": 5}]  # old rows -> core


# ---- normalizer -------------------------------------------------------


def test_normalize_sets_report_and_excludes_it_from_extras():
    d = date(2026, 7, 1)
    out = normalize("gsc", [{"date": d, "account_id": "a", "clicks": 1,
                             "query": "x", "report": "ignored"}], report="queries")
    assert out[0].report == "queries"
    assert out[0].extras == {"query": "x"}


# ---- connector framework ----------------------------------------------


class MultiReportConnector(BaseConnector):
    id = "fake"
    fields = FieldRegistry([FieldSpec("date", "date", dimension=True),
                            FieldSpec("clicks", "clicks")])
    reports = {"queries": FieldRegistry([FieldSpec("date", "date", dimension=True),
                                         FieldSpec("query", "query", dimension=True),
                                         FieldSpec("clicks", "clicks")])}

    def __init__(self, options=None):
        super().__init__(ConnectorSettings(options=options or {}), ".")

    def authenticate(self):
        pass

    def extract(self, date_from, date_to):
        return [{"date": date_from.isoformat(), "account_id": "a", "clicks": 100}]

    def extract_report(self, report, date_from, date_to):
        if report == "core":
            return self.extract(date_from, date_to)
        return [{"date": date_from.isoformat(), "account_id": "a",
                 "query": "q1", "clicks": 60}]


def test_get_reports_defaults_to_core_for_legacy_connectors():
    assert list(YouTubeConnector.get_reports()) == ["core"]


def test_enabled_reports_all_by_default_and_restrictable():
    assert MultiReportConnector().enabled_reports() == ["core", "queries"]
    assert MultiReportConnector({"reports": ["core"]}).enabled_reports() == ["core"]
    with pytest.raises(KeyError):
        MultiReportConnector({"reports": ["nope"]}).enabled_reports()


def test_run_sync_writes_every_report(store):
    d = date(2026, 7, 1)
    n = run_sync(store, MultiReportConnector(), date_from=d, date_to=d)
    assert n == 2  # one core row + one queries row
    assert store.query(["clicks"], d, d) == [{"clicks": 100}]
    assert store.query(["query", "clicks"], d, d, report="queries") == [
        {"query": "q1", "clicks": 60}]


# ---- report registries -------------------------------------------------


def test_ga4_reports_cover_analyst_needs():
    assert {"channels", "landing_pages", "pages", "audience", "visitors"} <= set(GA4_REPORTS)
    assert "channel" in GA4_REPORTS["channels"].names()
    assert "landing_page" in GA4_REPORTS["landing_pages"].names()
    # only additive metrics stored - no rate metrics
    for reg in GA4_REPORTS.values():
        assert not any("rate" in s.name.lower() for s in reg.metrics())


def test_landing_pages_carries_new_users():
    """'how many NEW users landed on this specific page' was previously
    unanswerable from synced data - users existed but not new_users."""
    reg = GA4_REPORTS["landing_pages"]
    assert "new_users" in reg.names()
    spec = next(s for s in reg.specs if s.name == "new_users")
    assert spec.native == "newUsers"
    assert spec.dimension is False  # additive metric, not a new dimension -
    # adding a dimension would change every existing row's granularity


def test_gsc_reports_cover_analyst_needs():
    assert {"queries", "pages", "devices", "countries"} <= set(GSC_REPORTS)
    assert "query" in GSC_REPORTS["queries"].names()
    assert "page" in GSC_REPORTS["pages"].names()


def test_parse_ga4_report_with_report_registry():
    reg = GA4_REPORTS["channels"]
    report = {
        "dimensionHeaders": [{"name": "date"}, {"name": "sessionDefaultChannelGroup"}],
        "metricHeaders": [{"name": "sessions"}, {"name": "totalUsers"},
                          {"name": "keyEvents"}, {"name": "engagedSessions"},
                          {"name": "screenPageViews"}],
        "rows": [{"dimensionValues": [{"value": "20260701"}, {"value": "Organic Search"}],
                  "metricValues": [{"value": "50"}, {"value": "40"}, {"value": "2"},
                                   {"value": "30"}, {"value": "90"}]}],
    }
    out = parse_ga4_report(report, "123", "Vetrotech", reg.native_to_unified())
    assert out[0]["channel"] == "Organic Search"
    assert out[0]["engaged_sessions"] == "30"
    assert out[0]["date"] == "2026-07-01"


def test_parse_gsc_response_with_extra_dimension():
    resp = {"rows": [{"keys": ["2026-07-01", "vetrotech glass"], "clicks": 9,
                      "impressions": 100, "ctr": 0.09, "position": 3.2}]}
    out = parse_gsc_response(resp, "https://x.com/", "Vetrotech", ("date", "query"))
    assert out[0]["query"] == "vetrotech glass"
    assert out[0]["date"] == "2026-07-01"
    assert out[0]["clicks"] == 9


def test_ga4_and_gsc_declare_reports():
    assert set(GA4Connector.get_reports()) == {"core", *GA4_REPORTS}
    assert set(SearchConsoleConnector.get_reports()) == {"core", *GSC_REPORTS}


# ---- extras aggregation & filtering ------------------------------------


def test_extra_metrics_are_summed_not_grouped(store):
    d1, d2 = date(2026, 7, 1), date(2026, 7, 2)
    store.replace_rows("ga4", d1, d2, [
        UnifiedRow(date=d1, source="ga4", account_id="a", account_name="A",
                   sessions=10, extras={"channel": "Organic Search", "pageviews": 100}),
        UnifiedRow(date=d2, source="ga4", account_id="a", account_name="A",
                   sessions=20, extras={"channel": "Organic Search", "pageviews": 50}),
    ], report="channels")
    out = store.query(["channel", "sessions", "pageviews"], d1, d2,
                      report="channels", extra_metrics={"pageviews"})
    assert out == [{"channel": "Organic Search", "sessions": 30, "pageviews": 150.0}]


def test_filters_on_extras_dimension(store):
    d = date(2026, 7, 1)
    store.replace_rows("ga4", d, d, [
        UnifiedRow(date=d, source="ga4", account_id="a", account_name="A",
                   extras={"event": "form_submit", "events": 7}),
        UnifiedRow(date=d, source="ga4", account_id="a", account_name="A",
                   extras={"event": "call_click", "events": 3}),
    ], report="events")
    out = store.query(["event", "events"], d, d, report="events",
                      filters={"event": "form_submit"}, extra_metrics={"events"})
    assert out == [{"event": "form_submit", "events": 7.0}]


def test_extra_metric_fields_helper():
    from hub.connectors.catalog import extra_metric_fields
    assert "pageviews" in extra_metric_fields("channels", ["ga4"])
    assert "engaged_sessions" in extra_metric_fields("channels", ["ga4"])
    # non-additive extras must not be summed
    assert "position" not in extra_metric_fields("queries", ["gsc"])
    assert "ctr" not in extra_metric_fields("queries", ["gsc"])
    # core metrics live in real columns, not extras
    assert "sessions" not in extra_metric_fields("channels", ["ga4"])


def test_ga4_events_report_registered():
    reg = GA4_REPORTS["events"]
    assert "event" in [s.name for s in reg.dimensions()]
    assert {"events", "conversions", "users"} <= {s.name for s in reg.metrics()}


# ---- branded / non-branded tagging --------------------------------------


def test_tag_branded_matches_substring_case_insensitive():
    from hub.connectors.gsc import tag_branded
    rows = [{"query": "Vetrotech fire glass"}, {"query": "fire rated glass price"},
            {"query": "SAINT GOBAIN glazing"}, {"query": None}]
    tag_branded(rows, ["vetrotech", "saint gobain"])
    assert [r["branded"] for r in rows] == [True, False, True, False]


def test_branded_is_registered_but_not_an_api_dimension():
    reg = GSC_REPORTS["queries"]
    assert "branded" in [s.name for s in reg.dimensions()]
    api_dims = [s.name for s in reg.dimensions() if not s.native.startswith("_")]
    assert api_dims == ["date", "query"]  # branded never sent to the API


def test_branded_split_roundtrip(store):
    d = date(2026, 7, 1)
    store.replace_rows("gsc", d, d, [
        UnifiedRow(date=d, source="gsc", account_id="x", account_name="Vetrotech",
                   clicks=60, extras={"query": "vetrotech glass", "branded": True}),
        UnifiedRow(date=d, source="gsc", account_id="x", account_name="Vetrotech",
                   clicks=40, extras={"query": "fire glass", "branded": False}),
    ], report="queries")
    out = store.query(["branded", "clicks"], d, d, report="queries")
    assert {(r["branded"], r["clicks"]) for r in out} == {("true", 60), ("false", 40)}
    only = store.query(["clicks"], d, d, report="queries",
                       filters={"branded": "true"})
    assert only == [{"clicks": 60}]
