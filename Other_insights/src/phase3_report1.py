"""
Phase 3 — Narrative Report: Demand-Supply Gap Analysis
Generates report_demand_supply_gap.md and .pdf using data from analytics/ + LLM (gpt-5.4).
"""

import os, re, textwrap
from datetime import date
from pathlib import Path

import pandas as pd
import numpy as np
from dotenv import load_dotenv
from openai import OpenAI

SCRIPT_DIR = Path(__file__).parent
ROOT_DIR   = SCRIPT_DIR.parent.parent
ANA_DIR    = SCRIPT_DIR.parent / "analytics"
INT_DIR    = SCRIPT_DIR.parent / "intermediate"
RPT_DIR    = SCRIPT_DIR.parent / "reports"
RPT_DIR.mkdir(parents=True, exist_ok=True)

load_dotenv(ROOT_DIR / ".env")
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
MODEL  = "gpt-5.4"

def chat(system, user, max_tokens=2500):
    r = client.chat.completions.create(
        model=MODEL,
        messages=[{"role":"system","content":system},{"role":"user","content":user}],
        max_completion_tokens=max_tokens, temperature=0.25,
    )
    return r.choices[0].message.content.strip()

def safe_div(a, b):
    return np.where((pd.isna(b))|(b==0), np.nan, a/b)

def pct(v, d=0):
    return f"{v*100:.{d}f}%"

def inr_lakh(v):
    if pd.isna(v): return "—"
    l = v / 1e5
    if l >= 100: return f"INR {l/100:.1f} crore"
    return f"INR {l:.1f} lakh"

def md_table(df, max_rows=None):
    if max_rows: df = df.head(max_rows)
    def _fmt(v):
        if isinstance(v, float):
            if pd.isna(v): return "—"
            if abs(v) < 1 and v != 0: return f"{v:.3f}"
            return f"{v:,.1f}" if v != int(v) else f"{int(v):,}"
        if isinstance(v, bool): return "Yes" if v else "No"
        if pd.isna(v): return "—"
        return str(v)
    header = "| " + " | ".join(str(c) for c in df.columns) + " |"
    sep    = "| " + " | ".join("---" for _ in df.columns) + " |"
    rows   = []
    for _, r in df.iterrows():
        rows.append("| " + " | ".join(_fmt(v) for v in r) + " |")
    return "\n".join([header, sep] + rows)

SYS = (
    "You are a senior health policy analyst writing a briefing note for UP state health officials "
    "about the PM-JAY demand-supply gap analysis. Write in direct, factual prose using bullet-list "
    "format for findings (not essay paragraphs). Name specific blocks and districts. "
    "Translate numbers into meaning (e.g., '8 out of 100 families'). "
    "Use INR in lakhs/crores. Keep each bullet to 1-2 lines. No jargon. No hedging."
)

# ─── Load data ────────────────────────────────────────────────────────────────
print("Loading data...", flush=True)
a1  = pd.read_parquet(ANA_DIR / "gap_utilization_scores.parquet")
a2  = pd.read_parquet(ANA_DIR / "gap_specialty_matrix.parquet")
a3  = pd.read_parquet(ANA_DIR / "gap_disease_burden.parquet")
a4b = pd.read_parquet(ANA_DIR / "gap_portability_flows.parquet")
a4d = pd.read_parquet(ANA_DIR / "gap_district_patient_flows.parquet")
a5  = pd.read_parquet(ANA_DIR / "gap_card_dropoff.parquet")
a6  = pd.read_parquet(ANA_DIR / "gap_repeat_utilization.parquet")
a7p = pd.read_parquet(ANA_DIR / "gap_seasonal_patterns.parquet")
a7s = pd.read_parquet(ANA_DIR / "gap_seasonal_summary.parquet")
a8  = pd.read_parquet(ANA_DIR / "gap_delisted_impact.parquet")
ids = pd.read_parquet(INT_DIR / "int_demand_supply.parquet")
ien = pd.read_parquet(INT_DIR / "int_enrolment_monthly.parquet")

# ─── Pre-compute all stats ───────────────────────────────────────────────────
print("Computing stats...", flush=True)

