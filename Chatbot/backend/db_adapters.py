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
    """DuckDB in-memory backend. Loads each CSV as a DuckDB table on startup
    via read_csv_auto, then serves all queries from DuckDB's columnar memory.

    Historical note: this used to load CSVs into pandas DataFrames and then
    register DuckDB views over them. That doubled memory (pandas + view
    metadata) and made queries re-read CSVs from disk. The current version
    is ~3–4x smaller in RAM (DuckDB columnar storage) with no disk re-reads
    at query time — the name PandasAdapter is kept only to avoid breaking
    the factory import path.
    """

    def __init__(self, data_dir: Path, tables: list[str]):
        import duckdb

        self._conn = duckdb.connect()  # pure in-memory, no file
        self.dataframes: dict[str, object] = {}  # kept for backwards compat only

        for table in tables:
            # Prefer parquet (smaller, typed, faster to load). Fall back to
            # CSV so local dev against the raw ab_data/ directory still works.
            pq_path = data_dir / f"{table}.parquet"
            csv_path = data_dir / f"{table}.csv"
            if pq_path.exists():
                self._conn.execute(
                    f"CREATE TABLE {table} AS "
                    f"SELECT * FROM read_parquet('{pq_path.as_posix()}')"
                )
                self.dataframes[table] = True
            elif csv_path.exists():
                self._conn.execute(
                    f"CREATE TABLE {table} AS "
                    f"SELECT * FROM read_csv_auto('{csv_path.as_posix()}', header=true)"
                )
                self.dataframes[table] = True

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
    """Uses DuckDB as the query engine with Postgres as the storage backend.

    Rationale: the query catalog was written in DuckDB SQL dialect (DATE_DIFF,
    ROUND(double, int), DISTINCT in window functions, etc.), which plain
    Postgres cannot execute. Instead of rewriting hundreds of queries, we
    attach Postgres as an external database inside an in-process DuckDB
    instance via the postgres extension. DuckDB pulls the rows it needs and
    runs aggregations in its own columnar engine, so both the dialect
    mismatch and Postgres's temp-file disk pressure for large GROUP BYs
    disappear.

    Thread safety: we use a single DuckDB connection guarded by a lock.
    FastAPI's default thread pool is fine for demo-scale concurrency.
    """

    def __init__(self, database_url: str):
        import duckdb
        import threading

        # Railway's TCP proxy requires SSL; DuckDB's postgres extension does
        # not default to it, so force it on the URL if the caller omitted it.
        if "sslmode=" not in database_url:
            sep = "&" if "?" in database_url else "?"
            database_url = f"{database_url}{sep}sslmode=require"
        self._url = database_url

        # Single-threaded: Railway's TCP proxy drops parallel DuckDB→Postgres
        # connections under heavy fan-out, which crashes mid-query. One
        # connection is plenty for demo throughput.
        self._conn = duckdb.connect(config={"threads": "1"})
        self._conn.execute("INSTALL postgres")
        self._conn.execute("LOAD postgres")
        self._conn.execute(f"ATTACH '{database_url}' AS pg (TYPE postgres)")
        self._conn.execute("USE pg.public")

        self._lock = threading.Lock()

    def execute(self, sql: str, params: list[Any] | None = None) -> DBResult:
        with self._lock:
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
        with self._lock:
            self._conn.execute(sql)
