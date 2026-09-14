# Domain Pack format

A **domain pack** is everything domain-specific the analytical-view pipeline
needs, expressed declaratively (YAML + SQL) — no Python. The generic runner
[`src/build_views.py`](../src/build_views.py) executes a pack on DuckDB and
materialises one Parquet view per SQL file. Standing up "Discover" for a new
ministry / dataset means writing a new pack; the runner never changes.

This pack (`domain_pack/`) is the reference implementation for the Ayushman
Bharat PM-JAY (Uttar Pradesh) dataset. Future domains (e.g. PDS Maharashtra,
Education Indonesia) should copy its structure.

```
domain_pack/
├── sources.yaml          # per-table: CSV file, column type casts, expected rows
├── derived_columns.sql   # staging views that add derived columns (stg_*)
├── views/                # one *.sql per output view -> one *.parquet
│   ├── view1_....sql
│   └── ...
├── validation.yaml       # PK / FK / null / categorical / date + post-view checks
└── README.md             # this file
```

## How the runner uses the pack

`build_views.py` runs six ordered steps. Each reads only from the pack — the
runner contains **no** table or column names.

| Step | What it does | Pack input |
|------|--------------|------------|
| 1. Register sources | One typed DuckDB view per source file (Parquet or CSV), named exactly like the table | `sources.yaml` |
| 2. Derived columns  | Runs the SQL, creating `stg_<table>` views | `derived_columns.sql` |
| 3. Pre-view validation | Row counts, PK, FK, null rates, categoricals, date ranges | `sources.yaml`, `validation.yaml` |
| 4. Build views | Runs each `views/*.sql`, `COPY … TO <name>.parquet` | `views/*.sql` |
| 5. Profile | Per-view/column stats → `reports/view_summaries.txt` | (generic) |
| 6. Post-view checks | Row-count + grain expectations per view | `validation.yaml` → `post_view` |

Run it:

```bash
python src/build_views.py \
    [--pack domain_pack] [--data-dir ab_data] \
    [--views-dir views] [--reports-dir reports] [--strict]
```

All paths default to today's layout. `--strict` exits non-zero if any
validation check fails (for CI / automation); default mode logs failures and
continues. **Validation never drops or fixes rows** — data-quality issues in the
source are analytically meaningful and must flow through to the views.

> **Environment note.** DuckDB spills temp files that cannot be written on a
> Google Drive mount. The runner points DuckDB's `temp_directory` at the local
> system temp dir, so you can keep the CSVs and outputs on Drive. If you hit
> temp-write errors anyway, run with `--data-dir`/`--views-dir` pointing at a
> local copy.

## `sources.yaml`

```yaml
row_count_tolerance_pct: 20     # CHECK 1 tolerance for expected_rows
tables:
  <table_name>:
    file: <filename>.parquet      # or .csv; inside --data-dir
    expected_rows: 22500          # optional; CHECK 1 applies the tolerance
    casts:                        # optional; everything else stays a string
      <column>: timestamp | date | float | int | bool
```

The runner reads every source as raw text — CSVs with `all_varchar=true` (no
type sampling — a reproducibility hazard) — and applies these casts explicitly.
IDs and any column not listed under `casts` stay `VARCHAR`. A `.parquet` source
must hold that same raw text (every column `VARCHAR`), which is what
`scripts/csv_to_parquet.py` writes; the repo's `ab_data/` ships that way.

**Cast semantics** (see `_cast` in the runner):

| type | DuckDB | notes |
|------|--------|-------|
| `timestamp` | `CAST(col AS TIMESTAMPTZ) AT TIME ZONE 'UTC'` | The session runs in UTC, so a naive string is assumed UTC and an offset-bearing string (e.g. `+05:30`) is converted to UTC, then the tz is stripped. Mirrors pandas `to_datetime(..., utc=True).tz_localize(None)`. |
| `date`  | `CAST(col AS DATE)`    | calendar date, no time |
| `float` | `CAST(col AS DOUBLE)`  | numeric measure |
| `int`   | `CAST(col AS BIGINT)`  | count / year / rank |
| `bool`  | `CAST(col AS BOOLEAN)` | `True`/`False` strings accepted |

## `derived_columns.sql`

A sequence of `CREATE OR REPLACE VIEW stg_<table> AS SELECT *, <derived exprs>
FROM <table>` statements. Give **every** table a `stg_` view (pass-through
`SELECT *` if it needs no derived columns) so the view SQL can reference a single
uniform namespace. Dataset-wide reference points (e.g. "latest admission year")
are written as scalar subqueries, not wall-clock values, so the pipeline is
reproducible.

## `views/*.sql`

One file per output view. The filename stem is the Parquet name
(`view1_claims_lifecycle.sql` → `view1_claims_lifecycle.parquet`). Reference
`stg_*` views. **Cast every output column to its target logical type** in the
final `SELECT` (dimensions → strings, flags → integers, measures → `DOUBLE`) so
the Parquet dtypes are stable and independent of aggregation quirks — downstream
engines read these files with pandas and pin column names and types.

Files are executed in sorted filename order.

## `validation.yaml`

```yaml
null_rate_threshold_pct: 20       # CHECK 4: log columns above this (never fails)
primary_keys: { <table>: <pk_col>, ... }                 # CHECK 2
foreign_keys:                                            # CHECK 3
  - {child: t, child_col: c, parent: p, parent_col: k}
categorical: { <table>: { <col>: [allowed, values] } }   # CHECK 5
date_ranges:                                             # CHECK 6
  min_years: 1
  max_years: 10
  columns: [{table: t, column: c}, ...]
post_view:                                               # step 6
  <view_name>:
    expected_rows: 22500      # OR min_rows: 1000
    tolerance_pct: 20
    unique_grain: [key, cols]
```

## Verifying a refactor (parity)

When changing how a view is built, prove the output is unchanged: run the old
and new pipelines to separate directories and compare each view for identical
row counts, identical column names, matching **physical** Parquet types, and
value equality after sorting by the view's grain key (numerics within a
tolerance; strings/flags/bools exact). A convenience harness lives in
`src/parity_check.py`. Note that pandas' optional nullable-dtype hint (`boolean`
vs `bool`, `Int64` vs `int64`) is a write-time metadata flag, not a physical or
logical type difference — compare physical Parquet types, not pandas dtypes.