# State-level
total_enrolled = int(a1["total_beneficiaries_enrolled"].sum())
total_cases    = int(a1["total_cases_all_months"].fillna(0).sum())
total_distinct_ben = int(a1["distinct_beneficiaries_with_cases"].fillna(0).sum())
state_util     = total_distinct_ben / total_enrolled if total_enrolled else 0
total_hospitals= int(a1["total_hospitals"].fillna(0).sum())
total_beds     = int(a1["total_inpatient_beds"].fillna(0).sum())
min_month      = ids["month"].min()
max_month      = ids["month"].max()
today_str      = date.today().strftime("%d %B %Y")

# HELU
helu = a1[a1["high_enrolment_low_utilization"]==True]
helu_count  = len(helu)
helu_enrolled = int(helu["total_beneficiaries_enrolled"].sum())
helu_top10 = helu.nlargest(10,"total_beneficiaries_enrolled")[
    ["block","district","total_beneficiaries_enrolled","overall_utilization_rate"]].copy()
helu_top10["overall_utilization_rate"] = (helu_top10["overall_utilization_rate"]*100).round(1)
helu_top10.columns = ["Block","District","Enrolled","Utilization (%)"]
helu_districts = helu.groupby("district").size().sort_values(ascending=False).head(5)

# Zero supply
zs = a1[a1["zero_supply"]==True]
zs_count = len(zs)
zs_enrolled = int(zs["total_beneficiaries_enrolled"].fillna(0).sum())
zs_top5 = zs.nlargest(5,"total_beneficiaries_enrolled")[
    ["block","district","total_beneficiaries_enrolled"]].copy()
zs_top5.columns = ["Block","District","Enrolled"]

# Single hospital
sh = a1[a1["single_hospital_dependency"]==True]
sh_count = len(sh)
sh_enrolled = int(sh["total_beneficiaries_enrolled"].fillna(0).sum())

# Delisted + single
sole_del = a8[a8["sole_provider_delisted"]==True] if len(a8) else pd.DataFrame()

# Specialty gaps
sg_flagged = a2[a2["gap_flag"]==True]
sg_no_supply = a2[a2["gap_severity"]=="NO_SUPPLY"]
sg_total_combos = len(sg_flagged)
sg_no_supply_cnt = len(sg_no_supply)
total_leakage = sg_no_supply["estimated_revenue_leakage"].sum()
sg_by_spec = (sg_flagged.groupby(["specialty_code","specialty_name"])
              .agg(unmet_cases=("cases_demanding","sum"),
                   blocks=("block","nunique"),
                   leakage=("estimated_revenue_leakage","sum"))
              .sort_values("unmet_cases",ascending=False).reset_index())

# Infrastructure mismatch
mm = a3[a3["infrastructure_mismatch"]==True]
mm_count = len(mm)
mm_by_cat = mm.groupby("disease_category").agg(
    mismatch_blocks=("block","nunique"), total_cases=("case_count","sum")
).sort_values("total_cases",ascending=False).reset_index()

# Patient flows
local_retain_rate = float((a4b["cases_same_block"].sum()+a4b["cases_same_district"].sum()) / a4b["total_cases"].sum())
cross = a4d[a4d["origin_district"]!=a4d["destination_district"]].copy()
top_cross = cross.nlargest(10,"flow_count")[["origin_district","destination_district","flow_count"]]
top_cross.columns = ["From","To","Cases"]
# Net flow
net_by_dist = (a4d[a4d["origin_district"]==a4d["destination_district"]]
               [["origin_district","net_flow"]].drop_duplicates()
               .rename(columns={"origin_district":"district"}).sort_values("net_flow"))
exporters = net_by_dist.head(5)
importers = net_by_dist.tail(5).iloc[::-1]

# Lowest retention blocks
low_retain = a4b.nsmallest(10,"local_retention_rate")[
    ["block","district","total_cases","local_retention_rate"]].copy()
low_retain["local_retention_rate"] = (low_retain["local_retention_rate"]*100).round(1)
low_retain.columns = ["Block","District","Cases","Retention (%)"]

# Card drop-off
card_act_rate = float(a5["beneficiaries_with_active_card"].sum()/a5["total_beneficiaries"].sum())
hd_count = int(a5["high_drop_off"].sum())
hr_count = int(a5["high_rejection"].sum())
top_dropoff = a5.nlargest(10,"drop_off_rate")[
    ["block","district","total_beneficiaries","card_activation_rate","drop_off_rate"]].copy()
