from pathlib import Path

from hub.core.config import HubConfig, load_config


def test_load_config(tmp_path: Path):
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text(
        """
db_path: data/hub.duckdb
connectors:
  ga4:
    window_days: 14
    options:
      property_id: "123"
exports:
  - name: overview
    fields: [date, clicks]
    date_preset: last_7d
""",
        encoding="utf-8",
    )
    cfg = load_config(cfg_file)
    assert isinstance(cfg, HubConfig)
    # relative db_path resolved against the config file's directory
    assert cfg.db_path == str((tmp_path / "data" / "hub.duckdb").resolve())
    assert cfg.connectors["ga4"].window_days == 14
    assert cfg.connectors["ga4"].schedule == "0 6 * * *"  # default
    assert cfg.connectors["ga4"].options["property_id"] == "123"
    assert cfg.exports[0].name == "overview"
    assert cfg.exports[0].date_preset == "last_7d"


def test_defaults_when_sections_missing(tmp_path: Path):
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text("db_path: x.duckdb\n", encoding="utf-8")
    cfg = load_config(cfg_file)
    assert cfg.connectors == {}
    assert cfg.exports == []
    # relative defaults resolved against the config file's directory
    assert cfg.secrets_dir == str((tmp_path / "secrets").resolve())
    assert cfg.exports_dir == str((tmp_path / "exports").resolve())


def test_unknown_key_fails_loudly(tmp_path: Path):
    import pytest
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text("db_path: x.duckdb\nconnectors:\n  ga4:\n    windw_days: 14\n",
                        encoding="utf-8")
    with pytest.raises(Exception, match="windw_days"):
        load_config(cfg_file)


def test_missing_file_message_is_actionable(tmp_path: Path):
    import pytest
    with pytest.raises(FileNotFoundError, match="config.yaml.example"):
        load_config(tmp_path / "nope.yaml")


def test_relative_paths_resolved_against_config_dir(tmp_path):
    from hub.core.config import load_config
    cfgfile = tmp_path / "sub" / "config.yaml"
    cfgfile.parent.mkdir()
    cfgfile.write_text("db_path: data/hub.duckdb\nsecrets_dir: secrets\n"
                       "exports_dir: exports\n", encoding="utf-8")
    cfg = load_config(cfgfile)
    assert cfg.db_path == str((tmp_path / "sub" / "data" / "hub.duckdb").resolve())
    assert cfg.secrets_dir == str((tmp_path / "sub" / "secrets").resolve())
    # portable regardless of cwd
    assert Path(cfg.db_path).is_absolute()


def test_absolute_paths_left_untouched(tmp_path):
    from hub.core.config import load_config
    abs_db = (tmp_path / "elsewhere" / "x.duckdb").resolve()
    cfgfile = tmp_path / "config.yaml"
    cfgfile.write_text(f"db_path: {abs_db.as_posix()}\n", encoding="utf-8")
    cfg = load_config(cfgfile)
    assert Path(cfg.db_path) == abs_db
