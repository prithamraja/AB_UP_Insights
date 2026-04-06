# =============================================================================
# Data Fix: Synthetic Data Post-Processing
# =============================================================================
# Two issues in the synthetic CSVs need correction before the analytical
# views are reliable:
#
#   Fix 1 — Timestamps: beneficiary / household / card timestamps are all
#            collapsed to a single date (2026-02-27). This breaks View 2's
#            cumulative enrolment metric and View 4's journey durations.
#
#   Fix 2 — Hospital specialty offerings: hm_specialty_offered was generated
#            without reference to actual case activity, causing 62% of cases
#            to be treated at hospitals that don't list the relevant specialty.
#            This makes View 3's underutilisation analysis unreliable.
#
# Run from the project root:
#   python src/data_fix.py
#
# After this script completes, re-run phase1_pipeline.py to rebuild all views.
# =============================================================================

import os
import sys
import uuid
import shutil

import numpy as np
import pandas as pd

np.random.seed(42)  # reproducibility for all random generation in both fixes

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "ab_data")
ORIG_DIR = os.path.join(DATA_DIR, "originals")


# =============================================================================
# UTILITIES
# =============================================================================

def log(msg: str) -> None:
    print(msg)


def check(condition: bool, label: str) -> bool:
    status = "[PASS]" if condition else "[FAIL]"
    print(f"  {status} {label}")
    return condition


# =============================================================================
# STEP 0 — Back up originals
# =============================================================================

log("=" * 70)
log("STEP 0: Backing up original CSVs")
log("=" * 70)

os.makedirs(ORIG_DIR, exist_ok=True)
FILES_TO_BACKUP = [
    "bm_beneficiary.csv",
    "bm_household.csv",
    "bm_card.csv",
    "bm_enrolment_request.csv",
    "hm_specialty_offered.csv",
]
for fname in FILES_TO_BACKUP:
    src = os.path.join(DATA_DIR, fname)
    dst = os.path.join(ORIG_DIR, fname)
    if not os.path.exists(dst):          # never overwrite a prior backup
        shutil.copy2(src, dst)
        log(f"  Backed up {fname}")
    else:
        log(f"  {fname} already backed up — skipping")


# =============================================================================
# FIX 1 — Timestamps
# =============================================================================

log("\n" + "=" * 70)
log("FIX 1: Timestamps")
log("=" * 70)

# ── 1.0  Dataset time window ──────────────────────────────────────────────────
cases = pd.read_csv(
    os.path.join(DATA_DIR, "cm_case.csv"),
    parse_dates=["admission_datetime"],
)
# Strip timezone so arithmetic is straightforward
cases["admission_datetime"] = pd.to_datetime(
    cases["admission_datetime"], utc=True
).dt.tz_localize(None)

dataset_start = cases["admission_datetime"].min()   # ~2023-02-28
dataset_end   = cases["admission_datetime"].max()   # ~2026-01-28

# Enrolment window: 12 months before first recorded admission -> dataset end
enrol_window_start = dataset_start - pd.DateOffset(months=12)  # ~2022-02-28
enrol_window_end   = dataset_end

enrol_start_ts = enrol_window_start.timestamp()
enrol_end_ts   = enrol_window_end.timestamp()

log(f"\n  Dataset window : {dataset_start.date()} -> {dataset_end.date()}")
log(f"  Enrolment window: {enrol_window_start.date()} -> {enrol_window_end.date()}")


# ── 1.1  First admission date per beneficiary ─────────────────────────────────
first_admission = (
    cases
    .groupby("beneficiary_id")["admission_datetime"]
    .min()
    .reset_index()
    .rename(columns={"admission_datetime": "first_admission_date"})
)


# ── 1.2  Beneficiary created_at ───────────────────────────────────────────────
log("\n  Generating bm_beneficiary.created_at …")

beneficiaries = pd.read_csv(os.path.join(DATA_DIR, "bm_beneficiary.csv"))
beneficiaries = beneficiaries.merge(first_admission, on="beneficiary_id", how="left")
beneficiaries["first_admission_date"] = pd.to_datetime(
    beneficiaries["first_admission_date"]
)

has_claims = beneficiaries["first_admission_date"].notna()

# Beneficiaries WITH claims: enrol at least 14 days before first admission
upper_bounds = beneficiaries.loc[has_claims, "first_admission_date"] - pd.Timedelta(days=14)
upper_ts     = (upper_bounds.values.astype("int64") / 1e9).clip(
    min=enrol_start_ts + 86_400  # at least one day after window start
)
fracs    = np.random.uniform(0, 1, size=has_claims.sum())
ts_with  = enrol_start_ts + fracs * (upper_ts - enrol_start_ts)
beneficiaries.loc[has_claims, "created_at"] = pd.to_datetime(ts_with, unit="s")