top_dropoff["card_activation_rate"]=(top_dropoff["card_activation_rate"]*100).round(1)
top_dropoff["drop_off_rate"]=(top_dropoff["drop_off_rate"]*100).round(1)
top_dropoff.columns=["Block","District","Beneficiaries","Card Activation (%)","Drop-off (%)"]

# Repeat utilization
state_repeat = float(a6["repeat_beneficiaries"].sum()/a6["total_beneficiaries_with_cases"].sum())
hr_repeat = int(a6["high_repeat_rate"].sum())
ptf = a6[a6["possible_treatment_failure"]==True]

# Seasonal
seasonal_count = int(a7s["is_seasonal"].sum())
surge_months_raw = a7p[a7p["surge_month"]==True].copy()
surge_months_raw["cal"] = surge_months_raw["month"].str[5:7].astype(int)
peak_cal = surge_months_raw["cal"].value_counts().head(3)
peak_disease = surge_months_raw["surge_dominant_disease"].value_counts().head(1)
top_seasonal = a7s[a7s["is_seasonal"]==True].nlargest(5,"seasonality_index")[
    ["block","district","seasonality_index","peak_months","peak_disease_category"]].copy()
top_seasonal.columns = ["Block","District","Seasonality Index","Peak Months","Peak Disease"]

# Delisted
del_count = len(a8)
sole_count= int(a8["sole_provider_delisted"].sum()) if del_count else 0
maj_count = int(a8["majority_capacity_lost"].sum()) if del_count else 0

# ─── LLM narrative calls ─────────────────────────────────────────────────────
print("Generating LLM sections...", flush=True)

def make_section(title, question, data_summary, max_tokens=1200):
    prompt = f"""Section: {title}
Question for this section: {question}

Data summary:
{data_summary}

Write this section using bullet-list format as specified in the report rules.
Lead with findings, not methodology. Name specific blocks and districts.
Translate rates into plain language (e.g., '8 out of 100 families').
Use INR in lakhs/crores. Keep each bullet to 1-2 lines.
Include all sub-sections as described. Use ### for sub-section headers.
Target length: as specified in the section heading guidance.
"""
    return chat(SYS, prompt, max_tokens=max_tokens)

exec_data = f"""
State context:
- {total_enrolled:,} beneficiaries enrolled across {len(a1)} blocks in 75 districts
- {total_cases:,} cases over {min_month} to {max_month}
- State-wide utilization: {pct(state_util,1)} ({total_distinct_ben:,} distinct beneficiaries used the scheme)
- {total_hospitals:,} empanelled hospitals, {total_beds:,} inpatient beds
- {zs_count} blocks have zero hospitals; {sh_count} blocks depend on a single hospital
- {helu_count} blocks flagged high-enrolment low-utilization, covering {helu_enrolled:,} enrolled beneficiaries
- Top specialty gap: {sg_by_spec.iloc[0]['specialty_name']} with {int(sg_by_spec.iloc[0]['unmet_cases'])} unmet cases
- {mm_count} block×disease mismatches where required infrastructure is absent
- Local retention rate: only {pct(local_retain_rate,1)} of cases treated within same district
- Card activation: {pct(card_act_rate,1)}; {hd_count} blocks with high drop-off
- {seasonal_count} blocks show seasonal surges, peaking Aug-Sep
- {del_count} delisted hospitals; {sole_count} were sole providers in their block
- Total estimated revenue leakage from specialty gaps: {inr_lakh(total_leakage)}
"""

n_exec = chat(SYS, f"""Write the Executive Summary (400-600 words) for a report titled
'Demand-Supply Gap Analysis Report — AB PM-JAY Uttar Pradesh'.

{exec_data}

4 paragraphs:
1. State-level context (enrolment, cases, hospitals, utilization rate)
2. Headline findings (3-4 most important, prioritized by population impact) — use bullet points
3. What this means in plain language for families
4. Brief roadmap of the 5 sections that follow

Write 400-600 words. Be thorough — every paragraph should be substantive.
""", max_tokens=1500)

