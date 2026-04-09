"""
Phase 2b — Analytical Engine: Product 2 (Hospital Performance Benchmarking)
Produces 7 analytics parquet files: summary table + 5 analyses + scorecard.
"""

import sys
import pandas as pd
import numpy as np
from pathlib import Path
from scipy.stats import percentileofscore

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

def safe_div(num, den):
    return np.where((pd.isna(den)) | (den == 0), np.nan, num / den)

def w_avg(df, val_col, weight_col):
    """Weighted average, safe for zero/null weights."""
    v = df[val_col] * df[weight_col]
    w = df[weight_col]
    return safe_div(v.sum(), w.sum())

def save(df, name):
    path = OUT_DIR / name
    df.to_parquet(path, index=False)
    print(f"  -> {path}  shape={df.shape}")


# ─── Load ─────────────────────────────────────────────────────────────────────
section("Loading inputs")
int_hp = pd.read_parquet(INT_DIR / "int_hospital_performance.parquet")
print(f"  int_hospital_performance: {int_hp.shape}")


# ═══════════════════════════════════════════════════════════════════════════════
# STEP 0: Hospital-Procedure Summary Table
# ═══════════════════════════════════════════════════════════════════════════════
section("STEP 0 — Hospital-Procedure Summary")

GRP = ["hospital_id", "hbp_procedure_code"]

# Static columns: take first value per group
static_cols = ["hospital_name", "hospital_type", "hospital_sub_type",
               "block", "district", "division", "capacity_band",
               "procedure_name", "specialty_code", "specialty_name", "base_package_price"]
static = int_hp.groupby(GRP, dropna=False)[static_cols].first().reset_index()

# Weighted-average helper columns
int_hp["_w_los"]          = int_hp["avg_los_days"]           * int_hp["case_count"]
int_hp["_w_appr_rate"]    = int_hp["claim_approval_rate"]    * int_hp["case_count"]
int_hp["_w_rej_rate"]     = int_hp["claim_rejection_rate"]   * int_hp["case_count"]
int_hp["_w_qry_rate"]     = int_hp["claim_query_rate"]       * int_hp["case_count"]
int_hp["_w_qry_cnt"]      = int_hp["avg_query_count"]        * int_hp["case_count"]
int_hp["_w_norm_disc"]    = int_hp["normal_discharge_rate"]   * int_hp["case_count"]
int_hp["_w_lama"]         = int_hp["lama_dama_rate"]          * int_hp["case_count"]
int_hp["_w_tat"]          = int_hp["avg_settlement_tat_days"] * int_hp["case_count"]
int_hp["_w_preauth_auto"] = int_hp["preauth_auto_approval_rate"] * int_hp["case_count"]
int_hp["_w_bio"]          = int_hp["biometric_auth_rate"]     * int_hp["case_count"]
int_hp["_w_med"]          = int_hp["medicines_provided_rate"] * int_hp["case_count"]

agg = int_hp.groupby(GRP, dropna=False).agg(
    total_cases           = ("case_count",            "sum"),
    active_months         = ("case_count",            lambda x: (x > 0).sum()),
    first_month           = ("month",                 "min"),
    last_month            = ("month",                 "max"),
    total_amount_claimed  = ("total_amount_claimed",  "sum"),
    total_amount_approved = ("total_amount_approved",  "sum"),
    _sum_w_los            = ("_w_los",                "sum"),
    _sum_w_appr           = ("_w_appr_rate",          "sum"),
    _sum_w_rej            = ("_w_rej_rate",           "sum"),
    _sum_w_qry            = ("_w_qry_rate",           "sum"),
    _sum_w_qcnt           = ("_w_qry_cnt",            "sum"),
    _sum_w_norm           = ("_w_norm_disc",          "sum"),
    _sum_w_lama           = ("_w_lama",               "sum"),
    _sum_w_tat            = ("_w_tat",                "sum"),
    _sum_w_pa             = ("_w_preauth_auto",       "sum"),
    _sum_w_bio            = ("_w_bio",                "sum"),
    _sum_w_med            = ("_w_med",                "sum"),
).reset_index()

