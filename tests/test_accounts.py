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


# ---- flag_duplicate_names / probe_ga4_activity: the "two properties both --
# ---- named Fevicreate, one dead" situation, confirmed real in the field ---


def test_flag_duplicate_names_marks_shared_name_under_same_parent():
    from hub.core.accounts import flag_duplicate_names

    accounts = [
        {"source": "ga4", "parent": "Fevicreate New Website Prod",
         "name": "Fevicreate", "id": "307775988"},
        {"source": "ga4", "parent": "Fevicreate New Website Prod",
         "name": "Fevicreate", "id": "461984716"},
        {"source": "ga4", "parent": "Vetrotech Acct", "name": "Vetrotech", "id": "1"},
    ]
    flag_duplicate_names(accounts)
    assert accounts[0]["duplicate_name"] is True
    assert accounts[1]["duplicate_name"] is True
    assert accounts[2]["duplicate_name"] is False


def test_flag_duplicate_names_same_name_different_parent_is_not_flagged():
    """Same name under a DIFFERENT parent is already disambiguated by the
    parent shown alongside it - only same name + same parent is the real
    ambiguity."""
    from hub.core.accounts import flag_duplicate_names

    accounts = [
        {"source": "ga4", "parent": "Client A", "name": "Website", "id": "1"},
        {"source": "ga4", "parent": "Client B", "name": "Website", "id": "2"},
    ]
    flag_duplicate_names(accounts)
    assert accounts[0]["duplicate_name"] is False
    assert accounts[1]["duplicate_name"] is False


def test_discover_all_probes_activity_only_for_duplicates(monkeypatch):
    """The activity probe must never run for every discovered property
    (a real login can see 150+) - only for the small duplicate-named set."""
    from hub.core import accounts as accounts_mod

    monkeypatch.setattr(accounts_mod, "discover_ga4", lambda creds: [
        {"source": "ga4", "parent": "P", "name": "Fevicreate", "id": "307775988"},
        {"source": "ga4", "parent": "P", "name": "Fevicreate", "id": "461984716"},
        {"source": "ga4", "parent": "P", "name": "Vetrotech", "id": "999"},
    ])
    monkeypatch.setattr(accounts_mod, "discover_gsc", lambda creds: [])

    probed = {}

    def fake_probe(creds, property_ids, days=30):
        probed["ids"] = property_ids
        return {pid: False for pid in property_ids}
    monkeypatch.setattr(accounts_mod, "probe_ga4_activity", fake_probe)

    out = accounts_mod.discover_all(creds="fake-creds")
    assert set(probed["ids"]) == {"307775988", "461984716"}  # not "999"
    by_id = {a["id"]: a for a in out}
    assert by_id["307775988"]["active_recently"] is False
    assert by_id["461984716"]["active_recently"] is False
    assert "active_recently" not in by_id["999"]  # never probed, never touched


def test_discover_all_survives_probe_failure(monkeypatch):
    """Discovery must still succeed even if the activity probe itself
    fails (e.g. a permission error on one of the duplicate properties)."""
    from hub.core import accounts as accounts_mod

    monkeypatch.setattr(accounts_mod, "discover_ga4", lambda creds: [
        {"source": "ga4", "parent": "P", "name": "Fevicreate", "id": "1"},
        {"source": "ga4", "parent": "P", "name": "Fevicreate", "id": "2"},
    ])
    monkeypatch.setattr(accounts_mod, "discover_gsc", lambda creds: [])

    def boom(creds, property_ids, days=30):
        raise Exception("API error")
    monkeypatch.setattr(accounts_mod, "probe_ga4_activity", boom)

    out = accounts_mod.discover_all(creds="fake-creds")
    assert len(out) == 2
    assert all(a["duplicate_name"] for a in out)
    assert all("active_recently" not in a for a in out)  # probe failed -> just absent
