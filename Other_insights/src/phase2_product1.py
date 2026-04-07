"""
Phase 2 — Analytical Engine: Product 1 (Demand-Supply Gap Analysis)
Produces 9 analytics parquet files from Phase 1 intermediates + raw CSVs.
"""

import sys
import pandas as pd
import numpy as np
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
ROOT_DIR   = SCRIPT_DIR.parent.parent
DATA_DIR   = ROOT_DIR / "ab_data"
INT_DIR    = SCRIPT_DIR.parent / "intermediate"
OUT_DIR    = SCRIPT_DIR.parent / "analytics"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# ─── Helpers ──────────────────────────────────────────────────────────────────
def section(title):
    print(f"\n{'='*70}", flush=True)
    print(f"  {title}", flush=True)
    print('='*70, flush=True)

def load_csv(name, ts_cols=None, bool_cols=None):
    path = DATA_DIR / name
    if not path.exists():
        raise FileNotFoundError(f"Missing: {path}")
    df = pd.read_csv(path, parse_dates=ts_cols or [], low_memory=False)
    if bool_cols:
        for col in bool_cols:
            if col in df.columns and df[col].dtype == object:
                df[col] = df[col].map({'True': True, 'False': False})
            elif col in df.columns:
                df[col] = df[col].astype(bool)
    return df

def load_parquet(name):
    path = INT_DIR / name
    if not path.exists():
        raise FileNotFoundError(f"Missing intermediate: {path}")
    return pd.read_parquet(path)

def safe_div(num, den):
    return np.where((pd.isna(den)) | (den == 0), np.nan, num / den)

def save(df, name):
    path = OUT_DIR / name
    df.to_parquet(path, index=False)
    print(f"  -> {path}  shape={df.shape}")


# ─── Load Phase 1 intermediates ───────────────────────────────────────────────
section("Loading Phase 1 intermediates")
int_ds  = load_parquet("int_demand_supply.parquet")
int_hp  = load_parquet("int_hospital_performance.parquet")
int_enr = load_parquet("int_enrolment_monthly.parquet")
int_sg  = load_parquet("int_specialty_gap.parquet")
print(f"  int_demand_supply:          {int_ds.shape}")
print(f"  int_hospital_performance:   {int_hp.shape}")
print(f"  int_enrolment_monthly:      {int_enr.shape}")
print(f"  int_specialty_gap:          {int_sg.shape}")


# ─── Load raw CSVs ────────────────────────────────────────────────────────────
section("Loading raw CSVs")
cases_df   = load_csv("cm_case.csv",
                      ts_cols=["admission_datetime", "discharge_datetime"],
                      bool_cols=["is_portability"])
diag_df    = load_csv("cm_case_diagnosis.csv")
claim_df   = load_csv("cm_claim.csv")
hosp_df    = load_csv("hm_hospital.csv",
                      bool_cols=["delisted_from_gov_schemes", "has_fully_equipped_ot",
                                 "has_icu_with_ac", "has_casualty", "has_opd",
                                 "has_hdu", "has_general_ward", "has_labour_room"])
spec_df    = load_csv("hm_specialty_offered.csv")
ben_df     = load_csv("bm_beneficiary.csv")
hh_df      = load_csv("bm_household.csv")
card_df    = load_csv("bm_card.csv")
enrol_df   = load_csv("bm_enrolment_request.csv", ts_cols=["submitted_at"])
preauth_df = load_csv("cm_preauth_request.csv",   ts_cols=["initiated_at"])
proc_df    = load_csv("cm_preauth_procedure_line.csv")

# Derived columns on cases
adm_dt = pd.to_datetime(cases_df["admission_datetime"], utc=True)
dis_dt = pd.to_datetime(cases_df["discharge_datetime"],  utc=True)
cases_df["admission_month"] = adm_dt.dt.strftime("%Y-%m")
cases_df["los_days"]        = (dis_dt - adm_dt).dt.days


# ─── Rebuild claims_per_case (lightweight) ────────────────────────────────────
section("Rebuilding claims_per_case helper")
claims_per_case = (
    claim_df.groupby("case_id")
    .agg(
        total_amount_claimed  = ("amount_claimed",  "sum"),
        total_amount_approved = ("amount_approved", "sum"),
    )
    .reset_index()
)
print(f"  claims_per_case: {len(claims_per_case)} rows")


# ─── Active preauth per case (reused in Analyses 4, 6) ───────────────────────
active_preauth = preauth_df[~preauth_df["status"].isin(["REJECTED", "CANCELLED"])].copy()
active_preauth["initiated_at"] = pd.to_datetime(active_preauth["initiated_at"], utc=True)
active_preauth = (
    active_preauth.sort_values("initiated_at", ascending=False)
                  .drop_duplicates(subset=["case_id"], keep="first")
    [["case_id", "preauth_id", "status"]]
    .rename(columns={"status": "preauth_status"})
)
primary_proc_lines = proc_df[proc_df["procedure_rank"] == 1][["preauth_id", "hbp_procedure_code"]]


# ─── ICD-10 classifier (reused in Analyses 3 and 7) ──────────────────────────
def classify_icd(code):
    if pd.isna(code):
        return "OTHER"
    code = str(code).strip().upper()
    if not code:
        return "OTHER"
    letter = code[0]
    try:
        num_str = code[1:].split(".")[0].split(" ")[0]
        num = int(num_str) if num_str else 0
    except Exception:
        return "OTHER"
    # First match wins
    if letter == "I":                         return "NCD"
    if letter == "E" and 10 <= num <= 14:     return "NCD"
    if letter == "J" and 40 <= num <= 47:     return "NCD"
    if letter == "C" and num <= 97:           return "NCD"
    if letter == "N" and 17 <= num <= 19:     return "NCD"
    if letter == "A" and num <= 9:            return "COMMUNICABLE"
    if letter == "A" and 15 <= num <= 19:     return "COMMUNICABLE"
    if letter == "A" and 90 <= num <= 99:     return "COMMUNICABLE"
    if letter == "B" and 50 <= num <= 54:     return "COMMUNICABLE"
    if letter == "J" and 9 <= num <= 18:      return "COMMUNICABLE"
    if letter == "O":                         return "MATERNAL_NEONATAL"
    if letter == "P":                         return "MATERNAL_NEONATAL"
    if letter == "Z" and num == 37:           return "MATERNAL_NEONATAL"
    if letter == "K" and 35 <= num <= 38:     return "SURGICAL"
    if letter == "K" and 40 <= num <= 46:     return "SURGICAL"
    if letter == "H" and 25 <= num <= 26:     return "SURGICAL"
    if letter == "N" and num == 40:           return "SURGICAL"
    if letter == "S":                         return "INJURY"
    if letter == "T" and num <= 98:           return "INJURY"
    return "OTHER"

