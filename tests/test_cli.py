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
