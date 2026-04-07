# Phase 1: Data Ingestion & Analytical View Materialization

## Overview

This phase reads the 21 source CSVs from the Ayushman Bharat PM-JAY synthetic dataset for Uttar Pradesh, validates them, and materializes four denormalized analytical views. These views are the foundation for the MetaInsight engine in subsequent phases.

**Inputs:** 21 CSV files (see Source Tables below)  
**Outputs:** 4 Parquet files (one per analytical view) + 1 validation report  
**Estimated data:** ~50K households, ~200K beneficiaries, ~800 hospitals, ~22.5K cases  
**Tech stack:** Python 3.10+, pandas, pyarrow  

---

## 1. Source Tables

### Reference Tables (2)
| File | Primary Key | ~Rows |
|------|------------|-------|
| `ref_up_geography.csv` | composite (district_name, block_name) | ~1,000 |
| `ref_hbp_procedure_master.csv` | hbp_procedure_code | 25 |

### Beneficiary Management (5)
| File | Primary Key | ~Rows |
|------|------------|-------|
| `bm_household.csv` | household_id | 50,000 |
| `bm_beneficiary.csv` | beneficiary_id | ~200,000 |
| `bm_id_document.csv` | id_doc_id | ~300,000 |
| `bm_enrolment_request.csv` | enrolment_request_id | ~200,000 |
| `bm_card.csv` | card_id | ~190,000 |

### Hospital Management (5)
| File | Primary Key | ~Rows |
|------|------------|-------|
| `hm_hospital.csv` | hospital_id | ~800 |
| `hm_hospital_bank_account.csv` | hospital_bank_id | ~800 |
| `hm_license_certificate.csv` | hospital_license_id | ~4,000 |
| `hm_specialty_offered.csv` | hospital_specialty_id | ~4,000 |
| `hm_staff.csv` | staff_id | ~5,000 |

### Claims Management (9)
| File | Primary Key | ~Rows |
|------|------------|-------|
| `cm_case.csv` | case_id | ~22,500 |
| `cm_case_diagnosis.csv` | case_diagnosis_id | ~35,000 |
| `cm_preauth_request.csv` | preauth_id | ~22,500 |
| `cm_preauth_procedure_line.csv` | preauth_proc_id | ~28,000 |
| `cm_discharge.csv` | discharge_id | ~22,500 |
| `cm_claim.csv` | claim_id | ~22,500 |
| `cm_claim_document.csv` | claim_doc_id | ~110,000 |
| `cm_adjudication_event.csv` | event_id | ~70,000 |
| `cm_payment.csv` | payment_id | ~19,000 |

> Row counts are estimates from the README. Actual counts will be confirmed during ingestion.

---

## 2. Data Ingestion (Layer 0)

### 2.1 Load all CSVs

```python
import pandas as pd
import os

DATA_DIR = "path/to/csv/files"

tables = {}
csv_files = [
    "ref_up_geography", "ref_hbp_procedure_master",
    "bm_household", "bm_beneficiary", "bm_id_document",
    "bm_enrolment_request", "bm_card",
    "hm_hospital", "hm_hospital_bank_account",
    "hm_license_certificate", "hm_specialty_offered", "hm_staff",
    "cm_case", "cm_case_diagnosis", "cm_preauth_request",
    "cm_preauth_procedure_line", "cm_discharge", "cm_claim",
    "cm_claim_document", "cm_adjudication_event", "cm_payment"
]

for name in csv_files:
    filepath = os.path.join(DATA_DIR, f"{name}.csv")
    tables[name] = pd.read_csv(filepath)
    print(f"{name}: {tables[name].shape[0]} rows, {tables[name].shape[1]} cols")
```

### 2.2 Type Casting

Apply these type conversions after loading:

**UUIDs:** Keep as string (object dtype). Columns: all `*_id` columns.

**Timestamps:** Parse to datetime64. Columns:
- `created_at`, `updated_at` (multiple tables)
- `submitted_at`, `reviewed_at` (bm_enrolment_request)
- `issued_at` (bm_card)
- `admission_datetime`, `discharge_datetime` (cm_case)
- `initiated_at`, `ppd_decision_at`, `last_query_at`, `last_query_response_at`, `cancelled_at` (cm_preauth_request)
- `submitted_at`, `settled_at` (cm_claim)
- `uploaded_at` (cm_claim_document)
- `event_time` (cm_adjudication_event)
- `payment_date` (cm_payment)
- `surgery_date`, `discharge_date`, `lama_date`, `death_date` (cm_discharge)
- `issue_date`, `expiry_date` (hm_license_certificate)
- `dob` (bm_beneficiary)

