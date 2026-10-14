import sys

from hub.core import schedule


def test_sync_command_pip(monkeypatch, tmp_path):
    monkeypatch.delattr(sys, "frozen", raising=False)
    exe, args = schedule.sync_command(tmp_path / "config.yaml")
    assert exe == sys.executable
    assert args == ["-m", "hub.cli", "sync", "all", "--unattended",
                    "--config", str(tmp_path / "config.yaml")]


def test_install_windows_calls_powershell(monkeypatch, tmp_path):
    monkeypatch.setattr(schedule.sys, "platform", "win32")
    calls = []

    def fake_run(cmd, **kw):
        calls.append(cmd)

        class R:
            returncode = 0
            stdout = ""
            stderr = ""
        return R()
    monkeypatch.setattr(schedule.subprocess, "run", fake_run)
    result = schedule.install_daily_sync(tmp_path / "config.yaml", hour=6)
    assert result["installed"] is True
    assert result["task_name"] == schedule.TASK_NAME
    script = calls[0][-1]
    assert "Register-ScheduledTask" in script
    assert "-AllowStartIfOnBatteries" in script and "-StartWhenAvailable" in script
    assert "06:00" in script
    assert "--unattended" in script


def test_install_posix_returns_cron_line(monkeypatch, tmp_path):
    monkeypatch.setattr(schedule.sys, "platform", "linux")
    result = schedule.install_daily_sync(tmp_path / "config.yaml", hour=6)
    assert result["installed"] is False
    assert result["cron_line"].startswith("0 6 * * * ")
    assert "--unattended" in result["cron_line"]


def test_install_macos_writes_launchd_agent(monkeypatch, tmp_path):
    import plistlib

    monkeypatch.setattr(schedule.sys, "platform", "darwin")
    monkeypatch.setattr(schedule.Path, "home", classmethod(lambda cls: tmp_path))
    monkeypatch.setattr(schedule.os, "getuid", lambda: 501, raising=False)  # no getuid on Windows CI
    calls = []

    def fake_run(cmd, **kw):
        calls.append(cmd)

        class R:
            returncode = 0
            stdout = ""
            stderr = ""
        return R()
    monkeypatch.setattr(schedule.subprocess, "run", fake_run)
    config = tmp_path / "hub home" / "config.yaml"
    result = schedule.install_daily_sync(config, hour=6)
    assert result == {"installed": True, "task_name": schedule.LAUNCHD_LABEL, "time": "06:00"}
    data = plistlib.loads(schedule.launchd_plist_path().read_bytes())
    assert data["Label"] == schedule.LAUNCHD_LABEL
    assert data["StartCalendarInterval"] == {"Hour": 6, "Minute": 0}
    assert data["ProgramArguments"][-3:] == ["--unattended", "--config", str(config)]
    assert calls[-1][:2] == ["launchctl", "bootstrap"]


def test_remove_macos_deletes_launchd_agent(monkeypatch, tmp_path):
    monkeypatch.setattr(schedule.sys, "platform", "darwin")
    monkeypatch.setattr(schedule.Path, "home", classmethod(lambda cls: tmp_path))
    monkeypatch.setattr(schedule.os, "getuid", lambda: 501, raising=False)
    monkeypatch.setattr(schedule.subprocess, "run", lambda *a, **k: None)
    assert schedule.remove_daily_sync() is False
    plist = schedule.launchd_plist_path()
    plist.parent.mkdir(parents=True)
    plist.write_bytes(b"x")
    assert schedule.remove_daily_sync() is True
    assert not plist.exists()
