from hub.connectors.ga4 import GA4_FIELDS, GA4Connector, parse_ga4_report

FIXTURE = {
    "dimensionHeaders": [{"name": "date"}, {"name": "sessionCampaignName"}],
    "metricHeaders": [{"name": "sessions"}, {"name": "totalUsers"},
                      {"name": "keyEvents"}, {"name": "purchaseRevenue"}],
    "rows": [
        {"dimensionValues": [{"value": "20260701"}, {"value": "summer_sale"}],
         "metricValues": [{"value": "120"}, {"value": "95"}, {"value": "4"}, {"value": "199.5"}]},
        {"dimensionValues": [{"value": "20260702"}, {"value": "(direct)"}],
         "metricValues": [{"value": "80"}, {"value": "70"}, {"value": "1"}, {"value": "0"}]},
    ],
}


def test_parse_ga4_report():
    rows = parse_ga4_report(FIXTURE, property_id="123")
    assert len(rows) == 2
    assert rows[0] == {
        "account_id": "123", "account_name": "GA4 123",
        "date": "2026-07-01", "campaign": "summer_sale",
        "sessions": "120", "users": "95", "conversions": "4",
        "conversion_value": "199.5",
    }


def test_parse_empty_report():
    assert parse_ga4_report({"rows": []}, property_id="123") == []


def test_parse_ga4_report_with_label():
    rows = parse_ga4_report(FIXTURE, property_id="123", account_name="Vetrotech")
    assert rows[0]["account_name"] == "Vetrotech"


def test_connector_metadata():
    assert GA4Connector.id == "ga4"
    assert set(GA4_FIELDS.names()) == {
        "date", "campaign", "sessions", "users", "conversions", "conversion_value"}


# ---- GA4 '(other)' rows are dropped, not stored -------------------------

from hub.connectors.ga4 import GA4_REPORTS, parse_ga4_report


def _audience_report(rows):
    return {
        "dimensionHeaders": [{"name": "date"}, {"name": "deviceCategory"},
                             {"name": "country"}],
        "metricHeaders": [{"name": "sessions"}, {"name": "totalUsers"},
                          {"name": "keyEvents"}, {"name": "engagedSessions"}],
        "rows": [{"dimensionValues": [{"value": d} for d in dims],
                  "metricValues": [{"value": m} for m in mets]}
                 for dims, mets in rows],
    }


def test_other_rows_are_dropped():
    # the spurious '(other)' bucket must NOT be stored (it inflated totals)
    reg = GA4_REPORTS["audience"]
    report = _audience_report([
        (["20260610", "mobile", "India"], ["728354", "1", "0", "1"]),
        (["20260610", "(other)", "(other)"], ["442578", "1", "0", "1"]),
        (["20260610", "desktop", "India"], ["37352", "1", "0", "1"]),
    ])
    out = parse_ga4_report(report, "1", "Sharekhan", reg.native_to_unified())
    devices = [r["device"] for r in out]
    assert "(other)" not in devices
    assert devices == ["mobile", "desktop"]
    assert sum(int(r["sessions"]) for r in out) == 765706  # no phantom 442k


def test_other_in_any_dimension_is_dropped():
    reg = GA4_REPORTS["audience"]
    report = _audience_report([
        (["20260610", "mobile", "(other)"], ["100", "1", "0", "1"]),  # dropped
        (["20260610", "mobile", "India"], ["50", "1", "0", "1"]),
    ])
    out = parse_ga4_report(report, "1", "Sharekhan", reg.native_to_unified())
    assert len(out) == 1 and out[0]["country"] == "India"


def test_one_property_failing_does_not_block_the_others(monkeypatch):
    """A permission error on one property must not abort the rest of the
    GA4 batch or mislabel properties that never even ran."""
    from hub.connectors import ga4 as ga4_mod
    from hub.core.config import ConnectorSettings

    conn = ga4_mod.GA4Connector(ConnectorSettings(options={
        "property_ids": ["1", "2"],
        "labels": {"1": "Bad", "2": "Good"}}), ".")
    conn._groups = {"default": ["1", "2"]}
    conn._creds = {"default": object()}

    def fake_fetch(self, client, registry, n2u, property_id, label, date_from, date_to):
        if property_id == "1":
            raise RuntimeError("403 insufficient permission")
        return [{"account_id": "2", "account_name": "Good", "date": "2026-07-01"}]
    monkeypatch.setattr(ga4_mod.GA4Connector, "_fetch", fake_fetch)
    monkeypatch.setattr("google.analytics.data_v1beta.BetaAnalyticsDataClient",
                        lambda credentials: object())

    errors, progressed = [], []
    conn.progress_error = lambda aid, err: errors.append((aid, err))
    conn.progress = lambda aid, label, rows: progressed.append((aid, rows))

    from datetime import date
    rows = conn.extract_report("core", date(2026, 7, 1), date(2026, 7, 2))

    assert errors == [("1", "403 insufficient permission")]
    assert [aid for aid, _ in progressed] == ["2"]
    assert rows == [{"account_id": "2", "account_name": "Good", "date": "2026-07-01"}]
