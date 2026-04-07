# Data Fix: Synthetic Data Post-Processing

Two issues in the synthetic data need correction before the analytical views are reliable.

**Fix 1:** Beneficiary/household/card timestamps are all set to a single date  
**Fix 2:** Hospital specialty offerings don't reflect actual case activity (62% mismatch)

Run both fixes, then re-run `phase1_pipeline.py` to rebuild all four views.

---

## Prerequisites

```bash
# Back up originals before any modifications
mkdir -p ab_data/originals
cp ab_data/bm_beneficiary.csv ab_data/originals/
cp ab_data/bm_household.csv ab_data/originals/
cp ab_data/bm_card.csv ab_data/originals/
cp ab_data/bm_enrolment_request.csv ab_data/originals/
cp ab_data/hm_specialty_offered.csv ab_data/originals/
```

```python
import pandas as pd
import numpy as np

np.random.seed(42)  # reproducibility for both fixes
```

---

## Fix 1: Timestamps

### Problem

| Table | Column | Actual | Expected |
|-------|--------|--------|----------|
| `bm_beneficiary` | `created_at` | Single date: 2026-02-27 for all 205,847 rows | Spread across 2022-01 to 2026-01, preceding each beneficiary's first admission |
| `bm_beneficiary` | `updated_at` | Same issue | At or after `created_at` |
| `bm_card` | `issued_at` | All values ~same date | A few days to weeks after `beneficiary.created_at`, before first admission |
| `bm_household` | `created_at` | Likely single date | At or before the earliest `beneficiary.created_at` in that household |

### Downstream Impact

- View 2: `claims_per_1000_beneficiaries` is 97.2% null
- View 4: `days_enrolment_to_card` is -0.44 for every row
- View 4: `days_card_to_first_claim` is entirely negative
- Temporal enrolment patterns are invisible

### Temporal Consistency Constraint

All generated timestamps must satisfy:

```
household.created_at  ≤  beneficiary.created_at  ≤  card.issued_at  ≤  first case.admission_datetime
```

### Step 1.0: Determine the dataset time window

```python
cases = pd.read_csv("ab_data/cm_case.csv", parse_dates=["admission_datetime"])
dataset_start = cases["admission_datetime"].min()  # ~2023-02-28
dataset_end = cases["admission_datetime"].max()      # ~2026-01-28

# Enrolment window starts 12 months before first admission (scheme ramp-up)
enrol_window_start = dataset_start - pd.DateOffset(months=12)  # ~2022-02-28
enrol_window_end = dataset_end                                  # ~2026-01-28

enrol_start_ts = enrol_window_start.timestamp()
enrol_end_ts = enrol_window_end.timestamp()
```

### Step 1.1: Compute first admission date per beneficiary

```python
first_admission = (
    cases
    .groupby("beneficiary_id")["admission_datetime"]
    .min()
    .reset_index()
    .rename(columns={"admission_datetime": "first_admission_date"})
)
```

### Step 1.2: Generate beneficiary `created_at`

```python
beneficiaries = pd.read_csv("ab_data/bm_beneficiary.csv")
beneficiaries = beneficiaries.merge(first_admission, on="beneficiary_id", how="left")

has_claims = beneficiaries["first_admission_date"].notna()

# --- Beneficiaries WITH claims (~10%): enrol before first admission ---
upper_bounds = (
    beneficiaries.loc[has_claims, "first_admission_date"]
    .apply(lambda x: pd.Timestamp(x))
    - pd.Timedelta(days=14)
)
upper_ts = upper_bounds.astype(np.int64) / 1e9
upper_ts = upper_ts.clip(lower=enrol_start_ts + 86400)
fracs = np.random.uniform(0, 1, size=has_claims.sum())
ts_with = enrol_start_ts + fracs * (upper_ts.values - enrol_start_ts)
beneficiaries.loc[has_claims, "created_at"] = pd.to_datetime(ts_with, unit="s")

# --- Beneficiaries WITHOUT claims (~90%): spread with beta(2,3) ---
n_without = (~has_claims).sum()
fracs = np.random.beta(2, 3, size=n_without)
ts_without = enrol_start_ts + fracs * (enrol_end_ts - enrol_start_ts)
beneficiaries.loc[~has_claims, "created_at"] = pd.to_datetime(ts_without, unit="s")
```

### Step 1.3: Generate beneficiary `updated_at`

