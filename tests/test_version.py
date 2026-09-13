from hub.core import version


def test_current_reads_installed_metadata():
    assert version.current().count(".") >= 1


def test_latest_returns_none_when_offline(monkeypatch):
    def boom(*a, **k):
        raise OSError("no network")
    monkeypatch.setattr(version, "_fetch_json", boom)
    version._cache.clear()
    assert version.latest() is None
    version._cache.clear()


def test_latest_parses_release(monkeypatch):
    monkeypatch.setattr(version, "_fetch_json", lambda url, timeout: {
        "tag_name": "v9.9.9", "html_url": "https://example/rel"})
    version._cache.clear()
    assert version.latest() == {"version": "9.9.9", "url": "https://example/rel"}
    assert version.is_newer("9.9.9", "0.4.0") is True
    assert version.is_newer("0.4.0", "0.4.0") is False
    assert version.is_newer("0.4.0", "0.10.0") is False
    version._cache.clear()
