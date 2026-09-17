"""Setup wizard: API endpoints, security token, config writing."""
import json

import pytest
from fastapi.testclient import TestClient

from hub.core.accounts import set_connector_options
from hub.core.config import load_config
from hub.setup_wizard import create_setup_app


@pytest.fixture()
def wizard(tmp_path):
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        "db_path: data/t.duckdb\nsecrets_dir: secrets\nexports_dir: exports\n"
        "connectors:\n  gsc:\n    options: {site_urls: ['https://a.example/'],\n"
        "      labels: {'https://a.example/': 'Site A'}}\n",
        encoding="utf-8")
    app = create_setup_app(cfg)
    client = TestClient(app, base_url="http://127.0.0.1")
    # fish the per-run token out of the served page (as the browser would)
    page = client.get("/").text
    token = page.split('const TOKEN = "')[1].split('"')[0]
    return client, {"X-Setup-Token": token}, cfg


def test_page_serves_and_embeds_config_path(wizard):
    client, _, cfg = wizard
    page = client.get("/").text
    assert "Marketing Data Hub" in page
    assert "/static/app.js" in page
    assert 'const TOKEN = "' in page


def test_concurrent_sync_requests_spawn_once_and_track_startup(wizard, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from unittest.mock import Mock

    client, headers, _ = wizard
    child = Mock()
    child.poll.return_value = None
    launch = Mock(return_value=child)
    monkeypatch.setattr("hub.setup_wizard.app.subprocess.Popen", launch)
    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(lambda _: client.post("/api/sync", headers=headers).json(), range(6)))
    assert sum(r["status"] == "started" for r in results) == 1
    assert launch.call_count == 1
    assert client.get("/api/sync/status", headers=headers).json()["in_progress"] is True
    child.poll.return_value = 1
    status = client.get("/api/sync/status", headers=headers).json()
    assert status["in_progress"] is False
    assert "exit code 1" in status["error"]
    # Polling and opening a new page never relaunch a failed child.
    client.get("/")
    client.get("/api/sync/status", headers=headers)
    assert launch.call_count == 1
    assert client.post("/api/sync", headers=headers).json()["status"] == "started"


def test_sync_spawn_failure_is_visible_and_retryable(wizard, monkeypatch):
    from unittest.mock import Mock
    client, headers, _ = wizard
    launch = Mock(side_effect=FileNotFoundError("hub.exe missing"))
    monkeypatch.setattr("hub.setup_wizard.app.subprocess.Popen", launch)
    assert client.post("/api/sync", headers=headers).json()["status"] == "failed"
    status = client.get("/api/sync/status", headers=headers).json()
    assert status["in_progress"] is False
    assert "hub.exe missing" in status["error"]


def test_previous_success_cannot_mask_starting_or_failed_child(wizard, monkeypatch, tmp_path):
    from unittest.mock import Mock
    from hub.core.progress import SyncProgress
    client, headers, _ = wizard
    progress = SyncProgress(tmp_path / "logs/sync_progress.json")
    progress.begin([])
    progress.finish()
    child = Mock()
    child.poll.return_value = None
    monkeypatch.setattr("hub.setup_wizard.app.subprocess.Popen", Mock(return_value=child))
    client.post("/api/sync", headers=headers)
    status = client.get("/api/sync/status", headers=headers).json()
    assert status["in_progress"] is True and status["run"] is None
    child.poll.return_value = 0
    assert client.get("/api/sync/status", headers=headers).json()["error"]


def test_state_requires_token(wizard):
    client, headers, _ = wizard
    assert client.get("/api/state").status_code == 403
    assert client.get("/api/state", headers={"X-Setup-Token": "wrong"}).status_code == 403
    r = client.get("/api/state", headers=headers)
    assert r.status_code == 200
    body = r.json()
    assert body["connectors"]["gsc"]["accounts"] == [
        {"id": "https://a.example/", "label": "Site A", "identity": "default"}]


def test_foreign_host_and_origin_are_rejected(wizard):
    client, headers, _ = wizard
    assert client.get("/", headers={"Host": "attacker.example"}).status_code == 400
    assert client.post("/api/sync", headers={**headers, "Origin": "https://attacker.example"}).status_code == 403
    assert client.get("/api/sync/status", headers={**headers, "Origin": "http://127.0.0.1"}).status_code == 200


