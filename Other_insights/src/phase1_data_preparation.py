"""
Phase 1 — Data Preparation
Produces 4 intermediate parquet files for Demand-Supply Gap Analysis
and Hospital Performance Benchmarking.
"""

import os
import sys
import pandas as pd
import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
from pathlib import Path

# ─── Paths ────────────────────────────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).parent
ROOT_DIR   = SCRIPT_DIR.parent.parent          # AB_UP_insights/
DATA_DIR   = ROOT_DIR / "ab_data"
OUT_DIR    = SCRIPT_DIR.parent / "intermediate"
OUT_DIR.mkdir(parents=True, exist_ok=True)

CURRENT_YEAR = 2026

# ─── Source file registry ─────────────────────────────────────────────────────
SOURCE_FILES = {
    # Reference
    "ref_up_geography":          ("ref_up_geography.csv",          "state_code"),
    "ref_hbp_procedure_master":  ("ref_hbp_procedure_master.csv",  "hbp_procedure_code"),
    # Beneficiary
    "bm_household":              ("bm_household.csv",              "household_id"),
    "bm_beneficiary":            ("bm_beneficiary.csv",            "beneficiary_id"),
    "bm_id_document":            ("bm_id_document.csv",            "id_doc_id"),
    "bm_enrolment_request":      ("bm_enrolment_request.csv",      "enrolment_request_id"),
    "bm_card":                   ("bm_card.csv",                   "card_id"),
    # Hospital
    "hm_hospital":               ("hm_hospital.csv",               "hospital_id"),
    "hm_hospital_bank_account":  ("hm_hospital_bank_account.csv",  "hospital_bank_id"),
    "hm_license_certificate":    ("hm_license_certificate.csv",    "hospital_license_id"),
    "hm_specialty_offered":      ("hm_specialty_offered.csv",      "hospital_specialty_id"),
    "hm_staff":                  ("hm_staff.csv",                  "staff_id"),
    # Claims
    "cm_case":                   ("cm_case.csv",                   "case_id"),
    "cm_case_diagnosis":         ("cm_case_diagnosis.csv",         "case_diagnosis_id"),
    "cm_preauth_request":        ("cm_preauth_request.csv",        "preauth_id"),
    "cm_preauth_procedure_line": ("cm_preauth_procedure_line.csv", "preauth_proc_id"),
    "cm_discharge":              ("cm_discharge.csv",              "discharge_id"),
    "cm_claim":                  ("cm_claim.csv",                  "claim_id"),
    "cm_claim_document":         ("cm_claim_document.csv",         "claim_doc_id"),
    "cm_adjudication_event":     ("cm_adjudication_event.csv",     "event_id"),
    "cm_payment":                ("cm_payment.csv",                "payment_id"),
}

# Timestamp columns per table (for parse_dates)
TIMESTAMP_COLS = {
    "bm_household":              ["created_at"],
    "bm_beneficiary":            ["created_at", "updated_at"],
    "bm_enrolment_request":      ["submitted_at", "reviewed_at"],
    "bm_card":                   ["issued_at"],
    "hm_hospital":               ["accreditation_valid_upto", "created_at", "updated_at"],
    "hm_license_certificate":    ["issue_date", "expiry_date"],
    "cm_case":                   ["admission_datetime", "discharge_datetime", "created_at"],
    "cm_preauth_request":        ["initiated_at", "ppd_decision_at", "last_query_at",
                                  "last_query_response_at", "cancelled_at"],
    "cm_discharge":              ["surgery_date", "discharge_date", "lama_date", "death_date"],
    "cm_claim":                  ["submitted_at", "settled_at"],
    "cm_payment":                ["payment_date"],
    "cm_adjudication_event":     ["event_time"],
}