# Beneficiaries WITHOUT claims: beta(2,3) — heavier earlier, tapering off
n_without   = (~has_claims).sum()
fracs       = np.random.beta(2, 3, size=n_without)
ts_without  = enrol_start_ts + fracs * (enrol_end_ts - enrol_start_ts)
beneficiaries.loc[~has_claims, "created_at"] = pd.to_datetime(ts_without, unit="s")

log(f"    created_at span: "
    f"{beneficiaries['created_at'].min().date()} -> "
    f"{beneficiaries['created_at'].max().date()}")


# ── 1.3  Beneficiary updated_at ───────────────────────────────────────────────
random_offset = pd.to_timedelta(
    np.random.uniform(0, 90, size=len(beneficiaries)), unit="D"
)
beneficiaries["updated_at"] = beneficiaries["created_at"] + random_offset


# ── 1.4  Household created_at ─────────────────────────────────────────────────
log("\n  Generating bm_household.created_at …")

households = pd.read_csv(os.path.join(DATA_DIR, "bm_household.csv"))

earliest_member = (
    beneficiaries
    .groupby("household_id")["created_at"]
    .min()
    .reset_index()
    .rename(columns={"created_at": "earliest_member_created"})
)
households = households.merge(earliest_member, on="household_id", how="left")

hh_offset = pd.to_timedelta(
    np.random.uniform(0, 7, size=len(households)), unit="D"
)
households["created_at"] = (
    pd.to_datetime(households["earliest_member_created"]) - hh_offset
)
households = households.drop(columns=["earliest_member_created"])

log(f"    created_at span: "
    f"{households['created_at'].min().date()} -> "
    f"{households['created_at'].max().date()}")


# ── 1.5  Card issued_at ───────────────────────────────────────────────────────
log("\n  Generating bm_card.issued_at …")

cards = pd.read_csv(os.path.join(DATA_DIR, "bm_card.csv"))
cards = cards.merge(
    beneficiaries[["beneficiary_id", "created_at", "first_admission_date"]],
    on="beneficiary_id", how="left",
)
cards["created_at"]           = pd.to_datetime(cards["created_at"])
cards["first_admission_date"] = pd.to_datetime(cards["first_admission_date"])

# Card issued 1-30 days after enrolment
base_offset      = pd.to_timedelta(np.random.uniform(1, 30, size=len(cards)), unit="D")
cards["issued_at"] = cards["created_at"] + base_offset

# Ensure card is before first admission for beneficiaries with claims
has_admission = cards["first_admission_date"].notna()
too_late = has_admission & (cards["issued_at"] >= cards["first_admission_date"])

if too_late.any():
    safe_upper = cards.loc[too_late, "first_admission_date"] - pd.Timedelta(days=1)
    safe_lower = cards.loc[too_late, "created_at"]           + pd.Timedelta(days=1)
    # For rows where the window is valid, use the midpoint; otherwise fall back to safe_lower
    window_ok  = safe_lower < safe_upper
    midpoint   = safe_lower + (safe_upper - safe_lower) / 2
    cards.loc[too_late &  window_ok, "issued_at"] = midpoint[window_ok]
    cards.loc[too_late & ~window_ok, "issued_at"] = safe_lower[~window_ok]
    log(f"    Corrected {too_late.sum()} cards that were issued after first admission")

cards = cards.drop(columns=["created_at", "first_admission_date"])

log(f"    issued_at span: "
    f"{pd.to_datetime(cards['issued_at']).min().date()} -> "
    f"{pd.to_datetime(cards['issued_at']).max().date()}")


# ── 1.6  Enrolment request timestamps ────────────────────────────────────────
log("\n  Checking bm_enrolment_request.submitted_at …")

enrolment = pd.read_csv(os.path.join(DATA_DIR, "bm_enrolment_request.csv"))
submitted_dates = pd.to_datetime(enrolment["submitted_at"], utc=True)

