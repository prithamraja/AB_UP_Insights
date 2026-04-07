# Phase 1 — Data Preparation Spec

## Objective

Read the 21 raw CSV files for the Ayushman Bharat PM-JAY Uttar Pradesh synthetic dataset and produce a set of clean, joined intermediate tables (as parquet files) that serve as the foundation for two analytical products:

1. **Demand-Supply Gap Analysis** (block-level, monthly trends)
2. **Hospital Performance Benchmarking** (hospital × procedure × month)

All outputs go to `./intermediate/` directory as `.parquet` files.

**Primary geographic unit: Block** — with district and division retained as roll-up dimensions on every table.

---

## Source Files

All source CSVs are located in `/mnt/user-data/uploads/`. The 21 tables are:

### Reference
- `ref_up_geography.csv`
- `ref_hbp_procedure_master.csv`

### Beneficiary Management
- `bm_household.csv`
- `bm_beneficiary.csv`
- `bm_id_document.csv`
- `bm_enrolment_request.csv`
- `bm_card.csv`

### Hospital Management
- `hm_hospital.csv`
- `hm_hospital_bank_account.csv`
- `hm_license_certificate.csv`
- `hm_specialty_offered.csv`
- `hm_staff.csv`

### Claims Management
- `cm_case.csv`
- `cm_case_diagnosis.csv`
- `cm_preauth_request.csv`
- `cm_preauth_procedure_line.csv`
- `cm_discharge.csv`
- `cm_claim.csv`
- `cm_claim_document.csv`
- `cm_adjudication_event.csv`
- `cm_payment.csv`

---

## Step 1: Load and Validate

Use Python with pandas. For each CSV:

1. Load into a DataFrame.
2. Print shape (rows, columns).
3. Check for expected primary key uniqueness (see table definitions in README).
4. Check foreign key referential integrity — flag any orphan records but do NOT drop them (they may be intentional anomalies).
5. Parse all timestamp/date columns as datetime.
6. Print null percentages for every column.

**Output:** A validation summary printed to console (no file needed). If any critical issue is found (e.g., a PK is not unique where it should be), stop and report.

---

## Step 2: Derived Columns on Source Tables

Add these columns to the source DataFrames before joining:

### On `bm_beneficiary`:
- `age_at_record` = current year (2026) minus `yob`. If `yob` is null, leave null.
- `age_band` = categorical: `0-5`, `6-14`, `15-30`, `31-45`, `46-60`, `60+`

### On `cm_case`:
- `admission_date` = date portion of `admission_datetime`
- `discharge_date_derived` = date portion of `discharge_datetime`
- `los_days` = (`discharge_datetime` - `admission_datetime`).days. If negative or null, flag as anomaly but keep.
- `admission_year` = year from `admission_datetime`
- `admission_month` = YYYY-MM string from `admission_datetime` (e.g., `2024-03`)

### On `cm_claim`:
- `amount_diff` = `amount_claimed` - `amount_approved` (null if `amount_approved` is null)
- `approval_ratio` = `amount_approved` / `amount_claimed` (null if either is null)

### On `hm_hospital`:
- `capacity_band` = categorical based on `total_bed_strength`: `Small (<30)`, `Medium (30-100)`, `Large (100-300)`, `Very Large (300+)`

---

## Step 2b: Pre-aggregate Claims per Case

**IMPORTANT — prevents row explosion in downstream joins.**

`cm_claim` can have multiple rows per `case_id`. Before joining claims to cases anywhere, first build a helper table `claims_per_case`:

Group `cm_claim` by `case_id` and compute:

| Column | Derivation |
|--------|------------|
| `case_id` | Group key |
| `total_amount_claimed` | SUM of `amount_claimed` |
| `total_amount_approved` | SUM of `amount_approved` |
| `claim_count` | COUNT |
| `any_claim_approved` | True if ANY claim has `claim_status` in (APPROVED, SETTLED) |
| `any_claim_rejected` | True if ANY claim has `claim_status` = REJECTED |
| `any_claim_queried` | True if ANY claim has `claim_status` = QUERY_RAISED |
| `any_claim_pending` | True if ANY claim has `claim_status` = PENDING |
| `max_query_count` | MAX of `query_count` |
| `total_query_count` | SUM of `query_count` |
| `min_settlement_tat_days` | MIN of `settlement_tat_days` (first settlement) |
| `avg_settlement_tat_days` | AVG of `settlement_tat_days` |
| `is_portability_claim` | MAX (True if any claim is portability) |
| `worst_claim_status` | Use priority: REJECTED > QUERY_RAISED > PENDING > APPROVED > SETTLED. Take the "worst" status across all claims for the case. |

This gives exactly one row per case_id. Use this helper for all downstream joins instead of joining `cm_claim` directly.

---

## Step 3: Build Intermediate Table 1 — `int_demand_supply`