**Dates:** Parse to date. Columns: `hospital_bill_date` (cm_claim).

**Numerics:** Ensure float64 for monetary amounts:
- `base_package_price` (ref_hbp_procedure_master)
- `stratification_amount`, `implant_amount`, `incentive_amount`, `base_amount`, `computed_final_amount`, `expected_payable_amount`, `payout_factor` (cm_preauth_procedure_line)
- `amount_claimed`, `amount_approved` (cm_claim)
- `amount_paid` (cm_payment)

**Booleans:** Convert to bool:
- `has_stratification`, `has_implant_or_high_end`, `reserved_public_hospitals_only` (ref_hbp_procedure_master)
- `is_duplicate` (bm_beneficiary)
- `is_portability` (cm_case)
- `is_portability_claim` (cm_claim)
- `is_addon` (cm_preauth_procedure_line)
- `delisted_from_gov_schemes` (hm_hospital)
- `has_fully_equipped_ot`, `has_icu_with_ac`, `has_casualty`, `has_opd`, `has_hdu`, `has_general_ward`, `has_labour_room` (hm_hospital)
- `tds_exemption` (hm_hospital_bank_account)
- `provided_medicines_flag`, `biometric_auth_used` (cm_discharge)

### 2.3 Validation Checks

Run these checks and produce a validation report. **Do not drop or fix data** — log issues only. The synthetic data has intentional quality issues (3% duplicates, 7% expired licenses, etc.) that are analytically meaningful.

```
CHECK 1: Row counts — log actual vs expected for each table
CHECK 2: Primary key uniqueness — verify PK has no duplicates in each table
CHECK 3: Foreign key integrity — for each FK relationship, count orphan records
    - bm_beneficiary.household_id → bm_household.household_id
    - bm_id_document.beneficiary_id → bm_beneficiary.beneficiary_id
    - bm_enrolment_request.beneficiary_id → bm_beneficiary.beneficiary_id
    - bm_card.beneficiary_id → bm_beneficiary.beneficiary_id
    - hm_hospital_bank_account.hospital_id → hm_hospital.hospital_id
    - hm_license_certificate.hospital_id → hm_hospital.hospital_id
    - hm_specialty_offered.hospital_id → hm_hospital.hospital_id
    - hm_staff.hospital_id → hm_hospital.hospital_id
    - cm_case.beneficiary_id → bm_beneficiary.beneficiary_id
    - cm_case.hospital_id → hm_hospital.hospital_id
    - cm_case_diagnosis.case_id → cm_case.case_id
    - cm_preauth_request.case_id → cm_case.case_id
    - cm_preauth_procedure_line.preauth_id → cm_preauth_request.preauth_id
    - cm_preauth_procedure_line.hbp_procedure_code → ref_hbp_procedure_master.hbp_procedure_code
    - cm_preauth_procedure_line.clinician_staff_id → hm_staff.staff_id
    - cm_claim.case_id → cm_case.case_id
    - cm_claim.preauth_id → cm_preauth_request.preauth_id
    - cm_claim_document.claim_id → cm_claim.claim_id
    - cm_adjudication_event.claim_id → cm_claim.claim_id
    - cm_payment.claim_id → cm_claim.claim_id
    - cm_payment.hospital_bank_id → hm_hospital_bank_account.hospital_bank_id
CHECK 4: Null rates — for each column, log % null. Flag if significantly different from README specs
CHECK 5: Value distributions — for categorical columns, log unique values and compare to README
    - bm_beneficiary.gender should be {M, F}
    - cm_case.admission_type should be {EMERGENCY, ELECTIVE}
    - cm_case.discharge_type should be {NORMAL, LIVE, LAMA, DAMA, DEATH}
    - cm_claim.claim_status should be {APPROVED, SETTLED, QUERY_RAISED, REJECTED, PENDING}
    - hm_hospital.hospital_type should be {PUBLIC, PRIVATE}
    - etc.
CHECK 6: Date ranges — log min/max for all timestamp columns to confirm ~3-year span
```

Output: `validation_report.txt` with all check results.

---

## 3. Derived Columns

Before building views, create these derived columns on source tables. These are reused across multiple views.

### 3.1 On `bm_beneficiary`

```python
# Age group derived from yob (year of birth) — always populated
# Use reference year = max year in cm_case.admission_datetime
reference_year = tables["cm_case"]["admission_datetime"].dt.year.max()

def age_group(yob):
    if pd.isna(yob):
        return "UNKNOWN"
    age = reference_year - yob
    if age < 1: return "INFANT"
    if age <= 5: return "1-5"
    if age <= 14: return "6-14"
    if age <= 25: return "15-25"
    if age <= 40: return "26-40"
    if age <= 60: return "41-60"
    return "60+"

tables["bm_beneficiary"]["age_group"] = tables["bm_beneficiary"]["yob"].apply(age_group)
```

