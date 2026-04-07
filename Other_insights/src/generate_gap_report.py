"""
Demand-Supply Gap Analysis Report Generator
Reads all 10 analytics parquet files and produces a structured markdown report
with LLM-generated narrative via OpenAI API.
"""

import os
import json
import textwrap
import pandas as pd
import numpy as np
from pathlib import Path
from dotenv import load_dotenv
from openai import OpenAI

SCRIPT_DIR  = Path(__file__).parent
ROOT_DIR    = SCRIPT_DIR.parent.parent
ANA_DIR     = SCRIPT_DIR.parent / "analytics"
OUT_DIR     = SCRIPT_DIR.parent
REPORT_MD   = OUT_DIR / "gap_analysis_report.md"

load_dotenv(ROOT_DIR / ".env")
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
MODEL  = "gpt-5.4-mini"

def chat(system_prompt, user_prompt, max_tokens=900):
    resp = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_prompt},
        ],
        max_completion_tokens=max_tokens,
        temperature=0.3,
    )
    return resp.choices[0].message.content.strip()

def load(name):
    return pd.read_parquet(ANA_DIR / name)

def pct(v):
    return f"{v*100:.1f}%"

def inr(v):
    if v >= 1e7:  return f"INR {v/1e7:.1f} Cr"
    if v >= 1e5:  return f"INR {v/1e5:.1f} L"
    return f"INR {v:,.0f}"

def md_table(df, cols=None, max_rows=10):
    if cols:
        df = df[cols]
    df = df.head(max_rows)
    header = "| " + " | ".join(str(c) for c in df.columns) + " |"
    sep    = "| " + " | ".join("---" for _ in df.columns) + " |"
    rows   = []
    for _, r in df.iterrows():
        cells = []
        for v in r:
            if isinstance(v, float):
                cells.append(f"{v:.3f}" if not pd.isna(v) else "—")
            elif pd.isna(v):
                cells.append("—")
            else:
                cells.append(str(v))
        rows.append("| " + " | ".join(cells) + " |")
    return "\n".join([header, sep] + rows)

SYS = (
    "You are a senior health policy analyst specialising in India's AB PM-JAY programme "
    "for Uttar Pradesh. Write concise, evidence-grounded prose for a policy report. "
    "Use plain English. Avoid bullet lists — write in flowing paragraphs. "
    "Do not repeat numbers already shown in tables — interpret them. "
    "3-4 sentences per paragraph, 2 paragraphs maximum unless instructed otherwise."
)

print("Loading analytics files…", flush=True)

a1  = load("gap_utilization_scores.parquet")
a2  = load("gap_specialty_matrix.parquet")
a3  = load("gap_disease_burden.parquet")
a4b = load("gap_portability_flows.parquet")
a4d = load("gap_district_patient_flows.parquet")
a5  = load("gap_card_dropoff.parquet")
a6  = load("gap_repeat_utilization.parquet")
a7p = load("gap_seasonal_patterns.parquet")
a7s = load("gap_seasonal_summary.parquet")
a8  = load("gap_delisted_impact.parquet")

# ─── Pre-compute headline numbers ────────────────────────────────────────────
total_blocks         = len(a1)
zero_supply_blocks   = int(a1["zero_supply"].sum())
helu_blocks          = int(a1["high_enrolment_low_utilization"].sum())
hdls_blocks          = int(a1["high_demand_low_local_supply"].sum())
single_hosp          = int(a1["single_hospital_dependency"].sum())
state_util_rate      = float(a1["overall_utilization_rate"].mean())

no_supply_rows       = int((a2["gap_severity"] == "NO_SUPPLY").sum())
undersupply_rows     = int((a2["gap_severity"] == "UNDERSUPPLIED").sum())
total_leakage        = float(a2["estimated_revenue_leakage"].sum())
top_spec_gaps        = (a2[a2["gap_flag"] == True]
                        .groupby("specialty_code")["cases_demanding"]
                        .sum().sort_values(ascending=False))

infra_mismatches     = int(a3["infrastructure_mismatch"].sum())
infra_by_cat         = a3.groupby("disease_category")["infrastructure_mismatch"].sum().to_dict()

same_block_rate      = float(a4b["cases_same_block"].sum()  / a4b["total_cases"].sum())
local_retain         = float((a4b["cases_same_block"].sum()  +
                               a4b["cases_same_district"].sum()) / a4b["total_cases"].sum())
oos_rate             = float(a4b["cases_out_of_state"].sum() / a4b["total_cases"].sum())

