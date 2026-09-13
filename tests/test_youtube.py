from hub.connectors.youtube import YOUTUBE_FIELDS, YouTubeConnector, parse_youtube_response

FIXTURE = {
    "columnHeaders": [
        {"name": "day"}, {"name": "views"}, {"name": "likes"},
        {"name": "estimatedMinutesWatched"}, {"name": "subscribersGained"},
    ],
    "rows": [
        ["2026-07-01", 500, 40, 1200, 6],
        ["2026-07-02", 430, 33, 990, 2],
    ],
}


def test_parse_youtube_response():
    rows = parse_youtube_response(FIXTURE, channel_id="mine")
    assert rows[0] == {
        "account_id": "mine", "account_name": "YouTube mine",
        "date": "2026-07-01", "views": 500, "likes": 40,
        "watch_minutes": 1200, "subscribers_gained": 6,
    }


def test_parse_empty():
    assert parse_youtube_response({"rows": []}, channel_id="mine") == []


def test_connector_metadata():
    assert YouTubeConnector.id == "youtube"
    assert set(YOUTUBE_FIELDS.names()) == {
        "date", "views", "likes", "watch_minutes", "subscribers_gained"}


def test_youtube_requests_its_own_scope(monkeypatch, tmp_path):
    from hub.connectors import youtube as yt_mod
    from hub.connectors.google_auth import GOOGLE_SCOPES, YOUTUBE_SCOPE
    from hub.core.config import ConnectorSettings

    captured = {}

    def fake_get_credentials(secrets_dir, scopes=None, identity=None):
        captured["scopes"] = scopes
        return object()

    monkeypatch.setattr(yt_mod, "get_credentials", fake_get_credentials)
    conn = YouTubeConnector(ConnectorSettings(options={}), tmp_path)
    conn.authenticate()
    assert captured["scopes"] == [*GOOGLE_SCOPES, YOUTUBE_SCOPE]
