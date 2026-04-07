# Phase 5b: Executive MetaInsight Report (LLM-Generated)

## Overview

This phase takes the ranked MetaInsight candidates from Phase 5 (Layer 3P) and uses an LLM to generate a readable executive report for a non-technical audience — specifically, a state-level PM-JAY programme officer in Uttar Pradesh.

The current template-based NL output says things like:
> "Across all hospital_sub_type values, CARD and ORTH lead in amount_claimed among specialty_code values"

The target output should say:
> "Cardiology and Orthopaedics consistently generate the highest claim amounts regardless of hospital type — this holds across government hospitals, private hospitals, trusts, NGOs, and all other facility categories. No hospital type breaks this pattern."

**Inputs:**
- `metainsights/view1_ranked.json`
- `metainsights/view2_ranked.json`
- `metainsights/view3_ranked.json`
- `metainsights/view4_ranked.json`
- `reports/layer3p_ranked_dashboard.txt` (for context)

**Outputs:**
- `reports/executive_metainsight_report.md` — the final readable report

**Dependency:** Anthropic API (`claude-sonnet-4-20250514`)

---

## Design

### What the LLM Does

For each view's ranked list, the LLM receives:
1. The structured MetaInsight data (pattern type, commonness, exceptions, scores)
2. A view description (what this data represents, what the columns mean)
3. Instructions on tone, audience, and formatting

The LLM does NOT re-analyse the data or run queries. It translates already-validated structured knowledge into clear prose.

### What the LLM Does NOT Do

- No hallucination risk — the LLM is given exact numbers, exact entities, exact patterns
- No analytical judgment — the ranking is pre-computed; the LLM just presents in rank order
- No data access — it works entirely from the JSON output of Phase 5

---

## Implementation

### Step 1: Prepare Context Per View