# Primary diagnosis per case (used in Analysis 3 and 7)
primary_diag = (
    diag_df[diag_df["diagnosis_rank"] == 1][["case_id", "icd_code"]].copy()
)
primary_diag["disease_category"] = primary_diag["icd_code"].apply(classify_icd)


# ═══════════════════════════════════════════════════════════════════════════════
# ANALYSIS 1: Utilization Gap Scoring
# ═══════════════════════════════════════════════════════════════════════════════
section("ANALYSIS 1 — Utilization Gap Scoring")

BLK = ["block", "district"]

# Block-level total cases (sum across months)
cases_sum = (
    int_ds.groupby(BLK)
    .agg(total_cases_all_months=("total_cases", lambda x: x.fillna(0).sum()))
    .reset_index()
)

# Static snapshot columns (take first non-null per block)
block_static = (
    int_ds.groupby(BLK)[["division", "total_hospitals", "total_inpatient_beds",
                           "total_beneficiaries_enrolled"]]
    .first()
    .reset_index()
)

# Distinct beneficiaries with at least one case (can't sum monthly counts)
case_home = (
    cases_df[["case_id", "beneficiary_id"]]
    .merge(ben_df[["beneficiary_id", "household_id"]], on="beneficiary_id", how="left")
    .merge(hh_df[["household_id", "home_block_name", "home_district_code"]], on="household_id", how="left")
)
distinct_ben = (
    case_home.groupby(["home_block_name", "home_district_code"])["beneficiary_id"]
    .nunique().reset_index()
    .rename(columns={"beneficiary_id":    "distinct_beneficiaries_with_cases",
                     "home_block_name":   "block",
                     "home_district_code":"district"})
)

# Bed-days consumed per block (demand perspective: where patient lives)
bed_days = (
    cases_df[["beneficiary_id", "los_days"]]
    .merge(ben_df[["beneficiary_id", "household_id"]], on="beneficiary_id", how="left")
    .merge(hh_df[["household_id", "home_block_name", "home_district_code"]], on="household_id", how="left")
    .groupby(["home_block_name", "home_district_code"])["los_days"]
    .sum().reset_index()
    .rename(columns={"los_days":          "bed_days_consumed",
                     "home_block_name":   "block",
                     "home_district_code":"district"})
)

a1 = (
    block_static
    .merge(cases_sum,   on=BLK, how="left")
    .merge(distinct_ben, on=BLK, how="left")
    .merge(bed_days,     on=BLK, how="left")
)

a1["overall_utilization_rate"] = safe_div(a1["distinct_beneficiaries_with_cases"],
                                           a1["total_beneficiaries_enrolled"])
a1["cases_per_1000_enrolled"]  = safe_div(a1["total_cases_all_months"],
                                           a1["total_beneficiaries_enrolled"]) * 1000
a1["demand_intensity"]         = safe_div(a1["bed_days_consumed"],
                                           a1["total_beneficiaries_enrolled"])
a1["local_bed_availability"]   = safe_div(a1["total_inpatient_beds"],
                                           a1["total_beneficiaries_enrolled"]) * 1000

# Z-scores
for metric, zcol in [("overall_utilization_rate", "z_utilization_rate"),
                     ("cases_per_1000_enrolled",   "z_cases_per_1000"),
                     ("local_bed_availability",    "z_local_bed_availability")]:
    valid = a1[metric].dropna()
    m, s = valid.mean(), valid.std()
    if pd.isna(s) or s == 0:
        a1[zcol] = 0.0
    else:
        a1[zcol] = (a1[metric] - m) / s

# Flags
enr_median = a1["total_beneficiaries_enrolled"].median()
util_p25   = a1["overall_utilization_rate"].quantile(0.25)
cper1k_p75 = a1["cases_per_1000_enrolled"].quantile(0.75)
bed_p25    = a1["local_bed_availability"].quantile(0.25)

a1["high_enrolment_low_utilization"] = (
    (a1["total_beneficiaries_enrolled"] >= enr_median) &
    (a1["overall_utilization_rate"]     <  util_p25)
)
a1["high_demand_low_local_supply"] = (
    (a1["cases_per_1000_enrolled"] > cper1k_p75) &
    (a1["local_bed_availability"]  < bed_p25)
)
a1["zero_supply"]               = a1["total_hospitals"].isna() | (a1["total_hospitals"] == 0)
a1["single_hospital_dependency"]= a1["total_hospitals"] == 1

out1 = ["block", "district", "division", "total_beneficiaries_enrolled",
        "total_cases_all_months", "distinct_beneficiaries_with_cases",
        "overall_utilization_rate", "cases_per_1000_enrolled",
        "bed_days_consumed", "demand_intensity", "local_bed_availability",
        "total_hospitals", "total_inpatient_beds",
        "z_utilization_rate", "z_cases_per_1000", "z_local_bed_availability",
        "high_enrolment_low_utilization", "high_demand_low_local_supply",
        "zero_supply", "single_hospital_dependency"]
a1 = a1[[c for c in out1 if c in a1.columns]]
save(a1, "gap_utilization_scores.parquet")

