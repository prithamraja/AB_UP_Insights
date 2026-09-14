# Handoff: Rebuild MetaInsights Phase 1 as a config-driven DuckDB pipeline

## Why

`Metainsights_anomalies/src/phase1_pipeline.py` is a 1,290-line pandas script that ingests
the 21 PM-JAY CSVs and materialises the 4 analytical Parquet views the MetaInsight engine
consumes. Every line of domain knowledge (join chains, dedup rules, derived columns,
validation expectations) is interleaved with generic plumbing (CSV loading, type casting,
report writing, Parquet export).

We are turning this product into a replicable platform ("domain packs" for new ministries /
datasets). The goal of this task: **split phase 1 into (a) a generic, reusable runner and
(b) a declarative domain pack**, with all SQL executed by DuckDB instead of pandas. After
this refactor, standing up Discover for a new domain means writing YAML + SQL files only —
no Python.

**This is a pure refactor. The output Parquet files must be functionally identical to
today's.** Downstream consumers (`phase2_engine.py`, `phase4a_engine.py`, `phase4b_engine.py`)
read the Parquet files at `Metainsights_anomalies/views/*.parquet` and reference specific
column names in their hardcoded `VIEW1_CONFIG`…`VIEW4_CONFIG` objects. Do not rename any
output column, change any grain, or alter any metric definition.

---

## Target architecture

```
Metainsights_anomalies/
├── domain_pack/                     # NEW — everything domain-specific lives here
│   ├── sources.yaml                 # per-table: csv filename, column type casts,
│   │                                #   expected row count (+/- tolerance)
│   ├── derived_columns.sql          # staging views adding derived cols (SQL, see below)
│   ├── views/
│   │   ├── view1_claims_lifecycle.sql
│   │   ├── view2_district_month_cube.sql
│   │   ├── view3_hospital_performance.sql
│   │   └── view4_beneficiary_journey.sql
│   ├── view_configs.yaml            # dimensions / temporal_dimensions / measures /
│   │                                #   impact_measures + engine params per view
│   │                                #   (mirrors ViewConfig in phase2/4a — see "Step 2")
│   └── validation.yaml              # PK / FK / null / distribution checks (declarative)
├── src/
│   ├── build_views.py               # NEW — generic runner (replaces phase1_pipeline.py)
│   └── phase1_pipeline.py           # KEEP until parity is verified, then archive
└── views/                           # unchanged output location + filenames
```

### Generic runner (`build_views.py`) responsibilities, in order

1. **Register sources.** For each table in `sources.yaml`, create a DuckDB view over the
   CSV via `read_csv` with explicit column types (or a staging `SELECT` with casts).
   Never mutate the CSVs.
2. **Apply derived columns.** Execute `derived_columns.sql` — a sequence of
   `CREATE OR REPLACE VIEW stg_<table> AS SELECT *, <derived exprs> FROM <table>`
   statements. View SQL files reference `stg_*` names.
3. **Run validation checks** from `validation.yaml`. Write
   `reports/validation_report.txt`. **Replace the current interactive `input()` prompt**
   with a `--strict` CLI flag: strict mode exits non-zero on any failed check; default
   mode logs failures and continues. (The `input()` call blocks any automated run.)
   Checks log only — they never drop or fix rows; the data-quality issues are
   analytically meaningful and must flow through.
4. **Build views.** Execute each `views/*.sql` and `COPY (…) TO '<views_dir>/<name>.parquet'`.
5. **Profile.** Write `reports/view_summaries.txt` — row count, per-column dtype,
   null %, distinct count, min/max for each view. This is generic; no domain code.
6. **Post-view checks.** Row-count expectations per view from config (tolerances, not
   exact values).

CLI: `python src/build_views.py [--pack domain_pack] [--data-dir ab_data] [--views-dir views] [--strict]`.
All paths configurable; defaults preserve today's layout.

### Out of scope

- `data_fix.py` stays as-is. It is a synthetic-data repair script (backfills collapsed
  timestamps, regenerates `hm_specialty_offered`), not part of the generic pipeline.
  It still runs before the pipeline when needed.
- Do not touch phase 2/4/5 engines. (Externalising their `VIEW*_CONFIG` into
  `view_configs.yaml` is a stretch goal — see "Step 2" at the end.)
- No changes to the Chatbot backend.

---

## Semantics that MUST be preserved (the subtle stuff)

