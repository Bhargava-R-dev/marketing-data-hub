from datetime import date

import pytest

from hub.core.models import UnifiedRow
from hub.core.storage import Storage


@pytest.fixture()
def store(tmp_path):
    return Storage(str(tmp_path / "test.duckdb"))


def rows_for(source, day, clicks, extras=None):
    return [UnifiedRow(date=day, source=source, account_id="a1", account_name="Acct",
                       clicks=clicks, impressions=clicks * 10, extras=extras or {})]


def test_replace_rows_is_idempotent(store):
    d = date(2026, 7, 1)
    assert store.replace_rows("ga4", d, d, rows_for("ga4", d, 5)) == 1
    assert store.replace_rows("ga4", d, d, rows_for("ga4", d, 7)) == 1  # replaces
    out = store.query(["date", "clicks"], d, d)
    assert out == [{"date": d, "clicks": 7}]


def test_replace_rows_scoped_to_source(store):
    d = date(2026, 7, 1)
    store.replace_rows("ga4", d, d, rows_for("ga4", d, 5))
    store.replace_rows("gsc", d, d, rows_for("gsc", d, 3))
    store.replace_rows("ga4", d, d, rows_for("ga4", d, 9))
    out = store.query(["source", "clicks"], d, d)
    assert sorted(out, key=lambda r: r["source"]) == [
        {"source": "ga4", "clicks": 9}, {"source": "gsc", "clicks": 3}]


def test_query_aggregates_metrics_over_dims(store):
    d1, d2 = date(2026, 7, 1), date(2026, 7, 2)
    store.replace_rows("ga4", d1, d2, rows_for("ga4", d1, 5) + rows_for("ga4", d2, 2))
    store.replace_rows("gsc", d1, d2, rows_for("gsc", d1, 3))
    out = store.query(["date", "clicks"], d1, d2)
    assert out == [{"date": d1, "clicks": 8}, {"date": d2, "clicks": 2}]


def test_query_extras_and_filters(store):
    d = date(2026, 7, 1)
    store.replace_rows("gsc", d, d, rows_for("gsc", d, 3, extras={"position": 12.5}))
    out = store.query(["date", "position", "clicks"], d, d, sources=["gsc"])
    assert out == [{"date": d, "position": "12.5", "clicks": 3}]  # extras come back as strings
    out = store.query(["date", "clicks"], d, d, filters={"account_id": "nope"})
    assert out == []


def test_query_rejects_bad_field_names(store):
    with pytest.raises(ValueError):
        store.query(["date; DROP TABLE metrics"], date(2026, 7, 1), date(2026, 7, 1))


def test_sync_run_lifecycle(store):
    run_id = store.start_sync("ga4", date(2026, 6, 1), date(2026, 7, 1))
    store.finish_sync(run_id, rows=10, status="success")
    runs = store.last_runs()
    assert runs["ga4"]["status"] == "success"
    assert runs["ga4"]["rows_written"] == 10


def test_status_counts(store):
    d = date(2026, 7, 1)
    store.replace_rows("ga4", d, d, rows_for("ga4", d, 5))
    counts = store.row_counts()
    assert counts["ga4"]["rows"] == 1
    assert counts["ga4"]["latest_date"] == d


def test_concurrent_replace_rows_is_serialized(store):
    import threading
    from datetime import date as d
    errors = []

    def writer(source, n):
        try:
            for i in range(20):
                store.replace_rows(source, d(2026, 7, 1), d(2026, 7, 1),
                                   rows_for(source, d(2026, 7, 1), i))
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=writer, args=(f"src{k}", k)) for k in range(4)]
    for t in threads: t.start()
    for t in threads: t.join()
    assert errors == []
    # connection still healthy afterwards
    assert len(store.row_counts()) == 4