# FK relationships to check (child_table, fk_col, parent_table, pk_col)
FK_CHECKS = [
    ("bm_beneficiary",            "household_id",       "bm_household",            "household_id"),
    ("bm_id_document",            "beneficiary_id",     "bm_beneficiary",           "beneficiary_id"),
    ("bm_enrolment_request",      "beneficiary_id",     "bm_beneficiary",           "beneficiary_id"),
    ("bm_card",                   "beneficiary_id",     "bm_beneficiary",           "beneficiary_id"),
    ("cm_case",                   "beneficiary_id",     "bm_beneficiary",           "beneficiary_id"),
    ("cm_case",                   "hospital_id",        "hm_hospital",              "hospital_id"),
    ("cm_case_diagnosis",         "case_id",            "cm_case",                  "case_id"),
    ("cm_preauth_request",        "case_id",            "cm_case",                  "case_id"),
    ("cm_preauth_procedure_line", "preauth_id",         "cm_preauth_request",       "preauth_id"),
    ("cm_discharge",              "case_id",            "cm_case",                  "case_id"),
    ("cm_claim",                  "case_id",            "cm_case",                  "case_id"),
    ("cm_claim_document",         "claim_id",           "cm_claim",                 "claim_id"),
    ("cm_adjudication_event",     "claim_id",           "cm_claim",                 "claim_id"),
    ("cm_payment",                "claim_id",           "cm_claim",                 "claim_id"),
    ("hm_hospital_bank_account",  "hospital_id",        "hm_hospital",              "hospital_id"),
    ("hm_license_certificate",    "hospital_id",        "hm_hospital",              "hospital_id"),
    ("hm_specialty_offered",      "hospital_id",        "hm_hospital",              "hospital_id"),
    ("hm_staff",                  "hospital_id",        "hm_hospital",              "hospital_id"),
]


def section(title):
    print(f"\n{'='*70}", flush=True)
    print(f"  {title}", flush=True)
    print('='*70, flush=True)


def subsection(title):
    print(f"\n  {'-'*60}")
    print(f"  {title}")
    print(f"  {'-'*60}")


# ─── STEP 1: Load & Validate ──────────────────────────────────────────────────
section("STEP 1 — Load and Validate")

tables = {}
critical_errors = []

for name, (fname, pk_col) in SOURCE_FILES.items():
    fpath = DATA_DIR / fname
    if not fpath.exists():
        print(f"[MISSING] {fname}")
        critical_errors.append(f"Missing file: {fname}")
        continue

    ts_cols = TIMESTAMP_COLS.get(name, [])
    df = pd.read_csv(fpath, parse_dates=ts_cols, low_memory=False)

    # Shape
    print(f"\n[{name}]  shape={df.shape}")

    # PK uniqueness (skip ref_up_geography — geography has no single unique PK)
    if name != "ref_up_geography":
        if pk_col in df.columns:
            dupes = df[pk_col].duplicated().sum()
            if dupes > 0:
                msg = f"PK '{pk_col}' has {dupes} duplicates in {name}"
                print(f"  [CRITICAL] {msg}")
                critical_errors.append(msg)
            else:
                print(f"  PK '{pk_col}': OK (unique)")
        else:
            print(f"  [WARN] PK column '{pk_col}' not found")

    # Null percentages
    null_pct = (df.isnull().sum() / len(df) * 100).round(1)
    non_zero = null_pct[null_pct > 0]
    if len(non_zero):
        print("  Nulls (%):", dict(non_zero))
    else:
        print("  Nulls: none")

    tables[name] = df

if critical_errors:
    print("\n[STOPPING] Critical errors found:")
    for e in critical_errors:
        print(f"  • {e}")
    sys.exit(1)

# FK checks
subsection("Foreign Key Checks")
for child, fk, parent, pk in FK_CHECKS:
    if child not in tables or parent not in tables:
        continue
    child_vals  = set(tables[child][fk].dropna())
    parent_vals = set(tables[parent][pk].dropna())
    orphans = child_vals - parent_vals
    status = f"  {orphans} orphan(s)" if orphans else "  OK"
    print(f"  {child}.{fk} → {parent}.{pk}: {status}")


# ─── STEP 2: Derived Columns ──────────────────────────────────────────────────
section("STEP 2 — Derived Columns")

