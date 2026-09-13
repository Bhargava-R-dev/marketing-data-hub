import pytest


@pytest.fixture(autouse=True)
def _no_bundled_google_client(monkeypatch, tmp_path):
    # The package ships a real OAuth client. Without this, any test that
    # exercises the "no client file" path would find it and start a real
    # browser login that blocks for minutes. Tests that want the bundled
    # fallback point BUNDLED_CLIENT at a temp file themselves.
    from hub.connectors import google_auth

    monkeypatch.setattr(google_auth, "BUNDLED_CLIENT", tmp_path / "_no_bundled_client.json")
