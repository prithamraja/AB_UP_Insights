# =============================================================================
# MetaInsight Candidate Report Generator
# =============================================================================
# Reads view1_candidates.json and writes a structured human-readable report
# covering score distribution, top candidates overall, top candidates with
# exceptions (the actionable subset), and breakdowns by strategy/dimension.
#
# Run from project root:
#   python src/generate_candidate_report.py
# =============================================================================

import os
import json
import pandas as pd

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INPUT    = os.path.join(BASE_DIR, "metainsights", "view1_candidates.json")
OUTPUT   = os.path.join(BASE_DIR, "reports", "candidate_report.txt")


def fmt_candidate(c: dict, rank: int) -> list[str]:
    """Format one MetaInsight candidate as a block of lines."""
    common_strs = []
    for cs in c["commonness_sets"]:
        members = cs["members"]
        mem_str = ", ".join(str(m) for m in members[:10])
        if len(members) > 10:
            mem_str += f" ... (+{len(members)-10} more)"
        common_strs.append(
            f"      [{cs['pattern_type']}] highlight={cs['highlight']}  "
            f"{cs['count']}/{c['hdp_size']} ({cs['proportion']:.0%})"
        )
        common_strs.append(f"        Members: {mem_str}")

    exc_lines = []
    for exc in c["exceptions"][:8]:
        exc_lines.append(
            f"      {exc['member_label']:20s}  {exc['category']:20s}  "
            f"highlight={exc['highlight']}"
        )
    if len(c["exceptions"]) > 8:
        exc_lines.append(f"      ... and {len(c['exceptions'])-8} more")

    lines = [
        f"  #{rank}  score={c['score']:.4f}  "
        f"(conciseness={c['conciseness']:.4f}, impact={c['impact']:.4f} via {c['impact_measure_used']})",
        f"    Strategy:   {c['extending_strategy']} on '{c['extending_dimension']}'",
        f"    Pattern:    {c['pattern_type']}",
        f"    Breakdown:  {c['breakdown']}    Measure: {c['measure']}",
        f"    Subspace:   {c['base_subspace']}",
        f"    HDP size:   {c['hdp_size']}    Exceptions: {len(c['exceptions'])}",
        f"    Commonness:",
    ] + common_strs

    if exc_lines:
        lines.append(f"    Exceptions:")
        lines.extend(exc_lines)

    return lines


def write_section(lines: list[str], title: str, candidates: list[dict], n: int, rank_offset: int = 1):
    lines.append("")
    lines.append("=" * 70)
    lines.append(title)
    lines.append("=" * 70)
    for i, c in enumerate(candidates[:n]):
        lines.extend(fmt_candidate(c, rank_offset + i))
        lines.append("")