# bm_beneficiary
ben = tables["bm_beneficiary"].copy()
ben["age_at_record"] = ben["yob"].apply(
    lambda y: CURRENT_YEAR - int(y) if pd.notna(y) else None
)
def age_band(age):
    if pd.isna(age): return None
    a = int(age)
    if a <=  5: return "0-5"
    if a <= 14: return "6-14"
    if a <= 30: return "15-30"
    if a <= 45: return "31-45"
    if a <= 60: return "46-60"
    return "60+"
ben["age_band"] = ben["age_at_record"].apply(age_band)
tables["bm_beneficiary"] = ben
print("  bm_beneficiary: age_at_record, age_band added")

# cm_case
cases = tables["cm_case"].copy()
cases["admission_date"]       = pd.to_datetime(cases["admission_datetime"], utc=True).dt.date
cases["discharge_date_derived"] = pd.to_datetime(cases["discharge_datetime"], utc=True).dt.date
adm_dt = pd.to_datetime(cases["admission_datetime"], utc=True)
dis_dt = pd.to_datetime(cases["discharge_datetime"], utc=True)
cases["los_days"]             = (dis_dt - adm_dt).dt.days
neg_los = (cases["los_days"] < 0).sum()
if neg_los:
    print(f"  [ANOMALY] {neg_los} cases with negative LOS — kept")
cases["admission_year"]  = adm_dt.dt.year
cases["admission_month"] = adm_dt.dt.strftime("%Y-%m")
tables["cm_case"] = cases
print("  cm_case: admission_date, discharge_date_derived, los_days, admission_year, admission_month added")

# cm_claim
claims = tables["cm_claim"].copy()
claims["amount_diff"]    = claims["amount_claimed"] - claims["amount_approved"]
claims["approval_ratio"] = np.where(
    claims["amount_claimed"].notna() & (claims["amount_claimed"] != 0) & claims["amount_approved"].notna(),
    claims["amount_approved"] / claims["amount_claimed"],
    np.nan
)
tables["cm_claim"] = claims
print("  cm_claim: amount_diff, approval_ratio added")

# hm_hospital
hosp = tables["hm_hospital"].copy()
def capacity_band(beds):
    if pd.isna(beds): return None
    b = int(beds)
    if b < 30:   return "Small (<30)"
    if b < 100:  return "Medium (30-100)"
    if b < 300:  return "Large (100-300)"
    return "Very Large (300+)"
hosp["capacity_band"] = hosp["total_bed_strength"].apply(capacity_band)
tables["hm_hospital"] = hosp
print("  hm_hospital: capacity_band added")


# ─── STEP 2b: Pre-aggregate Claims per Case ───────────────────────────────────
section("STEP 2b — claims_per_case helper")

STATUS_PRIORITY = {"REJECTED": 5, "QUERY_RAISED": 4, "PENDING": 3,
                   "APPROVED": 2, "SETTLED": 1}

def worst_status(statuses):
    best_priority = 0
    winner = None
    for s in statuses:
        p = STATUS_PRIORITY.get(s, 0)
        if p > best_priority:
            best_priority = p
            winner = s
    return winner

cl = tables["cm_claim"]
claims_per_case = cl.groupby("case_id").agg(
    total_amount_claimed    = ("amount_claimed",      "sum"),
    total_amount_approved   = ("amount_approved",     "sum"),
    claim_count             = ("claim_id",            "count"),
    any_claim_approved      = ("claim_status",        lambda x: any(v in ("APPROVED", "SETTLED") for v in x)),
    any_claim_rejected      = ("claim_status",        lambda x: any(v == "REJECTED" for v in x)),
    any_claim_queried       = ("claim_status",        lambda x: any(v == "QUERY_RAISED" for v in x)),
    any_claim_pending       = ("claim_status",        lambda x: any(v == "PENDING" for v in x)),
    max_query_count         = ("query_count",         "max"),
    total_query_count       = ("query_count",         "sum"),
    min_settlement_tat_days = ("settlement_tat_days", "min"),
    avg_settlement_tat_days = ("settlement_tat_days", "mean"),
    is_portability_claim    = ("is_portability_claim","max"),
).reset_index()

claims_per_case["worst_claim_status"] = (
    cl.groupby("case_id")["claim_status"]
      .apply(worst_status)
      .reset_index(drop=True)
)