summary = static.merge(agg, on=GRP, how="inner")

tc = summary["total_cases"]
summary["avg_los_days"]               = safe_div(summary["_sum_w_los"],  tc)
summary["avg_amount_claimed"]         = safe_div(summary["total_amount_claimed"], tc)
summary["avg_amount_approved"]        = safe_div(summary["total_amount_approved"], tc)
summary["avg_approval_ratio"]         = safe_div(summary["total_amount_approved"],
                                                  summary["total_amount_claimed"])
summary["claim_approval_rate"]        = safe_div(summary["_sum_w_appr"], tc)
summary["claim_rejection_rate"]       = safe_div(summary["_sum_w_rej"],  tc)
summary["claim_query_rate"]           = safe_div(summary["_sum_w_qry"],  tc)
summary["avg_query_count"]            = safe_div(summary["_sum_w_qcnt"], tc)
summary["normal_discharge_rate"]      = safe_div(summary["_sum_w_norm"], tc)
summary["lama_dama_rate"]             = safe_div(summary["_sum_w_lama"], tc)
summary["avg_settlement_tat_days"]    = safe_div(summary["_sum_w_tat"],  tc)
summary["preauth_auto_approval_rate"] = safe_div(summary["_sum_w_pa"],   tc)
summary["biometric_auth_rate"]        = safe_div(summary["_sum_w_bio"],  tc)
summary["medicines_provided_rate"]    = safe_div(summary["_sum_w_med"],  tc)

# Drop temp columns
summary.drop(columns=[c for c in summary.columns if c.startswith("_sum_w_")], inplace=True)

# Filter: minimum 5 cases
before = len(summary)
summary = summary[summary["total_cases"] >= 5].reset_index(drop=True)
print(f"  Rows before filter: {before}  |  after (>=5 cases): {len(summary)}")

save(summary, "bench_hospital_procedure_summary.parquet")
print(f"  Hospitals: {summary['hospital_id'].nunique()}")
print(f"  Procedures: {summary['hbp_procedure_code'].nunique()}")


# ─── Peer group utility ──────────────────────────────────────────────────────
PEER = ["hbp_procedure_code", "hospital_type"]

def add_peer_stats(df, metric, prefix):
    """Add peer group mean, median, std, p25, p75, count for a metric."""
    peer = (
        df.groupby(PEER)[metric]
        .agg(["mean", "median", "std",
              lambda x: x.quantile(0.25),
              lambda x: x.quantile(0.75),
              "count"])
        .reset_index()
    )
    peer.columns = PEER + [f"{prefix}_avg", f"{prefix}_median", f"{prefix}_std",
                           f"{prefix}_p25", f"{prefix}_p75", "peer_hospital_count"]
    df = df.merge(peer, on=PEER, how="left", suffixes=("", "_peer"))
    # Small peer group flag
    if "small_peer_group" not in df.columns:
        df["small_peer_group"] = df["peer_hospital_count"] < 3
    else:
        df["small_peer_group"] = df["small_peer_group"] | (df["peer_hospital_count"] < 3)
    return df

def peer_z(df, metric, peer_avg, peer_std):
    """Z-score within peer group, 0 if std=0."""
    return np.where(
        pd.isna(df[peer_std]) | (df[peer_std] == 0),
        0.0,
        (df[metric] - df[peer_avg]) / df[peer_std]
    )

def peer_pctile(df, metric, peer_key=PEER):
    """Percentile rank within peer group."""
    def _pct(group):
        vals = group[metric].values
        return group[metric].apply(lambda v: percentileofscore(vals, v, kind="rank"))
    return df.groupby(peer_key, group_keys=False).apply(_pct)


# ═══════════════════════════════════════════════════════════════════════════════
# ANALYSIS 1: Cost Benchmarking
# ═══════════════════════════════════════════════════════════════════════════════
section("ANALYSIS 1 — Cost Benchmarking")

