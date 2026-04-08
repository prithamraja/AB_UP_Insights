# =============================================================================
# Gamma Sensitivity Analysis
# =============================================================================
# Re-scores all MetaInsight candidates with different gamma values and
# compares how the top-15 ranked list changes per view.
#
# Gamma controls the actionability penalty in the conciseness formula:
#   s_reg = S + gamma * I(no_exceptions)
# Higher gamma penalises "universal" insights (no exceptions), boosting
# actionable insights (those WITH exceptions) in the rankings.
#
# No engine re-run needed -- all information to recompute conciseness
# is stored in the candidate JSONs.
#
# Outputs:
#   reports/gamma_sensitivity_report.md
#
# Run from Metainsights_anomalies/:
#   python src/gamma_sensitivity.py
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
from phase5_ranking import rank_metainsights, generate_nl_summary, compute_total_use_approx

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(os.path.dirname(BASE_DIR), ".env"))

# Fixed parameters (same as compute_conciseness in phase2_engine.py)
TAU   = 0.5
R     = 1.0
K     = 3

# S* upper bound (constant for these params)
_tau_r     = TAU ** (1.0 / R)
_threshold = (1 - TAU) * math.e / _tau_r
S_STAR = (
    -TAU * math.log2(TAU)
    - R * (1 - TAU) * math.log2((1 - TAU) / K)
) if K >= _threshold else (
    -math.log2(TAU)
    + R * (K * _tau_r / math.e) * math.log2(math.e / (K * _tau_r))
)

GAMMA_VALUES = [0.1, 0.3, 0.5, 0.8]


# =============================================================================
# RESCORE
# =============================================================================

def compute_raw_entropy(candidate: MetaInsightCandidate) -> float:
    """Reconstruct S (raw entropy) from stored commonness_sets and exceptions."""
    n = candidate.hdp_size

    # Commonness proportions (alpha)
    alphas = [cs["proportion"] for cs in candidate.commonness_sets]

    # Exception category proportions (beta)
    exc_cats: dict = {}
    for exc in candidate.exceptions:
        exc_cats[exc["category"]] = exc_cats.get(exc["category"], 0) + 1
    betas = [count / n for count in exc_cats.values()] if n > 0 else []

    s = 0.0
    for a in alphas:
        if a > 0:
            s -= a * math.log2(a)
    for b in betas:
        if b > 0:
            s -= R * b * math.log2(b)

    return s


def rescore_candidates(candidates: list, gamma: float) -> list:
    """
    Deep-copy candidates and recompute conciseness + score with new gamma.
    Impact is unchanged.
    """
    rescored = []
    for c in candidates:
        c2 = copy.deepcopy(c)
        s = compute_raw_entropy(c2)
        has_exc = len(c2.exceptions) > 0
        s_reg = s + gamma * (0.0 if has_exc else 1.0)
        c2.conciseness = max(0.0, 1.0 - s_reg / S_STAR) if S_STAR > 0 else 1.0
        c2.score = c2.conciseness * c2.impact
        rescored.append(c2)
    return rescored


# =============================================================================
# CANDIDATE FINGERPRINT (for diffing ranked lists)
# =============================================================================

def fingerprint(c: MetaInsightCandidate) -> str:
    """Short unique-ish key for a candidate."""
    return f"{c.pattern_type}|{c.extending_strategy}|{c.extending_dimension}|{c.breakdown}|{c.measure}|{c.base_subspace}"


# =============================================================================
# REPORT GENERATION
# =============================================================================