card_act_rate        = float(a5["beneficiaries_with_active_card"].sum() /
                              a5["total_beneficiaries"].sum())
high_dropoff         = int(a5["high_drop_off"].sum())

state_repeat_rate    = float(a6["repeat_beneficiaries"].sum() /
                              a6["total_beneficiaries_with_cases"].sum())

seasonal_blocks      = int(a7s["is_seasonal"].sum())

sole_delisted        = int(a8["sole_provider_delisted"].sum()) if len(a8) else 0
majority_lost        = int(a8["majority_capacity_lost"].sum()) if len(a8) else 0
spec_lost            = int((a8["specialties_lost"] != "").sum()) if len(a8) else 0

# ─── Section data summaries (passed to LLM) ──────────────────────────────────
def a1_summary():
    top_gap = (a1[a1["high_enrolment_low_utilization"]]
               .nlargest(5, "total_beneficiaries_enrolled")
               [["block","district","total_beneficiaries_enrolled","overall_utilization_rate"]])
    bottom_util = a1.nsmallest(5, "overall_utilization_rate")[
        ["block","district","overall_utilization_rate","total_hospitals"]]
    return f"""
Total blocks: {total_blocks}. Blocks with zero empanelled hospitals: {zero_supply_blocks} ({pct(zero_supply_blocks/total_blocks)}).
Blocks with single-hospital dependency: {single_hosp}.
State-wide average utilization rate: {pct(state_util_rate)}.
High-enrolment low-utilization flag: {helu_blocks} blocks. High-demand low-local-supply flag: {hdls_blocks} blocks.

Top 5 high-enrolment low-utilization blocks:
{top_gap.to_string(index=False)}

Lowest utilization blocks:
{bottom_util.to_string(index=False)}
"""

def a2_summary():
    spec_gap_df = top_spec_gaps.head(8).reset_index()
    spec_gap_df.columns = ["specialty_code", "unmet_cases"]
    top10 = (a2[a2["gap_flag"] == True]
             .nlargest(10, "cases_demanding")
             [["block","district","specialty_code","specialty_name","cases_demanding",
               "nearest_block_same_district"]])
    return f"""
Total block×specialty rows: {len(a2)}.
NO_SUPPLY gaps (demand present, zero local hospitals): {no_supply_rows}.
UNDERSUPPLIED gaps (high demand/supply ratio): {undersupply_rows}.
Estimated revenue leakage from NO_SUPPLY gaps: {inr(total_leakage)}.

Top specialties with unmet demand (no local supply):
{spec_gap_df.to_string(index=False)}

Top 10 block-specialty gaps by case volume:
{top10.to_string(index=False)}
"""

def a3_summary():
    worst = (a3[a3["infrastructure_mismatch"] == True]
             .sort_values("case_count", ascending=False)
             .head(8)[["block","district","disease_category","case_count","infrastructure_strain"]])
    cat_df = pd.DataFrame(list(infra_by_cat.items()),
                          columns=["disease_category","mismatch_blocks"]).sort_values("mismatch_blocks",ascending=False)
    return f"""
Total block×disease_category rows: {len(a3)}.
Infrastructure mismatches (cases present, required facility absent): {infra_mismatches}.

Mismatches by disease category:
{cat_df.to_string(index=False)}

Worst-affected blocks (highest case volume with mismatch):
{worst.to_string(index=False)}
"""

def a4_summary():
    net = a4d.dropna(subset=["net_flow"]).copy()
    net_by_dist = (a4d[a4d["origin_district"] == a4d["destination_district"]]
                   [["origin_district","net_flow"]]
                   .drop_duplicates().sort_values("net_flow", ascending=False))
    importers  = net_by_dist.head(5)
    exporters  = net_by_dist.tail(5)
    top_leakage= a4b.nlargest(10, "leakage_rate")[
        ["block","district","total_cases","cases_diff_district","leakage_rate"]]
    return f"""
Total cases: {int(a4b['total_cases'].sum())}.
Cases treated in same block: {pct(same_block_rate)}.
Local retention rate (same block or same district): {pct(local_retain)}.
Out-of-state portability cases: {pct(oos_rate)}.

Top 10 highest-leakage blocks (most cross-district travel):
{top_leakage.to_string(index=False)}

Net importing districts (positive = more cases coming in):
{importers.to_string(index=False)}

Net exporting districts (negative = more cases leaving):
{exporters.tail().to_string(index=False)}
"""