a1 = summary.copy()
a1 = add_peer_stats(a1, "avg_amount_claimed", "peer_cost")

a1["cost_z_score"]        = peer_z(a1, "avg_amount_claimed", "peer_cost_avg", "peer_cost_std")
a1["cost_vs_package"]     = safe_div(a1["avg_amount_claimed"], a1["base_package_price"])
a1["cost_percentile_rank"]= peer_pctile(a1, "avg_amount_claimed")
a1["approval_gap"]        = a1["avg_amount_claimed"] - a1["avg_amount_approved"]
a1["approval_gap_rate"]   = 1 - a1["avg_approval_ratio"]

a1["high_cost_outlier"]   = a1["cost_z_score"] > 1.5
a1["low_cost_outlier"]    = a1["cost_z_score"] < -1.5
a1["high_approval_gap"]   = a1["approval_gap_rate"] > 0.2
a1["above_package_rate"]  = a1["cost_vs_package"] > 1.3

out1 = ["hospital_id", "hospital_name", "hospital_type", "hospital_sub_type",
        "block", "district", "division", "hbp_procedure_code", "procedure_name",
        "specialty_code", "base_package_price", "total_cases",
        "avg_amount_claimed", "avg_amount_approved", "avg_approval_ratio",
        "peer_cost_avg", "peer_cost_median", "peer_cost_p25", "peer_cost_p75",
        "peer_hospital_count", "cost_z_score", "cost_vs_package",
        "cost_percentile_rank", "approval_gap", "approval_gap_rate",
        "high_cost_outlier", "low_cost_outlier", "high_approval_gap",
        "above_package_rate", "small_peer_group"]
a1 = a1[[c for c in out1 if c in a1.columns]]
save(a1, "bench_cost.parquet")

print(f"  high_cost_outlier:  {a1['high_cost_outlier'].sum()}")
print(f"  low_cost_outlier:   {a1['low_cost_outlier'].sum()}")
print(f"  high_approval_gap:  {a1['high_approval_gap'].sum()}")
print(f"  above_package_rate: {a1['above_package_rate'].sum()}")
top5 = a1.nlargest(5, "cost_z_score")[["hospital_name","district","procedure_name","cost_z_score","total_cases"]]
print(f"  Top 5 cost outliers:\n{top5.to_string()}")


# ═══════════════════════════════════════════════════════════════════════════════
# ANALYSIS 2: Length of Stay Benchmarking
# ═══════════════════════════════════════════════════════════════════════════════
section("ANALYSIS 2 — LOS Benchmarking")

a2 = summary.copy()
a2 = add_peer_stats(a2, "avg_los_days", "peer_los")

a2["los_z_score"]         = peer_z(a2, "avg_los_days", "peer_los_avg", "peer_los_std")
a2["los_percentile_rank"] = peer_pctile(a2, "avg_los_days")
a2["los_vs_peer_median"]  = safe_div(a2["avg_los_days"], a2["peer_los_median"])

a2["long_stay_outlier"]   = a2["los_z_score"] > 1.5
a2["short_stay_outlier"]  = a2["los_z_score"] < -1.5

out2 = ["hospital_id", "hospital_name", "hospital_type",
        "hbp_procedure_code", "procedure_name", "total_cases",
        "avg_los_days", "peer_los_avg", "peer_los_median",
        "peer_los_p25", "peer_los_p75",
        "los_z_score", "los_percentile_rank", "los_vs_peer_median",
        "long_stay_outlier", "short_stay_outlier", "small_peer_group"]
a2 = a2[[c for c in out2 if c in a2.columns]]
save(a2, "bench_los.parquet")

print(f"  long_stay_outlier:  {a2['long_stay_outlier'].sum()}")
print(f"  short_stay_outlier: {a2['short_stay_outlier'].sum()}")
top5 = a2.nlargest(5, "los_z_score")[["hospital_name","procedure_name","los_z_score","avg_los_days"]]
print(f"  Top 5 long-stay outliers:\n{top5.to_string()}")