```python
VIEW_DESCRIPTIONS = {
    "view1": {
        "title": "Claims Processing & Treatment Patterns",
        "description": (
            "This view analyses 22,500 hospital treatment cases under PM-JAY in Uttar Pradesh. "
            "Each case represents one patient admission at an empanelled hospital. "
            "The data covers admissions from 2022 to 2025 across 75 districts, 18 divisions, "
            "800+ hospitals, and 11 medical specialties."
        ),
        "audience_context": (
            "Key questions for the programme officer: Which specialties drive the most spending? "
            "Are there districts or hospital types with unusual patterns? "
            "Are claim processing times consistent?"
        ),
        "column_glossary": {
            "specialty_code": "Medical specialty (e.g., CARD=Cardiology, ORTH=Orthopaedics, GS=General Surgery, OBG=Obstetrics & Gynaecology, MED=General Medicine, etc.)",
            "amount_claimed": "Total amount (INR) claimed by hospitals for treatments",
            "amount_approved": "Total amount (INR) approved after review",
            "amount_paid": "Total amount (INR) actually disbursed to hospitals",
            "base_amount": "Standard package price for the procedure",
            "case_count": "Number of treatment cases",
            "length_of_stay": "Average days of hospitalisation per case",
            "settlement_tat_days": "Average turnaround time (days) to settle a claim",
            "discharge_type": "How the patient left: NORMAL (recovered), LAMA (left against medical advice), DAMA (discharged against medical advice), DEATH, LIVE (ongoing)",
            "claim_status": "Current state: APPROVED, SETTLED (paid), REJECTED, QUERY_RAISED, PENDING",
            "preauth_status": "Pre-authorisation status: AUTO_APPROVED, APPROVED, QUERY_RAISED, REJECTED",
            "division": "Administrative division of UP (18 total, e.g., Lucknow, Gorakhpur, Meerut)",
            "district": "Administrative district (75 total)",
            "hospital_type": "PUBLIC or PRIVATE",
            "hospital_sub_type": "Facility category: CHC, PHC, Civil Hospital, District Hospital, Medical College, Private, Trust, NGO",
            "disease_category": "Broad disease grouping: COMMUNICABLE, NCD, SURGICAL, MATERNAL_NEONATAL, INJURY",
            "admission_type": "ELECTIVE or EMERGENCY",
            "bed_size_bucket": "Hospital bed capacity: SMALL (<=30), MEDIUM (31-100), LARGE (101-300), VERY_LARGE (300+)",
            "query_count": "Number of clarification queries raised during claim processing",
            "is_emergency": "Whether the case was an emergency admission (0/1)",
            "is_death": "Whether the patient died during treatment (0/1)",
            "is_lama_dama": "Whether the patient left or was discharged against medical advice (0/1)",
        },
    },
    "view2": {
        "title": "District-Level Monthly Performance Trends",
        "description": (
            "This view tracks monthly performance metrics for each of the 75 districts, "
            "spanning approximately 50 months (2022-2025). It captures enrolment activity, "
            "claims processing, financial flows, and utilisation rates at the district-month level."
        ),
        "audience_context": (
            "Key questions: Are enrolments growing or declining? Which districts are underperforming? "
            "Are there seasonal patterns in claims? Has utilisation changed over time?"
        ),
        "column_glossary": {
            "new_beneficiaries": "Number of new beneficiaries enrolled that month in the district",
            "new_households": "Number of new households enrolled",
            "cases_admitted": "Number of hospital admissions under PM-JAY",
            "claims_per_1000_beneficiaries": "Utilisation rate: claims per 1,000 enrolled beneficiaries",
            "cumulative_beneficiaries": "Running total of enrolled beneficiaries in the district",
            "approval_rate": "Proportion of claims that were approved",
            "emergency_share": "Proportion of cases that were emergency admissions",
            "death_rate": "Proportion of cases resulting in patient death",
            "public_private_ratio": "Ratio of public to private hospital cases",
            "amount_claimed": "Total INR claimed in the district that month",
            "amount_paid": "Total INR disbursed to hospitals",
            "cards_issued": "Number of Ayushman cards issued",
            "month": "Calendar month (e.g., 2023-03)",
            "quarter": "Calendar quarter (e.g., 2023Q1)",
            "year": "Calendar year",
            "division": "Administrative division (18 total)",
            "district": "Administrative district (75 total)",
        },
    },
    "view3": {
        "title": "Hospital Infrastructure & Specialty Capacity",
        "description": (
            "This view examines 800 empanelled hospitals and their offered specialties (7,336 hospital-specialty pairs). "
            "It captures bed capacity, staffing, licensing, accreditation, and treatment volumes per hospital per specialty."
        ),
        "audience_context": (
            "Key questions: Are hospitals adequately staffed and licensed? Which specialties are underutilised? "
            "Are there capacity gaps in certain districts or hospital types?"
        ),
        "column_glossary": {
            "specialty_code": "Medical specialty offered (15 specialties including CARD, ORTH, GS, MED, OBG, ENT, OPTH, PEDS, NEURO, BURNS, DERM, PSYCH, URO, PULM, ONCO)",
            "total_bed_strength": "Total beds in the hospital",
            "inpatient_beds": "Beds designated for inpatient care",
            "cases_treated": "Number of PM-JAY cases treated at this hospital in this specialty",
            "cases_per_bed": "Utilisation rate: PM-JAY cases per bed",
            "total_staff": "Number of clinical staff at the hospital",
            "avg_experience_years": "Average years of experience of clinical staff",
            "total_licenses": "Total professional licenses held by the hospital",
            "expired_licenses": "Number of expired licenses",
            "active_licenses": "Number of currently valid licenses",
            "zero_claim_flag": "Whether this hospital-specialty combination had zero PM-JAY claims (1=yes)",
            "amount_claimed": "Total INR claimed for this specialty at this hospital",
            "hospital_type": "PUBLIC or PRIVATE",
            "hospital_sub_type": "Facility category",
            "bed_size_bucket": "Hospital size category",
            "division": "Administrative division",
            "district": "Administrative district",
        },
    },
    "view4": {
        "title": "Beneficiary Enrolment & Scheme Uptake",
        "description": (
            "This view covers all 205,847 enrolled beneficiaries in UP. It tracks enrolment quality, "
            "documentation status, card issuance, and whether beneficiaries actually used the scheme."
        ),
        "audience_context": (
            "Key questions: What proportion of enrolled beneficiaries actually file claims? "
            "Are there demographic or geographic gaps in scheme uptake? "
            "How long does card issuance take?"
        ),
        "column_glossary": {
            "has_claim": "Number of beneficiaries who filed at least one claim",
            "claim_count": "Total claims filed by beneficiaries in this group",
            "claim_rate": "Proportion of beneficiaries who filed at least one claim",
            "has_aadhaar": "Proportion of beneficiaries with Aadhaar linked",
            "days_enrolment_to_card": "Average days between enrolment and card issuance",
            "days_card_to_first_claim": "Average days between card issuance and first hospital visit",
            "document_count": "Average number of identity documents per beneficiary",
            "gender": "M or F",
            "age_group": "15-25, 26-40, 41-60, 60+",
            "entitlement_source": "How the beneficiary was identified: SECC (census), STATE_DB (state database), RSBY (previous scheme)",
            "bis_record_status": "Data quality status: GOLD (verified), SILVER (partial), PENDING",
            "enrolment_status": "How enrolment was approved: AUTO_APPROVED, ISA_APPROVED, SHA_APPROVED, REJECTED",
            "card_status": "Current card status: ACTIVE, INACTIVE, DISABLED",
            "document_count_bucket": "1_DOC or 2-3_DOCS",
            "division": "Administrative division",
            "district": "Administrative district",
        },
    },
}
```