print(f"  Blocks: {len(a1)}")
print(f"  high_enrolment_low_utilization: {a1['high_enrolment_low_utilization'].sum()}")
print(f"  high_demand_low_local_supply:   {a1['high_demand_low_local_supply'].sum()}")
print(f"  zero_supply:                    {a1['zero_supply'].sum()}")
print(f"  single_hospital_dependency:     {a1['single_hospital_dependency'].sum()}")
top5 = a1.nlargest(5, "overall_utilization_rate")[["block", "district", "overall_utilization_rate"]]
bot5 = a1.nsmallest(5, "overall_utilization_rate")[["block", "district", "overall_utilization_rate"]]
print(f"  Top 5 utilization:\n{top5.to_string()}")
print(f"  Bottom 5 utilization:\n{bot5.to_string()}")


# ═══════════════════════════════════════════════════════════════════════════════
# ANALYSIS 2: Specialty Gap Matrix
# ═══════════════════════════════════════════════════════════════════════════════
section("ANALYSIS 2 — Specialty Gap Matrix")

a2 = int_sg.copy()

# gap_severity
nz_ratios = a2["demand_supply_ratio"].dropna()
nz_ratios  = nz_ratios[nz_ratios > 0]
under_thresh = nz_ratios.quantile(0.75) if len(nz_ratios) > 0 else np.inf

def _gap_severity(row):
    cd = row["cases_demanding"]
    if pd.isna(cd) or cd == 0:
        return "NO_DEMAND"
    if row["gap_flag"]:
        return "NO_SUPPLY"
    if not pd.isna(row["demand_supply_ratio"]) and row["demand_supply_ratio"] > under_thresh:
        return "UNDERSUPPLIED"
    return "ADEQUATE"

a2["gap_severity"]             = a2.apply(_gap_severity, axis=1)
a2["estimated_revenue_leakage"]= np.where(a2["gap_severity"] == "NO_SUPPLY",
                                           a2["amount_claimed"], np.nan)

# Nearest block with supply in same district (for gap rows)
supply_blocks = (
    a2[a2["hospitals_offering"].fillna(0) > 0][["district", "specialty_code", "block"]]
    .sort_values("block")  # alphabetic — deterministic
)
nearest_supply = (
    supply_blocks.groupby(["district", "specialty_code"])["block"]
    .first().reset_index()
    .rename(columns={"block": "nearest_block_with_supply"})
)
has_supply_in_district = (
    supply_blocks.groupby(["district", "specialty_code"])["block"]
    .count().reset_index()
    .rename(columns={"block": "_cnt"})
)
has_supply_in_district["nearest_block_same_district"] = True

a2 = (
    a2.merge(nearest_supply, on=["district", "specialty_code"], how="left")
      .merge(has_supply_in_district[["district", "specialty_code", "nearest_block_same_district"]],
             on=["district", "specialty_code"], how="left")
)
# Blocks that already have supply: clear nearest_block_with_supply for them
a2.loc[a2["hospitals_offering"].fillna(0) > 0, "nearest_block_with_supply"] = np.nan
a2["nearest_block_same_district"] = a2["nearest_block_same_district"].fillna(False)

out2 = ["block", "district", "division", "specialty_code", "specialty_name",
        "cases_demanding", "unique_patients", "amount_claimed",
        "hospitals_offering", "total_prev_fy_admissions",
        "gap_flag", "demand_supply_ratio", "gap_severity",
        "estimated_revenue_leakage", "nearest_block_with_supply", "nearest_block_same_district"]
a2 = a2[[c for c in out2 if c in a2.columns]]
save(a2, "gap_specialty_matrix.parquet")

print(f"  Total rows: {len(a2)}")
print(f"  NO_SUPPLY:    {(a2['gap_severity'] == 'NO_SUPPLY').sum()}")
print(f"  UNDERSUPPLIED:{(a2['gap_severity'] == 'UNDERSUPPLIED').sum()}")
print(f"  Total leakage: INR {a2['estimated_revenue_leakage'].sum():,.0f}")
top_gaps = (a2[a2["gap_flag"] == True]
            .sort_values("cases_demanding", ascending=False)
            .head(10)[["block", "district", "specialty_code", "cases_demanding"]])
print(f"  Top 10 specialty gaps:\n{top_gaps.to_string()}")


# ═══════════════════════════════════════════════════════════════════════════════
# ANALYSIS 3: Disease Burden Mismatch
# ═══════════════════════════════════════════════════════════════════════════════
section("ANALYSIS 3 — Disease Burden Mismatch")

# Step 3a: classify cases by disease category (home block)
case_disease = (
    cases_df[["case_id", "beneficiary_id", "discharge_type"]]
    .merge(primary_diag[["case_id", "disease_category"]], on="case_id", how="left")
    .merge(ben_df[["beneficiary_id", "household_id"]], on="beneficiary_id", how="left")
    .merge(hh_df[["household_id", "home_block_name",
                   "home_district_code", "home_division_name"]], on="household_id", how="left")
)

block_totals = (
    case_disease.groupby(["home_block_name", "home_district_code"])["case_id"]
    .count().reset_index()
    .rename(columns={"case_id": "block_total_cases",
                     "home_block_name":    "_block",
                     "home_district_code": "_district"})
)

disease_block = (
    case_disease.groupby(
        ["home_block_name", "home_district_code", "home_division_name", "disease_category"],
        dropna=False
    )
    .agg(
        case_count  = ("case_id",        "count"),
        death_count = ("discharge_type", lambda x: (x == "DEATH").sum()),
    )
    .reset_index()
    .rename(columns={"home_block_name":    "block",
                     "home_district_code": "district",
                     "home_division_name": "division"})
)
# Merge totals
disease_block = disease_block.merge(
    block_totals.rename(columns={"_block": "block", "_district": "district"}),
    on=["block", "district"], how="left"
)
disease_block["proportion_of_block_cases"] = safe_div(disease_block["case_count"],
                                                       disease_block["block_total_cases"])
disease_block["category_mortality_rate"]   = safe_div(disease_block["death_count"],
                                                       disease_block["case_count"])