# ═══════════════════════════════════════════════════════════════════════════════
# ANALYSIS 3: Patient Outcome Benchmarking (LAMA/DAMA)
# ═══════════════════════════════════════════════════════════════════════════════
section("ANALYSIS 3 — LAMA/DAMA Outcomes")

a3 = summary.copy()

# Peer stats for lama_dama_rate
peer_lama = (
    a3.groupby(PEER)["lama_dama_rate"]
    .agg(["mean", "std"]).reset_index()
    .rename(columns={"mean": "peer_avg_lama_dama_rate", "std": "peer_std_lama_dama_rate"})
)
peer_norm = (
    a3.groupby(PEER)["normal_discharge_rate"]
    .mean().reset_index()
    .rename(columns={"normal_discharge_rate": "peer_avg_normal_discharge_rate"})
)
a3 = a3.merge(peer_lama, on=PEER, how="left").merge(peer_norm, on=PEER, how="left")

# Sparsity guard: skip z-score if peer avg < 1%
sparse = a3["peer_avg_lama_dama_rate"] < 0.01
a3["lama_dama_z_score"] = np.where(
    sparse | pd.isna(a3["peer_std_lama_dama_rate"]) | (a3["peer_std_lama_dama_rate"] == 0),
    np.nan,
    (a3["lama_dama_rate"] - a3["peer_avg_lama_dama_rate"]) / a3["peer_std_lama_dama_rate"]
)
a3["lama_dama_percentile_rank"] = peer_pctile(a3, "lama_dama_rate")

a3["high_lama_dama"]       = a3["lama_dama_z_score"] > 1.5
a3["excellent_retention"]  = (a3["normal_discharge_rate"] > 0.95) & (a3["total_cases"] >= 10)

out3 = ["hospital_id", "hospital_name", "hospital_type",
        "hbp_procedure_code", "procedure_name", "total_cases",
        "lama_dama_rate", "normal_discharge_rate",
        "peer_avg_lama_dama_rate", "peer_avg_normal_discharge_rate",
        "lama_dama_z_score", "lama_dama_percentile_rank",
        "high_lama_dama", "excellent_retention"]
a3 = a3[[c for c in out3 if c in a3.columns]]
save(a3, "bench_outcomes.parquet")

print(f"  high_lama_dama:      {a3['high_lama_dama'].sum()}")
print(f"  excellent_retention: {a3['excellent_retention'].sum()}")


# ═══════════════════════════════════════════════════════════════════════════════
# ANALYSIS 4: Claims Quality Benchmarking
# ═══════════════════════════════════════════════════════════════════════════════
section("ANALYSIS 4 — Claims Quality")

a4 = summary.copy()

# Peer stats
for metric, prefix in [("claim_rejection_rate", "peer_rej"),
                        ("claim_query_rate",     "peer_qry"),
                        ("avg_settlement_tat_days", "peer_tat")]:
    peer = (a4.groupby(PEER)[metric]
              .agg(["mean", "std"]).reset_index()
              .rename(columns={"mean": f"{prefix}_avg", "std": f"{prefix}_std"}))
    a4 = a4.merge(peer, on=PEER, how="left")

a4["rejection_z_score"]    = peer_z(a4, "claim_rejection_rate",    "peer_rej_avg", "peer_rej_std")
a4["query_z_score"]        = peer_z(a4, "claim_query_rate",        "peer_qry_avg", "peer_qry_std")
a4["settlement_tat_z_score"]= peer_z(a4, "avg_settlement_tat_days","peer_tat_avg", "peer_tat_std")

# Claims quality score: 1 - minmax-normalized for each component within peer group
def _minmax_inverted(df, metric):
    """Within each peer group, return 1 - minmax(metric). Higher = better."""
    def _norm(g):
        mn, mx = g[metric].min(), g[metric].max()
        if mx == mn:
            return pd.Series(1.0, index=g.index)
        return 1 - (g[metric] - mn) / (mx - mn)
    return df.groupby(PEER, group_keys=False).apply(_norm)