### 3.2 On `cm_case`

```python
# Temporal dimensions from admission_datetime
tables["cm_case"]["admission_month"] = tables["cm_case"]["admission_datetime"].dt.to_period("M").astype(str)
tables["cm_case"]["admission_quarter"] = tables["cm_case"]["admission_datetime"].dt.to_period("Q").astype(str)
tables["cm_case"]["admission_year"] = tables["cm_case"]["admission_datetime"].dt.year.astype(str)

# Length of stay in days
tables["cm_case"]["length_of_stay"] = (
    tables["cm_case"]["discharge_datetime"] - tables["cm_case"]["admission_datetime"]
).dt.total_seconds() / 86400

# Binary flags for discharge outcomes
tables["cm_case"]["is_emergency"] = (tables["cm_case"]["admission_type"] == "EMERGENCY").astype(int)
tables["cm_case"]["is_death"] = (tables["cm_case"]["discharge_type"] == "DEATH").astype(int)
tables["cm_case"]["is_lama_dama"] = tables["cm_case"]["discharge_type"].isin(["LAMA", "DAMA"]).astype(int)
```

### 3.3 On `cm_case_diagnosis` — Disease Category Mapping

```python
# Map ICD-10 codes to disease categories
# Based on the README's disease burden weights
# This mapping uses the first letter/section of ICD-10

def map_disease_category(icd_code):
    if pd.isna(icd_code):
        return "UNKNOWN"
    code = str(icd_code).upper().strip()
    first = code[0] if len(code) > 0 else ""

    # Maternal/Neonatal: O-codes (pregnancy/childbirth), P-codes (perinatal)
    if first in ("O", "P"):
        return "MATERNAL_NEONATAL"
    # Communicable: A/B-codes (infectious/parasitic)
    if first in ("A", "B"):
        return "COMMUNICABLE"
    # Injury: S/T-codes (injury, poisoning)
    if first in ("S", "T"):
        return "INJURY"
    # NCD: I-codes (circulatory), E-codes (endocrine/metabolic),
    #       J-codes (respiratory), N-codes (genitourinary), C/D-codes (neoplasms)
    if first in ("I", "E", "J", "N", "C", "D"):
        return "NCD"
    # Surgical: K-codes (digestive), H-codes (eye/ear), G-codes (nervous),
    #           M-codes (musculoskeletal), L-codes (skin)
    if first in ("K", "H", "G", "M", "L"):
        return "SURGICAL"
    return "OTHER"

tables["cm_case_diagnosis"]["disease_category"] = (
    tables["cm_case_diagnosis"]["icd_code"].apply(map_disease_category)
)
```

> Note: This ICD mapping is approximate. The README says diagnoses are weighted by category (NCD 30%, Communicable 28%, Maternal 18%, Surgical 16%, Injury 8%). Validate that the derived distribution roughly matches.

### 3.4 On `hm_hospital` — Bed Size Bucket

```python
def bed_size_bucket(beds):
    if pd.isna(beds):
        return "UNKNOWN"
    if beds <= 30:
        return "SMALL (<=30)"
    if beds <= 100:
        return "MEDIUM (31-100)"
    if beds <= 300:
        return "LARGE (101-300)"
    return "VERY_LARGE (300+)"

tables["hm_hospital"]["bed_size_bucket"] = (
    tables["hm_hospital"]["total_bed_strength"].apply(bed_size_bucket)
)
```

### 3.5 On `hm_license_certificate` — Expired Flag

```python
from datetime import datetime
reference_date = tables["cm_case"]["admission_datetime"].max()

tables["hm_license_certificate"]["is_expired"] = (
    tables["hm_license_certificate"]["expiry_date"] < reference_date
).astype(int)
```

---

## 4. Analytical View Construction (Layer 1)

### 4.1 View 1 — Claims Lifecycle

**Grain:** One row per case (case_id).  
**Purpose:** Full transactional journey from admission to payment.

#### Join Strategy

```
cm_case (anchor)
├── LEFT JOIN bm_beneficiary ON beneficiary_id
│   └── LEFT JOIN bm_household ON household_id
├── LEFT JOIN hm_hospital ON hospital_id
├── LEFT JOIN cm_case_diagnosis ON case_id WHERE diagnosis_rank = 1 (primary only)
├── LEFT JOIN cm_preauth_request ON case_id
│   └── LEFT JOIN cm_preauth_procedure_line ON preauth_id WHERE procedure_rank = 1 (primary only)
│       └── LEFT JOIN ref_hbp_procedure_master ON hbp_procedure_code
├── LEFT JOIN cm_claim ON case_id
├── LEFT JOIN cm_payment ON claim_id
└── LEFT JOIN cm_discharge ON case_id
```

