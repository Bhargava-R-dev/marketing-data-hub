import json
import sys

from hub.setup_wizard import claude_config as cc


def test_mcp_command_pip(monkeypatch, tmp_path):
    monkeypatch.delattr(sys, "frozen", raising=False)
    cmd, args = cc.mcp_command(tmp_path / "config.yaml")
    assert cmd == sys.executable
    assert args == ["-m", "hub.cli", "mcp", "--config", str(tmp_path / "config.yaml")]


def test_mcp_command_frozen(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", r"C:\Apps\hub.exe")
    cmd, args = cc.mcp_command(tmp_path / "config.yaml")
    assert cmd == r"C:\Apps\hub.exe"
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


def test_is_registered(tmp_path):
    cfg = tmp_path / "c.json"
    assert cc.is_registered(cfg) is False
    cc.write_mcp_entry(cfg, "python", ["mcp"])
    assert cc.is_registered(cfg) is True


def test_detect_lists_targets(monkeypatch, tmp_path):
    fake = tmp_path / "claude_desktop_config.json"
    fake.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(cc, "desktop_config_candidates", lambda: [fake])
    monkeypatch.setattr(cc, "cli_available", lambda: True)
    d = cc.detect(tmp_path / "config.yaml")
    assert [t["id"] for t in d["targets"]] == ["desktop:0", "cli"]
    assert "marketing-hub" in d["snippet"]
