from datetime import date

import pytest

from hub.core.storage import Storage
from hub.core.sync import backfill_chunks, run_sync
from hub.connectors.base import BaseConnector, FieldRegistry, FieldSpec
from hub.core.config import ConnectorSettings


class FakeConnector(BaseConnector):
    id = "fake"
    fields = FieldRegistry([FieldSpec("date", "date", dimension=True),
                            FieldSpec("clicks", "clicks")])

    def __init__(self, fail_times: int = 0):
        super().__init__(ConnectorSettings(), ".")
        self.fail_times = fail_times
        self.calls = 0

    def authenticate(self):
        pass

    def extract(self, date_from, date_to):
        self.calls += 1
        if self.calls <= self.fail_times:
            raise RuntimeError("api down")
        return [{"date": date_from.isoformat(), "account_id": "a", "clicks": 5}]


class AuthFailConnector(FakeConnector):
    def authenticate(self):
        from hub.connectors.base import AuthError
        raise AuthError("token revoked", hint="delete secrets/google_token.json")


@pytest.fixture()
def store(tmp_path):
    return Storage(str(tmp_path / "t.duckdb"))


def test_run_sync_happy_path(store):
    run_sync(store, FakeConnector(), date_from=date(2026, 7, 1), date_to=date(2026, 7, 1))
    assert store.row_counts()["fake"]["rows"] == 1
    assert store.last_runs()["fake"]["status"] == "success"


def test_run_sync_retries_then_succeeds(store, monkeypatch):
    monkeypatch.setattr("hub.core.sync.time.sleep", lambda s: None)
    conn = FakeConnector(fail_times=2)
    run_sync(store, conn, date_from=date(2026, 7, 1), date_to=date(2026, 7, 1))
    assert conn.calls == 3
    assert store.last_runs()["fake"]["status"] == "success"


def test_run_sync_records_error_after_retries(store, monkeypatch):
    monkeypatch.setattr("hub.core.sync.time.sleep", lambda s: None)
    with pytest.raises(RuntimeError):
        run_sync(store, FakeConnector(fail_times=99),
                 date_from=date(2026, 7, 1), date_to=date(2026, 7, 1))
    run = store.last_runs()["fake"]
    assert run["status"] == "error"
    assert "api down" in run["error_message"]


def test_auth_error_fails_fast_with_hint(store, monkeypatch):
    sleeps = []
    monkeypatch.setattr("hub.core.sync.time.sleep", lambda s: sleeps.append(s))
    from hub.connectors.base import AuthError
    conn = AuthFailConnector()
    with pytest.raises(AuthError):
        run_sync(store, conn, date_from=date(2026, 7, 1), date_to=date(2026, 7, 1))
    assert sleeps == []  # no retries, no backoff
    run = store.last_runs()["fake"]
    assert run["status"] == "error"
    assert "google_token.json" in run["error_message"]  # hint preserved


def test_default_window_is_rolling(store):
    conn = FakeConnector()
    run_sync(store, conn, window_days=30)
    run = store.last_runs()["fake"]
    assert (run["finished_at"] is not None)
    assert (date.today() - store.query(["date"], date(2000, 1, 1), date.today())[0]["date"]).days <= 30


def test_backfill_chunks():
    chunks = backfill_chunks(date(2024, 1, 1), date(2024, 6, 30), chunk_days=90)
    assert chunks[0] == (date(2024, 1, 1), date(2024, 3, 30))
    assert chunks[-1][1] == date(2024, 6, 30)
    # chunks cover the range with no gaps/overlaps
    for (a, b), (c, d) in zip(chunks, chunks[1:]):
        assert (c - b).days == 1
