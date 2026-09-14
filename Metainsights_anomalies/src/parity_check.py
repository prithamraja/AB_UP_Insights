#!/usr/bin/env python
"""Parity harness — verify a refactor leaves the analytical views unchanged.

Compares two directories of Parquet views (e.g. old pandas pipeline vs new
build_views.py). For each view it checks: identical row count, identical
column-name set, matching PHYSICAL Parquet types, and value equality after
sorting by the view's grain key (numerics within tolerance; strings/flags/bools
exact; NaN == NaN).

pandas' optional nullable-dtype hint (`boolean` vs `bool`, `Int64` vs `int64`)
is a write-time metadata flag on the same physical type and identical values, so
it is reported as informational, not a failure.

    python src/parity_check.py --old-dir views_old --new-dir views_new [view ...]
"""
from __future__ import annotations

import argparse
import sys

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

# view name -> grain key columns (the sort key for row-wise comparison)
GRAIN = {
    "view1_claims_lifecycle":     ["case_id"],
    "view2_district_month_cube":  ["district", "month"],
    "view3_hospital_performance": ["hospital_specialty_id"],
    "view4_beneficiary_journey":  ["beneficiary_id"],
}
RTOL, ATOL = 1e-9, 1e-6


def compare(view: str, old_dir: str, new_dir: str) -> bool:
    old = pd.read_parquet(f"{old_dir}/{view}.parquet")
    new = pd.read_parquet(f"{new_dir}/{view}.parquet")
    so = pq.read_schema(f"{old_dir}/{view}.parquet")
    sn = pq.read_schema(f"{new_dir}/{view}.parquet")
    print(f"\n===== {view} =====")
    ok = True

    if len(old) != len(new):
        print(f"  ROWCOUNT MISMATCH: old={len(old):,} new={len(new):,}")
        ok = False
    else:
        print(f"  rows: {len(old):,} (match)")

    old_cols, new_cols = set(old.columns), set(new.columns)
    if old_cols != new_cols:
        print(f"  COLUMN MISMATCH: only-old={old_cols - new_cols}  only-new={new_cols - old_cols}")
        ok = False
    common = [c for c in old.columns if c in new_cols]

    for c in common:
        if str(so.field(c).type) != str(sn.field(c).type):
            print(f"  DTYPE {c}: old={so.field(c).type} new={sn.field(c).type}")
            ok = False
        elif str(old[c].dtype) != str(new[c].dtype):
            print(f"  (info) {c}: pandas dtype old={old[c].dtype} new={new[c].dtype} "
                  f"(same physical type {sn.field(c).type}; nullable-hint only)")

    if len(old) != len(new):
        return ok

    grain = GRAIN.get(view)
    if grain is None:
        print(f"  (no grain key registered for {view}; skipping value diff)")
        print("  RESULT:", "PASS" if ok else "FAIL")
        return ok
    old_s = old.sort_values(grain, kind="mergesort").reset_index(drop=True)
    new_s = new.sort_values(grain, kind="mergesort").reset_index(drop=True)

    for c in common:
        o, n = old_s[c], new_s[c]
        numeric = (pd.api.types.is_numeric_dtype(o) and pd.api.types.is_numeric_dtype(n)
                   and not pd.api.types.is_bool_dtype(o))
        if numeric:
            of = o.astype("float64").to_numpy()
            nf = n.astype("float64").to_numpy()
            bad = ~np.isclose(of, nf, rtol=RTOL, atol=ATOL, equal_nan=True)
            if bad.any():
                idx = np.where(bad)[0][:3]
                print(f"  VALUE {c}: {int(bad.sum()):,} numeric diffs "
                      f"e.g. {[(int(i), of[i], nf[i]) for i in idx]}")
                ok = False
        else:
            oo = o.astype("object").where(o.notna(), "<NA>").to_numpy()
            nn = n.astype("object").where(n.notna(), "<NA>").to_numpy()
            bad = oo != nn
            if bad.any():
                idx = np.where(bad)[0][:3]
                print(f"  VALUE {c}: {int(bad.sum()):,} diffs "
                      f"e.g. {[(int(i), oo[i], nn[i]) for i in idx]}")
                ok = False

    print("  RESULT:", "PASS" if ok else "FAIL")
    return ok


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--old-dir", required=True)
    p.add_argument("--new-dir", required=True)
    p.add_argument("views", nargs="*", help="views to compare (default: all known)")
    args = p.parse_args()

    views = args.views or list(GRAIN)
    results = {v: compare(v, args.old_dir, args.new_dir) for v in views}
    print("\n===== SUMMARY =====")
    for v, r in results.items():
        print(f"  {v}: {'PASS' if r else 'FAIL'}")
    return 0 if all(results.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