```python
random_offset = pd.to_timedelta(
    np.random.uniform(0, 90, size=len(beneficiaries)), unit="D"
)
beneficiaries["updated_at"] = beneficiaries["created_at"] + random_offset
```

### Step 1.4: Generate household `created_at`

```python
households = pd.read_csv("ab_data/bm_household.csv")

earliest_benef = (
    beneficiaries
    .groupby("household_id")["created_at"]
    .min()
    .reset_index()
    .rename(columns={"created_at": "earliest_member_created"})
)

households = households.merge(earliest_benef, on="household_id", how="left")

# Household created 0-7 days before first member
offset = pd.to_timedelta(
    np.random.uniform(0, 7, size=len(households)), unit="D"
)
households["created_at"] = households["earliest_member_created"] - offset
households = households.drop(columns=["earliest_member_created"])
```

### Step 1.5: Generate card `issued_at`

```python
cards = pd.read_csv("ab_data/bm_card.csv")

cards = cards.merge(
    beneficiaries[["beneficiary_id", "created_at", "first_admission_date"]],
    on="beneficiary_id", how="left"
)

# Card issued 1-30 days after enrolment
base_offset = pd.to_timedelta(
    np.random.uniform(1, 30, size=len(cards)), unit="D"
)
cards["issued_at"] = cards["created_at"] + base_offset

# Ensure card issuance is before first admission for beneficiaries with claims
has_admission = cards["first_admission_date"].notna()
too_late = has_admission & (cards["issued_at"] >= cards["first_admission_date"])

if too_late.any():
    safe_upper = cards.loc[too_late, "first_admission_date"] - pd.Timedelta(days=1)
    safe_lower = cards.loc[too_late, "created_at"] + pd.Timedelta(days=1)
    cards.loc[too_late, "issued_at"] = safe_lower + (safe_upper - safe_lower) / 2

cards = cards.drop(columns=["created_at", "first_admission_date"])
```

### Step 1.6: Fix `bm_enrolment_request` timestamps (if broken)

Check whether `submitted_at` and `reviewed_at` have the same single-date issue. If so:

```python
enrolment = pd.read_csv("ab_data/bm_enrolment_request.csv")

# Check: if all submitted_at are the same date, fix them
submitted_dates = pd.to_datetime(enrolment["submitted_at"])
if submitted_dates.nunique() < 10:
    print("bm_enrolment_request.submitted_at is broken — fixing")

    enrolment = enrolment.merge(
        beneficiaries[["beneficiary_id", "created_at"]],
        on="beneficiary_id", how="left"
    )

    # submitted_at = beneficiary.created_at + 0 to 3 days
    offset = pd.to_timedelta(
        np.random.uniform(0, 3, size=len(enrolment)), unit="D"
    )
    enrolment["submitted_at"] = enrolment["created_at"] + offset

    # reviewed_at = submitted_at + 0.5 to 14 days
    review_offset = pd.to_timedelta(
        np.random.uniform(0.5, 14, size=len(enrolment)), unit="D"
    )
    enrolment["reviewed_at"] = enrolment["submitted_at"] + review_offset

    enrolment = enrolment.drop(columns=["created_at"])
    enrolment.to_csv("ab_data/bm_enrolment_request.csv", index=False)
    print(f"Saved bm_enrolment_request.csv: {len(enrolment):,} rows")
else:
    print("bm_enrolment_request.submitted_at looks fine — skipping")
```

### Step 1.7: Save fixed CSVs

```python
beneficiaries = beneficiaries.drop(columns=["first_admission_date"])

beneficiaries.to_csv("ab_data/bm_beneficiary.csv", index=False)
households.to_csv("ab_data/bm_household.csv", index=False)
cards.to_csv("ab_data/bm_card.csv", index=False)

print("Fix 1 complete — timestamps fixed")
```

---

## Fix 2: Hospital Specialty Offerings

### Problem

`hm_specialty_offered` was randomly generated without reference to actual case activity. Result: 62% of cases are treated at hospitals that don't list the relevant specialty. This makes View 3's underutilization analysis unreliable — a "zero claims" row might mean the hospital treats that specialty but it's missing from the offerings list.

### Target

95% of cases should be treated at hospitals that list the relevant specialty. The remaining 5% become genuine anomalies — cases processed at hospitals without formal specialty listings (realistic: emergency referrals, cross-coverage, etc.).

### Approach