if submitted_dates.nunique() < 10:
    log("    Broken (< 10 unique values) — fixing")

    enrolment = enrolment.merge(
        beneficiaries[["beneficiary_id", "created_at"]],
        on="beneficiary_id", how="left",
    )
    enrolment["created_at"] = pd.to_datetime(enrolment["created_at"])

    # submitted_at = beneficiary.created_at + 0-3 days
    sub_offset              = pd.to_timedelta(np.random.uniform(0, 3, size=len(enrolment)), unit="D")
    enrolment["submitted_at"] = enrolment["created_at"] + sub_offset

    # reviewed_at = submitted_at + 0.5-14 days
    rev_offset               = pd.to_timedelta(np.random.uniform(0.5, 14, size=len(enrolment)), unit="D")
    enrolment["reviewed_at"] = enrolment["submitted_at"] + rev_offset

    enrolment = enrolment.drop(columns=["created_at"])
    enrolment.to_csv(os.path.join(DATA_DIR, "bm_enrolment_request.csv"), index=False)
    log(f"    Saved bm_enrolment_request.csv ({len(enrolment):,} rows)")
else:
    log("    Looks fine — skipping")


# ── 1.7  Save fixed CSVs ─────────────────────────────────────────────────────
log("\n  Saving fixed CSVs …")

beneficiaries = beneficiaries.drop(columns=["first_admission_date"])
beneficiaries.to_csv(os.path.join(DATA_DIR, "bm_beneficiary.csv"), index=False)
log("    Saved bm_beneficiary.csv")

households.to_csv(os.path.join(DATA_DIR, "bm_household.csv"), index=False)
log("    Saved bm_household.csv")

cards.to_csv(os.path.join(DATA_DIR, "bm_card.csv"), index=False)
log("    Saved bm_card.csv")


# =============================================================================
# FIX 1 VALIDATION (Checks A-F)
# =============================================================================

log("\n--- Fix 1 Validation ---")
all_pass = True

# CHECK A: bm_beneficiary.created_at span
span_benef = (
    beneficiaries["created_at"].max() - beneficiaries["created_at"].min()
).days / 365
all_pass &= check(span_benef >= 2,
    f"CHECK A: bm_beneficiary.created_at span >= 2 years (actual: {span_benef:.1f} yrs)")

# CHECK B: bm_household.created_at span
span_hh = (
    households["created_at"].max() - households["created_at"].min()
).days / 365
all_pass &= check(span_hh >= 2,
    f"CHECK B: bm_household.created_at span >= 2 years (actual: {span_hh:.1f} yrs)")

# CHECK C: bm_card.issued_at span
issued_series = pd.to_datetime(cards["issued_at"])
span_card = (issued_series.max() - issued_series.min()).days / 365
all_pass &= check(span_card >= 2,
    f"CHECK C: bm_card.issued_at span >= 2 years (actual: {span_card:.1f} yrs)")

# CHECK D: Temporal ordering — household <= beneficiary <= card <= admission
log("  Checking CHECK D: temporal ordering …")

# household.created_at <= beneficiary.created_at
benef_hh = beneficiaries.merge(
    households[["household_id", "created_at"]].rename(columns={"created_at": "hh_created"}),
    on="household_id", how="left",
)
benef_hh["hh_created"]  = pd.to_datetime(benef_hh["hh_created"])
benef_hh["created_at"]  = pd.to_datetime(benef_hh["created_at"])
bad_order = (benef_hh["hh_created"] > benef_hh["created_at"]).sum()
all_pass &= check(bad_order == 0,
    f"CHECK D1: household.created_at <= beneficiary.created_at "
    f"(violations: {bad_order:,})")

# beneficiary.created_at <= card.issued_at
benef_card = cards.merge(
    beneficiaries[["beneficiary_id", "created_at"]].rename(columns={"created_at": "benef_created"}),
    on="beneficiary_id", how="left",
)
benef_card["benef_created"] = pd.to_datetime(benef_card["benef_created"])
benef_card["issued_at"]     = pd.to_datetime(benef_card["issued_at"])
bad_card_order = (benef_card["benef_created"] > benef_card["issued_at"]).sum()
all_pass &= check(bad_card_order == 0,
    f"CHECK D2: beneficiary.created_at <= card.issued_at "
    f"(violations: {bad_card_order:,})")

# card.issued_at < first admission (for beneficiaries with claims)
benef_card_adm = benef_card.merge(first_admission, on="beneficiary_id", how="left")
benef_card_adm["first_admission_date"] = pd.to_datetime(
    benef_card_adm["first_admission_date"]
)
has_adm_mask = benef_card_adm["first_admission_date"].notna()
bad_adm_order = (
    benef_card_adm.loc[has_adm_mask, "issued_at"]
    >= benef_card_adm.loc[has_adm_mask, "first_admission_date"]
).sum()
all_pass &= check(bad_adm_order == 0,
    f"CHECK D3: card.issued_at < first admission "
    f"(violations: {bad_adm_order:,})")

