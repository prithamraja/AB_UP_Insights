# Phase 4b: All Four Views

## Overview

This phase adds view configurations for Views 2, 3, and 4, then runs the engine (with all 11 pattern types, HDP dedup, and SUM/AVG aggregation support) on all four views independently. Each view produces its own candidate list. Cross-view deduplication happens in Phase 5.

**Prerequisites:** Before running, ensure:
1. All 11 pattern types from Phase 4a are implemented
2. HDP dedup is implemented
3. `MeasureConfig` and AVG aggregation support from the engine_avg_aggregation spec are implemented
4. View 4's parquet includes the `claim_rate` derived column (add `v4["claim_rate"] = v4["has_claim"]` in Phase 1 and rebuild)

**Inputs:**
- `views/view1_claims_lifecycle.parquet` (22,500 rows)
- `views/view2_district_month_cube.parquet` (3,589 rows)
- `views/view3_hospital_performance.parquet` (7,336 rows)
- `views/view4_beneficiary_journey.parquet` (205,847 rows)

**Outputs:**
- `metainsights/view1_candidates.json`
- `metainsights/view2_candidates.json`
- `metainsights/view3_candidates.json`
- `metainsights/view4_candidates.json`
- `reports/engine_diagnostics_all_views.txt`

**Code changes:** View configs only. The engine, pattern evaluators, scoring, and HDP dedup are unchanged.

---

## View Configurations

### View 1 — Claims Lifecycle

**Grain:** One row per case (22,500 rows). 13 categorical dimensions, 3 temporal, 12 measures.

```python
VIEW1_CONFIG = ViewConfig(
    name="Claims Lifecycle",
    parquet_path="views/view1_claims_lifecycle.parquet",

    dimensions=[
        "division",              # 18
        "district",              # 75
        "hospital_type",         # 2
        "hospital_sub_type",     # 8
        "specialty_code",        # 11
        "disease_category",      # 5
        "gender",                # 2
        "age_group",             # 4
        "admission_type",        # 2
        "discharge_type",        # 5
        "claim_status",          # 5
        "preauth_status",        # 4
        "bed_size_bucket",       # 4
    ],

    temporal_dimensions=[
        "admission_month",       # ~36
        "admission_quarter",     # ~13
        "admission_year",        # ~4
    ],

    measures=[
        MeasureConfig("case_count",             "sum"),
        MeasureConfig("amount_claimed",         "sum"),
        MeasureConfig("amount_approved",        "sum"),
        MeasureConfig("amount_paid",            "sum"),
        MeasureConfig("length_of_stay",         "avg"),
        MeasureConfig("is_emergency",           "sum"),
        MeasureConfig("is_death",               "sum"),
        MeasureConfig("is_lama_dama",           "sum"),
        MeasureConfig("settlement_tat_days",    "avg"),
        MeasureConfig("query_count",            "sum"),
        MeasureConfig("base_amount",            "sum"),
        MeasureConfig("computed_final_amount",  "sum"),
    ],

    impact_measures=["case_count", "amount_claimed", "amount_paid"],
    max_subspace_depth=2,
    tau=0.5,
    min_impact=0.01,
    min_hdp_size=3,
)
```

---

### View 2 — District-Month Performance Cube

**Grain:** One row per district × month (3,589 rows). 2 categorical dimensions, 3 temporal, 26 measures.

This view's strength is temporal patterns per district. Filtering to a division or district and breaking down by month gives a time series where Trend, Seasonality, Change Point, Outlier, and Unimodality can operate.

