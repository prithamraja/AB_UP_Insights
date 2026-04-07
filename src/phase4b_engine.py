# =============================================================================
# Engine Upgrade: HDP Deduplication (pandas query layer)
# =============================================================================
# Single change to the Phase 4a engine:
#
#   HDP deduplication set
#     - Tracks (member_subspaces, pattern_type, breakdown, measure) keys
#     - Skips evaluate_hdp if the exact HDP was already evaluated
#     - Eliminates redundant candidates discovered via different seed scopes
#
# Everything else is unchanged from Phase 4a:
#   Pandas query layer (with augmented-query prefetch), all 11 pattern
#   evaluators, HDP construction, scoring, output format.
#
# Outputs:
#   metainsights/view1_dedup_candidates.json
#   reports/engine_diagnostics_dedup.txt
#
# Run from project root:
#   python src/phase4b_engine.py
# =============================================================================

import os
import sys
import math
import time
import heapq
import warnings

import pandas as pd

warnings.filterwarnings("ignore")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# ---------------------------------------------------------------------------
# Import everything from Phase 4a (pandas query layer, all 11 evaluators,
# HDP construction, scoring, output). Phase 4a already patches phase2_engine
# with the full pattern registry and updated detect_pattern on import.
# ---------------------------------------------------------------------------
from phase4a_engine import (
    # Config
    MeasureConfig, ViewConfig, VIEW1_CONFIG, VIEW2_CONFIG, VIEW3_CONFIG, VIEW4_CONFIG,
    # Data structures
    Subspace, DataScope, MetaInsightCandidate,
    # Enumeration
    generate_subspaces, generate_data_scopes,
    # Priority queue
    build_priority_queue,
    # Query layer (pandas, with augmented-query prefetch)
    QueryCache, PatternCache,
    # Impact (pandas)
    ImpactCalculator,
    # Pattern detection
    detect_pattern, PATTERN_EVALUATORS, TEMPORAL_ONLY_TYPES, CATEGORICAL_ONLY_TYPES,
    # HDP construction
    extend_subspace, extend_measure, extend_breakdown, evaluate_hdp,
    # Scoring
    score_candidate,
    # Output
    save_candidates,
)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# =============================================================================
# RUN_ENGINE — Phase 4a engine + HDP deduplication
# =============================================================================