s2_data = f"""
Sub-section 2.1 — High enrolment low utilization:
- {helu_count} blocks flagged; state avg utilization {pct(state_util,1)}
- Top 10 blocks:\n{helu_top10.to_string(index=False)}
- Districts with multiple problem blocks: {dict(helu_districts)}

Sub-section 2.2 — Zero supply and single hospital:
- {zs_count} blocks with zero hospitals; total enrolled in these: {zs_enrolled:,}
- Top 5 zero-supply blocks:\n{zs_top5.to_string(index=False)}
- {sh_count} single-hospital blocks covering {sh_enrolled:,} enrolled beneficiaries
- Sole-provider delisted blocks: {len(sole_del)} — {sole_del[['hospital_name','block','district']].to_string(index=False) if len(sole_del) else 'none'}

Sub-section 2.3 — Patient travel:
- Local retention rate (same block + same district): {pct(local_retain_rate,1)}
- 10 lowest-retention blocks:\n{low_retain.to_string(index=False)}
- Top 10 cross-district flows:\n{top_cross.to_string(index=False)}
- Net exporter districts (losing patients):\n{exporters.to_string(index=False)}
- Net importer districts (receiving patients):\n{importers.to_string(index=False)}
"""
n_s2 = make_section("Where People Can't Access Care (800-1200 words)",
                     "Where are the biggest access gaps?", s2_data, 2500)

s3_data = f"""
Sub-section 3.1 — Specialty gaps:
- {sg_total_combos} block×specialty combos with gap_flag; {sg_no_supply_cnt} with NO_SUPPLY
- Total leakage: {inr_lakh(total_leakage)}
- Top specialties by unmet cases:\n{sg_by_spec.head(7).to_string(index=False)}
- Top 3 blocks per top 5 specialties:
"""
for _, row in sg_by_spec.head(5).iterrows():
    top3 = sg_flagged[sg_flagged["specialty_code"]==row["specialty_code"]].nlargest(3,"cases_demanding")[["block","district","cases_demanding"]]
    s3_data += f"\n  {row['specialty_name']}:\n{top3.to_string(index=False)}\n"

s3_data += f"""
Sub-section 3.2 — Infrastructure mismatches:
- {mm_count} total mismatches across categories
- By category:\n{mm_by_cat.to_string(index=False)}
- Top 5 MATERNAL_NEONATAL mismatch blocks:\n{mm[mm['disease_category']=='MATERNAL_NEONATAL'].nlargest(5,'case_count')[['block','district','case_count']].to_string(index=False)}
- Top 5 INJURY mismatch blocks:\n{mm[mm['disease_category']=='INJURY'].nlargest(5,'case_count')[['block','district','case_count']].to_string(index=False)}
- Top 5 SURGICAL mismatch blocks:\n{mm[mm['disease_category']=='SURGICAL'].nlargest(5,'case_count')[['block','district','case_count']].to_string(index=False)}
- Top 5 NCD mismatch blocks:\n{mm[mm['disease_category']=='NCD'].nlargest(5,'case_count')[['block','district','case_count']].to_string(index=False)}

Sub-section 3.3 — Delisted hospitals:
- {del_count} delisted hospitals
- Sole provider delisted: {sole_count}
- Majority capacity lost: {maj_count}
- Detail:\n{a8[['hospital_name','block','district','delisted_beds','block_total_beds','bed_share_lost','specialties_lost','sole_provider_delisted']].to_string(index=False) if del_count else 'None'}
"""
n_s3 = make_section("What's Missing Where (800-1200 words)",
                     "Which specialties and infrastructure are absent where needed?", s3_data, 2500)

s4_data = f"""
Sub-section 4.1 — Card drop-off:
- State-wide card activation: {pct(card_act_rate,1)}
- {hd_count} blocks with high drop-off; {hr_count} with high rejection
- Top 10 drop-off blocks:\n{top_dropoff.to_string(index=False)}

Sub-section 4.2 — Repeat visits:
- State-wide repeat rate: {pct(state_repeat,1)}
- {hr_repeat} blocks with high repeat rate
- {len(ptf)} blocks flagged possible treatment failure
"""
if len(ptf):
    s4_data += f"- Treatment failure blocks:\n{ptf.nlargest(5,'repeat_rate')[['block','district','repeat_rate','possible_treatment_failure_rate']].to_string(index=False)}"
n_s4 = make_section("Administrative Barriers (400-600 words)",
                     "What scheme-process gaps exist beyond infrastructure?", s4_data, 1200)

