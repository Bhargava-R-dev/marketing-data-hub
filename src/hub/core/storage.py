from __future__ import annotations

import json
import os
import re
import tempfile
import threading
from datetime import date, datetime, timedelta
from pathlib import Path

import duckdb

from hub.core.models import CORE_DIMENSIONS, CORE_METRICS, UnifiedRow

_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
# a 'running' sync_runs row older than this crashed rather than finishing -
# the single source of truth for that threshold (mcp/server.py imports it
# rather than keeping its own copy, which had silently drifted out of sync
# with reality: rows like this were found stuck 'running' for DAYS with
# nothing ever correcting them - a human had to notice and fix it by hand)
STALE_RUNNING = timedelta(minutes=15)

_METRIC_COLUMNS = {  # bulk-load column spec, in metrics-table order
    "date": "DATE", "source": "VARCHAR", "report": "VARCHAR",
    "account_id": "VARCHAR", "account_name": "VARCHAR",
    "campaign_id": "VARCHAR", "campaign": "VARCHAR",
    "impressions": "BIGINT", "clicks": "BIGINT", "spend": "DOUBLE",
    "conversions": "DOUBLE", "conversion_value": "DOUBLE",
    "sessions": "BIGINT", "users": "BIGINT", "extras": "JSON",
}

_SCHEMA = [
    """CREATE TABLE IF NOT EXISTS metrics (
        date DATE, source VARCHAR, report VARCHAR DEFAULT 'core',
        account_id VARCHAR, account_name VARCHAR,
        campaign_id VARCHAR, campaign VARCHAR,
        impressions BIGINT, clicks BIGINT, spend DOUBLE, conversions DOUBLE,
        conversion_value DOUBLE, sessions BIGINT, users BIGINT, extras JSON)""",
    # migration for DBs created before multi-report support (fills 'core')
    "ALTER TABLE metrics ADD COLUMN IF NOT EXISTS report VARCHAR DEFAULT 'core'",
    "CREATE SEQUENCE IF NOT EXISTS sync_runs_seq",
    """CREATE TABLE IF NOT EXISTS sync_runs (
        id BIGINT DEFAULT nextval('sync_runs_seq'), source VARCHAR,
        started_at TIMESTAMP, finished_at TIMESTAMP, date_from DATE, date_to DATE,
        rows_written BIGINT, status VARCHAR, error_message VARCHAR)""",
]