These are the behaviours embedded in the pandas code that are easy to lose in translation.
Read `phase1_pipeline.py` sections 4–8 alongside this list.

### Derived columns (section 4)

| Column | Rule |
|---|---|
| `age_group` (bm_beneficiary) | Age = `ref_year − yob` where **ref_year = MAX(year(admission_datetime)) over cm_case**, not today's date. Buckets: INFANT (<1), 1-5, 6-14, 15-25, 26-40, 41-60, 60+, UNKNOWN for null yob. |
| `admission_month/quarter/year` (cm_case) | String-typed. Month format `YYYY-MM`, quarter `YYYYQn` (e.g. `2024Q3` — match pandas `Period` rendering exactly; the engine treats these as categorical strings and sorts them lexically). |
| `length_of_stay` | Fractional days: `(discharge − admission)` in seconds / 86 400. |
| `is_emergency`, `is_death`, `is_lama_dama` | **Integer 0/1**, not boolean (engine SUMs them). LAMA/DAMA = discharge_type in (LAMA, DAMA). |
| `disease_category` (cm_case_diagnosis) | ICD-10 first-letter mapping: O,P→MATERNAL_NEONATAL; A,B→COMMUNICABLE; S,T→INJURY; I,E,J,N,C,D→NCD; K,H,G,M,L→SURGICAL; else OTHER; null→UNKNOWN. |
| `bed_size_bucket` (hm_hospital) | `SMALL (<=30)`, `MEDIUM (31-100)`, `LARGE (101-300)`, `VERY_LARGE (300+)`, `UNKNOWN` — exact strings including the parenthetical. |
| `is_expired` (hm_license_certificate) | Integer flag; expiry_date < **MAX(admission_datetime)** (dataset reference date, not wall clock). |

### View 1 — Claims Lifecycle (one row per case_id)

- Primary diagnosis only: `diagnosis_rank = 1`.
- Primary procedure line only: `procedure_rank = 1`.
- **Multiple claims per case → keep the first by `submitted_at`** (window/`QUALIFY row_number() = 1`).
- **Multiple preauths per case → keep the latest by `initiated_at`.** (Re-submissions after
  queries; joining undeduped multiplies rows and breaks the grain.)
- Payments aggregated per claim: `SUM(amount_paid)`, **modal** `payment_status`
  (DuckDB `mode()`).
- All joins LEFT, anchored on cm_case. `division`/`district` come from the **beneficiary's
  home** geography (bm_household), while `hospital_division`/`hospital_district` are the
  hospital's — both are kept, don't conflate them.
- Trailing `case_count = 1` convenience column.
- Final column list and rename map: copy from lines 663–684 of the old script verbatim.

### View 2 — District-Month Cube (one row per district × month)

- Five separate aggregates (enrolment, cards, cases, claims, payments), each grouped to
  district × month using **different date columns** (created_at, issued_at,
  admission_datetime, submitted_at, payment_date) and **beneficiary home district**
  throughout (cases are attributed to the patient's home district, not the hospital's).
- Combined with **FULL OUTER joins**; missing activity → **0** for the 19 count/sum
  columns (list at lines 808–815), then division backfilled via a district→division map.
- `cumulative_beneficiaries` = running SUM of `new_beneficiaries` per district ordered by
  month (window function). Documented choice: enrolment-based denominator, not
  card-based — keep the comment.
- Ratio metrics use **NULL (not 0) on zero denominators** (`NULLIF`), except
  `public_private_ratio = public_cases / (private_cases + 1)` — keep the +1 exactly.
- `quarter`/`year` derived from the month string.

### View 3 — Hospital Performance (one row per hospital × specialty offered)

- **Anchor on `hm_specialty_offered`**, LEFT-join activity: hospitals offering a
  specialty with zero cases must appear with `cases_treated = 0` and
  `zero_claim_flag = 1` — that's the underutilisation signal; an inner join silently
  destroys it.
- Specialty of a case comes via case → preauth → primary procedure line
  (`procedure_rank = 1`) → `ref_hbp_procedure_master.specialty_code`.
- Preauth approved = status in (AUTO_APPROVED, APPROVED); claims approved = status in
  (APPROVED, SETTLED).
- `cases_per_bed` NULL when bed strength is 0/null.
- Renames: `division_name→division`, `district_name→district`,
  `has_fully_equipped_ot→has_ot`, `has_icu_with_ac→has_icu`.

