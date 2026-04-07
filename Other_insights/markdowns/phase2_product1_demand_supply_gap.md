# Phase 2 — Analytical Engine: Product 1 (Demand-Supply Gap Analysis)

## Objective

Using the 4 intermediate parquet files from Phase 1 (and raw CSVs where needed for additional joins), compute all metrics, rankings, flags, and outlier detection for the Demand-Supply Gap Analysis.

All outputs go to `./analytics/` directory as `.parquet` files.

**Primary geographic unit: Block** (with district and division as roll-up dimensions).

---

## Input Files

### From Phase 1 (`./intermediate/`):
- `int_demand_supply.parquet` — block × month demand, supply, enrolment
- `int_hospital_performance.parquet` — hospital × procedure × month
- `int_enrolment_monthly.parquet` — block × month enrolment trends
- `int_specialty_gap.parquet` — block × specialty demand vs supply

### Raw CSVs (from `/mnt/user-data/uploads/`) needed for additional analysis:
- `cm_case.csv` — for repeat utilization, seasonal analysis, portability flows
- `cm_case_diagnosis.csv` — for disease burden mapping
- `cm_claim.csv` — for portability flow amounts (rebuild claims_per_case helper here)
- `cm_discharge.csv` — for outcome analysis by disease category
- `hm_hospital.csv` — for facility infrastructure flags, portability destination
- `hm_specialty_offered.csv` — for delisted hospital specialty analysis
- `bm_beneficiary.csv` — for repeat utilization, card drop-off
- `bm_household.csv` — for block mapping
- `bm_card.csv` — for card drop-off analysis
- `bm_enrolment_request.csv` — for enrolment funnel
- `cm_preauth_request.csv` — for repeat utilization procedure identification
- `cm_preauth_procedure_line.csv` — for repeat utilization procedure identification

---

## Prerequisite: Rebuild `claims_per_case` Helper

Phase 1 built a `claims_per_case` helper DataFrame in memory but did not save it. Rebuild it here from `cm_claim.csv`:

Group `cm_claim` by `case_id` and compute:

| Column | Derivation |
|--------|------------|
| `case_id` | Group key |
| `total_amount_claimed` | SUM of `amount_claimed` |
| `total_amount_approved` | SUM of `amount_approved` |

This is used in Analysis 4 for flow amounts. Keep it lightweight — only the columns needed.

---

## Analysis 1: Utilization Gap Scoring

**Question:** Which blocks have high enrolment but low utilization, suggesting access barriers rather than low need?

**Source:** `int_demand_supply.parquet`, `cm_case.csv` (for distinct beneficiary counts)

### Important Note on Geography:
`int_demand_supply` measures demand at the **beneficiary's home block** and supply at the **same block**. This means:
- Demand columns (cases, beneficiaries) reflect where patients LIVE.
- Supply columns (hospitals, beds) reflect what's physically IN that block.
- A block with zero hospitals but high cases means residents are travelling elsewhere — this is a valid gap signal.
- Bed-related pressure metrics should be interpreted as "local infrastructure available to residents," not as hospital occupancy.

### Logic:

1. Aggregate `int_demand_supply` to block-level totals (sum across all months):
   - `total_cases_all_months` = SUM of `total_cases`
   - `total_unique_beneficiaries_all_months` = Cannot be summed across months (same person may appear in multiple months). Instead, go back to `cm_case` joined to `bm_beneficiary` → `bm_household` and COUNT DISTINCT `beneficiary_id` per block+district.
   - Use snapshot columns for `total_beneficiaries_enrolled`, `total_inpatient_beds`, etc. (these are static per block, so take the value from any row).

2. Compute actual bed-days consumed per block (from the demand perspective):
   - From `cm_case` joined to `bm_household`: SUM of `los_days` grouped by home block+district.
   - `bed_days_consumed` = SUM of `los_days` for all cases originating from this block.
   - Note: these bed-days may have been consumed at hospitals in OTHER blocks. This metric reflects demand intensity, not local hospital occupancy.

3. Compute block-level utilization metrics:
   | Metric | Formula |
   |--------|---------|
   | `overall_utilization_rate` | distinct beneficiaries with at least one case / total_beneficiaries_enrolled |
   | `cases_per_1000_enrolled` | (total_cases_all_months / total_beneficiaries_enrolled) × 1000 |
   | `demand_intensity` | `bed_days_consumed` / `total_beneficiaries_enrolled`. Measures how many inpatient bed-days are demanded per enrolled beneficiary. Higher = heavier healthcare demand from this block's population. |
   | `local_bed_availability` | `total_inpatient_beds` / `total_beneficiaries_enrolled` × 1000. Measures locally available beds per 1000 enrolled — NOT occupancy. A low number means residents likely must travel for care. |

