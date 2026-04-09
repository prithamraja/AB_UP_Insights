# =============================================================================
# Phase 5c: Generate Five Gamma-Level Reports for Frontend
# =============================================================================
# Produces one markdown report per gamma value (0.1, 0.3, 0.5, 0.7, 0.9),
# each covering the top 30 ranked insights per view, using the actionable
# format (bold leadline + numbered bullets).
#
# Outputs:
#   reports/gamma_0.1_report.md
#   reports/gamma_0.3_report.md
#   reports/gamma_0.5_report.md
#   reports/gamma_0.7_report.md
#   reports/gamma_0.9_report.md
#
# Run from Metainsights_anomalies/:
#   python src/phase5c_gamma_reports.py
# =============================================================================

import os
import sys
import json
import copy
import math

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
from openai import OpenAI

from phase2_engine import load_candidates
from phase4a_engine import VIEW1_CONFIG, VIEW2_CONFIG, VIEW3_CONFIG, VIEW4_CONFIG
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

VIEW_ORDER = [
    ("view1", "Claims Processing & Treatment Patterns"),
    ("view2", "District-Level Monthly Performance Trends"),
    ("view3", "Hospital Infrastructure & Specialty Capacity"),
    ("view4", "Beneficiary Enrolment & Scheme Uptake"),
]

GAMMA_VALUES = [0.1, 0.3, 0.5, 0.7, 0.9]
K_PER_VIEW = 30

# Conciseness parameters (same as phase5b)
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
# RESCORE
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


# =============================================================================
# LLM PROMPT
# =============================================================================

def build_finding_dict(candidate) -> dict:
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


def build_prompt(view_name: str, ranked_candidates: list, gamma: float) -> str:
    view_info = VIEW_DESCRIPTIONS[view_name]
    findings_json = json.dumps(
        [build_finding_dict(c) for c in ranked_candidates],
        indent=2, default=str,
    )

    # Adjust tone based on gamma
    if gamma <= 0.3:
        tone = "broad programme patterns — what holds true across the state"
        headline_guidance = (
            "For universal patterns (no exceptions), the headline states what's consistent and why it matters. "
            "For patterns with exceptions, mention the exceptions by name."
        )
    elif gamma <= 0.5:
        tone = "a mix of broad patterns and targeted anomalies"
        headline_guidance = (
            "Balance broad patterns with exception-focused insights. "
            "Where exceptions exist, name the specific districts/entities."
        )
    else:
        tone = "specific anomalies and deviations — where things break from the norm"
        headline_guidance = (
            "Focus on where the pattern breaks. The headline must name the exception(s) and state what's different. "
            "Universal patterns (no exceptions) should still be included but framed around what's noteworthy."
        )

    return f"""You are writing an analytical report section on the Ayushman Bharat PM-JAY health insurance scheme in Uttar Pradesh, India.

## Your Audience
A senior state programme officer who manages PM-JAY operations across UP. She is non-technical but understands healthcare operations and programme metrics.

## Tone
This report focuses on {tone}.

## This Section: {view_info['title']}

{view_info['description']}

## Column Glossary
{json.dumps(view_info['column_glossary'], indent=2)}

## Findings (ranked by importance)

{findings_json}

## Instructions

Write insights for ALL findings provided. Follow this exact format:

1. STRUCTURE: Present each insight (or closely related group of 2-3 insights) as:
   - A **one-line headline** in bold that tells the full story in one sentence. The reader should understand the insight completely from this line alone.
   - **Numbered bullets** using markdown numbered list syntax (1. 2. 3.) with 3-5 items of supporting evidence, specific numbers, and context.

2. EXAMPLE FORMAT:

   **Cardiology and Orthopaedics dominate PM-JAY spending in 17 of 18 divisions -- except Basti, where General Surgery leads instead.**

   1. Statewide, Cardiology accounts for INR 401.9 crore (39.4%) and Orthopaedics INR 260.2 crore (25.5%) of total claim amounts.
   2. This pattern holds across 17 of 18 divisions -- every division except Basti.
   3. In Basti, General Surgery overtakes both, accounting for 34% of local claims vs Cardiology at 28%.
   4. Implication: Basti's different specialty mix may reflect local hospital capabilities, referral patterns, or coding practices worth reviewing.

3. HEADLINE RULES:
   - Must be a single sentence
   - {headline_guidance}
   - Must be self-contained -- a reader who only reads headlines should get the full picture
   - Use specific entity names: district names, specialty names, hospital types -- not "some districts"

4. BULLET RULES:
   - Every bullet must contain a specific number from the stats
   - Use INR and crore/lakh for financial amounts
   - The last bullet in each group should be an "Implication" -- what this means operationally
   - Keep each bullet to one line where possible

5. GENERAL RULES:
   - Spell out specialty codes on first use (e.g., Cardiology (CARD))
   - Do NOT mention scores, conciseness, impact, HDP, extending strategies, or technical terms
   - Do NOT invent numbers not in the stats
   - Cover ALL {len(ranked_candidates)} findings — do not skip any
   - You may group 2-3 very closely related findings under one headline
"""