**Purpose:** One row per block per month, combining demand signals (enrolment, cases) with supply signals (hospitals, beds, specialties). District and division are retained as roll-up columns.

**IMPORTANT — start from the geography spine, not from demand.** Blocks with enrolled beneficiaries but zero cases are exactly the access-barrier signals we want to detect. Starting from demand would make these blocks invisible.

### Base Spine:
Create a complete spine of all block+district+division+month combinations:
- Blocks: All unique block+district+division combos from `ref_up_geography.csv`
- Months: All unique `admission_month` values from `cm_case` (to define the time range)
- Cross join to produce every block × month combination

### Demand Side (group by block + district + division + admission_month):
From `cm_case` joined to `bm_beneficiary` (on beneficiary_id) joined to `bm_household` (on household_id). The beneficiary's HOME location (from household) defines the demand block, NOT the hospital's location.

Use `claims_per_case` (from Step 2b) joined to `cm_case` on case_id for financial columns.

| Column | Derivation |
|--------|------------|
| `block` | `bm_household.home_block_name` |
| `district` | `bm_household.home_district_code` |
| `division` | `bm_household.home_division_name` |
| `month` | `cm_case.admission_month` (YYYY-MM) |
| `total_cases` | COUNT of cases (count from `cm_case`, NOT from claims join) |
| `emergency_cases` | COUNT where `cm_case.admission_type` = EMERGENCY |
| `elective_cases` | COUNT where `cm_case.admission_type` = ELECTIVE |
| `portability_out_cases` | COUNT where `cm_case.is_portability` = True |
| `unique_beneficiaries` | COUNT DISTINCT `cm_case.beneficiary_id` |
| `total_amount_claimed` | SUM of `claims_per_case.total_amount_claimed` |
| `total_amount_approved` | SUM of `claims_per_case.total_amount_approved` |
| `death_cases` | COUNT where `cm_case.discharge_type` = DEATH |
| `lama_dama_cases` | COUNT where `cm_case.discharge_type` in (LAMA, DAMA) |

### Supply Side (static per block — snapshot, not monthly):
From `hm_hospital`:

| Column | Derivation |
|--------|------------|
| `block` | `hm_hospital.block_name` |
| `district` | `hm_hospital.district_name` |
| `division` | `hm_hospital.division_name` |
| `total_hospitals` | COUNT of hospitals |
| `public_hospitals` | COUNT where `hospital_type` = PUBLIC |
| `private_hospitals` | COUNT where `hospital_type` = PRIVATE |
| `total_beds` | SUM of `total_bed_strength` |
| `total_inpatient_beds` | SUM of `inpatient_beds` |
| `hospitals_with_icu` | COUNT where `has_icu_with_ac` = True |
| `hospitals_with_ot` | COUNT where `has_fully_equipped_ot` = True |
| `delisted_hospitals` | COUNT where `delisted_from_gov_schemes` = True |
| `accredited_hospitals` | COUNT where `accreditation_board` is not null/blank |
| `specialties_available` | COUNT DISTINCT specialties from `hm_specialty_offered` joined to hospital |

### Enrolment Side (static per block — cumulative snapshot):
From `bm_household` joined to `bm_beneficiary`:

| Column | Derivation |
|--------|------------|
| `block` | `bm_household.home_block_name` |
| `district` | `bm_household.home_district_code` |
| `total_households_enrolled` | COUNT DISTINCT `household_id` |
| `total_beneficiaries_enrolled` | COUNT DISTINCT `beneficiary_id` |
| `active_cards` | COUNT from `bm_card` where `card_status` = ACTIVE, joined via beneficiary_id to get block |

### Join Logic:
- Start from the **geography spine** (all block × month combos).
- Left join demand on block + district + month.
- Left join supply (static) on block + district.
- Left join enrolment (static) on block + district.
- **Important:** Join on BOTH block AND district to avoid false matches (block names can repeat across districts).
- Blocks with zero demand in a given month will have null/0 in demand columns — this is correct and desired.

### Computed Columns on the Joined Table:
| Column | Derivation |
|--------|------------|
| `cases_per_1000_enrolled` | (`total_cases` / `total_beneficiaries_enrolled`) * 1000. Null if either is null or zero. |
| `cases_per_bed` | `total_cases` / `total_inpatient_beds`. Null if beds = 0 or null. |
| `utilization_rate` | `unique_beneficiaries` / `total_beneficiaries_enrolled`. Null if denominator is 0 or null. |
| `portability_out_rate` | `portability_out_cases` / `total_cases`. Null if total_cases = 0 or null. |
| `bed_density_per_1000` | (`total_inpatient_beds` / `total_beneficiaries_enrolled`) * 1000. Null if denominator is 0 or null. |

**Output:** `./intermediate/int_demand_supply.parquet`

