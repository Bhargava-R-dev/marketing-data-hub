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


def test_parse_gsc_response_with_label():
    rows = parse_gsc_response(FIXTURE, site_url="sc-domain:example.com", account_name="Vetrotech")
    assert rows[0]["account_name"] == "Vetrotech"


def test_connector_metadata():
    assert SearchConsoleConnector.id == "gsc"
    assert set(GSC_FIELDS.names()) == {"date", "clicks", "impressions", "ctr", "position"}


def test_one_site_failing_does_not_block_the_others():
    """A 403 on one site (wrong property type, revoked access, ...) must not
    abort the whole batch or mislabel sites that never even ran."""
    from unittest.mock import MagicMock

    from hub.core.config import ConnectorSettings

    conn = SearchConsoleConnector(ConnectorSettings(options={
        "site_urls": ["https://bad.example/", "https://good.example/"],
        "labels": {"https://bad.example/": "Bad", "https://good.example/": "Good"}}), ".")
    conn._groups = {"default": ["https://bad.example/", "https://good.example/"]}

    service = MagicMock()

    def query_side_effect(siteUrl, body):
        if siteUrl == "https://bad.example/":
            raise RuntimeError("403 insufficient permission")
        return MagicMock(execute=lambda: FIXTURE)
    service.searchanalytics.return_value.query.side_effect = query_side_effect
    conn._creds = {"default": object()}

    errors, progressed = [], []
    conn.progress_error = lambda aid, err: errors.append((aid, err))
    conn.progress = lambda aid, label, rows: progressed.append((aid, rows))

    from datetime import date
    from unittest.mock import patch
    with patch("googleapiclient.discovery.build", return_value=service):
        rows = conn.extract_report("core", date(2026, 7, 1), date(2026, 7, 2))

    assert errors == [("https://bad.example/", "403 insufficient permission")]
    assert [aid for aid, _ in progressed] == ["https://good.example/"]
    assert len(rows) == 2  # only the good site's rows made it through
    assert all(r["account_name"] == "Good" for r in rows)