a4["_n_rej"] = _minmax_inverted(a4, "claim_rejection_rate")
a4["_n_qry"] = _minmax_inverted(a4, "claim_query_rate")
a4["_n_tat"] = _minmax_inverted(a4, "avg_settlement_tat_days")
a4["claims_quality_score"] = (a4["_n_rej"] + a4["_n_qry"] + a4["_n_tat"]) / 3

# Flags
a4["high_rejection"]       = a4["rejection_z_score"] > 1.5
a4["high_query"]           = a4["query_z_score"] > 1.5
a4["slow_settlement"]      = a4["settlement_tat_z_score"] > 1.5
a4["poor_claims_quality"]  = (a4[["high_rejection","high_query","slow_settlement"]]
                               .sum(axis=1) >= 2)
a4["clean_claims"]         = ((a4["claim_rejection_rate"] == 0) &
                               (a4["claim_query_rate"] < 0.05) &
                               (a4["total_cases"] >= 10))

out4 = ["hospital_id", "hospital_name", "hospital_type",
        "hbp_procedure_code", "procedure_name", "total_cases",
        "claim_rejection_rate", "claim_query_rate", "avg_query_count",
        "avg_settlement_tat_days",
        "peer_rej_avg", "peer_qry_avg", "peer_tat_avg",
        "rejection_z_score", "query_z_score", "settlement_tat_z_score",
        "claims_quality_score",
        "high_rejection", "high_query", "slow_settlement",
        "poor_claims_quality", "clean_claims"]
a4 = a4[[c for c in out4 if c in a4.columns]]
save(a4, "bench_claims_quality.parquet")

print(f"  high_rejection:      {a4['high_rejection'].sum()}")
print(f"  high_query:          {a4['high_query'].sum()}")
print(f"  slow_settlement:     {a4['slow_settlement'].sum()}")
print(f"  poor_claims_quality: {a4['poor_claims_quality'].sum()}")
print(f"  clean_claims:        {a4['clean_claims'].sum()}")


# ═══════════════════════════════════════════════════════════════════════════════
# ANALYSIS 5: Trend Detection
# ═══════════════════════════════════════════════════════════════════════════════
section("ANALYSIS 5 — Trend Detection")

# Work from monthly grain, but only for hospital-procedures meeting thresholds
qualified = summary[["hospital_id", "hbp_procedure_code", "total_cases", "active_months"]].copy()
qualified = qualified[qualified["active_months"] >= 4]

monthly = int_hp.merge(qualified[GRP], on=GRP, how="inner")

# Encode month as integer index for regression
all_months = sorted(monthly["month"].dropna().unique())
month_idx = {m: i for i, m in enumerate(all_months)}
monthly["_month_idx"] = monthly["month"].map(month_idx)

# Metrics to trend and their "good" direction
TREND_METRICS = {
    "avg_amount_claimed":      "decreasing",
    "avg_los_days":            "decreasing",
    "claim_approval_rate":     "increasing",
    "claim_query_rate":        "decreasing",
    "lama_dama_rate":          "decreasing",
    "normal_discharge_rate":   "increasing",
    "avg_settlement_tat_days": "decreasing",
}

def _compute_trend(group, metric, good_dir):
    g = group[["_month_idx", metric, "case_count"]].dropna()
    if len(g) < 4:
        return "INSUFFICIENT_DATA", np.nan
    x = g["_month_idx"].values.astype(float)
    y = g[metric].values.astype(float)
    w = g["case_count"].values.astype(float)
    if w.sum() == 0:
        return "STABLE", 0.0
    # Weighted linear regression
    w_sum = w.sum()
    wx = (w * x).sum() / w_sum
    wy = (w * y).sum() / w_sum
    wxx = (w * x * x).sum() / w_sum
    wxy = (w * x * y).sum() / w_sum
    denom = wxx - wx * wx
    if denom == 0:
        return "STABLE", 0.0
    slope = (wxy - wx * wy) / denom
    mean_y = wy
    if mean_y == 0:
        return "STABLE", slope
    rel_change = abs(slope) / abs(mean_y)
    if rel_change <= 0.05:
        return "STABLE", slope
    if good_dir == "decreasing":
        return ("IMPROVING" if slope < 0 else "DECLINING"), slope
    else:
        return ("IMPROVING" if slope > 0 else "DECLINING"), slope

