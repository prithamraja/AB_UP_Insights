#!/usr/bin/env python
# =============================================================================
# build_views.py — generic, domain-agnostic analytical-view runner
# =============================================================================
# Replaces the hand-written pandas pipeline (phase1_pipeline.py) with a thin
# runner that executes a *domain pack* (declarative YAML + SQL) on DuckDB.
#
# Standing up "Discover" for a new domain means writing a new domain_pack/
# (sources.yaml, derived_columns.sql, views/*.sql, validation.yaml) — NO Python.
# This file contains no domain-specific table or column names; every domain
# string lives in the pack.
#
# Pipeline (see README in the pack for the contract):
#   1. Register sources     — one typed DuckDB view per source file (explicit casts).
#   2. Apply derived columns — run derived_columns.sql (creates stg_* views).
#   3. Pre-view validation   — checks from validation.yaml (+ row counts).
#   4. Build views           — run each views/*.sql and COPY to Parquet.
#   5. Profile               — per-view/-column stats to reports/view_summaries.txt.
#   6. Post-view checks       — row-count + grain expectations from config.
#
# CLI:
#   python src/build_views.py [--pack domain_pack] [--data-dir ab_data]
#                             [--views-dir views] [--reports-dir reports]
#                             [--strict]
#
# --strict exits non-zero on any failed validation check (for automation).
# Default mode logs failures and continues. Checks never mutate data.
#
# NOTE (environment): DuckDB spills temp files that cannot be written on a
# Google Drive mount, so the runner points DuckDB's temp_directory at the local
# system temp dir. Reading CSVs from / writing Parquet to a Drive path is fine;
# only the engine's scratch space must be local.
# =============================================================================

from __future__ import annotations

import argparse
import glob
import os
import sys
import tempfile
from datetime import datetime

import duckdb
import yaml


# ── Cast expressions: logical type in sources.yaml -> DuckDB SQL ────────────
# `timestamp` mirrors pandas `to_datetime(..., utc=True).tz_localize(None)`:
# with the session in UTC, naive strings are assumed UTC and offset-bearing
# strings are converted to UTC, then the tz is stripped to a naive TIMESTAMP.
def _cast(col: str, logical_type: str) -> str:
    q = f'"{col}"'
    return {
        "timestamp": f"CAST({q} AS TIMESTAMPTZ) AT TIME ZONE 'UTC'",
        "date":      f"CAST({q} AS DATE)",
        "float":     f"CAST({q} AS DOUBLE)",
        "int":       f"CAST({q} AS BIGINT)",
        "bool":      f"CAST({q} AS BOOLEAN)",
    }[logical_type]


# Sources are read as raw text and typed only by the explicit casts above. A
# .parquet source holds that same text with every column VARCHAR (what
# scripts/csv_to_parquet.py writes), so both readers yield identical relations.
def _raw_reader(path: str) -> str:
    if path.lower().endswith(".parquet"):
        return f"read_parquet('{_sql_str(path)}')"
    return f"read_csv('{_sql_str(path)}', all_varchar=true, header=true)"