# Null out total_amount_approved where 0 and no approved claim (sum of NaN = 0 in pandas)
claims_per_case["total_amount_approved"] = np.where(
    claims_per_case["any_claim_approved"],
    claims_per_case["total_amount_approved"],
    np.nan
)

print(f"  claims_per_case: {claims_per_case.shape[0]} rows (one per case_id)")
print(f"  Sample:\n{claims_per_case.head(2).to_string()}")


# ─── STEP 3: int_demand_supply ────────────────────────────────────────────────
section("STEP 3 — int_demand_supply")

geo      = tables["ref_up_geography"]
cases_df = tables["cm_case"]
ben_df   = tables["bm_beneficiary"]
hh_df    = tables["bm_household"]
hosp_df  = tables["hm_hospital"]
spec_df  = tables["hm_specialty_offered"]
card_df  = tables["bm_card"]

# Geography spine: unique block+district+division
geo_spine = geo[["block_name", "district_name", "division_name"]].drop_duplicates()
geo_spine = geo_spine.rename(columns={
    "block_name":    "block",
    "district_name": "district",
    "division_name": "division",
})

# Months from cases
months = cases_df["admission_month"].dropna().unique()
months_df = pd.DataFrame({"month": months})

# Full spine: every block × month
spine = geo_spine.merge(months_df, how="cross")
print(f"  Spine: {len(geo_spine)} blocks × {len(months)} months = {len(spine)} rows")

# ── Demand side ──
case_hh = (
    cases_df
    .merge(ben_df[["beneficiary_id", "household_id"]], on="beneficiary_id", how="left")
    .merge(hh_df[["household_id", "home_block_name", "home_district_code", "home_division_name"]],
           on="household_id", how="left")
    .merge(claims_per_case, on="case_id", how="left")
)

demand = case_hh.groupby(
    ["home_block_name", "home_district_code", "home_division_name", "admission_month"],
    dropna=False
).agg(
    total_cases           = ("case_id",               "count"),
    emergency_cases       = ("admission_type",        lambda x: (x == "EMERGENCY").sum()),
    elective_cases        = ("admission_type",        lambda x: (x == "ELECTIVE").sum()),
    portability_out_cases = ("is_portability",        lambda x: x.astype(bool).sum()),
    unique_beneficiaries  = ("beneficiary_id",        "nunique"),
    total_amount_claimed  = ("total_amount_claimed",  "sum"),
    total_amount_approved = ("total_amount_approved", "sum"),
    death_cases           = ("discharge_type",        lambda x: (x == "DEATH").sum()),
    lama_dama_cases       = ("discharge_type",        lambda x: x.isin(["LAMA", "DAMA"]).sum()),
).reset_index().rename(columns={
    "home_block_name":    "block",
    "home_district_code": "district",
    "home_division_name": "division",
    "admission_month":    "month",
})

# ── Supply side (static per block) ──
spec_counts = (
    spec_df.merge(hosp_df[["hospital_id", "block_name", "district_name"]], on="hospital_id", how="left")
    .groupby(["block_name", "district_name"])["specialty_code"]
    .nunique()
    .reset_index()
    .rename(columns={"specialty_code": "specialties_available",
                     "block_name": "block", "district_name": "district"})
)

supply = (
    hosp_df.groupby(["block_name", "district_name", "division_name"])
    .agg(
        total_hospitals     = ("hospital_id",                "count"),
        public_hospitals    = ("hospital_type",              lambda x: (x == "PUBLIC").sum()),
        private_hospitals   = ("hospital_type",              lambda x: (x == "PRIVATE").sum()),
        total_beds          = ("total_bed_strength",         "sum"),
        total_inpatient_beds= ("inpatient_beds",             "sum"),
        hospitals_with_icu  = ("has_icu_with_ac",            lambda x: x.astype(bool).sum()),
        hospitals_with_ot   = ("has_fully_equipped_ot",      lambda x: x.astype(bool).sum()),
        delisted_hospitals  = ("delisted_from_gov_schemes",  lambda x: x.astype(bool).sum()),
        accredited_hospitals= ("accreditation_board",        lambda x: x.notna().sum()),
    )
    .reset_index()
    .rename(columns={"block_name": "block", "district_name": "district",
                     "division_name": "division"})
    .merge(spec_counts, on=["block", "district"], how="left")
)