trend_records = []
for (hid, proc), grp in monthly.groupby(GRP):
    rec = {"hospital_id": hid, "hbp_procedure_code": proc}
    trends = []
    for metric, good_dir in TREND_METRICS.items():
        direction, slope = _compute_trend(grp, metric, good_dir)
        short = metric.replace("avg_", "").replace("claim_", "").replace("_days", "")
        rec[f"{short}_trend"] = direction
        rec[f"{short}_slope"] = slope
        trends.append(direction)
    # Overall trajectory
    imp = sum(1 for t in trends if t == "IMPROVING")
    dec = sum(1 for t in trends if t == "DECLINING")
    valid = [t for t in trends if t not in ("INSUFFICIENT_DATA",)]
    if not valid:
        rec["overall_trajectory"] = "INSUFFICIENT_DATA"
    elif dec == 0 and imp > len(valid) / 2:
        rec["overall_trajectory"] = "IMPROVING"
    elif imp == 0 and dec > len(valid) / 2:
        rec["overall_trajectory"] = "DECLINING"
    elif imp == 0 and dec == 0:
        rec["overall_trajectory"] = "STABLE"
    else:
        rec["overall_trajectory"] = "MIXED"
    trend_records.append(rec)

a5 = pd.DataFrame(trend_records)

# Merge static attributes
static_attrs = summary[["hospital_id", "hbp_procedure_code", "hospital_name", "hospital_type",
                         "procedure_name", "block", "district", "division",
                         "total_cases", "active_months"]].copy()
a5 = a5.merge(static_attrs, on=GRP, how="left")

a5["declining_hospital"] = a5["overall_trajectory"] == "DECLINING"
a5["improving_hospital"] = a5["overall_trajectory"] == "IMPROVING"

save(a5, "bench_trends.parquet")

traj_dist = a5["overall_trajectory"].value_counts()
print(f"  Trajectory distribution:\n{traj_dist.to_string()}")
print(f"  declining_hospital: {a5['declining_hospital'].sum()}")
print(f"  improving_hospital: {a5['improving_hospital'].sum()}")


# ═══════════════════════════════════════════════════════════════════════════════
# ANALYSIS 6: Hospital Scorecard
# ═══════════════════════════════════════════════════════════════════════════════
section("ANALYSIS 6 — Hospital Scorecard")

# Part 1: aggregate summary across procedures per hospital
sc = summary.copy()
sc["_w_los"]  = sc["avg_los_days"]           * sc["total_cases"]
sc["_w_cost"] = sc["avg_amount_claimed"]      * sc["total_cases"]
sc["_w_lama"] = sc["lama_dama_rate"]          * sc["total_cases"]
sc["_w_rej"]  = sc["claim_rejection_rate"]    * sc["total_cases"]
sc["_w_qry"]  = sc["claim_query_rate"]        * sc["total_cases"]
sc["_w_tat"]  = sc["avg_settlement_tat_days"] * sc["total_cases"]
sc["_w_bio"]  = sc["biometric_auth_rate"]     * sc["total_cases"]
sc["_w_med"]  = sc["medicines_provided_rate"] * sc["total_cases"]

