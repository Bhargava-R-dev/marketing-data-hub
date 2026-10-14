"""Live mode: queries fetch what they need from the APIs, cached briefly."""
import asyncio
from datetime import date, datetime, timedelta

import pytest

from hub.connectors.base import AuthError, BaseConnector, FieldRegistry, FieldSpec
from hub.core import live
from hub.core.config import ConnectorSettings, HubConfig
from hub.core.storage import Storage
from hub.mcp.server import build_mcp

TODAY = date(2026, 10, 14)
NOW = datetime(2026, 10, 14, 12, 0)


class FakeConnector(BaseConnector):
    id = "ga4"
    fields = FieldRegistry(specs=[FieldSpec("clicks", "clicks")])
    calls: list = []
    fail: Exception | None = None

    def authenticate(self):
        if FakeConnector.fail is not None:
            raise FakeConnector.fail

    def extract(self, date_from, date_to):
        FakeConnector.calls.append((date_from, date_to))
        day = date_from
        while day <= date_to:
            yield {"date": day, "account_id": "1", "account_name": "Acme",
                   "clicks": 10, "impressions": 100}
            day += timedelta(days=1)


@pytest.fixture
def cfg(tmp_path, monkeypatch):
    FakeConnector.calls = []
    FakeConnector.fail = None
    monkeypatch.setattr(live, "build_connector",
                        lambda source, config: FakeConnector(
                            config.connectors[source], config.secrets_dir))
    return HubConfig(db_path=str(tmp_path / "hub.duckdb"),
                     secrets_dir=str(tmp_path / "secrets"),
                     connectors={"ga4": ConnectorSettings()})


def test_ttl_is_shorter_for_recent_days():
    assert live.ttl_for(0) < live.ttl_for(5) < live.ttl_for(20) < live.ttl_for(200)


def test_first_query_fetches_then_second_is_served_from_cache(cfg):
    a, b = TODAY - timedelta(days=9), TODAY - timedelta(days=3)
    live.ensure_fresh(cfg, ["ga4"], "core", a, b)
    assert FakeConnector.calls == [(a, b)]
    live.ensure_fresh(cfg, ["ga4"], "core", a, b)
    assert FakeConnector.calls == [(a, b)]  # fresh: no second API call


def test_only_the_missing_edge_is_fetched(cfg):
    a, b = date.today() - timedelta(days=40), date.today() - timedelta(days=20)
    live.ensure_fresh(cfg, ["ga4"], "core", a, b)
    FakeConnector.calls.clear()
    live.ensure_fresh(cfg, ["ga4"], "core", a, b + timedelta(days=5))
    assert FakeConnector.calls == [(b + timedelta(days=1), b + timedelta(days=5))]


def test_stale_days_are_refetched(cfg):
    st = Storage(cfg.db_path)
    day = TODAY - timedelta(days=2)
    st.mark_fetched("ga4", "core", day, day, when=NOW - timedelta(hours=3))
    ranges = live.stale_ranges(st, "ga4", "core", day, day, now=NOW, today=TODAY)
    assert ranges == [(day, day)]  # 2 days old => 1h freshness, fetched 3h ago
    st.mark_fetched("ga4", "core", day, day, when=NOW - timedelta(minutes=10))
    assert live.stale_ranges(st, "ga4", "core", day, day, now=NOW, today=TODAY) == []
    st.close()


def test_future_days_are_never_fetched(cfg):
    st = Storage(cfg.db_path)
    assert live.stale_ranges(st, "ga4", "core", TODAY + timedelta(days=1),
                             TODAY + timedelta(days=5), now=NOW, today=TODAY) == []
    st.close()


def test_old_pre_live_history_is_trusted_not_refetched(cfg):
    """Rows synced before live mode (no fetch record) must survive: the API
    may no longer be able to return them (GSC keeps ~16 months)."""
    from hub.core.models import UnifiedRow

    st = Storage(cfg.db_path)
    old = TODAY - timedelta(days=400)
    st.replace_rows("ga4", old, old, [UnifiedRow(
        date=old, source="ga4", account_id="1", account_name="Acme", clicks=5)])
    assert live.stale_ranges(st, "ga4", "core", old, old, now=NOW, today=TODAY) == []
    recent = TODAY - timedelta(days=3)
    assert live.stale_ranges(st, "ga4", "core", recent, recent,
                             now=NOW, today=TODAY) == [(recent, recent)]
    st.close()


