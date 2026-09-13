from __future__ import annotations

import json
import urllib.request
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _pkg_version

RELEASES_API = "https://api.github.com/repos/Bhargava-R-dev/marketing-data-hub/releases/latest"
_cache: dict = {}


def current() -> str:
    try:
        return _pkg_version("marketing-data-hub")
    except PackageNotFoundError:
        return "0.0.0"


def _fetch_json(url: str, timeout: float) -> dict:
    req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json",
                                               "User-Agent": "marketing-data-hub"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 - fixed https URL
        return json.loads(resp.read().decode("utf-8"))


def latest(timeout: float = 3.0) -> dict | None:
    """{'version', 'url'} of the newest GitHub release, cached per process;
    None when offline or no release exists yet."""
    if "latest" in _cache:
        return _cache["latest"]
    try:
        data = _fetch_json(RELEASES_API, timeout)
        result = {"version": str(data.get("tag_name", "")).lstrip("v"),
                  "url": data.get("html_url")}
    except Exception:  # noqa: BLE001 - offline / rate-limited / 404 all mean "unknown"
        result = None
    _cache["latest"] = result
    return result


def _key(v: str) -> tuple:
    return tuple(int(p) if p.isdigit() else 0 for p in v.split("."))


def is_newer(candidate: str, than: str) -> bool:
    return _key(candidate) > _key(than)
