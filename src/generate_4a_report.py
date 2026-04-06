# =============================================================================
# Phase 4a Candidate Report Generator
# =============================================================================
# Reads view1_all_patterns_candidates.json and writes a structured report
# with sections organised by pattern type, score bands, and actionability.
#
# Run from project root:
#   python src/generate_4a_report.py
# =============================================================================

import os
import json
import pandas as pd

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INPUT    = os.path.join(BASE_DIR, "metainsights", "view1_all_patterns_candidates.json")
OUTPUT   = os.path.join(BASE_DIR, "reports", "candidate_report_all_patterns.txt")

CATEGORICAL_TYPES = ["OUTSTANDING_1", "OUTSTANDING_LAST", "TOP_TWO", "LAST_TWO",
                     "EVENNESS", "ATTRIBUTION"]
TEMPORAL_TYPES    = ["TREND", "OUTLIER", "SEASONALITY", "CHANGE_POINT", "UNIMODALITY"]

PATTERN_DESCRIPTIONS = {
    "OUTSTANDING_1":    "One breakdown value is significantly higher than all others (z>=2, ratio>=1.5x)",
    "OUTSTANDING_LAST": "One breakdown value is significantly lower than all others (z<=-2, ratio<=0.67x)",
    "TOP_TWO":          "Two breakdown values are jointly significantly higher than the rest",
    "LAST_TWO":         "Two breakdown values are jointly significantly lower than the rest",
    "EVENNESS":         "All breakdown values are distributed approximately equally (CV<0.15)",
    "ATTRIBUTION":      "One breakdown value accounts for >50% of the total (and is 2x the next)",
    "TREND":            "Significant monotonic trend in the time series (Spearman |rho|>0.5, p<0.05)",
    "OUTLIER":          "One or more time points are 3-sigma outliers",
    "SEASONALITY":      "Repeating periodic pattern (autocorrelation at lag 3/4/6/12 > 0.4)",
    "CHANGE_POINT":     "Significant shift in mean at some point in the series (Welch t-test p<0.01)",
    "UNIMODALITY":      "Time series forms a single peak or valley (70% directional step tolerance)",
}


def fmt_candidate(c: dict, rank: int) -> list:
    lines = [
        f"  #{rank}  score={c['score']:.4f}  "
        f"(conciseness={c['conciseness']:.4f}, impact={c['impact']:.4f} via {c['impact_measure_used']})",
        f"    Strategy:  {c['extending_strategy']} on '{c['extending_dimension']}'",
        f"    Breakdown: {c['breakdown']}    Measure: {c['measure']}",
        f"    Subspace:  {c['base_subspace']}",
        f"    HDP size:  {c['hdp_size']}    Exceptions: {len(c['exceptions'])}",
        f"    Commonness:",
    ]
    for cs in c["commonness_sets"]:
        members = cs["members"]
        mem_str = ", ".join(str(m) for m in members[:10])
        if len(members) > 10:
            mem_str += f" ... (+{len(members)-10} more)"
        lines.append(f"      [{cs['pattern_type']}] highlight={cs['highlight']}  "
                     f"{cs['count']}/{c['hdp_size']} ({cs['proportion']:.0%})")
        lines.append(f"        Members: {mem_str}")
    if c["exceptions"]:
        lines.append(f"    Exceptions:")
        for exc in c["exceptions"][:6]:
            lines.append(f"      {exc['member_label']:22s}  {exc['category']:20s}  "
                         f"highlight={exc['highlight']}")
        if len(c["exceptions"]) > 6:
            lines.append(f"      ... and {len(c['exceptions'])-6} more")
    else:
        lines.append("    Exceptions:  none (universal pattern)")
    return lines


def section(lines, title, body_lines):
    lines += ["", "=" * 70, title, "=" * 70]
    lines += body_lines