def a5_summary():
    high_do = (a5[a5["high_drop_off"] == True]
               .nlargest(10, "drop_off_rate")
               [["block","district","total_beneficiaries","card_activation_rate",
                 "drop_off_rate","enrolment_rejection_rate"]])
    return f"""
State-wide card activation rate: {pct(card_act_rate)}.
Blocks with high drop-off (>75th percentile): {high_dropoff}.
State-wide enrolment rejection rate: {pct(float(a5['enrolment_rejected_count'].sum()/a5['total_beneficiaries'].sum()))}.

Top 10 highest drop-off blocks:
{high_do.to_string(index=False)}
"""

def a6_summary():
    top_repeat = a6.nlargest(10, "repeat_rate")[
        ["block","district","total_beneficiaries_with_cases",
         "repeat_beneficiaries","repeat_rate","possible_treatment_failure_rate"]]
    return f"""
State-wide repeat utilization rate: {pct(state_repeat_rate)}.
Blocks with high repeat rate (>75th percentile): {int(a6['high_repeat_rate'].sum())}.
Blocks flagged for possible treatment failure: {int(a6['possible_treatment_failure'].sum())}.

Top 10 highest repeat-rate blocks:
{top_repeat.to_string(index=False)}
"""

def a7_summary():
    peak_months = a7p[a7p["surge_month"] == True].copy()
    peak_months["cal_month"] = peak_months["month"].str[5:7].astype(int)
    month_dist = peak_months["cal_month"].value_counts().head(6)
    disease_in_surges = peak_months["surge_dominant_disease"].value_counts().head(5)
    top_seasonal = (a7s[a7s["is_seasonal"] == True]
                    .sort_values("seasonality_index", ascending=False)
                    .head(8)[["block","district","seasonality_index",
                               "peak_to_trough_ratio","peak_months","peak_disease_category"]])
    return f"""
Blocks meeting seasonality threshold (>=12 cases, >=6 active months): {int(a7s['meets_threshold'].sum())}.
Blocks with at least one surge month: {seasonal_blocks}.

Calendar month frequency in surge events:
{month_dist.to_string()}

Dominant disease category in surge months:
{disease_in_surges.to_string()}

Most seasonal blocks by coefficient of variation:
{top_seasonal.to_string(index=False)}
"""

def a8_summary():
    if len(a8) == 0:
        return "No delisted hospitals found."
    detail = a8[["hospital_name","block","district","delisted_beds",
                  "bed_share_lost","sole_provider_delisted",
                  "majority_capacity_lost","specialties_lost","block_cases_per_remaining_bed"]]
    return f"""
Delisted hospitals: {len(a8)}.
Sole-provider blocks (only hospital delisted): {sole_delisted}.
Blocks where >50% of bed capacity lost: {majority_lost}.
Delisted hospitals with unique specialties lost: {spec_lost}.

Detail:
{detail.to_string(index=False)}
"""

# ─── LLM calls ───────────────────────────────────────────────────────────────
print("Generating LLM narrative sections…", flush=True)

exec_prompt = f"""
Write an Executive Summary (3 paragraphs) for a policy report titled:
"Demand-Supply Gap Analysis — AB PM-JAY Uttar Pradesh".

Dataset context: 3 years of synthetic PM-JAY data for UP — 641 blocks, 75 districts,
50,000 households (~200K beneficiaries), 800 empanelled hospitals, 22,500 cases.

Key headline numbers:
- {zero_supply_blocks} of {total_blocks} blocks have zero empanelled hospitals ({pct(zero_supply_blocks/total_blocks)})
- State-wide beneficiary utilization rate: {pct(state_util_rate)}
- {no_supply_rows:,} block×specialty combinations have patient demand but no local hospital offering that specialty
- Estimated financial leakage from no-supply gaps: {inr(total_leakage)}
- Only {pct(same_block_rate)} of cases are treated within the patient's own block; local retention (same district) is {pct(local_retain)}
- Card activation rate: {pct(card_act_rate)} (drop-off in {high_dropoff} blocks flagged)
- {seasonal_blocks} blocks show seasonal demand surges, peaking in August–September
- {sole_delisted} blocks have had their sole hospital delisted from the scheme

Paragraph 1: Context and purpose of this analysis.
Paragraph 2: Most critical access and supply findings.
Paragraph 3: Key operational and policy implications.
"""
exec_summary = chat(SYS, exec_prompt, max_tokens=600)