---

## Step 4: Build Intermediate Table 2 — `int_hospital_performance`

**Purpose:** One row per hospital per procedure per month, aggregating performance metrics. This grain allows both procedure-level benchmarking and monthly trend analysis per hospital.

### Join Chain (with explicit cardinality handling):

1. Start from `cm_case` — one row per case.
2. Join `cm_case` to `hm_hospital` on `hospital_id` — many-to-one, safe.
3. Join `cm_case` to `cm_preauth_request` on `case_id` — one case can have 1+ preauths. **Use only the preauth where `status` is not REJECTED or CANCELLED (i.e., the active/approved preauth). If multiple, take the latest by `initiated_at`.** This gives one preauth per case.
4. Join preauth to `cm_preauth_procedure_line` on `preauth_id` — one preauth has 1-3 procedure lines. **Use only `procedure_rank = 1` (primary procedure) for the purpose of grouping by procedure.** Add-on procedures (rank 2, 3) are excluded from this table to avoid double-counting cases. If add-on analysis is needed, it will be handled in Phase 2.
5. Join procedure line to `ref_hbp_procedure_master` on `hbp_procedure_code` — many-to-one, safe.
6. Join `cm_case` to `cm_discharge` on `case_id` — one-to-one, safe.
7. Join `cm_case` to `claims_per_case` (from Step 2b) on `case_id` — one-to-one, safe.

After this chain, there should be exactly **one row per case**, with the primary procedure identified. Then group by hospital_id + hbp_procedure_code + admission_month.

### Group By:
- `hospital_id`
- `hbp_procedure_code`
- `admission_month` (YYYY-MM from `cm_case.admission_month`)

### Columns:

| Column | Derivation |
|--------|------------|
| `hospital_id` | From `cm_case` |
| `hospital_name` | From `hm_hospital` |
| `hospital_type` | PUBLIC or PRIVATE |
| `hospital_sub_type` | From `hm_hospital` |
| `block` | From `hm_hospital.block_name` |
| `district` | From `hm_hospital.district_name` |
| `division` | From `hm_hospital.division_name` |
| `capacity_band` | From derived column on `hm_hospital` |
| `hbp_procedure_code` | From procedure line (rank 1 only) |
| `procedure_name` | From `ref_hbp_procedure_master` |
| `specialty_code` | From `ref_hbp_procedure_master` |
| `specialty_name` | From `ref_hbp_procedure_master` |
| `base_package_price` | From `ref_hbp_procedure_master` |
| `month` | `admission_month` (YYYY-MM) |
| `case_count` | COUNT of cases |
| `avg_los_days` | AVG of `cm_case.los_days` |
| `median_los_days` | MEDIAN of `cm_case.los_days` |
| `avg_amount_claimed` | AVG of `claims_per_case.total_amount_claimed` |
| `avg_amount_approved` | AVG of `claims_per_case.total_amount_approved` |
| `avg_approval_ratio` | AVG of (`claims_per_case.total_amount_approved` / `claims_per_case.total_amount_claimed`) |
| `total_amount_claimed` | SUM of `claims_per_case.total_amount_claimed` |
| `total_amount_approved` | SUM of `claims_per_case.total_amount_approved` |
| `claim_approval_rate` | proportion of cases where `claims_per_case.any_claim_approved` = True |
| `claim_rejection_rate` | proportion of cases where `claims_per_case.any_claim_rejected` = True |
| `claim_query_rate` | proportion of cases where `claims_per_case.any_claim_queried` = True |
| `avg_query_count` | AVG of `claims_per_case.total_query_count` |
| `normal_discharge_rate` | proportion of cases with `cm_case.discharge_type` = NORMAL or LIVE |
| `lama_dama_rate` | proportion of cases with `cm_case.discharge_type` in (LAMA, DAMA) |
| `mortality_rate` | proportion of cases with `cm_case.discharge_type` = DEATH |
| `avg_settlement_tat_days` | AVG of `claims_per_case.avg_settlement_tat_days` |
| `preauth_auto_approval_rate` | proportion of cases where preauth `status` = AUTO_APPROVED |
| `biometric_auth_rate` | proportion of cases where `cm_discharge.biometric_auth_used` = True |
| `medicines_provided_rate` | proportion of cases where `cm_discharge.provided_medicines_flag` = True |

**Note on sparse cells:** At hospital × procedure × month grain, many cells will have low case counts (1-3 cases). This is expected. Phase 2 will handle minimum thresholds for statistical validity when benchmarking. Do NOT filter out low-count rows here.

**Output:** `./intermediate/int_hospital_performance.parquet`

---

## Step 5: Build Intermediate Table 3 — `int_enrolment_monthly`

**Purpose:** Monthly enrolment trend per block (with district and division roll-up) for demand-side time series.