> **Important:** For diagnosis, preauth_procedure_line, use only the PRIMARY record (rank = 1) to maintain one-row-per-case grain. If a case has multiple claims, take the first by submitted_at. If multiple payments per claim, sum amount_paid and take max payment_date.

#### Output Columns

**Dimensions (categorical):**
| Column | Source | Description |
|--------|--------|-------------|
| case_id | cm_case | PK |
| division | bm_household.home_division_name | Beneficiary's home division |
| district | bm_household.home_district_code | Beneficiary's home district |
| hospital_division | cm_case.hospital_division | Treating hospital's division |
| hospital_district | cm_case.hospital_district | Treating hospital's district |
| hospital_type | hm_hospital.hospital_type | PUBLIC or PRIVATE |
| hospital_sub_type | hm_hospital.hospital_sub_type | Civil Hospital, CHC, PHC, etc. |
| specialty_code | ref_hbp_procedure_master.specialty_code | Procedure specialty |
| specialty_name | ref_hbp_procedure_master.specialty_name | Procedure specialty full name |
| procedure_name | ref_hbp_procedure_master.procedure_name | Specific procedure |
| disease_category | cm_case_diagnosis (derived) | NCD, COMMUNICABLE, etc. |
| icd_code | cm_case_diagnosis.icd_code | Primary ICD-10 code |
| gender | bm_beneficiary.gender | M or F |
| age_group | bm_beneficiary (derived) | Age bucket |
| admission_type | cm_case.admission_type | EMERGENCY or ELECTIVE |
| discharge_type | cm_case.discharge_type | NORMAL, LAMA, DAMA, DEATH, LIVE |
| is_portability | cm_case.is_portability | Cross-state flag |
| claim_status | cm_claim.claim_status | APPROVED, REJECTED, etc. |
| preauth_status | cm_preauth_request.status | AUTO_APPROVED, APPROVED, etc. |
| payment_status | cm_payment.payment_status | SUCCESS, FAILED, INITIATED |
| accreditation_level | hm_hospital.accreditation_level | FULL, PRE, or blank |
| bed_size_bucket | hm_hospital (derived) | Hospital size category |

**Dimensions (temporal):**
| Column | Source | Description |
|--------|--------|-------------|
| admission_month | cm_case (derived) | e.g., "2023-04" |
| admission_quarter | cm_case (derived) | e.g., "2023Q2" |
| admission_year | cm_case (derived) | e.g., "2023" |

**Measures (numeric):**
| Column | Source | Description |
|--------|--------|-------------|
| case_count | literal 1 | Always 1, for counting |
| base_amount | cm_preauth_procedure_line | Base package price (INR) |
| computed_final_amount | cm_preauth_procedure_line | base + stratification + implant + incentive |
| expected_payable_amount | cm_preauth_procedure_line | final × payout factor |
| amount_claimed | cm_claim | Total claimed (INR) |
| amount_approved | cm_claim | Approved amount (INR) |
| amount_paid | cm_payment | Paid amount (INR) |
| settlement_tat_days | cm_claim | Days to settle |
| length_of_stay | cm_case (derived) | Days in hospital |
| is_emergency | cm_case (derived) | 0/1 flag |
| is_death | cm_case (derived) | 0/1 flag |
| is_lama_dama | cm_case (derived) | 0/1 flag |
| query_count | cm_claim | Number of queries raised |

**Impact measures for this view:** `case_count` (SUM), `amount_claimed` (SUM), `amount_paid` (SUM)

#### Expected Row Count
~22,500 rows (one per case)

---

### 4.2 View 2 — District-Month Performance Cube

**Grain:** One row per district × month.  
**Purpose:** Cross-domain aggregate metrics for geographic and temporal pattern discovery.

#### Build Strategy

This view is built by aggregating from multiple source tables independently and then joining on (district, month).