s5_data = f"""
- {seasonal_count} blocks with seasonal surges (is_seasonal=True)
- Peak calendar months: {dict(peak_cal)}
- Dominant surge disease: {dict(peak_disease)}
- Top 5 most volatile blocks:\n{top_seasonal.to_string(index=False)}
"""
n_s5 = make_section("Seasonal Patterns (300-500 words)",
                     "When do demand surges happen and are they predictable?", s5_data, 1000)

# ─── Division-level table (Section 6) ────────────────────────────────────────
print("Building summary tables...", flush=True)

# Need division for each block — from a1
div_agg = a1.copy()
div_agg["_wutil"] = div_agg["overall_utilization_rate"]*div_agg["total_beneficiaries_enrolled"]

# Specialty gap: top per division
spec_gap_div = (sg_flagged.groupby(["division","specialty_name"])["cases_demanding"]
                .sum().reset_index()
                .sort_values("cases_demanding",ascending=False)
                .drop_duplicates("division"))

# Leakage per division — a4b already has division
leak_div = a4b.merge(a1[["block","district","division"]], on=["block","district"], how="left",
                      suffixes=("","_a1"))
if "division_a1" in leak_div.columns:
    leak_div["division"] = leak_div["division"].combine_first(leak_div["division_a1"])
    leak_div.drop(columns=["division_a1"], inplace=True)
leak_div["_wleak"] = leak_div["leakage_rate"]*leak_div["total_cases"]

# Card per division
card_div = a5.merge(a1[["block","district","division"]], on=["block","district"], how="left",
                     suffixes=("","_a1"))
if "division_a1" in card_div.columns:
    card_div["division"] = card_div["division"].combine_first(card_div["division_a1"])
    card_div.drop(columns=["division_a1"], inplace=True)
card_div["_wcard"] = card_div["card_activation_rate"]*card_div["total_beneficiaries"]

# Seasonal per division
seas_div = a7s.merge(a1[["block","district","division"]], on=["block","district"], how="left",
                      suffixes=("","_a1"))
if "division_a1" in seas_div.columns:
    seas_div["division"] = seas_div["division"].combine_first(seas_div["division_a1"])
    seas_div.drop(columns=["division_a1"], inplace=True)

div_tbl = (div_agg.groupby("division").agg(
    Enrolled=("total_beneficiaries_enrolled","sum"),
    _wutil_sum=("_wutil","sum"),
    _enr_sum=("total_beneficiaries_enrolled","sum"),
    ZeroSupply=("zero_supply","sum"),
).reset_index())
div_tbl["Utilization (%)"] = (div_tbl["_wutil_sum"]/div_tbl["_enr_sum"]*100).round(1)
div_tbl = div_tbl.drop(columns=["_wutil_sum","_enr_sum"])
div_tbl = div_tbl.merge(spec_gap_div[["division","specialty_name"]].rename(
    columns={"specialty_name":"Top Specialty Gap"}), on="division", how="left")

leak_d = (leak_div.groupby("division").agg(_wl=("_wleak","sum"),_tc=("total_cases","sum")).reset_index())
leak_d["Leakage (%)"] = (leak_d["_wl"]/leak_d["_tc"]*100).round(1)
div_tbl = div_tbl.merge(leak_d[["division","Leakage (%)"]], on="division", how="left")

card_d = (card_div.groupby("division").agg(_wc=("_wcard","sum"),_tb=("total_beneficiaries","sum")).reset_index())
card_d["Card Drop-off (%)"] = (100 - card_d["_wc"]/card_d["_tb"]*100).round(1)
div_tbl = div_tbl.merge(card_d[["division","Card Drop-off (%)"]], on="division", how="left")

seas_d = seas_div.groupby("division")["is_seasonal"].sum().reset_index().rename(columns={"is_seasonal":"Seasonal Blocks"})
div_tbl = div_tbl.merge(seas_d, on="division", how="left")
div_tbl = div_tbl.rename(columns={"division":"Division","ZeroSupply":"Zero-Supply Blocks"})
div_tbl["Enrolled"] = div_tbl["Enrolled"].astype(int)
div_tbl["Zero-Supply Blocks"] = div_tbl["Zero-Supply Blocks"].astype(int)
div_tbl["Seasonal Blocks"] = div_tbl["Seasonal Blocks"].fillna(0).astype(int)
div_tbl = div_tbl.sort_values("Utilization (%)")
div_tbl_md = md_table(div_tbl)