def run_engine(config: ViewConfig, time_budget_seconds: int = 900) -> tuple:
    """
    Phase 4a engine with HDP deduplication added.

    Before calling evaluate_hdp, checks whether the exact same HDP
    (same member subspaces, pattern type, breakdown, measure) was already
    evaluated. If so, skips it — the candidate would be identical.
    """
    print("=" * 70)
    print("ENGINE: All Pattern Types + HDP Deduplication")
    print("=" * 70)

    print(f"Loading {config.parquet_path} ...")
    df = pd.read_parquet(config.parquet_path)
    print(f"  {len(df):,} rows x {len(df.columns)} cols")

    # Pattern type partitions
    pattern_types_categorical = [pt for pt in PATTERN_EVALUATORS if pt not in TEMPORAL_ONLY_TYPES]
    pattern_types_temporal    = [pt for pt in PATTERN_EVALUATORS if pt not in CATEGORICAL_ONLY_TYPES]
    print(f"\nPattern types: {len(pattern_types_categorical)} categorical, "
          f"{len(pattern_types_temporal)} temporal  ({len(PATTERN_EVALUATORS)} total)")

    # Initialise
    query_cache    = QueryCache()
    pattern_cache  = PatternCache()
    impact_calc    = ImpactCalculator(df, config.impact_measures)
    candidates: list = []
    evaluated_hdps: set = set()   # dedup set
    hdps_skipped   = 0

    # Subspace enumeration
    print("\nGenerating subspaces ...")
    subspaces = generate_subspaces(config, df)
    d0 = 1
    d1 = sum(1 for s in subspaces if s.depth == 1)
    d2 = sum(1 for s in subspaces if s.depth == 2)
    print(f"  depth-0: {d0}  depth-1: {d1}  depth-2: {d2}  total: {len(subspaces):,}")

    # Priority queue
    print("Building priority queue ...")
    queue = build_priority_queue(subspaces, impact_calc, config.min_impact)
    print(f"  {len(queue):,} subspaces retained after impact pruning (min={config.min_impact})")

    # Mining loop
    start_time         = time.time()
    scopes_evaluated   = 0
    patterns_found     = 0
    hdps_evaluated     = 0
    metainsights_found = 0

    print(f"\nMining (budget: {time_budget_seconds}s) ...")

    while queue and (time.time() - start_time) < time_budget_seconds:
        neg_impact, _, subspace = heapq.heappop(queue)
        data_scopes = generate_data_scopes(subspace, config)

        for ds in data_scopes:
            if (time.time() - start_time) >= time_budget_seconds:
                break

            scopes_evaluated += 1
            is_temporal  = ds.breakdown in config.temporal_dimensions
            active_types = pattern_types_temporal if is_temporal else pattern_types_categorical

            for pattern_type in active_types:
                cached = pattern_cache.get(ds, pattern_type)
                if cached is not None:
                    pattern = cached
                else:
                    pattern = detect_pattern(df, ds, pattern_type, query_cache, config)
                    pattern_cache.put(ds, pattern_type, pattern)

                if pattern.pattern_type == pattern_type:
                    patterns_found += 1

                    extensions = []
                    extensions.extend(extend_subspace(ds, df, config))
                    extensions.extend(extend_measure(ds, config))
                    extensions.extend(extend_breakdown(ds, config))

                    for ext_strategy, ext_dim, hdp_scopes in extensions:
                        # --- HDP deduplication ---
                        hdp_key = (
                            frozenset(s.subspace for s in hdp_scopes),
                            pattern_type,
                            hdp_scopes[0].breakdown if ext_strategy != "breakdown" else "(varies)",
                            hdp_scopes[0].measure   if ext_strategy != "measure"   else "(varies)",
                        )
                        if hdp_key in evaluated_hdps:
                            hdps_skipped += 1
                            continue
                        evaluated_hdps.add(hdp_key)
                        # --- end dedup ---

                        hdps_evaluated += 1
                        # Augmented-query prefetch for subspace-extending HDPs
                        if ext_strategy == "subspace":
                            query_cache.prefetch_subspace_hdp(df, hdp_scopes, ext_dim, config)
                        candidate = evaluate_hdp(
                            hdp_scopes, pattern_type,
                            ext_strategy, ext_dim,
                            df, config, query_cache, pattern_cache,
                        )
                        if candidate is not None:
                            score_candidate(candidate, impact_calc, config)
                            if candidate.score > 0:
                                candidates.append(candidate)
                                metainsights_found += 1

            if scopes_evaluated % 5000 == 0:
                elapsed = time.time() - start_time
                print(f"  {scopes_evaluated:,} scopes | {patterns_found:,} patterns | "
                      f"{metainsights_found:,} MetaInsights | {elapsed:.1f}s elapsed")

    elapsed = time.time() - start_time
    candidates.sort(key=lambda c: c.score, reverse=True)

    total_hdps = hdps_evaluated + hdps_skipped
    dedup_rate = hdps_skipped / total_hdps if total_hdps > 0 else 0.0

    print(f"\nMining complete in {elapsed:.1f}s")
    print(f"  Scopes evaluated:      {scopes_evaluated:,}")
    print(f"  Patterns found:        {patterns_found:,}")
    print(f"  HDPs evaluated:        {hdps_evaluated:,}")
    print(f"  HDPs skipped (dedup):  {hdps_skipped:,}")
    print(f"  HDP dedup hit rate:    {dedup_rate:.1%}")
    print(f"  MetaInsights found:    {metainsights_found:,}")
    print(f"  Query cache hit rate:  {query_cache.hit_rate:.1%}")
    print(f"  Pattern cache rate:    {pattern_cache.hit_rate:.1%}")
    if candidates:
        print(f"  Top score:             {candidates[0].score:.4f}")

    # Pattern type breakdown
    type_counts: dict = {}
    for c in candidates:
        type_counts[c.pattern_type] = type_counts.get(c.pattern_type, 0) + 1
    print("\n  Candidates by pattern type:")
    for pt, cnt in sorted(type_counts.items(), key=lambda x: -x[1]):
        print(f"    {pt:20s}: {cnt:,}")

    # Verify S*
    tau, r, k = config.tau, 1.0, 3
    tau_r     = tau ** (1.0 / r)
    threshold = (1 - tau) * math.e / tau_r
    s_star    = (
        -tau * math.log2(tau) - r * (1 - tau) * math.log2((1 - tau) / k)
        if k >= threshold else
        -math.log2(tau) + r * (k * tau_r / math.e) * math.log2(math.e / (k * tau_r))
    )
    print(f"\n  S* (tau={tau}, r={r}, k={k}): {s_star:.4f}  (expected ~1.792)")

    diagnostics = {
        "elapsed":          elapsed,
        "scopes_evaluated": scopes_evaluated,
        "patterns_found":   patterns_found,
        "hdps_evaluated":   hdps_evaluated,
        "hdps_skipped":     hdps_skipped,
        "query_cache":      query_cache,
        "pattern_cache":    pattern_cache,
        "type_counts":      type_counts,
    }
    return candidates, diagnostics


