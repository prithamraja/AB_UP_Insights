# =============================================================================
# Phase 5: Intra-View Ranking & Presentation (Layers 3 + 3P)
# =============================================================================
# Takes raw MetaInsight candidates from each view (Phase 4b output) and
# produces a ranked top-k list per view using the paper's greedy second-order
# approximation of TotalUse maximisation (Section 4.3).
#
# Selects candidates with high individual scores and low inter-MetaInsight
# redundancy. Also generates Layer 2P (raw explorer) and Layer 3P (ranked
# dashboard) presentation reports.
#
# Inputs:
#   metainsights/view1_candidates.json
#   metainsights/view2_candidates.json
#   metainsights/view3_candidates.json
#   metainsights/view4_candidates.json
#
# Outputs:
#   metainsights/view1_ranked.json
#   metainsights/view2_ranked.json
#   metainsights/view3_ranked.json
#   metainsights/view4_ranked.json
#   reports/layer2p_raw_explorer.txt
#   reports/layer3p_ranked_dashboard.txt
#
# Run from project root:
#   python src/phase5_ranking.py
# =============================================================================

import os
import sys
import ast
import json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from phase2_engine import MetaInsightCandidate, Subspace, load_candidates

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# All pattern types (for zero-count reporting)
ALL_PATTERN_TYPES = [
    "OUTSTANDING_1", "OUTSTANDING_LAST", "TOP_TWO", "LAST_TWO",
    "EVENNESS", "ATTRIBUTION",
    "TREND", "OUTLIER", "SEASONALITY", "CHANGE_POINT", "UNIMODALITY",
]


# =============================================================================
# PART 2: INTER-METAINSIGHT OVERLAP (Paper Section 4.3 + Appendix 9.4)
# =============================================================================

def _subspace_overlap_coefficient(
    mi1: MetaInsightCandidate, mi2: MetaInsightCandidate
) -> float:
    """Overlap coefficient of base subspace filters."""
    filters1 = set(mi1.base_subspace.filters)
    filters2 = set(mi2.base_subspace.filters)

    if len(filters1) == 0 and len(filters2) == 0:
        return 1.0   # both are {*}
    if len(filters1) == 0 or len(filters2) == 0:
        return 0.0   # one is {*}, other has filters

    intersection = len(filters1 & filters2)
    return intersection / min(len(filters1), len(filters2))


def _subspace_overlap(mi1: MetaInsightCandidate, mi2: MetaInsightCandidate) -> float:
    """Overlap for subspace-extending MetaInsights."""
    w1, w2, w3, w4 = 0.4, 0.3, 0.15, 0.15
    sub = _subspace_overlap_coefficient(mi1, mi2)
    ext = 1.0 if mi1.extending_dimension == mi2.extending_dimension else 0.0
    msr = 1.0 if mi1.measure == mi2.measure else 0.0
    bkd = 1.0 if mi1.breakdown == mi2.breakdown else 0.0
    return w1 * sub + w2 * ext + w3 * msr + w4 * bkd


def _measure_overlap(mi1: MetaInsightCandidate, mi2: MetaInsightCandidate) -> float:
    """Overlap for measure-extending MetaInsights."""
    w1, w2 = 0.6, 0.4
    sub = _subspace_overlap_coefficient(mi1, mi2)
    bkd = 1.0 if mi1.breakdown == mi2.breakdown else 0.0
    return w1 * sub + w2 * bkd


def _breakdown_overlap(mi1: MetaInsightCandidate, mi2: MetaInsightCandidate) -> float:
    """Overlap for breakdown-extending MetaInsights."""
    w1, w2 = 0.6, 0.4
    sub = _subspace_overlap_coefficient(mi1, mi2)
    msr = 1.0 if mi1.measure == mi2.measure else 0.0
    return w1 * sub + w2 * msr


def compute_overlap_ratio(
    mi1: MetaInsightCandidate, mi2: MetaInsightCandidate
) -> float:
    """
    Overlap ratio between two MetaInsights in [0, 1].
    Two MetaInsights can only overlap if they share the same extending strategy
    and pattern type; otherwise returns 0.
    """
    if mi1.extending_strategy != mi2.extending_strategy:
        return 0.0
    if mi1.pattern_type != mi2.pattern_type:
        return 0.0

    strategy = mi1.extending_strategy
    if strategy == "subspace":
        return _subspace_overlap(mi1, mi2)
    if strategy == "measure":
        return _measure_overlap(mi1, mi2)
    if strategy == "breakdown":
        return _breakdown_overlap(mi1, mi2)
    return 0.0