def main():
    print(f"Loading {INPUT} ...")
    with open(INPUT, encoding="utf-8") as f:
        cands = json.load(f)

    # Build summary frame
    rows = []
    for c in cands:
        rows.append({
            "score":               c["score"],
            "conciseness":         c["conciseness"],
            "impact":              c["impact"],
            "extending_strategy":  c["extending_strategy"],
            "extending_dimension": c["extending_dimension"],
            "breakdown":           c["breakdown"],
            "measure":             c["measure"],
            "base_subspace":       c["base_subspace"],
            "hdp_size":            c["hdp_size"],
            "n_exceptions":        len(c["exceptions"]),
            "impact_measure":      c["impact_measure_used"],
            "_idx":                rows.__len__(),  # original rank
        })
    df = pd.DataFrame(rows)

    # Partition: no-exception (universal) vs with-exception (actionable)
    univ  = [cands[i] for i in df[df.n_exceptions == 0].index]
    actbl = [cands[i] for i in df[df.n_exceptions >  0].sort_values("score", ascending=False).index]

    lines = []

    # ---- Header --------------------------------------------------------
    lines += [
        "=" * 70,
        "METAINSIGHT CANDIDATE REPORT  --  View 1: Claims Lifecycle",
        "Pattern type: OUTSTANDING_1",
        "=" * 70,
        "",
        f"Total candidates:          {len(cands):,}",
        f"  Universal (0 exceptions): {len(univ):,}",
        f"  Actionable (>=1 except.): {len(actbl):,}",
        "",
        "Score distribution:",
    ]
    for lo, hi in [(0.8, 1.01), (0.6, 0.8), (0.4, 0.6), (0.2, 0.4), (0.0, 0.2)]:
        n = int(((df.score >= lo) & (df.score < hi)).sum())
        bar = "#" * (n // 50)
        lines.append(f"  {lo:.1f}-{hi if hi < 1.01 else 1.0:.1f}:  {n:5,}  {bar}")

    lines += [
        "",
        "By extending strategy:",
    ]
    for strat, cnt in df["extending_strategy"].value_counts().items():
        lines.append(f"  {strat:12s}: {cnt:,}")

    lines += ["", "By breakdown dimension (top 10):"]
    for bd, cnt in df["breakdown"].value_counts().head(10).items():
        lines.append(f"  {bd:20s}: {cnt:,}")

    lines += ["", "By extending dimension (top 10):"]
    for ed, cnt in df["extending_dimension"].value_counts().head(10).items():
        lines.append(f"  {ed:20s}: {cnt:,}")

    # ---- Section 1: Top 30 overall ----------------------------------------
    write_section(lines, "SECTION 1 -- TOP 30 CANDIDATES (ALL)", cands, 30)

    # ---- Section 2: Top 50 actionable (with exceptions) -------------------
    write_section(
        lines,
        "SECTION 2 -- TOP 50 ACTIONABLE CANDIDATES (WITH EXCEPTIONS)",
        actbl, 50,
    )

    # ---- Section 3: Top 20 by each breakdown (w/ exceptions only) ---------
    lines += ["", "=" * 70,
              "SECTION 3 -- TOP 10 ACTIONABLE BY BREAKDOWN DIMENSION", "=" * 70]
    for bd in df["breakdown"].value_counts().head(6).index:
        subset = [
            cands[i] for i in
            df[(df.breakdown == bd) & (df.n_exceptions > 0)]
            .sort_values("score", ascending=False).head(10).index
        ]
        if not subset:
            continue
        lines.append(f"\n--- breakdown={bd} ({len(subset)} shown) ---")
        for i, c in enumerate(subset):
            lines.extend(fmt_candidate(c, i + 1))
            lines.append("")

    # ---- Section 4: Top 10 actionable by extending dimension --------------
    lines += ["", "=" * 70,
              "SECTION 4 -- TOP 10 ACTIONABLE BY EXTENDING DIMENSION", "=" * 70]
    for ed in df["extending_dimension"].value_counts().head(8).index:
        subset = [
            cands[i] for i in
            df[(df.extending_dimension == ed) & (df.n_exceptions > 0)]
            .sort_values("score", ascending=False).head(10).index
        ]
        if not subset:
            continue
        lines.append(f"\n--- extending_dimension={ed} ({len(subset)} shown) ---")
        for i, c in enumerate(subset):
            lines.extend(fmt_candidate(c, i + 1))
            lines.append("")

    # ---- Section 5: Non-trivial subspaces (depth > 0) with exceptions -----
    depth1_plus = [
        cands[i] for i in
        df[(df.base_subspace != "{*}") & (df.n_exceptions > 0)]
        .sort_values("score", ascending=False).head(30).index
    ]
    write_section(
        lines,
        "SECTION 5 -- TOP 30 ACTIONABLE IN NON-TRIVIAL SUBSPACES (depth>=1)",
        depth1_plus, 30,
    )

    # Write file
    os.makedirs(os.path.dirname(OUTPUT), exist_ok=True)
    with open(OUTPUT, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"Report written -> {OUTPUT}")
    print(f"  {len(lines):,} lines")


if __name__ == "__main__":
    main()
