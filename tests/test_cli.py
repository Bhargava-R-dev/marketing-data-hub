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