def compute_pairwise_overlap(
    mi1: MetaInsightCandidate, mi2: MetaInsightCandidate
) -> float:
    """
    |I1 ∩ I2| = min(|I1|, |I2|) × r(I1, I2)
    Where |I| = score, r = overlap ratio.  (Paper Equation 20)
    """
    r = compute_overlap_ratio(mi1, mi2)
    return min(mi1.score, mi2.score) * r


# =============================================================================
# PART 3: GREEDY RANKING (Paper Section 4.3)
# =============================================================================

def compute_total_use_approx(selected: list) -> float:
    """
    TotalUse_approx = sum(|Ii|) - sum(|Ii ∩ Ij|) for all pairs i < j
    (Paper Equation 22)
    """
    total = sum(mi.score for mi in selected)
    for i in range(len(selected)):
        for j in range(i + 1, len(selected)):
            total -= compute_pairwise_overlap(selected[i], selected[j])
    return total


def prefilter_candidates(candidates: list, max_candidates: int = 5000) -> list:
    """Keep only top-N by score. Low scorers have near-zero chance of selection."""
    if len(candidates) <= max_candidates:
        return candidates
    return sorted(candidates, key=lambda c: c.score, reverse=True)[:max_candidates]


def rank_metainsights(candidates: list, k: int = 15) -> list:
    """
    Greedy algorithm to select top-k MetaInsights maximising TotalUse_approx.

    1. Start with the highest-scoring candidate.
    2. At each step, add the candidate that gives the highest marginal gain
       (score minus overlap penalties with already-selected candidates).
    3. Stop when k candidates selected or no candidate improves TotalUse.
    """
    if not candidates:
        return []

    sorted_cands = sorted(candidates, key=lambda c: c.score, reverse=True)
    selected = [sorted_cands[0]]
    remaining = set(range(1, len(sorted_cands)))

    for _ in range(1, k):
        if not remaining:
            break

        best_marginal = -float("inf")
        best_idx = None

        for idx in remaining:
            candidate = sorted_cands[idx]
            marginal = candidate.score
            for sel in selected:
                marginal -= compute_pairwise_overlap(candidate, sel)
            if marginal > best_marginal:
                best_marginal = marginal
                best_idx = idx

        if best_marginal <= 0:
            break

        selected.append(sorted_cands[best_idx])
        remaining.remove(best_idx)

    return selected


# =============================================================================
# PART 4: NATURAL LANGUAGE SUMMARIES
# =============================================================================

def _pattern_type_to_text(
    pattern_type: str, highlight: str, breakdown: str, measure: str
) -> str:
    """Convert pattern type + highlight string into readable text."""
    try:
        hl = ast.literal_eval(highlight) if highlight else ()
    except (ValueError, SyntaxError):
        hl = (highlight,) if highlight else ()

    templates = {
        "OUTSTANDING_1":    lambda: f"{hl[0]} has the highest {measure} among {breakdown} values",
        "OUTSTANDING_LAST": lambda: f"{hl[0]} has the lowest {measure} among {breakdown} values",
        "TOP_TWO":          lambda: f"{hl[0]} and {hl[1]} lead in {measure} among {breakdown} values",
        "LAST_TWO":         lambda: f"{hl[0]} and {hl[1]} are lowest in {measure} among {breakdown} values",
        "EVENNESS":         lambda: f"{measure} is evenly distributed across {breakdown} values",
        "ATTRIBUTION":      lambda: f"{hl[0]} accounts for the majority of {measure} among {breakdown} values",
        "TREND":            lambda: f"{measure} is {hl[0].lower()} over {breakdown}",
        "OUTLIER":          lambda: (
            f"{measure} has an outlier at {hl[0][0]} ({hl[0][1].lower()}) in {breakdown}"
            if len(hl) == 1
            else f"{measure} has outliers at {', '.join(h[0] for h in hl)} in {breakdown}"
        ),
        "SEASONALITY":      lambda: f"{measure} shows seasonal pattern ({hl[0]}) over {breakdown}",
        "CHANGE_POINT":     lambda: f"{measure} has a significant shift at {hl[0]} in {breakdown}",
        "UNIMODALITY":      lambda: f"{measure} forms a {hl[0].lower()} at {hl[1]} over {breakdown}",
    }

    try:
        return templates.get(pattern_type, lambda: f"{pattern_type} pattern on {measure}")()
    except (IndexError, TypeError):
        return f"{pattern_type} pattern on {measure} across {breakdown}"


