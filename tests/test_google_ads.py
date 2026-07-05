import pytest

from hub.connectors.base import AuthError
from hub.connectors.google_ads import (GOOGLE_ADS_FIELDS, GoogleAdsConnector,
                                       parse_google_ads_rows)
from hub.core.config import ConnectorSettings

FIXTURE = [
    {"segments.date": "2026-07-01", "campaign.id": 111, "campaign.name": "Brand",
     "metrics.impressions": 1000, "metrics.clicks": 50,
     "metrics.cost_micros": 12_500_000, "metrics.conversions": 3.0,
     "metrics.conversions_value": 240.0},
]


def test_parse_google_ads_rows():
    rows = parse_google_ads_rows(FIXTURE, customer_id="123-456")
    assert rows[0] == {
        "account_id": "123-456", "account_name": "Google Ads 123-456",
        "date": "2026-07-01", "campaign_id": "111", "campaign": "Brand",
        "impressions": 1000, "clicks": 50, "spend": 12.5,
        "conversions": 3.0, "conversion_value": 240.0,
    }


def test_connector_metadata():
    assert GoogleAdsConnector.id == "google_ads"
    assert "spend" in GOOGLE_ADS_FIELDS.names()


def test_authenticate_without_dev_token_raises_hint():
    conn = GoogleAdsConnector(ConnectorSettings(options={"customer_id": "1"}), ".")
    with pytest.raises(AuthError) as exc:
        conn.authenticate()
    assert "developer_token" in exc.value.hint
