"""
Database adapters — unified interface for Pandas, DuckDB, and Supabase (PostgreSQL).

Each adapter exposes:
  execute(sql, params=None) → DBResult
    .description   → list[str]  (column names)
    .fetchone()    → tuple | None
    .fetchmany(n)  → list[tuple]
    .fetchall()    → list[tuple]
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any


class DBResult:
    """Thin wrapper that stores all rows in-memory so the cursor can be closed."""

    def __init__(self, col_names: list[str], rows: list[tuple]):
        self._col_names = col_names
        self._rows = rows
        self._pos = 0

    @property
    def description(self) -> list[str]:
        return self._col_names

    def fetchone(self) -> tuple | None:
        if self._pos >= len(self._rows):
            return None
        row = self._rows[self._pos]
        self._pos += 1
        return row

    def fetchmany(self, size: int = 1) -> list[tuple]:
        end = min(self._pos + size, len(self._rows))
        chunk = self._rows[self._pos:end]
        self._pos = end
        return chunk

    def fetchall(self) -> list[tuple]:
        remaining = self._rows[self._pos:]
        self._pos = len(self._rows)
        return remaining


# ── DuckDB Adapter ────────────────────────────────────────────────────────────

class DuckDBAdapter:
    """Wraps a duckdb.DuckDBPyConnection."""

    def __init__(self, conn):
        self._conn = conn

    def execute(self, sql: str, params: list[Any] | None = None) -> DBResult:
        if params:
            rel = self._conn.execute(sql, params)
        else:
            rel = self._conn.execute(sql)
        col_names = [d[0] for d in rel.description]
        rows = rel.fetchall()
        return DBResult(col_names, rows)


# ── Pandas Adapter (default) ──────────────────────────────────────────────────

class PandasAdapter:
    """Loads CSVs into pandas DataFrames; uses DuckDB in-memory for SQL queries.

    The data lifecycle is:  CSV → pd.read_csv() → DataFrame → registered in
    an in-memory DuckDB connection so existing SQL keeps working unchanged.
    No .duckdb file is created on disk.
    """

    def __init__(self, data_dir: Path, tables: list[str]):
        import pandas as pd
        import duckdb

        self.dataframes: dict[str, pd.DataFrame] = {}
        self._conn = duckdb.connect()  # pure in-memory, no file

        for table in tables:
            csv_path = data_dir / f"{table}.csv"
            if csv_path.exists():
                # Load into pandas for direct DataFrame access
                df = pd.read_csv(csv_path)
                self.dataframes[table] = df
                # Create DuckDB view with read_csv_auto for proper type inference
                # (dates, numerics, etc.) so existing SQL works unchanged
                self._conn.execute(
                    f"CREATE OR REPLACE VIEW {table} AS "
                    f"SELECT * FROM read_csv_auto('{csv_path.as_posix()}', header=true)"
                )

    def execute(self, sql: str, params: list[Any] | None = None) -> DBResult:
        if params:
            rel = self._conn.execute(sql, params)
        else:
            rel = self._conn.execute(sql)
        # DML (INSERT/UPDATE/DELETE) — no result rows
        if rel.description is None:
            return DBResult([], [])
        col_names = [d[0] for d in rel.description]
        rows = rel.fetchall()
        return DBResult(col_names, rows)

    def execute_ddl(self, sql: str) -> None:
        """Run a DDL statement (CREATE TABLE, etc.) that returns no rows."""
        self._conn.execute(sql)


# ── Supabase / PostgreSQL Adapter ─────────────────────────────────────────────

class SupabaseAdapter:
    """Wraps a psycopg2 connection with connection-pool lifecycle."""

    def __init__(self, database_url: str):
        import psycopg2
        from psycopg2.extras import RealDictCursor
        self._url = database_url
        self._psycopg2 = psycopg2
        self._RealDictCursor = RealDictCursor
        # We open a fresh connection per execute() call to stay thread-safe
        # in FastAPI's default-threaded model.  For higher throughput you'd
        # swap this for a psycopg2.pool.SimpleConnectionPool.

    def _get_conn(self):
        conn = self._psycopg2.connect(self._url)
        return conn

    @staticmethod
    def _to_pg_params(sql: str, params: list[Any] | None) -> tuple[str, list[Any] | None]:
        """Rewrite DuckDB's '?' placeholders into psycopg2's '%s' style."""
        if not params:
            return sql, None
        sql_out = sql
        parts: list[str] = []
        in_single_quote = False
        in_double_quote = False
        i = 0
        while i < len(sql_out):
            ch = sql_out[i]
            if ch == "'" and not in_double_quote:
                in_single_quote = not in_single_quote
            elif ch == '"' and not in_single_quote:
                in_double_quote = not in_double_quote
            elif ch == '?' and not in_single_quote and not in_double_quote:
                parts.append("%s")
                i += 1
                continue
            parts.append(ch)
            i += 1
        return "".join(parts), params

    def execute(self, sql: str, params: list[Any] | None = None) -> DBResult:
        pg_sql, pg_params = self._to_pg_params(sql, params)
        conn = self._get_conn()
        try:
            cur = conn.cursor(cursor_factory=self._RealDictCursor)
            if pg_params:
                cur.execute(pg_sql, pg_params)
            else:
                cur.execute(pg_sql)

            # DML (INSERT/UPDATE/DELETE) — no result rows
            if cur.description is None:
                conn.commit()
                return DBResult([], [])

            col_names = [d.name for d in cur.description]
            rows = cur.fetchall()
            tuples = [tuple(r.values()) for r in rows]
            conn.commit()
            return DBResult(col_names, tuples)
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def execute_ddl(self, sql: str) -> None:
        """Run a DDL statement that returns no rows."""
        conn = self._get_conn()
        try:
            cur = conn.cursor()
            cur.execute(sql)
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