def generate_nl_summary(candidate: MetaInsightCandidate) -> str:
    """
    Generate a natural language summary.
    Template: "Across most [dim], [commonness]. Exception: [entity] ([detail])."
    """
    if not candidate.commonness_sets:
        return "(no commonness)"

    cs = candidate.commonness_sets[0]
    pattern_desc = _pattern_type_to_text(
        cs["pattern_type"], cs["highlight"],
        candidate.breakdown, candidate.measure,
    )

    ext_dim    = candidate.extending_dimension
    proportion = cs["proportion"]
    count      = cs["count"]
    hdp_size   = candidate.hdp_size

    if proportion >= 1.0:
        prefix = f"Across all {ext_dim} values"
    elif proportion >= 0.9:
        prefix = f"Across nearly all {ext_dim} values ({count}/{hdp_size})"
    else:
        prefix = f"Across most {ext_dim} values ({count}/{hdp_size})"

    summary = f"{prefix}, {pattern_desc}"

    if candidate.exceptions:
        n_exc = len(candidate.exceptions)
        exc_descs = []
        for e in candidate.exceptions[:3]:
            if e["category"] == "HIGHLIGHT_CHANGE":
                exc_text = _pattern_type_to_text(
                    e["pattern_type"], e["highlight"],
                    candidate.breakdown, candidate.measure,
                )
                exc_descs.append(f"{e['member_label']} ({exc_text})")
            elif e["category"] == "TYPE_CHANGE":
                exc_descs.append(f"{e['member_label']} (different pattern)")
            else:
                exc_descs.append(f"{e['member_label']} (no clear pattern)")

        if n_exc <= 3:
            summary += f". Exception: {'; '.join(exc_descs)}"
        else:
            summary += f". Exceptions: {'; '.join(exc_descs)} and {n_exc - 3} others"

    return summary


# =============================================================================
# PART 5: LAYER 2P — RAW METAINSIGHT EXPLORER
# =============================================================================

def generate_layer2p_report(
    all_candidates: dict,
    output_path: str,
):
    """Generate diagnostic report of all raw candidates per view."""
    lines = [
        "=" * 70,
        "LAYER 2P -- RAW METAINSIGHT EXPLORER",
        "=" * 70, "",
    ]

    for view_name, candidates in all_candidates.items():
        lines += [
            "=" * 70,
            f"VIEW: {view_name}  |  Total candidates: {len(candidates):,}",
            "=" * 70,
        ]

        if not candidates:
            lines += ["  (no candidates)", ""]
            continue

        scores = [c.score for c in candidates]
        lines += [
            "",
            "Score distribution:",
            f"  Max={max(scores):.4f}  Median={sorted(scores)[len(scores)//2]:.4f}  "
            f"Min={min(scores):.4f}  Mean={sum(scores)/len(scores):.4f}",
        ]

        type_counts: dict = {}
        type_actionable: dict = {}
        for c in candidates:
            type_counts[c.pattern_type] = type_counts.get(c.pattern_type, 0) + 1
            if c.exceptions:
                type_actionable[c.pattern_type] = type_actionable.get(c.pattern_type, 0) + 1

        lines += [
            "",
            f"  {'Pattern Type':<25} {'Total':>8} {'Actionable':>12} {'Top Score':>10}",
            f"  {'-'*57}",
        ]
        for pt in sorted(type_counts, key=lambda x: -type_counts[x]):
            top = max(c.score for c in candidates if c.pattern_type == pt)
            lines.append(
                f"  {pt:<25} {type_counts[pt]:>8,} "
                f"{type_actionable.get(pt, 0):>12,} {top:>10.4f}"
            )
        zero_types = [pt for pt in ALL_PATTERN_TYPES if pt not in type_counts]
        if zero_types:
            lines.append(f"\n  Zero candidates: {zero_types}")

        strat_counts: dict = {}
        for c in candidates:
            strat_counts[c.extending_strategy] = strat_counts.get(c.extending_strategy, 0) + 1
        lines += ["", "Extending strategies:"]
        for s, n in sorted(strat_counts.items(), key=lambda x: -x[1]):
            lines.append(f"  {s}: {n:,}")

        universal = sum(1 for c in candidates if not c.exceptions)
        lines += [
            "",
            f"Universal: {universal:,}  |  Actionable: {len(candidates)-universal:,}",
            "",
        ]

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"Layer 2P report -> {output_path}")


# =============================================================================
# PART 6: LAYER 3P — RANKED PER-VIEW DASHBOARD
# =============================================================================

