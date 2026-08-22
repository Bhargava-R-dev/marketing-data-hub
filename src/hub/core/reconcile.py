"""Reconciliation: catch a breakdown report silently OVER-counting against
core, the exact failure class that inflated Sharekhan's numbers by 38% for
weeks (GA4's '(other)' cardinality bug) before anyone noticed - a wrong
number that looked completely normal.

Deliberately one-directional: breakdown reports are EXPECTED to undercount
slightly (GSC anonymises rare queries, GA4 can't attribute every session to
a dimension) - that's documented, benign, and never flagged. Only
OVER-counting is checked, because a breakdown genuinely can never contain
more of an additive metric than the exact core total for the same account
and range; if it does, something is double-counting.

Only reports whose metric is SESSION/CLICK-scoped like core, AND that don't
have a KNOWN, benign reason to deviate, are included:
- report="pages"/"events" for GA4 are page-view/event scoped (a different
  attribution model entirely, see query_metrics' landing_pages-vs-pages
  warning) and would never reconcile even when everything is working
  correctly.
- report="pages" for GSC is deliberately excluded too, for a reason found
  by this exact check in the field: Google's own Search Console API
  returns a page-dimension breakdown that consistently overcounts core by
  2-9.5% - confirmed on a SINGLE, unpaginated live API call (2,055 rows,
  nowhere near a page boundary), so it's not this codebase's pagination,
  it's how GSC itself attributes clicks by page (URL-variant/canonicali-
  sation quirks). Same class of expected deviation as query-level
  anonymisation, just in the other direction - benign, not a bug.
"""
from __future__ import annotations

from datetime import date

RECONCILABLE_REPORTS: dict[str, dict[str, str]] = {
    "ga4": {"channels": "sessions", "landing_pages": "sessions",
            "audience": "sessions", "visitors": "sessions"},
    "gsc": {"queries": "clicks", "devices": "clicks", "countries": "clicks"},
}


def find_over_counts(storage, date_from: date, date_to: date,
                     tolerance: float = 0.01,
                     source: str | None = None) -> list[dict]:
    """Per account, compare each reconcilable report's total against core's
    total for the same metric/range. Returns one finding per account+report
    whose total exceeds core's by more than `tolerance` (default 1%, to
    absorb rounding/timing noise, not real double-counting). Pass source=
    to check just one connector's reports (e.g. right after that source's
    own sync) instead of every source."""
    findings = []
    for src, reports in RECONCILABLE_REPORTS.items():
        if source and src != source:
            continue
        for report, metric in reports.items():
            core_rows = storage.query(["account_id", "account_name", metric],
                                      date_from, date_to, sources=[src],
                                      report="core")
            core_by_id = {r["account_id"]: (r.get(metric) or 0) for r in core_rows}
            names = {r["account_id"]: r["account_name"] for r in core_rows}
            try:
                brk_rows = storage.query(["account_id", metric], date_from, date_to,
                                         sources=[src], report=report)
            except Exception:  # noqa: BLE001 - report not synced for this source yet
                continue
            for r in brk_rows:
                aid = r["account_id"]
                core_total = core_by_id.get(aid, 0) or 0
                brk_total = r.get(metric) or 0
                if core_total and brk_total > core_total * (1 + tolerance):
                    findings.append({
                        "source": src, "report": report, "metric": metric,
                        "account_id": aid, "account_name": names.get(aid, aid),
                        "core_total": core_total, "report_total": brk_total,
                        "overcount_pct": round(
                            (brk_total - core_total) / core_total * 100, 1),
                    })
    return findings
