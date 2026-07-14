from __future__ import annotations

import json
import re
import threading
from datetime import date, datetime
from pathlib import Path

import duckdb

from hub.core.models import CORE_DIMENSIONS, CORE_METRICS, UnifiedRow

_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

_SCHEMA = [
    """CREATE TABLE IF NOT EXISTS metrics (
        date DATE, source VARCHAR, account_id VARCHAR, account_name VARCHAR,
        campaign_id VARCHAR, campaign VARCHAR,
        impressions BIGINT, clicks BIGINT, spend DOUBLE, conversions DOUBLE,
        conversion_value DOUBLE, sessions BIGINT, users BIGINT, extras JSON)""",
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
                     rows: list[UnifiedRow]) -> int:
        with self._lock:
            self.conn.execute("BEGIN TRANSACTION")
            try:
                self.conn.execute(
                    "DELETE FROM metrics WHERE source = ? AND date BETWEEN ? AND ?",
                    [source, date_from, date_to])
                if rows:
                    self.conn.executemany(
                        "INSERT INTO metrics VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        [[r.date, r.source, r.account_id, r.account_name, r.campaign_id,
                          r.campaign, r.impressions, r.clicks, r.spend, r.conversions,
                          r.conversion_value, r.sessions, r.users, json.dumps(r.extras)]
                         for r in rows])
                self.conn.execute("COMMIT")
            except Exception:
                self.conn.execute("ROLLBACK")
                raise
            return len(rows)

    # ---- queries ------------------------------------------------------
    def query(self, fields: list[str], date_from: date, date_to: date,
              sources: list[str] | None = None,
              filters: dict[str, str] | None = None) -> list[dict]:
        """Extras fields are extracted with json_extract_string and always come
        back as strings — callers must cast numeric extras themselves."""
        with self._lock:
            for f in fields:
                if not _IDENT.match(f):
                    raise ValueError(f"invalid field name: {f!r}")
            dims = [f for f in fields if f in CORE_DIMENSIONS]
            mets = [f for f in fields if f in CORE_METRICS]
            extra = [f for f in fields if f not in CORE_DIMENSIONS and f not in CORE_METRICS]

            sel = [f'"{d}"' for d in dims]
            # _IDENT validation above also makes this JSON path interpolation safe (no dots/quotes/$)
            sel += [f"json_extract_string(extras, '$.{e}') AS \"{e}\"" for e in extra]
            sel += [f'SUM("{m}") AS "{m}"' for m in mets]

            where = ["date BETWEEN ? AND ?"]
            params: list = [date_from, date_to]
            if sources:
                where.append(f"source IN ({','.join(['?'] * len(sources))})")
                params.extend(sources)
            for key, val in (filters or {}).items():
                if key not in CORE_DIMENSIONS:
                    raise ValueError(f"invalid filter: {key!r}")
                where.append(f'"{key}" = ?')
                params.append(val)

            group_cols = dims + extra
            sql = f"SELECT {', '.join(sel)} FROM metrics WHERE {' AND '.join(where)}"
            if group_cols and mets:
                sql += f" GROUP BY {', '.join(str(i + 1) for i in range(len(group_cols)))}"
            if group_cols:
                sql += f" ORDER BY {', '.join(str(i + 1) for i in range(len(group_cols)))}"
            cur = self.conn.execute(sql, params)
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]

    def row_counts(self) -> dict[str, dict]:
        with self._lock:
            cur = self.conn.execute(
                "SELECT source, COUNT(*), MAX(date) FROM metrics GROUP BY source")
            return {s: {"rows": n, "latest_date": latest} for s, n, latest in cur.fetchall()}

    def accounts(self) -> list[dict]:
        """Distinct accounts/brands in the data with their coverage window."""
        with self._lock:
            cur = self.conn.execute(
                """SELECT source, account_id, account_name, COUNT(*), MIN(date), MAX(date)
                   FROM metrics GROUP BY 1, 2, 3 ORDER BY 1, 3""")
            return [{"source": s, "account_id": aid, "account_name": name,
                     "rows": n, "first_date": first, "latest_date": latest}
                    for s, aid, name, n, first, latest in cur.fetchall()]

    # ---- sync log -----------------------------------------------------
    def start_sync(self, source: str, date_from: date, date_to: date) -> int:
        with self._lock:
            cur = self.conn.execute(
                """INSERT INTO sync_runs (source, started_at, date_from, date_to,
                   rows_written, status) VALUES (?, ?, ?, ?, 0, 'running') RETURNING id""",
                [source, datetime.now(), date_from, date_to])
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
                """SELECT source, started_at, finished_at, rows_written, status, error_message
                   FROM sync_runs QUALIFY ROW_NUMBER() OVER
                   (PARTITION BY source ORDER BY started_at DESC) = 1""")
            out = {}
            for s, started, finished, rows, status, err in cur.fetchall():
                out[s] = {"started_at": started, "finished_at": finished,
                          "rows_written": rows, "status": status, "error_message": err}
            return out

    def close(self) -> None:
        with self._lock:
            self.conn.close()
