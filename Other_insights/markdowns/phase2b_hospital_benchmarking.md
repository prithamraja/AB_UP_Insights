# Phase 2b — Analytical Engine: Product 2 (Hospital Performance Benchmarking)

## Objective

Using the intermediate parquet files from Phase 1 (and raw CSVs where needed), compute all metrics, rankings, flags, and trend detection for Hospital Performance Benchmarking.

All outputs go to `./analytics/` directory as `.parquet` files.

**Benchmarking approach:** Compare hospitals performing the same procedure, split by hospital_type (public vs private) as peer groups. Minimum 5 cases per hospital per procedure (across all months) to be included in benchmarks.

**Important: Do NOT compute or flag mortality rates.** The dataset's 0.4% death rate produces too few events per hospital-procedure to be statistically meaningful. Mortality-based flags would be misleading.

---

## Input Files

### From Phase 1 (`./intermediate/`):
- `int_hospital_performance.parquet` — hospital × procedure × month (primary input)
- `int_demand_supply.parquet` — for block-level context

### Raw CSVs (from `/mnt/user-data/uploads/`) needed for additional analysis:
- `cm_case.csv` — for case-level detail where monthly aggregation is too coarse
- `cm_claim.csv` — for claim-level detail
- `cm_discharge.csv` — for discharge detail
- `cm_preauth_request.csv` — for preauth patterns
- `cm_preauth_procedure_line.csv` — for procedure-level pricing detail
- `hm_hospital.csv` — for hospital attributes
- `hm_specialty_offered.csv` — for specialty context
- `ref_hbp_procedure_master.csv` — for package pricing reference

---

## Step 0: Build Hospital-Procedure Summary Table

Before running individual analyses, aggregate `int_hospital_performance` from the monthly grain to hospital × procedure (across all months). This is the base table for benchmarking.

### Logic:
Group `int_hospital_performance` by `hospital_id` + `hbp_procedure_code`. Aggregate across all months:

| Column | Derivation |
|--------|------------|
| `hospital_id` | Group key |
| `hbp_procedure_code` | Group key |
| `hospital_name` | From any row (static) |
| `hospital_type` | PUBLIC or PRIVATE (static) |
| `hospital_sub_type` | From any row (static) |
| `block` | From any row (static) |
| `district` | From any row (static) |
| `division` | From any row (static) |
| `capacity_band` | From any row (static) |
| `procedure_name` | From any row (static) |
| `specialty_code` | From any row (static) |
| `specialty_name` | From any row (static) |
| `base_package_price` | From any row (static) |
| `total_cases` | SUM of `case_count` across all months |
| `active_months` | COUNT of months with `case_count` > 0 |
| `first_month` | MIN of `month` |
| `last_month` | MAX of `month` |
| `avg_los_days` | Weighted average: SUM(`avg_los_days` × `case_count`) / SUM(`case_count`) |
| `avg_amount_claimed` | SUM(`total_amount_claimed`) / SUM(`case_count`) |
| `avg_amount_approved` | SUM(`total_amount_approved`) / SUM(`case_count`) |
| `total_amount_claimed` | SUM of `total_amount_claimed` |
| `total_amount_approved` | SUM of `total_amount_approved` |
| `avg_approval_ratio` | `total_amount_approved` / `total_amount_claimed` |
| `claim_approval_rate` | Weighted average of monthly `claim_approval_rate` by `case_count` |
| `claim_rejection_rate` | Weighted average of monthly `claim_rejection_rate` by `case_count` |
| `claim_query_rate` | Weighted average of monthly `claim_query_rate` by `case_count` |
| `avg_query_count` | Weighted average of monthly `avg_query_count` by `case_count` |
| `normal_discharge_rate` | Weighted average of monthly `normal_discharge_rate` by `case_count` |
| `lama_dama_rate` | Weighted average of monthly `lama_dama_rate` by `case_count` |
| `avg_settlement_tat_days` | Weighted average of monthly `avg_settlement_tat_days` by `case_count` |
| `preauth_auto_approval_rate` | Weighted average by `case_count` |
| `biometric_auth_rate` | Weighted average by `case_count` |
| `medicines_provided_rate` | Weighted average by `case_count` |

**Filter:** Drop rows where `total_cases` < 5. These hospital-procedure combinations don't have enough volume for meaningful benchmarking.