### Step 2: Enrich Candidates with Quantitative Stats

The ranked candidates contain pattern structure (who's #1, who's an exception) but not the actual numbers. Before sending to the LLM, we query the underlying data to attach summary statistics.

```python
import pandas as pd

def enrich_candidates_with_stats(
    view_name: str,
    ranked_candidates: list[dict],
    config: ViewConfig,
) -> list[dict]:
    """
    For each ranked candidate, compute the actual distribution values
    so the LLM can cite specific numbers.
    
    Adds a 'stats' field to each candidate with:
    - distribution: {breakdown_value: aggregated_value, ...} (top 5 + bottom 2)
    - total: total across all breakdown values
    - shares: {breakdown_value: percentage, ...} (for SUM measures)
    - highlight_value: the actual value of the highlighted breakdown value(s)
    - highlight_share: percentage share of highlighted value(s)
    """
    df = pd.read_parquet(config.parquet_path)
    
    enriched = []
    for candidate in ranked_candidates:
        c = candidate.copy()
        
        breakdown = c["breakdown"]
        measure = c["measure"]
        base_subspace = c["base_subspace"]
        
        # Skip measure-extending and breakdown-extending (measure/breakdown = "(varies)")
        if measure == "(varies)" or breakdown == "(varies)":
            c["stats"] = {"note": "Varies across members — see individual patterns"}
            enriched.append(c)
            continue
        
        # Apply base subspace filter
        filtered = df.copy()
        if isinstance(base_subspace, list):
            for dim, val in base_subspace:
                filtered = filtered[filtered[dim] == val]
        
        # Aggregate
        agg_type = config.get_agg(measure)
        if agg_type == "avg":
            dist = filtered.groupby(breakdown)[measure].mean()
        else:
            dist = filtered.groupby(breakdown)[measure].sum()
        
        dist = dist.sort_values(ascending=False)
        
        if len(dist) == 0:
            c["stats"] = {"note": "No data after filtering"}
            enriched.append(c)
            continue
        
        total = dist.sum()
        
        # Build stats
        stats = {}
        
        # Top 5 and bottom 2 values
        top_entries = {}
        for label, val in dist.head(5).items():
            share = (val / total * 100) if total > 0 else 0
            top_entries[str(label)] = {
                "value": round(float(val), 2),
                "share_pct": round(share, 1),
            }
        
        bottom_entries = {}
        for label, val in dist.tail(2).items():
            share = (val / total * 100) if total > 0 else 0
            bottom_entries[str(label)] = {
                "value": round(float(val), 2),
                "share_pct": round(share, 1),
            }
        
        stats["top_values"] = top_entries
        stats["bottom_values"] = bottom_entries
        stats["total"] = round(float(total), 2)
        stats["count_breakdown_values"] = len(dist)
        stats["agg_type"] = agg_type
        
        # Highlight-specific stats
        if c["commonness_sets"]:
            cs = c["commonness_sets"][0]
            highlight = cs.get("highlight", "")
            
            # Try to extract the highlighted value(s)
            try:
                import ast
                hl = ast.literal_eval(highlight) if isinstance(highlight, str) else highlight
            except (ValueError, SyntaxError):
                hl = ()
            
            if isinstance(hl, tuple) and len(hl) > 0 and hl[0] != "EVEN":
                highlight_vals = {}
                for h in hl:
                    if h in dist.index:
                        val = float(dist[h])
                        share = (val / total * 100) if total > 0 else 0
                        highlight_vals[str(h)] = {
                            "value": round(val, 2),
                            "share_pct": round(share, 1),
                        }
                stats["highlight_values"] = highlight_vals
        
        # For AVG measures, add count of non-null values
        if agg_type == "avg":
            non_null_counts = filtered.groupby(breakdown)[measure].count()
            stats["sample_sizes"] = {
                str(k): int(v) for k, v in non_null_counts.head(5).items()
            }
        
        c["stats"] = stats
        enriched.append(c)
    
    return enriched
```