# ── Enrolment side (static per block) ──
active_cards = (
    card_df[card_df["card_status"] == "ACTIVE"]
    .merge(ben_df[["beneficiary_id", "household_id"]], on="beneficiary_id", how="left")
    .merge(hh_df[["household_id", "home_block_name", "home_district_code"]], on="household_id", how="left")
    .groupby(["home_block_name", "home_district_code"])["card_id"]
    .count().reset_index()
    .rename(columns={"card_id": "active_cards",
                     "home_block_name": "block", "home_district_code": "district"})
)

enrolment = (
    hh_df.merge(ben_df[["beneficiary_id", "household_id"]], on="household_id", how="left")
    .groupby(["home_block_name", "home_district_code", "home_division_name"])
    .agg(
        total_households_enrolled  = ("household_id",   "nunique"),
        total_beneficiaries_enrolled = ("beneficiary_id", "nunique"),
    )
    .reset_index()
    .rename(columns={"home_block_name": "block", "home_district_code": "district",
                     "home_division_name": "division"})
    .merge(active_cards, on=["block", "district"], how="left")
)

# ── Join on spine ──
# division is fully determined by block+district — include it in join keys to avoid suffix duplication
int_ds = (
    spine
    .merge(demand.drop(columns=["division"], errors="ignore"),
           on=["block", "district", "month"], how="left")
    .merge(supply.drop(columns=["division"], errors="ignore"),
           on=["block", "district"],          how="left")
    .merge(enrolment.drop(columns=["division"], errors="ignore"),
           on=["block", "district"],          how="left")
)
# Drop any accidental duplicate suffix columns
dup_cols = [c for c in int_ds.columns if c.endswith("_x") or c.endswith("_y")]
int_ds.drop(columns=dup_cols, inplace=True, errors="ignore")

# ── Computed columns ──
def safe_div(num, den):
    return np.where((den.isna()) | (den == 0), np.nan, num / den)

int_ds["cases_per_1000_enrolled"] = safe_div(int_ds["total_cases"], int_ds["total_beneficiaries_enrolled"]) * 1000
int_ds["cases_per_bed"]           = safe_div(int_ds["total_cases"], int_ds["total_inpatient_beds"])
int_ds["utilization_rate"]        = safe_div(int_ds["unique_beneficiaries"], int_ds["total_beneficiaries_enrolled"])
int_ds["portability_out_rate"]    = safe_div(int_ds["portability_out_cases"], int_ds["total_cases"])
int_ds["bed_density_per_1000"]    = safe_div(int_ds["total_inpatient_beds"], int_ds["total_beneficiaries_enrolled"]) * 1000

out_path = OUT_DIR / "int_demand_supply.parquet"
int_ds.to_parquet(out_path, index=False)
print(f"  → {out_path}")
print(f"  Shape: {int_ds.shape}")
print(f"  Sample:\n{int_ds.head(3).to_string()}")


# ─── STEP 4: int_hospital_performance ─────────────────────────────────────────
section("STEP 4 — int_hospital_performance")

preauth_df   = tables["cm_preauth_request"]
proc_line_df = tables["cm_preauth_procedure_line"]
proc_master  = tables["ref_hbp_procedure_master"]
discharge_df = tables["cm_discharge"]

# Active preauth per case: not REJECTED/CANCELLED, latest by initiated_at
active_preauth = preauth_df[
    ~preauth_df["status"].isin(["REJECTED", "CANCELLED"])
].copy()
active_preauth["initiated_at"] = pd.to_datetime(active_preauth["initiated_at"], utc=True)
active_preauth = (
    active_preauth.sort_values("initiated_at", ascending=False)
                  .drop_duplicates(subset=["case_id"], keep="first")
)

# Primary procedure only (rank 1)
primary_proc = proc_line_df[proc_line_df["procedure_rank"] == 1]

