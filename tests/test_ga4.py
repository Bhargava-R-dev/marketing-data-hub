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


# ---- '(other)' cardinality-overflow bisection ---------------------------

from datetime import date as _date

from hub.connectors.base import FieldRegistry as _FR
from hub.connectors.ga4 import GA4_REPORTS, GA4Connector, has_other_row
from hub.core.config import ConnectorSettings as _CS


def test_has_other_row():
    dims = ["device", "country"]
    assert has_other_row([{"device": "(other)", "country": "India"}], dims)
    assert not has_other_row([{"device": "mobile", "country": "(other) places"}], dims)
    assert not has_other_row([{"device": "mobile", "sessions": "5"}], dims)


class BisectProbe(GA4Connector):
    """Stub _fetch_once: multi-day ranges come back cardinality-collapsed,
    single days come back clean — mirrors real GA4 on huge properties."""

    def __init__(self):
        super().__init__(_CS(options={"property_id": "1"}), ".")
        self.calls = []

    def _fetch_once(self, client, registry, n2u, property_id, label,
                    date_from, date_to):
        self.calls.append((date_from, date_to))
        if date_from < date_to:
            return [{"date": date_from.isoformat(), "account_id": "1",
                     "device": "(other)", "country": "(other)", "sessions": "999"}]
        return [{"date": date_from.isoformat(), "account_id": "1",
                 "device": "mobile", "country": "India", "sessions": "10"}]


def test_fetch_range_bisects_until_clean():
    probe = BisectProbe()
    reg = GA4_REPORTS["audience"]
    rows = probe._fetch_range(None, reg, reg.native_to_unified(), "1", None,
                              _date(2026, 6, 1), _date(2026, 6, 4))
    assert len(rows) == 4  # one clean row per day
    assert all(r["device"] == "mobile" for r in rows)
    # every returned row came from a single-day request
    single_day_calls = [c for c in probe.calls if c[0] == c[1]]
    assert len(single_day_calls) == 4


def test_fetch_range_keeps_single_day_other():
    # a single day that still overflows is stored as-is (no finer split)
    class AlwaysOther(BisectProbe):
        def _fetch_once(self, client, registry, n2u, property_id, label,
                        date_from, date_to):
            return [{"date": date_from.isoformat(), "account_id": "1",
                     "device": "(other)", "country": "(other)", "sessions": "7"}]

    probe = AlwaysOther()
    reg = GA4_REPORTS["audience"]
    rows = probe._fetch_range(None, reg, reg.native_to_unified(), "1", None,
                              _date(2026, 6, 1), _date(2026, 6, 1))
    assert len(rows) == 1 and rows[0]["device"] == "(other)"
