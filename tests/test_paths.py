from pathlib import Path

from hub.core import paths


def test_default_home_uses_env_override(monkeypatch, tmp_path):
    monkeypatch.setenv("HUB_HOME", str(tmp_path / "custom"))
    assert paths.default_home() == (tmp_path / "custom").resolve()


def test_default_home_windows_localappdata(monkeypatch, tmp_path):
    monkeypatch.delenv("HUB_HOME", raising=False)
    monkeypatch.setattr(paths.sys, "platform", "win32")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    assert paths.default_home() == (tmp_path / "MarketingDataHub").resolve()


def test_default_home_posix(monkeypatch, tmp_path):
    monkeypatch.delenv("HUB_HOME", raising=False)
    monkeypatch.setattr(paths.sys, "platform", "darwin")
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
    assert paths.default_home() == (tmp_path / ".marketing-data-hub").resolve()


def test_resolve_config_explicit_wins(tmp_path):
    p = tmp_path / "x.yaml"
    assert paths.resolve_config_path(str(p)) == p.resolve()


def test_resolve_config_prefers_cwd_config(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "config.yaml").write_text("connectors: {}\n", encoding="utf-8")
    monkeypatch.setenv("HUB_HOME", str(tmp_path / "home"))
    assert paths.resolve_config_path(None) == (tmp_path / "config.yaml").resolve()


def test_resolve_config_falls_back_to_home(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HUB_HOME", str(tmp_path / "home"))
    assert paths.resolve_config_path(None) == (tmp_path / "home" / "config.yaml").resolve()


def test_ensure_home_scaffolds_folders_and_config(tmp_path):
    home = tmp_path / "home"
    cfg = paths.ensure_home(home)
    assert cfg == home / "config.yaml"
    for sub in ("data", "secrets", "logs", "exports"):
        assert (home / sub).is_dir()
    assert "connectors: {}" in cfg.read_text(encoding="utf-8")
    cfg.write_text("db_path: data/keep.duckdb\nconnectors: {}\n", encoding="utf-8")
    paths.ensure_home(home)
    assert "keep.duckdb" in cfg.read_text(encoding="utf-8")