# Step 3b: hospital capability per disease category per block
FACILITY_REQS = {
    "NCD":               ("OR",  "has_icu_with_ac", "has_hdu"),
    "COMMUNICABLE":      ("OR",  "has_general_ward", "has_casualty"),
    "MATERNAL_NEONATAL": ("ONE", "has_labour_room",  None),
    "SURGICAL":          ("ONE", "has_fully_equipped_ot", None),
    "INJURY":            ("AND", "has_casualty", "has_fully_equipped_ot"),
    "OTHER":             ("ONE", "has_general_ward", None),
}

fac_cols = ["hospital_id", "block_name", "district_name",
            "has_icu_with_ac", "has_hdu", "has_general_ward",
            "has_casualty", "has_labour_room", "has_fully_equipped_ot"]
hf = hosp_df[fac_cols].copy()

caps_rows = []
for cat, (op, f1, f2) in FACILITY_REQS.items():
    v1 = hf[f1].fillna(False).astype(bool)
    if op == "OR":
        v2 = hf[f2].fillna(False).astype(bool)
        mask = v1 | v2
    elif op == "AND":
        v2 = hf[f2].fillna(False).astype(bool)
        mask = v1 & v2
    else:
        mask = v1
    sub = hf[mask][["hospital_id", "block_name", "district_name"]].copy()
    sub["disease_category"] = cat
    caps_rows.append(sub)

hosp_caps = pd.concat(caps_rows, ignore_index=True)
block_facility = (
    hosp_caps.groupby(["block_name", "district_name", "disease_category"])["hospital_id"]
    .nunique().reset_index()
    .rename(columns={"hospital_id":  "hospitals_with_required_facilities",
                     "block_name":   "block",
                     "district_name":"district"})
)

a3 = disease_block.merge(block_facility, on=["block", "district", "disease_category"], how="left")
a3["hospitals_with_required_facilities"] = a3["hospitals_with_required_facilities"].fillna(0)
a3["infrastructure_mismatch"] = (
    (a3["case_count"] > 0) & (a3["hospitals_with_required_facilities"] == 0)
)
a3["infrastructure_strain"] = safe_div(a3["case_count"],
                                        a3["hospitals_with_required_facilities"])

out3 = ["block", "district", "division", "disease_category",
        "case_count", "proportion_of_block_cases", "death_count",
        "category_mortality_rate", "hospitals_with_required_facilities",
        "infrastructure_mismatch", "infrastructure_strain"]
a3 = a3[[c for c in out3 if c in a3.columns]]
save(a3, "gap_disease_burden.parquet")

print(f"  Rows: {len(a3)}")
print(f"  Infrastructure mismatches: {a3['infrastructure_mismatch'].sum()}")
print(f"  By category:\n{a3.groupby('disease_category')['infrastructure_mismatch'].sum().to_string()}")


# ═══════════════════════════════════════════════════════════════════════════════
# ANALYSIS 4: Portability Flow Analysis
# ═══════════════════════════════════════════════════════════════════════════════
section("ANALYSIS 4 — Portability Flow Analysis")

# Build case with home and destination
hosp_loc = hosp_df[["hospital_id", "block_name", "district_name", "division_name"]].rename(
    columns={"block_name":    "hosp_block",
             "district_name": "hosp_district",
             "division_name": "hosp_division"}
)

case_flow = (
    cases_df[["case_id", "beneficiary_id", "hospital_id",
               "is_portability", "hospital_district"]]
    .merge(ben_df[["beneficiary_id", "household_id"]], on="beneficiary_id", how="left")
    .merge(hh_df[["household_id", "home_block_name",
                   "home_district_code", "home_division_name"]], on="household_id", how="left")
    .merge(hosp_loc, on="hospital_id", how="left")
    .merge(claims_per_case, on="case_id", how="left")
)

# Resolve destination (portability: use cm_case columns; no block/division available)
case_flow["dest_district"] = case_flow["hosp_district"].copy()
case_flow["dest_block"]    = case_flow["hosp_block"].copy()
case_flow["dest_division"] = case_flow["hosp_division"].copy()
pm = case_flow["is_portability"] == True
case_flow.loc[pm, "dest_district"] = case_flow.loc[pm, "hospital_district"]
case_flow.loc[pm, "dest_block"]    = np.nan
case_flow.loc[pm, "dest_division"] = np.nan

# Classify each case
def _classify_flow(row):
    if row["is_portability"]:
        return "OUT_OF_STATE"
    hb = row["home_block_name"];   hd = row["home_district_code"]; hdv = row["home_division_name"]
    db = row["dest_block"];        dd = row["dest_district"];       ddv = row["dest_division"]
    if pd.isna(dd):
        return "UNKNOWN"
    if hb == db and hd == dd:
        return "SAME_BLOCK"
    if hd == dd:
        return "SAME_DISTRICT_DIFF_BLOCK"
    if not pd.isna(hdv) and hdv == ddv:
        return "DIFF_DISTRICT_SAME_DIVISION"
    return "DIFF_DIVISION"

case_flow["flow_category"] = case_flow.apply(_classify_flow, axis=1)

# Block-level retention / leakage
block_flow = (
    case_flow.groupby(["home_block_name", "home_district_code", "home_division_name"])
    .agg(
        total_cases         = ("case_id",        "count"),
        cases_same_block    = ("flow_category",  lambda x: (x == "SAME_BLOCK").sum()),
        cases_same_district = ("flow_category",  lambda x: (x == "SAME_DISTRICT_DIFF_BLOCK").sum()),
        cases_diff_district = ("flow_category",
                               lambda x: x.isin(["DIFF_DISTRICT_SAME_DIVISION","DIFF_DIVISION"]).sum()),
        cases_out_of_state  = ("flow_category",  lambda x: (x == "OUT_OF_STATE").sum()),
    )
    .reset_index()
    .rename(columns={"home_block_name":    "block",
                     "home_district_code": "district",
                     "home_division_name": "division"})
)
block_flow["local_retention_rate"] = safe_div(
    block_flow["cases_same_block"] + block_flow["cases_same_district"],
    block_flow["total_cases"]
)
block_flow["leakage_rate"] = safe_div(
    block_flow["cases_diff_district"] + block_flow["cases_out_of_state"],
    block_flow["total_cases"]
)
save(block_flow, "gap_portability_flows.parquet")

