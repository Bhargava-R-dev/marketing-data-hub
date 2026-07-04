from hub.connectors.gsc import GSC_FIELDS, SearchConsoleConnector, parse_gsc_response

FIXTURE = {
    "rows": [
        {"keys": ["2026-07-01"], "clicks": 31, "impressions": 820,
         "ctr": 0.0378, "position": 14.2},
        {"keys": ["2026-07-02"], "clicks": 27, "impressions": 790,
         "ctr": 0.0342, "position": 15.1},
    ]
}


def test_parse_gsc_response():
    rows = parse_gsc_response(FIXTURE, site_url="sc-domain:example.com")
    assert rows[0] == {
        "account_id": "sc-domain:example.com", "account_name": "sc-domain:example.com",
        "date": "2026-07-01", "clicks": 31, "impressions": 820,
        "ctr": 0.0378, "position": 14.2,
    }


def test_parse_empty_response():
    assert parse_gsc_response({}, site_url="x") == []


def test_connector_metadata():
    assert SearchConsoleConnector.id == "gsc"
    assert set(GSC_FIELDS.names()) == {"date", "clicks", "impressions", "ctr", "position"}