```python
VIEW2_CONFIG = ViewConfig(
    name="District-Month Performance Cube",
    parquet_path="views/view2_district_month_cube.parquet",

    dimensions=[
        "division",              # 18
        "district",              # 75
    ],

    temporal_dimensions=[
        "month",                 # ~50
        "quarter",               # ~17
        "year",                  # ~5
    ],

    measures=[
        MeasureConfig("new_beneficiaries",              "sum"),
        MeasureConfig("new_households",                 "sum"),
        MeasureConfig("cases_admitted",                 "sum"),
        MeasureConfig("emergency_cases",                "sum"),
        MeasureConfig("portability_cases",              "sum"),
        MeasureConfig("deaths",                         "sum"),
        MeasureConfig("lama_dama_cases",                "sum"),
        MeasureConfig("public_cases",                   "sum"),
        MeasureConfig("private_cases",                  "sum"),
        MeasureConfig("unique_hospitals",               "avg"),
        MeasureConfig("cards_issued",                   "sum"),
        MeasureConfig("claims_submitted",               "sum"),
        MeasureConfig("claims_approved",                "sum"),
        MeasureConfig("claims_rejected",                "sum"),
        MeasureConfig("amount_claimed",                 "sum"),
        MeasureConfig("amount_approved",                "sum"),
        MeasureConfig("amount_paid",                    "sum"),
        MeasureConfig("payment_count",                  "sum"),
        MeasureConfig("payment_failures",               "sum"),
        MeasureConfig("cumulative_beneficiaries",       "avg"),
        MeasureConfig("claims_per_1000_beneficiaries",  "avg"),
        MeasureConfig("approval_rate",                  "avg"),
        MeasureConfig("emergency_share",                "avg"),
        MeasureConfig("death_rate",                     "avg"),
        MeasureConfig("public_private_ratio",           "avg"),
        MeasureConfig("avg_claim_amount",               "avg"),
    ],

    impact_measures=["cases_admitted", "amount_claimed", "cumulative_beneficiaries"],
    max_subspace_depth=1,
    tau=0.5,
    min_impact=0.01,
    min_hdp_size=3,
)
```

**Design notes:**
- `max_subspace_depth=1`: Only 2 categorical dimensions (division, district). Depth-2 filters to a single district — no siblings for HDP extension.
- Ratio/rate measures use AVG: `approval_rate`, `emergency_share`, `death_rate`, `claims_per_1000_beneficiaries`, `public_private_ratio`, `avg_claim_amount` are pre-computed rates at the district-month grain. AVG across the breakdown gives the mean rate, which is the correct aggregation for comparing subgroups.
- `unique_hospitals` uses AVG: SUM of monthly unique counts would double-count hospitals active in multiple months.
- `avg_length_of_stay` and `avg_settlement_tat` are excluded — ~27% nulls and they're pre-computed averages where even AVG(AVG) is not a properly weighted mean.

---

### View 3 — Hospital Performance

**Grain:** One row per hospital × specialty (7,336 rows). 6 categorical dimensions, 0 temporal, 20 measures.

