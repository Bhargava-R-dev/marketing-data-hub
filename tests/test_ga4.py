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
