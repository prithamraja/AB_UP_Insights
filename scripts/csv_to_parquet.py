#!/usr/bin/env python
"""
csv_to_parquet.py — convert a directory of source CSVs to Parquet, losslessly.

Each <name>.csv becomes <name>.parquet (zstd) next to it, holding the CSV's
exact text: every column VARCHAR, empty fields NULL — the same relation
build_views.py gets from read_csv(all_varchar=true). The column types DuckDB's
read_csv_auto sniffs from the CSV are stored in the file's key/value metadata
(`csv_sniffed_types`), so the backend's local DuckDB adapter can cast back to
exactly the tables it used to build from the CSVs.

Every file is verified before its CSV may be deleted:
  1. raw text  read_parquet == read_csv(all_varchar=true)   (ordered, null-aware)
  2. typed     CAST(read_parquet AS sniffed types) == read_csv_auto
  3. no quoted-empty ("") fields — readers that re-emit the text as CSV write
     NULLs as unquoted empties, so a "" would not survive the round trip as-is.
A file that fails keeps its CSV and gets no Parquet.

Usage:
  python scripts/csv_to_parquet.py [DATA_DIR] [--delete-csv]

DATA_DIR defaults to ab_data/ at the repo root; subdirectories are included.
--delete-csv removes each CSV only after its Parquet passes verification.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import tempfile
from pathlib import Path

import duckdb

QUOTED_EMPTY = re.compile(rb'(^|,)""(,|\r?$)', re.M)


def _lit(path: Path) -> str:
    return "'" + path.as_posix().replace("'", "''") + "'"


def _same(con, sql_a: str, sql_b: str) -> bool:
    return con.execute(sql_a).to_arrow_table().equals(con.execute(sql_b).to_arrow_table())


def convert(con, csv_path: Path) -> tuple[Path, list[str]]:
    """Write <csv>.parquet next to the CSV; return (parquet path, failed checks)."""
    pq_path = csv_path.with_suffix(".parquet")
    raw = f"read_csv({_lit(csv_path)}, all_varchar=true, header=true)"
    auto = f"read_csv_auto({_lit(csv_path)}, header=true)"
    types = [[c, t] for c, t, *_ in con.execute(f"DESCRIBE SELECT * FROM {auto}").fetchall()]
    meta = json.dumps(types).replace("'", "''")
    con.execute(
        f"COPY (SELECT * FROM {raw}) TO {_lit(pq_path)} "
        f"(FORMAT parquet, COMPRESSION zstd, KV_METADATA {{csv_sniffed_types: '{meta}'}})"
    )

    stored = f"read_parquet({_lit(pq_path)})"
    casts = ", ".join(f'CAST("{c}" AS {t}) AS "{c}"' for c, t in types)
    failed = []
    if not _same(con, f"SELECT * FROM {raw}", f"SELECT * FROM {stored}"):
        failed.append("raw text differs")
    if not _same(con, f"SELECT * FROM {auto}", f"SELECT {casts} FROM {stored}"):
        failed.append("sniffed-type cast differs from read_csv_auto")
    if QUOTED_EMPTY.search(csv_path.read_bytes()):
        failed.append('has quoted-empty ("") fields')
    if failed:
        pq_path.unlink()  # never leave an unverified parquet for readers to prefer
    return pq_path, failed


def main() -> int:
    repo = Path(__file__).resolve().parent.parent
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("data_dir", nargs="?", type=Path, default=repo / "ab_data")
    p.add_argument("--delete-csv", action="store_true",
                   help="delete each CSV once its Parquet passes verification")
    args = p.parse_args()

    con = duckdb.connect()
    # DuckDB cannot write its temp files on a Google Drive mount.
    tmp = Path(tempfile.gettempdir()) / "duckdb_csv_to_parquet"
    tmp.mkdir(exist_ok=True)
    con.execute(f"SET temp_directory={_lit(tmp)}")

    csvs = sorted(args.data_dir.rglob("*.csv"))
    if not csvs:
        print(f"No CSVs under {args.data_dir}")
        return 1

    bad = size_in = size_out = 0
    for csv_path in csvs:
        rel = csv_path.relative_to(args.data_dir)
        pq_path, failed = convert(con, csv_path)
        if failed:
            bad += 1
            print(f"  FAIL {rel}: {'; '.join(failed)} (CSV kept, no parquet written)")
            continue
        size_in += csv_path.stat().st_size
        size_out += pq_path.stat().st_size
        print(f"  ok   {rel}: {csv_path.stat().st_size / 1e6:.1f} MB -> {pq_path.stat().st_size / 1e6:.1f} MB")
        if args.delete_csv:
            csv_path.unlink()

    print(f"\n{len(csvs) - bad}/{len(csvs)} verified: {size_in / 1e6:.0f} MB of CSV -> "
          f"{size_out / 1e6:.0f} MB of Parquet" + (" (CSVs deleted)" if args.delete_csv else ""))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