# ─── District-level table (Section 7) ────────────────────────────────────────
dist_agg = a1.copy()
dist_agg["_wutil"] = dist_agg["overall_utilization_rate"]*dist_agg["total_beneficiaries_enrolled"]

# Any flag per block
dist_agg["any_flag"] = (dist_agg["high_enrolment_low_utilization"] |
                         dist_agg["high_demand_low_local_supply"] |
                         dist_agg["zero_supply"] |
                         dist_agg["single_hospital_dependency"])

# Top specialty per district
spec_gap_dist = (sg_flagged.groupby(["district","specialty_name"])["cases_demanding"]
                 .sum().reset_index()
                 .sort_values("cases_demanding",ascending=False)
                 .drop_duplicates("district"))

# Net flow per district
net_flow_dist = net_by_dist.copy()

# Card per district
card_dist = a5.copy()
card_dist["_wc"] = card_dist["card_activation_rate"]*card_dist["total_beneficiaries"]

dist_tbl = (dist_agg.groupby(["district","division"]).agg(
    Enrolled=("total_beneficiaries_enrolled","sum"),
    _wutil=("_wutil","sum"),
    _enr=("total_beneficiaries_enrolled","sum"),
    Cases=("total_cases_all_months",lambda x: x.fillna(0).sum()),
    FlaggedBlocks=("any_flag","sum"),
).reset_index())
dist_tbl["Utilization (%)"] = (dist_tbl["_wutil"]/dist_tbl["_enr"]*100).round(1)
dist_tbl = dist_tbl.drop(columns=["_wutil","_enr"])
dist_tbl = dist_tbl.merge(spec_gap_dist[["district","specialty_name"]].rename(
    columns={"specialty_name":"Top Unmet Specialty"}), on="district", how="left")
dist_tbl = dist_tbl.merge(net_flow_dist.rename(columns={"net_flow":"Net Patient Flow"}),
                           on="district", how="left")
cd = (card_dist.groupby("district").agg(_wc=("_wc","sum"),_tb=("total_beneficiaries","sum")).reset_index())
cd["Card Activation (%)"] = (cd["_wc"]/cd["_tb"]*100).round(1)
dist_tbl = dist_tbl.merge(cd[["district","Card Activation (%)"]], on="district", how="left")
dist_tbl["Enrolled"] = dist_tbl["Enrolled"].astype(int)
dist_tbl["Cases"] = dist_tbl["Cases"].astype(int)
dist_tbl["FlaggedBlocks"] = dist_tbl["FlaggedBlocks"].astype(int)
dist_tbl = dist_tbl.rename(columns={"district":"District","division":"Division",
                                     "FlaggedBlocks":"Flagged Blocks"})
dist_tbl = dist_tbl.sort_values("Utilization (%)")
dist_tbl_md = md_table(dist_tbl)

# ─── Annexure A ───────────────────────────────────────────────────────────────
print("Building annexures...", flush=True)

priority = a1[(a1["high_enrolment_low_utilization"]) |
               (a1["zero_supply"]) |
               (a1["single_hospital_dependency"])].copy()

# Merge extra columns
spec_gap_cnt = sg_flagged.groupby(["block","district"]).size().reset_index(name="specialty_gaps")
mm_cnt = mm.groupby(["block","district"]).size().reset_index(name="infra_mismatches")

priority = (priority.merge(spec_gap_cnt, on=["block","district"], how="left")
                    .merge(mm_cnt, on=["block","district"], how="left")
                    .merge(a5[["block","district","drop_off_rate"]], on=["block","district"], how="left")
                    .merge(a4b[["block","district","leakage_rate"]], on=["block","district"], how="left")
                    .merge(a7s[["block","district","is_seasonal"]], on=["block","district"], how="left"))

priority = priority.sort_values("total_beneficiaries_enrolled", ascending=False)
ann_a = priority[["block","district","division","total_beneficiaries_enrolled",
                   "overall_utilization_rate","total_hospitals","total_inpatient_beds",
                   "specialty_gaps","infra_mismatches","drop_off_rate","leakage_rate","is_seasonal"]].copy()
ann_a.columns = ["Block","District","Division","Enrolled","Utilization","Hospitals","Beds",
                  "Specialty Gaps","Infra Mismatches","Drop-off Rate","Leakage Rate","Seasonal"]
