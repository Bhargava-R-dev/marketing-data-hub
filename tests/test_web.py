"""`hub web`: browser chats reach the hub through a secret address, read-only."""
import asyncio
import os
import stat
import sys

import pytest
from starlette.testclient import TestClient

from hub.core.config import ConnectorSettings, HubConfig
from hub.core.webtoken import load_or_create_token, mcp_path
from hub.mcp.server import build_mcp

WRITE_TOOLS = {"add_accounts", "trigger_sync", "backfill",
               "list_available_accounts", "list_identities"}


def _config(tmp_path):
    (tmp_path / "config.yaml").write_text("connectors: {}\n")
    return HubConfig(db_path=str(tmp_path / "hub.duckdb"),
                     secrets_dir=str(tmp_path / "secrets"),
                     connectors={"ga4": ConnectorSettings()})


def _tool_names(mcp):
    return {t.name for t in asyncio.run(mcp.list_tools())}


def test_token_is_long_stable_and_rotatable(tmp_path):
    first = load_or_create_token(tmp_path / "secrets")
    assert len(first) >= 40
    assert load_or_create_token(tmp_path / "secrets") == first
    rotated = load_or_create_token(tmp_path / "secrets", rotate=True)
    assert rotated != first and load_or_create_token(tmp_path / "secrets") == rotated


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX file modes")
def test_token_file_is_owner_only(tmp_path):
    load_or_create_token(tmp_path / "secrets")
    mode = stat.S_IMODE(os.stat(tmp_path / "secrets" / "web_mcp_token").st_mode)
    assert mode == 0o600


def test_web_mode_leaves_out_every_write_tool(tmp_path):
    cfg = _config(tmp_path)
    normal = _tool_names(build_mcp(cfg, config_path=str(tmp_path / "config.yaml")))
    web = _tool_names(build_mcp(cfg, config_path=str(tmp_path / "config.yaml"), web=True))
    assert WRITE_TOOLS <= normal          # they exist for local use...
    assert not (WRITE_TOOLS & web)        # ...and are absent over the web
    assert {"query_metrics", "query_ga4_live", "query_gsc_live"} <= web


def test_only_the_exact_secret_path_answers(tmp_path):
    cfg = _config(tmp_path)
    mcp = build_mcp(cfg, config_path=str(tmp_path / "config.yaml"), web=True)
    token = load_or_create_token(cfg.secrets_dir)
    app = mcp.http_app(path=mcp_path(token), stateless_http=True)
    with TestClient(app, base_url="https://abc.trycloudflare.com") as client:
        for wrong in ("/mcp", "/mcp/", "/mcp/wrong", f"/mcp/{token}x", "/"):
            assert client.post(wrong, json={}).status_code == 404, wrong
        init = {"jsonrpc": "2.0", "id": 1, "method": "initialize",
                "params": {"protocolVersion": "2025-03-26", "capabilities": {},
                           "clientInfo": {"name": "t", "version": "0"}}}
        ok = client.post(mcp_path(token), json=init,
                         headers={"Accept": "application/json, text/event-stream"})
        assert ok.status_code == 200, ok.text


def test_db_override_keeps_web_cache_out_of_the_real_folder(tmp_path):
    cfg = _config(tmp_path)
    scratch = tmp_path / "scratch" / "hub.duckdb"
    build_mcp(cfg, config_path=str(tmp_path / "config.yaml"), web=True,
              db_path_override=str(scratch))
    assert scratch.exists() and not (tmp_path / "hub.duckdb").exists()