For each hospital:
1. Compute which specialties it actually treats and how many cases per specialty
2. Rank specialties by case volume
3. Add specialties to `hm_specialty_offered` (starting from highest volume) until 95% of that hospital's cases are covered
4. The bottom 5% of cases by volume remain as "beyond-registration" anomalies

### Step 2.0: Build the hospital × specialty case matrix

```python
# Join cases to their primary specialty
preauth = pd.read_csv("ab_data/cm_preauth_request.csv")
proc_lines = pd.read_csv("ab_data/cm_preauth_procedure_line.csv")
ref_proc = pd.read_csv("ab_data/ref_hbp_procedure_master.csv")

# Get primary procedure per case
primary_proc = proc_lines[proc_lines["procedure_rank"] == 1][["preauth_id", "hbp_procedure_code"]]
primary_proc = primary_proc.merge(preauth[["preauth_id", "case_id"]], on="preauth_id")
primary_proc = primary_proc.merge(
    ref_proc[["hbp_procedure_code", "specialty_code", "specialty_name"]],
    on="hbp_procedure_code"
)

# Attach hospital_id from cases
cases = pd.read_csv("ab_data/cm_case.csv")
case_specialty = primary_proc.merge(cases[["case_id", "hospital_id"]], on="case_id")

# Count cases per (hospital_id, specialty_code)
hosp_spec_counts = (
    case_specialty
    .groupby(["hospital_id", "specialty_code", "specialty_name"])
    .size()
    .reset_index(name="case_count")
    .sort_values(["hospital_id", "case_count"], ascending=[True, False])
)
```

### Step 2.1: Determine which specialties to add per hospital

```python
specialty_offered = pd.read_csv("ab_data/hm_specialty_offered.csv")

# Build set of currently offered (hospital_id, specialty_code) pairs
currently_offered = set(
    zip(specialty_offered["hospital_id"], specialty_offered["specialty_code"])
)

rows_to_add = []

for hospital_id, group in hosp_spec_counts.groupby("hospital_id"):
    total_cases = group["case_count"].sum()
    target = total_cases * 0.95  # cover 95% of cases

    cumulative = 0
    for _, row in group.iterrows():
        pair = (row["hospital_id"], row["specialty_code"])
        if pair not in currently_offered:
            # Need to add this specialty
            rows_to_add.append({
                "hospital_id": row["hospital_id"],
                "specialty_code": row["specialty_code"],
                "specialty_name": row["specialty_name"],
                "case_count_for_reference": row["case_count"],
            })
        cumulative += row["case_count"]
        if cumulative >= target:
            break  # 95% threshold reached — remaining specialties stay as anomalies

print(f"Specialties to add: {len(rows_to_add)}")
```

### Step 2.2: Generate new `hm_specialty_offered` rows

New rows need the same columns as existing rows: `hospital_specialty_id`, `hospital_id`, `specialty_code`, `specialty_name`, `admissions_prev_fy`, `admissions_before_last_year`.

```python
import uuid

# Get existing admissions stats to generate realistic values
existing_stats = specialty_offered[["admissions_prev_fy", "admissions_before_last_year"]]
prev_fy_mean = existing_stats["admissions_prev_fy"].mean()
prev_fy_std = existing_stats["admissions_prev_fy"].std()
before_last_mean = existing_stats["admissions_before_last_year"].mean()
before_last_std = existing_stats["admissions_before_last_year"].std()

new_rows = []
for row_data in rows_to_add:
    new_rows.append({
        "hospital_specialty_id": str(uuid.uuid4()),
        "hospital_id": row_data["hospital_id"],
        "specialty_code": row_data["specialty_code"],
        "specialty_name": row_data["specialty_name"],
        "admissions_prev_fy": max(
            50,
            int(np.random.normal(prev_fy_mean, prev_fy_std))
        ),
        "admissions_before_last_year": max(
            40,
            int(np.random.normal(before_last_mean, before_last_std))
        ),
    })

new_rows_df = pd.DataFrame(new_rows)
print(f"Generated {len(new_rows_df)} new specialty offering rows")
```

### Step 2.3: Append and save

```python
# Combine with existing
specialty_offered_fixed = pd.concat(
    [specialty_offered, new_rows_df],
    ignore_index=True
)

# Verify no duplicate (hospital_id, specialty_code) pairs
assert not specialty_offered_fixed.duplicated(
    subset=["hospital_id", "specialty_code"]
).any(), "Duplicate hospital-specialty pairs found!"

specialty_offered_fixed.to_csv("ab_data/hm_specialty_offered.csv", index=False)
print(f"Saved hm_specialty_offered.csv: {len(specialty_offered_fixed):,} rows "
      f"(was {len(specialty_offered):,})")
```