```python
# Step 1: Aggregate enrolment by district × month
enrol_agg = (
    bm_beneficiary
    .merge(bm_household, on="household_id")
    .assign(month=lambda df: df["created_at"].dt.to_period("M").astype(str))
    .groupby(["home_division_name", "home_district_code", "month"])
    .agg(
        new_beneficiaries=("beneficiary_id", "count"),
        new_households=("household_id", "nunique")
    )
    .reset_index()
)

# Step 2: Aggregate cards by district × month
card_agg = (
    bm_card
    .merge(bm_beneficiary, on="beneficiary_id")
    .merge(bm_household, on="household_id")
    .assign(month=lambda df: df["issued_at"].dt.to_period("M").astype(str))
    .groupby(["home_district_code", "month"])
    .agg(cards_issued=("card_id", "count"))
    .reset_index()
)

# Step 3: Aggregate cases by district × month (using beneficiary's home district)
# Also compute sub-aggregates by hospital_type, admission_type, discharge_type
case_agg = (
    cm_case
    .merge(bm_beneficiary, on="beneficiary_id")
    .merge(bm_household, on="household_id")
    .merge(hm_hospital[["hospital_id", "hospital_type"]], on="hospital_id")
    .assign(month=lambda df: df["admission_datetime"].dt.to_period("M").astype(str))
    .groupby(["home_division_name", "home_district_code", "month"])
    .agg(
        cases_admitted=("case_id", "count"),
        emergency_cases=("is_emergency", "sum"),
        portability_cases=("is_portability", "sum"),
        deaths=("is_death", "sum"),
        lama_dama_cases=("is_lama_dama", "sum"),
        public_cases=("hospital_type", lambda x: (x == "PUBLIC").sum()),
        private_cases=("hospital_type", lambda x: (x == "PRIVATE").sum()),
        unique_hospitals=("hospital_id", "nunique"),
        avg_length_of_stay=("length_of_stay", "mean")
    )
    .reset_index()
)

# Step 4: Aggregate claims and payments by district × month
claims_agg = (
    cm_claim
    .merge(cm_case, on="case_id")
    .merge(bm_beneficiary, on="beneficiary_id")
    .merge(bm_household, on="household_id")
    .assign(month=lambda df: df["submitted_at"].dt.to_period("M").astype(str))
    .groupby(["home_district_code", "month"])
    .agg(
        claims_submitted=("claim_id", "count"),
        claims_approved=("claim_status", lambda x: (x == "APPROVED").sum() + (x == "SETTLED").sum()),
        claims_rejected=("claim_status", lambda x: (x == "REJECTED").sum()),
        amount_claimed=("amount_claimed", "sum"),
        amount_approved=("amount_approved", "sum"),
        avg_settlement_tat=("settlement_tat_days", "mean")
    )
    .reset_index()
)

payments_agg = (
    cm_payment
    .merge(cm_claim, on="claim_id")
    .merge(cm_case, on="case_id")
    .merge(bm_beneficiary, on="beneficiary_id")
    .merge(bm_household, on="household_id")
    .assign(month=lambda df: df["payment_date"].dt.to_period("M").astype(str))
    .groupby(["home_district_code", "month"])
    .agg(
        amount_paid=("amount_paid", "sum"),
        payment_count=("payment_id", "count"),
        payment_failures=("payment_status", lambda x: (x == "FAILED").sum())
    )
    .reset_index()
)

# Step 5: Cumulative beneficiaries and cards (running total per district up to each month)
# This gives "total enrolled as of month X" rather than "new in month X"
# Implementation: sort by month, cumsum within district

# Step 6: Outer join all aggregates on (home_district_code, month), fill NaN with 0

# Step 7: Compute cross-domain ratios
# claims_per_1000_beneficiaries = (cases_admitted / cumulative_beneficiaries) * 1000
# approval_rate = claims_approved / claims_submitted
# emergency_share = emergency_cases / cases_admitted
# death_rate = deaths / cases_admitted
# public_private_ratio = public_cases / (private_cases + 1)  # +1 to avoid div by zero
# avg_claim_amount = amount_claimed / claims_submitted
```

#### Output Columns

**Dimensions:**
| Column | Description |
|--------|-------------|
| division | UP division name (18 values) |
| district | UP district name (75 values) |
| month | Period string, e.g., "2022-01" |
| quarter | Derived: e.g., "2022Q1" |
| year | Derived: e.g., "2022" |

**Measures (raw aggregates):**
| Column | Description |
|--------|-------------|
| new_beneficiaries | Newly enrolled in this month |
| cumulative_beneficiaries | Total enrolled up to this month |
| new_households | New households enrolled |
| cards_issued | Cards issued this month |
| cases_admitted | Cases admitted this month |
| emergency_cases | Emergency admissions |
| portability_cases | Cross-state cases |
| deaths | Death discharges |
| lama_dama_cases | LAMA + DAMA discharges |
| public_cases | Cases at public hospitals |
| private_cases | Cases at private hospitals |
| unique_hospitals | Distinct hospitals with activity |
| claims_submitted | Claims submitted |
| claims_approved | Claims approved or settled |
| claims_rejected | Claims rejected |
| amount_claimed | Total INR claimed |
| amount_approved | Total INR approved |
| amount_paid | Total INR paid |
| payment_count | Number of payments |
| payment_failures | Failed payments |
| avg_length_of_stay | Mean LOS in days |
| avg_settlement_tat | Mean settlement TAT in days |

