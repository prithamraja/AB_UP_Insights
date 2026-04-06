# =============================================================================
# Phase 1: Data Ingestion & Analytical View Materialization
# AB/UP Ayushman Bharat PM-JAY Synthetic Dataset — Uttar Pradesh
# =============================================================================
# This script is Phase 1 of the MetaInsight pipeline. It:
#   1. Loads all 21 source CSVs from ab_data/
#   2. Applies type casting (timestamps, booleans, floats)
#   3. Runs validation checks (row counts, PKs, FKs, nulls, distributions, dates)
#   4. Derives computed columns needed for analytical views
#   5. Materialises four denormalized analytical views as Parquet files
#   6. Writes a validation report and view summaries to reports/
#
# Run from the project root:
#   python src/phase1_pipeline.py
#
# Google Colab usage:
#   1. Mount Google Drive
#   2. Update the four path constants in the CONFIGURATION section below
#   3. Run all cells / execute the script
# =============================================================================

import os
import sys
import warnings
from datetime import datetime

import pandas as pd
import pyarrow  # noqa: F401 — required by pandas .to_parquet()

warnings.filterwarnings("ignore")


# =============================================================================
# CONFIGURATION — edit these paths when running on Colab
# =============================================================================
# When running locally the script lives in src/ so two dirname() calls reach
# the project root. On Colab, replace BASE_DIR with your Drive mount path,
# e.g. "/content/drive/MyDrive/AB_UP_insights".

BASE_DIR    = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR    = os.path.join(BASE_DIR, "ab_data")    # 21 source CSV files
VIEWS_DIR   = os.path.join(BASE_DIR, "views")      # output Parquet files
REPORTS_DIR = os.path.join(BASE_DIR, "reports")    # validation_report.txt, view_summaries.txt

# Expected row counts (from the dataset README) used in CHECK 1.
# A +/-20 % tolerance is applied; the synthetic data may differ slightly.
EXPECTED_ROW_COUNTS = {
    "ref_up_geography":          1_000,
    "ref_hbp_procedure_master":     25,
    "bm_household":             50_000,
    "bm_beneficiary":          200_000,
    "bm_id_document":          300_000,
    "bm_enrolment_request":    200_000,
    "bm_card":                 190_000,
    "hm_hospital":                 800,
    "hm_hospital_bank_account":    800,
    "hm_license_certificate":    4_000,
    "hm_specialty_offered":      4_000,
    "hm_staff":                  5_000,
    "cm_case":                  22_500,
    "cm_case_diagnosis":        35_000,
    "cm_preauth_request":       22_500,
    "cm_preauth_procedure_line": 28_000,
    "cm_discharge":             22_500,
    "cm_claim":                 22_500,
    "cm_claim_document":       110_000,
    "cm_adjudication_event":    70_000,
    "cm_payment":               19_000,
}


# =============================================================================
# UTILITY: Logging, validation report, and user-prompt-on-failure
# =============================================================================

_report_lines = []  # accumulates every log line; written to disk at the end


def log(msg: str, also_print: bool = True) -> None:
    """Append msg to the in-memory validation log and optionally print it."""
    _report_lines.append(msg)
    if also_print:
        print(msg)


def save_validation_report() -> None:
    """Flush the accumulated log to reports/validation_report.txt."""
    os.makedirs(REPORTS_DIR, exist_ok=True)
    path = os.path.join(REPORTS_DIR, "validation_report.txt")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(_report_lines))
    print(f"\nValidation report saved -> {path}")


def check_and_prompt(check_name: str, issues: list) -> None:
    """
    Log validation results for one check.
    If there are issues, print them and ask the user whether to continue.
    Exits the process if the user says no.
    """
    if not issues:
        log(f"[PASSED] {check_name}")
        return

    log(f"\n[FAILED] {check_name}")
    for issue in issues:
        log(f"  - {issue}")

    answer = input(
        f"\nValidation issues found in '{check_name}'. Continue anyway? (y/n): "
    ).strip().lower()

    if answer != "y":
        log("User chose to halt pipeline. Saving report and exiting.")
        save_validation_report()
        sys.exit(1)


# =============================================================================
# SECTION 1 — Load all 21 CSVs (Layer 0: raw ingestion)
# =============================================================================

print("=" * 70)
print("SECTION 1: Loading CSVs")
print("=" * 70)

CSV_NAMES = [
    "ref_up_geography", "ref_hbp_procedure_master",
    "bm_household", "bm_beneficiary", "bm_id_document",
    "bm_enrolment_request", "bm_card",
    "hm_hospital", "hm_hospital_bank_account",
    "hm_license_certificate", "hm_specialty_offered", "hm_staff",
    "cm_case", "cm_case_diagnosis", "cm_preauth_request",
    "cm_preauth_procedure_line", "cm_discharge", "cm_claim",
    "cm_claim_document", "cm_adjudication_event", "cm_payment",
]

tables: dict[str, pd.DataFrame] = {}

log("\n--- Row counts at load ---")
for name in CSV_NAMES:
    filepath = os.path.join(DATA_DIR, f"{name}.csv")
    tables[name] = pd.read_csv(filepath, low_memory=False)
    log(f"  {name}: {len(tables[name]):,} rows x {tables[name].shape[1]} cols")


# =============================================================================
# SECTION 2 — Type Casting
# =============================================================================
# All IDs stay as strings (object dtype).
# Timestamps are coerced to datetime64[ns]; date-only fields use .dt.date.
# Monetary amounts become float64.
# Boolean columns use pandas nullable boolean dtype to preserve NA.
# =============================================================================

print("\n" + "=" * 70)
print("SECTION 2: Type Casting")
print("=" * 70)