4. Compute z-scores for each metric across all blocks (using mean and std dev of all blocks). This positions each block relative to the state average.

5. Flag blocks:
   | Flag | Condition |
   |------|-----------|
   | `high_enrolment_low_utilization` | `total_beneficiaries_enrolled` is above median AND `overall_utilization_rate` is below 25th percentile |
   | `high_demand_low_local_supply` | `cases_per_1000_enrolled` is above 75th percentile AND `local_bed_availability` is below 25th percentile |
   | `zero_supply` | `total_hospitals` = 0 or null (block has enrolled beneficiaries but no empanelled hospital) |
   | `single_hospital_dependency` | `total_hospitals` = 1 (block depends on a single facility) |

**Output:** `./analytics/gap_utilization_scores.parquet`

Columns: block, district, division, total_beneficiaries_enrolled, total_cases_all_months, distinct_beneficiaries_with_cases, overall_utilization_rate, cases_per_1000_enrolled, bed_days_consumed, demand_intensity, local_bed_availability, total_hospitals, total_inpatient_beds, z_utilization_rate, z_cases_per_1000, z_local_bed_availability, high_enrolment_low_utilization (bool), high_demand_low_local_supply (bool), zero_supply (bool), single_hospital_dependency (bool)

---

## Analysis 2: Specialty Gap Matrix

**Question:** Which block × specialty combinations have patient demand but no local hospital offering that specialty?

**Source:** `int_specialty_gap.parquet`

### Logic:

1. Start from `int_specialty_gap.parquet` which already has demand and supply per block × specialty.

2. Compute additional metrics:
   | Metric | Formula |
   |--------|---------|
   | `gap_severity` | Categorical: `NO_SUPPLY` (demand > 0, supply = 0), `UNDERSUPPLIED` (demand_supply_ratio > 75th percentile of non-zero ratios), `ADEQUATE` (all others), `NO_DEMAND` (demand = 0) |
   | `estimated_revenue_leakage` | For `NO_SUPPLY` gaps: `amount_claimed` represents money flowing to other blocks/districts. Sum this as leakage. |

3. Build a summary table:
   - Top 20 block × specialty gaps ranked by `cases_demanding` where `gap_flag` = True
   - For each gap, identify the nearest block (same district) that DOES offer that specialty (if any). This requires a lookup: for each gap row, find other blocks in the same district with `hospitals_offering` > 0 for that specialty.

4. District-level rollup:
   - Per district: count of specialties with at least one block-level gap
   - Per district × specialty: total unmet cases, total revenue leakage

**Output:** `./analytics/gap_specialty_matrix.parquet`

Columns: block, district, division, specialty_code, specialty_name, cases_demanding, unique_patients, amount_claimed, hospitals_offering, total_prev_fy_admissions, gap_flag, demand_supply_ratio, gap_severity, estimated_revenue_leakage, nearest_block_with_supply (nullable), nearest_block_same_district (bool)

---

## Analysis 3: Disease Burden Mismatch

**Question:** Does the disease mix in each block match the infrastructure available there?

**Source:** Raw CSVs — `cm_case_diagnosis.csv`, `cm_case.csv`, `hm_hospital.csv`, `bm_beneficiary.csv`, `bm_household.csv`

### Step 3a: Classify cases by disease category

Using `cm_case_diagnosis` where `diagnosis_rank = 1` (primary diagnosis only), map each case to a disease category based on ICD-10 code prefixes.

**Important clarification:** This classifies the patient's DIAGNOSIS (what they were sick with), NOT the treatment/procedure performed. A patient diagnosed with a hernia (surgical diagnosis) might have been treated at a medical ward if surgery wasn't available. The diagnosis-based categorization reflects the disease burden, while the facility flags reflect treatment capability. The mismatch between these two is exactly what we're looking for.