def generate_layer3p_report(
    all_ranked: dict,
    all_candidates: dict,
    output_path: str,
):
    """Generate the ranked dashboard with full detail and NL summaries."""
    lines = [
        "=" * 70,
        "LAYER 3P -- RANKED PER-VIEW DASHBOARD",
        "=" * 70, "",
    ]

    for view_name in all_ranked:
        ranked = all_ranked[view_name]
        total  = len(all_candidates[view_name])

        lines += [
            "=" * 70,
            f"VIEW: {view_name}  |  Selected {len(ranked)} from {total:,} candidates",
            "=" * 70,
        ]

        # Diversity profile
        types_repr    = sorted(set(c.pattern_type        for c in ranked))
        dims_repr     = sorted(set(c.extending_dimension  for c in ranked))
        measures_repr = sorted(set(c.measure for c in ranked if c.measure != "(varies)"))

        lines += [
            "",
            "Diversity:",
            f"  Pattern types ({len(types_repr)}): {', '.join(types_repr)}",
            f"  Extending dims ({len(dims_repr)}): {', '.join(dims_repr)}",
            f"  Measures ({len(measures_repr)}): {', '.join(measures_repr[:8])}"
            + (f" +{len(measures_repr)-8} more" if len(measures_repr) > 8 else ""),
        ]

        # TotalUse stats
        total_use  = compute_total_use_approx(ranked)
        sum_scores = sum(c.score for c in ranked)
        lines += [
            "",
            f"TotalUse: {total_use:.4f}  |  Sum of scores: {sum_scores:.4f}  "
            f"|  Redundancy penalty: {sum_scores - total_use:.4f}",
            "",
            "--- Ranked MetaInsights ---",
            "",
        ]

        for rank, c in enumerate(ranked, 1):
            lines += [
                f"  #{rank}  score={c.score:.4f}  "
                f"(conciseness={c.conciseness:.4f}, impact={c.impact:.4f})",
                f"    {c.extending_strategy} on {c.extending_dimension}  |  "
                f"{c.pattern_type}  |  breakdown={c.breakdown}  |  measure={c.measure}",
                f"    Subspace: {c.base_subspace}  |  HDP: {c.hdp_size}",
            ]

            for cs in c.commonness_sets:
                members = ", ".join(str(m) for m in cs["members"][:6])
                more = f" +{len(cs['members'])-6} more" if len(cs["members"]) > 6 else ""
                lines += [
                    f"    Commonness: [{cs['pattern_type']}] {cs['highlight']}  "
                    f"({cs['count']}/{c.hdp_size} = {cs['proportion']:.0%})",
                    f"      Members: {members}{more}",
                ]

            if c.exceptions:
                lines.append(f"    Exceptions ({len(c.exceptions)}):")
                for exc in c.exceptions[:4]:
                    lines.append(
                        f"      {str(exc['member_label']):<25} {exc['category']:<20} "
                        f"{exc['highlight'] or ''}"
                    )
                if len(c.exceptions) > 4:
                    lines.append(f"      ... +{len(c.exceptions)-4} more")

            nl = generate_nl_summary(c)
            lines += [f"    >> {nl}", ""]

        lines.append("")

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"Layer 3P report -> {output_path}")


# =============================================================================
# ENTRY POINT
# =============================================================================

if __name__ == "__main__":
    views = ["view1", "view2", "view3", "view4"]
    k = 15

    all_candidates: dict = {}
    all_ranked: dict = {}

    for view_name in views:
        path = os.path.join(BASE_DIR, "metainsights", f"{view_name}_candidates.json")
        print(f"\nLoading {path} ...")
        candidates = load_candidates(path)
        print(f"  {len(candidates):,} candidates loaded")

        filtered = prefilter_candidates(candidates, max_candidates=5000)
        print(f"  {len(filtered):,} after pre-filter")

        ranked = rank_metainsights(filtered, k=k)
        print(f"  {len(ranked)} selected for top-{k}")

        all_candidates[view_name] = candidates
        all_ranked[view_name]     = ranked

        ranked_path = os.path.join(BASE_DIR, "metainsights", f"{view_name}_ranked.json")
        os.makedirs(os.path.dirname(ranked_path), exist_ok=True)
        with open(ranked_path, "w", encoding="utf-8") as fout:
            json.dump([c.to_dict() for c in ranked], fout, indent=2, default=str)

    generate_layer2p_report(
        all_candidates,
        os.path.join(BASE_DIR, "reports", "layer2p_raw_explorer.txt"),
    )
    generate_layer3p_report(
        all_ranked,
        all_candidates,
        os.path.join(BASE_DIR, "reports", "layer3p_ranked_dashboard.txt"),
    )

    print(f"\n{'=' * 70}")
    print("Phase 5 Summary")
    print(f"{'=' * 70}")
    for view_name in views:
        ranked = all_ranked[view_name]
        total  = len(all_candidates[view_name])
        types  = sorted(set(c.pattern_type for c in ranked))
        tu     = compute_total_use_approx(ranked)
        print(f"  {view_name}: {len(ranked)} selected from {total:,}  "
              f"| TotalUse={tu:.4f}  | types: {', '.join(types)}")
