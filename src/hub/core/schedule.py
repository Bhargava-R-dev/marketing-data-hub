"""Register the 6am daily sync. Windows: a per-user scheduled task that also
runs on battery and catches up if the laptop was asleep (both bit us before).
macOS: a per-user launchd agent (launchd also runs a missed job on wake).
Elsewhere: hand back a cron line."""
from __future__ import annotations

import os
import plistlib
import shlex
import subprocess
import sys
from pathlib import Path

TASK_NAME = "MarketingDataHub Daily Sync"
LAUNCHD_LABEL = "com.marketingdatahub.dailysync"


def sync_command(config_path: Path) -> tuple[str, list[str]]:
    from hub.core.paths import cli_command

    command = cli_command("sync", "all", "--unattended", "--config", str(config_path))
    return command[0], command[1:]


def _ps_quote(s: str) -> str:
    return "'" + s.replace("'", "''") + "'"


def launchd_plist_path() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{LAUNCHD_LABEL}.plist"


def _install_launchd(exe: str, args: list[str], log: Path, hour: int) -> dict:
    log.parent.mkdir(parents=True, exist_ok=True)
    plist = launchd_plist_path()
    plist.parent.mkdir(parents=True, exist_ok=True)
    plist.write_bytes(plistlib.dumps({
        "Label": LAUNCHD_LABEL,
        "ProgramArguments": [exe, *args],
        "StartCalendarInterval": {"Hour": hour, "Minute": 0},
        "StandardOutPath": str(log),
        "StandardErrorPath": str(log),
    }))
    domain = f"gui/{os.getuid()}"
    # bootout first so re-running 'schedule' replaces the old definition
    subprocess.run(["launchctl", "bootout", f"{domain}/{LAUNCHD_LABEL}"],
                   capture_output=True, text=True, timeout=60)
    proc = subprocess.run(["launchctl", "bootstrap", domain, str(plist)],
                          capture_output=True, text=True, timeout=60)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or "launchctl bootstrap failed")
    return {"installed": True, "task_name": LAUNCHD_LABEL, "time": f"{hour:02d}:00"}


def install_daily_sync(config_path: Path, hour: int = 6) -> dict:
    exe, args = sync_command(config_path)
    log = config_path.parent / "logs" / "sync.log"
    if sys.platform == "darwin":
        return _install_launchd(exe, args, log, hour)
    if sys.platform != "win32":
        line = (f"0 {hour} * * * {shlex.quote(exe)} {' '.join(shlex.quote(a) for a in args)}"
                f" >> {shlex.quote(str(log))} 2>&1")
        return {"installed": False, "cron_line": line}
    # cmd.exe wrapper so output lands in the log file
    inner = f'"{exe}" {" ".join(chr(34) + a + chr(34) for a in args)} >> "{log}" 2>&1'
    script = (
        f"$a = New-ScheduledTaskAction -Execute 'cmd.exe' -Argument {_ps_quote('/c ' + inner)}; "
        f"$t = New-ScheduledTaskTrigger -Daily -At {hour:02d}:00; "
        "$s = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries "
        "-StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Hours 2); "
        f"Register-ScheduledTask -TaskName {_ps_quote(TASK_NAME)} -Action $a -Trigger $t "
        "-Settings $s -Force | Out-Null"
    )
    proc = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                          capture_output=True, text=True, timeout=60)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or "Register-ScheduledTask failed")
    return {"installed": True, "task_name": TASK_NAME, "time": f"{hour:02d}:00"}


def remove_daily_sync() -> bool:
    if sys.platform == "darwin":
        plist = launchd_plist_path()
        if not plist.exists():
            return False
        subprocess.run(["launchctl", "bootout", f"gui/{os.getuid()}/{LAUNCHD_LABEL}"],
                       capture_output=True, text=True, timeout=60)
        plist.unlink()
        return True
    if sys.platform != "win32":
        return False
    proc = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command",
                           f"Unregister-ScheduledTask -TaskName {_ps_quote(TASK_NAME)} "
                           "-Confirm:$false"], capture_output=True, text=True, timeout=60)
    return proc.returncode == 0
