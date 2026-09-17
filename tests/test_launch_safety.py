"""Regression coverage for the v0.6.0 frozen GUI tab-spam chain."""
import asyncio
import runpy
import sys
from pathlib import Path
from unittest.mock import Mock

import pytest
import uvicorn
from fastapi import FastAPI

from hub.core.local_server import LocalServer
from hub.core.paths import cli_command
from hub.core.schedule import sync_command
from hub.setup_wizard.claude_config import mcp_command


@pytest.mark.parametrize("caller", ["hub.exe", "MarketingDataHub.exe"])
def test_frozen_background_commands_always_use_console_cli(tmp_path, monkeypatch, caller):
    cli = tmp_path / "hub.exe"
    cli.touch()
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(tmp_path / caller))
    config = tmp_path / "with spaces" / "config.yaml"
    for command in (sync_command(config), mcp_command(config)):
        exe, args = command
        assert exe == str(cli)
        assert "-m" not in args
        assert args[-1] == str(config)
    assert "--unattended" in sync_command(config)[1]


def test_missing_bundled_cli_fails_without_falling_back_to_gui(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(tmp_path / "MarketingDataHub.exe"))
    with pytest.raises(FileNotFoundError, match="Reinstall"):
        cli_command("sync", "all")


@pytest.mark.parametrize("args", [[], ["sync", "all", "--unattended"], ["--version"]])
def test_gui_entry_preserves_arguments(monkeypatch, args):
    seen = []
    monkeypatch.setattr("hub.cli.app", lambda: seen.append(sys.argv[1:]))
    monkeypatch.setattr(sys, "argv", ["MarketingDataHub.exe", *args])
    runpy.run_path(str(Path(__file__).parents[1] / "packaging/hub_gui_entry.py"),
                   run_name="__main__")
    assert seen == [args or ["setup"]]


def test_browser_only_opens_after_successful_startup(monkeypatch):
    opened = Mock()
    monkeypatch.setattr("hub.core.local_server.webbrowser.open", opened)

    async def startup(server, sockets=None):
        opened.assert_not_called()
        server.started = True

    monkeypatch.setattr(uvicorn.Server, "startup", startup)
    server = LocalServer(uvicorn.Config(FastAPI(), port=8770), open_browser=True)
    asyncio.run(server.startup())
    opened.assert_called_once_with("http://127.0.0.1:8770")


def test_failed_bind_never_opens_browser(monkeypatch):
    opened = Mock()
    monkeypatch.setattr("hub.core.local_server.webbrowser.open", opened)

    async def startup(server, sockets=None):
        raise SystemExit(1)

    monkeypatch.setattr(uvicorn.Server, "startup", startup)
    server = LocalServer(uvicorn.Config(FastAPI(), port=8770), open_browser=True)
    with pytest.raises(SystemExit):
        asyncio.run(server.startup())
    opened.assert_not_called()