def build_structured_report(all_results: dict) -> str:
    """Build the markdown report comparing top-15 across gamma values."""
    lines = ["# Gamma Sensitivity Analysis", ""]

    for view_name, gamma_data in all_results.items():
        lines += [f"## {view_name}", ""]

        # Per-gamma summary table
        lines.append(f"| Gamma | Universal | Actionable | TotalUse | Top Score |")
        lines.append(f"|-------|-----------|------------|----------|-----------|")
        for gamma, ranked in gamma_data["ranked"].items():
            n_uni = sum(1 for c in ranked if not c.exceptions)
            n_act = sum(1 for c in ranked if c.exceptions)
            tu = compute_total_use_approx(ranked)
            top = ranked[0].score if ranked else 0
            lines.append(f"| {gamma} | {n_uni} | {n_act} | {tu:.4f} | {top:.4f} |")
        lines.append("")

        # Top-15 with NL summaries for each gamma
        for gamma, ranked in gamma_data["ranked"].items():
            lines.append(f"### gamma = {gamma}")
            lines.append("")
            for rank, c in enumerate(ranked, 1):
                tag = "[actionable]" if c.exceptions else "[universal]"
                nl = generate_nl_summary(c)
                lines.append(f"{rank}. (score={c.score:.4f}) {tag} {nl}")
            lines.append("")

        # Diff vs baseline (gamma=0.1)
        baseline_fps = set(fingerprint(c) for c in gamma_data["ranked"][0.1])
        lines.append("### Changes vs baseline (gamma=0.1)")
        lines.append("")
        for gamma in [0.3, 0.5, 0.8]:
            ranked = gamma_data["ranked"][gamma]
            current_fps = set(fingerprint(c) for c in ranked)
            entered = current_fps - baseline_fps
            exited = baseline_fps - current_fps
            if not entered and not exited:
                lines.append(f"**gamma={gamma}**: No change from baseline.")
            else:
                lines.append(f"**gamma={gamma}**: {len(entered)} entered, {len(exited)} exited")
                for c in ranked:
                    if fingerprint(c) in entered:
                        tag = "[actionable]" if c.exceptions else "[universal]"
                        lines.append(f"  + {tag} {c.pattern_type} on {c.measure} via {c.extending_dimension}")
                for c in gamma_data["ranked"][0.1]:
                    if fingerprint(c) in exited:
                        tag = "[actionable]" if c.exceptions else "[universal]"
                        lines.append(f"  - {tag} {c.pattern_type} on {c.measure} via {c.extending_dimension}")
            lines.append("")
        lines.append("---")
        lines.append("")

    return "\n".join(lines)


def build_llm_prompt(structured_report: str) -> str:
    """Build prompt for LLM executive summary of gamma sensitivity."""
    return f"""You are writing an analytical note for a data scientist who is tuning the actionability parameter (gamma) of a MetaInsight ranking system for a PM-JAY health insurance programme in Uttar Pradesh.

## Background

The MetaInsight system discovers patterns in healthcare data and ranks them. Each insight is either:
- **Universal**: the pattern holds for ALL subgroups (no exceptions)
- **Actionable**: the pattern holds for MOST subgroups but has specific exceptions worth investigating

Gamma controls how much the system penalises universal insights. At gamma=0.1 (baseline), universal insights are only lightly penalised. At gamma=0.8, they are heavily penalised, pushing actionable insights to the top.

## The Data

Below is a structured comparison of the top-15 ranked insights across four views for gamma = 0.1, 0.3, 0.5, 0.8:

{structured_report}

## Instructions

Write a concise (400-600 word) executive summary addressing:

1. At what gamma value do the rankings start to meaningfully change? Is it gradual or abrupt?
2. Which views are most sensitive to gamma? Which are least?
3. What kinds of insights get promoted at higher gamma? What gets demoted?
4. Give 2-3 concrete examples of actionable insights that enter the top-15 at higher gamma -- explain what they reveal and why a programme officer should care.
5. Recommend a gamma value (or range) and briefly explain why.

Use plain English. No jargon. Use ### headers for sections. Do not use bullet points for the main narrative. Be direct and advisory.
"""


def generate_llm_summary(structured_report: str) -> str:
    """Call gpt-5.4-mini to produce the executive summary."""
    client = OpenAI()
    prompt = build_llm_prompt(structured_report)
    response = client.chat.completions.create(
        model="gpt-5.4-mini",
        max_completion_tokens=1500,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.choices[0].message.content


# =============================================================================
# ENTRY POINT
# =============================================================================

if __name__ == "__main__":
    views = ["view1", "view2", "view3", "view4"]
    all_results = {}

    for view_name in views:
        path = os.path.join(BASE_DIR, "metainsights", f"{view_name}_candidates.json")
        print(f"\nLoading {view_name} ...")
        candidates = load_candidates(path)
        print(f"  {len(candidates):,} candidates")

        gamma_ranked = {}
        for gamma in GAMMA_VALUES:
            rescored = rescore_candidates(candidates, gamma)
            ranked = rank_metainsights(rescored, k=15)
            gamma_ranked[gamma] = ranked
            n_act = sum(1 for c in ranked if c.exceptions)
            print(f"  gamma={gamma}: top score={ranked[0].score:.4f}, "
                  f"actionable={n_act}/15")

        all_results[view_name] = {"ranked": gamma_ranked}

    # Build structured report
    print("\nBuilding report ...")
    structured_report = build_structured_report(all_results)

    # LLM executive summary
    print("Generating LLM summary ...")
    llm_summary = generate_llm_summary(structured_report)

    # Assemble final output
    final_report = (
        structured_report
        + "\n\n# Executive Summary\n\n"
        + llm_summary
    )

    output_path = os.path.join(BASE_DIR, "reports", "gamma_sensitivity_report.md")
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(final_report)
    print(f"\nReport -> {output_path}")