| Category | ICD-10 Patterns | Key Conditions |
|----------|----------------|----------------|
| `NCD` | I00-I99 (circulatory), E10-E14 (diabetes), J40-J47 (chronic respiratory), C00-C97 (neoplasms), N17-N19 (renal failure — medical management) | MI, heart failure, stroke, diabetes, CKD, cancers |
| `COMMUNICABLE` | A00-A09 (intestinal), A15-A19 (TB), A90-A99 (dengue/viral), B50-B54 (malaria), J09-J18 (pneumonia/flu) | Diarrhoea, dengue, malaria, typhoid, TB |
| `MATERNAL_NEONATAL` | O00-O99 (pregnancy/childbirth), P00-P96 (perinatal), Z37 (delivery outcome) | C-section, normal delivery, pre-eclampsia |
| `SURGICAL` | K35-K38 (appendix), K40-K46 (hernia), H25-H26 (cataract), N40 (prostate), plus any other code NOT already captured above that commonly requires surgical intervention | Hernia, appendicitis, cataract |
| `INJURY` | S00-S99, T00-T98 (injuries/trauma) | Fractures, brain injury |
| `OTHER` | Everything not matched above | |

**ICD code matching logic:** Match on the letter prefix first (e.g., `O` → MATERNAL), then refine with numeric ranges. Some codes may overlap conceptually (e.g., N17 renal failure could be NCD or could need surgery); resolve by matching in the order listed above — first match wins. This is imperfect but consistent.

Join `cm_case_diagnosis` (rank 1) → `cm_case` (on case_id) → `bm_beneficiary` (on beneficiary_id) → `bm_household` (on household_id) for block location.

Group by block + district + division + disease_category:

| Column | Derivation |
|--------|------------|
| `block`, `district`, `division` | From household |
| `disease_category` | Mapped from ICD-10 |
| `case_count` | COUNT |
| `proportion_of_block_cases` | case_count / total cases in that block |
| `death_count` | COUNT where `cm_case.discharge_type` = DEATH |
| `category_mortality_rate` | death_count / case_count |

### Step 3b: Map facility capabilities to disease needs

Define what infrastructure each disease category needs:

| Disease Category | Required Facility Flags (ANY of these) |
|-----------------|----------------------------------------|
| `NCD` | `has_icu_with_ac` OR `has_hdu` |
| `COMMUNICABLE` | `has_general_ward` OR `has_casualty` |
| `MATERNAL_NEONATAL` | `has_labour_room` |
| `SURGICAL` | `has_fully_equipped_ot` |
| `INJURY` | `has_casualty` AND `has_fully_equipped_ot` |