# District-to-district flow matrix
district_flow = (
    case_flow.groupby(["home_district_code", "dest_district"])
    .agg(
        flow_count          = ("case_id",               "count"),
        flow_amount_claimed = ("total_amount_claimed",  "sum"),
    )
    .reset_index()
    .rename(columns={"home_district_code": "origin_district",
                     "dest_district":      "destination_district"})
)

# Net flow per district
cross = case_flow[case_flow["home_district_code"] != case_flow["dest_district"]]
exported = (cross.groupby("home_district_code")["case_id"].count()
               .reset_index().rename(columns={"case_id": "cases_exported",
                                              "home_district_code": "district"}))
imported = (cross.groupby("dest_district")["case_id"].count()
               .reset_index().rename(columns={"case_id": "cases_imported",
                                              "dest_district": "district"}))
net_flow = (exported.merge(imported, on="district", how="outer").fillna(0))
net_flow["net_flow"] = net_flow["cases_imported"] - net_flow["cases_exported"]

district_flow = district_flow.merge(
    net_flow[["district", "net_flow"]].rename(columns={"district": "origin_district"}),
    on="origin_district", how="left"
)
save(district_flow, "gap_district_patient_flows.parquet")

print(f"  Block flow rows: {len(block_flow)}")
print(f"  Flow distribution:\n{case_flow['flow_category'].value_counts().to_string()}")
print(f"  District flow matrix rows: {len(district_flow)}")
print(f"  Top 5 leakage blocks:\n{block_flow.nlargest(5,'leakage_rate')[['block','district','leakage_rate']].to_string()}")


# ═══════════════════════════════════════════════════════════════════════════════
# ANALYSIS 5: Enrolment-to-Card Drop-off
# ═══════════════════════════════════════════════════════════════════════════════
section("ANALYSIS 5 — Enrolment-to-Card Drop-off")

# Card status per beneficiary
card_status = (
    card_df.groupby("beneficiary_id")
    .agg(
        has_card        = ("card_id",     lambda x: len(x) > 0),
        has_active_card = ("card_status", lambda x: "ACTIVE" in x.values),
    )
    .reset_index()
)
card_status["card_inactive_or_disabled"] = card_status["has_card"] & ~card_status["has_active_card"]

# Enrolment: any rejection & pending status
enrol_rejected = (
    enrol_df.groupby("beneficiary_id")["status"]
    .apply(lambda x: "REJECTED" in x.values)
    .reset_index()
    .rename(columns={"status": "enrolment_rejected"})
)

TERMINAL = {"AUTO_APPROVED", "ISA_APPROVED", "SHA_APPROVED", "REJECTED"}
latest_enrol = (
    enrol_df.sort_values("submitted_at", ascending=False)
    .drop_duplicates(subset=["beneficiary_id"], keep="first")
    [["beneficiary_id", "status"]]
)
latest_enrol["enrolment_pending"] = ~latest_enrol["status"].isin(TERMINAL)

# Join all
ben_full = (
    ben_df[["beneficiary_id", "household_id"]]
    .merge(hh_df[["household_id", "home_block_name",
                   "home_district_code", "home_division_name"]], on="household_id", how="left")
    .merge(card_status,    on="beneficiary_id", how="left")
    .merge(enrol_rejected, on="beneficiary_id", how="left")
    .merge(latest_enrol[["beneficiary_id", "enrolment_pending"]],
           on="beneficiary_id", how="left")
)
ben_full["has_card"]                  = ben_full["has_card"].fillna(False)
ben_full["has_active_card"]           = ben_full["has_active_card"].fillna(False)
ben_full["card_inactive_or_disabled"] = ben_full["card_inactive_or_disabled"].fillna(False)
ben_full["enrolment_rejected"]        = ben_full["enrolment_rejected"].fillna(False)
ben_full["enrolment_pending"]         = ben_full["enrolment_pending"].fillna(False)

a5 = (
    ben_full.groupby(["home_block_name", "home_district_code", "home_division_name"])
    .agg(
        total_beneficiaries            = ("beneficiary_id",           "count"),
        beneficiaries_with_active_card = ("has_active_card",          "sum"),
        beneficiaries_no_card          = ("has_card",                 lambda x: (~x).sum()),
        beneficiaries_inactive_card    = ("card_inactive_or_disabled","sum"),
        enrolment_rejected_count       = ("enrolment_rejected",       "sum"),
    )
    .reset_index()
    .rename(columns={"home_block_name":    "block",
                     "home_district_code": "district",
                     "home_division_name": "division"})
)
a5["card_activation_rate"]     = safe_div(a5["beneficiaries_with_active_card"],
                                           a5["total_beneficiaries"])
a5["enrolment_rejection_rate"] = safe_div(a5["enrolment_rejected_count"],
                                           a5["total_beneficiaries"])
a5["drop_off_rate"]            = 1 - a5["card_activation_rate"]

a5["high_drop_off"]  = a5["drop_off_rate"] > a5["drop_off_rate"].quantile(0.75)
a5["high_rejection"] = a5["enrolment_rejection_rate"] > a5["enrolment_rejection_rate"].quantile(0.75)

save(a5, "gap_card_dropoff.parquet")
print(f"  Rows: {len(a5)}")
print(f"  high_drop_off: {a5['high_drop_off'].sum()}")
print(f"  high_rejection: {a5['high_rejection'].sum()}")
overall_act = a5["beneficiaries_with_active_card"].sum() / a5["total_beneficiaries"].sum()
print(f"  State-wide card activation rate: {overall_act:.3f}")


# ═══════════════════════════════════════════════════════════════════════════════
# ANALYSIS 6: Repeat Utilization
# ═══════════════════════════════════════════════════════════════════════════════
section("ANALYSIS 6 — Repeat Utilization")