---

## Validation

### Fix 1 Checks (Timestamps)

```
CHECK A: bm_beneficiary.created_at date range
    - Should span at least 2 years (~2022-02 to ~2025-12)
    - FAIL if span < 1 year or all same date

CHECK B: bm_household.created_at date range
    - Should span at least 2 years

CHECK C: bm_card.issued_at date range
    - Should span at least 2 years

CHECK D: Temporal ordering (CRITICAL — check ALL rows)
    For every beneficiary with a card:
        household.created_at <= beneficiary.created_at <= card.issued_at
    For every beneficiary with claims:
        card.issued_at < first case.admission_datetime
    FAIL if any row violates this ordering

CHECK E: Monthly distribution of beneficiary.created_at
    - Plot histogram by month
    - Should show gradual ramp-up (heavier early, steady later)
    - Should NOT be a single spike

CHECK F: Row counts unchanged
    - bm_beneficiary: 205,847
    - bm_household: 50,000
    - bm_card: 195,619
```

### Fix 2 Checks (Specialty Offerings)

```
CHECK G: Coverage percentage
    - Compute: for each case, check if (hospital_id, specialty_code) exists
      in the updated hm_specialty_offered
    - Target: >= 95% of cases should have a matching specialty
    - FAIL if < 90%

CHECK H: Anomaly percentage
    - The remaining uncovered cases should be ~5%
    - Verify they exist (we don't want 100% coverage — the 5% anomalies
      are analytically interesting)

CHECK I: No duplicate (hospital_id, specialty_code) pairs
    - The append must not create duplicates

CHECK J: Row count increase is plausible
    - Original: 2,840 rows
    - Expected increase: varies, but likely 500-2,000 new rows
    - FAIL if increase > 5,000 (something went wrong)

CHECK K: New rows have valid specialty codes
    - All specialty_code values in new rows should exist in
      ref_hbp_procedure_master.specialty_code

CHECK L: Hospital coverage distribution
    - Print how many hospitals needed new specialties added
    - Print distribution of specialties added per hospital (min/mean/max)
```

### Post-Fix Pipeline Checks

After re-running `phase1_pipeline.py`:

```
CHECK M: View 2 — claims_per_1000_beneficiaries
    - Should be populated for most rows (null rate < 10%, was 97.2%)

CHECK N: View 4 — days_enrolment_to_card
    - Should be positive (1-30 day range, was -0.44)

CHECK O: View 4 — days_card_to_first_claim
    - Should be positive (14+ days, was negative)

CHECK P: View 3 — case coverage
    - SUM(cases_treated) / View 1 row count should be >= 90% (was 38%)

CHECK Q: View 3 — zero_claim_flag still exists
    - Some rows should still have zero_claim_flag = 1
    - These are specialties a hospital offers but had no cases in the window
    - FAIL if zero_claim_flag is 0 for all rows (we want both 0s and 1s)

CHECK R: View 3 — row count increased
    - Should reflect the new specialty offerings (~3,000-5,000 rows)
```

---

## Execution Order

```
1. Back up original CSVs
2. Run Fix 1 (timestamps)
3. Validate Fix 1 (checks A-F)
4. Run Fix 2 (specialty offerings)
5. Validate Fix 2 (checks G-L)
6. Re-run phase1_pipeline.py
7. Validate rebuilt views (checks M-R)
8. Bring back new validation_report.txt and view_summaries.txt
```

---

## Notes

1. **Reproducibility:** `np.random.seed(42)` at the top ensures deterministic output.

2. **Fix 2 does NOT modify `cm_case` or any claims tables.** It only adds rows to `hm_specialty_offered`. The case-to-specialty mapping (via procedure lines) stays exactly as generated.

3. **The 5% anomaly cases are valuable.** They represent real-world scenarios: a patient with a cardiac emergency treated at a hospital that only lists General Medicine. MetaInsight should surface these as exceptions in View 3.

4. **Existing `hm_specialty_offered` rows are never removed.** A hospital might list a specialty but have zero cases — that's legitimate (newly empanelled specialty, low demand). We only add, never subtract.

5. **Order matters:** Run Fix 1 before Fix 2. Fix 2 reads `cm_case.csv` which is unchanged, so technically the order doesn't matter for correctness, but running timestamps first means the validation pipeline can check everything in sequence.
