"""The secret that makes `hub web` reachable. It is a long random string placed
in the URL path, because the browser chats (claude.ai, ChatGPT) can only add a
tool by address: anyone without the exact address gets a plain 404."""
from __future__ import annotations

import os
import secrets
from pathlib import Path

TOKEN_FILE = "web_mcp_token"


def token_path(secrets_dir: str | Path) -> Path:
    return Path(secrets_dir) / TOKEN_FILE


def load_or_create_token(secrets_dir: str | Path, rotate: bool = False) -> str:
    path = token_path(secrets_dir)
    if path.exists() and not rotate:
        token = path.read_text(encoding="utf-8").strip()
        if len(token) >= 32:
            return token
    path.parent.mkdir(parents=True, exist_ok=True)
    token = secrets.token_urlsafe(32)  # 256 bits
    # owner-only from the first byte written
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(token)
    return token


def mcp_path(token: str) -> str:
    return f"/mcp/{token}"