**Measures (derived ratios):**
| Column | Description |
|--------|-------------|
| claims_per_1000_beneficiaries | Utilization rate |
| approval_rate | claims_approved / claims_submitted |
| emergency_share | emergency_cases / cases_admitted |
| death_rate | deaths / cases_admitted |
| public_private_ratio | public_cases / private_cases |
| avg_claim_amount | amount_claimed / claims_submitted |

**Impact measures for this view:** `cases_admitted` (SUM), `amount_claimed` (SUM), `cumulative_beneficiaries` (SUM)

#### Expected Row Count
~75 districts × ~36 months = ~2,700 rows. Some district-months may have zero activity; keep them with zero measures so temporal patterns are continuous.

---

### 4.3 View 3 — Hospital Performance

**Grain:** One row per hospital × specialty offered.  
**Purpose:** Structural capacity vs. actual utilization, specialty-level gap analysis.

#### Join Strategy

```
hm_hospital (anchor)
├── CROSS with hm_specialty_offered ON hospital_id (creates hospital × specialty matrix)
├── LEFT JOIN aggregated staff counts from hm_staff grouped by (hospital_id, role_type)
├── LEFT JOIN aggregated license data from hm_license_certificate grouped by hospital_id
├── LEFT JOIN aggregated claims data:
│   cm_case
│   → cm_preauth_request → cm_preauth_procedure_line → ref_hbp_procedure_master
│   → cm_claim → cm_payment
│   grouped by (hospital_id, specialty_code)
```

> **Critical:** The join between `hm_specialty_offered` and claims data must use LEFT JOIN on (hospital_id, specialty_code) so that specialties with zero claims still appear as rows. This is the foundation of the underutilization analysis.

#### Aggregating Claims per Hospital × Specialty

```python
# Build claims aggregation at hospital × specialty grain
hosp_spec_claims = (
    cm_case
    .merge(cm_preauth_request, on="case_id")
    .merge(cm_preauth_procedure_line[cm_preauth_procedure_line["procedure_rank"] == 1],
           on="preauth_id")
    .merge(ref_hbp_procedure_master[["hbp_procedure_code", "specialty_code"]], 
           on="hbp_procedure_code")
    .merge(cm_claim, on="case_id")
    .merge(cm_payment, on="claim_id", how="left")
    .groupby(["hospital_id", "specialty_code"])
    .agg(
        cases_treated=("case_id", "count"),
        preauth_approved=("status", lambda x: x.isin(["AUTO_APPROVED", "APPROVED"]).sum()),
        preauth_rejected=("status", lambda x: (x == "REJECTED").sum()),
        claims_approved=("claim_status", lambda x: x.isin(["APPROVED", "SETTLED"]).sum()),
        amount_claimed=("amount_claimed", "sum"),
        amount_approved=("amount_approved", "sum"),
        amount_paid=("amount_paid", "sum"),
        avg_settlement_tat=("settlement_tat_days", "mean"),
        emergency_count=("is_emergency", "sum"),
        death_count=("is_death", "sum")
    )
    .reset_index()
)
```

#### Aggregating Staff per Hospital

```python
# Count staff by hospital (not by specialty, since staff table doesn't map to specialty directly)
# But role_type can approximate: GYNAECOLOGIST → OBG, SURGEON → GS, etc.
hosp_staff = (
    hm_staff
    .groupby("hospital_id")
    .agg(
        total_staff=("staff_id", "count"),
        avg_experience_years=("experience_years", "mean")
    )
    .reset_index()
)
```

#### Aggregating License Compliance per Hospital

```python
hosp_license = (
    hm_license_certificate
    .groupby("hospital_id")
    .agg(
        total_licenses=("hospital_license_id", "count"),
        expired_licenses=("is_expired", "sum"),
        active_licenses=("is_expired", lambda x: (x == 0).sum())
    )
    .reset_index()
)
```

#### Output Columns

