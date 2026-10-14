import pytest


@pytest.fixture(autouse=True)
def _no_bundled_google_client(monkeypatch, tmp_path):
    # The package ships a real OAuth client. Without this, any test that
    # exercises the "no client file" path would find it and start a real
    # browser login that blocks for minutes. Tests that want the bundled
    # fallback point BUNDLED_CLIENT at a temp file themselves.
    from hub.connectors import google_auth

    monkeypatch.setattr(google_auth, "BUNDLED_CLIENT", tmp_path / "_no_bundled_client.json")


@pytest.fixture(autouse=True)
def _no_live_api_calls(monkeypatch, request):
    # live mode is the default, so any MCP/API test with a configured connector
    # would otherwise try to fetch from the real APIs. test_live.py exercises
    # the real ensure_fresh with fake connectors.
    if request.module.__name__.endswith("test_live"):
        return
    from hub.core import live

    monkeypatch.setattr(live, "ensure_fresh", lambda *a, **k: live.LiveResult())
