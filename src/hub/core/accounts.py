"""Account discovery and selection — Windsor-style onboarding.

Lists every GA4 property and Search Console site the Google token can see,
marks which are already configured, and writes selections back to config.yaml
(comments and anchors preserved via ruamel round-trip)."""
from __future__ import annotations

from pathlib import Path

from ruamel.yaml import YAML

# source -> (plural options key, labels supported)
SOURCE_KEYS = {"ga4": "property_ids", "gsc": "site_urls"}


def discover_ga4(creds) -> list[dict]:
    """All GA4 properties visible to the token, via the Admin API."""
    from googleapiclient.discovery import build

    admin = build("analyticsadmin", "v1beta", credentials=creds,
                  cache_discovery=False)
    out: list[dict] = []
    token = None
    while True:
        resp = admin.accountSummaries().list(pageSize=200, pageToken=token).execute()
        for acct in resp.get("accountSummaries", []):
            for prop in acct.get("propertySummaries", []):
                out.append({
                    "source": "ga4",
                    "id": prop["property"].split("/")[-1],
                    "name": prop.get("displayName", ""),
                    "parent": acct.get("displayName", ""),
                })
        token = resp.get("nextPageToken")
        if not token:
            return out


def discover_gsc(creds) -> list[dict]:
    """All verified Search Console sites visible to the token."""
    from googleapiclient.discovery import build

    sc = build("searchconsole", "v1", credentials=creds, cache_discovery=False)
    resp = sc.sites().list().execute()
    return [{
        "source": "gsc",
        "id": s["siteUrl"],
        "name": s["siteUrl"],
        "parent": s.get("permissionLevel", ""),
    } for s in resp.get("siteEntry", [])]


def discover_all(creds, source: str | None = None) -> list[dict]:
    out: list[dict] = []
    if source in (None, "ga4"):
        out += discover_ga4(creds)
    if source in (None, "gsc"):
        out += discover_gsc(creds)
    return out


def configured_ids(config, source: str) -> list[str]:
    """Account ids currently in config for one source ('' options tolerated)."""
    if source not in config.connectors:
        return []
    opts = config.connectors[source].options
    plural = SOURCE_KEYS[source]
    ids = [str(t) for t in (opts.get(plural) or [])]
    single = opts.get(plural.rstrip("s"))  # property_id / site_url
    if single is not None and str(single) not in ids:
        ids.append(str(single))
    return ids


def annotate_configured(accounts: list[dict], config) -> list[dict]:
    for a in accounts:
        a["configured"] = a["id"] in configured_ids(config, a["source"])
    return accounts


def add_accounts(config_path: str | Path, source: str,
                 selections: list[dict], identity: str = "default") -> list[str]:
    """Append selected accounts to config.yaml, preserving comments/anchors.

    selections: [{"id": ..., "name": ...}]. Ids already present are skipped.
    Returns the ids actually added. Creates the connector block (with the
    default schedule) if it isn't in the config yet. A non-default identity
    records which Google login owns each added account (options.identities)."""
    if source not in SOURCE_KEYS:
        raise KeyError(f"account selection not supported for {source!r} "
                       f"(supported: {list(SOURCE_KEYS)})")
    config_path = Path(config_path)
    yaml = YAML()  # round-trip mode: keeps comments, anchors, ordering
    yaml.preserve_quotes = True
    yaml.width = 4096  # never wrap mid-string
    yaml.indent(mapping=2, sequence=4, offset=2)  # keep "  - item" list style
    data = yaml.load(config_path.read_text(encoding="utf-8")) or {}

    connectors = data.setdefault("connectors", {})
    conn = connectors.setdefault(source, {"schedule": "0 6 * * *", "options": {}})
    opts = conn.setdefault("options", {})
    plural = SOURCE_KEYS[source]
    ids = opts.setdefault(plural, [])
    labels = opts.setdefault("labels", {})

    existing = {str(i) for i in ids}
    single = opts.get(plural.rstrip("s"))
    if single is not None:
        existing.add(str(single))

    added: list[str] = []
    for sel in selections:
        sid = str(sel["id"])
        if sid in existing:
            continue
        ids.append(sid)
        if sel.get("name"):
            labels[sid] = sel["name"]
        if identity and identity != "default":
            opts.setdefault("identities", {})[sid] = identity
        existing.add(sid)
        added.append(sid)

    if added:
        yaml.dump(data, config_path.open("w", encoding="utf-8"))
    return added


# option keys each connector accepts from the setup wizard (safety whitelist)
WIZARD_OPTION_KEYS = {
    "meta_ads": {"access_token", "ad_account_ids", "labels"},
    "google_ads": {"developer_token", "customer_ids", "login_customer_id",
                   "labels", "identity"},
}


def set_connector_options(config_path: str | Path, source: str,
                          options: dict) -> None:
    """Merge whitelisted option keys into connectors.<source>.options in
    config.yaml (comments/anchors preserved). Used by the setup wizard for
    token-based connectors (meta_ads, google_ads)."""
    allowed = WIZARD_OPTION_KEYS.get(source)
    if allowed is None:
        raise KeyError(f"wizard cannot configure {source!r} "
                       f"(supported: {sorted(WIZARD_OPTION_KEYS)})")
    bad = set(options) - allowed
    if bad:
        raise KeyError(f"unsupported option(s) for {source}: {sorted(bad)}")
    config_path = Path(config_path)
    yaml = YAML()
    yaml.preserve_quotes = True
    yaml.width = 4096
    yaml.indent(mapping=2, sequence=4, offset=2)
    data = yaml.load(config_path.read_text(encoding="utf-8")) or {}
    conn = data.setdefault("connectors", {}).setdefault(
        source, {"schedule": "0 6 * * *", "options": {}})
    opts = conn.setdefault("options", {})
    for key, value in options.items():
        if isinstance(value, dict):
            opts.setdefault(key, {}).update(value)
        else:
            opts[key] = value
    yaml.dump(data, config_path.open("w", encoding="utf-8"))