# Primary procedure per case
case_proc = (
    cases_df[["case_id", "beneficiary_id", "hospital_id", "admission_datetime"]]
    .merge(active_preauth[["case_id", "preauth_id"]],   on="case_id",   how="left")
    .merge(primary_proc_lines,                           on="preauth_id", how="left")
)
case_proc["admission_datetime"] = pd.to_datetime(case_proc["admission_datetime"], utc=True)
case_proc = case_proc.sort_values(["beneficiary_id", "admission_datetime"])

# Build per-beneficiary admission pair patterns
records = []
for ben_id, grp in case_proc.groupby("beneficiary_id"):
    grp   = grp.reset_index(drop=True)
    n     = len(grp)
    spsh  = 0  # same_proc_same_hosp
    spdh  = 0  # same_proc_diff_hosp
    dp    = 0  # diff_proc
    for i in range(1, n):
        pp = grp.loc[i-1, "hbp_procedure_code"]
        cp = grp.loc[i,   "hbp_procedure_code"]
        ph = grp.loc[i-1, "hospital_id"]
        ch = grp.loc[i,   "hospital_id"]
        if pd.isna(cp) or pd.isna(pp):
            dp += 1
        elif cp == pp and ch == ph:
            spsh += 1
        elif cp == pp:
            spdh += 1
        else:
            dp += 1
    counts = {"SAME_PROCEDURE_SAME_HOSPITAL": spsh,
              "SAME_PROCEDURE_DIFF_HOSPITAL":  spdh,
              "DIFF_PROCEDURE":                dp}
    records.append({
        "beneficiary_id":            ben_id,
        "total_admissions":          n,
        "is_repeat":                 n > 1,
        "same_proc_same_hosp_pairs": spsh,
        "same_proc_diff_hosp_pairs": spdh,
        "diff_proc_pairs":           dp,
        "total_pairs":               spsh + spdh + dp,
        "dominant_pattern":          max(counts, key=counts.get) if n > 1 else None,
    })

ben_repeat = pd.DataFrame(records)

# Join to block
ben_repeat_hh = (
    ben_repeat
    .merge(ben_df[["beneficiary_id", "household_id"]], on="beneficiary_id", how="left")
    .merge(hh_df[["household_id", "home_block_name",
                   "home_district_code", "home_division_name"]], on="household_id", how="left")
)

a6 = (
    ben_repeat_hh.groupby(["home_block_name", "home_district_code", "home_division_name"])
    .agg(
        total_beneficiaries_with_cases  = ("beneficiary_id",            "nunique"),
        repeat_beneficiaries            = ("is_repeat",                 "sum"),
        avg_admissions_per_patient      = ("total_admissions",          "mean"),
        same_proc_same_hosp_pairs_total = ("same_proc_same_hosp_pairs", "sum"),
        same_proc_diff_hosp_pairs_total = ("same_proc_diff_hosp_pairs", "sum"),
        diff_proc_pairs_total           = ("diff_proc_pairs",           "sum"),
    )
    .reset_index()
    .rename(columns={"home_block_name":    "block",
                     "home_district_code": "district",
                     "home_division_name": "division"})
)
a6["repeat_rate"] = safe_div(a6["repeat_beneficiaries"],
                              a6["total_beneficiaries_with_cases"])
total_pairs = (a6["same_proc_same_hosp_pairs_total"] +
               a6["same_proc_diff_hosp_pairs_total"] +
               a6["diff_proc_pairs_total"])
a6["possible_treatment_failure_rate"] = safe_div(a6["same_proc_same_hosp_pairs_total"],
                                                   total_pairs)
a6["high_repeat_rate"]           = a6["repeat_rate"] > a6["repeat_rate"].quantile(0.75)
a6["possible_treatment_failure"] = (
    (a6["possible_treatment_failure_rate"] > 0.5) &
    (a6["repeat_beneficiaries"] >= 5)
)
save(a6, "gap_repeat_utilization.parquet")

print(f"  Rows: {len(a6)}")
print(f"  high_repeat_rate: {a6['high_repeat_rate'].sum()}")
print(f"  possible_treatment_failure: {a6['possible_treatment_failure'].sum()}")
print(f"  State-wide repeat rate: {ben_repeat['is_repeat'].mean():.3f}")


# ═══════════════════════════════════════════════════════════════════════════════
# ANALYSIS 7: Seasonal Demand Patterns
# ═══════════════════════════════════════════════════════════════════════════════
section("ANALYSIS 7 — Seasonal Demand Patterns")

ds_monthly = int_ds[["block", "district", "division", "month", "total_cases"]].copy()
ds_monthly["total_cases"] = ds_monthly["total_cases"].fillna(0)

# Per-block stats
block_stats = (
    ds_monthly.groupby(BLK)
    .agg(
        total_cases_sum = ("total_cases", "sum"),
        nonzero_months  = ("total_cases", lambda x: (x > 0).sum()),
        mean_cases      = ("total_cases", "mean"),
        std_cases       = ("total_cases", "std"),
    )
    .reset_index()
)
block_stats["meets_threshold"] = (
    (block_stats["total_cases_sum"] >= 12) &
    (block_stats["nonzero_months"]  >= 6)
)
block_stats["seasonality_index"] = np.where(
    block_stats["meets_threshold"] & (block_stats["mean_cases"] > 0),
    block_stats["std_cases"] / block_stats["mean_cases"],
    np.nan
)

# Peak-to-trough ratio
def _peak_trough(group):
    nz = group["total_cases"][group["total_cases"] > 0]
    return nz.max() / nz.min() if len(nz) >= 2 else np.nan

ptr = (
    ds_monthly.groupby(BLK)
    .apply(_peak_trough, include_groups=False)
    .reset_index().rename(columns={0: "peak_to_trough_ratio"})
)
ptr = ptr.merge(block_stats[BLK + ["meets_threshold"]], on=BLK, how="left")
ptr.loc[~ptr["meets_threshold"], "peak_to_trough_ratio"] = np.nan
block_stats = block_stats.merge(ptr[BLK + ["peak_to_trough_ratio"]], on=BLK, how="left")