# CHECK E: Monthly distribution is not a single spike
monthly_counts = (
    beneficiaries["created_at"]
    .apply(lambda x: pd.Timestamp(x).to_period("M").strftime("%Y-%m"))
    .value_counts()
)
all_pass &= check(len(monthly_counts) >= 24,
    f"CHECK E: created_at spread across >= 24 months "
    f"(actual: {len(monthly_counts)} months)")

# CHECK F: Row counts unchanged
all_pass &= check(len(beneficiaries) == 205_847,
    f"CHECK F1: bm_beneficiary row count = 205,847 (actual: {len(beneficiaries):,})")
all_pass &= check(len(households) == 50_000,
    f"CHECK F2: bm_household row count = 50,000 (actual: {len(households):,})")
all_pass &= check(len(cards) == 195_619,
    f"CHECK F3: bm_card row count = 195,619 (actual: {len(cards):,})")

if not all_pass:
    print("\nFix 1 validation failed. Aborting before Fix 2.")
    sys.exit(1)

log("\nFix 1 validation passed.")


# =============================================================================
# FIX 2 — Hospital Specialty Offerings
# =============================================================================

log("\n" + "=" * 70)
log("FIX 2: Hospital Specialty Offerings")
log("=" * 70)

# ── 2.0  Build hospital x specialty case matrix ───────────────────────────────
log("\n  Building hospital x specialty case matrix …")

preauth    = pd.read_csv(os.path.join(DATA_DIR, "cm_preauth_request.csv"))
proc_lines = pd.read_csv(os.path.join(DATA_DIR, "cm_preauth_procedure_line.csv"))
ref_proc   = pd.read_csv(os.path.join(DATA_DIR, "ref_hbp_procedure_master.csv"))

# Primary procedure per case
primary_proc = (
    proc_lines[proc_lines["procedure_rank"] == 1][["preauth_id", "hbp_procedure_code"]]
    .merge(preauth[["preauth_id", "case_id"]], on="preauth_id")
    .merge(
        ref_proc[["hbp_procedure_code", "specialty_code", "specialty_name"]],
        on="hbp_procedure_code",
    )
)

case_specialty = primary_proc.merge(
    cases[["case_id", "hospital_id"]], on="case_id"
)

# Cases per (hospital_id, specialty_code)
hosp_spec_counts = (
    case_specialty
    .groupby(["hospital_id", "specialty_code", "specialty_name"])
    .size()
    .reset_index(name="case_count")
    .sort_values(["hospital_id", "case_count"], ascending=[True, False])
)

log(f"    {len(case_specialty):,} cases across "
    f"{case_specialty['hospital_id'].nunique()} hospitals, "
    f"{case_specialty['specialty_code'].nunique()} specialties")


# ── 2.1  Determine which specialties to add (to cover 95% of cases) ───────────
log("\n  Determining which specialties to add per hospital …")

specialty_offered = pd.read_csv(os.path.join(DATA_DIR, "hm_specialty_offered.csv"))
currently_offered = set(
    zip(specialty_offered["hospital_id"], specialty_offered["specialty_code"])
)

rows_to_add = []
for hospital_id, group in hosp_spec_counts.groupby("hospital_id"):
    total_cases = group["case_count"].sum()
    target      = total_cases * 0.95   # cover 95% of this hospital's cases

    cumulative = 0
    for _, row in group.iterrows():
        pair = (row["hospital_id"], row["specialty_code"])
        if pair not in currently_offered:
            rows_to_add.append({
                "hospital_id":           row["hospital_id"],
                "specialty_code":        row["specialty_code"],
                "specialty_name":        row["specialty_name"],
                "case_count_ref":        row["case_count"],
            })
        cumulative += row["case_count"]
        if cumulative >= target:
            break   # 95% threshold reached; remaining stay as anomalies

log(f"    Specialties to add: {len(rows_to_add)}")


# ── 2.2  Generate new hm_specialty_offered rows ───────────────────────────────
log("\n  Generating new hm_specialty_offered rows …")

prev_fy_mean   = specialty_offered["admissions_prev_fy"].mean()
prev_fy_std    = specialty_offered["admissions_prev_fy"].std()
before_last_mean = specialty_offered["admissions_before_last_year"].mean()
before_last_std  = specialty_offered["admissions_before_last_year"].std()

