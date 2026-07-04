import pytest

from hub.connectors.catalog import ALL_CONNECTORS, build_connector
from hub.connectors.ga4 import GA4Connector
from hub.core.config import ConnectorSettings, HubConfig


def test_catalog_lists_all_five():
    assert set(ALL_CONNECTORS) == {"ga4", "gsc", "youtube", "google_ads", "meta_ads"}


def test_build_configured_connector():
    cfg = HubConfig(connectors={"ga4": ConnectorSettings(options={"property_id": "1"})})
    conn = build_connector("ga4", cfg)
    assert isinstance(conn, GA4Connector)
    assert conn.settings.options["property_id"] == "1"


def test_build_unconfigured_raises():
    with pytest.raises(KeyError, match="not configured"):
        build_connector("ga4", HubConfig())


def test_build_unknown_raises():
    with pytest.raises(KeyError, match="unknown"):
        build_connector("nope", HubConfig())
