"""Find Claude Desktop / Claude Code and register the hub's MCP server so the
user never has to open a JSON file by hand."""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
from datetime import datetime
from pathlib import Path

SERVER_NAME = "marketing-hub"


def mcp_command(config_path: Path) -> tuple[str, list[str]]:
    from hub.core.paths import cli_command

    command = cli_command("mcp", "--config", str(config_path))
    return command[0], command[1:]


def desktop_config_candidates() -> list[Path]:
    """Existing Claude Desktop config files, most likely first. The Microsoft
    Store build keeps its config under LocalCache (not %APPDATA%)."""
    out: list[Path] = []
    if sys.platform == "win32":
        local = Path(os.environ.get("LOCALAPPDATA", ""))
        for pkg in sorted(local.glob("Packages/Claude_*")):
            out.append(pkg / "LocalCache" / "Roaming" / "Claude" / "claude_desktop_config.json")
        out.append(Path(os.environ.get("APPDATA", "")) / "Claude" / "claude_desktop_config.json")
    elif sys.platform == "darwin":
        out.append(Path.home() / "Library" / "Application Support" / "Claude"
                   / "claude_desktop_config.json")
    else:
        out.append(Path.home() / ".config" / "Claude" / "claude_desktop_config.json")
    # the Store build's LocalCache path and %APPDATA% can be the same file
    # (folder redirection) - list it once or the user sees two "Claude Desktop"s
    unique: list[Path] = []
    for p in out:
        if p.exists() and not any(os.path.samefile(p, q) for q in unique):
            unique.append(p)
    return unique


def cli_available() -> bool:
    return shutil.which("claude") is not None


def is_registered(config_file: Path, config_path: Path | None = None,
                  command: str | None = None, args: list[str] | None = None) -> bool:
    """True when our server entry exists - and, if config_path is given, points
    at THIS hub (a machine can host several hubs; another hub's entry doesn't
    count)."""
    try:
        data = json.loads(config_file.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    if not isinstance(data, dict) or not isinstance(data.get("mcpServers", {}), dict):
        return False
    entry = data.get("mcpServers", {}).get(SERVER_NAME)
    if not isinstance(entry, dict) or not entry:
        return False
    if command is not None:
        return entry.get("command") == command and entry.get("args") == args
    if config_path is None:
        return True
    return str(config_path) in [str(a) for a in entry.get("args", [])]


def write_mcp_entry(config_file: Path, command: str, args: list[str]) -> Path:
    """Merge our server into the file, preserving everything else. Backs the
    original up beside it first."""
    config_file.parent.mkdir(parents=True, exist_ok=True)
    data: dict = {}
    if config_file.exists():
        try:
            data = json.loads(config_file.read_text(encoding="utf-8"))
        except ValueError as exc:
            raise ValueError(f"Invalid JSON in {config_file}; repair it before connecting Claude") from exc
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        shutil.copy2(config_file, config_file.with_name(config_file.name + f".bak-{stamp}"))
    if not isinstance(data, dict) or not isinstance(data.get("mcpServers", {}), dict):
        raise ValueError("Claude configuration must contain JSON objects")
    servers = data.setdefault("mcpServers", {})
    servers[SERVER_NAME] = {"command": command, "args": args}
    temp_name = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", delete=False,
                                         dir=config_file.parent) as temp:
            temp_name = temp.name
            json.dump(data, temp, indent=2)
        os.replace(temp_name, config_file)
    finally:
        if temp_name and os.path.exists(temp_name):
            os.unlink(temp_name)
    return config_file


def register_with_cli(command: str, args: list[str]) -> str:
    """Replace this server's stale user entry while preserving other settings."""
    return str(write_mcp_entry(code_config_path(), command, args))


def code_config_path() -> Path:
    override = os.environ.get("CLAUDE_CONFIG_DIR")
    return Path(override) / ".claude.json" if override else Path.home() / ".claude.json"


def detect(config_path: Path) -> dict:
    command, args = mcp_command(config_path)
    targets = [{"id": f"desktop:{i}", "label": "Claude Desktop", "path": str(p),
                "registered": is_registered(p, config_path, command, args)}
               for i, p in enumerate(desktop_config_candidates())]
    if cli_available() or code_config_path().exists():
        targets.append({"id": "cli", "label": "Claude Code (terminal)", "path": "claude",
                        "registered": is_registered(code_config_path(), config_path, command, args)})
    return {"targets": targets, "command": command, "args": args,
            "snippet": json.dumps({SERVER_NAME: {"command": command, "args": args}}, indent=2)}