# =============================================================================
# SAVE DIAGNOSTICS (adds dedup stats)
# =============================================================================

def save_diagnostics(candidates: list, diagnostics: dict, output_path: str):
    """Write engine diagnostics including HDP dedup stats."""
    qc = diagnostics["query_cache"]
    pc = diagnostics["pattern_cache"]
    tc = diagnostics.get("type_counts", {})

    total_hdps = diagnostics["hdps_evaluated"] + diagnostics["hdps_skipped"]
    dedup_rate = diagnostics["hdps_skipped"] / total_hdps if total_hdps > 0 else 0.0

    lines = [
        "=" * 70,
        "ENGINE DIAGNOSTICS -- HDP Deduplication",
        "=" * 70,
        f"Time elapsed:          {diagnostics['elapsed']:.1f}s",
        f"Scopes evaluated:      {diagnostics['scopes_evaluated']:,}",
        f"Patterns found:        {diagnostics['patterns_found']:,}",
        f"HDPs evaluated:        {diagnostics['hdps_evaluated']:,}",
        f"HDPs skipped (dedup):  {diagnostics['hdps_skipped']:,}",
        f"HDP dedup hit rate:    {dedup_rate:.1%}",
        f"MetaInsights:          {len(candidates):,}",
        f"Query cache:           {qc.hits:,} hits / {qc.misses:,} misses ({qc.hit_rate:.1%})",
        f"Pattern cache:         {pc.hits:,} hits / {pc.misses:,} misses ({pc.hit_rate:.1%})",
        "",
        "--- Candidates by Pattern Type ---",
    ]
    for pt, cnt in sorted(tc.items(), key=lambda x: -x[1]):
        bar = "#" * (cnt // 100)
        lines.append(f"  {pt:20s}: {cnt:6,}  {bar}")

    zero_types = [pt for pt in PATTERN_EVALUATORS if pt not in tc]
    if zero_types:
        lines.append(f"\n  Zero-candidate types: {zero_types}")

    lines += ["", "--- Score Distribution ---"]
    if candidates:
        lines += [
            f"  Max:    {candidates[0].score:.4f}",
            f"  Median: {candidates[len(candidates)//2].score:.4f}",
            f"  Min:    {candidates[-1].score:.4f}",
            f"  Above 0.1: {sum(1 for c in candidates if c.score >= 0.1):,}",
        ]
    else:
        lines.append("  (no candidates)")

    lines += ["", "--- Top 20 MetaInsights ---"]
    for i, c in enumerate(candidates[:20]):
        lines.append(f"\n  #{i+1}  score={c.score:.4f}  "
                     f"(conciseness={c.conciseness:.4f}, impact={c.impact:.4f} "
                     f"via {c.impact_measure_used})")
        lines.append(f"    Strategy:    {c.extending_strategy} on '{c.extending_dimension}'")
        lines.append(f"    Pattern:     {c.pattern_type}")
        lines.append(f"    Breakdown:   {c.breakdown}   Measure: {c.measure}")
        lines.append(f"    Base scope:  {c.base_subspace}")
        lines.append(f"    HDP size:    {c.hdp_size}")
        for cs in c.commonness_sets:
            members_str = ", ".join(str(m) for m in cs["members"][:8])
            if len(cs["members"]) > 8:
                members_str += f" ... (+{len(cs['members'])-8})"
            lines.append(f"    Commonness:  {cs['highlight']}  "
                         f"({cs['count']}/{c.hdp_size} = {cs['proportion']:.0%})")
            lines.append(f"      Members:   {members_str}")
        if c.exceptions:
            lines.append(f"    Exceptions ({len(c.exceptions)}):")
            for exc in c.exceptions[:5]:
                lines.append(f"      - {exc['member_label']}: {exc['category']} "
                             f"(highlight={exc['highlight']})")
            if len(c.exceptions) > 5:
                lines.append(f"      ... and {len(c.exceptions)-5} more")
        else:
            lines.append("    Exceptions:  none")

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"Diagnostics saved -> {output_path}")


# =============================================================================
# ENTRY POINT
# =============================================================================

if __name__ == "__main__":
    candidates, diagnostics = run_engine(VIEW1_CONFIG, time_budget_seconds=900)

    save_candidates(
        candidates,
        os.path.join(BASE_DIR, "metainsights", "view1_dedup_candidates.json"),
    )
    save_diagnostics(
        candidates,
        diagnostics,
        os.path.join(BASE_DIR, "reports", "engine_diagnostics_dedup.txt"),
    )