### Step 4: Build LLM Prompt Per View

```python
def build_view_prompt(view_name: str, ranked_candidates: list[dict]) -> str:
    """Build the prompt for generating the executive summary for one view."""
    
    view_info = VIEW_DESCRIPTIONS[view_name]
    
    # Format the ranked candidates as structured text
    findings = []
    for i, candidate in enumerate(ranked_candidates):
        c = candidate if isinstance(candidate, dict) else candidate.to_dict()
        
        finding = {
            "rank": i + 1,
            "pattern_type": c["pattern_type"],
            "extending_strategy": c["extending_strategy"],
            "extending_dimension": c["extending_dimension"],
            "breakdown": c["breakdown"],
            "measure": c["measure"],
            "base_subspace": c["base_subspace"],
            "hdp_size": c["hdp_size"],
            "commonness_sets": c["commonness_sets"],
            "exceptions": c["exceptions"],
            "score": c["score"],
            "conciseness": c["conciseness"],
            "impact": c["impact"],
        }
        
        # Include quantitative stats if available
        if "stats" in c:
            finding["stats"] = c["stats"]
        
        findings.append(finding)
    
    findings_json = json.dumps(findings, indent=2, default=str)
    
    prompt = f"""You are writing the findings section of an analytical report on the Ayushman Bharat PM-JAY health insurance scheme in Uttar Pradesh, India.

## Your Audience
A senior state programme officer who manages PM-JAY operations across UP. She is non-technical — she understands healthcare operations, district administration, and programme metrics, but not data science terminology. She wants to know: what did the data reveal, why does it matter, and what should she look into further.

## This Section: {view_info['title']}

{view_info['description']}

{view_info['audience_context']}

## Column Glossary
{json.dumps(view_info['column_glossary'], indent=2)}

## Ranked Findings (from automated pattern analysis)

The following findings were automatically discovered and ranked by analytical importance. Each finding represents a pattern that holds consistently across multiple subgroups, with any exceptions noted.

Key concepts in the data:
- "commonness" = a pattern that holds for the majority of subgroups (e.g., "in 73 out of 75 districts, Cardiology has the highest claim amounts")
- "exceptions" = specific subgroups where the pattern breaks (e.g., "except in Lalitpur and Kushinagar, where a different pattern holds")
- "HIGHLIGHT_CHANGE" exception = the same type of pattern exists but with a different leading value
- "TYPE_CHANGE" exception = a completely different pattern applies
- "NO_PATTERN" exception = no clear pattern exists in that subgroup

{findings_json}

## Instructions

Write a clear, readable summary of these findings for the programme officer. Follow these rules:

1. STRUCTURE: Organize findings into 3-5 thematic groups (e.g., "Financial Patterns", "Temporal Trends", "Geographic Variations"). Don't list findings by rank number.

2. LANGUAGE:
   - Use plain English, no jargon
   - Spell out specialty codes on first use (e.g., "Cardiology (CARD)")
   - Explain what each finding means operationally, not just statistically
   - Use INR/rupees for financial amounts where relevant
   - Name specific districts/divisions when they appear as exceptions

3. EXCEPTIONS ARE THE STORY: Universal patterns (100% commonness) are context. The exceptions are where actionable intelligence lives. Highlight exceptions prominently — "this pattern holds everywhere EXCEPT in X, which deserves investigation."

4. TONE: Professional, direct, advisory. Not academic. Think of a trusted analyst briefing a decision-maker.

5. LENGTH: 400-800 words per view section. Be concise but complete.

6. DO NOT:
   - Mention scores, conciseness, impact, HDP, extending strategies, or any technical MetaInsight terminology
   - Invent information not present in the findings
   - Speculate about causes unless the data directly supports it
   - Use bullet points for the main narrative (short lists for exceptions are OK)

7. DO:
   - Start with the most important headline finding
   - Connect related findings into a narrative
   - **Use specific numbers from the 'stats' field**: cite actual values, percentages, and shares wherever available. For example, instead of "Cardiology leads in spending," write "Cardiology accounts for 28.3% of total claim amounts (₹X.X crore), followed by Orthopaedics at 24.1%." If stats.highlight_values is present, always cite those numbers. If stats.top_values is present, use the share_pct values.
   - For AVG measures, mention the actual average values (e.g., "average length of stay is 4.2 days")
   - End with 2-3 specific follow-up questions the officer should investigate
   - Use formatting: bold for key entities, section headers for thematic groups
"""
    
    return prompt
```

