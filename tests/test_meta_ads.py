import pytest

from hub.connectors.base import AuthError
from hub.connectors.meta_ads import META_FIELDS, MetaAdsConnector, parse_meta_insights
from hub.core.config import ConnectorSettings

FIXTURE = [
    {"date_start": "2026-07-01", "campaign_id": "c1", "campaign_name": "Retarget",
     "impressions": "2000", "clicks": "80", "spend": "45.20",
     "actions": [{"action_type": "purchase", "value": "4"},
                 {"action_type": "link_click", "value": "70"}]},
]


def test_parse_meta_insights():
    rows = parse_meta_insights(FIXTURE, account_id="act_1")
    assert rows[0] == {
        "account_id": "act_1", "account_name": "Meta act_1",
        "date": "2026-07-01", "campaign_id": "c1", "campaign": "Retarget",
        "impressions": "2000", "clicks": "80", "spend": "45.20",
        "conversions": 4.0,
    }


def test_parse_custom_conversion_actions():
    rows = parse_meta_insights(FIXTURE, account_id="act_1",
                               conversion_actions=["link_click"])
    assert rows[0]["conversions"] == 70.0


def test_connector_metadata():
    assert MetaAdsConnector.id == "meta_ads"
    assert "spend" in META_FIELDS.names()


def test_authenticate_without_token_raises_hint():
    conn = MetaAdsConnector(ConnectorSettings(options={"ad_account_id": "act_1"}), ".")
    with pytest.raises(AuthError) as exc:
        conn.authenticate()
    assert "access_token" in exc.value.hint