# Build join chain
hp_df = (
    cases_df[["case_id", "hospital_id", "admission_month", "discharge_type",
               "admission_type", "los_days", "beneficiary_id"]]
    .merge(hosp_df[["hospital_id", "hospital_name", "hospital_type", "hospital_sub_type",
                     "block_name", "district_name", "division_name", "capacity_band"]],
           on="hospital_id", how="left")
    .merge(active_preauth[["case_id", "preauth_id", "status"]]
           .rename(columns={"status": "preauth_status"}),
           on="case_id", how="left")
    .merge(primary_proc[["preauth_id", "hbp_procedure_code"]],
           on="preauth_id", how="left")
    .merge(proc_master[["hbp_procedure_code", "procedure_name", "specialty_code",
                         "specialty_name", "base_package_price"]],
           on="hbp_procedure_code", how="left")
    .merge(discharge_df[["case_id", "biometric_auth_used", "provided_medicines_flag"]],
           on="case_id", how="left")
    .merge(claims_per_case, on="case_id", how="left")
)

# Cases with no matched preauth/procedure are still included but grouped under nulls —
# they represent missing preauth linkage (intentional anomalies)

# Pre-compute boolean/float indicator columns for easy aggregation
hp_df["_normal_discharge"]    = hp_df["discharge_type"].isin(["NORMAL", "LIVE"]).astype(float)
hp_df["_lama_dama"]           = hp_df["discharge_type"].isin(["LAMA", "DAMA"]).astype(float)
hp_df["_death"]               = (hp_df["discharge_type"] == "DEATH").astype(float)
hp_df["_preauth_auto"]        = (hp_df["preauth_status"] == "AUTO_APPROVED").astype(float)
hp_df["_biometric"]           = hp_df["biometric_auth_used"].astype(float)
hp_df["_medicines"]           = hp_df["provided_medicines_flag"].astype(float)
hp_df["_approval_ratio_row"]  = hp_df["total_amount_approved"] / hp_df["total_amount_claimed"].replace(0, np.nan)

GRP = ["hospital_id", "hbp_procedure_code", "admission_month"]

int_hp = (
    hp_df.groupby(GRP, dropna=False)
    .agg(
        case_count                = ("case_id",               "count"),
        avg_los_days              = ("los_days",              "mean"),
        median_los_days           = ("los_days",              "median"),
        avg_amount_claimed        = ("total_amount_claimed",  "mean"),
        avg_amount_approved       = ("total_amount_approved", "mean"),
        avg_approval_ratio        = ("_approval_ratio_row",   "mean"),
        total_amount_claimed      = ("total_amount_claimed",  "sum"),
        total_amount_approved     = ("total_amount_approved", "sum"),
        claim_approval_rate       = ("any_claim_approved",    "mean"),
        claim_rejection_rate      = ("any_claim_rejected",    "mean"),
        claim_query_rate          = ("any_claim_queried",     "mean"),
        avg_query_count           = ("total_query_count",     "mean"),
        normal_discharge_rate     = ("_normal_discharge",     "mean"),
        lama_dama_rate            = ("_lama_dama",            "mean"),
        mortality_rate            = ("_death",                "mean"),
        avg_settlement_tat_days   = ("avg_settlement_tat_days","mean"),
        preauth_auto_approval_rate= ("_preauth_auto",         "mean"),
        biometric_auth_rate       = ("_biometric",            "mean"),
        medicines_provided_rate   = ("_medicines",            "mean"),
    )
    .reset_index()
    .rename(columns={"admission_month": "month"})
)

# Merge static descriptor columns (take first value per group — stable)
static_cols = hp_df.groupby(GRP, dropna=False)[
    ["hospital_name", "hospital_type", "hospital_sub_type",
     "block_name", "district_name", "division_name", "capacity_band",
     "procedure_name", "specialty_code", "specialty_name", "base_package_price"]
].first().reset_index().rename(columns={"admission_month": "month"})

int_hp = int_hp.merge(static_cols, on=["hospital_id", "hbp_procedure_code", "month"], how="left")
int_hp = int_hp.rename(columns={
    "block_name": "block", "district_name": "district", "division_name": "division"
})

