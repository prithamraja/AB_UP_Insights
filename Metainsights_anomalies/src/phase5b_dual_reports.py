# =============================================================================
# Phase 5b (Revised): Dual Executive Reports
# =============================================================================
# Generates two complementary reports from the same MetaInsight candidates:
#
#   1. Overview Report (gamma=0.1)
#      Status briefing with leadline paragraphs + bullet-point facts.
#      Answers: "What's broadly true about PM-JAY in UP?"
#
#   2. Actionable Insights Report (gamma=0.5)
#      Investigation brief with bold one-line headlines + numbered evidence.
#      Answers: "Where do things break, and what should we look into?"
#
# Both reports are generated from the same candidate JSONs, rescored
# with the appropriate gamma value, then enriched with quantitative
# stats from the parquet files before being sent to the LLM.
#
# Outputs:
#   reports/overview_report.md
#   reports/actionable_insights_report.md
#
# Run from Metainsights_anomalies/:
#   python src/phase5b_dual_reports.py
# =============================================================================

import os
import sys
import math
import json
import copy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
from openai import OpenAI

from phase2_engine import MetaInsightCandidate, Subspace, load_candidates
from phase4a_engine import VIEW1_CONFIG, VIEW2_CONFIG, VIEW3_CONFIG, VIEW4_CONFIG, ViewConfig
from phase5_ranking import rank_metainsights, prefilter_candidates
from phase5b_report import VIEW_DESCRIPTIONS, enrich_candidates_with_stats

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(os.path.dirname(BASE_DIR), ".env"))

ALL_CONFIGS = {
    "view1": VIEW1_CONFIG,
    "view2": VIEW2_CONFIG,
    "view3": VIEW3_CONFIG,
    "view4": VIEW4_CONFIG,
}

# Fixed conciseness parameters
TAU = 0.5
R   = 1.0
K   = 3

_tau_r     = TAU ** (1.0 / R)
_threshold = (1 - TAU) * math.e / _tau_r
S_STAR = (
    -TAU * math.log2(TAU)
    - R * (1 - TAU) * math.log2((1 - TAU) / K)
) if K >= _threshold else (
    -math.log2(TAU)
    + R * (K * _tau_r / math.e) * math.log2(math.e / (K * _tau_r))
)


# =============================================================================
# STEP 1: RESCORE + DUAL RANKINGS
# =============================================================================

def rescore_candidates(candidates: list, gamma: float) -> list:
    """Deep-copy candidates and recompute conciseness + score with new gamma."""
    rescored = []
    for c in candidates:
        c2 = copy.deepcopy(c)
        n = c2.hdp_size

        alphas = [cs["proportion"] for cs in c2.commonness_sets]

        exc_cats: dict = {}
        for exc in c2.exceptions:
            exc_cats[exc["category"]] = exc_cats.get(exc["category"], 0) + 1
        betas = [count / n for count in exc_cats.values()] if n > 0 else []

        s = 0.0
        for a in alphas:
            if a > 0:
                s -= a * math.log2(a)
        for b in betas:
            if b > 0:
                s -= R * b * math.log2(b)

        has_exc = len(c2.exceptions) > 0
        s_reg = s + gamma * (0.0 if has_exc else 1.0)
        c2.conciseness = max(0.0, 1.0 - s_reg / S_STAR) if S_STAR > 0 else 1.0
        c2.score = c2.conciseness * c2.impact
        rescored.append(c2)
    return rescored


def generate_dual_rankings():
    """Load candidates, rescore with gamma=0.1 and 0.5, rank both."""
    views = ["view1", "view2", "view3", "view4"]
    overview_ranked = {}
    actionable_ranked = {}

    for view_name in views:
        path = os.path.join(BASE_DIR, "metainsights", f"{view_name}_candidates.json")
        print(f"Loading {view_name} ...")
        candidates_01 = load_candidates(path)
        candidates_05 = load_candidates(path)
        print(f"  {len(candidates_01):,} candidates")

        rescored_01 = rescore_candidates(candidates_01, gamma=0.1)
        rescored_05 = rescore_candidates(candidates_05, gamma=0.5)

        filtered_01 = prefilter_candidates(rescored_01, max_candidates=5000)
        filtered_05 = prefilter_candidates(rescored_05, max_candidates=5000)

        overview_ranked[view_name] = rank_metainsights(filtered_01, k=15)
        actionable_ranked[view_name] = rank_metainsights(filtered_05, k=15)

        n_act_01 = sum(1 for c in overview_ranked[view_name] if c.exceptions)
        n_act_05 = sum(1 for c in actionable_ranked[view_name] if c.exceptions)
        print(f"  Overview (g=0.1): {n_act_01}/15 actionable")
        print(f"  Actionable (g=0.5): {n_act_05}/15 actionable")

    return overview_ranked, actionable_ranked


# =============================================================================
# STEP 2: ENRICH BOTH LISTS
# =============================================================================