def test_long_ranges_are_chunked_to_90_days(cfg):
    st = Storage(cfg.db_path)
    ranges = live.stale_ranges(st, "ga4", "core", TODAY - timedelta(days=200),
                               TODAY, now=NOW, today=TODAY)
    assert all((b - a).days + 1 <= 90 for a, b in ranges)
    assert ranges[0][0] == TODAY - timedelta(days=200) and ranges[-1][1] == TODAY
    st.close()


def test_stored_mode_never_calls_the_api(cfg):
    cfg.mode = "stored"
    result = live.ensure_fresh(cfg, ["ga4"], "core", TODAY - timedelta(days=5), TODAY)
    assert result.ok and FakeConnector.calls == []


def test_auth_failure_is_reported_not_raised(cfg):
    FakeConnector.fail = AuthError("Google login expired", hint="Run 'hub login'.")
    result = live.ensure_fresh(cfg, ["ga4"], "core", TODAY - timedelta(days=5), TODAY)
    assert "expired" in result.errors["ga4"] and "hub login" in result.errors["ga4"]
    assert "COULD NOT REFRESH" in live.describe(result)["warning"]


def test_unattended_flag_is_set_during_fetch_and_restored(cfg, monkeypatch):
    import os

    seen = []
    monkeypatch.setattr(FakeConnector, "authenticate",
                        lambda self: seen.append(os.environ.get("HUB_UNATTENDED")))
    monkeypatch.delenv("HUB_UNATTENDED", raising=False)
    live.ensure_fresh(cfg, ["ga4"], "core", TODAY - timedelta(days=5), TODAY)
    assert seen == ["1"] and "HUB_UNATTENDED" not in os.environ


def test_prune_evicts_only_cache_fetched_days(cfg):
    st = Storage(cfg.db_path)
    old = date.today() - timedelta(days=100)
    live_day = date.today() - timedelta(days=90)
    from hub.core.models import UnifiedRow

    for d in (old, live_day):
        st.replace_rows("ga4", d, d, [UnifiedRow(
            date=d, source="ga4", account_id="1", account_name="A", clicks=1)])
    st.mark_fetched("ga4", "core", live_day, live_day,
                    when=datetime.now() - timedelta(days=60))
    assert st.prune_cache(45) == 1
    assert st.days_with_rows("ga4", "core", old, live_day) == {old}  # legacy kept
    st.close()


def test_mcp_query_fetches_live_and_reports_refresh_failure(cfg, tmp_path, monkeypatch):
    (tmp_path / "config.yaml").write_text("connectors: {}\n")
    # build_mcp reloads config.yaml per call; hand it our in-memory config
    monkeypatch.setattr("hub.mcp.server.load_config", lambda path: cfg)
    mcp = build_mcp(cfg, config_path=str(tmp_path / "config.yaml"))
    ok = asyncio.run(mcp._call_query_metrics(
        fields=["clicks"], date_from=(date.today() - timedelta(days=4)).isoformat(),
        date_to=(date.today() - timedelta(days=2)).isoformat()))
    assert ok["rows"][0]["clicks"] == 30
    assert ok["live"]["fetched_days"] == 3

    FakeConnector.fail = AuthError("Google login expired", hint="Run 'hub login'.")
    stale = asyncio.run(mcp._call_query_metrics(
        fields=["clicks"], date_from=(date.today() - timedelta(days=1)).isoformat(),
        date_to=date.today().isoformat()))
    assert "COULD NOT REFRESH" in stale["warning"]


def test_cache_commands_work_on_a_fresh_home(tmp_path):
    from typer.testing import CliRunner

    from hub.cli import app

    cfg = tmp_path / "config.yaml"
    cfg.write_text("connectors: {}\n")
    runner = CliRunner()
    status = runner.invoke(app, ["cache", "status", "--config", str(cfg)])
    assert status.exit_code == 0 and "mode: live" in status.output
    cleared = runner.invoke(app, ["cache", "clear", "--config", str(cfg)])
    assert cleared.exit_code == 0 and "cleared 0" in cleared.output