ann_a["Utilization"] = (ann_a["Utilization"]*100).round(1)
ann_a["Drop-off Rate"] = (ann_a["Drop-off Rate"]*100).round(1)
ann_a["Leakage Rate"] = (ann_a["Leakage Rate"]*100).round(1)
ann_a = ann_a.fillna({"Specialty Gaps":0,"Infra Mismatches":0,"Hospitals":0,"Beds":0})
ann_a_md = md_table(ann_a)

# ─── Annexure B ───────────────────────────────────────────────────────────────
ann_b = sg_flagged.sort_values("cases_demanding", ascending=False)[
    ["block","district","specialty_name","cases_demanding","hospitals_offering",
     "gap_severity","estimated_revenue_leakage","nearest_block_with_supply"]].copy()
ann_b.columns = ["Block","District","Specialty","Cases","Hospitals Offering",
                  "Severity","Revenue Leakage (INR)","Nearest Supply Block"]
ann_b_md = md_table(ann_b)

# ─── Assemble report ─────────────────────────────────────────────────────────
print("Assembling report...", flush=True)

report = f"""# AYUSHMAN BHARAT PM-JAY — UTTAR PRADESH
# Demand-Supply Gap Analysis Report

**Prepared for:** State Health Agency, Uttar Pradesh
**Data Period:** {min_month} to {max_month}
**Report Generated:** {today_str}

---

## 1. Executive Summary

{n_exec}

---

## 2. Where People Can't Access Care

{n_s2}

---

## 3. What's Missing Where

{n_s3}

---

## 4. Administrative Barriers

{n_s4}

---

## 5. Seasonal Patterns

{n_s5}

---

## 6. Division-Level Summary

{div_tbl_md}

---

## 7. District-Level Summary

{dist_tbl_md}

---

## Annexure A: High-Priority Blocks

All blocks flagged as high-enrolment low-utilization, zero-supply, or single-hospital dependency ({len(ann_a)} blocks):

{ann_a_md}

---

## Annexure B: Full Specialty Gap Detail

All block × specialty combinations with unmet demand ({len(ann_b)} rows):

{ann_b_md}

---

*Analysis based on synthetic PM-JAY data for Uttar Pradesh. All findings are for demonstration and research purposes.*
"""

md_path = RPT_DIR / "report_demand_supply_gap.md"
md_path.write_text(report, encoding="utf-8")
print(f"Report written: {md_path} ({len(report):,} chars)", flush=True)

# Word count (main body, excluding annexures)
annex_start = report.find("## Annexure A")
main_body = report[:annex_start] if annex_start > 0 else report
word_count = len(main_body.split())
print(f"Main body word count: {word_count}")

# ─── PDF conversion ──────────────────────────────────────────────────────────
print("Converting to PDF...", flush=True)

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, HRFlowable, Table, TableStyle, KeepTogether,
)

NAVY = colors.HexColor("#1a3c5e")
PAGE_W, PAGE_H = A4
MARGIN = 2.0 * cm
USABLE_W = PAGE_W - 2 * MARGIN

pdf_styles = {
    "h1": ParagraphStyle("h1", fontSize=17, leading=22, spaceAfter=8, spaceBefore=14,
                          fontName="Helvetica-Bold", textColor=NAVY),
    "h2": ParagraphStyle("h2", fontSize=13, leading=18, spaceAfter=5, spaceBefore=12,
                          fontName="Helvetica-Bold", textColor=NAVY),
    "h3": ParagraphStyle("h3", fontSize=10.5, leading=14, spaceAfter=4, spaceBefore=8,
                          fontName="Helvetica-Bold", textColor=colors.HexColor("#2d5f8a")),
    "body": ParagraphStyle("body", fontSize=9, leading=13, spaceAfter=4,
                            fontName="Helvetica", textColor=colors.HexColor("#222")),
    "italic": ParagraphStyle("italic", fontSize=9, leading=13, spaceAfter=5,
                              fontName="Helvetica-Oblique", textColor=colors.HexColor("#555")),
    "bullet": ParagraphStyle("bullet", fontSize=9, leading=13, spaceAfter=2,
                              fontName="Helvetica", textColor=colors.HexColor("#222"), leftIndent=16),
    "tcell": ParagraphStyle("tcell", fontSize=6.5, leading=8.5, fontName="Helvetica",
                             textColor=colors.HexColor("#222")),
    "theader": ParagraphStyle("theader", fontSize=6.5, leading=8.5, fontName="Helvetica-Bold",
                               textColor=colors.white),
}