### View 4 — Beneficiary Journey (one row per beneficiary_id)

- Latest enrolment request and latest card per beneficiary (by submitted_at / issued_at).
- `document_count`, `has_aadhaar` (any doc_type = AADHAAR), fill 0.
- `claim_count` fill 0; `has_claim` 0/1; `claim_rate` = alias of has_claim (kept so the
  engine can AVG it as a proportion while SUMming has_claim as a count — keep both).
- `document_count_bucket`: NO_DOCS / 1_DOC / 2-3_DOCS / 4+_DOCS.
- Durations in fractional days: `days_enrolment_to_card`, `days_card_to_first_claim`.
- Drop the intermediate columns (household_id, created_at, card_issued_at,
  first_admission_date) from the final output.

### Type-casting rules (section 2)

Encode per-table in `sources.yaml`: which columns are timestamps (parse then **strip
timezone** — everything tz-naive), dates, floats, booleans. IDs stay strings. The
timestamp columns per table are listed at lines 194–281 of the old script.

---

## DuckDB translation notes / gotchas

- **Dedup "first/latest per group"**: use `QUALIFY row_number() OVER (PARTITION BY … ORDER BY …) = 1`.
- **Modal value**: DuckDB `mode(col)`.
- **Period strings**: `strftime(ts, '%Y-%m')` for month; quarter must render as
  `2024Q3` — build with `year(ts) || 'Q' || quarter(ts)`. Verify against the old
  parquet values byte-for-byte; the engine's temporal ordering depends on lexical sort.
- **Dtype fidelity**: the engines load the parquet with pandas. Match the old files'
  logical types: dims as strings, flags as integers, measures as DOUBLE. Run the
  comparison script (below) on dtypes, not just values.
- **Float sums**: DuckDB may sum in a different order than pandas → last-decimal
  differences. Compare numerics with a tolerance (e.g. rtol 1e-9), not equality.
- **Environment**: DuckDB cannot write its temp files on the Google Drive mount. Run the
  pipeline from a **local working directory** (copy or point `--data-dir` at the Drive
  CSVs read-only; write views/reports locally, then sync back). Same constraint applies
  to any test harness.
- Prefer `read_csv(…, types={…})` with explicit types over `auto_detect` — sampling-based
  detection is a reproducibility hazard.

---

## Verification plan (acceptance criteria)

1. **Parity harness** (small throwaway script, keep in `src/` or scratch):
   - Run old `phase1_pipeline.py` → `views_old/`; run new `build_views.py` → `views_new/`.
   - For each of the 4 views: identical row counts, identical column sets and order not
     required but **identical column names**, matching dtypes (per note above), and
     value equality after sorting by the view's grain key (numeric columns within
     tolerance; string/flag columns exact).
2. **Engine-level parity**: point `phase4b_engine.py` at the new views and diff the
   generated `metainsights/view*_candidates.json` against a run on the old views.
   Identical (or explainable-FP-only) output is the real acceptance test.
3. **Runner is domain-clean**: grep `build_views.py` for any PM-JAY table or column
   name — there must be none. Every domain string lives in `domain_pack/`.
4. **Non-interactive**: full pipeline runs end-to-end with no stdin.
5. Old script left in place until 1–2 pass; then move it to `Archive of md files`-style
   archival (coordinate with repo owner before deleting).

---

## Suggested order of work

1. Runner skeleton: sources.yaml loading, DuckDB registration, parquet export, reports.
2. `derived_columns.sql` + View 1 (richest view, most gotchas) → parity-check View 1.
3. Views 2–4 → parity-check each.
4. Port validation checks (section 3 of old script) into `validation.yaml` + runner
   support; add `--strict`.
5. Full parity run + phase4b diff.
6. Write a short `domain_pack/README.md` documenting the pack format — this doc is the
   template future domains (PDS Maharashtra, Education Indonesia) will follow, so write
   it for someone who has never seen the PM-JAY code.

## Step 2 (stretch, separate PR)

Externalise `VIEW1_CONFIG`…`VIEW4_CONFIG` (dimensions / temporal_dimensions / measures /
impact_measures / tau / max_subspace_depth / min_impact / min_hdp_size — currently
hardcoded in `phase2_engine.py` and re-exported by `phase4a_engine.py`) into
`domain_pack/view_configs.yaml`, with a small loader the engines import. Keep the
dataclass interface identical so the engine code doesn't change. Do this only after the
phase-1 parity work has landed.