# =============================================================================
# MAIN PIPELINE
# =============================================================================

def main():
    os.makedirs(os.path.join(BASE_DIR, "reports"), exist_ok=True)
    client = OpenAI()

    # Load candidates once (shared across all gamma values)
    print("Loading candidates ...")
    raw_candidates = {}
    for view_name in ["view1", "view2", "view3", "view4"]:
        path = os.path.join(BASE_DIR, "metainsights", f"{view_name}_candidates.json")
        raw_candidates[view_name] = load_candidates(path)
        print(f"  {view_name}: {len(raw_candidates[view_name]):,} candidates")

    for gamma in GAMMA_VALUES:
        print(f"\n{'='*60}")
        print(f"GAMMA = {gamma}")
        print(f"{'='*60}")

        # Step 1: Rescore + rank
        ranked = {}
        for view_name in ["view1", "view2", "view3", "view4"]:
            candidates = load_candidates(
                os.path.join(BASE_DIR, "metainsights", f"{view_name}_candidates.json")
            )
            rescored = rescore_candidates(candidates, gamma=gamma)
            filtered = prefilter_candidates(rescored, max_candidates=5000)
            ranked[view_name] = rank_metainsights(filtered, k=K_PER_VIEW)
            n_exc = sum(1 for c in ranked[view_name] if c.exceptions)
            print(f"  {view_name}: {len(ranked[view_name])} ranked, {n_exc} with exceptions")

        # Step 2: Enrich with stats
        print("  Enriching with stats ...")
        enriched = {}
        for view_name, view_ranked in ranked.items():
            config = ALL_CONFIGS[view_name]
            as_dicts = [c.to_dict() if hasattr(c, "to_dict") else c for c in view_ranked]
            enriched[view_name] = enrich_candidates_with_stats(view_name, as_dicts, config)

        # Step 3: Generate report via LLM
        print("  Generating report ...")
        sections = [
            f"# PM-JAY Uttar Pradesh — Gamma {gamma}\n\n---\n"
        ]

        for view_name, view_title in VIEW_ORDER:
            print(f"    {view_title} ...")
            prompt = build_prompt(view_name, enriched[view_name], gamma)
            response = client.chat.completions.create(
                model="gpt-5.4-mini",
                max_completion_tokens=5000,
                messages=[{"role": "user", "content": prompt}],
            )
            sections.append(f"\n## {view_title}\n\n")
            sections.append(response.choices[0].message.content)
            sections.append("\n\n---\n")

        report_path = os.path.join(BASE_DIR, "reports", f"gamma_{gamma}_report.md")
        with open(report_path, "w", encoding="utf-8") as f:
            f.write("".join(sections))
        print(f"  -> {report_path}")

    print("\nDone. Generated 5 gamma reports.")


if __name__ == "__main__":
    main()
