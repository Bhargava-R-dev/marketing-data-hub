import sys

from hub.core import shortcut
from hub.core.paths import python_exe


def test_python_exe_maps_pythonw_to_python(monkeypatch):
    monkeypatch.setattr(sys, "executable", r"C:\Py\pythonw.exe")
    assert python_exe() == r"C:\Py\python.exe"
    monkeypatch.setattr(sys, "executable", r"C:\Py\python.exe")
    assert python_exe() == r"C:\Py\python.exe"


def test_launcher_uses_pythonw_for_pip(monkeypatch, tmp_path):
    monkeypatch.delattr(sys, "frozen", raising=False)
    monkeypatch.setattr(sys, "executable", r"C:\Py\python.exe")
    target, args = shortcut.launcher_command(tmp_path / "config.yaml")
    assert target == r"C:\Py\pythonw.exe"
    assert args == f'-m hub.cli setup --config "{tmp_path / "config.yaml"}"'


def test_launcher_frozen(monkeypatch):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", r"C:\Apps\hub.exe")
    assert shortcut.launcher_command() == (r"C:\Apps\hub.exe", "setup")


def test_create_shortcuts_windows_writes_both(monkeypatch, tmp_path):
    monkeypatch.setattr(shortcut.sys, "platform", "win32")
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setenv("APPDATA", str(tmp_path / "AppData" / "Roaming"))
    calls = []

    def fake_run(cmd, **kw):
        calls.append(cmd[-1])

        class R:
            returncode = 0
            stderr = ""
        return R()
    monkeypatch.setattr(shortcut.subprocess, "run", fake_run)
    result = shortcut.create_shortcuts(tmp_path / "config.yaml")
    assert len(result["created"]) == 2
    assert any("Desktop" in c for c in calls) and any("Start Menu" in c for c in calls)
    assert all("hub.ico" in c for c in calls)


def test_create_shortcuts_posix_gives_hint(monkeypatch):
    monkeypatch.setattr(shortcut.sys, "platform", "darwin")
    assert shortcut.create_shortcuts()["created"] == []


def test_launcher_frozen_prefers_gui_exe(monkeypatch, tmp_path):
    (tmp_path / "MarketingDataHub.exe").write_bytes(b"")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(tmp_path / "hub.exe"))
    assert shortcut.launcher_command() == (str(tmp_path / "MarketingDataHub.exe"), "")
