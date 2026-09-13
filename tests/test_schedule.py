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