**Dimensions:**
| Column | Source | Description |
|--------|--------|-------------|
| hospital_id | hm_hospital | PK part 1 |
| specialty_code | hm_specialty_offered | PK part 2 |
| specialty_name | hm_specialty_offered | Full specialty name |
| division | hm_hospital.division_name | Hospital's division |
| district | hm_hospital.district_name | Hospital's district |
| hospital_type | hm_hospital | PUBLIC or PRIVATE |
| hospital_sub_type | hm_hospital | Civil Hospital, CHC, etc. |
| accreditation_level | hm_hospital | FULL, PRE, or blank |
| bed_size_bucket | hm_hospital (derived) | Size category |
| has_icu | hm_hospital.has_icu_with_ac | Boolean |
| has_ot | hm_hospital.has_fully_equipped_ot | Boolean |

**Measures:**
| Column | Source | Description |
|--------|--------|-------------|
| total_beds | hm_hospital | Total bed strength |
| inpatient_beds | hm_hospital | Inpatient beds |
| total_staff | aggregated | Staff count for this hospital |
| avg_experience_years | aggregated | Mean staff experience |
| admissions_prev_fy | hm_specialty_offered | Prior year admissions for this specialty |
| admissions_before_last_year | hm_specialty_offered | Year before that |
| cases_treated | aggregated from claims | Actual claims-backed case count |
| preauth_approved | aggregated | Approved preauths |
| preauth_rejected | aggregated | Rejected preauths |
| claims_approved | aggregated | Approved claims count |
| amount_claimed | aggregated | Total INR claimed |
| amount_approved | aggregated | Total INR approved |
| amount_paid | aggregated | Total INR paid |
| avg_settlement_tat | aggregated | Mean settlement TAT |
| emergency_count | aggregated | Emergency cases |
| death_count | aggregated | Deaths |
| zero_claim_flag | derived | 1 if cases_treated == 0, else 0 |
| cases_per_bed | derived | cases_treated / total_beds |
| total_licenses | aggregated | License count |
| expired_licenses | aggregated | Expired license count |
| active_licenses | aggregated | Active license count |

**Impact measures for this view:** `total_beds` (SUM), `cases_treated` (SUM), `amount_paid` (SUM)

#### Expected Row Count
~800 hospitals × ~5 specialties each = ~4,000 rows

---

### 4.4 View 4 — Beneficiary Journey

**Grain:** One row per beneficiary.  
**Purpose:** Enrolment quality, scheme access equity, demographic patterns in utilization.

#### Join Strategy

```
bm_beneficiary (anchor)
├── LEFT JOIN bm_household ON household_id
├── LEFT JOIN bm_enrolment_request ON beneficiary_id
│   (take latest by submitted_at if multiple)
├── LEFT JOIN bm_card ON beneficiary_id
│   (take latest by issued_at if multiple)
├── LEFT JOIN aggregated bm_id_document grouped by beneficiary_id
├── LEFT JOIN aggregated cm_case + cm_claim grouped by beneficiary_id
```

#### Aggregating Documents per Beneficiary

```python
doc_agg = (
    bm_id_document
    .groupby("beneficiary_id")
    .agg(
        document_count=("id_doc_id", "count"),
        has_aadhaar=("doc_type", lambda x: (x == "AADHAAR").any().astype(int))
    )
    .reset_index()
)
```

#### Aggregating Claims per Beneficiary

```python
benef_claims = (
    cm_case
    .merge(cm_claim, on="case_id", how="left")
    .groupby("beneficiary_id")
    .agg(
        claim_count=("case_id", "count"),
        total_amount_claimed=("amount_claimed", "sum"),
        total_amount_approved=("amount_approved", "sum"),
        first_admission_date=("admission_datetime", "min")
    )
    .reset_index()
)
```

#### Derived Columns

```python
# days_enrolment_to_card = card.issued_at - beneficiary.created_at (in days)
# days_card_to_first_claim = first_admission_date - card.issued_at (in days)
# has_claim = 1 if claim_count > 0 else 0

# document_count_bucket
def doc_count_bucket(n):
    if n == 0: return "NO_DOCS"
    if n == 1: return "1_DOC"
    if n <= 3: return "2-3_DOCS"
    return "4+_DOCS"
```

#### Output Columns

**Dimensions:**
| Column | Source | Description |
|--------|--------|-------------|
| beneficiary_id | bm_beneficiary | PK |
| division | bm_household.home_division_name | Home division |
| district | bm_household.home_district_code | Home district |
| gender | bm_beneficiary | M or F |
| age_group | bm_beneficiary (derived) | Age bucket |
| entitlement_source | bm_household | SECC, STATE_DB, RSBY |
| bis_record_status | bm_beneficiary | GOLD, SILVER, PENDING |
| enrolment_status | bm_enrolment_request | AUTO_APPROVED, ISA_APPROVED, etc. |
| auth_mode | bm_enrolment_request | OTP, FINGERPRINT, IRIS, OFFLINE |
| card_status | bm_card | ACTIVE, INACTIVE, DISABLED |
| has_aadhaar | bm_id_document (derived) | 0 or 1 |
| is_duplicate | bm_beneficiary | Boolean |
| document_count_bucket | derived | NO_DOCS, 1_DOC, 2-3_DOCS, 4+_DOCS |