def narrate(section_title, data_summary, question, max_tokens=500):
    prompt = f"""
Analysis section: {section_title}
Policy question: {question}

Data summary:
{data_summary}

Write 2 concise paragraphs interpreting these findings for a health policy audience.
Focus on what the numbers mean — do not re-list all numbers already in the table above.
Highlight the most concerning patterns and what they suggest about access barriers.
"""
    return chat(SYS, prompt, max_tokens=max_tokens)

n1 = narrate("Access and Utilization Gap Scoring",   a1_summary(),
             "Which blocks have high enrolment but low utilization, suggesting access barriers?")
n2 = narrate("Specialty Supply Gap Matrix",           a2_summary(),
             "Which block×specialty combinations have demand but no local supply?")
n3 = narrate("Disease Burden vs Infrastructure",      a3_summary(),
             "Does the disease mix in each block match the available facility infrastructure?")
n4 = narrate("Patient Flow and Portability Patterns", a4_summary(),
             "Where are beneficiaries going for care, and what does the flow pattern reveal about local gaps?")
n5 = narrate("Enrolment-to-Card Activation Drop-off", a5_summary(),
             "Are there blocks where beneficiaries enrol but disproportionately fail to get an active card?")
n6 = narrate("Repeat Utilization Patterns",           a6_summary(),
             "Which blocks have high repeat visits, potentially signalling chronic burden or ineffective treatment?")
n7 = narrate("Seasonal Demand Surges",                a7_summary(),
             "Do certain blocks experience seasonal surges that may overwhelm local capacity?")
n8 = narrate("Delisted Hospital Impact",              a8_summary(),
             "Which blocks have lost effective hospital capacity due to scheme delisting?")

reco_prompt = f"""
Based on this demand-supply gap analysis for AB PM-JAY in Uttar Pradesh, write a
'Policy Recommendations' section with exactly 6 numbered recommendations.
Each recommendation should be 2-3 sentences: what to do, why (evidence from the analysis),
and who is responsible (SHA / district health officer / NHA).

Key findings to draw from:
1. {zero_supply_blocks} blocks with zero hospitals — including {single_hosp} with single-hospital dependency
2. OBG, GS, MED, ORTH, CARD are the top 5 specialty gaps; {inr(total_leakage)} in leakage
3. Only {pct(local_retain)} local retention rate — {pct(1-local_retain)} of patients cross district lines
4. {infra_mismatches} blocks lack infrastructure matched to their disease burden (NCD, Surgical, Maternal)
5. {high_dropoff} blocks have above-average enrolment drop-off; state card activation {pct(card_act_rate)}
6. August–September surge peaks in {seasonal_blocks} blocks, dominated by communicable diseases
7. {sole_delisted} sole-provider hospitals delisted; {majority_lost} blocks lost >50% bed capacity

Write the 6 recommendations as numbered prose paragraphs.
"""
recommendations = chat(SYS, reco_prompt, max_tokens=900)

print("Assembling report…", flush=True)

# ─── Assemble markdown ───────────────────────────────────────────────────────
top_gap_tbl = md_table(
    a1[a1["high_enrolment_low_utilization"]].nlargest(10, "total_beneficiaries_enrolled"),
    cols=["block","district","total_beneficiaries_enrolled",
          "overall_utilization_rate","total_hospitals","zero_supply"]
)
spec_gap_tbl = md_table(
    a2[a2["gap_flag"] == True].nlargest(15, "cases_demanding"),
    cols=["block","district","specialty_code","specialty_name",
          "cases_demanding","gap_severity","nearest_block_with_supply"]
)
disease_tbl = md_table(
    a3[a3["infrastructure_mismatch"] == True].sort_values("case_count", ascending=False),
    cols=["block","district","disease_category","case_count",
          "hospitals_with_required_facilities","infrastructure_strain"],
    max_rows=12
)
flow_tbl = md_table(
    a4b.nlargest(12, "leakage_rate"),
    cols=["block","district","total_cases","cases_same_block",
          "cases_diff_district","cases_out_of_state","leakage_rate"]
)
card_tbl = md_table(
    a5[a5["high_drop_off"] == True].nlargest(12, "drop_off_rate"),
    cols=["block","district","total_beneficiaries","card_activation_rate",
          "drop_off_rate","enrolment_rejection_rate"]
)
seasonal_tbl = md_table(
    a7s[a7s["is_seasonal"] == True].sort_values("seasonality_index", ascending=False),
    cols=["block","district","seasonality_index","peak_to_trough_ratio",
          "peak_months","peak_disease_category"],
    max_rows=12
)
delisted_tbl = md_table(
    a8,
    cols=["hospital_name","block","district","delisted_beds","bed_share_lost",
          "sole_provider_delisted","specialties_lost","block_cases_per_remaining_bed"]
) if len(a8) else "_No delisted hospitals in dataset._"