new_rows = []
for rd in rows_to_add:
    new_rows.append({
        "hospital_specialty_id":        str(uuid.uuid4()),
        "hospital_id":                  rd["hospital_id"],
        "specialty_code":               rd["specialty_code"],
        "specialty_name":               rd["specialty_name"],
        "admissions_prev_fy":           max(50, int(np.random.normal(prev_fy_mean, prev_fy_std))),
        "admissions_before_last_year":  max(40, int(np.random.normal(before_last_mean, before_last_std))),
    })

new_rows_df = pd.DataFrame(new_rows)
log(f"    Generated {len(new_rows_df):,} new rows")


# ── 2.3  Append and save ──────────────────────────────────────────────────────
specialty_offered_fixed = pd.concat(
    [specialty_offered, new_rows_df], ignore_index=True
)

assert not specialty_offered_fixed.duplicated(
    subset=["hospital_id", "specialty_code"]
).any(), "Duplicate hospital-specialty pairs found — aborting!"

specialty_offered_fixed.to_csv(
    os.path.join(DATA_DIR, "hm_specialty_offered.csv"), index=False
)
log(f"    Saved hm_specialty_offered.csv: "
    f"{len(specialty_offered_fixed):,} rows (was {len(specialty_offered):,})")


# =============================================================================
# FIX 2 VALIDATION (Checks G-L)
# =============================================================================

log("\n--- Fix 2 Validation ---")
all_pass2 = True

# Reload the fixed file to validate from disk
specialty_offered_fixed = pd.read_csv(
    os.path.join(DATA_DIR, "hm_specialty_offered.csv")
)
offered_set_fixed = set(
    zip(specialty_offered_fixed["hospital_id"], specialty_offered_fixed["specialty_code"])
)

case_specialty["matched"] = case_specialty.apply(
    lambda r: (r["hospital_id"], r["specialty_code"]) in offered_set_fixed, axis=1
)
coverage_pct = case_specialty["matched"].mean() * 100
anomaly_pct  = 100 - coverage_pct

# CHECK G: >= 95% coverage
all_pass2 &= check(coverage_pct >= 90,
    f"CHECK G: Case coverage >= 90% (target 95%) — actual: {coverage_pct:.1f}%")

# CHECK H: Anomaly cases still exist (we want ~5%, not 0%)
all_pass2 &= check(anomaly_pct > 0,
    f"CHECK H: Anomaly cases exist (beyond-registration) — actual: {anomaly_pct:.1f}%")

# CHECK I: No duplicate (hospital_id, specialty_code) pairs
dups = specialty_offered_fixed.duplicated(subset=["hospital_id", "specialty_code"]).sum()
all_pass2 &= check(dups == 0,
    f"CHECK I: No duplicate (hospital_id, specialty_code) pairs (duplicates: {dups})")

# CHECK J: Row count increase is plausible
orig_count  = len(specialty_offered)
fixed_count = len(specialty_offered_fixed)
increase    = fixed_count - orig_count
all_pass2 &= check(0 < increase <= 5_000,
    f"CHECK J: Row increase 0 < {increase:,} <= 5,000 "
    f"(was {orig_count:,}, now {fixed_count:,})")

# CHECK K: All new specialty codes exist in ref_hbp
valid_specialty_codes = set(ref_proc["specialty_code"])
new_codes = set(new_rows_df["specialty_code"]) if len(new_rows_df) > 0 else set()
invalid_new_codes = new_codes - valid_specialty_codes
all_pass2 &= check(len(invalid_new_codes) == 0,
    f"CHECK K: All new specialty_codes are valid "
    f"(invalid: {invalid_new_codes if invalid_new_codes else 'none'})")

# CHECK L: Coverage distribution summary
hospitals_needing_adds = len({rd["hospital_id"] for rd in rows_to_add})
log(f"  CHECK L (info): {hospitals_needing_adds} hospitals received new specialty rows")
adds_per_hosp = pd.Series([rd["hospital_id"] for rd in rows_to_add]).value_counts()
if len(adds_per_hosp) > 0:
    log(f"    Specialties added per hospital — "
        f"min: {adds_per_hosp.min()}, "
        f"mean: {adds_per_hosp.mean():.1f}, "
        f"max: {adds_per_hosp.max()}")
all_pass2 &= check(True, "CHECK L: Coverage distribution logged above")

if not all_pass2:
    print("\nFix 2 validation failed.")
    sys.exit(1)

log("\nFix 2 validation passed.")

# =============================================================================
# DONE
# =============================================================================

log("\n" + "=" * 70)
log("Both fixes applied successfully.")
log("Next step: re-run  python src/phase1_pipeline.py")
log("=" * 70)