No temporal dimension — only categorical pattern types (Outstanding #1/#Last, Top/Last-Two, Evenness, Attribution). This is where underutilization analysis and specialty gap patterns live.

```python
VIEW3_CONFIG = ViewConfig(
    name="Hospital Performance",
    parquet_path="views/view3_hospital_performance.parquet",

    dimensions=[
        "specialty_code",        # 15
        "division",              # 18
        "district",              # 75
        "hospital_type",         # 2
        "hospital_sub_type",     # 8
        "bed_size_bucket",       # 4
    ],

    temporal_dimensions=[],

    measures=[
        MeasureConfig("admissions_prev_fy",         "sum"),
        MeasureConfig("admissions_before_last_year", "sum"),
        MeasureConfig("total_bed_strength",         "sum"),
        MeasureConfig("inpatient_beds",             "sum"),
        MeasureConfig("cases_treated",              "sum"),
        MeasureConfig("preauth_approved",           "sum"),
        MeasureConfig("preauth_rejected",           "sum"),
        MeasureConfig("claims_approved",            "sum"),
        MeasureConfig("amount_claimed",             "sum"),
        MeasureConfig("amount_approved",            "sum"),
        MeasureConfig("amount_paid",                "sum"),
        MeasureConfig("emergency_count",            "sum"),
        MeasureConfig("death_count",                "sum"),
        MeasureConfig("total_staff",                "avg"),
        MeasureConfig("avg_experience_years",       "avg"),
        MeasureConfig("total_licenses",             "avg"),
        MeasureConfig("expired_licenses",           "avg"),
        MeasureConfig("active_licenses",            "avg"),
        MeasureConfig("zero_claim_flag",            "sum"),
        MeasureConfig("cases_per_bed",              "avg"),
    ],

    impact_measures=["total_bed_strength", "cases_treated", "amount_paid"],
    max_subspace_depth=2,
    tau=0.5,
    min_impact=0.01,
    min_hdp_size=3,
)
```

**Design notes:**
- No temporal dimensions → only 6 categorical pattern types evaluated.
- Hospital-level attributes (`total_staff`, `total_licenses`, `expired_licenses`, `active_licenses`) use AVG. These values are duplicated across specialty rows for the same hospital — SUM would over-count hospitals with more specialties.
- `total_bed_strength` and `inpatient_beds` stay as SUM despite the same duplication issue, because `total_bed_strength` is an impact measure (impact always uses SUM). The over-counting is a consistent bias that preserves relative rankings.
- `avg_experience_years` and `cases_per_bed` use AVG — they're rates/averages.
- Excluded dimensions: `has_ot`, `has_icu` (booleans, only 2 values < min_hdp_size), `accreditation_level` (34.5% null, only 2 non-null values), `hospital_id`/`hospital_specialty_id` (PKs).
- Excluded measures: `avg_settlement_tat` (9.3% null, pre-computed average).

---

### View 4 — Beneficiary Journey

**Grain:** One row per beneficiary (205,847 rows). 9 categorical dimensions, 0 temporal, 7 measures.

Largest DataFrame. No temporal dimension. Focus is demographic and geographic patterns in scheme uptake and utilization.

**Requires:** `claim_rate` column added to the parquet (see Prerequisites).

```python
VIEW4_CONFIG = ViewConfig(
    name="Beneficiary Journey",
    parquet_path="views/view4_beneficiary_journey.parquet",

    dimensions=[
        "division",              # 18
        "district",              # 75
        "gender",                # 2
        "age_group",             # 4
        "entitlement_source",    # 3
        "bis_record_status",     # 3
        "enrolment_status",      # 4
        "card_status",           # 3 (+ 5% null)
        "document_count_bucket", # 2
    ],

    temporal_dimensions=[],

    measures=[
        MeasureConfig("document_count",             "avg"),
        MeasureConfig("has_aadhaar",                "avg"),
        MeasureConfig("claim_count",                "sum"),
        MeasureConfig("has_claim",                  "sum"),
        MeasureConfig("claim_rate",                 "avg"),
        MeasureConfig("days_enrolment_to_card",     "avg"),
        MeasureConfig("days_card_to_first_claim",   "avg"),
    ],

    impact_measures=["has_claim", "claim_count"],
    max_subspace_depth=2,
    tau=0.5,
    min_impact=0.01,
    min_hdp_size=3,
)
```

**Design notes:**
- No temporal dimensions → categorical patterns only.
- `claim_rate` (alias of `has_claim`) with AVG gives "proportion who claimed" — the key utilization rate metric. `has_claim` with SUM gives "count of claimants" — the volume metric.
- `days_enrolment_to_card` and `days_card_to_first_claim` use AVG — gives mean wait time per subgroup. High nulls (90% for days_card_to_first_claim) means AVG is computed over only the beneficiaries with values. Pattern evaluators' minimum size checks protect against unstable averages.
- `has_aadhaar` with AVG gives "proportion with Aadhaar" per subgroup — useful for identifying demographics/regions with low Aadhaar penetration.
- `document_count` with AVG gives "average documents per beneficiary" — identifies subgroups with incomplete documentation.
- Excluded: `beneficiary_id` (PK), `is_duplicate` (97/3 split), `auth_mode` (nearly uniform — would flood results with trivial Evenness patterns), `total_amount_claimed`/`total_amount_approved` (89.6% null).

---

## Running Phase 4b

### Test Run (10 minutes total)

```python
import os

os.makedirs("metainsights", exist_ok=True)
os.makedirs("reports", exist_ok=True)

ALL_CONFIGS = [
    ("view1", VIEW1_CONFIG, 300),    # 5 min
    ("view2", VIEW2_CONFIG, 120),    # 2 min
    ("view3", VIEW3_CONFIG, 120),    # 2 min
    ("view4", VIEW4_CONFIG, 60),     # 1 min — verify it handles 205K rows
]

all_diagnostics = {}

for view_name, config, budget in ALL_CONFIGS:
    print(f"\n{'=' * 70}")
    print(f"Running: {config.name}")
    print(f"{'=' * 70}")
    
    candidates, diagnostics = run_engine(config, time_budget_seconds=budget)
    
    save_candidates(candidates, f"metainsights/{view_name}_candidates.json")
    all_diagnostics[view_name] = diagnostics

save_all_view_diagnostics(all_diagnostics, "reports/engine_diagnostics_all_views.txt")
```

### Production Run (when on cloud)

```python
ALL_CONFIGS = [
    ("view1", VIEW1_CONFIG, 900),
    ("view2", VIEW2_CONFIG, 600),
    ("view3", VIEW3_CONFIG, 600),
    ("view4", VIEW4_CONFIG, 900),
]
```

---

## Combined Diagnostics Output

```python
def save_all_view_diagnostics(all_diagnostics: dict, output_path: str):
    """Save a combined diagnostics report across all views."""
    lines = [
        "=" * 70,
        "METAINSIGHT ENGINE DIAGNOSTICS — ALL VIEWS",
        "=" * 70,
        "",
    ]
    
    total_candidates = 0
    total_scopes = 0
    total_patterns = 0
    total_hdps = 0
    total_skipped = 0
    
    for view_name, diag in all_diagnostics.items():
        candidates_path = f"metainsights/{view_name}_candidates.json"
        import json
        with open(candidates_path) as f:
            n_candidates = len(json.load(f))
        
        total_candidates += n_candidates
        total_scopes += diag["scopes_evaluated"]
        total_patterns += diag["patterns_found"]
        total_hdps += diag["hdps_evaluated"]
        total_skipped += diag["hdps_skipped"]
        
        lines.append(f"--- {view_name} ---")
        lines.append(f"  Time:             {diag['elapsed']:.1f}s")
        lines.append(f"  Scopes evaluated: {diag['scopes_evaluated']:,}")
        lines.append(f"  Patterns found:   {diag['patterns_found']:,}")
        lines.append(f"  HDPs evaluated:   {diag['hdps_evaluated']:,}")
        lines.append(f"  HDPs skipped:     {diag['hdps_skipped']:,}")
        lines.append(f"  Candidates:       {n_candidates:,}")
        lines.append(f"  Query cache HR:   {diag['query_cache'].hit_rate:.1%}")
        lines.append(f"  Pattern cache HR: {diag['pattern_cache'].hit_rate:.1%}")
        lines.append("")
    
    lines.append("--- TOTALS ---")
    lines.append(f"  Total candidates: {total_candidates:,}")
    lines.append(f"  Total scopes:     {total_scopes:,}")
    lines.append(f"  Total patterns:   {total_patterns:,}")
    lines.append(f"  Total HDPs:       {total_hdps:,}")
    lines.append(f"  Total skipped:    {total_skipped:,}")
    
    with open(output_path, "w") as f:
        f.write("\n".join(lines))
    print(f"\nCombined diagnostics -> {output_path}")
```

---

## Validation Checklist

### Per-View Checks

**View 1:**
- [ ] Results comparable to Phase 4a (same pattern types, similar top candidates)
- [ ] AVG measures (`length_of_stay`, `settlement_tat_days`) produce plausible values (2-6 days, 5-20 days)

**View 2:**
- [ ] Temporal patterns appear (TREND, SEASONALITY on monthly breakdown)
- [ ] AVG ratio measures produce meaningful patterns (e.g., "district X has the highest average approval_rate")
- [ ] `claims_per_1000_beneficiaries` produces Outstanding patterns identifying high/low utilization districts
- [ ] Partial-month outlier (2023-02 or 2022-02) likely appears

**View 3:**
- [ ] Only categorical patterns (no temporal types)
- [ ] `zero_claim_flag` patterns appear (underutilization)
- [ ] `cases_per_bed` AVG patterns appear (utilization rate outliers)
- [ ] AVG measures (`total_staff`, `avg_experience_years`, `cases_per_bed`) produce plausible values

**View 4:**
- [ ] Only categorical patterns
- [ ] `claim_rate` AVG patterns appear — identifies demographic/geographic segments with higher scheme uptake
- [ ] `days_enrolment_to_card` AVG patterns appear — identifies districts with slow card processing
- [ ] Engine handles 205K rows without memory issues
- [ ] At least some candidates produced within 60s test budget

### Cross-View Checks
- [ ] All four views produce at least 50 candidates each (even with short test budgets)
- [ ] No crashes or errors
- [ ] Total test runtime under 12 minutes

### What to bring back

1. `reports/engine_diagnostics_all_views.txt`
2. Per-view: candidate count, top-3 candidates (brief summary), pattern type distribution
3. Any pattern types producing zero candidates in any view
4. Any errors
5. Total runtime