# ─── Specialty gap leakage by specialty ──────────────────────────────────────
leakage_by_spec = (a2[a2["gap_severity"] == "NO_SUPPLY"]
                   .groupby(["specialty_code","specialty_name"])
                   .agg(no_supply_blocks=("block","nunique"),
                        total_unmet_cases=("cases_demanding","sum"),
                        revenue_leakage=("estimated_revenue_leakage","sum"))
                   .sort_values("revenue_leakage", ascending=False)
                   .reset_index())
leakage_by_spec["revenue_leakage"] = leakage_by_spec["revenue_leakage"].apply(
    lambda v: f"{v/1e5:.1f} L" if not pd.isna(v) else "—")
leakage_tbl = md_table(leakage_by_spec, max_rows=15)

# ─── District net flow table ──────────────────────────────────────────────────
dist_net = (a4d[a4d["origin_district"] == a4d["destination_district"]]
            [["origin_district","net_flow"]].drop_duplicates()
            .sort_values("net_flow", ascending=False))
dist_net_tbl = md_table(dist_net.rename(columns={"origin_district":"district"}), max_rows=20)

report = f"""# Demand-Supply Gap Analysis
## Ayushman Bharat PM-JAY — Uttar Pradesh
### Synthetic Data Analysis Report

---

## Executive Summary

{exec_summary}

---

## Dataset Overview

| Parameter | Value |
|-----------|-------|
| Geographic scope | Uttar Pradesh — 18 divisions, 75 districts, {total_blocks} blocks |
| Observation period | January 2022 – December 2025 (36 months) |
| Households enrolled | 50,000 |
| Beneficiaries | ~205,847 |
| Empanelled hospitals | 800 |
| Cases analysed | 22,500 |
| Parquet analytics files | 10 |

---

## 1. Access and Utilization Gaps

**Policy question:** Which blocks have high enrolment but low utilization, suggesting access barriers rather than low need?

{n1}

### Key Metrics

| Metric | Value |
|--------|-------|
| Blocks with zero empanelled hospitals | {zero_supply_blocks} ({pct(zero_supply_blocks/total_blocks)}) |
| Blocks with single-hospital dependency | {single_hosp} ({pct(single_hosp/total_blocks)}) |
| State-wide utilization rate | {pct(state_util_rate)} |
| High-enrolment low-utilization blocks | {helu_blocks} |
| High-demand low-local-supply blocks | {hdls_blocks} |

### Top 10 High-Enrolment Low-Utilization Blocks

{top_gap_tbl}

---

## 2. Specialty Supply Gaps

**Policy question:** Which block × specialty combinations have patient demand but no local hospital offering that specialty?

{n2}

### Revenue Leakage by Specialty (NO_SUPPLY gaps)

{leakage_tbl}

### Top 15 Block × Specialty Gaps by Unmet Case Volume

{spec_gap_tbl}

---

## 3. Disease Burden vs. Infrastructure

**Policy question:** Does the disease mix in each block match the infrastructure available at local hospitals?

{n3}

### Infrastructure Mismatches by Disease Category

| Disease Category | Blocks with Mismatch | Required Facility |
|-----------------|---------------------|-------------------|
| NCD | {infra_by_cat.get('NCD',0)} | ICU with AC or HDU |
| SURGICAL | {infra_by_cat.get('SURGICAL',0)} | Fully equipped OT |
| INJURY | {infra_by_cat.get('INJURY',0)} | Casualty AND OT |
| MATERNAL_NEONATAL | {infra_by_cat.get('MATERNAL_NEONATAL',0)} | Labour room |
| COMMUNICABLE | {infra_by_cat.get('COMMUNICABLE',0)} | General ward or Casualty |
| OTHER | {infra_by_cat.get('OTHER',0)} | General ward |

### Top 12 Blocks with Infrastructure Mismatch

{disease_tbl}

---

## 4. Patient Flow and Portability

**Policy question:** Where are beneficiaries going for care? What does the flow pattern reveal about local gaps?

{n4}

### Flow Distribution (State-wide)

| Flow Category | Cases | Share |
|---------------|-------|-------|
| Same block | {int(a4b['cases_same_block'].sum())} | {pct(same_block_rate)} |
| Same district, different block | {int(a4b['cases_same_district'].sum())} | {pct(float(a4b['cases_same_district'].sum()/a4b['total_cases'].sum()))} |
| Different district, same division | {int(a4b['cases_diff_district'].sum())} | {pct(float(a4b['cases_diff_district'].sum()/a4b['total_cases'].sum()))} |
| Out of state (portability) | {int(a4b['cases_out_of_state'].sum())} | {pct(oos_rate)} |

### Top 12 Highest-Leakage Blocks

{flow_tbl}

### District Net Patient Flow (Importers vs Exporters)

{dist_net_tbl}

---

## 5. Enrolment-to-Card Activation Drop-off

**Policy question:** Are there blocks where beneficiaries enrol but fail to receive an active Ayushman Card?

{n5}

### Drop-off Summary

| Metric | Value |
|--------|-------|
| State-wide card activation rate | {pct(card_act_rate)} |
| Blocks above 75th percentile drop-off | {high_dropoff} |
| State-wide enrolment rejection rate | {pct(float(a5['enrolment_rejected_count'].sum()/a5['total_beneficiaries'].sum()))} |
| Beneficiaries without any card | {int(a5['beneficiaries_no_card'].sum()):,} |
| Beneficiaries with inactive/disabled card | {int(a5['beneficiaries_inactive_card'].sum()):,} |

### Top 12 High Drop-off Blocks

{card_tbl}

---

## 6. Repeat Utilization Patterns

**Policy question:** Which blocks have high repeat admissions, potentially signalling chronic disease burden or ineffective initial treatment?

{n6}

### Repeat Utilization Summary

| Metric | Value |
|--------|-------|
| State-wide repeat utilization rate | {pct(state_repeat_rate)} |
| Blocks with high repeat rate (>75th pct) | {int(a6['high_repeat_rate'].sum())} |
| Blocks flagged for treatment failure | {int(a6['possible_treatment_failure'].sum())} |
| Total same-procedure same-hospital repeat pairs | {int(a6['same_proc_same_hosp_pairs_total'].sum()):,} |
| Total same-procedure different-hospital pairs | {int(a6['same_proc_diff_hosp_pairs_total'].sum()):,} |

---

## 7. Seasonal Demand Patterns

**Policy question:** Do certain blocks experience seasonal demand surges that may overwhelm local capacity?

{n7}

### Seasonality Summary

| Metric | Value |
|--------|-------|
| Blocks meeting analysis threshold | {int(a7s['meets_threshold'].sum())} of {total_blocks} |
| Blocks with at least one surge month | {seasonal_blocks} ({pct(seasonal_blocks/total_blocks)}) |
| Peak calendar months | August (month 8), July (month 7), September (month 9) |
| Dominant surge disease | Communicable diseases |

### Most Seasonal Blocks (by Coefficient of Variation)

{seasonal_tbl}

---

## 8. Delisted Hospital Impact

**Policy question:** Which blocks have lost effective hospital capacity due to scheme delisting?

{n8}

### Delisted Hospital Detail

{delisted_tbl}

---

## 9. Policy Recommendations

{recommendations}

---

## Appendix: Files Generated

| File | Description | Rows |
|------|-------------|------|
| `gap_utilization_scores.parquet` | Block-level utilization gap scoring | {len(a1):,} |
| `gap_specialty_matrix.parquet` | Block × specialty supply gap matrix | {len(a2):,} |
| `gap_disease_burden.parquet` | Disease burden vs infrastructure mismatch | {len(a3):,} |
| `gap_portability_flows.parquet` | Block-level patient retention/leakage | {len(a4b):,} |
| `gap_district_patient_flows.parquet` | District-to-district flow matrix | {len(a4d):,} |
| `gap_card_dropoff.parquet` | Enrolment-to-card activation analysis | {len(a5):,} |
| `gap_repeat_utilization.parquet` | Repeat utilization per block | {len(a6):,} |
| `gap_seasonal_patterns.parquet` | Block × month surge flags | {len(a7p):,} |
| `gap_seasonal_summary.parquet` | Block-level seasonal profile | {len(a7s):,} |
| `gap_delisted_impact.parquet` | Delisted hospital capacity impact | {len(a8):,} |

---

*Analysis based on synthetic PM-JAY data for Uttar Pradesh. All findings are for
demonstration and research purposes. No real beneficiary data is included.*
"""

REPORT_MD.write_text(report, encoding="utf-8")
print(f"\nReport written: {REPORT_MD}  ({len(report):,} chars)", flush=True)
print("[DONE]", flush=True)