class Storage:
    def __init__(self, db_path: str, read_only: bool = False):
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self.conn = duckdb.connect(db_path, read_only=read_only)
        if not read_only:
            for stmt in _SCHEMA:
                self.conn.execute(stmt)

    # ---- writes -------------------------------------------------------
    def replace_rows(self, source: str, date_from: date, date_to: date,
                     rows: list[UnifiedRow], report: str = "core") -> int:
        """Transactionally replace one (source, report) slice of a date range.

        Bulk-loads through a temp JSONL file + read_json: parameter-bound
        executemany is ~16ms/row on some Windows setups, which turns
        breakdown-report volumes (tens of thousands of rows) into hours.
        JSONL rather than CSV because campaign names, queries, and landing
        pages contain quotes/commas/newlines that trip strict CSV parsing."""
        with self._lock:
            jsonl_path = self._write_rows_jsonl(rows, report) if rows else None
            self.conn.execute("BEGIN TRANSACTION")
            try:
                self.conn.execute(
                    "DELETE FROM metrics WHERE source = ? AND report = ? "
                    "AND date BETWEEN ? AND ?",
                    [source, report, date_from, date_to])
                if jsonl_path:
                    cols = ", ".join(_METRIC_COLUMNS)
                    spec = ", ".join(f"'{c}': '{t}'" for c, t in _METRIC_COLUMNS.items())
                    self.conn.execute(
                        f"""INSERT INTO metrics ({cols})
                            SELECT {cols}
                            FROM read_json('{jsonl_path.as_posix()}',
                                           format = 'newline_delimited',
                                           columns = {{{spec}}})""")
                self.conn.execute("COMMIT")
            except Exception:
                self.conn.execute("ROLLBACK")
                raise
            finally:
                if jsonl_path:
                    os.unlink(jsonl_path)
            return len(rows)

    @staticmethod
    def _write_rows_jsonl(rows: list[UnifiedRow], report: str) -> Path:
        fh = tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", suffix=".jsonl", delete=False)
        try:
            with fh:
                for r in rows:
                    fh.write(json.dumps({
                        "date": r.date.isoformat(), "source": r.source,
                        "report": report, "account_id": r.account_id,
                        "account_name": r.account_name, "campaign_id": r.campaign_id,
                        "campaign": r.campaign, "impressions": r.impressions,
                        "clicks": r.clicks, "spend": r.spend,
                        "conversions": r.conversions,
                        "conversion_value": r.conversion_value,
                        "sessions": r.sessions, "users": r.users,
                        "extras": r.extras,
                    }, ensure_ascii=False) + "\n")
        except Exception:
            os.unlink(fh.name)
            raise
        return Path(fh.name)

    # ---- queries ------------------------------------------------------
    def query(self, fields: list[str], date_from: date, date_to: date,
              sources: list[str] | None = None,
              filters: dict[str, str] | None = None,
              report: str = "core",
              extra_metrics: set[str] | None = None) -> list[dict]:
        """Extras fields named in extra_metrics are SUMmed as numbers; other
        extras are group-by dimensions extracted with json_extract_string and
        come back as strings (callers cast non-additive extras themselves).

        Always filters on one report: rows from different reports of the same
        source are different granularities and must never be summed together."""
        with self._lock:
            for f in fields:
                if not _IDENT.match(f):
                    raise ValueError(f"invalid field name: {f!r}")
            extra_metrics = extra_metrics or set()
            dims = [f for f in fields if f in CORE_DIMENSIONS]
            mets = [f for f in fields if f in CORE_METRICS]
            extra = [f for f in fields if f not in CORE_DIMENSIONS and f not in CORE_METRICS]
            extra_dims = [e for e in extra if e not in extra_metrics]
            extra_mets = [e for e in extra if e in extra_metrics]

            sel = [f'"{d}"' for d in dims]
            # _IDENT validation above also makes this JSON path interpolation safe (no dots/quotes/$)
            sel += [f"json_extract_string(extras, '$.{e}') AS \"{e}\"" for e in extra_dims]
            sel += [f"SUM(TRY_CAST(json_extract_string(extras, '$.{e}') AS DOUBLE))"
                    f" AS \"{e}\"" for e in extra_mets]
            sel += [f'SUM("{m}") AS "{m}"' for m in mets]

            where = ["date BETWEEN ? AND ?", "report = ?"]
            params: list = [date_from, date_to, report]
            if sources:
                where.append(f"source IN ({','.join(['?'] * len(sources))})")
                params.extend(sources)
            for key, val in (filters or {}).items():
                if not _IDENT.match(key):
                    raise ValueError(f"invalid filter: {key!r}")
                if key in CORE_DIMENSIONS:
                    where.append(f'"{key}" = ?')
                else:  # extras dimension (event, query, channel, device, ...)
                    where.append(f"json_extract_string(extras, '$.{key}') = ?")
                params.append(str(val))

            group_cols = dims + extra_dims
            sql = f"SELECT {', '.join(sel)} FROM metrics WHERE {' AND '.join(where)}"
            if group_cols and (mets or extra_mets):
                sql += f" GROUP BY {', '.join(str(i + 1) for i in range(len(group_cols)))}"
            if group_cols:
                sql += f" ORDER BY {', '.join(str(i + 1) for i in range(len(group_cols)))}"
            cur = self.conn.execute(sql, params)
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]

    def row_counts(self) -> dict[str, dict]:
        with self._lock:
            cur = self.conn.execute(
                """SELECT source, COUNT(*), MAX(date) FROM metrics
                   WHERE report = 'core' GROUP BY source""")
            return {s: {"rows": n, "latest_date": latest} for s, n, latest in cur.fetchall()}

    def report_coverage(self) -> list[dict]:
        """Rows and date window per (source, report) — shows what's synced."""
        with self._lock:
            cur = self.conn.execute(
                """SELECT source, report, COUNT(*), MIN(date), MAX(date)
                   FROM metrics GROUP BY 1, 2 ORDER BY 1, 2""")
            return [{"source": s, "report": rep, "rows": n,
                     "first_date": first, "latest_date": latest}
                    for s, rep, n, first, latest in cur.fetchall()]

    def accounts(self) -> list[dict]:
        """Distinct accounts/brands in the data with their coverage window."""
        with self._lock:
            cur = self.conn.execute(
                """SELECT source, account_id, account_name, COUNT(*), MIN(date), MAX(date)
                   FROM metrics WHERE report = 'core' GROUP BY 1, 2, 3 ORDER BY 1, 3""")
            return [{"source": s, "account_id": aid, "account_name": name,
                     "rows": n, "first_date": first, "latest_date": latest}
                    for s, aid, name, n, first, latest in cur.fetchall()]

    def date_gaps(self, source: str, date_from: date, date_to: date,
                 report: str = "core", account_id: str | None = None) -> dict:
        """Missing calendar days within a range, for one account if given
        (or the whole source otherwise). Deliberately scoped to a single
        account when possible: a source-level check can mask a real gap -
        one account's hole disappears behind another account covering the
        same dates, which is exactly how a 68-day outage went unnoticed
        while the dashboard's source-level date range looked fine."""
        where = "source = ? AND report = ?"
        params: list = [source, report]
        if account_id is not None:
            where += " AND account_id = ?"
            params.append(account_id)
        with self._lock:
            cur = self.conn.execute(
                f"""WITH days AS (
                        SELECT unnest(generate_series(?::DATE, ?::DATE,
                                                      INTERVAL 1 DAY))::DATE d
                    ), have AS (SELECT DISTINCT date FROM metrics WHERE {where})
                    SELECT d FROM days LEFT JOIN have ON days.d = have.date
                    WHERE have.date IS NULL ORDER BY d""",
                [date_from, date_to, *params])
            missing = [r[0] for r in cur.fetchall()]
        total_days = (date_to - date_from).days + 1
        return {"days_requested": total_days,
                "days_with_data": total_days - len(missing),
                "missing_dates": [d.isoformat() for d in missing]}

    # ---- sync log -----------------------------------------------------
    def start_sync(self, source: str, date_from: date, date_to: date) -> int:
        with self._lock:
            now = datetime.now()
            # housekeeping: a prior run for this source stuck on 'running'
            # past the stale threshold crashed (killed process, machine
            # sleep, a hard kill mid-sync) rather than ever finishing - it
            # would otherwise sit there misleadingly forever, since nothing
            # else ever revisits a sync_runs row once written. Clear it the
            # moment a new run for the same source starts.
            self.conn.execute(
                """UPDATE sync_runs SET status = 'error', finished_at = ?,
                   error_message = 'crashed (never finished - marked stale '
                   || 'automatically when a later sync started)'
                   WHERE source = ? AND status = 'running'
                   AND started_at < ?""",
                [now, source, now - STALE_RUNNING])
            cur = self.conn.execute(
                """INSERT INTO sync_runs (source, started_at, date_from, date_to,
                   rows_written, status) VALUES (?, ?, ?, ?, 0, 'running') RETURNING id""",
                [source, now, date_from, date_to])
            return cur.fetchone()[0]

    def finish_sync(self, run_id: int, rows: int, status: str,
                    error: str | None = None) -> None:
        with self._lock:
            self.conn.execute(
                """UPDATE sync_runs SET finished_at = ?, rows_written = ?,
                   status = ?, error_message = ? WHERE id = ?""",
                [datetime.now(), rows, status, error, run_id])

    def last_runs(self) -> dict[str, dict]:
        with self._lock:
            cur = self.conn.execute(
                """SELECT source, started_at, finished_at, rows_written, status,
                   error_message, date_from, date_to
                   FROM sync_runs QUALIFY ROW_NUMBER() OVER
                   (PARTITION BY source ORDER BY started_at DESC) = 1""")
            out = {}
            for s, started, finished, rows, status, err, d_from, d_to in cur.fetchall():
                out[s] = {"started_at": started, "finished_at": finished,
                          "rows_written": rows, "status": status, "error_message": err,
                          # the window this run actually covered - a "success"
                          # covering the last 30 days looks identical to one
                          # covering 2 years without this; callers must be
                          # able to tell "caught up" from "just the recent bit"
                          "date_from": d_from, "date_to": d_to}
            return out

    def close(self) -> None:
        with self._lock:
            self.conn.close()