# Z-scores per block-month
bm = ds_monthly.merge(
    block_stats[BLK + ["mean_cases", "std_cases", "meets_threshold"]], on=BLK, how="left"
)
bm["z_score_monthly"] = np.where(
    bm["meets_threshold"] & (bm["std_cases"] > 0),
    (bm["total_cases"] - bm["mean_cases"]) / bm["std_cases"],
    np.nan
)
bm["surge_month"] = bm["z_score_monthly"] > 1.5

# Disease category in surge months
case_disease_monthly = (
    cases_df[["case_id", "beneficiary_id", "admission_month"]]
    .merge(primary_diag[["case_id", "disease_category"]], on="case_id", how="left")
    .merge(ben_df[["beneficiary_id", "household_id"]], on="beneficiary_id", how="left")
    .merge(hh_df[["household_id", "home_block_name", "home_district_code"]],
           on="household_id", how="left")
)

surge_idx = bm[bm["surge_month"] == True][BLK + ["month"]].copy()
surge_cases = surge_idx.rename(columns={"block": "home_block_name",
                                         "district": "home_district_code",
                                         "month": "admission_month"}) \
    .merge(case_disease_monthly,
           on=["home_block_name", "home_district_code", "admission_month"], how="left")

# Dominant disease per surge block-month
surge_dom = (
    surge_cases.groupby(["home_block_name", "home_district_code",
                          "admission_month", "disease_category"])["case_id"]
    .count().reset_index()
    .sort_values("case_id", ascending=False)
    .drop_duplicates(subset=["home_block_name", "home_district_code", "admission_month"])
    .rename(columns={"home_block_name":   "block",
                     "home_district_code":"district",
                     "admission_month":   "month",
                     "disease_category":  "surge_dominant_disease"})
    [["block", "district", "month", "surge_dominant_disease"]]
)

seasonal_patterns = (
    bm[["block", "district", "division", "month",
        "total_cases", "z_score_monthly", "surge_month"]]
    .merge(surge_dom, on=["block", "district", "month"], how="left")
)
save(seasonal_patterns, "gap_seasonal_patterns.parquet")

# Seasonal summary per block
surge_only = bm[bm["surge_month"] == True].copy()
surge_only["cal_month"] = surge_only["month"].str[5:7].astype(int)

peak_months_lkp = (
    surge_only.groupby(BLK)["cal_month"]
    .apply(lambda x: ",".join(str(m) for m in sorted(x.unique())))
    .reset_index().rename(columns={"cal_month": "peak_months"})
)

peak_disease_lkp = (
    surge_cases.rename(columns={"home_block_name":   "block",
                                 "home_district_code":"district",
                                 "admission_month":   "month"})
    .groupby(["block", "district", "disease_category"])["case_id"]
    .count().reset_index()
    .sort_values("case_id", ascending=False)
    .drop_duplicates(subset=BLK)
    .rename(columns={"disease_category": "peak_disease_category"})
    [BLK + ["peak_disease_category"]]
)

all_blocks_div = int_ds[["block", "district", "division"]].drop_duplicates()
seasonal_summary = (
    all_blocks_div
    .merge(block_stats[BLK + ["meets_threshold", "seasonality_index", "peak_to_trough_ratio"]],
           on=BLK, how="left")
    .merge(peak_months_lkp, on=BLK, how="left")
    .merge(peak_disease_lkp, on=BLK, how="left")
)
seasonal_summary["is_seasonal"] = (
    seasonal_summary["meets_threshold"].fillna(False) &
    seasonal_summary["peak_months"].notna()
)
# Null out metrics for below-threshold blocks
below = ~seasonal_summary["meets_threshold"].fillna(False)
seasonal_summary.loc[below, ["seasonality_index", "peak_to_trough_ratio"]] = np.nan
not_seasonal = ~seasonal_summary["is_seasonal"]
seasonal_summary.loc[not_seasonal, ["peak_months", "peak_disease_category"]] = np.nan

save(seasonal_summary, "gap_seasonal_summary.parquet")

print(f"  Seasonal patterns rows: {len(seasonal_patterns)}")
print(f"  Blocks meeting threshold: {block_stats['meets_threshold'].sum()}")
print(f"  Seasonal blocks (with surges): {seasonal_summary['is_seasonal'].sum()}")
print(f"  Most common peak months: {surge_only['cal_month'].value_counts().head(3).to_string()}")


# ═══════════════════════════════════════════════════════════════════════════════
# ANALYSIS 8: Delisted Hospital Impact
# ═══════════════════════════════════════════════════════════════════════════════
section("ANALYSIS 8 — Delisted Hospital Impact")

delisted = hosp_df[hosp_df["delisted_from_gov_schemes"] == True].copy()
print(f"  Delisted hospitals found: {len(delisted)}")

if len(delisted) == 0:
    a8 = pd.DataFrame(columns=["hospital_id", "hospital_name", "block", "district", "division",
                                "delisted_beds", "block_total_beds", "block_remaining_beds",
                                "bed_share_lost", "delisted_specialties", "sole_provider_delisted",
                                "majority_capacity_lost", "specialties_lost",
                                "block_total_cases", "block_cases_per_remaining_bed"])