def enrich_all(ranked_dict: dict) -> dict:
    enriched = {}
    for view_name, ranked in ranked_dict.items():
        config = ALL_CONFIGS[view_name]
        as_dicts = [c.to_dict() if hasattr(c, "to_dict") else c for c in ranked]
        enriched[view_name] = enrich_candidates_with_stats(view_name, as_dicts, config)
    return enriched


# =============================================================================
# STEP 3: OVERVIEW REPORT PROMPT (gamma=0.1)
# =============================================================================

def build_finding_dict(candidate: dict) -> dict:
    c = candidate if isinstance(candidate, dict) else candidate.to_dict()
    finding = {
        "pattern_type":        c["pattern_type"],
        "extending_dimension": c["extending_dimension"],
        "breakdown":           c["breakdown"],
        "measure":             c["measure"],
        "base_subspace":       c["base_subspace"],
        "hdp_size":            c["hdp_size"],
        "commonness_sets":     c["commonness_sets"],
        "exceptions":          c["exceptions"],
    }
    if "stats" in c:
        finding["stats"] = c["stats"]
    return finding


def build_overview_prompt(view_name: str, ranked_candidates: list) -> str:
    view_info = VIEW_DESCRIPTIONS[view_name]
    findings_json = json.dumps(
        [build_finding_dict(c) for c in ranked_candidates],
        indent=2, default=str,
    )

    return f"""You are writing the overview section of an analytical report on the Ayushman Bharat PM-JAY health insurance scheme in Uttar Pradesh, India.

## Your Audience
A senior state programme officer who manages PM-JAY operations across UP. She is non-technical but understands healthcare operations and programme metrics. This is a status briefing -- she wants to understand the overall state of the programme before a quarterly review meeting.

## This Section: {view_info['title']}

{view_info['description']}

## Column Glossary
{json.dumps(view_info['column_glossary'], indent=2)}

## Findings (ranked by importance)

{findings_json}

## Instructions

Write a clear overview section. Follow this exact format:

1. STRUCTURE: Group findings into 3-5 thematic areas. Each thematic area has:
   - A **leadline**: 2-3 sentences summarising the theme in plain English. This is a narrative paragraph, not a bullet.
   - **Supporting bullets**: 3-6 bullet points using markdown dash syntax (- ) with specific numbers from the stats field. Each bullet is one fact -- concise, with the number front and centre.

2. EXAMPLE FORMAT:

   ### Spending is concentrated in two specialties

   PM-JAY spending in UP is overwhelmingly driven by Cardiology and Orthopaedics. These two specialties account for nearly two-thirds of all claim amounts, and this pattern holds across every division in the state.

   - Cardiology: INR 401.9 crore claimed (39.4% of total)
   - Orthopaedics: INR 260.2 crore claimed (25.5% of total)
   - Next largest: OBG at INR 8.50 crore, General Surgery at INR 7.22 crore
   - Pattern holds across all 18 divisions with no exceptions
   - Base package amounts show the same concentration: Cardiology at 42.7% of base amount

3. RULES:
   - Use plain English, spell out specialty codes on first use
   - Use INR and crore/lakh for financial amounts. Use plain numbers for counts, days, rates.
   - Every bullet must contain a specific number from the stats
   - Leadlines are narrative (no bullets, no numbers). Bullets are facts (numbers, concise).
   - Do NOT mention scores, conciseness, impact, HDP, extending strategies, or technical terms
   - Do NOT invent numbers not in the stats
   - Do NOT include follow-up questions or recommendations -- this is a factual overview
   - Keep it to 400-700 words total
"""


# =============================================================================
# STEP 4: ACTIONABLE INSIGHTS REPORT PROMPT (gamma=0.5)
# =============================================================================

