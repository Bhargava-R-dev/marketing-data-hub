"""Account discovery/selection: config writing, dedup, discovery parsing."""
from pathlib import Path

import pytest

from hub.core.accounts import add_accounts, annotate_configured, configured_ids
from hub.core.config import load_config

SAMPLE = """\
db_path: data/hub.duckdb   # keep this comment
secrets_dir: secrets
exports_dir: exports

connectors:
  ga4:
    schedule: "0 6 * * *"   # daily at six
    options:
      property_ids:
        - "111"    # first property
      labels:
        "111": "First"
  gsc:
    schedule: "0 6 * * *"
    options:
      site_urls: ["https://a.example/", "https://b.example/"]
      brand_terms:
        "https://a.example/": &terms [alpha, beta]
        "https://b.example/": *terms
"""


@pytest.fixture()
def cfg_path(tmp_path):
    p = tmp_path / "config.yaml"
    p.write_text(SAMPLE, encoding="utf-8")
    return p


def test_add_accounts_appends_and_labels(cfg_path):
    added = add_accounts(cfg_path, "ga4", [
        {"id": "222", "name": "Second"},
        {"id": "111", "name": "First"},      # duplicate -> skipped
    ])
    assert added == ["222"]
    cfg = load_config(cfg_path)
    assert cfg.connectors["ga4"].options["property_ids"] == ["111", "222"]
    assert cfg.connectors["ga4"].options["labels"]["222"] == "Second"


def test_add_accounts_preserves_comments_and_anchors(cfg_path):
    add_accounts(cfg_path, "ga4", [{"id": "222", "name": "Second"}])
    text = cfg_path.read_text(encoding="utf-8")
    assert "# keep this comment" in text
    assert "# daily at six" in text
    assert "# first property" in text
    assert "&terms" in text  # anchor untouched


def test_add_accounts_creates_missing_connector_block(tmp_path):
    p = tmp_path / "config.yaml"
    p.write_text("db_path: x.duckdb\nconnectors:\n  ga4:\n    options: {property_id: '1'}\n",
                 encoding="utf-8")
    added = add_accounts(p, "gsc", [{"id": "https://new.example/", "name": "New"}])
    assert added == ["https://new.example/"]
    cfg = load_config(p)
    assert cfg.connectors["gsc"].options["site_urls"] == ["https://new.example/"]
    assert cfg.connectors["gsc"].schedule == "0 6 * * *"


def test_add_accounts_respects_singular_key(tmp_path):
    p = tmp_path / "config.yaml"
    p.write_text("connectors:\n  ga4:\n    options: {property_id: '333'}\n",
                 encoding="utf-8")
    assert add_accounts(p, "ga4", [{"id": "333", "name": "Dup"}]) == []


def test_add_accounts_unknown_source(cfg_path):
    with pytest.raises(KeyError):
        add_accounts(cfg_path, "meta_ads", [{"id": "act_1", "name": "x"}])


def test_configured_ids_and_annotate(cfg_path):
    cfg = load_config(cfg_path)
    assert configured_ids(cfg, "ga4") == ["111"]
    assert configured_ids(cfg, "gsc") == ["https://a.example/", "https://b.example/"]
    found = annotate_configured([
        {"source": "ga4", "id": "111", "name": "First", "parent": ""},
        {"source": "ga4", "id": "999", "name": "Other", "parent": ""},
    ], cfg)
    assert [a["configured"] for a in found] == [True, False]