**Save as:** `./analytics/bench_hospital_procedure_summary.parquet` (this is both an output and an input for subsequent analyses)

---

## Analysis 1: Cost Benchmarking

**Question:** For a given procedure, which hospitals charge significantly more or less than their peers?

**Source:** `bench_hospital_procedure_summary`

### Logic:

1. For each procedure × hospital_type (peer group), compute:
   | Metric | Formula |
   |--------|---------|
   | `peer_avg_cost` | Mean of `avg_amount_claimed` across all hospitals in the peer group |
   | `peer_median_cost` | Median of `avg_amount_claimed` across all hospitals in the peer group |
   | `peer_std_cost` | Std dev of `avg_amount_claimed` across the peer group |
   | `peer_p25_cost` | 25th percentile |
   | `peer_p75_cost` | 75th percentile |
   | `peer_hospital_count` | Number of hospitals in this peer group |

2. For each hospital-procedure row, compute:
   | Metric | Formula |
   |--------|---------|
   | `cost_z_score` | (`avg_amount_claimed` - `peer_avg_cost`) / `peer_std_cost`. Null if `peer_std_cost` = 0. |
   | `cost_vs_package` | `avg_amount_claimed` / `base_package_price`. Shows how much the hospital claims relative to the fixed package rate. Values > 1 mean add-ons/implants are driving up cost. |
   | `cost_percentile_rank` | Percentile rank within the peer group (0-100). |
   | `approval_gap` | `avg_amount_claimed` - `avg_amount_approved`. How much is being cut by the insurer. |
   | `approval_gap_rate` | 1 - `avg_approval_ratio`. Proportion of claimed amount not approved. |

3. Flag outliers:
   | Flag | Condition |
   |------|-----------|
   | `high_cost_outlier` | `cost_z_score` > 1.5 (significantly above peer average) |
   | `low_cost_outlier` | `cost_z_score` < -1.5 (significantly below — could indicate under-treatment) |
   | `high_approval_gap` | `approval_gap_rate` > 0.2 (more than 20% of claimed amount not approved — possible over-billing) |
   | `above_package_rate` | `cost_vs_package` > 1.3 (claiming 30%+ above base package price) |

**Output:** `./analytics/bench_cost.parquet`

Columns: hospital_id, hospital_name, hospital_type, hospital_sub_type, block, district, division, hbp_procedure_code, procedure_name, specialty_code, base_package_price, total_cases, avg_amount_claimed, avg_amount_approved, avg_approval_ratio, peer_avg_cost, peer_median_cost, peer_p25_cost, peer_p75_cost, peer_hospital_count, cost_z_score, cost_vs_package, cost_percentile_rank, approval_gap, approval_gap_rate, high_cost_outlier (bool), low_cost_outlier (bool), high_approval_gap (bool), above_package_rate (bool)

---

## Analysis 2: Length of Stay Benchmarking

**Question:** For a given procedure, which hospitals keep patients significantly longer or shorter than peers?

**Source:** `bench_hospital_procedure_summary`

### Logic:

1. For each procedure × hospital_type (peer group), compute:
   | Metric | Formula |
   |--------|---------|
   | `peer_avg_los` | Mean of `avg_los_days` across peer group |
   | `peer_median_los` | Median of `avg_los_days` across peer group |
   | `peer_std_los` | Std dev |
   | `peer_p25_los` | 25th percentile |
   | `peer_p75_los` | 75th percentile |

2. For each hospital-procedure row:
   | Metric | Formula |
   |--------|---------|
   | `los_z_score` | (`avg_los_days` - `peer_avg_los`) / `peer_std_los` |
   | `los_percentile_rank` | Percentile rank within peer group |
   | `los_vs_peer_median` | `avg_los_days` / `peer_median_los`. Values > 1 mean longer than typical. |

3. Flag outliers:
   | Flag | Condition |
   |------|-----------|
   | `long_stay_outlier` | `los_z_score` > 1.5 |
   | `short_stay_outlier` | `los_z_score` < -1.5 (very short stays could indicate premature discharge) |

**Output:** `./analytics/bench_los.parquet`

Columns: hospital_id, hospital_name, hospital_type, hbp_procedure_code, procedure_name, total_cases, avg_los_days, peer_avg_los, peer_median_los, peer_p25_los, peer_p75_los, los_z_score, los_percentile_rank, los_vs_peer_median, long_stay_outlier (bool), short_stay_outlier (bool)

---