def build_actionable_prompt(view_name: str, ranked_candidates: list) -> str:
    view_info = VIEW_DESCRIPTIONS[view_name]
    findings_json = json.dumps(
        [build_finding_dict(c) for c in ranked_candidates],
        indent=2, default=str,
    )

    return f"""You are writing the actionable insights section of an analytical report on the Ayushman Bharat PM-JAY health insurance scheme in Uttar Pradesh, India.

## Your Audience
A senior state programme officer preparing for district-level review meetings. She needs to know exactly where things deviate from the norm, which districts or entities are exceptions, and what to investigate. This is an investigation brief, not a status overview.

## This Section: {view_info['title']}

{view_info['description']}

## Column Glossary
{json.dumps(view_info['column_glossary'], indent=2)}

## Findings (ranked by importance, filtered for actionability)

These findings were specifically selected to highlight patterns that hold broadly but break in specific places. The exceptions are the actionable part.

{findings_json}

## Instructions

Write a set of actionable insights. Follow this exact format:

1. STRUCTURE: Present each insight (or closely related group of 2-3 insights) as:
   - A **one-line headline** in bold that tells the full story in one sentence, including the exception. The reader should understand the insight completely from this line alone.
   - **Numbered bullets** using markdown numbered list syntax (1. 2. 3.) with 3-6 items of supporting evidence, specific numbers, and context.

2. EXAMPLE FORMAT:

   **Cardiology and Orthopaedics dominate PM-JAY spending in 17 of 18 divisions -- except Basti, where General Surgery leads instead.**

   1. Statewide, Cardiology accounts for INR 401.9 crore (39.4%) and Orthopaedics INR 260.2 crore (25.5%) of total claim amounts
   2. This pattern holds across 17 of 18 divisions -- every division except Basti
   3. In Basti, General Surgery overtakes both, accounting for 34% of local claims vs Cardiology at 28%
   4. The concentration is even stronger in base package amounts: Cardiology alone is 42.7% of total base amount
   5. Implication: Basti's different specialty mix may reflect local hospital capabilities, referral patterns, or coding practices worth reviewing

3. HEADLINE RULES:
   - Must be a single sentence
   - Must state the broad pattern AND the exception(s) by name
   - Must be self-contained -- a reader who only reads headlines should get the full picture
   - For universal patterns (no exceptions), the headline states what's consistent and why it matters
   - Use specific entity names: district names, specialty names, hospital types -- not "some districts"

4. BULLET RULES:
   - Every bullet must contain a specific number from the stats
   - Use INR and crore/lakh for financial amounts
   - The last bullet in each group should be an "Implication" -- what this means operationally and what to investigate
   - Keep each bullet to one line where possible

5. GENERAL RULES:
   - Spell out specialty codes on first use (e.g., Cardiology (CARD))
   - Do NOT mention scores, conciseness, impact, HDP, extending strategies, or technical terms
   - Do NOT invent numbers not in the stats
   - Present 8-12 insights total (group related findings)
   - Keep it to 600-1000 words total
"""


# =============================================================================
# STEP 6: GENERATE BOTH REPORTS
# =============================================================================

def generate_dual_reports(
    overview_enriched: dict,
    actionable_enriched: dict,
    overview_path: str,
    actionable_path: str,
):
    client = OpenAI()

    view_order = [
        ("view1", "Claims Processing & Treatment Patterns"),
        ("view2", "District-Level Monthly Performance Trends"),
        ("view3", "Hospital Infrastructure & Specialty Capacity"),
        ("view4", "Beneficiary Enrolment & Scheme Uptake"),
    ]

    # --- Overview Report ---
    overview_sections = [
        "# PM-JAY Uttar Pradesh -- Programme Overview\n\n"
        "*Key patterns and structural findings across the scheme*\n\n---\n"
    ]

    for view_name, view_title in view_order:
        print(f"  Overview: {view_title} ...")
        prompt = build_overview_prompt(view_name, overview_enriched[view_name])
        response = client.chat.completions.create(
            model="gpt-5.4-mini",
            max_completion_tokens=2000,
            messages=[{"role": "user", "content": prompt}],
        )
        overview_sections.append(f"\n## {view_title}\n\n")
        overview_sections.append(response.choices[0].message.content)
        overview_sections.append("\n\n---\n")

    os.makedirs(os.path.dirname(overview_path), exist_ok=True)
    with open(overview_path, "w", encoding="utf-8") as f:
        f.write("".join(overview_sections))
    print(f"  Overview report -> {overview_path}")

    # --- Actionable Insights Report ---
    actionable_sections = [
        "# PM-JAY Uttar Pradesh -- Actionable Insights\n\n"
        "*Patterns that hold broadly but break in specific places -- "
        "for investigation and follow-up*\n\n---\n"
    ]

    for view_name, view_title in view_order:
        print(f"  Actionable: {view_title} ...")
        prompt = build_actionable_prompt(view_name, actionable_enriched[view_name])
        response = client.chat.completions.create(
            model="gpt-5.4-mini",
            max_completion_tokens=2500,
            messages=[{"role": "user", "content": prompt}],
        )
        actionable_sections.append(f"\n## {view_title}\n\n")
        actionable_sections.append(response.choices[0].message.content)
        actionable_sections.append("\n\n---\n")

    with open(actionable_path, "w", encoding="utf-8") as f:
        f.write("".join(actionable_sections))
    print(f"  Actionable report -> {actionable_path}")


# =============================================================================
# ENTRY POINT
# =============================================================================

if __name__ == "__main__":
    os.makedirs(os.path.join(BASE_DIR, "reports"), exist_ok=True)

    # Step 1: Dual rankings
    print("Step 1: Generating dual rankings ...")
    overview_ranked, actionable_ranked = generate_dual_rankings()

    # Step 2: Enrich with stats
    print("\nStep 2: Enriching with quantitative stats ...")
    overview_enriched = enrich_all(overview_ranked)
    actionable_enriched = enrich_all(actionable_ranked)

    # Step 3: Generate reports
    print("\nStep 3: Generating LLM reports ...")
    generate_dual_reports(
        overview_enriched,
        actionable_enriched,
        os.path.join(BASE_DIR, "reports", "overview_report.md"),
        os.path.join(BASE_DIR, "reports", "actionable_insights_report.md"),
    )

    print("\nDone.")
