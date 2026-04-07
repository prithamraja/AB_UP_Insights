# Engine Upgrade: AVG Aggregation Support

## Overview

Add AVG as a second aggregation type alongside SUM. Each measure in a ViewConfig declares whether it should be aggregated with SUM or AVG. The engine respects this when querying data. No changes to pattern evaluators, HDP construction, scoring, or ranking.

**No new dependencies.**

---

## Changes

### 1. Update ViewConfig

Replace the flat `measures` list with a structured list that includes aggregation type:

```python
@dataclass
class MeasureConfig:
    """A measure with its aggregation type."""
    name: str
    agg: str = "sum"    # "sum" or "avg"


@dataclass
class ViewConfig:
    name: str
    parquet_path: str
    dimensions: list[str]
    temporal_dimensions: list[str]
    measures: list[MeasureConfig]       # changed from list[str]
    impact_measures: list[str]          # these are always SUM (impact = proportion of total)
    
    max_subspace_depth: int = 2
    tau: float = 0.5
    min_impact: float = 0.01
    min_hdp_size: int = 3
    
    @property
    def measure_names(self) -> list[str]:
        """All measure names (for iteration)."""
        return [m.name for m in self.measures]
    
    def get_agg(self, measure_name: str) -> str:
        """Get aggregation type for a measure."""
        for m in self.measures:
            if m.name == measure_name:
                return m.agg
        return "sum"  # default
```

### 2. Update query_data_scope

```python
def query_data_scope(df: pd.DataFrame, data_scope: DataScope, config: ViewConfig) -> pd.Series:
    """
    Execute grouped aggregation with the measure's configured agg type.
    SUM for additive measures, AVG for rates/durations.
    """
    filtered = apply_subspace(df, data_scope.subspace)
    if len(filtered) == 0:
        return pd.Series(dtype=float)
    
    agg_type = config.get_agg(data_scope.measure)
    
    if agg_type == "avg":
        result = filtered.groupby(data_scope.breakdown)[data_scope.measure].mean()
    else:
        result = filtered.groupby(data_scope.breakdown)[data_scope.measure].sum()
    
    return result.sort_index()
```

### 3. Update All Callers

`query_data_scope` now takes `config` as a third argument. Update calls in:

- `detect_pattern`: passes `config` (already available)
- Anywhere else `query_data_scope` is called directly

```python
# In detect_pattern:
distribution = query_data_scope(df, data_scope, config)    # add config

# In QueryCache — no change needed, cache is keyed by (subspace, breakdown, measure)
# The agg type is deterministic per measure name, so same key = same result
```

### 4. Update generate_data_scopes

This function iterates over measure names. Update to use the property:

```python
def generate_data_scopes(subspace: Subspace, config: ViewConfig) -> list[DataScope]:
    filtered_dims = {dim for dim, _ in subspace.filters}
    available_breakdowns = [
        d for d in config.dimensions + config.temporal_dimensions
        if d not in filtered_dims
    ]
    
    scopes = []
    for breakdown in available_breakdowns:
        for measure_name in config.measure_names:    # was: config.measures
            scopes.append(DataScope(subspace, breakdown, measure_name))
    return scopes
```

### 5. Update extend_measure

```python
def extend_measure(data_scope: DataScope, config: ViewConfig):
    sibling_scopes = []
    for measure_name in config.measure_names:        # was: config.measures
        sibling_scopes.append(DataScope(data_scope.subspace, data_scope.breakdown, measure_name))
    
    if len(sibling_scopes) >= config.min_hdp_size:
        return [("measure", "measure", sibling_scopes)]
    return []
```

---

## Updated View Configs

### View 1 — Claims Lifecycle

