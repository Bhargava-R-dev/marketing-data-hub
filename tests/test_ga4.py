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


def test_connector_metadata():
    assert GA4Connector.id == "ga4"
    assert set(GA4_FIELDS.names()) == {
        "date", "campaign", "sessions", "users", "conversions", "conversion_value"}