def main():
    print(f"Loading {INPUT} ...")
    with open(INPUT, encoding="utf-8") as f:
        cands = json.load(f)

    df = pd.DataFrame([{
        "score":               c["score"],
        "conciseness":         c["conciseness"],
        "impact":              c["impact"],
        "pattern_type":        c["pattern_type"],
        "extending_strategy":  c["extending_strategy"],
        "extending_dimension": c["extending_dimension"],
        "breakdown":           c["breakdown"],
        "measure":             c["measure"],
        "base_subspace":       c["base_subspace"],
        "hdp_size":            c["hdp_size"],
        "n_exceptions":        len(c["exceptions"]),
        "impact_measure":      c["impact_measure_used"],
    } for c in cands])

    univ  = [cands[i] for i in df[df.n_exceptions == 0].index]
    actbl = [cands[i] for i in df[df.n_exceptions >  0].sort_values("score", ascending=False).index]

    lines = [
        "=" * 70,
        "METAINSIGHT CANDIDATE REPORT  --  Phase 4a: All Pattern Types",
        "View 1: Claims Lifecycle",
        "=" * 70,
        "",
        f"Total candidates:          {len(cands):,}",
        f"  Universal (0 exceptions): {len(univ):,}",
        f"  Actionable (>=1 except.): {len(actbl):,}",
        "",
        "Score distribution:",
    ]
    for lo, hi in [(0.8, 1.01), (0.6, 0.8), (0.4, 0.6), (0.2, 0.4), (0.0, 0.2)]:
        n    = int(((df.score >= lo) & (df.score < hi)).sum())
        bar  = "#" * (n // 100)
        label = f"{lo:.1f}-{hi if hi < 1.01 else 1.0:.1f}"
        lines.append(f"  {label}: {n:6,}  {bar}")

    lines += ["", "Candidates by pattern type:"]
    type_counts = df["pattern_type"].value_counts()
    for pt, cnt in type_counts.items():
        is_temporal = pt in TEMPORAL_TYPES
        tag = "[temporal]" if is_temporal else "[categorical]"
        actbl_cnt = int((df[df.pattern_type == pt].n_exceptions > 0).sum())
        top_score = df[df.pattern_type == pt]["score"].max()
        lines.append(f"  {pt:20s} {tag:14s}  {cnt:5,} total  "
                     f"{actbl_cnt:5,} actionable  top={top_score:.4f}")

    zero = [pt for pt in PATTERN_DESCRIPTIONS if pt not in type_counts.index]
    if zero:
        lines.append(f"\n  Zero candidates: {zero}")

    # -------------------------------------------------------------------------
    # Section 1: Top 30 overall
    # -------------------------------------------------------------------------
    section(lines, "SECTION 1 -- TOP 30 CANDIDATES OVERALL", [])
    for i, c in enumerate(cands[:30]):
        lines.extend(fmt_candidate(c, i + 1))
        lines.append("")

    # -------------------------------------------------------------------------
    # Section 2: Top 10 per pattern type (actionable only)
    # -------------------------------------------------------------------------
    section(lines, "SECTION 2 -- TOP 10 ACTIONABLE CANDIDATES PER PATTERN TYPE", [])
    for pt in PATTERN_DESCRIPTIONS:
        subset = [
            cands[i] for i in
            df[(df.pattern_type == pt) & (df.n_exceptions > 0)]
            .sort_values("score", ascending=False).head(10).index
        ]
        if not subset:
            lines += ["", f"--- {pt}  [{PATTERN_DESCRIPTIONS[pt]}]",
                      "  (no actionable candidates)"]
            continue
        lines += ["", f"--- {pt}  [{PATTERN_DESCRIPTIONS[pt]}]",
                  f"    ({len(subset)} shown of "
                  f"{int((df[(df.pattern_type==pt)&(df.n_exceptions>0)]).shape[0])} actionable)"]
        for i, c in enumerate(subset):
            lines.extend(fmt_candidate(c, i + 1))
            lines.append("")

    # -------------------------------------------------------------------------
    # Section 3: Temporal patterns deep-dive
    # -------------------------------------------------------------------------
    section(lines, "SECTION 3 -- TEMPORAL PATTERNS DEEP-DIVE (top 20 each)", [])
    for pt in TEMPORAL_TYPES:
        subset = [
            cands[i] for i in
            df[df.pattern_type == pt].sort_values("score", ascending=False).head(20).index
        ]
        if not subset:
            lines += ["", f"--- {pt}: no candidates found"]
            continue
        total_actbl = int((df[(df.pattern_type==pt)&(df.n_exceptions>0)]).shape[0])
        lines += ["", f"--- {pt}  ({len(subset)} shown, {total_actbl} actionable total)",
                  f"    {PATTERN_DESCRIPTIONS[pt]}"]
        for i, c in enumerate(subset):
            lines.extend(fmt_candidate(c, i + 1))
            lines.append("")

    # -------------------------------------------------------------------------
    # Section 4: Top 30 actionable in non-trivial subspaces
    # -------------------------------------------------------------------------
    depth1_plus = [
        cands[i] for i in
        df[(df.base_subspace != "{*}") & (df.n_exceptions > 0)]
        .sort_values("score", ascending=False).head(30).index
    ]
    section(lines, "SECTION 4 -- TOP 30 ACTIONABLE IN NON-TRIVIAL SUBSPACES (depth>=1)",
            [f"  ({len(depth1_plus)} shown)"])
    for i, c in enumerate(depth1_plus):
        lines.extend(fmt_candidate(c, i + 1))
        lines.append("")

    # -------------------------------------------------------------------------
    # Section 5: Top 50 actionable overall
    # -------------------------------------------------------------------------
    section(lines, "SECTION 5 -- TOP 50 ACTIONABLE CANDIDATES (WITH EXCEPTIONS)", [])
    for i, c in enumerate(actbl[:50]):
        lines.extend(fmt_candidate(c, i + 1))
        lines.append("")

    os.makedirs(os.path.dirname(OUTPUT), exist_ok=True)
    with open(OUTPUT, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"Report written -> {OUTPUT}")
    print(f"  {len(lines):,} lines")


if __name__ == "__main__":
    main()