**Measures:**
| Column | Source | Description |
|--------|--------|-------------|
| has_claim | derived | 0 or 1 |
| claim_count | aggregated | Total cases |
| total_amount_claimed | aggregated | Total INR claimed |
| total_amount_approved | aggregated | Total INR approved |
| days_enrolment_to_card | derived | Days from enrolment to card |
| days_card_to_first_claim | derived | Days from card to first hospital visit |
| document_count | aggregated | Number of ID documents |

**Impact measures for this view:** `COUNT(*)` (beneficiary count), `SUM(has_claim)` (active utilizers)

#### Expected Row Count
~200,000 rows (one per beneficiary)

---

## 5. Output

### 5.1 Save Views as Parquet

```python
import pyarrow as pa
import pyarrow.parquet as pq

OUTPUT_DIR = "views/"

view1.to_parquet(os.path.join(OUTPUT_DIR, "view1_claims_lifecycle.parquet"), index=False)
view2.to_parquet(os.path.join(OUTPUT_DIR, "view2_district_month_cube.parquet"), index=False)
view3.to_parquet(os.path.join(OUTPUT_DIR, "view3_hospital_performance.parquet"), index=False)
view4.to_parquet(os.path.join(OUTPUT_DIR, "view4_beneficiary_journey.parquet"), index=False)
```

### 5.2 Save Validation Report

Save `validation_report.txt` with all Layer 0 checks.

### 5.3 Save View Summaries

For each view, produce a summary containing:
- Actual row count and column count
- All column names with dtype
- Null counts per column
- For each dimension: unique value count and top 5 values by frequency
- For each measure: min, max, mean, median, std, null count
- Sample of 5 random rows

Save as `view_summaries.txt` or four separate `view{N}_summary.txt` files.

---

## 6. Validation Checklist

After building views, verify the following before moving to Phase 2:

- [ ] View 1 row count ≈ 22,500 (one per case)
- [ ] View 2 row count ≈ 2,700 (75 districts × ~36 months)
- [ ] View 3 row count ≈ 4,000 (800 hospitals × ~5 specialties)
- [ ] View 4 row count ≈ 200,000 (one per beneficiary)
- [ ] View 1: no duplicate case_ids
- [ ] View 2: no duplicate (district, month) pairs
- [ ] View 3: zero_claim_flag = 1 exists for some rows (confirms left join worked)
- [ ] View 3: no duplicate (hospital_id, specialty_code) pairs
- [ ] View 4: no duplicate beneficiary_ids
- [ ] View 2: claims_per_1000_beneficiaries is in a plausible range (not negative, not > 1000)
- [ ] View 2: approval_rate is between 0 and 1
- [ ] All monetary measures are non-negative
- [ ] Temporal dimensions in View 1 span approximately 3 years
- [ ] Disease category distribution roughly matches README weights (NCD ~30%, Communicable ~28%, Maternal ~18%, Surgical ~16%, Injury ~8%)
- [ ] View 1 gender distribution is roughly 50/50
- [ ] View 1 hospital_type distribution is roughly 60% PUBLIC / 40% PRIVATE
- [ ] View 3 has rows where cases_treated > 0 and rows where cases_treated == 0

---

## 7. Notes for Implementation

1. **Memory management:** The full dataset is ~300 MB in CSV. All four views together should be well under 100 MB in Parquet. Process one view at a time if memory is constrained.

2. **Colab compatibility:** If using Google Colab, upload CSVs to Google Drive and mount. Parquet output can stay in Colab's local storage or be saved back to Drive.

3. **Do not drop data quality issues.** The 3% duplicate beneficiaries, 7% expired licenses, and varying null rates are intentional features of the synthetic data. They represent real-world conditions and may surface as MetaInsight patterns in later phases.

4. **Edge cases to watch for:**
   - Cases with no claim (cm_claim left join produces nulls for claim columns)
   - Claims with no payment (cm_payment left join produces nulls)
   - Beneficiaries with no enrolment request or no card
   - Hospitals with specialties offered but zero cases
   - Division-by-zero in derived ratios (use fillna or +1 in denominator)

5. **Preserve the README.** Copy `README.md` alongside the output files — it serves as the data dictionary for all subsequent phases.