out_path = OUT_DIR / "int_hospital_performance.parquet"
int_hp.to_parquet(out_path, index=False)
print(f"  → {out_path}")
print(f"  Shape: {int_hp.shape}")
print(f"  Sample:\n{int_hp.head(3).to_string()}")


# ─── STEP 5: int_enrolment_monthly ────────────────────────────────────────────
section("STEP 5 — int_enrolment_monthly")

ben_hh = (
    ben_df[["beneficiary_id", "household_id", "created_at"]]
    .merge(hh_df[["household_id", "home_block_name", "home_district_code", "home_division_name"]],
           on="household_id", how="left")
)
ben_hh["month"] = pd.to_datetime(ben_hh["created_at"]).dt.strftime("%Y-%m")

new_ben = (
    ben_hh.groupby(["home_block_name", "home_district_code", "home_division_name", "month"])
    ["beneficiary_id"].count().reset_index()
    .rename(columns={"beneficiary_id": "new_beneficiaries_enrolled",
                     "home_block_name": "block",
                     "home_district_code": "district",
                     "home_division_name": "division"})
)

# Cards issued per month per block
card_ben = (
    card_df[["card_id", "beneficiary_id", "issued_at"]]
    .merge(ben_df[["beneficiary_id", "household_id"]], on="beneficiary_id", how="left")
    .merge(hh_df[["household_id", "home_block_name", "home_district_code"]], on="household_id", how="left")
)
card_ben["month"] = pd.to_datetime(card_ben["issued_at"]).dt.strftime("%Y-%m")

new_cards = (
    card_ben.groupby(["home_block_name", "home_district_code", "month"])["card_id"]
    .count().reset_index()
    .rename(columns={"card_id": "new_cards_issued",
                     "home_block_name": "block",
                     "home_district_code": "district"})
)

int_enr = new_ben.merge(new_cards, on=["block", "district", "month"], how="left")

# Cumulative sums per block+district (sort first)
int_enr = int_enr.sort_values(["block", "district", "month"])
int_enr["cumulative_beneficiaries"] = (
    int_enr.groupby(["block", "district"])["new_beneficiaries_enrolled"]
    .cumsum()
)
int_enr["new_cards_issued"] = int_enr["new_cards_issued"].fillna(0).astype(int)
int_enr["cumulative_cards_issued"] = (
    int_enr.groupby(["block", "district"])["new_cards_issued"]
    .cumsum()
)

out_path = OUT_DIR / "int_enrolment_monthly.parquet"
int_enr.to_parquet(out_path, index=False)
print(f"  → {out_path}")
print(f"  Shape: {int_enr.shape}")
print(f"  Sample:\n{int_enr.head(3).to_string()}")


# ─── STEP 6: int_specialty_gap ────────────────────────────────────────────────
section("STEP 6 — int_specialty_gap")

# Demand: case → preauth → primary proc → procedure master → beneficiary home location
demand_spec = (
    cases_df[["case_id", "beneficiary_id"]]
    .merge(active_preauth[["case_id", "preauth_id"]], on="case_id", how="left")
    .merge(primary_proc[["preauth_id", "hbp_procedure_code"]], on="preauth_id", how="left")
    .merge(proc_master[["hbp_procedure_code", "specialty_code", "specialty_name"]],
           on="hbp_procedure_code", how="left")
    .merge(ben_df[["beneficiary_id", "household_id"]], on="beneficiary_id", how="left")
    .merge(hh_df[["household_id", "home_block_name", "home_district_code", "home_division_name"]],
           on="household_id", how="left")
    .merge(claims_per_case[["case_id", "total_amount_claimed"]], on="case_id", how="left")
)

demand_spec_agg = (
    demand_spec.groupby(
        ["home_block_name", "home_district_code", "home_division_name",
         "specialty_code", "specialty_name"], dropna=False)
    .agg(
        cases_demanding  = ("case_id",               "count"),
        unique_patients  = ("beneficiary_id",        "nunique"),
        amount_claimed   = ("total_amount_claimed",  "sum"),
    )
    .reset_index()
    .rename(columns={"home_block_name": "block",
                     "home_district_code": "district",
                     "home_division_name": "division"})
)