## Analysis 3: Patient Outcome Benchmarking (LAMA/DAMA)

**Question:** Which hospitals have unusually high rates of patients leaving against medical advice?

**Source:** `bench_hospital_procedure_summary`

### Logic:

High LAMA/DAMA rates can signal: patient dissatisfaction, unexpected out-of-pocket costs, poor communication, or inadequate facilities. This is a more reliable outcome signal than mortality at this data scale.

1. For each procedure × hospital_type (peer group), compute:
   | Metric | Formula |
   |--------|---------|
   | `peer_avg_lama_dama_rate` | Mean of `lama_dama_rate` across peer group |
   | `peer_std_lama_dama_rate` | Std dev |
   | `peer_avg_normal_discharge_rate` | Mean of `normal_discharge_rate` |

   **Sparsity guard:** If `peer_avg_lama_dama_rate` < 0.01 (less than 1% across the peer group), skip z-score computation for this peer group and set `lama_dama_z_score` to null. With near-zero base rates, z-scores become unstable and misleading.

2. For each hospital-procedure row:
   | Metric | Formula |
   |--------|---------|
   | `lama_dama_z_score` | (`lama_dama_rate` - `peer_avg_lama_dama_rate`) / `peer_std_lama_dama_rate` |
   | `lama_dama_percentile_rank` | Percentile rank within peer group |

3. Flag:
   | Flag | Condition |
   |------|-----------|
   | `high_lama_dama` | `lama_dama_z_score` > 1.5 |
   | `excellent_retention` | `normal_discharge_rate` > 0.95 AND `total_cases` >= 10 (consistently good outcomes with enough volume to be meaningful) |

**Output:** `./analytics/bench_outcomes.parquet`

Columns: hospital_id, hospital_name, hospital_type, hbp_procedure_code, procedure_name, total_cases, lama_dama_rate, normal_discharge_rate, peer_avg_lama_dama_rate, peer_avg_normal_discharge_rate, lama_dama_z_score, lama_dama_percentile_rank, high_lama_dama (bool), excellent_retention (bool)

---

## Analysis 4: Claims Quality Benchmarking

**Question:** Which hospitals have high claim rejection or query rates, suggesting documentation or billing issues?

**Source:** `bench_hospital_procedure_summary`

### Logic:

1. For each procedure × hospital_type (peer group), compute:
   | Metric | Formula |
   |--------|---------|
   | `peer_avg_rejection_rate` | Mean of `claim_rejection_rate` |
   | `peer_avg_query_rate` | Mean of `claim_query_rate` |
   | `peer_avg_query_count` | Mean of `avg_query_count` |
   | `peer_avg_settlement_tat` | Mean of `avg_settlement_tat_days` |

2. For each hospital-procedure row:
   | Metric | Formula |
   |--------|---------|
   | `rejection_z_score` | (`claim_rejection_rate` - `peer_avg_rejection_rate`) / peer std |
   | `query_z_score` | (`claim_query_rate` - `peer_avg_query_rate`) / peer std |
   | `settlement_tat_z_score` | (`avg_settlement_tat_days` - `peer_avg_settlement_tat`) / peer std |
   | `claims_quality_score` | Simple average of (1 - normalized rejection rate), (1 - normalized query rate), and (1 - normalized settlement TAT). Range 0-1, higher = better claims quality. Normalize each component using min-max within the peer group. |

3. Flag:
   | Flag | Condition |
   |------|-----------|
   | `high_rejection` | `rejection_z_score` > 1.5 |
   | `high_query` | `query_z_score` > 1.5 |
   | `slow_settlement` | `settlement_tat_z_score` > 1.5 |
   | `poor_claims_quality` | At least 2 of the above 3 flags are True |
   | `clean_claims` | `claim_rejection_rate` = 0 AND `claim_query_rate` < 0.05 AND `total_cases` >= 10 |

**Output:** `./analytics/bench_claims_quality.parquet`

Columns: hospital_id, hospital_name, hospital_type, hbp_procedure_code, procedure_name, total_cases, claim_rejection_rate, claim_query_rate, avg_query_count, avg_settlement_tat_days, peer_avg_rejection_rate, peer_avg_query_rate, peer_avg_settlement_tat, rejection_z_score, query_z_score, settlement_tat_z_score, claims_quality_score, high_rejection (bool), high_query (bool), slow_settlement (bool), poor_claims_quality (bool), clean_claims (bool)