class Runner:
    def __init__(self, pack_dir, data_dir, views_dir, reports_dir, strict):
        self.pack_dir = pack_dir
        self.data_dir = data_dir
        self.views_dir = views_dir
        self.reports_dir = reports_dir
        self.strict = strict

        self.report: list[str] = []       # validation_report.txt lines
        self.failures = 0                  # failed checks (drives --strict exit)

        self.con = duckdb.connect()
        self.con.execute("SET TimeZone='UTC'")
        tmp = os.path.join(tempfile.gettempdir(), "duckdb_build_views")
        os.makedirs(tmp, exist_ok=True)
        self.con.execute(f"SET temp_directory='{_sql_str(tmp)}'")
        # DuckDB 1.5.1's top_n_window_elimination optimizer raises an internal
        # binder error ("inequal types (DOUBLE != VARCHAR)") on view1 when the
        # sources are Parquet. Disabling it changes the plan, never the results.
        if self.con.execute(
            "SELECT count(*) FROM duckdb_optimizers() WHERE name = 'top_n_window_elimination'"
        ).fetchone()[0]:
            self.con.execute("SET disabled_optimizers = 'top_n_window_elimination'")

        os.makedirs(self.views_dir, exist_ok=True)
        os.makedirs(self.reports_dir, exist_ok=True)

    # ── logging helpers ────────────────────────────────────────────────────
    def log(self, msg: str = "") -> None:
        self.report.append(msg)
        print(msg)

    def check(self, name: str, issues: list[str]) -> None:
        """Log one named check. Any issue increments the failure counter."""
        if not issues:
            self.log(f"[PASSED] {name}")
            return
        self.failures += 1
        self.log(f"[FAILED] {name}")
        for issue in issues:
            self.log(f"  - {issue}")

    def _load_yaml(self, filename: str) -> dict:
        with open(os.path.join(self.pack_dir, filename), encoding="utf-8") as fh:
            return yaml.safe_load(fh)

    # ── step 1: register sources ───────────────────────────────────────────
    def register_sources(self) -> None:
        self.log("=" * 70)
        self.log("STEP 1: Register sources")
        self.log("=" * 70)
        self.sources = self._load_yaml("sources.yaml")
        for name, spec in self.sources["tables"].items():
            path = os.path.join(self.data_dir, spec["file"])
            reader = _raw_reader(path)
            cols = [r[0] for r in self.con.execute(f"DESCRIBE SELECT * FROM {reader}").fetchall()]
            casts = spec.get("casts") or {}
            select_list = ", ".join(
                _cast(c, casts[c]) + f' AS "{c}"' if c in casts else f'"{c}"'
                for c in cols
            )
            self.con.execute(
                f"CREATE OR REPLACE VIEW {name} AS SELECT {select_list} FROM {reader}"
            )
            n = self.con.execute(f"SELECT count(*) FROM {name}").fetchone()[0]
            self.log(f"  registered {name}: {n:,} rows x {len(cols)} cols")

    # ── step 2: derived columns ────────────────────────────────────────────
    def apply_derived_columns(self) -> None:
        self.log("\n" + "=" * 70)
        self.log("STEP 2: Apply derived columns")
        self.log("=" * 70)
        with open(os.path.join(self.pack_dir, "derived_columns.sql"), encoding="utf-8") as fh:
            self.con.execute(fh.read())
        self.log("  derived_columns.sql executed (stg_* views created)")

    # ── step 3: pre-view validation ────────────────────────────────────────
    def validate_sources(self) -> None:
        self.log("\n" + "=" * 70)
        self.log("STEP 3: Pre-view validation")
        self.log("=" * 70)
        self.log(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        self.v = self._load_yaml("validation.yaml")

        self._check_row_counts()
        self._check_primary_keys()
        self._check_foreign_keys()
        self._check_null_rates()
        self._check_categoricals()
        self._check_date_ranges()

    def _check_row_counts(self) -> None:
        self.log("\n--- CHECK 1: Row counts ---")
        tol = self.sources.get("row_count_tolerance_pct", 20)
        issues = []
        for name, spec in self.sources["tables"].items():
            expected = spec.get("expected_rows")
            if not expected:
                continue
            actual = self.con.execute(f"SELECT count(*) FROM {name}").fetchone()[0]
            pct = abs(actual - expected) / expected * 100
            status = "OK" if pct < tol else "UNEXPECTED"
            self.log(f"  {name}: actual={actual:,} expected~{expected:,} ({pct:.1f}% diff) [{status}]")
            if pct >= tol:
                issues.append(f"{name}: {actual:,} rows vs expected ~{expected:,} ({pct:.1f}% diff)")
        self.check("CHECK 1: Row counts", issues)

    def _check_primary_keys(self) -> None:
        self.log("\n--- CHECK 2: Primary-key uniqueness ---")
        issues = []
        for table, pk in (self.v.get("primary_keys") or {}).items():
            total, distinct = self.con.execute(
                f'SELECT count(*), count(DISTINCT "{pk}") FROM {table}'
            ).fetchone()
            dups = total - distinct
            if dups > 0:
                self.log(f"  [FAIL] {table}.{pk}: {dups:,} duplicates")
                issues.append(f"{table}.{pk} has {dups:,} duplicates")
            else:
                self.log(f"  [OK]   {table}.{pk}: unique")
        self.check("CHECK 2: Primary-key uniqueness", issues)

    def _check_foreign_keys(self) -> None:
        self.log("\n--- CHECK 3: Foreign-key integrity ---")
        issues = []
        for fk in (self.v.get("foreign_keys") or []):
            child, cc = fk["child"], fk["child_col"]
            parent, pc = fk["parent"], fk["parent_col"]
            total = self.con.execute(
                f'SELECT count(*) FROM {child} WHERE "{cc}" IS NOT NULL'
            ).fetchone()[0]
            orphans = self.con.execute(
                f'SELECT count(*) FROM {child} c '
                f'LEFT JOIN (SELECT DISTINCT "{pc}" AS k FROM {parent} WHERE "{pc}" IS NOT NULL) p '
                f'ON c."{cc}" = p.k WHERE c."{cc}" IS NOT NULL AND p.k IS NULL'
            ).fetchone()[0]
            pct = orphans / total * 100 if total else 0
            self.log(f"  {child}.{cc} -> {parent}.{pc}: {orphans:,}/{total:,} orphans ({pct:.1f}%)")
            if orphans > 0:
                issues.append(f"{child}.{cc} -> {parent}.{pc}: {orphans:,} orphans ({pct:.1f}%)")
        self.check("CHECK 3: Foreign-key integrity", issues)

    def _check_null_rates(self) -> None:
        # CHECK 4 logs high-null columns for awareness; never a hard failure.
        threshold = self.v.get("null_rate_threshold_pct", 20)
        self.log(f"\n--- CHECK 4: Null rates (columns with >{threshold}% nulls) ---")
        for name in self.sources["tables"]:
            cols = [r[0] for r in self.con.execute(f"DESCRIBE {name}").fetchall()]
            total = self.con.execute(f"SELECT count(*) FROM {name}").fetchone()[0]
            if not total:
                continue
            exprs = ", ".join(f'count(*) - count("{c}") AS "{c}"' for c in cols)
            nulls = self.con.execute(f"SELECT {exprs} FROM {name}").fetchone()
            for col, n in zip(cols, nulls):
                pct = n / total * 100
                if pct > threshold:
                    self.log(f"  {name}.{col}: {pct:.1f}% null")

    def _check_categoricals(self) -> None:
        self.log("\n--- CHECK 5: Categorical value domains ---")
        issues = []
        for table, colmap in (self.v.get("categorical") or {}).items():
            for col, expected in colmap.items():
                actual = [r[0] for r in self.con.execute(
                    f'SELECT DISTINCT "{col}" FROM {table} WHERE "{col}" IS NOT NULL'
                ).fetchall()]
                self.log(f"  {table}.{col}: {sorted(actual)}")
                unexpected = set(actual) - set(expected)
                if unexpected:
                    issues.append(f"{table}.{col}: unexpected values {unexpected}")
        self.check("CHECK 5: Categorical value domains", issues)

    def _check_date_ranges(self) -> None:
        cfg = self.v.get("date_ranges") or {}
        lo, hi = cfg.get("min_years", 1), cfg.get("max_years", 10)
        self.log(f"\n--- CHECK 6: Date ranges (span {lo}-{hi} yrs) ---")
        issues = []
        for item in cfg.get("columns", []):
            table, col = item["table"], item["column"]
            mn, mx = self.con.execute(
                f'SELECT min("{col}"), max("{col}") FROM {table}'
            ).fetchone()
            if mn is None or mx is None:
                continue
            span = (mx - mn).days / 365
            self.log(f"  {table}.{col}: {mn.date()} -> {mx.date()} ({span:.1f} yrs)")
            if not (lo <= span <= hi):
                issues.append(f"{table}.{col}: span={span:.1f} yrs (expected {lo}-{hi})")
        self.check("CHECK 6: Date ranges", issues)

    # ── step 4: build views ────────────────────────────────────────────────
    def build_views(self) -> None:
        self.log("\n" + "=" * 70)
        self.log("STEP 4: Build views")
        self.log("=" * 70)
        self.view_names: list[str] = []
        for sql_path in sorted(glob.glob(os.path.join(self.pack_dir, "views", "*.sql"))):
            name = os.path.splitext(os.path.basename(sql_path))[0]
            with open(sql_path, encoding="utf-8") as fh:
                sql = fh.read().rstrip().rstrip(";")
            self.con.execute(f"CREATE OR REPLACE TEMP VIEW {name} AS {sql}")
            out = os.path.join(self.views_dir, f"{name}.parquet")
            self.con.execute(
                f"COPY (SELECT * FROM {name}) TO '{_sql_str(out)}' (FORMAT PARQUET)"
            )
            n = self.con.execute(f"SELECT count(*) FROM {name}").fetchone()[0]
            self.view_names.append(name)
            self.log(f"  built {name}: {n:,} rows -> {out}")

    # ── step 5: profile ────────────────────────────────────────────────────
    def profile_views(self) -> None:
        self.log("\n" + "=" * 70)
        self.log("STEP 5: Profile views")
        self.log("=" * 70)
        lines: list[str] = []
        for name in self.view_names:
            schema = self.con.execute(f"DESCRIBE {name}").fetchall()
            total = self.con.execute(f"SELECT count(*) FROM {name}").fetchone()[0]
            lines.append("\n" + "=" * 70)
            lines.append(f"SUMMARY: {name}")
            lines.append(f"Rows: {total:,} | Columns: {len(schema)}")
            lines.append("=" * 70)
            for col, dtype, *_ in schema:
                q = f'"{col}"'
                nulls, distinct, mn, mx = self.con.execute(
                    f"SELECT count(*) - count({q}), count(DISTINCT {q}), "
                    f"min({q})::VARCHAR, max({q})::VARCHAR FROM {name}"
                ).fetchone()
                null_pct = nulls / total * 100 if total else 0
                lines.append(
                    f"  {col} [{dtype}]  null={null_pct:.1f}%  distinct={distinct:,}  "
                    f"min={mn!r}  max={mx!r}"
                )
        path = os.path.join(self.reports_dir, "view_summaries.txt")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("\n".join(lines))
        self.log(f"  view summaries -> {path}")

    # ── step 6: post-view checks ───────────────────────────────────────────
    def validate_views(self) -> None:
        self.log("\n" + "=" * 70)
        self.log("STEP 6: Post-view checks")
        self.log("=" * 70)
        for name, cfg in (self.v.get("post_view") or {}).items():
            if name not in self.view_names:
                continue
            total = self.con.execute(f"SELECT count(*) FROM {name}").fetchone()[0]
            issues = []
            if "expected_rows" in cfg:
                exp = cfg["expected_rows"]
                tol = cfg.get("tolerance_pct", 20)
                pct = abs(total - exp) / exp * 100
                self.log(f"  {name}: {total:,} rows (expected ~{exp:,}, {pct:.1f}% diff)")
                if pct >= tol:
                    issues.append(f"{name}: {total:,} rows vs expected ~{exp:,}")
            if "min_rows" in cfg:
                self.log(f"  {name}: {total:,} rows (min {cfg['min_rows']:,})")
                if total < cfg["min_rows"]:
                    issues.append(f"{name}: {total:,} rows below min {cfg['min_rows']:,}")
            grain = cfg.get("unique_grain")
            if grain:
                keys = ", ".join(f'"{k}"' for k in grain)
                distinct = self.con.execute(
                    f"SELECT count(*) FROM (SELECT DISTINCT {keys} FROM {name})"
                ).fetchone()[0]
                if distinct != total:
                    issues.append(f"{name}: grain {grain} not unique ({total - distinct:,} dup rows)")
                else:
                    self.log(f"  {name}: grain {grain} unique")
            self.check(f"POST-VIEW: {name}", issues)

    # ── orchestration ──────────────────────────────────────────────────────
    def run(self) -> int:
        self.register_sources()
        self.apply_derived_columns()
        self.validate_sources()
        self.build_views()
        self.profile_views()
        self.validate_views()

        report_path = os.path.join(self.reports_dir, "validation_report.txt")
        with open(report_path, "w", encoding="utf-8") as fh:
            fh.write("\n".join(self.report))
        self.log("\n" + "=" * 70)
        self.log(f"Done. {self.failures} failed check(s).")
        self.log(f"  Views:   {self.views_dir}")
        self.log(f"  Reports: {report_path}")
        self.log("=" * 70)

        if self.strict and self.failures:
            print(f"\n--strict: {self.failures} failed check(s); exiting non-zero.")
            return 1
        return 0


def _sql_str(s: str) -> str:
    """Escape a Python string for embedding in a single-quoted SQL literal."""
    return s.replace("\\", "/").replace("'", "''")


def main() -> int:
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    p = argparse.ArgumentParser(description="Generic domain-pack view runner (DuckDB).")
    p.add_argument("--pack", default=os.path.join(base, "domain_pack"))
    p.add_argument("--data-dir", default=os.path.join(base, "ab_data"))
    p.add_argument("--views-dir", default=os.path.join(base, "views"))
    p.add_argument("--reports-dir", default=os.path.join(base, "reports"))
    p.add_argument("--strict", action="store_true",
                   help="exit non-zero on any failed validation check")
    args = p.parse_args()

    return Runner(args.pack, args.data_dir, args.views_dir,
                  args.reports_dir, args.strict).run()


if __name__ == "__main__":
    sys.exit(main())