### Step 5: Call the LLM and Assemble Report

```python
import json
from anthropic import Anthropic

def generate_executive_report(
    all_ranked: dict[str, list],
    all_configs: dict[str, ViewConfig],
    output_path: str,
):
    """Generate the full executive report using Claude."""
    
    client = Anthropic()
    
    report_sections = []
    
    # Report header
    report_sections.append(
        "# PM-JAY Uttar Pradesh — Analytical Findings Report\n\n"
        "*Automated MetaInsight Analysis*\n\n"
        "---\n"
    )
    
    view_order = [
        ("view1", "Claims Processing & Treatment Patterns"),
        ("view2", "District-Level Monthly Performance Trends"),
        ("view3", "Hospital Infrastructure & Specialty Capacity"),
        ("view4", "Beneficiary Enrolment & Scheme Uptake"),
    ]
    
    for view_name, view_title in view_order:
        print(f"Generating section: {view_title}...")
        
        ranked = all_ranked[view_name]
        config = all_configs[view_name]
        
        # Enrich with quantitative stats
        enriched = enrich_candidates_with_stats(view_name, ranked, config)
        
        prompt = build_view_prompt(view_name, enriched)
        
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=2000,
            messages=[{"role": "user", "content": prompt}],
        )
        
        section_text = response.content[0].text
        
        report_sections.append(f"\n## {view_title}\n\n")
        report_sections.append(section_text)
        report_sections.append("\n\n---\n")
    
    # Write report
    full_report = "".join(report_sections)
    with open(output_path, "w") as f:
        f.write(full_report)
    
    print(f"\nExecutive report -> {output_path}")
    return full_report
```

### Step 6: Run

```python
import json

if __name__ == "__main__":
    import os
    os.makedirs("reports", exist_ok=True)
    
    views = ["view1", "view2", "view3", "view4"]
    all_ranked = {}
    all_configs = {
        "view1": VIEW1_CONFIG,
        "view2": VIEW2_CONFIG,
        "view3": VIEW3_CONFIG,
        "view4": VIEW4_CONFIG,
    }
    
    for view_name in views:
        path = f"metainsights/{view_name}_ranked.json"
        with open(path) as f:
            all_ranked[view_name] = json.load(f)
    
    generate_executive_report(all_ranked, all_configs, "reports/executive_metainsight_report.md")
```

---

## Example: What Good Output Looks Like

Given View 1 finding #2 (CARD and ORTH lead in amount_claimed across all divisions), enriched with stats showing CARD=28.3% share, ORTH=24.1% share:

**Template output (Phase 5):**
> "Across all division values, CARD and ORTH lead in amount_claimed among specialty_code values"

**LLM output with stats (Phase 5b):**
> **Cardiology and Orthopaedics dominate scheme spending.** Across all 18 administrative divisions in UP, these two specialties consistently generate the highest claim amounts — Cardiology accounts for 28.3% of total claims and Orthopaedics for 24.1%, together making up over half of all PM-JAY spending. This pattern holds uniformly regardless of division, with no exceptions. The likely driver is the high cost of cardiac procedures (stents, bypass) and orthopaedic surgeries (joint replacements, fracture management). Given that these two specialties alone account for ₹52 out of every ₹100 claimed, programme officers should ensure that package rates are regularly benchmarked against actual costs and that pre-authorisation scrutiny is proportionate to the financial exposure.

---

## Validation

- [ ] Report is readable by a non-technical audience
- [ ] No MetaInsight jargon (HDP, extending strategy, commonness set, etc.)
- [ ] Specialty codes are spelled out (CARD → Cardiology)
- [ ] Exceptions are highlighted with specific entity names
- [ ] No hallucinated facts — every claim in the report traces to a finding in the input
- [ ] Each section is 400-800 words
- [ ] Follow-up questions are specific and actionable
- [ ] Report renders correctly as Markdown

### What to bring back

1. `reports/executive_metainsight_report.md` — the full report
2. Any instances where the LLM added information not in the findings
3. Any findings that were dropped or misrepresented
4. Your assessment: would a PM-JAY officer find this useful?
