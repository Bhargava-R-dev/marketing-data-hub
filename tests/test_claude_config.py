import json
import os
import sys

import pytest

from hub.setup_wizard import claude_config as cc


def test_mcp_command_pip(monkeypatch, tmp_path):
    monkeypatch.delattr(sys, "frozen", raising=False)
    cmd, args = cc.mcp_command(tmp_path / "config.yaml")
    assert cmd == sys.executable
    assert args == ["-m", "hub.cli", "mcp", "--config", str(tmp_path / "config.yaml")]


def test_mcp_command_frozen(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    cli = tmp_path / "hub.exe"
    cli.touch()
    monkeypatch.setattr(sys, "executable", str(cli))
    cmd, args = cc.mcp_command(tmp_path / "config.yaml")
    assert cmd == str(cli)
    assert args == ["mcp", "--config", str(tmp_path / "config.yaml")]


def test_desktop_candidates_windows(monkeypatch, tmp_path):
    monkeypatch.setattr(cc.sys, "platform", "win32")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    monkeypatch.setenv("APPDATA", str(tmp_path / "roaming"))
    store = tmp_path / "local" / "Packages" / "Claude_abc123" / "LocalCache" / "Roaming" / "Claude"
    store.mkdir(parents=True)
    (store / "claude_desktop_config.json").write_text("{}", encoding="utf-8")
    classic = tmp_path / "roaming" / "Claude"
    classic.mkdir(parents=True)
    (classic / "claude_desktop_config.json").write_text("{}", encoding="utf-8")
    found = cc.desktop_config_candidates()
    assert store / "claude_desktop_config.json" in found
    assert classic / "claude_desktop_config.json" in found


def test_write_entry_merges_and_backs_up(tmp_path):
    cfg = tmp_path / "claude_desktop_config.json"
    cfg.write_text(json.dumps({"mcpServers": {"other": {"command": "x"}}, "theme": "dark"}),
                   encoding="utf-8")
    written = cc.write_mcp_entry(cfg, "python", ["-m", "hub.cli", "mcp"])
    data = json.loads(cfg.read_text(encoding="utf-8"))
    assert data["theme"] == "dark"
    assert data["mcpServers"]["other"] == {"command": "x"}
    assert data["mcpServers"]["marketing-hub"] == {"command": "python",
                                                   "args": ["-m", "hub.cli", "mcp"]}
    assert written == cfg
    assert list(tmp_path.glob("claude_desktop_config.json.bak-*"))


def test_write_entry_creates_file_when_missing(tmp_path):
    cfg = tmp_path / "Claude" / "claude_desktop_config.json"
    cc.write_mcp_entry(cfg, "python", ["mcp"])
    assert json.loads(cfg.read_text(encoding="utf-8"))["mcpServers"]["marketing-hub"]["args"] == ["mcp"]


def test_invalid_config_is_not_overwritten(tmp_path):
    cfg = tmp_path / "claude.json"
    cfg.write_text("{broken", encoding="utf-8")
    with pytest.raises(ValueError, match="Invalid JSON"):
        cc.write_mcp_entry(cfg, "hub.exe", ["mcp"])
    assert cfg.read_text(encoding="utf-8") == "{broken"


@pytest.mark.parametrize("content", ["[]", "null", '{"mcpServers": []}'])
def test_wrong_config_shape_is_not_overwritten(tmp_path, content):
    cfg = tmp_path / "claude.json"
    cfg.write_text(content, encoding="utf-8")
    assert cc.is_registered(cfg) is False
    with pytest.raises(ValueError):
        cc.write_mcp_entry(cfg, "hub.exe", ["mcp"])
    assert cfg.read_text(encoding="utf-8") == content


def test_stale_command_is_not_reported_connected(tmp_path, monkeypatch):
    cfg = tmp_path / "claude.json"
    hub = tmp_path / "config.yaml"
    cc.write_mcp_entry(cfg, "missing-python", ["-m", "hub.cli", "mcp", "--config", str(hub)])
    monkeypatch.setattr(cc, "desktop_config_candidates", lambda: [cfg])
    assert cc.detect(hub)["targets"][0]["registered"] is False
    cc.write_mcp_entry(cfg, *cc.mcp_command(hub))
    assert cc.detect(hub)["targets"][0]["registered"] is True


def test_code_repair_replaces_only_hub_entry(tmp_path, monkeypatch):
    cfg = tmp_path / ".claude.json"
    cfg.write_text(json.dumps({"mcpServers": {"other": {"command": "keep"},
                                              "marketing-hub": {"command": "old"}}}), encoding="utf-8")
    monkeypatch.setattr(cc, "code_config_path", lambda: cfg)
    cc.register_with_cli("hub.exe", ["mcp"])
    servers = json.loads(cfg.read_text(encoding="utf-8"))["mcpServers"]
    assert servers["other"]["command"] == "keep"
    assert servers["marketing-hub"]["command"] == "hub.exe"


def test_is_registered(tmp_path):
    cfg = tmp_path / "c.json"
    assert cc.is_registered(cfg) is False
    cc.write_mcp_entry(cfg, "python", ["mcp", "--config", str(tmp_path / "a.yaml")])
    assert cc.is_registered(cfg) is True
    assert cc.is_registered(cfg, tmp_path / "a.yaml") is True
    # an entry for a different hub on the same machine does not count
    assert cc.is_registered(cfg, tmp_path / "other.yaml") is False


def test_detect_lists_targets(monkeypatch, tmp_path):
    fake = tmp_path / "claude_desktop_config.json"
    fake.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(cc, "desktop_config_candidates", lambda: [fake])
    monkeypatch.setattr(cc, "cli_available", lambda: True)
    d = cc.detect(tmp_path / "config.yaml")
    assert [t["id"] for t in d["targets"]] == ["desktop:0", "cli"]
    assert "marketing-hub" in d["snippet"]


def test_desktop_candidates_dedupes_same_file(monkeypatch, tmp_path):
    monkeypatch.setattr(cc.sys, "platform", "win32")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    monkeypatch.setenv("APPDATA", str(tmp_path / "roaming"))
    real = tmp_path / "local" / "Packages" / "Claude_x" / "LocalCache" / "Roaming" / "Claude"
    real.mkdir(parents=True)
    (real / "claude_desktop_config.json").write_text("{}", encoding="utf-8")
    (tmp_path / "roaming").mkdir()
    # %APPDATA%\Claude is a junction/symlink to the Store folder on some machines
    try:
        os.symlink(real, tmp_path / "roaming" / "Claude", target_is_directory=True)
    except OSError:
        pytest.skip("symlinks need privileges on this machine")
    assert len(cc.desktop_config_candidates()) == 1