hosp_agg = (
    sc.groupby("hospital_id")
    .agg(
        hospital_name      = ("hospital_name",      "first"),
        hospital_type      = ("hospital_type",      "first"),
        hospital_sub_type  = ("hospital_sub_type",  "first"),
        block              = ("block",              "first"),
        district           = ("district",           "first"),
        division           = ("division",           "first"),
        capacity_band      = ("capacity_band",      "first"),
        total_cases        = ("total_cases",        "sum"),
        procedures_performed = ("hbp_procedure_code", "nunique"),
        specialties_covered  = ("specialty_code",     "nunique"),
        _tc                = ("total_cases",        "sum"),
        _total_approved    = ("total_amount_approved","sum"),
        _total_claimed     = ("total_amount_claimed", "sum"),
        _s_w_los           = ("_w_los",             "sum"),
        _s_w_cost          = ("_w_cost",            "sum"),
        _s_w_lama          = ("_w_lama",            "sum"),
        _s_w_rej           = ("_w_rej",             "sum"),
        _s_w_qry           = ("_w_qry",             "sum"),
        _s_w_tat           = ("_w_tat",             "sum"),
        _s_w_bio           = ("_w_bio",             "sum"),
        _s_w_med           = ("_w_med",             "sum"),
    )
    .reset_index()
)
tc2 = hosp_agg["_tc"]
hosp_agg["weighted_avg_los"]              = safe_div(hosp_agg["_s_w_los"],  tc2)
hosp_agg["weighted_avg_cost"]             = safe_div(hosp_agg["_s_w_cost"], tc2)
hosp_agg["overall_approval_ratio"]        = safe_div(hosp_agg["_total_approved"],
                                                      hosp_agg["_total_claimed"])
hosp_agg["overall_lama_dama_rate"]        = safe_div(hosp_agg["_s_w_lama"], tc2)
hosp_agg["overall_claim_rejection_rate"]  = safe_div(hosp_agg["_s_w_rej"],  tc2)
hosp_agg["overall_claim_query_rate"]      = safe_div(hosp_agg["_s_w_qry"],  tc2)
hosp_agg["overall_settlement_tat"]        = safe_div(hosp_agg["_s_w_tat"],  tc2)
hosp_agg["biometric_auth_rate"]           = safe_div(hosp_agg["_s_w_bio"],  tc2)
hosp_agg["medicines_provided_rate"]       = safe_div(hosp_agg["_s_w_med"],  tc2)
hosp_agg.drop(columns=[c for c in hosp_agg.columns if c.startswith("_")], inplace=True)

# Part 2: flag counts per hospital
flags_df = (
    a1[["hospital_id", "hbp_procedure_code", "high_cost_outlier", "high_approval_gap"]]
    .merge(a2[["hospital_id", "hbp_procedure_code", "long_stay_outlier"]], on=GRP, how="outer")
    .merge(a3[["hospital_id", "hbp_procedure_code", "high_lama_dama"]],   on=GRP, how="outer")
    .merge(a4[["hospital_id", "hbp_procedure_code", "poor_claims_quality"]],on=GRP, how="outer")
    .merge(a5[["hospital_id", "hbp_procedure_code", "declining_hospital"]],on=GRP, how="outer")
)

flag_cols = ["high_cost_outlier", "high_approval_gap", "long_stay_outlier",
             "high_lama_dama", "poor_claims_quality", "declining_hospital"]
for c in flag_cols:
    flags_df[c] = flags_df[c].fillna(False)

flags_df["flags_per_procedure"] = flags_df[flag_cols].sum(axis=1)

hosp_flags = (
    flags_df.groupby("hospital_id")
    .agg(
        cost_outlier_procedures   = ("high_cost_outlier",   "sum"),
        los_outlier_procedures    = ("long_stay_outlier",   "sum"),
        high_lama_dama_procedures = ("high_lama_dama",      "sum"),
        poor_claims_procedures    = ("poor_claims_quality", "sum"),
        declining_procedures      = ("declining_hospital",  "sum"),
        total_flags               = ("flags_per_procedure", "sum"),
        max_flags_single_procedure= ("flags_per_procedure", "max"),
        clean_procedures          = ("flags_per_procedure", lambda x: (x == 0).sum()),
    )
    .reset_index()
)

scorecard = hosp_agg.merge(hosp_flags, on="hospital_id", how="left")
for c in ["total_flags", "max_flags_single_procedure"]:
    scorecard[c] = scorecard[c].fillna(0).astype(int)