```python
VIEW1_CONFIG = ViewConfig(
    name="Claims Lifecycle",
    parquet_path="views/view1_claims_lifecycle.parquet",
    
    dimensions=[
        "division", "district", "hospital_type", "hospital_sub_type",
        "specialty_code", "disease_category", "gender", "age_group",
        "admission_type", "discharge_type", "claim_status",
        "preauth_status", "bed_size_bucket",
    ],
    
    temporal_dimensions=["admission_month", "admission_quarter", "admission_year"],
    
    measures=[
        MeasureConfig("case_count",             "sum"),
        MeasureConfig("amount_claimed",         "sum"),
        MeasureConfig("amount_approved",        "sum"),
        MeasureConfig("amount_paid",            "sum"),
        MeasureConfig("length_of_stay",         "avg"),     # was sum — avg is more meaningful
        MeasureConfig("is_emergency",           "sum"),     # sum = count of emergencies
        MeasureConfig("is_death",               "sum"),     # sum = count of deaths
        MeasureConfig("is_lama_dama",           "sum"),     # sum = count of LAMA/DAMA
        MeasureConfig("settlement_tat_days",    "avg"),     # was sum — avg is more meaningful
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

### View 2 — District-Month Performance Cube

```python
VIEW2_CONFIG = ViewConfig(
    name="District-Month Performance Cube",
    parquet_path="views/view2_district_month_cube.parquet",
    
    dimensions=["division", "district"],
    temporal_dimensions=["month", "quarter", "year"],
    
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
        MeasureConfig("unique_hospitals",               "avg"),     # avg monthly count (SUM would double-count across months)
        MeasureConfig("cards_issued",                   "sum"),
        MeasureConfig("claims_submitted",               "sum"),
        MeasureConfig("claims_approved",                "sum"),
        MeasureConfig("claims_rejected",                "sum"),
        MeasureConfig("amount_claimed",                 "sum"),
        MeasureConfig("amount_approved",                "sum"),
        MeasureConfig("amount_paid",                    "sum"),
        MeasureConfig("payment_count",                  "sum"),
        MeasureConfig("payment_failures",               "sum"),
        MeasureConfig("cumulative_beneficiaries",       "avg"),     # avg across time = typical level
        MeasureConfig("claims_per_1000_beneficiaries",  "avg"),     # rate — must be averaged
        MeasureConfig("approval_rate",                  "avg"),     # rate
        MeasureConfig("emergency_share",                "avg"),     # rate
        MeasureConfig("death_rate",                     "avg"),     # rate
        MeasureConfig("public_private_ratio",           "avg"),     # ratio
        MeasureConfig("avg_claim_amount",               "avg"),     # already an average
    ],
    
    impact_measures=["cases_admitted", "amount_claimed", "cumulative_beneficiaries"],
    max_subspace_depth=1,
    tau=0.5,
    min_impact=0.01,
    min_hdp_size=3,
)
```

### View 3 — Hospital Performance

```python
VIEW3_CONFIG = ViewConfig(
    name="Hospital Performance",
    parquet_path="views/view3_hospital_performance.parquet",
    
    dimensions=[
        "specialty_code", "division", "district",
        "hospital_type", "hospital_sub_type", "bed_size_bucket",
    ],
    temporal_dimensions=[],
    
    measures=[
        MeasureConfig("admissions_prev_fy",         "sum"),
        MeasureConfig("admissions_before_last_year", "sum"),
        MeasureConfig("total_bed_strength",         "sum"),     # total capacity (NOTE: over-counts when grouped across specialties per hospital — see notes)
        MeasureConfig("inpatient_beds",             "sum"),     # same note as total_bed_strength
        MeasureConfig("cases_treated",              "sum"),
        MeasureConfig("preauth_approved",           "sum"),
        MeasureConfig("preauth_rejected",           "sum"),
        MeasureConfig("claims_approved",            "sum"),
        MeasureConfig("amount_claimed",             "sum"),
        MeasureConfig("amount_approved",            "sum"),
        MeasureConfig("amount_paid",                "sum"),
        MeasureConfig("emergency_count",            "sum"),
        MeasureConfig("death_count",                "sum"),
        MeasureConfig("total_staff",                "avg"),     # hospital-level attr — AVG avoids double-counting across specialty rows
        MeasureConfig("avg_experience_years",       "avg"),     # already an average
        MeasureConfig("total_licenses",             "avg"),     # hospital-level attr — AVG avoids double-counting
        MeasureConfig("expired_licenses",           "avg"),     # hospital-level attr
        MeasureConfig("active_licenses",            "avg"),     # hospital-level attr
        MeasureConfig("zero_claim_flag",            "sum"),     # sum = count of zero-claim specialties
        MeasureConfig("cases_per_bed",              "avg"),     # rate
    ],
    
    impact_measures=["total_bed_strength", "cases_treated", "amount_paid"],
    max_subspace_depth=2,
    tau=0.5,
    min_impact=0.01,
    min_hdp_size=3,
)
```

### View 4 — Beneficiary Journey

```python
VIEW4_CONFIG = ViewConfig(
    name="Beneficiary Journey",
    parquet_path="views/view4_beneficiary_journey.parquet",
    
    dimensions=[
        "division", "district", "gender", "age_group",
        "entitlement_source", "bis_record_status",
        "enrolment_status", "card_status", "document_count_bucket",
    ],
    temporal_dimensions=[],
    
    measures=[
        MeasureConfig("document_count",             "avg"),     # avg docs per beneficiary
        MeasureConfig("has_aadhaar",                "avg"),     # avg = proportion with Aadhaar
        MeasureConfig("claim_count",                "sum"),     # total claims
        MeasureConfig("has_claim",                  "sum"),     # sum = count of claimants
        MeasureConfig("claim_rate",                 "avg"),     # proportion who claimed (alias of has_claim — see note below)
        MeasureConfig("days_enrolment_to_card",     "avg"),     # avg wait time
        MeasureConfig("days_card_to_first_claim",   "avg"),     # avg time to first use
    ],
    
    impact_measures=["has_claim", "claim_count"],
    max_subspace_depth=2,
    tau=0.5,
    min_impact=0.01,
    min_hdp_size=3,
)
```

**Note on View 4:** `has_claim` appears twice — once as SUM (count of claimants) and once as AVG (proportion who claimed). These are different measures analytically. However, they share the same column name which would create a conflict in `DataScope`. Two options:

**Option A:** Allow duplicate measure names with different aggs by making the measure identifier include the agg type. Change `DataScope.measure` to store `"has_claim_sum"` and `"has_claim_avg"`, and map back to the column name in `query_data_scope`.

**Option B:** Create a derived column in View 4 during Phase 1: `claim_rate = has_claim` (same values, different name). Then use `has_claim` with SUM and `claim_rate` with AVG. No engine changes needed.

**Recommendation:** Option B is simpler. Add this one line to View 4 construction in Phase 1:

```python
v4["claim_rate"] = v4["has_claim"]  # alias for AVG aggregation
```

Then in VIEW4_CONFIG:
```python
MeasureConfig("has_claim",    "sum"),     # count of claimants
MeasureConfig("claim_rate",   "avg"),     # proportion who claimed
```

---

## Impact Measures

Impact measures always use SUM regardless of the measure's configured agg type. Impact represents "what proportion of the total does this subspace cover" — which is inherently additive. The `ImpactCalculator` uses its own direct SUM computation and is not affected by this change.

---

## Known Limitations

1. **View 3 hospital-level attributes at hospital×specialty grain.** Measures like `total_staff`, `total_licenses`, and `total_bed_strength` are hospital-level values duplicated across every specialty row for the same hospital. When grouped by a geographic dimension (district, division), hospitals with more specialties are over-weighted. AVG mitigates this (gives average per hospital-specialty row) but isn't a true hospital-level aggregate. The correct fix would be deduplicating by hospital_id before aggregating, which requires a more complex query. Acceptable for MVP — the relative ranking of districts is still approximately correct.

2. **View 3 `total_bed_strength` as impact measure.** Impact always uses SUM internally. At the hospital×specialty grain, SUM(total_bed_strength) counts each hospital's beds once per specialty it offers. This inflates absolute impact values but the bias is consistent across all subspaces, so relative impact rankings are preserved.

3. **View 2 `cumulative_beneficiaries` as impact measure.** Impact SUM of a running total over-weights later months. A district that enrolled beneficiaries early accumulates more impact than one that enrolled the same number later. Approximately correct for "total enrollment coverage over time" but not a clean metric.

4. **AVG on sparse columns.** `days_card_to_first_claim` in View 4 has 90% nulls. AVG excludes NaN, so it computes the average over only the ~10% of beneficiaries who have claims. This is correct ("average wait among those who claimed") but produces unstable averages when a subspace-filtered group has very few claimants. Pattern evaluators' minimum size checks provide some protection.

---

## View 4 — Required Phase 1 Change

Add this derived column during View 4 construction in Phase 1, before saving the parquet:

```python
v4["claim_rate"] = v4["has_claim"]  # alias for AVG aggregation
```

This avoids the duplicate measure name problem. `has_claim` with SUM gives count of claimants. `claim_rate` with AVG gives proportion who claimed. Same underlying data, different analytical perspective.

---

## Validation

- [ ] Existing SUM measures produce identical results to Phase 4a
- [ ] New AVG measures produce plausible values (e.g., avg length_of_stay per district is 2-6 days, not thousands)
- [ ] "Outlier districts on enrolment time" is now discoverable: `DS({*}, breakdown=district, measure=days_enrolment_to_card)` with AVG aggregation
- [ ] View 2 ratio measures (approval_rate, emergency_share) produce meaningful Outstanding patterns
- [ ] No impact on scoring (impact still uses SUM internally)