---

## Analysis 5: Trend Detection

**Question:** Are there hospitals whose performance is improving or deteriorating over time?

**Source:** `int_hospital_performance.parquet` (monthly grain)

### Logic:

For each hospital × procedure with at least 5 total cases AND at least 4 active months (enough data points for a trend), compute simple trend direction on key metrics.

**Trend method:** For each metric's monthly time series, compute the slope of a simple linear regression (month index as X, metric value as Y). Classify:
   | Direction | Condition |
   |-----------|-----------|
   | `IMPROVING` | Slope is in the "good" direction AND the slope is notable relative to the metric's mean: `abs(slope) / abs(mean) > 0.05` (i.e., the metric is changing by more than 5% of its average value per month) |
   | `DECLINING` | Slope is in the "bad" direction AND `abs(slope) / abs(mean) > 0.05` |
   | `STABLE` | `abs(slope) / abs(mean) <= 0.05`, or mean is zero |
   | `INSUFFICIENT_DATA` | Fewer than 4 active months |

**"Good" direction per metric:**
| Metric | Good direction (improving) | Bad direction (declining) |
|--------|---------------------------|--------------------------|
| `avg_amount_claimed` | Decreasing (getting cheaper) | Increasing |
| `avg_los_days` | Decreasing (shorter stays) | Increasing |
| `claim_approval_rate` | Increasing | Decreasing |
| `claim_query_rate` | Decreasing | Increasing |
| `lama_dama_rate` | Decreasing | Increasing |
| `normal_discharge_rate` | Increasing | Decreasing |
| `avg_settlement_tat_days` | Decreasing (faster settlement) | Increasing |

**Weight months by case count:** When computing the regression, weight each month's data point by its `case_count` so months with more cases have more influence. This prevents a month with 1 case from having equal influence as a month with 20.

### Output per hospital × procedure:
| Column | Derivation |
|--------|------------|
| `hospital_id`, `hbp_procedure_code` | Group keys |
| `hospital_name`, `hospital_type`, `procedure_name` | Static attributes |
| `block`, `district`, `division` | Location |
| `total_cases` | From summary table |
| `active_months` | Count of months with cases |
| `cost_trend` | IMPROVING / DECLINING / STABLE / INSUFFICIENT_DATA |
| `cost_slope` | Raw slope value per month |
| `los_trend` | Direction |
| `los_slope` | Raw slope |
| `approval_trend` | Direction |
| `approval_slope` | Raw slope |
| `query_trend` | Direction |
| `query_slope` | Raw slope |
| `lama_dama_trend` | Direction |
| `lama_dama_slope` | Raw slope |
| `overall_trajectory` | `IMPROVING` if majority of metrics are improving and none declining. `DECLINING` if majority are declining and none improving. `MIXED` otherwise. `STABLE` if all stable. |

Flag:
| Flag | Condition |
|------|-----------|
| `declining_hospital` | `overall_trajectory` = DECLINING |
| `improving_hospital` | `overall_trajectory` = IMPROVING |

**Output:** `./analytics/bench_trends.parquet`

---

## Analysis 6: Hospital Scorecard

**Question:** Can we give each hospital a single summary view combining all benchmarking dimensions?

**Source:** Outputs from Analyses 1-5, `bench_hospital_procedure_summary`

### Logic:

This is NOT a composite score (we're not ranking hospitals). It's a **summary table** — one row per hospital, aggregating across all their procedures, designed to give a quick overview.

1. For each `hospital_id`, aggregate across all procedures (from `bench_hospital_procedure_summary`):
   | Column | Derivation |
   |--------|------------|
   | `hospital_id` | Group key |
   | `hospital_name`, `hospital_type`, `hospital_sub_type` | Static |
   | `block`, `district`, `division`, `capacity_band` | Static |
   | `total_cases` | SUM across all procedures |
   | `procedures_performed` | COUNT DISTINCT `hbp_procedure_code` |
   | `specialties_covered` | COUNT DISTINCT `specialty_code` |
   | `weighted_avg_los` | SUM(`avg_los_days` × `total_cases`) / SUM(`total_cases`) |
   | `weighted_avg_cost` | SUM(`avg_amount_claimed` × `total_cases`) / SUM(`total_cases`) |
   | `overall_approval_ratio` | SUM(`total_amount_approved`) / SUM(`total_amount_claimed`) |
   | `overall_lama_dama_rate` | Weighted avg of `lama_dama_rate` by case count |
   | `overall_claim_rejection_rate` | Weighted avg |
   | `overall_claim_query_rate` | Weighted avg |
   | `overall_settlement_tat` | Weighted avg |
   | `biometric_auth_rate` | Weighted avg |
   | `medicines_provided_rate` | Weighted avg |

2. Count flags from Analyses 1-5 per hospital:

   First, build a unified flag table by joining all 4 analysis outputs on `hospital_id` + `hbp_procedure_code`:
   - From `bench_cost.parquet`: `high_cost_outlier`, `high_approval_gap`
   - From `bench_los.parquet`: `long_stay_outlier`
   - From `bench_outcomes.parquet`: `high_lama_dama`
   - From `bench_claims_quality.parquet`: `poor_claims_quality`
   - From `bench_trends.parquet`: `declining_hospital`

   For each hospital-procedure row, count how many distinct analyses flagged it:
   - `flags_per_procedure` = count of True flags across the 6 flags above (max 6)

   Then aggregate per hospital:
   | Column | Derivation |
   |--------|------------|
   | `cost_outlier_procedures` | COUNT of procedures where `high_cost_outlier` = True |
   | `los_outlier_procedures` | COUNT of procedures where `long_stay_outlier` = True |
   | `high_lama_dama_procedures` | COUNT of procedures where `high_lama_dama` = True |
   | `poor_claims_procedures` | COUNT of procedures where `poor_claims_quality` = True |
   | `declining_procedures` | COUNT of procedures where `declining_hospital` = True |
   | `total_flags` | Sum of all the above |
   | `max_flags_single_procedure` | MAX of `flags_per_procedure` across all procedures for this hospital |
   | `clean_procedures` | COUNT of procedures with zero flags across all analyses |

3. Assign attention level (NOT a ranking, just a triage signal):
   | Level | Condition |
   |-------|-----------|
   | `NEEDS_REVIEW` | `total_flags` >= 3 OR `max_flags_single_procedure` >= 3 |
   | `WATCH` | `total_flags` = 1 or 2 |
   | `SATISFACTORY` | `total_flags` = 0 |

**Output:** `./analytics/bench_hospital_scorecard.parquet`

---

## Technical Notes

- Use `pandas` for data manipulation, `numpy` for linear regression (`np.polyfit` with degree 1), `scipy.stats.percentileofscore` for percentile ranks.
- All rates/proportions remain as 0-1 floats.
- **Minimum case threshold:** 5 cases per hospital-procedure to be included in benchmarks. Applied in Step 0 and carried through.
- **Peer group:** procedure × hospital_type (PUBLIC or PRIVATE). All z-scores and percentile ranks are computed within the peer group.
- For z-scores: if peer group std dev = 0 (all hospitals identical), set z-score to 0.
- For peer groups with fewer than 3 hospitals: still compute metrics but add a `small_peer_group` flag = True. Benchmarks with tiny peer groups should be interpreted cautiously.
- Weighted averages: always weight by case count when aggregating from monthly to summary level, to avoid giving equal weight to a month with 1 case and a month with 50.
- Print summary after each analysis: count of outlier flags, distribution of z-scores, top 5 and bottom 5 hospitals per metric.

---

## FRONTEND CAVEAT REMINDER

When presenting benchmarking results, the frontend must include this caveat:

> *"Public and private hospitals are benchmarked separately within each peer group. Public hospitals typically handle more complex and emergency referrals, so direct public-vs-private comparison is not appropriate. Outlier flags indicate deviation from peers performing the same procedure, not absolute quality judgments."*

---

## Output File Count

7 parquet files total:
1. `bench_hospital_procedure_summary.parquet` (base table)
2. `bench_cost.parquet`
3. `bench_los.parquet`
4. `bench_outcomes.parquet`
5. `bench_claims_quality.parquet`
6. `bench_trends.parquet`
7. `bench_hospital_scorecard.parquet`

---

## Success Criteria

Phase 2b is complete when:
1. All 7 output parquet files exist in `./analytics/`.
2. Console output shows summary statistics for each analysis.
3. The hospital scorecard covers all hospitals that meet the minimum case threshold.
4. A brief `phase2b_summary.md` is written listing: files created, row counts, count of outlier flags per analysis, top 10 hospitals needing review, and any assumptions made.