else:
    # Block-level totals (ALL hospitals including delisted)
    block_beds_all = (
        hosp_df.groupby(["block_name", "district_name"])
        .agg(block_total_beds     = ("inpatient_beds", "sum"),
             block_total_hospitals= ("hospital_id",    "count"))
        .reset_index()
        .rename(columns={"block_name": "block", "district_name": "district"})
    )

    # Specialties per delisted hospital
    delisted_specs = (
        spec_df.merge(delisted[["hospital_id"]], on="hospital_id", how="inner")
        .groupby("hospital_id")["specialty_code"]
        .apply(lambda x: ",".join(sorted(x.unique())))
        .reset_index().rename(columns={"specialty_code": "delisted_specialties"})
    )

    # Non-delisted hospitals' specialties per block
    non_del = hosp_df[~hosp_df["delisted_from_gov_schemes"].fillna(False)][
        ["hospital_id", "block_name", "district_name"]
    ]
    nondel_spec = spec_df.merge(non_del, on="hospital_id", how="inner")
    nondel_by_block = (
        nondel_spec.groupby(["block_name", "district_name"])["specialty_code"]
        .apply(set).reset_index()
        .rename(columns={"specialty_code": "nondel_specs_in_block"})
    )

    a8 = (
        delisted[["hospital_id", "hospital_name", "block_name", "district_name",
                   "division_name", "inpatient_beds"]]
        .rename(columns={"block_name":    "block",
                         "district_name": "district",
                         "division_name": "division",
                         "inpatient_beds":"delisted_beds"})
        .merge(block_beds_all, on=["block", "district"], how="left")
        .merge(delisted_specs, on="hospital_id", how="left")
        .merge(nondel_by_block.rename(columns={"block_name":    "block",
                                                "district_name": "district"}),
               on=["block", "district"], how="left")
    )

    a8["bed_share_lost"]        = safe_div(a8["delisted_beds"], a8["block_total_beds"])
    a8["block_remaining_beds"]  = a8["block_total_beds"] - a8["delisted_beds"]
    a8["sole_provider_delisted"]= a8["block_total_hospitals"] == 1
    a8["majority_capacity_lost"]= a8["bed_share_lost"] > 0.5

    def _lost_specs(row):
        specs_str = row["delisted_specialties"]
        nondel    = row["nondel_specs_in_block"]
        if pd.isna(specs_str):
            return ""
        specs = set(specs_str.split(","))
        available = nondel if isinstance(nondel, set) else set()
        return ",".join(sorted(specs - available))

    a8["specialties_lost"] = a8.apply(_lost_specs, axis=1)
    a8["specialty_lost"]   = a8["specialties_lost"] != ""

    # Block case totals from Analysis 1
    a8 = a8.merge(
        a1[["block", "district", "total_cases_all_months"]].rename(
            columns={"total_cases_all_months": "block_total_cases"}),
        on=["block", "district"], how="left"
    )
    a8["block_cases_per_remaining_bed"] = safe_div(a8["block_total_cases"],
                                                    a8["block_remaining_beds"])
    a8 = a8.drop(columns=["block_total_hospitals", "nondel_specs_in_block"],
                 errors="ignore")

save(a8, "gap_delisted_impact.parquet")
if len(a8) > 0:
    print(f"  sole_provider_delisted:  {a8['sole_provider_delisted'].sum()}")
    print(f"  majority_capacity_lost:  {a8['majority_capacity_lost'].sum()}")
    print(f"  with specialties_lost:   {(a8['specialties_lost'] != '').sum()}")


# ═══════════════════════════════════════════════════════════════════════════════
# SUMMARY
# ═══════════════════════════════════════════════════════════════════════════════
section("SUMMARY")

output_shapes = {
    "gap_utilization_scores":     a1,
    "gap_specialty_matrix":       a2,
    "gap_disease_burden":         a3,
    "gap_portability_flows":      block_flow,
    "gap_district_patient_flows": district_flow,
    "gap_card_dropoff":           a5,
    "gap_repeat_utilization":     a6,
    "gap_seasonal_patterns":      seasonal_patterns,
    "gap_seasonal_summary":       seasonal_summary,
    "gap_delisted_impact":        a8,
}

lines = ["# Phase 2 Product 1 Summary\n", "## Files Created\n"]
for name, df in output_shapes.items():
    lines.append(f"- `analytics/{name}.parquet` — {df.shape[0]:,} rows x {df.shape[1]} cols")

lines.append("\n## Key Findings\n")

# Top 10 gap blocks
top_gap = a1[a1["high_enrolment_low_utilization"]].nlargest(10, "total_beneficiaries_enrolled")
lines.append("### Top 10 High-Enrolment Low-Utilization Blocks")
for _, r in top_gap.iterrows():
    lines.append(f"- {r['block']}, {r['district']}: "
                 f"{int(r['total_beneficiaries_enrolled'])} enrolled, "
                 f"{r['overall_utilization_rate']:.3f} utilization")

# Most common specialty gaps
top_spec = (a2[a2["gap_flag"] == True]
            .groupby("specialty_code")["cases_demanding"]
            .sum().sort_values(ascending=False).head(5))
lines.append("\n### Top 5 Specialty Gaps (no local supply)")
for spec, cnt in top_spec.items():
    lines.append(f"- {spec}: {int(cnt)} unmet cases")

# Largest flows
top_fl = district_flow.nlargest(5, "flow_count")
lines.append("\n### Top 5 District-to-District Patient Flows")
for _, r in top_fl.iterrows():
    lines.append(f"- {r['origin_district']} -> {r['destination_district']}: {int(r['flow_count'])} cases")

lines.append("\n## Assumptions\n")
lines.append("- ICD-10 classification: first-match prefix logic; order: NCD > COMMUNICABLE > MATERNAL > SURGICAL > INJURY > OTHER.")
lines.append("- Portability destinations use cm_case.hospital_district (no block/division).")
lines.append("- Seasonality threshold: >= 12 total cases AND >= 6 non-zero months per block.")
lines.append("- Treatment failure flag: >= 5 repeat beneficiaries AND > 50% same-proc-same-hosp pairs.")
lines.append("- Revenue leakage = amount_claimed on NO_SUPPLY rows only.")
lines.append("- 'Nearest block with supply': alphabetically first block in same district offering that specialty.")
lines.append("- Lost specialties = specialties only offered by the delisted hospital in that block (no other hospital offers it).")

summary = "\n".join(lines)
summary_path = SCRIPT_DIR.parent / "phase2_product1_summary.md"
summary_path.write_text(summary, encoding="utf-8")
print(f"\n  Summary written to: {summary_path}")
print(summary)
print("\n[DONE] Phase 2 Product 1 complete.")
