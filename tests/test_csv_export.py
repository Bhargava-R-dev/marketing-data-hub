from datetime import date
from pathlib import Path

from hub.core.config import ExportConfig
from hub.core.models import UnifiedRow
from hub.core.storage import Storage
from hub.destinations.csv_export import run_export


def test_run_export_writes_csv(tmp_path: Path):
    store = Storage(str(tmp_path / "t.duckdb"))
    d = date.today()
    store.replace_rows("ga4", d, d, [
        UnifiedRow(date=d, source="ga4", account_id="p1", clicks=7, spend=1.5)])
    cfg = ExportConfig(name="overview", fields=["date", "source", "clicks", "spend"],
                       date_preset="last_7d")
    out = run_export(store, cfg, exports_dir=tmp_path / "exports")
    assert out == tmp_path / "exports" / "overview.csv"
    lines = out.read_text(encoding="utf-8").strip().splitlines()
    assert lines[0] == "date,source,clicks,spend"
    assert lines[1].endswith("ga4,7,1.5")


def test_export_respects_source_filter(tmp_path: Path):
    store = Storage(str(tmp_path / "t.duckdb"))
    d = date.today()
    store.replace_rows("ga4", d, d, [UnifiedRow(date=d, source="ga4", account_id="a", clicks=1)])
    store.replace_rows("gsc", d, d, [UnifiedRow(date=d, source="gsc", account_id="b", clicks=2)])
    cfg = ExportConfig(name="gsc_only", fields=["date", "clicks"],
                       sources=["gsc"], date_preset="last_7d")
    out = run_export(store, cfg, exports_dir=tmp_path)
    assert out.read_text(encoding="utf-8").strip().splitlines()[1].endswith(",2")
