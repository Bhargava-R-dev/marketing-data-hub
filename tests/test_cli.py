from pathlib import Path

from typer.testing import CliRunner

from hub.cli import app

runner = CliRunner()


def write_config(tmp_path: Path) -> Path:
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        f"db_path: {(tmp_path / 'hub.duckdb').as_posix()}\n"
        f"secrets_dir: {(tmp_path / 'secrets').as_posix()}\n"
        f"exports_dir: {(tmp_path / 'exports').as_posix()}\n"
        "connectors: {}\n",
        encoding="utf-8")
    return cfg


def test_status_on_empty_db(tmp_path):
    cfg = write_config(tmp_path)
    result = runner.invoke(app, ["status", "--config", str(cfg)])
    assert result.exit_code == 0
    assert "ga4" in result.output
    assert "inactive" in result.output


def test_doctor_with_no_connectors(tmp_path):
    cfg = write_config(tmp_path)
    result = runner.invoke(app, ["doctor", "--config", str(cfg)])
    assert result.exit_code == 0
    assert "No connectors configured" in result.output


def test_sync_unconfigured_source_fails_cleanly(tmp_path):
    cfg = write_config(tmp_path)
    result = runner.invoke(app, ["sync", "ga4", "--config", str(cfg)])
    assert result.exit_code == 1
    assert "not configured" in result.output


def test_backfill_bad_date_fails_cleanly(tmp_path):
    cfg = write_config(tmp_path)
    result = runner.invoke(app, ["backfill", "ga4", "--config", str(cfg),
                                 "--from", "07/01/2024"])
    assert result.exit_code == 1
    assert "YYYY-MM-DD" in result.output


def test_backfill_unconfigured_source_fails_cleanly(tmp_path):
    cfg = write_config(tmp_path)
    result = runner.invoke(app, ["backfill", "ga4", "--config", str(cfg),
                                 "--from", "2024-01-01"])
    assert result.exit_code == 1
    assert "not configured" in result.output


def test_setup_warns_loudly_when_creating_a_new_hub(tmp_path, monkeypatch):
    """A missing config.yaml means 'hub setup' scaffolds a fresh project - this
    must be impossible to miss, since running it from the wrong directory
    silently starting an empty second hub is exactly what happened in
    practice (a stray config.yaml appeared in a home directory)."""
    monkeypatch.setattr("hub.setup_wizard.run_setup", lambda *a, **k: None)
    cfg_path = tmp_path / "config.yaml"
    assert not cfg_path.exists()
    result = runner.invoke(app, ["setup", "--config", str(cfg_path), "--no-browser"])
    assert result.exit_code == 0
    assert "NEW HUB" in result.output
    assert str(cfg_path.resolve()) in result.output
    assert "Ctrl+C" in result.output
    assert cfg_path.exists()


def test_setup_stays_quiet_when_config_already_exists(tmp_path, monkeypatch):
    monkeypatch.setattr("hub.setup_wizard.run_setup", lambda *a, **k: None)
    cfg_path = write_config(tmp_path)
    result = runner.invoke(app, ["setup", "--config", str(cfg_path), "--no-browser"])
    assert result.exit_code == 0
    assert "NEW HUB" not in result.output


# ---- hub gaps: per-account holes a source-wide date range can't reveal ---


def test_gaps_reports_missing_days_per_account(tmp_path):
    from datetime import date

    from hub.core.models import UnifiedRow
    from hub.core.storage import Storage

    cfg = write_config(tmp_path)
    from hub.core.config import load_config
    store = Storage(load_config(cfg).db_path)
    store.replace_rows("gsc", date(2026, 5, 1), date(2026, 5, 3), [
        UnifiedRow(date=date(2026, 5, 1), source="gsc", account_id="x",
                   account_name="Vetrotech", clicks=1)])
    store.replace_rows("gsc", date(2026, 5, 3), date(2026, 5, 3), [
        UnifiedRow(date=date(2026, 5, 3), source="gsc", account_id="x",
                   account_name="Vetrotech", clicks=1)])
    store.close()

    result = runner.invoke(app, ["gaps", "--config", str(cfg)])
    assert result.exit_code == 0
    assert "[GAP]" in result.output
    assert "Vetrotech" in result.output
    assert "2026-05-02" in result.output


def test_gaps_reports_ok_when_nothing_missing(tmp_path):
    from datetime import date

    from hub.core.models import UnifiedRow
    from hub.core.storage import Storage

    cfg = write_config(tmp_path)
    from hub.core.config import load_config
    store = Storage(load_config(cfg).db_path)
    d = date(2026, 5, 1)
    store.replace_rows("gsc", d, d, [
        UnifiedRow(date=d, source="gsc", account_id="x", account_name="Vetrotech",
                   clicks=1)])
    store.close()

    result = runner.invoke(app, ["gaps", "--config", str(cfg)])
    assert result.exit_code == 0
    assert "[OK] no gaps found" in result.output


def test_gaps_filters_to_one_source(tmp_path):
    from datetime import date

    from hub.core.models import UnifiedRow
    from hub.core.storage import Storage

    cfg = write_config(tmp_path)
    from hub.core.config import load_config
    store = Storage(load_config(cfg).db_path)
    store.replace_rows("gsc", date(2026, 5, 1), date(2026, 5, 3), [
        UnifiedRow(date=date(2026, 5, 1), source="gsc", account_id="x",
                   account_name="Vetrotech", clicks=1)])
    store.close()

    result = runner.invoke(app, ["gaps", "ga4", "--config", str(cfg)])
    assert "[OK] no gaps found for ga4" in result.output


# ---- hub backup: cheap insurance for a multi-year, multi-GB database -----


def test_backup_copies_db_to_timestamped_file(tmp_path):
    from hub.core.storage import Storage

    cfg = write_config(tmp_path)
    from hub.core.config import load_config
    db_path = Path(load_config(cfg).db_path)
    Storage(str(db_path)).close()  # create the db file

    result = runner.invoke(app, ["backup", "--config", str(cfg),
                                "--out", str(tmp_path / "backups")])
    assert result.exit_code == 0
    assert "[OK]" in result.output
    backups = list((tmp_path / "backups").glob("*.duckdb"))
    assert len(backups) == 1
    assert backups[0].read_bytes() == db_path.read_bytes()


def test_backup_fails_cleanly_when_db_missing(tmp_path):
    cfg = tmp_path / "config.yaml"
    cfg.write_text(f"db_path: {(tmp_path / 'nope.duckdb').as_posix()}\n"
                  "connectors: {}\n", encoding="utf-8")
    result = runner.invoke(app, ["backup", "--config", str(cfg)])
    assert result.exit_code == 1
    assert "no database found" in result.output


def test_backup_refuses_while_a_sync_holds_the_write_lock(tmp_path):
    from hub.core.storage import Storage

    cfg = write_config(tmp_path)
    from hub.core.config import load_config
    store = Storage(load_config(cfg).db_path)  # writer, not closed - holds the lock
    try:
        result = runner.invoke(app, ["backup", "--config", str(cfg)])
        assert result.exit_code == 1
        assert "busy" in result.output
    finally:
        store.close()


def test_backup_default_location_is_alongside_the_db(tmp_path):
    from hub.core.storage import Storage

    cfg = write_config(tmp_path)
    from hub.core.config import load_config
    db_path = Path(load_config(cfg).db_path)
    Storage(str(db_path)).close()

    result = runner.invoke(app, ["backup", "--config", str(cfg)])
    assert result.exit_code == 0
    assert (db_path.parent / "backups").exists()
    assert list((db_path.parent / "backups").glob("*.duckdb"))