# Supply: hospital → specialty offered
supply_spec = (
    hosp_df[["hospital_id", "block_name", "district_name"]]
    .merge(spec_df[["hospital_id", "specialty_code", "admissions_prev_fy"]],
           on="hospital_id", how="inner")
    .groupby(["block_name", "district_name", "specialty_code"])
    .agg(
        hospitals_offering       = ("hospital_id",         "nunique"),
        total_prev_fy_admissions = ("admissions_prev_fy",  "sum"),
    )
    .reset_index()
    .rename(columns={"block_name": "block", "district_name": "district"})
)

# Full outer join
int_sg = demand_spec_agg.merge(
    supply_spec, on=["block", "district", "specialty_code"], how="outer"
)

int_sg["gap_flag"] = (
    (int_sg["cases_demanding"] > 0) &
    (int_sg["hospitals_offering"].isna() | (int_sg["hospitals_offering"] == 0))
)
int_sg["demand_supply_ratio"] = safe_div(
    int_sg["cases_demanding"], int_sg["hospitals_offering"]
)
int_sg["unmet_demand"] = int_sg["gap_flag"]  # threshold to be applied in Phase 2

out_path = OUT_DIR / "int_specialty_gap.parquet"
int_sg.to_parquet(out_path, index=False)
print(f"  → {out_path}")
print(f"  Shape: {int_sg.shape}")
print(f"  Sample:\n{int_sg.head(3).to_string()}")


# ─── Summary ──────────────────────────────────────────────────────────────────
section("SUMMARY")

outputs = {
    "int_demand_supply":       int_ds,
    "int_hospital_performance":int_hp,
    "int_enrolment_monthly":   int_enr,
    "int_specialty_gap":       int_sg,
}

anomalies = []
if neg_los:
    anomalies.append(f"{neg_los} cases with negative LOS (kept)")
for child, fk, parent, pk in FK_CHECKS:
    if child not in tables or parent not in tables:
        continue
    orphans = set(tables[child][fk].dropna()) - set(tables[parent][pk].dropna())
    if orphans:
        anomalies.append(f"{len(orphans)} orphan {child}.{fk} values")

summary_lines = ["# Phase 1 Summary\n"]
summary_lines.append("## Files Created\n")
for name, df in outputs.items():
    summary_lines.append(f"- `intermediate/{name}.parquet` — {df.shape[0]:,} rows × {df.shape[1]} cols")

summary_lines.append("\n## Anomalies / Notes\n")
if anomalies:
    for a in anomalies:
        summary_lines.append(f"- {a}")
else:
    summary_lines.append("- None detected")

summary_lines.append("\n## Assumptions\n")
summary_lines.append("- Geography spine built from `ref_up_geography`; months from `cm_case.admission_month`.")
summary_lines.append("- Demand block = beneficiary's HOME block (from `bm_household`), not hospital location.")
summary_lines.append("- Supply columns are static (not time-varying) — joined uniformly across all months.")
summary_lines.append("- Enrolment columns are static snapshots, not monthly-varying in `int_demand_supply`.")
summary_lines.append("- `claims_per_case` aggregates all claims per case to prevent row explosion.")
summary_lines.append("- Hospital performance uses only the active (non-rejected/cancelled) preauth, latest by `initiated_at`.")
summary_lines.append("- Only `procedure_rank = 1` used for procedure grouping; add-ons excluded.")
summary_lines.append("- `total_amount_approved` in `claims_per_case` set to NaN when no claim is approved (avoids misleading 0 sum).")
summary_lines.append("- Cases with no matched preauth/procedure are included in `int_hospital_performance` under null procedure group.")

summary_text = "\n".join(summary_lines)
summary_path = SCRIPT_DIR.parent / "phase1_summary.md"
summary_path.write_text(summary_text, encoding="utf-8")
print(f"\n  Summary written to: {summary_path}")
print(summary_text)
print("\n[DONE] Phase 1 complete.")