def test_state_reports_identities(wizard, tmp_path):
    client, headers, cfg = wizard
    secrets = tmp_path / "secrets"
    secrets.mkdir()
    (secrets / "google_token.json").write_text("{}", encoding="utf-8")
    (secrets / "google_token_personal.json").write_text("{}", encoding="utf-8")
    body = client.get("/api/state", headers=headers).json()
    idents = {i["identity"]: i for i in body["identities"]}
    assert set(idents) == {"default", "personal"}
    # invalid/placeholder token content -> no label yet, needs one re-auth click
    assert all(i["needs_reauth"] and i["label"] is None for i in idents.values())


def test_state_shows_real_email_label_when_available(wizard, tmp_path):
    from hub.connectors.google_auth import set_identity_label

    client, headers, cfg = wizard
    secrets = tmp_path / "secrets"
    secrets.mkdir()
    (secrets / "google_token.json").write_text("{}", encoding="utf-8")
    set_identity_label(secrets, "default", "seoteam@example.com")
    body = client.get("/api/state", headers=headers).json()
    default = next(i for i in body["identities"] if i["identity"] == "default")
    assert default["label"] == "seoteam@example.com"
    assert default["needs_reauth"] is False


def test_google_connect_auto_assigns_identity_no_name_needed(wizard, monkeypatch, tmp_path):
    client, headers, cfg = wizard
    (tmp_path / "secrets").mkdir(exist_ok=True)
    (tmp_path / "secrets" / "google_client.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr("hub.connectors.google_auth.login", lambda *a, **k: None)
    r = client.post("/api/google/connect", headers=headers, json={})
    assert r.status_code == 200
    assert r.json()["identity"] == "default"  # first connection -> 'default'


def test_google_connect_second_call_gets_new_slug(wizard, monkeypatch, tmp_path):
    client, headers, cfg = wizard
    (tmp_path / "secrets").mkdir(exist_ok=True)
    (tmp_path / "secrets" / "google_client.json").write_text("{}", encoding="utf-8")
    (tmp_path / "secrets" / "google_token.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr("hub.connectors.google_auth.login", lambda *a, **k: None)
    r = client.post("/api/google/connect", headers=headers, json={})
    assert r.json()["identity"] == "account2"  # 'default' already taken


def test_accounts_endpoint_filters_by_source(wizard, monkeypatch, tmp_path):
    client, headers, cfg = wizard
    (tmp_path / "secrets").mkdir(exist_ok=True)
    (tmp_path / "secrets" / "google_token.json").write_text("{}", encoding="utf-8")
    captured = {}
    monkeypatch.setattr("hub.connectors.google_auth.get_credentials",
                        lambda sd, **k: "creds")

    def fake_discover(creds, source=None):
        captured["source"] = source
        return []
    monkeypatch.setattr("hub.core.accounts.discover_all", fake_discover)
    r = client.get("/api/accounts", headers=headers, params={"source": "ga4"})
    assert r.json()["accounts"] == []
    assert captured["source"] == "ga4"


def test_accounts_add_via_wizard(wizard, monkeypatch):
    client, headers, cfg = wizard
    monkeypatch.setattr("hub.connectors.google_auth.get_credentials",
                        lambda sd, **k: "creds")
    monkeypatch.setattr("hub.core.accounts.discover_all",
                        lambda creds, source=None: [
                            {"source": "ga4", "id": "777", "name": "New Prop",
                             "parent": "Acct"}])
    r = client.post("/api/accounts/add", headers=headers,
                    json={"source": "ga4", "ids": ["777"], "identity": "default"})
    assert r.json() == {"added": ["777"]}
    loaded = load_config(cfg)
    assert loaded.connectors["ga4"].options["property_ids"] == ["777"]
    assert loaded.connectors["ga4"].options["labels"]["777"] == "New Prop"


def test_accounts_add_rejects_unknown_id(wizard, monkeypatch):
    client, headers, _ = wizard
    monkeypatch.setattr("hub.connectors.google_auth.get_credentials",
                        lambda sd, **k: "creds")
    monkeypatch.setattr("hub.core.accounts.discover_all",
                        lambda creds, source=None: [])
    r = client.post("/api/accounts/add", headers=headers,
                    json={"source": "ga4", "ids": ["999"]})
    assert "not visible" in r.json()["error"]


def test_connector_options_meta(wizard):
    client, headers, cfg = wizard
    r = client.post("/api/connector/options", headers=headers, json={
        "source": "meta_ads",
        "options": {"access_token": "tok", "ad_account_ids": ["act_1", "act_2"]}})
    assert sorted(r.json()["saved"]) == ["access_token", "ad_account_ids"]
    loaded = load_config(cfg)
    assert loaded.connectors["meta_ads"].options["ad_account_ids"] == ["act_1", "act_2"]


def test_connector_options_rejects_unknown_keys(wizard):
    client, headers, _ = wizard
    r = client.post("/api/connector/options", headers=headers, json={
        "source": "meta_ads", "options": {"evil_key": "x"}})
    assert "unsupported" in r.json()["error"]
    r = client.post("/api/connector/options", headers=headers, json={
        "source": "ga4", "options": {"access_token": "x"}})
    assert "error" in r.json()


def test_connector_options_drops_empty_values(wizard):
    client, headers, cfg = wizard
    client.post("/api/connector/options", headers=headers, json={
        "source": "google_ads",
        "options": {"developer_token": "dev", "customer_ids": ["1"],
                    "login_customer_id": ""}})  # empty -> not written
    loaded = load_config(cfg)
    assert "login_customer_id" not in loaded.connectors["google_ads"].options


def test_set_connector_options_merges_and_preserves(tmp_path):
    p = tmp_path / "c.yaml"
    p.write_text("connectors:\n  meta_ads:\n    options: {access_token: old}\n",
                 encoding="utf-8")
    set_connector_options(p, "meta_ads", {"ad_account_ids": ["act_9"]})
    loaded = load_config(p)
    assert loaded.connectors["meta_ads"].options["access_token"] == "old"
    assert loaded.connectors["meta_ads"].options["ad_account_ids"] == ["act_9"]


# ---- login failures are surfaced, not silently swallowed -----------------

def test_state_reports_login_error(wizard, monkeypatch, tmp_path):
    import time

    client, headers, cfg = wizard
    (tmp_path / "secrets").mkdir(exist_ok=True)
    (tmp_path / "secrets" / "google_client.json").write_text("{}", encoding="utf-8")

    def boom(*a, **k):
        raise Exception("Google sign-in for identity 'default' was not completed within 300s.")
    monkeypatch.setattr("hub.connectors.google_auth.login", boom)

    r = client.post("/api/google/connect", headers=headers, json={})
    assert r.json()["identity"] == "default"
    for _ in range(50):
        body = client.get("/api/state", headers=headers).json()
        if body["login_errors"].get("default"):
            break
        time.sleep(0.05)
    assert "not completed within 300s" in body["login_errors"]["default"]


def test_retrying_connect_clears_previous_error(wizard, monkeypatch, tmp_path):
    import time

    client, headers, cfg = wizard
    (tmp_path / "secrets").mkdir(exist_ok=True)
    (tmp_path / "secrets" / "google_client.json").write_text("{}", encoding="utf-8")

    def boom(*a, **k):
        raise Exception("boom")
    monkeypatch.setattr("hub.connectors.google_auth.login", boom)
    client.post("/api/google/connect", headers=headers, json={})
    for _ in range(50):
        if client.get("/api/state", headers=headers).json()["login_errors"].get("default"):
            break
        time.sleep(0.05)

    monkeypatch.setattr("hub.connectors.google_auth.login", lambda *a, **k: None)
    client.post("/api/google/connect", headers=headers, json={"identity": "default"})
    body = client.get("/api/state", headers=headers).json()
    assert "default" not in body["login_errors"]


def test_accounts_discovery_is_cached_until_refresh(wizard, monkeypatch, tmp_path):
    client, h, _ = wizard
    (tmp_path / "secrets").mkdir(exist_ok=True)
    (tmp_path / "secrets" / "google_token.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr("hub.connectors.google_auth.get_credentials", lambda *a, **k: object())
    calls = []
    monkeypatch.setattr("hub.core.accounts.discover_all",
                        lambda creds, source=None: calls.append(source) or [
                            {"id": "1", "name": "A", "parent": "P"}])
    client.get("/api/accounts?identity=default&source=ga4&request_id=7", headers=h)
    r = client.get("/api/accounts?identity=default&source=ga4&request_id=8", headers=h)
    assert r.json()["request_id"] == "8"
    assert calls == ["ga4"]
    client.get("/api/accounts?identity=default&source=ga4&refresh=1", headers=h)
    assert calls == ["ga4", "ga4"]


def test_accounts_remove(wizard):
    client, h, cfg = wizard
    r = client.post("/api/accounts/remove", headers=h,
                    json={"source": "gsc", "ids": ["https://a.example/"]})
    assert r.json() == {"removed": ["https://a.example/"]}
    assert "a.example" not in cfg.read_text(encoding="utf-8")


def test_sync_status_reads_progress_file(wizard, tmp_path):
    client, h, cfg = wizard
    from hub.core.progress import SyncProgress
    p = SyncProgress(tmp_path / "logs" / "sync_progress.json")
    p.begin([{"source": "gsc", "account_id": "https://a.example/", "label": "Site A",
              "identity": "default"}])
    r = client.get("/api/sync/status", headers=h).json()
    assert r["in_progress"] is True
    assert r["run"]["accounts"][0]["label"] == "Site A"
    p.finish()
    assert client.get("/api/sync/status", headers=h).json()["in_progress"] is False


def test_claude_detect_and_connect(wizard, monkeypatch, tmp_path):
    client, h, cfg = wizard
    fake = tmp_path / "claude_desktop_config.json"
    fake.write_text("{}", encoding="utf-8")
    monkeypatch.setattr("hub.setup_wizard.claude_config.desktop_config_candidates",
                        lambda: [fake])
    monkeypatch.setattr("hub.setup_wizard.claude_config.cli_available", lambda: False)
    d = client.get("/api/claude/detect", headers=h).json()
    assert d["targets"][0]["label"] == "Claude Desktop"
    assert d["targets"][0]["registered"] is False
    r = client.post("/api/claude/connect", headers=h, json={"target": "desktop:0"}).json()
    assert r["written"] == str(fake)
    assert "marketing-hub" in fake.read_text(encoding="utf-8")
    assert client.get("/api/claude/detect", headers=h).json()["targets"][0]["registered"] is True


def test_state_exposes_client_source_home_and_version(wizard, monkeypatch, tmp_path):
    client, h, cfg = wizard
    monkeypatch.setattr("hub.core.version.latest", lambda: None)
    s = client.get("/api/state", headers=h).json()
    assert s["client_source"] in ("bundled", "own", "missing")
    assert s["home"] == str(tmp_path)
    assert "current" in s["version"]
    assert s["claude_registered"] in (True, False)


def test_version_endpoint_offline(wizard, monkeypatch):
    client, h, _ = wizard
    monkeypatch.setattr("hub.core.version.latest", lambda: None)
    v = client.get("/api/version", headers=h).json()
    assert v["latest"] is None and v["update_available"] is False


def test_schedule_endpoint(wizard, monkeypatch):
    client, h, _ = wizard
    monkeypatch.setattr("hub.core.schedule.install_daily_sync",
                        lambda path, hour=6: {"installed": True, "task_name": "T", "time": "06:00"})
    assert client.post("/api/schedule", headers=h).json()["installed"] is True


def test_static_assets_served(wizard):
    client, _, _ = wizard
    assert client.get("/static/app.js").status_code == 200


def test_shortcut_endpoint(wizard, monkeypatch):
    client, h, _ = wizard
    monkeypatch.setattr("hub.core.shortcut.create_shortcuts",
                        lambda path=None: {"created": ["C:/Desktop/Marketing Data Hub.lnk"]})
    assert client.post("/api/shortcut", headers=h).json()["created"]


def test_requests_touch_last_seen(wizard):
    client, h, _ = wizard
    before = client.app.state.hub["last_seen"]
    import time
    time.sleep(0.01)
    client.get("/api/version", headers=h)
    assert client.app.state.hub["last_seen"] > before


def test_google_disconnect_removes_login_and_its_accounts(wizard, tmp_path):
    from hub.connectors.google_auth import set_identity_label, token_path_for
    from hub.core.accounts import add_accounts
    client, h, cfg = wizard
    secrets = tmp_path / "secrets"
    secrets.mkdir(exist_ok=True)
    token_path_for(secrets, "personal").write_text("{}", encoding="utf-8")
    set_identity_label(secrets, "personal", "p@example.com")
    add_accounts(cfg, "ga4", [{"id": "9", "name": "Nine"}], identity="personal")
    r = client.post("/api/google/disconnect", headers=h, json={"identity": "personal"}).json()
    assert r == {"disconnected": "personal", "removed_accounts": {"ga4": ["9"]}}
    assert not token_path_for(secrets, "personal").exists()
    assert "Nine" not in cfg.read_text(encoding="utf-8")
    # the untouched gsc site from the fixture is still there
    assert "a.example" in cfg.read_text(encoding="utf-8")