For each block, count hospitals (from `hm_hospital` using hospital's `block_name` + `district_name`) that satisfy the required flags for each disease category.

### Step 3c: Compute mismatch

For each block × disease_category, compare:
- `case_count` (demand for that disease type from residents of this block)
- `hospitals_with_required_facilities` (hospitals physically IN this block with the right infrastructure)

| Metric | Formula |
|--------|---------|
| `infrastructure_mismatch` | True if `case_count` > 0 AND `hospitals_with_required_facilities` = 0 |
| `infrastructure_strain` | `case_count` / `hospitals_with_required_facilities` (null if no supply) |

**Output:** `./analytics/gap_disease_burden.parquet`

Columns: block, district, division, disease_category, case_count, proportion_of_block_cases, death_count, category_mortality_rate, hospitals_with_required_facilities, infrastructure_mismatch (bool), infrastructure_strain

---

## Analysis 4: Portability Flow Analysis

**Question:** Where are beneficiaries going for care when they leave their home block/district? What does the flow pattern tell us about local gaps?

**Source:** `cm_case.csv`, `hm_hospital.csv`, `bm_beneficiary.csv`, `bm_household.csv`, `cm_claim.csv` (via `claims_per_case` helper rebuilt above)

### Logic:

1. For each case, identify:
   - **Origin:** beneficiary's home block + district + division (from `bm_household` via `bm_beneficiary`)
   - **Destination:** hospital's block + district + division (from `hm_hospital` via `cm_case.hospital_id`)
   - Whether origin and destination match at each geographic level.

2. Classify each case:
   | Category | Condition |
   |----------|-----------|
   | `SAME_BLOCK` | Home block+district = hospital block+district |
   | `SAME_DISTRICT_DIFF_BLOCK` | Same district, different block |
   | `DIFF_DISTRICT_SAME_DIVISION` | Different district, same division |
   | `DIFF_DIVISION` | Different division entirely (but still within UP) |
   | `OUT_OF_STATE` | `cm_case.is_portability` = True (`hospital_state_code` ≠ `home_state_code`) |

   **Edge case for OUT_OF_STATE:** For portability cases, the hospital may not exist in `hm_hospital` (it's in another state). Use `cm_case.hospital_district` and `cm_case.hospital_state_code` directly from the case table for destination, rather than joining to `hm_hospital`. Only join to `hm_hospital` for non-portability cases.

3. Group by origin block + district + division:
   | Column | Derivation |
   |--------|------------|
   | `block`, `district`, `division` | Origin (home) |
   | `total_cases` | COUNT |
   | `cases_same_block` | COUNT where SAME_BLOCK |
   | `cases_same_district` | COUNT where SAME_DISTRICT_DIFF_BLOCK |
   | `cases_diff_district` | COUNT where DIFF_DISTRICT_SAME_DIVISION or DIFF_DIVISION |
   | `cases_out_of_state` | COUNT where OUT_OF_STATE |
   | `local_retention_rate` | (cases_same_block + cases_same_district) / total_cases |
   | `leakage_rate` | (cases_diff_district + cases_out_of_state) / total_cases |

4. Build a flow table (origin → destination at district level):
   Group by origin_district + destination_district:
   | Column | Derivation |
   |--------|------------|
   | `origin_district` | Home district |
   | `destination_district` | Hospital district (from `hm_hospital.district_name` for in-state, from `cm_case.hospital_district` for portability) |
   | `flow_count` | COUNT of cases |
   | `flow_amount_claimed` | SUM of `claims_per_case.total_amount_claimed` |

5. Compute net flow per district:
   | Metric | Formula |
   |--------|---------|
   | `cases_exported` | Cases where home_district = this district AND hospital_district ≠ this district |
   | `cases_imported` | Cases where hospital_district = this district AND home_district ≠ this district |
   | `net_flow` | cases_imported - cases_exported. Positive = net importer (destination hub). Negative = net exporter (people leaving for care). |

**Output:** `./analytics/gap_portability_flows.parquet` (block-level retention/leakage)
**Output:** `./analytics/gap_district_patient_flows.parquet` (district-to-district flow matrix)

---

## Analysis 5: Enrolment-to-Card Drop-off

**Question:** Are there blocks where beneficiaries enrol but disproportionately fail to get an active card?

**Source:** `bm_beneficiary.csv`, `bm_household.csv`, `bm_card.csv`, `bm_enrolment_request.csv`

### Logic:

1. Join `bm_beneficiary` → `bm_household` (on household_id for block), then left join `bm_card` (on beneficiary_id).

2. Per beneficiary, determine card status:
   - `has_card` = True if any row in `bm_card` exists for this beneficiary
   - `has_active_card` = True if any `bm_card.card_status` = ACTIVE
   - `card_inactive_or_disabled` = True if has_card but no active card

3. Also join `bm_enrolment_request` (on beneficiary_id) to check:
   - `enrolment_rejected` = True if any enrolment request has `status` = REJECTED
   - `enrolment_pending` = True if latest enrolment request (by `submitted_at`) is not in a terminal approved/rejected state

4. Group by block + district + division:
   | Column | Derivation |
   |--------|------------|
   | `block`, `district`, `division` | From household |
   | `total_beneficiaries` | COUNT |
   | `beneficiaries_with_active_card` | COUNT where `has_active_card` |
   | `beneficiaries_no_card` | COUNT where `has_card` = False |
   | `beneficiaries_inactive_card` | COUNT where `card_inactive_or_disabled` |
   | `card_activation_rate` | `beneficiaries_with_active_card` / `total_beneficiaries` |
   | `enrolment_rejection_rate` | COUNT where `enrolment_rejected` / `total_beneficiaries` |
   | `drop_off_rate` | 1 - `card_activation_rate` |

5. Flag blocks:
   | Flag | Condition |
   |------|-----------|
   | `high_drop_off` | `drop_off_rate` above 75th percentile across all blocks |
   | `high_rejection` | `enrolment_rejection_rate` above 75th percentile |

**Output:** `./analytics/gap_card_dropoff.parquet`

---

## Analysis 6: Repeat Utilization

**Question:** Which blocks have high repeat visits, possibly signalling chronic disease burden or ineffective initial treatment?

**Source:** `cm_case.csv`, `bm_beneficiary.csv`, `bm_household.csv`, `cm_preauth_request.csv`, `cm_preauth_procedure_line.csv`

### Logic:

1. Identify primary procedure per case:
   - Join `cm_case` → `cm_preauth_request` (on case_id, take non-rejected preauth, latest by `initiated_at` if multiple) → `cm_preauth_procedure_line` (on preauth_id, filter `procedure_rank = 1`).
   - This gives one primary `hbp_procedure_code` per case.

2. Build per-beneficiary admission history:
   - From `cm_case` joined with primary procedure from step 1, create a list of admissions per beneficiary:
     - `beneficiary_id`, `case_id`, `hospital_id`, `hbp_procedure_code`, `admission_datetime`
   - Sort by `admission_datetime` per beneficiary.

3. Classify repeat patterns at the **admission-pair level**, not per beneficiary:
   - For each beneficiary with >1 admission, compare each consecutive pair of admissions:

   | Pattern | Condition |
   |---------|-----------|
   | `SAME_PROCEDURE_SAME_HOSPITAL` | Same `hospital_id` AND same `hbp_procedure_code` as previous admission |
   | `SAME_PROCEDURE_DIFF_HOSPITAL` | Different `hospital_id` BUT same `hbp_procedure_code` as previous admission |
   | `DIFF_PROCEDURE` | Different `hbp_procedure_code` from previous admission |

   - A beneficiary with 3 admissions produces 2 pairs, each classified independently. This avoids forcing a single label on complex patterns.

4. Aggregate per beneficiary:
   | Column | Derivation |
   |--------|------------|
   | `beneficiary_id` | Group key |
   | `total_admissions` | COUNT |
   | `is_repeat` | True if `total_admissions` > 1 |
   | `same_proc_same_hosp_pairs` | COUNT of SAME_PROCEDURE_SAME_HOSPITAL pairs |
   | `same_proc_diff_hosp_pairs` | COUNT of SAME_PROCEDURE_DIFF_HOSPITAL pairs |
   | `diff_proc_pairs` | COUNT of DIFF_PROCEDURE pairs |
   | `dominant_pattern` | The pattern with the highest count. Ties broken by: SAME_PROCEDURE_SAME_HOSPITAL > SAME_PROCEDURE_DIFF_HOSPITAL > DIFF_PROCEDURE |

5. Join to `bm_beneficiary` → `bm_household` for block. Group by block + district + division:
   | Column | Derivation |
   |--------|------------|
   | `block`, `district`, `division` | From household |
   | `total_beneficiaries_with_cases` | COUNT DISTINCT beneficiary_id |
   | `repeat_beneficiaries` | COUNT DISTINCT where `is_repeat` = True |
   | `repeat_rate` | `repeat_beneficiaries` / `total_beneficiaries_with_cases` |
   | `avg_admissions_per_patient` | AVG of `total_admissions` across all beneficiaries with cases |
   | `same_proc_same_hosp_pairs_total` | SUM across all beneficiaries |
   | `same_proc_diff_hosp_pairs_total` | SUM across all beneficiaries |
   | `diff_proc_pairs_total` | SUM across all beneficiaries |
   | `possible_treatment_failure_rate` | `same_proc_same_hosp_pairs_total` / total repeat pairs. High ratio means people are returning to the same hospital for the same thing. |

6. Flag:
   | Flag | Condition |
   |------|-----------|
   | `high_repeat_rate` | `repeat_rate` above 75th percentile |
   | `possible_treatment_failure` | `possible_treatment_failure_rate` above 0.5 AND `repeat_beneficiaries` >= 5 (minimum threshold to avoid noise) |

**Output:** `./analytics/gap_repeat_utilization.parquet`

---

## Analysis 7: Seasonal Demand Patterns

**Question:** Do certain blocks experience seasonal surges that overwhelm local capacity?

**Source:** `int_demand_supply.parquet`, `cm_case.csv`, `cm_case_diagnosis.csv`, `bm_household.csv`

### Logic:

1. From `int_demand_supply`, compute per block:
   - Monthly average case count (mean across all months where total_cases is not null)
   - Monthly standard deviation
   - For each month, compute z-score: (`total_cases` - mean) / std_dev

   **Minimum threshold:** Only compute seasonality metrics for blocks with at least 12 total cases across all months AND at least 6 months with non-zero cases. Below this threshold, seasonal patterns are noise. Set all seasonality metrics to null and `is_seasonal` to False for these blocks.

2. Flag surge months (only for blocks meeting threshold):
   | Flag | Condition |
   |------|-----------|
   | `surge_month` | z-score > 1.5 for that block in that month |

3. Add disease category overlay:
   - For surge months, join to case-level data with disease categories (from Analysis 3's ICD mapping logic — reuse the same mapping function) to identify WHAT is surging.
   - Group by block + district + month + disease_category for surge months only.
   - Identify the dominant disease category driving each surge.

4. Seasonal summary per block (only for blocks meeting threshold):
   | Column | Derivation |
   |--------|------------|
   | `block`, `district`, `division` | Location |
   | `is_seasonal` | True if block meets minimum threshold AND has at least one surge month |
   | `peak_months` | List of calendar months (1-12) where surges tend to occur (aggregate across years — e.g., if July 2023 and July 2024 both had surges, July is a peak month) |
   | `peak_disease_category` | Most common disease category during surge months |
   | `seasonality_index` | Coefficient of variation of monthly case counts (std/mean). Higher = more seasonal. Null if below threshold. |
   | `peak_to_trough_ratio` | MAX monthly cases / MIN monthly cases (excluding zero-case months to avoid infinity). Null if below threshold. |

**Output:** `./analytics/gap_seasonal_patterns.parquet` (block × month with surge flags)
**Output:** `./analytics/gap_seasonal_summary.parquet` (block-level seasonal profile)

---

## Analysis 8: Delisted Hospital Impact

**Question:** Which blocks have lost effective hospital capacity due to delisting?

**Source:** `hm_hospital.csv`, `hm_specialty_offered.csv`, `int_demand_supply.parquet`

### Logic:

1. From `hm_hospital`, identify delisted hospitals (`delisted_from_gov_schemes` = True).

2. For each delisted hospital, compute its share of the block's capacity:
   | Column | Derivation |
   |--------|------------|
   | `hospital_id` | Delisted hospital |
   | `block`, `district` | Hospital's location (`block_name`, `district_name`) |
   | `delisted_beds` | `inpatient_beds` of this hospital |
   | `block_total_beds` | Total inpatient beds in this block (ALL hospitals, including delisted) |
   | `bed_share_lost` | `delisted_beds` / `block_total_beds`. Null if `block_total_beds` = 0. |
   | `delisted_specialties` | List of specialties this hospital offered (from `hm_specialty_offered` joined on hospital_id) |

3. Flag critical impact:
   | Flag | Condition |
   |------|-----------|
   | `sole_provider_delisted` | Block had only 1 hospital and it's delisted |
   | `majority_capacity_lost` | `bed_share_lost` > 0.5 (lost more than half the block's beds) |
   | `specialty_lost` | Any specialty that was ONLY offered by the delisted hospital in that block (check: for each delisted specialty, count how many OTHER non-delisted hospitals in the same block+district also offer it. If zero, it's lost.) |

4. Join to demand data to assess impact:
   - For blocks with delisted hospitals, compute `block_remaining_beds` = `block_total_beds` - `delisted_beds`.
   - Pull `total_cases_all_months` from Analysis 1 output (or aggregate from `int_demand_supply`).
   - `block_cases_per_remaining_bed` = `total_cases_all_months` / `block_remaining_beds`. Null if remaining = 0.

**Output:** `./analytics/gap_delisted_impact.parquet`

Columns: hospital_id, hospital_name, block, district, division, delisted_beds, block_total_beds, block_remaining_beds, bed_share_lost, delisted_specialties, sole_provider_delisted (bool), majority_capacity_lost (bool), specialties_lost (list), block_total_cases, block_cases_per_remaining_bed

---

## Technical Notes

- Use `pandas` for data manipulation, `scipy.stats` for z-scores if needed.
- All rates/proportions remain as 0-1 floats.
- For z-scores: use the block-level population mean and std dev. Handle cases where std dev = 0 (all blocks identical) by setting z-score to 0.
- Print summary after each analysis: row count, distribution of flags, top/bottom 5 blocks by key metrics.
- **Do NOT discard any blocks.** Blocks with zero hospitals or zero cases are especially important — they may represent the worst gaps.

---

## Output File Count

9 parquet files total:
1. `gap_utilization_scores.parquet`
2. `gap_specialty_matrix.parquet`
3. `gap_disease_burden.parquet`
4. `gap_portability_flows.parquet`
5. `gap_district_patient_flows.parquet`
6. `gap_card_dropoff.parquet`
7. `gap_repeat_utilization.parquet`
8. `gap_seasonal_patterns.parquet`
9. `gap_seasonal_summary.parquet`

---

## Success Criteria

Phase 2 Product 1 is complete when:
1. All 9 output parquet files exist in `./analytics/`.
2. Console output shows summary statistics for each analysis.
3. A brief `phase2_product1_summary.md` is written listing: files created, row counts, key findings (top 10 gap blocks, most common specialty gaps, largest patient flows), and any assumptions made.