def _to_timestamps(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    # Parse to datetime and strip any timezone info so all timestamps are
    # tz-naive (UTC-equivalent). This avoids tz-aware vs tz-naive comparison
    # errors when columns from different tables are compared directly.
    for col in cols:
        if col in df.columns:
            parsed = pd.to_datetime(df[col], errors="coerce", utc=True)
            df[col] = parsed.dt.tz_localize(None)
    return df


def _to_dates(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    """Parse to date only (strips time component)."""
    for col in cols:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce")
    return df


def _to_float(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    for col in cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def _to_bool(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    for col in cols:
        if col in df.columns:
            df[col] = df[col].astype("boolean")
    return df


# ── Beneficiary management ──────────────────────────────────────────────────
tables["bm_beneficiary"] = _to_timestamps(
    tables["bm_beneficiary"], ["dob", "created_at", "updated_at"]
)
tables["bm_beneficiary"] = _to_bool(tables["bm_beneficiary"], ["is_duplicate"])

tables["bm_household"] = _to_timestamps(tables["bm_household"], ["created_at"])

tables["bm_enrolment_request"] = _to_timestamps(
    tables["bm_enrolment_request"], ["submitted_at", "reviewed_at"]
)

tables["bm_card"] = _to_timestamps(tables["bm_card"], ["issued_at"])

tables["bm_id_document"] = _to_timestamps(tables["bm_id_document"], ["created_at"])

# ── Hospital management ──────────────────────────────────────────────────────
tables["hm_hospital"] = _to_bool(
    tables["hm_hospital"],
    [
        "delisted_from_gov_schemes",
        "has_fully_equipped_ot", "has_icu_with_ac", "has_casualty",
        "has_opd", "has_hdu", "has_general_ward", "has_labour_room",
    ],
)
tables["hm_hospital"] = _to_timestamps(tables["hm_hospital"], ["created_at", "updated_at"])

tables["hm_hospital_bank_account"] = _to_bool(
    tables["hm_hospital_bank_account"], ["tds_exemption"]
)

# expiry_date / issue_date kept as datetime for comparison arithmetic
tables["hm_license_certificate"] = _to_dates(
    tables["hm_license_certificate"], ["issue_date", "expiry_date"]
)

# ── Claims management ────────────────────────────────────────────────────────
tables["cm_case"] = _to_timestamps(
    tables["cm_case"], ["admission_datetime", "discharge_datetime", "created_at"]
)
tables["cm_case"] = _to_bool(tables["cm_case"], ["is_portability"])

tables["cm_preauth_request"] = _to_timestamps(
    tables["cm_preauth_request"],
    ["initiated_at", "ppd_decision_at", "last_query_at",
     "last_query_response_at", "cancelled_at"],
)

tables["cm_preauth_procedure_line"] = _to_float(
    tables["cm_preauth_procedure_line"],
    [
        "stratification_amount", "implant_amount", "incentive_amount",
        "base_amount", "computed_final_amount", "expected_payable_amount",
        "payout_factor",
    ],
)
tables["cm_preauth_procedure_line"] = _to_bool(
    tables["cm_preauth_procedure_line"], ["is_addon"]
)

tables["cm_claim"] = _to_timestamps(tables["cm_claim"], ["submitted_at", "settled_at"])
tables["cm_claim"] = _to_dates(tables["cm_claim"], ["hospital_bill_date"])
tables["cm_claim"] = _to_float(tables["cm_claim"], ["amount_claimed", "amount_approved"])
tables["cm_claim"] = _to_bool(tables["cm_claim"], ["is_portability_claim"])

tables["cm_claim_document"] = _to_timestamps(tables["cm_claim_document"], ["uploaded_at"])

tables["cm_adjudication_event"] = _to_timestamps(tables["cm_adjudication_event"], ["event_time"])

tables["cm_payment"] = _to_timestamps(tables["cm_payment"], ["payment_date"])
tables["cm_payment"] = _to_float(tables["cm_payment"], ["amount_paid"])

tables["cm_discharge"] = _to_timestamps(
    tables["cm_discharge"],
    ["surgery_date", "discharge_date", "lama_date", "death_date"],
)
tables["cm_discharge"] = _to_bool(
    tables["cm_discharge"], ["provided_medicines_flag", "biometric_auth_used"]
)

# ── Reference tables ─────────────────────────────────────────────────────────
tables["ref_hbp_procedure_master"] = _to_float(
    tables["ref_hbp_procedure_master"], ["base_package_price"]
)
tables["ref_hbp_procedure_master"] = _to_bool(
    tables["ref_hbp_procedure_master"],
    ["has_stratification", "has_implant_or_high_end", "reserved_public_hospitals_only"],
)

print("Type casting complete.")


# =============================================================================
# SECTION 3 — Validation Checks (Layer 0)
# =============================================================================
# NOTE: We log issues and prompt the user — we never drop or fix data.
# The synthetic dataset intentionally contains quality issues
# (e.g. 3 % duplicate beneficiaries, 7 % expired licenses) that are
# analytically meaningful and must be preserved.
# =============================================================================

print("\n" + "=" * 70)
print("SECTION 3: Validation")
print("=" * 70)

log("\n" + "=" * 70)
log("VALIDATION REPORT")
log(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
log("=" * 70)


# ── CHECK 1: Row counts ──────────────────────────────────────────────────────
log("\n--- CHECK 1: Row Counts ---")
row_count_issues = []
for name, expected in EXPECTED_ROW_COUNTS.items():
    actual = len(tables[name])
    pct_diff = abs(actual - expected) / expected * 100
    status = "OK" if pct_diff < 20 else "UNEXPECTED"
    log(f"  {name}: actual={actual:,}  expected~{expected:,}  ({pct_diff:.1f}% diff)  [{status}]")
    if pct_diff >= 20:
        row_count_issues.append(
            f"{name}: {actual:,} rows vs expected ~{expected:,} ({pct_diff:.1f}% diff)"
        )
check_and_prompt("CHECK 1: Row Counts", row_count_issues)


# ── CHECK 2: Primary key uniqueness ─────────────────────────────────────────
log("\n--- CHECK 2: Primary Key Uniqueness ---")
PK_MAP = {
    "bm_household":             "household_id",
    "bm_beneficiary":           "beneficiary_id",
    "bm_id_document":           "id_doc_id",
    "bm_enrolment_request":     "enrolment_request_id",
    "bm_card":                  "card_id",
    "hm_hospital":              "hospital_id",
    "hm_hospital_bank_account": "hospital_bank_id",
    "hm_license_certificate":   "hospital_license_id",
    "hm_specialty_offered":     "hospital_specialty_id",
    "hm_staff":                 "staff_id",
    "cm_case":                  "case_id",
    "cm_case_diagnosis":        "case_diagnosis_id",
    "cm_preauth_request":       "preauth_id",
    "cm_preauth_procedure_line": "preauth_proc_id",
    "cm_discharge":             "discharge_id",
    "cm_claim":                 "claim_id",
    "cm_claim_document":        "claim_doc_id",
    "cm_adjudication_event":    "event_id",
    "cm_payment":               "payment_id",
    "ref_hbp_procedure_master": "hbp_procedure_code",
}
pk_issues = []
for table_name, pk_col in PK_MAP.items():
    dups = tables[table_name][pk_col].duplicated().sum()
    if dups > 0:
        log(f"  [FAIL] {table_name}.{pk_col}: {dups:,} duplicates")
        pk_issues.append(f"{table_name}.{pk_col} has {dups:,} duplicates")
    else:
        log(f"  [OK]   {table_name}.{pk_col}: unique")
check_and_prompt("CHECK 2: Primary Key Uniqueness", pk_issues)


# ── CHECK 3: Foreign key integrity ───────────────────────────────────────────
log("\n--- CHECK 3: Foreign Key Integrity ---")
FK_RELATIONSHIPS = [
    ("bm_beneficiary",           "household_id",       "bm_household",             "household_id"),
    ("bm_id_document",           "beneficiary_id",     "bm_beneficiary",            "beneficiary_id"),
    ("bm_enrolment_request",     "beneficiary_id",     "bm_beneficiary",            "beneficiary_id"),
    ("bm_card",                  "beneficiary_id",     "bm_beneficiary",            "beneficiary_id"),
    ("hm_hospital_bank_account", "hospital_id",        "hm_hospital",               "hospital_id"),
    ("hm_license_certificate",   "hospital_id",        "hm_hospital",               "hospital_id"),
    ("hm_specialty_offered",     "hospital_id",        "hm_hospital",               "hospital_id"),
    ("hm_staff",                 "hospital_id",        "hm_hospital",               "hospital_id"),
    ("cm_case",                  "beneficiary_id",     "bm_beneficiary",            "beneficiary_id"),
    ("cm_case",                  "hospital_id",        "hm_hospital",               "hospital_id"),
    ("cm_case_diagnosis",        "case_id",            "cm_case",                   "case_id"),
    ("cm_preauth_request",       "case_id",            "cm_case",                   "case_id"),
    ("cm_preauth_procedure_line","preauth_id",         "cm_preauth_request",        "preauth_id"),
    ("cm_preauth_procedure_line","hbp_procedure_code", "ref_hbp_procedure_master",  "hbp_procedure_code"),
    ("cm_preauth_procedure_line","clinician_staff_id", "hm_staff",                  "staff_id"),
    ("cm_claim",                 "case_id",            "cm_case",                   "case_id"),
    ("cm_claim",                 "preauth_id",         "cm_preauth_request",        "preauth_id"),
    ("cm_claim_document",        "claim_id",           "cm_claim",                  "claim_id"),
    ("cm_adjudication_event",    "claim_id",           "cm_claim",                  "claim_id"),
    ("cm_payment",               "claim_id",           "cm_claim",                  "claim_id"),
    ("cm_payment",               "hospital_bank_id",   "hm_hospital_bank_account",  "hospital_bank_id"),
]
fk_issues = []
for child_t, child_col, parent_t, parent_col in FK_RELATIONSHIPS:
    valid_keys = set(tables[parent_t][parent_col].dropna())
    child_vals = tables[child_t][child_col].dropna()
    orphans = (~child_vals.isin(valid_keys)).sum()
    pct = orphans / len(child_vals) * 100 if len(child_vals) > 0 else 0
    log(f"  {child_t}.{child_col} -> {parent_t}.{parent_col}: "
        f"{orphans:,}/{len(child_vals):,} orphans ({pct:.1f}%)")
    if orphans > 0:
        fk_issues.append(
            f"{child_t}.{child_col} -> {parent_t}.{parent_col}: "
            f"{orphans:,} orphans ({pct:.1f}%)"
        )
check_and_prompt("CHECK 3: Foreign Key Integrity", fk_issues)


# ── CHECK 4: Null rates ──────────────────────────────────────────────────────
# Log columns with >20 % nulls. Not treated as a hard failure; just surfaced
# for awareness since the spec allows intentional missingness.
log("\n--- CHECK 4: Null Rates (columns with >20% nulls) ---")
for name, df in tables.items():
    for col in df.columns:
        null_pct = df[col].isna().mean() * 100
        if null_pct > 20:
            log(f"  {name}.{col}: {null_pct:.1f}% null")


# ── CHECK 5: Categorical value distributions ─────────────────────────────────
log("\n--- CHECK 5: Categorical Value Distributions ---")
CAT_CHECKS = {
    "bm_beneficiary": {"gender":        {"M", "F"}},
    "cm_case": {
        "admission_type":  {"EMERGENCY", "ELECTIVE"},
        "discharge_type":  {"NORMAL", "LIVE", "LAMA", "DAMA", "DEATH"},
    },
    "cm_claim":   {"claim_status": {"APPROVED", "SETTLED", "QUERY_RAISED", "REJECTED", "PENDING"}},
    "hm_hospital": {"hospital_type": {"PUBLIC", "PRIVATE"}},
}
cat_issues = []
for tname, col_map in CAT_CHECKS.items():
    for col, expected_vals in col_map.items():
        actual_vals = set(tables[tname][col].dropna().unique())
        unexpected = actual_vals - expected_vals
        log(f"  {tname}.{col}: {sorted(actual_vals)}")
        if unexpected:
            cat_issues.append(f"{tname}.{col}: unexpected values {unexpected}")
check_and_prompt("CHECK 5: Categorical Value Distributions", cat_issues)


# ── CHECK 6: Date ranges ─────────────────────────────────────────────────────
# We expect the dataset to span approximately 3 years.
log("\n--- CHECK 6: Date Ranges ---")
DATE_COLS = {
    "cm_case":       ["admission_datetime", "discharge_datetime"],
    "cm_claim":      ["submitted_at", "settled_at"],
    "bm_beneficiary": ["created_at"],
    "cm_payment":    ["payment_date"],
}
date_issues = []
for tname, cols in DATE_COLS.items():
    for col in cols:
        series = tables[tname][col].dropna()
        if len(series) == 0:
            continue
        min_d, max_d = series.min(), series.max()
        span_years = (max_d - min_d).days / 365
        log(f"  {tname}.{col}: {min_d.date()} -> {max_d.date()} ({span_years:.1f} yrs)")
        if not (1 <= span_years <= 10):
            date_issues.append(
                f"{tname}.{col}: span={span_years:.1f} yrs (expected ~3)"
            )
check_and_prompt("CHECK 6: Date Ranges", date_issues)


# =============================================================================
# SECTION 4 — Derived Columns
# =============================================================================
# These columns are computed once here and reused across multiple views.
# =============================================================================

print("\n" + "=" * 70)
print("SECTION 4: Derived Columns")
print("=" * 70)

# Reference year: the latest year seen in admitted cases
_ref_year: int = int(tables["cm_case"]["admission_datetime"].dt.year.max())


# ── 4.1  Age group on bm_beneficiary ────────────────────────────────────────
def _age_group(yob) -> str:
    if pd.isna(yob):
        return "UNKNOWN"
    age = _ref_year - int(yob)
    if age < 1:   return "INFANT"
    if age <= 5:  return "1-5"
    if age <= 14: return "6-14"
    if age <= 25: return "15-25"
    if age <= 40: return "26-40"
    if age <= 60: return "41-60"
    return "60+"

tables["bm_beneficiary"]["age_group"] = (
    tables["bm_beneficiary"]["yob"].apply(_age_group)
)


# ── 4.2  Temporal dimensions and binary flags on cm_case ─────────────────────
tables["cm_case"]["admission_month"] = (
    tables["cm_case"]["admission_datetime"].dt.to_period("M").astype(str)
)
tables["cm_case"]["admission_quarter"] = (
    tables["cm_case"]["admission_datetime"].dt.to_period("Q").astype(str)
)
tables["cm_case"]["admission_year"] = (
    tables["cm_case"]["admission_datetime"].dt.year.astype("Int64").astype(str)
)
# Length of stay in fractional days
tables["cm_case"]["length_of_stay"] = (
    (tables["cm_case"]["discharge_datetime"] - tables["cm_case"]["admission_datetime"])
    .dt.total_seconds() / 86_400
)
tables["cm_case"]["is_emergency"] = (
    (tables["cm_case"]["admission_type"] == "EMERGENCY").astype(int)
)
tables["cm_case"]["is_death"] = (
    (tables["cm_case"]["discharge_type"] == "DEATH").astype(int)
)
tables["cm_case"]["is_lama_dama"] = (
    tables["cm_case"]["discharge_type"].isin(["LAMA", "DAMA"]).astype(int)
)


# ── 4.3  Disease category mapping on cm_case_diagnosis ───────────────────────
# Approximate ICD-10 first-letter bucketing per README disease-burden weights.
def _disease_category(icd_code) -> str:
    if pd.isna(icd_code):
        return "UNKNOWN"
    first = str(icd_code).upper().strip()[:1]
    if first in ("O", "P"):                        return "MATERNAL_NEONATAL"
    if first in ("A", "B"):                        return "COMMUNICABLE"
    if first in ("S", "T"):                        return "INJURY"
    if first in ("I", "E", "J", "N", "C", "D"):   return "NCD"
    if first in ("K", "H", "G", "M", "L"):        return "SURGICAL"
    return "OTHER"

tables["cm_case_diagnosis"]["disease_category"] = (
    tables["cm_case_diagnosis"]["icd_code"].apply(_disease_category)
)

# Log distribution to validate against README weights
# (NCD 30%, Communicable 28%, Maternal 18%, Surgical 16%, Injury 8%)
_cat_dist = (
    tables["cm_case_diagnosis"]["disease_category"]
    .value_counts(normalize=True) * 100
)
log("\n--- Disease Category Distribution (derived ICD mapping) ---")
for cat, pct in _cat_dist.items():
    log(f"  {cat}: {pct:.1f}%")


# ── 4.4  Bed size bucket on hm_hospital ──────────────────────────────────────
def _bed_size_bucket(beds) -> str:
    if pd.isna(beds):      return "UNKNOWN"
    if beds <= 30:         return "SMALL (<=30)"
    if beds <= 100:        return "MEDIUM (31-100)"
    if beds <= 300:        return "LARGE (101-300)"
    return "VERY_LARGE (300+)"

tables["hm_hospital"]["bed_size_bucket"] = (
    tables["hm_hospital"]["total_bed_strength"].apply(_bed_size_bucket)
)


# ── 4.5  Expired license flag on hm_license_certificate ──────────────────────
# Reference date: the latest admission datetime in the dataset
_ref_date = tables["cm_case"]["admission_datetime"].max()
tables["hm_license_certificate"]["is_expired"] = (
    tables["hm_license_certificate"]["expiry_date"] < _ref_date
).astype(int)

print("Derived columns complete.")


# =============================================================================
# SECTION 5 — View 1: Claims Lifecycle
# =============================================================================
# Grain: one row per case_id (~22,500 rows)
# Purpose: full transactional journey from admission to payment.
# =============================================================================

print("\n" + "=" * 70)
print("SECTION 5: Building View 1 — Claims Lifecycle")
print("=" * 70)

# Step A: filter to primary diagnosis only (diagnosis_rank == 1)
diag_primary = (
    tables["cm_case_diagnosis"][tables["cm_case_diagnosis"]["diagnosis_rank"] == 1]
    [["case_id", "icd_code", "disease_category"]]
)

# Step B: filter to primary procedure line (procedure_rank == 1)
ppl_primary = (
    tables["cm_preauth_procedure_line"][
        tables["cm_preauth_procedure_line"]["procedure_rank"] == 1
    ][["preauth_id", "hbp_procedure_code",
       "base_amount", "computed_final_amount", "expected_payable_amount"]]
)

# Step C: if a case has multiple claims, keep the first submitted one
claim_first = (
    tables["cm_claim"]
    .sort_values("submitted_at")
    .groupby("case_id", as_index=False)
    .first()
)

# Step D: aggregate payments per claim_id
#   - sum amount_paid (there can be partial payments)
#   - take the modal payment_status
payment_agg = (
    tables["cm_payment"]
    .groupby("claim_id", as_index=False)
    .agg(
        amount_paid=("amount_paid", "sum"),
        payment_status=(
            "payment_status",
            lambda x: x.mode().iloc[0] if len(x) > 0 else pd.NA,
        ),
    )
)

# Step E: join chain anchored on cm_case
v1 = tables["cm_case"].copy()

v1 = v1.merge(
    tables["bm_beneficiary"][["beneficiary_id", "household_id", "gender", "age_group"]],
    on="beneficiary_id", how="left",
)
v1 = v1.merge(
    tables["bm_household"][["household_id", "home_division_name", "home_district_code"]],
    on="household_id", how="left",
)
v1 = v1.merge(
    tables["hm_hospital"][[
        "hospital_id", "hospital_type", "hospital_sub_type",
        "accreditation_level", "bed_size_bucket",
    ]],
    on="hospital_id", how="left",
)
v1 = v1.merge(diag_primary, on="case_id", how="left")

# Deduplicate preauth: keep the latest preauth request per case.
# A case can have multiple preauths (initial + re-submissions after queries).
# Joining without dedup would multiply rows and break the one-row-per-case grain.
preauth_deduped = (
    tables["cm_preauth_request"]
    .sort_values("initiated_at")
    .groupby("case_id", as_index=False)
    .last()[["preauth_id", "case_id", "status"]]
    .rename(columns={"status": "preauth_status"})
)
v1 = v1.merge(preauth_deduped, on="case_id", how="left")
v1 = v1.merge(ppl_primary, on="preauth_id", how="left")
v1 = v1.merge(
    tables["ref_hbp_procedure_master"][[
        "hbp_procedure_code", "specialty_code", "specialty_name", "procedure_name"
    ]],
    on="hbp_procedure_code", how="left",
)
v1 = v1.merge(
    claim_first[[
        "case_id", "claim_id", "claim_status",
        "amount_claimed", "amount_approved",
        "settlement_tat_days", "query_count",
    ]],
    on="case_id", how="left",
)
v1 = v1.merge(
    payment_agg[["claim_id", "amount_paid", "payment_status"]],
    on="claim_id", how="left",
)

# Step F: select and rename final columns
view1 = v1[[
    "case_id",
    "home_division_name", "home_district_code",
    "hospital_division", "hospital_district",
    "hospital_type", "hospital_sub_type",
    "specialty_code", "specialty_name", "procedure_name",
    "disease_category", "icd_code",
    "gender", "age_group",
    "admission_type", "discharge_type",
    "is_portability",
    "claim_status", "preauth_status", "payment_status",
    "accreditation_level", "bed_size_bucket",
    "admission_month", "admission_quarter", "admission_year",
    "length_of_stay", "is_emergency", "is_death", "is_lama_dama",
    "base_amount", "computed_final_amount", "expected_payable_amount",
    "amount_claimed", "amount_approved", "amount_paid",
    "settlement_tat_days", "query_count",
]].rename(columns={
    "home_division_name":  "division",
    "home_district_code":  "district",
})
view1["case_count"] = 1  # convenience measure column for SUM aggregations

print(f"View 1 built: {len(view1):,} rows x {len(view1.columns)} cols")


# =============================================================================
# SECTION 6 — View 2: District-Month Performance Cube
# =============================================================================
# Grain: one row per (district x month) (~75 districts x ~36 months ~ 2,700 rows)
# Purpose: cross-domain aggregate metrics for geographic/temporal analysis.
# =============================================================================

print("\n" + "=" * 70)
print("SECTION 6: Building View 2 — District-Month Performance Cube")
print("=" * 70)

# Enriched beneficiary table: join household geography once and reuse
benef_geo = tables["bm_beneficiary"].merge(
    tables["bm_household"][["household_id", "home_district_code", "home_division_name"]],
    on="household_id", how="left",
)

# ── Enrolment: new beneficiaries and households per district x month ──────────
enrol_agg = (
    benef_geo
    .assign(month=lambda df: df["created_at"].dt.to_period("M").astype(str))
    .groupby(["home_division_name", "home_district_code", "month"], as_index=False)
    .agg(
        new_beneficiaries=("beneficiary_id", "count"),
        new_households=("household_id", "nunique"),
    )
)

# ── Cards issued per district x month ────────────────────────────────────────
card_agg = (
    tables["bm_card"]
    .merge(benef_geo[["beneficiary_id", "home_district_code"]], on="beneficiary_id", how="left")
    .assign(month=lambda df: df["issued_at"].dt.to_period("M").astype(str))
    .groupby(["home_district_code", "month"], as_index=False)
    .agg(cards_issued=("card_id", "count"))
)

# ── Cases admitted per district x month (using beneficiary home district) ─────
case_geo = (
    tables["cm_case"]
    .merge(benef_geo[["beneficiary_id", "home_district_code", "home_division_name"]],
           on="beneficiary_id", how="left")
    .merge(tables["hm_hospital"][["hospital_id", "hospital_type"]],
           on="hospital_id", how="left")
    .assign(month=lambda df: df["admission_datetime"].dt.to_period("M").astype(str))
)
case_agg = (
    case_geo
    .groupby(["home_division_name", "home_district_code", "month"], as_index=False)
    .agg(
        cases_admitted     =("case_id",        "count"),
        emergency_cases    =("is_emergency",   "sum"),
        portability_cases  =("is_portability", "sum"),
        deaths             =("is_death",       "sum"),
        lama_dama_cases    =("is_lama_dama",   "sum"),
        public_cases       =("hospital_type",  lambda x: (x == "PUBLIC").sum()),
        private_cases      =("hospital_type",  lambda x: (x == "PRIVATE").sum()),
        unique_hospitals   =("hospital_id",    "nunique"),
        avg_length_of_stay =("length_of_stay", "mean"),
    )
)

# ── Claims submitted per district x month ────────────────────────────────────
claims_geo = (
    tables["cm_claim"]
    .merge(tables["cm_case"][["case_id", "beneficiary_id"]], on="case_id", how="left")
    .merge(benef_geo[["beneficiary_id", "home_district_code"]], on="beneficiary_id", how="left")
    .assign(month=lambda df: df["submitted_at"].dt.to_period("M").astype(str))
)
claims_agg = (
    claims_geo
    .groupby(["home_district_code", "month"], as_index=False)
    .agg(
        claims_submitted  =("claim_id",            "count"),
        claims_approved   =("claim_status",        lambda x: x.isin(["APPROVED", "SETTLED"]).sum()),
        claims_rejected   =("claim_status",        lambda x: (x == "REJECTED").sum()),
        amount_claimed    =("amount_claimed",       "sum"),
        amount_approved   =("amount_approved",      "sum"),
        avg_settlement_tat=("settlement_tat_days", "mean"),
    )
)

# ── Payments per district x month ─────────────────────────────────────────────
payments_geo = (
    tables["cm_payment"]
    .merge(tables["cm_claim"][["claim_id", "case_id"]], on="claim_id", how="left")
    .merge(tables["cm_case"][["case_id", "beneficiary_id"]], on="case_id", how="left")
    .merge(benef_geo[["beneficiary_id", "home_district_code"]], on="beneficiary_id", how="left")
    .assign(month=lambda df: df["payment_date"].dt.to_period("M").astype(str))
)
payments_agg = (
    payments_geo
    .groupby(["home_district_code", "month"], as_index=False)
    .agg(
        amount_paid      =("amount_paid",      "sum"),
        payment_count    =("payment_id",       "count"),
        payment_failures =("payment_status",   lambda x: (x == "FAILED").sum()),
    )
)

# ── Merge all aggregates on (district x month) ────────────────────────────────
# Outer join so every district-month combination is present even if some
# activity sources have no data for it. Missing activity -> 0, not NaN.
v2 = (
    enrol_agg
    .merge(case_agg.drop(columns=["home_division_name"]),
           on=["home_district_code", "month"], how="outer")
    .merge(card_agg,     on=["home_district_code", "month"], how="outer")
    .merge(claims_agg,   on=["home_district_code", "month"], how="outer")
    .merge(payments_agg, on=["home_district_code", "month"], how="outer")
)

# For rows introduced by the outer join, fill division from enrol_agg
_div_map = enrol_agg.set_index("home_district_code")["home_division_name"].to_dict()
v2["home_division_name"] = v2["home_division_name"].fillna(
    v2["home_district_code"].map(_div_map)
)

# Fill count/sum columns with 0 where there was no activity
_numeric_fill_cols = [
    "new_beneficiaries", "new_households", "cards_issued",
    "cases_admitted", "emergency_cases", "portability_cases",
    "deaths", "lama_dama_cases", "public_cases", "private_cases",
    "unique_hospitals", "claims_submitted", "claims_approved",
    "claims_rejected", "amount_claimed", "amount_approved",
    "amount_paid", "payment_count", "payment_failures",
]
v2[_numeric_fill_cols] = v2[_numeric_fill_cols].fillna(0)

# Cumulative enrolled beneficiaries per district (running total by month).
# NOTE: This counts beneficiaries by their enrolment date (created_at),
# not by card issuance date. So claims_per_1000_beneficiaries measures
# "cases per 1000 enrolled beneficiaries" — including those who may not
# yet have received their Ayushman card. This gives the broader eligible-
# population view, which is more relevant for scheme coverage analysis.
# Alternative: use cumulative cards_issued for a stricter card-holder denominator.
v2 = v2.sort_values(["home_district_code", "month"])
v2["cumulative_beneficiaries"] = (
    v2.groupby("home_district_code")["new_beneficiaries"].cumsum()
)

# Temporal helpers
v2["quarter"] = (
    pd.to_datetime(v2["month"] + "-01").dt.to_period("Q").astype(str)
)
v2["year"] = v2["month"].str[:4]

# ── Cross-domain ratio metrics ────────────────────────────────────────────────
# Use .replace(0, pd.NA) to avoid division-by-zero; results will be NaN
# for district-months with zero denominator, which is correct.
v2["claims_per_1000_beneficiaries"] = (
    v2["cases_admitted"] / v2["cumulative_beneficiaries"].replace(0, pd.NA) * 1_000
)
v2["approval_rate"] = (
    v2["claims_approved"] / v2["claims_submitted"].replace(0, pd.NA)
)
v2["emergency_share"] = (
    v2["emergency_cases"] / v2["cases_admitted"].replace(0, pd.NA)
)
v2["death_rate"] = (
    v2["deaths"] / v2["cases_admitted"].replace(0, pd.NA)
)
v2["public_private_ratio"] = (
    v2["public_cases"] / (v2["private_cases"] + 1)  # +1 avoids zero denominator
)
v2["avg_claim_amount"] = (
    v2["amount_claimed"] / v2["claims_submitted"].replace(0, pd.NA)
)

view2 = v2.rename(columns={
    "home_district_code":  "district",
    "home_division_name":  "division",
})

print(f"View 2 built: {len(view2):,} rows x {len(view2.columns)} cols")


# =============================================================================
# SECTION 7 — View 3: Hospital Performance
# =============================================================================
# Grain: one row per (hospital x specialty offered) (~4,000 rows)
# Purpose: structural capacity vs. actual utilization; gap analysis.
# The LEFT JOIN on specialty ensures hospitals with zero claims still appear,
# which is the foundation of the underutilization signal.
# =============================================================================

print("\n" + "=" * 70)
print("SECTION 7: Building View 3 — Hospital Performance")
print("=" * 70)

# ── Claims aggregated at (hospital_id x specialty_code) grain ─────────────────
# Join path: case -> preauth -> primary procedure line -> ref table (gets specialty)
#                           -> claim -> payment
hosp_spec_raw = (
    tables["cm_case"]
    .merge(
        tables["cm_preauth_request"][["preauth_id", "case_id", "status"]],
        on="case_id", how="left",
    )
    .merge(
        tables["cm_preauth_procedure_line"][
            tables["cm_preauth_procedure_line"]["procedure_rank"] == 1
        ][["preauth_id", "hbp_procedure_code"]],
        on="preauth_id", how="left",
    )
    .merge(
        tables["ref_hbp_procedure_master"][["hbp_procedure_code", "specialty_code"]],
        on="hbp_procedure_code", how="left",
    )
    .merge(tables["cm_claim"], on="case_id", how="left")
    .merge(
        tables["cm_payment"][["claim_id", "amount_paid"]],
        on="claim_id", how="left",
    )
)

hosp_spec_agg = (
    hosp_spec_raw
    .groupby(["hospital_id", "specialty_code"], as_index=False)
    .agg(
        cases_treated     =("case_id",            "count"),
        preauth_approved  =("status",             lambda x: x.isin(["AUTO_APPROVED", "APPROVED"]).sum()),
        preauth_rejected  =("status",             lambda x: (x == "REJECTED").sum()),
        claims_approved   =("claim_status",       lambda x: x.isin(["APPROVED", "SETTLED"]).sum()),
        amount_claimed    =("amount_claimed",      "sum"),
        amount_approved   =("amount_approved",     "sum"),
        amount_paid       =("amount_paid",         "sum"),
        avg_settlement_tat=("settlement_tat_days", "mean"),
        emergency_count   =("is_emergency",        "sum"),
        death_count       =("is_death",            "sum"),
    )
)

# ── Staff counts per hospital ─────────────────────────────────────────────────
hosp_staff = (
    tables["hm_staff"]
    .groupby("hospital_id", as_index=False)
    .agg(
        total_staff          =("staff_id",         "count"),
        avg_experience_years =("experience_years", "mean"),
    )
)

# ── License compliance per hospital ──────────────────────────────────────────
hosp_license = (
    tables["hm_license_certificate"]
    .groupby("hospital_id", as_index=False)
    .agg(
        total_licenses   =("hospital_license_id", "count"),
        expired_licenses =("is_expired",          "sum"),
        active_licenses  =("is_expired",          lambda x: (x == 0).sum()),
    )
)

# ── Build the hospital x specialty matrix (anchor on hm_specialty_offered) ───
# Every offered specialty appears as a row; zero-claim rows surface as
# underutilization signals via zero_claim_flag.
v3 = (
    tables["hm_specialty_offered"]
    .merge(
        tables["hm_hospital"][[
            "hospital_id", "division_name", "district_name",
            "hospital_type", "hospital_sub_type", "accreditation_level",
            "bed_size_bucket", "total_bed_strength", "inpatient_beds",
            "has_fully_equipped_ot", "has_icu_with_ac",
        ]],
        on="hospital_id", how="left",
    )
    .merge(hosp_spec_agg, on=["hospital_id", "specialty_code"], how="left")
    .merge(hosp_staff,    on="hospital_id",                     how="left")
    .merge(hosp_license,  on="hospital_id",                     how="left")
)

v3["cases_treated"] = v3["cases_treated"].fillna(0)
v3["zero_claim_flag"] = (v3["cases_treated"] == 0).astype(int)
v3["cases_per_bed"]   = v3["cases_treated"] / v3["total_bed_strength"].replace(0, pd.NA)

view3 = v3.rename(columns={
    "division_name":       "division",
    "district_name":       "district",
    "has_fully_equipped_ot": "has_ot",
    "has_icu_with_ac":     "has_icu",
})

print(f"View 3 built: {len(view3):,} rows x {len(view3.columns)} cols")


# =============================================================================
# SECTION 8 — View 4: Beneficiary Journey
# =============================================================================
# Grain: one row per beneficiary_id (~200,000 rows)
# Purpose: enrolment quality, scheme access equity, demographic utilization.
# =============================================================================

print("\n" + "=" * 70)
print("SECTION 8: Building View 4 — Beneficiary Journey")
print("=" * 70)

# ── Latest enrolment request per beneficiary ──────────────────────────────────
enrol_latest = (
    tables["bm_enrolment_request"]
    .sort_values("submitted_at")
    .groupby("beneficiary_id", as_index=False)
    .last()[["beneficiary_id", "status", "auth_mode"]]
    .rename(columns={"status": "enrolment_status"})
)

# ── Latest card issued per beneficiary ────────────────────────────────────────
card_latest = (
    tables["bm_card"]
    .sort_values("issued_at")
    .groupby("beneficiary_id", as_index=False)
    .last()[["beneficiary_id", "card_status", "issued_at"]]
    .rename(columns={"issued_at": "card_issued_at"})
)

# ── Document count and Aadhaar presence per beneficiary ───────────────────────
doc_agg = (
    tables["bm_id_document"]
    .groupby("beneficiary_id", as_index=False)
    .agg(
        document_count=("id_doc_id",  "count"),
        has_aadhaar   =("doc_type",   lambda x: int((x == "AADHAAR").any())),
    )
)

# ── Claim history per beneficiary ─────────────────────────────────────────────
benef_claims = (
    tables["cm_case"]
    .merge(
        tables["cm_claim"][["case_id", "amount_claimed", "amount_approved"]],
        on="case_id", how="left",
    )
    .groupby("beneficiary_id", as_index=False)
    .agg(
        claim_count          =("case_id",           "count"),
        total_amount_claimed =("amount_claimed",    "sum"),
        total_amount_approved=("amount_approved",   "sum"),
        first_admission_date =("admission_datetime","min"),
    )
)

# ── Build View 4 via join chain anchored on bm_beneficiary ───────────────────
v4 = (
    tables["bm_beneficiary"][[
        "beneficiary_id", "household_id", "gender", "age_group",
        "bis_record_status", "is_duplicate", "created_at",
    ]]
    .merge(
        tables["bm_household"][[
            "household_id", "home_division_name", "home_district_code", "entitlement_source"
        ]],
        on="household_id", how="left",
    )
    .merge(enrol_latest, on="beneficiary_id", how="left")
    .merge(card_latest,  on="beneficiary_id", how="left")
    .merge(doc_agg,      on="beneficiary_id", how="left")
    .merge(benef_claims, on="beneficiary_id", how="left")
)

# ── Derived columns ───────────────────────────────────────────────────────────
v4["document_count"] = v4["document_count"].fillna(0).astype(int)
v4["has_aadhaar"]    = v4["has_aadhaar"].fillna(0).astype(int)
v4["claim_count"]    = v4["claim_count"].fillna(0).astype(int)
v4["has_claim"]      = (v4["claim_count"] > 0).astype(int)


def _doc_count_bucket(n: int) -> str:
    if n == 0: return "NO_DOCS"
    if n == 1: return "1_DOC"
    if n <= 3: return "2-3_DOCS"
    return "4+_DOCS"

v4["document_count_bucket"] = v4["document_count"].apply(_doc_count_bucket)

# Days from first enrolment (beneficiary created_at) to card issuance
v4["days_enrolment_to_card"] = (
    (v4["card_issued_at"] - v4["created_at"]).dt.total_seconds() / 86_400
)
# Days from card issuance to first hospital admission
v4["days_card_to_first_claim"] = (
    (v4["first_admission_date"] - v4["card_issued_at"]).dt.total_seconds() / 86_400
)

view4 = v4.rename(columns={
    "home_division_name": "division",
    "home_district_code": "district",
}).drop(columns=["household_id", "created_at", "card_issued_at", "first_admission_date"],
        errors="ignore")

print(f"View 4 built: {len(view4):,} rows x {len(view4.columns)} cols")


# =============================================================================
# SECTION 9 — Save Parquet Views
# =============================================================================

print("\n" + "=" * 70)
print("SECTION 9: Saving Parquet Views")
print("=" * 70)

os.makedirs(VIEWS_DIR, exist_ok=True)

_parquet_map = {
    "view1_claims_lifecycle.parquet":       view1,
    "view2_district_month_cube.parquet":    view2,
    "view3_hospital_performance.parquet":   view3,
    "view4_beneficiary_journey.parquet":    view4,
}
for filename, df in _parquet_map.items():
    path = os.path.join(VIEWS_DIR, filename)
    df.to_parquet(path, index=False)
    print(f"  Saved {filename}  ({len(df):,} rows)")

print(f"All views written to: {VIEWS_DIR}")


# =============================================================================
# SECTION 10 — View Summaries
# =============================================================================
# One combined file: reports/view_summaries.txt
# For each view: row/col count, dtypes, null counts, top values per dimension,
# descriptive stats per measure, and 5 random sample rows.
# =============================================================================

print("\n" + "=" * 70)
print("SECTION 10: View Summaries")
print("=" * 70)

_summary_lines: list[str] = []


def _summarize_view(name: str, df: pd.DataFrame) -> None:
    _summary_lines.append("\n" + "=" * 70)
    _summary_lines.append(f"SUMMARY: {name}")
    _summary_lines.append(f"Rows: {len(df):,}  |  Columns: {len(df.columns)}")
    _summary_lines.append("=" * 70)

    dim_cols     = df.select_dtypes(include=["object", "bool", "boolean"]).columns.tolist()
    measure_cols = df.select_dtypes(include=["number"]).columns.tolist()

    _summary_lines.append(f"\nAll columns: {list(df.columns)}")

    # Null counts (only non-zero)
    _summary_lines.append("\n--- Null counts (non-zero only) ---")
    null_found = False
    for col in df.columns:
        n = int(df[col].isna().sum())
        if n > 0:
            _summary_lines.append(f"  {col}: {n:,} ({n / len(df) * 100:.1f}%)")
            null_found = True
    if not null_found:
        _summary_lines.append("  (no nulls)")

    # Dimension distributions
    _summary_lines.append("\n--- Dimension columns (unique count + top 5 by frequency) ---")
    for col in dim_cols:
        vc = df[col].value_counts(dropna=False).head(5)
        _summary_lines.append(f"  {col}  [{df[col].nunique()} unique]:")
        for val, cnt in vc.items():
            _summary_lines.append(f"    {val!r}: {cnt:,}")

    # Measure stats
    _summary_lines.append("\n--- Measure columns (descriptive stats) ---")
    if measure_cols:
        desc = df[measure_cols].describe(percentiles=[0.5]).T
        for col, row in desc.iterrows():
            _summary_lines.append(
                f"  {col}: min={row['min']:.2f}  mean={row['mean']:.2f}  "
                f"median={row['50%']:.2f}  max={row['max']:.2f}  std={row['std']:.2f}  "
                f"nulls={int(df[col].isna().sum()):,}"
            )

    # 5 random sample rows
    _summary_lines.append("\n--- 5 random sample rows ---")
    sample = df.sample(min(5, len(df)), random_state=42)
    _summary_lines.append(sample.to_string(index=False))


_summarize_view("View 1: Claims Lifecycle",              view1)
_summarize_view("View 2: District-Month Performance Cube", view2)
_summarize_view("View 3: Hospital Performance",          view3)
_summarize_view("View 4: Beneficiary Journey",           view4)

os.makedirs(REPORTS_DIR, exist_ok=True)
_summary_path = os.path.join(REPORTS_DIR, "view_summaries.txt")
with open(_summary_path, "w", encoding="utf-8") as fh:
    fh.write("\n".join(_summary_lines))
print(f"View summaries saved -> {_summary_path}")


# =============================================================================
# SECTION 11 — Post-View Validation Checklist
# =============================================================================
# These checks run after views are built and are appended to the validation
# report. They confirm grain, join correctness, and plausible value ranges.
# =============================================================================

print("\n" + "=" * 70)
print("SECTION 11: Post-View Validation Checklist")
print("=" * 70)

log("\n\n" + "=" * 70)
log("POST-VIEW VALIDATION CHECKLIST")
log("=" * 70)


def _chk(condition: bool, msg: str) -> None:
    log(f"  {'[PASS]' if condition else '[FAIL]'} {msg}")


# ── Row count plausibility ────────────────────────────────────────────────────
_chk(abs(len(view1) - 22_500) / 22_500 < 0.20,
     f"View 1 row count ~22,500  (actual: {len(view1):,})")
_chk(len(view2) >= 1_000,
     f"View 2 row count reasonable  (actual: {len(view2):,})")
_chk(abs(len(view3) - 4_000) / 4_000 < 0.50,
     f"View 3 row count ~4,000  (actual: {len(view3):,})")
_chk(abs(len(view4) - 200_000) / 200_000 < 0.20,
     f"View 4 row count ~200,000  (actual: {len(view4):,})")

# ── Grain uniqueness ──────────────────────────────────────────────────────────
_chk(view1["case_id"].is_unique,
     "View 1: no duplicate case_ids")
_chk(not view2.duplicated(subset=["district", "month"]).any(),
     "View 2: no duplicate (district, month) pairs")
_chk(not view3.duplicated(subset=["hospital_id", "specialty_code"]).any(),
     "View 3: no duplicate (hospital_id, specialty_code) pairs")
_chk(view4["beneficiary_id"].is_unique,
     "View 4: no duplicate beneficiary_ids")

# ── Left-join integrity (underutilisation rows present) ───────────────────────
_chk((view3["zero_claim_flag"] == 1).any(),
     "View 3: rows with cases_treated=0 exist (left join worked)")
_chk((view3["cases_treated"] > 0).any(),
     "View 3: rows with cases_treated>0 exist")

# ── Monetary non-negativity ───────────────────────────────────────────────────
for _col in ["amount_claimed", "amount_approved", "amount_paid"]:
    if _col in view1.columns:
        _chk((view1[_col].dropna() >= 0).all(),
             f"View 1: {_col} is non-negative")

# ── Temporal span ─────────────────────────────────────────────────────────────
_span = (
    tables["cm_case"]["admission_datetime"].max()
    - tables["cm_case"]["admission_datetime"].min()
).days / 365
_chk(2 <= _span <= 5, f"Temporal span ~3 years  (actual: {_span:.1f} yrs)")

# ── View 2 ratio sanity ───────────────────────────────────────────────────────
_chk(view2["approval_rate"].dropna().between(0, 1).all(),
     "View 2: approval_rate in [0, 1]")
_chk((view2["claims_per_1000_beneficiaries"].dropna() >= 0).all(),
     "View 2: claims_per_1000 is non-negative")

# ── Disease category distribution ────────────────────────────────────────────
_dist = tables["cm_case_diagnosis"]["disease_category"].value_counts(normalize=True)
_chk(_dist.get("NCD", 0) > 0.20,
     f"NCD share ~30%  (actual: {_dist.get('NCD', 0)*100:.1f}%)")

# ── Demographic balance ───────────────────────────────────────────────────────
_gd = view1["gender"].value_counts(normalize=True)
_chk(0.30 < _gd.get("M", 0) < 0.70,
     f"Gender balance: M={_gd.get('M', 0)*100:.1f}%  F={_gd.get('F', 0)*100:.1f}%")

_ht = view1["hospital_type"].value_counts(normalize=True)
_chk("PUBLIC" in _ht.index,
     f"Hospital type: PUBLIC={_ht.get('PUBLIC', 0)*100:.1f}%  "
     f"PRIVATE={_ht.get('PRIVATE', 0)*100:.1f}%")

# ── Cross-view case count consistency (View 1 vs View 3) ─────────────────────
# View 3 is anchored on hm_specialty_offered. Cases treated in a specialty
# that the hospital does not formally list in hm_specialty_offered are
# excluded from View 3's cases_treated count — they appear in hosp_spec_agg
# but don't match any offered row in the left join.
# This is intentional per the spec (offered-capacity vs utilisation analysis),
# but the coverage gap is a meaningful data quality signal on its own:
#   Gap > 0 => hospitals treating beyond their registered specialty list.
# We flag if coverage is below 20% as a sign the join chain may be broken.
_v1_total = len(view1)
_v3_total = int(view3["cases_treated"].sum())
_coverage = _v3_total / _v1_total * 100 if _v1_total > 0 else 0
log(
    f"  [INFO] View 3 SUM(cases_treated) = {_v3_total:,} / {_v1_total:,} View 1 cases "
    f"({_coverage:.1f}% coverage). Gap = cases treated in specialties not listed in "
    f"hm_specialty_offered for that hospital (beyond-registration utilisation)."
)
_chk(
    _coverage > 20,
    f"View 3 case coverage above 20% sanity threshold ({_coverage:.1f}%)",
)

# ── Flush validation report ───────────────────────────────────────────────────
save_validation_report()

print("\n" + "=" * 70)
print("Phase 1 complete.")
print(f"  Views:   {VIEWS_DIR}")
print(f"  Reports: {REPORTS_DIR}")
print("=" * 70)