def _inline(t):
    t = t.replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")
    t = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", t)
    t = re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", r"<i>\1</i>", t)
    return t

def _parse_row(line):
    return [p.strip() for p in line.strip().strip("|").split("|")]

def _is_sep(line):
    return bool(re.match(r"^\|[\s\-:|]+\|$", line.strip()))

def _build_tbl(hdr, rows, styles):
    nc = len(hdr)
    cw = USABLE_W / nc
    data = [[Paragraph(_inline(c), styles["theader"]) for c in hdr]]
    for r in rows:
        cells = (r + [""]*(nc-len(r)))[:nc]
        data.append([Paragraph(_inline(c), styles["tcell"]) for c in cells])
    t = Table(data, colWidths=[cw]*nc, repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND",(0,0),(-1,0),NAVY), ("TEXTCOLOR",(0,0),(-1,0),colors.white),
        ("FONTSIZE",(0,0),(-1,-1),6.5), ("BOTTOMPADDING",(0,0),(-1,0),4),
        ("TOPPADDING",(0,1),(-1,-1),2), ("BOTTOMPADDING",(0,1),(-1,-1),2),
        ("LEFTPADDING",(0,0),(-1,-1),3), ("RIGHTPADDING",(0,0),(-1,-1),3),
        ("GRID",(0,0),(-1,-1),0.3,colors.HexColor("#ccc")),
        ("ROWBACKGROUNDS",(0,1),(-1,-1),[colors.white,colors.HexColor("#f5f8fb")]),
        ("VALIGN",(0,0),(-1,-1),"TOP"),
    ]))
    return t

def md_to_flows(text, styles):
    flows = []
    lines = text.splitlines()
    i, n = 0, len(lines)
    while i < n:
        s = lines[i].strip()
        if not s:
            flows.append(Spacer(1,2)); i+=1; continue
        if s.startswith("|") and i+1<n and _is_sep(lines[i+1]):
            hdr = _parse_row(s); i+=2; body=[]
            while i<n and lines[i].strip().startswith("|"):
                body.append(_parse_row(lines[i])); i+=1
            flows.append(Spacer(1,3))
            flows.append(_build_tbl(hdr, body, styles))
            flows.append(Spacer(1,3)); continue
        if s.startswith("# ") and not s.startswith("## "):
            flows.append(Spacer(1,5)); flows.append(Paragraph(_inline(s[2:]),styles["h1"])); i+=1; continue
        if s.startswith("## ") and not s.startswith("### "):
            flows.append(Spacer(1,5))
            flows.append(HRFlowable(width="100%",thickness=0.8,color=colors.HexColor("#ccc"),spaceAfter=2))
            flows.append(Paragraph(_inline(s[3:]),styles["h2"])); i+=1; continue
        if s.startswith("### "):
            flows.append(Paragraph(_inline(s[4:]),styles["h3"])); i+=1; continue
        if s in ("---","***","___"):
            flows.append(HRFlowable(width="100%",thickness=0.4,color=colors.HexColor("#ddd"),spaceAfter=4)); i+=1; continue
        if s.startswith("*") and s.endswith("*") and s.count("*")==2:
            flows.append(Paragraph(_inline(s[1:-1]),styles["italic"])); i+=1; continue
        m = re.match(r"^(\d+)\.\s+(.+)$", s)
        if m:
            flows.append(Paragraph(f"{m.group(1)}. {_inline(m.group(2))}",styles["bullet"])); i+=1; continue
        if s.startswith("- ") or s.startswith("* "):
            flows.append(Paragraph(f"\u2022 {_inline(s[2:])}",styles["bullet"])); i+=1; continue
        flows.append(Paragraph(_inline(s),styles["body"])); i+=1
    return flows

pdf_path = RPT_DIR / "report_demand_supply_gap.pdf"
doc = SimpleDocTemplate(str(pdf_path), pagesize=A4,
                         leftMargin=MARGIN, rightMargin=MARGIN,
                         topMargin=1.8*cm, bottomMargin=1.8*cm,
                         title="PM-JAY UP Demand-Supply Gap Analysis",
                         author="Other Insights Pipeline")
doc.build(md_to_flows(report, pdf_styles))
print(f"PDF written: {pdf_path}", flush=True)
print("[DONE]", flush=True)
