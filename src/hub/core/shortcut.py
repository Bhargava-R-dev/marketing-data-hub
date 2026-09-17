"""Desktop / Start Menu shortcuts so the hub opens with a double-click and no
console window. Windows only; other platforms get instructions."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

SHORTCUT_NAME = "Marketing Data Hub"
ICON = Path(__file__).resolve().parent.parent / "resources" / "hub.ico"


def launcher_command(config_path: Path | None = None) -> tuple[str, str]:
    """(target, arguments) that open the wizard/home page silently."""
    args = "setup"
    if config_path is not None:
        args += f' --config "{config_path}"'
    if getattr(sys, "frozen", False):
        gui = Path(sys.executable).with_name("MarketingDataHub.exe")
        if gui.exists():
            return str(gui), args if config_path is not None else ""
        return sys.executable, args
    exe = sys.executable
    if exe.lower().endswith("python.exe"):
        exe = exe[:-len("python.exe")] + "pythonw.exe"  # no console window
    return exe, f"-m hub.cli {args}"


def shortcut_locations() -> list[Path]:
    home = Path(os.environ.get("USERPROFILE", str(Path.home())))
    start = Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs"
    return [home / "Desktop" / f"{SHORTCUT_NAME}.lnk", start / f"{SHORTCUT_NAME}.lnk"]


def _ps_quote(s: str) -> str:
    return "'" + s.replace("'", "''") + "'"


def create_shortcuts(config_path: Path | None = None) -> dict:
    if sys.platform != "win32":
        target, args = launcher_command(config_path)
        return {"created": [], "hint": f"Create a launcher that runs: {target} {args}"}
    target, args = launcher_command(config_path)
    created = []
    for lnk in shortcut_locations():
        lnk.parent.mkdir(parents=True, exist_ok=True)
        script = (
            "$s = (New-Object -ComObject WScript.Shell).CreateShortcut(" + _ps_quote(str(lnk)) + "); "
            f"$s.TargetPath = {_ps_quote(target)}; $s.Arguments = {_ps_quote(args)}; "
            f"$s.WorkingDirectory = {_ps_quote(str(Path(target).parent))}; "
            f"$s.IconLocation = {_ps_quote(str(ICON))}; "
            f"$s.Description = {_ps_quote('Open Marketing Data Hub')}; $s.Save()"
        )
        proc = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                              capture_output=True, text=True, timeout=60)
        if proc.returncode != 0:
            raise RuntimeError(proc.stderr.strip() or f"could not create {lnk}")
        created.append(str(lnk))
    return {"created": created}