def _attention(row):
    if row["total_flags"] >= 3 or row["max_flags_single_procedure"] >= 3:
        return "NEEDS_REVIEW"
    if row["total_flags"] in (1, 2):
        return "WATCH"
    return "SATISFACTORY"

scorecard["attention_level"] = scorecard.apply(_attention, axis=1)
save(scorecard, "bench_hospital_scorecard.parquet")

att_dist = scorecard["attention_level"].value_counts()
print(f"  Attention distribution:\n{att_dist.to_string()}")
top_review = (scorecard[scorecard["attention_level"] == "NEEDS_REVIEW"]
              .nlargest(10, "total_flags")
              [["hospital_name","district","total_cases","total_flags","attention_level"]])
print(f"  Top 10 hospitals needing review:\n{top_review.to_string()}")


# ═══════════════════════════════════════════════════════════════════════════════
# SUMMARY
# ═══════════════════════════════════════════════════════════════════════════════
section("SUMMARY")

outputs = {
    "bench_hospital_procedure_summary": summary,
    "bench_cost":                       a1,
    "bench_los":                        a2,
    "bench_outcomes":                   a3,
    "bench_claims_quality":             a4,
    "bench_trends":                     a5,
    "bench_hospital_scorecard":         scorecard,
}

lines = ["# Phase 2b Summary\n", "## Files Created\n"]
for name, df in outputs.items():
    lines.append(f"- `analytics/{name}.parquet` -- {df.shape[0]:,} rows x {df.shape[1]} cols")

lines.append("\n## Flag Counts\n")
lines.append(f"- Cost outliers (high): {a1['high_cost_outlier'].sum()}")
lines.append(f"- Cost outliers (low): {a1['low_cost_outlier'].sum()}")
lines.append(f"- High approval gap: {a1['high_approval_gap'].sum()}")
lines.append(f"- Above package rate: {a1['above_package_rate'].sum()}")
lines.append(f"- Long stay outliers: {a2['long_stay_outlier'].sum()}")
lines.append(f"- Short stay outliers: {a2['short_stay_outlier'].sum()}")
lines.append(f"- High LAMA/DAMA: {a3['high_lama_dama'].sum()}")
lines.append(f"- Excellent retention: {a3['excellent_retention'].sum()}")
lines.append(f"- Poor claims quality: {a4['poor_claims_quality'].sum()}")
lines.append(f"- Clean claims: {a4['clean_claims'].sum()}")
lines.append(f"- Declining hospitals: {a5['declining_hospital'].sum()}")
lines.append(f"- Improving hospitals: {a5['improving_hospital'].sum()}")

lines.append("\n## Top 10 Hospitals Needing Review\n")
top10 = (scorecard[scorecard["attention_level"] == "NEEDS_REVIEW"]
         .nlargest(10, "total_flags"))
for _, r in top10.iterrows():
    lines.append(f"- {r['hospital_name']}, {r['district']}: "
                 f"{int(r['total_cases'])} cases, {int(r['total_flags'])} flags")

lines.append("\n## Assumptions\n")
lines.append("- Minimum 5 cases per hospital-procedure to be included in benchmarks.")
lines.append("- Peer groups: procedure x hospital_type (PUBLIC/PRIVATE).")
lines.append("- Mortality rates deliberately excluded (0.4% event rate too sparse for hospital-level inference).")
lines.append("- Trend detection requires >= 4 active months; uses weighted linear regression.")
lines.append("- Trend materiality threshold: slope must change metric by > 5% of mean per month.")
lines.append("- Claims quality score: average of 3 inverted min-max-normalized components within peer group.")
lines.append("- LAMA/DAMA z-scores nulled when peer group base rate < 1% (sparsity guard).")
lines.append("- Small peer group flag set when < 3 hospitals in the peer group.")

summary_text = "\n".join(lines)
summary_path = SCRIPT_DIR.parent / "phase2b_summary.md"
summary_path.write_text(summary_text, encoding="utf-8")
print(f"\n  Summary written: {summary_path}")
print(summary_text)
print("\n[DONE] Phase 2b complete.")