### Logic:
From `bm_beneficiary` joined to `bm_household` (on household_id), group by `home_block_name` + `home_district_code` + `home_division_name` + YYYY-MM of `bm_beneficiary.created_at`:

| Column | Derivation |
|--------|------------|
| `block` | `bm_household.home_block_name` |
| `district` | `bm_household.home_district_code` |
| `division` | `bm_household.home_division_name` |
| `month` | YYYY-MM of `bm_beneficiary.created_at` |
| `new_beneficiaries_enrolled` | COUNT of beneficiaries |
| `cumulative_beneficiaries` | Cumulative SUM of `new_beneficiaries_enrolled` over months, per block+district |
| `new_cards_issued` | COUNT from `bm_card` where `issued_at` falls in this month, joined via `bm_card.beneficiary_id` → `bm_beneficiary.beneficiary_id` → `bm_household` for block |
| `cumulative_cards_issued` | Cumulative SUM of `new_cards_issued` over months per block+district |

**Output:** `./intermediate/int_enrolment_monthly.parquet`

---

## Step 6: Build Intermediate Table 4 — `int_specialty_gap`

**Purpose:** Per block, compare specialty demand (from cases) vs. specialty supply (from hospital offerings). District and division retained for roll-up.

### Demand:
From `cm_case` → `cm_preauth_request` (on case_id) → `cm_preauth_procedure_line` (on preauth_id) → `ref_hbp_procedure_master` (on hbp_procedure_code). Then join `cm_case` → `bm_beneficiary` (on beneficiary_id) → `bm_household` (on household_id) for home location.

**Use only `procedure_rank = 1`** to count each case once under its primary specialty.

Group by `home_block_name` + `home_district_code` + `home_division_name` + `specialty_code`:

| Column | Derivation |
|--------|------------|
| `block` | Beneficiary's home block (`bm_household.home_block_name`) |
| `district` | Beneficiary's home district (`bm_household.home_district_code`) |
| `division` | Beneficiary's home division (`bm_household.home_division_name`) |
| `specialty_code` | From `ref_hbp_procedure_master.specialty_code` |
| `specialty_name` | From `ref_hbp_procedure_master.specialty_name` |
| `cases_demanding` | COUNT of cases |
| `unique_patients` | COUNT DISTINCT `cm_case.beneficiary_id` |
| `amount_claimed` | SUM of `claims_per_case.total_amount_claimed` |

### Supply:
From `hm_hospital` → `hm_specialty_offered` (on hospital_id), group by `hm_hospital.block_name` + `hm_hospital.district_name` + `hm_specialty_offered.specialty_code`:

| Column | Derivation |
|--------|------------|
| `block` | Hospital's block (`hm_hospital.block_name`) |
| `district` | Hospital's district (`hm_hospital.district_name`) |
| `specialty_code` | From `hm_specialty_offered.specialty_code` |
| `hospitals_offering` | COUNT DISTINCT `hm_hospital.hospital_id` |
| `total_prev_fy_admissions` | SUM of `hm_specialty_offered.admissions_prev_fy` |

### Join:
Full outer join on block + district + specialty_code. Compute:

| Column | Derivation |
|--------|------------|
| `gap_flag` | True if `cases_demanding` > 0 but `hospitals_offering` = 0 or null |
| `demand_supply_ratio` | `cases_demanding` / `hospitals_offering` (null if no supply) |
| `unmet_demand` | True if `gap_flag` = True OR `demand_supply_ratio` > reasonable threshold (leave threshold for Phase 2) |

**Output:** `./intermediate/int_specialty_gap.parquet`

---

## Technical Notes

- Use `pandas` for data manipulation.
- Use `pyarrow` for parquet output.
- Handle nulls gracefully — do not fill with zeros unless explicitly stated. For computed ratios, return null (not infinity or zero) when the denominator is 0 or null.
- All monetary values are in INR, keep as float.
- All rates/ratios should be 0-1 floats (not percentages).
- Print a summary after each intermediate table: row count, column count, sample of 3 rows.
- If any source CSV is missing, stop and report.
- **Block name uniqueness:** Block names are NOT unique across districts. Always use block + district as a composite key when joining or grouping.
- **Month format:** Always YYYY-MM as string (e.g., `2024-03`).
- **One-to-many discipline:** Never join a one-to-many table directly into an aggregation without pre-aggregating it first. The `claims_per_case` helper (Step 2b) exists for this reason. If any other one-to-many relationship is discovered during implementation, pre-aggregate before joining.

---

## Success Criteria

Phase 1 is complete when:
1. All 4 intermediate parquet files exist in `./intermediate/`.
2. Validation step reports no critical PK/FK issues.
3. Console output shows row counts and sample data for each intermediate table.
4. A brief `phase1_summary.md` is written listing: files created, row counts, any anomalies found, and any assumptions made.
