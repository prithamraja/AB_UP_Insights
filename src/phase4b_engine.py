# =============================================================================
# Engine Upgrade: DuckDB Query Layer + HDP Deduplication
# =============================================================================
# Two targeted changes to the Phase 4a engine:
#
#   Change 1: Replace pandas query layer with DuckDB SQL
#     - query_data_scope: SELECT/SUM/GROUP BY via DuckDB
#     - ImpactCalculator: DuckDB-backed with pandas-compatible cache interface
#     - apply_subspace is removed (no longer needed)
#
#   Change 2: HDP deduplication set
#     - Tracks (member_subspaces, pattern_type, breakdown, measure) keys
#     - Skips evaluate_hdp if the exact HDP was already evaluated
#
# Everything else is unchanged from Phase 4a:
#   All 11 pattern evaluators, HDP construction, scoring, output format.
#
# Outputs:
#   metainsights/view1_duckdb_candidates.json
#   reports/engine_diagnostics_duckdb.txt
#
# Run from project root:
#   python src/phase4b_engine.py
# =============================================================================

import os
import sys
import math
import json
import time
import heapq
import warnings
from typing import Optional

import duckdb
import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# ---------------------------------------------------------------------------
# Import all unchanged components from Phase 4a
# ---------------------------------------------------------------------------
from phase4a_engine import (
    # Config
    ViewConfig, VIEW1_CONFIG,
    # Data structures
    Subspace, DataScope, Highlight, BasicDataPattern, MetaInsightCandidate,
    # Subspace & scope enumeration (use pandas df at init — one-time, cheap)
    generate_subspaces, generate_data_scopes,
    # Priority queue
    build_priority_queue,
    # Caches (query cache interface unchanged; prefetch not called — DuckDB is fast)
    QueryCache, PatternCache,
    # All 11 pattern evaluators
    PATTERN_EVALUATORS, TEMPORAL_ONLY_TYPES, CATEGORICAL_ONLY_TYPES,
    # HDP extending strategies (use pandas df for .unique() — kept at init)
    extend_subspace, extend_measure, extend_breakdown,
    # HDP helpers
    _member_label, evaluate_hdp as _evaluate_hdp_base,
    # Scoring (unchanged)
    compute_conciseness, compute_impact, score_candidate,
    # Output (save_candidates unchanged)
    save_candidates,
)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# =============================================================================
# CHANGE 1: DuckDB QUERY LAYER
# =============================================================================

def _build_where(subspace: Subspace) -> str:
    """Build a SQL WHERE clause from a subspace's filters. Returns empty string for {*}."""
    if not subspace.filters:
        return ""
    conditions = [
        f'"{dim}" = \'{str(val).replace(chr(39), chr(39)+chr(39))}\''
        for dim, val in subspace.filters
    ]
    return "WHERE " + " AND ".join(conditions)


def query_data_scope(con: duckdb.DuckDBPyConnection, data_scope: DataScope) -> pd.Series:
    """
    Execute: SELECT breakdown, SUM(measure) FROM view_data
             WHERE <subspace filters> GROUP BY breakdown ORDER BY breakdown

    Returns a pandas Series indexed by breakdown values.
    DuckDB parallelises the scan automatically across available cores.
    """
    where = _build_where(data_scope.subspace)
    sql = f"""
        SELECT "{data_scope.breakdown}" AS breakdown_val,
               SUM("{data_scope.measure}")  AS agg_val
        FROM view_data
        {where}
        GROUP BY "{data_scope.breakdown}"
        ORDER BY "{data_scope.breakdown}"
    """
    result = con.execute(sql).fetchdf()
    if len(result) == 0:
        return pd.Series(dtype=float)
    return result.set_index("breakdown_val")["agg_val"]


class ImpactCalculator:
    """
    Lazily computes and caches subspace impacts using DuckDB SQL.
    Interface identical to the pandas version in phase2_engine.
    """

    def __init__(self, con: duckdb.DuckDBPyConnection, impact_measures: list):
        self._con = con
        self._impact_measures = impact_measures
        self._cache: dict = {}

        # Pre-compute totals once at init (single full-table scan)
        sum_exprs = ", ".join(f'SUM("{m}") AS "{m}"' for m in impact_measures)
        row = con.execute(f"SELECT {sum_exprs} FROM view_data").fetchone()
        self._totals = {
            m: (row[i] if row[i] is not None else 0.0)
            for i, m in enumerate(impact_measures)
        }

    def get(self, subspace: Subspace) -> dict:
        if subspace in self._cache:
            return self._cache[subspace]

        where    = _build_where(subspace)
        sum_exprs = ", ".join(f'SUM("{m}") AS "{m}"' for m in self._impact_measures)
        row = self._con.execute(
            f"SELECT {sum_exprs} FROM view_data {where}"
        ).fetchone()

        impacts = {}
        for i, m in enumerate(self._impact_measures):
            total = self._totals[m]
            val   = row[i] if row[i] is not None else 0.0
            impacts[m] = val / total if total > 0 else 0.0

        self._cache[subspace] = impacts
        return impacts

    def max_impact(self, subspace: Subspace) -> float:
        return max(self.get(subspace).values())


def detect_pattern(
    con: duckdb.DuckDBPyConnection,
    data_scope: DataScope,
    pattern_type: str,
    query_cache: QueryCache,
    config: ViewConfig,
) -> BasicDataPattern:
    """
    Detect a specific pattern type in a data scope.
    Identical logic to phase4a_engine.detect_pattern — only the query layer
    changed from df (pandas) to con (DuckDB).
    """
    is_temporal = data_scope.breakdown in config.temporal_dimensions

    if pattern_type in TEMPORAL_ONLY_TYPES and not is_temporal:
        return BasicDataPattern(data_scope, "NO_PATTERN", None)
    if pattern_type in CATEGORICAL_ONLY_TYPES and is_temporal:
        return BasicDataPattern(data_scope, "NO_PATTERN", None)

    distribution = query_cache.get(data_scope)
    if distribution is None:
        distribution = query_data_scope(con, data_scope)   # DuckDB
        query_cache.put(data_scope, distribution)

    if len(distribution) == 0:
        return BasicDataPattern(data_scope, "NO_PATTERN", None)

    highlight = PATTERN_EVALUATORS[pattern_type](distribution)
    if highlight is not None:
        return BasicDataPattern(data_scope, pattern_type, highlight)

    # Check if any OTHER eligible type matches (TYPE_CHANGE exception signal)
    for other_type, other_eval in PATTERN_EVALUATORS.items():
        if other_type == pattern_type:
            continue
        if other_type in TEMPORAL_ONLY_TYPES and not is_temporal:
            continue
        if other_type in CATEGORICAL_ONLY_TYPES and is_temporal:
            continue
        if other_eval(distribution) is not None:
            return BasicDataPattern(data_scope, "OTHER_PATTERN", None)

    return BasicDataPattern(data_scope, "NO_PATTERN", None)


def evaluate_hdp(
    hdp_scopes: list,
    pattern_type: str,
    extending_strategy: str,
    extending_dimension: str,
    con: duckdb.DuckDBPyConnection,
    config: ViewConfig,
    query_cache: QueryCache,
    pattern_cache: PatternCache,
) -> Optional[MetaInsightCandidate]:
    """
    Identical logic to phase4a's evaluate_hdp — signature updated to accept
    `con` instead of `df`. Internally calls our updated detect_pattern.
    """
    from collections import Counter

    n       = len(hdp_scopes)
    tau     = config.tau
    patterns = []

    for ds in hdp_scopes:
        cached = pattern_cache.get(ds, pattern_type)
        if cached is not None:
            patterns.append(cached)
        else:
            p = detect_pattern(con, ds, pattern_type, query_cache, config)
            pattern_cache.put(ds, pattern_type, p)
            patterns.append(p)

        # Early termination
        j         = len(patterns)
        remaining = n - j
        if j > n * (1 - tau):
            valid = [
                (p.pattern_type, p.highlight)
                for p in patterns
                if p.pattern_type not in ("NO_PATTERN", "OTHER_PATTERN")
            ]
            if not valid:
                if remaining / n < tau:
                    return None
            else:
                max_count = Counter(valid).most_common(1)[0][1]
                if (max_count + remaining) / n < tau:
                    return None

    # Partition
    groups: dict = {}
    no_pattern_list    = []
    other_pattern_list = []

    for p in patterns:
        if p.pattern_type == "NO_PATTERN":
            no_pattern_list.append(p)
        elif p.pattern_type == "OTHER_PATTERN":
            other_pattern_list.append(p)
        else:
            groups.setdefault((p.pattern_type, p.highlight), []).append(p)

    commonness_sets    = []
    exception_patterns = []

    for (ptype, highlight), members in groups.items():
        proportion = len(members) / n
        if proportion > tau:
            commonness_sets.append({
                "highlight":    str(highlight),
                "pattern_type": ptype,
                "members":      [_member_label(m.data_scope, extending_strategy, extending_dimension)
                                 for m in members],
                "count":        len(members),
                "proportion":   round(proportion, 4),
            })
        else:
            exception_patterns.extend(members)

    if not commonness_sets:
        return None

    exception_patterns.extend(no_pattern_list)
    exception_patterns.extend(other_pattern_list)

    exceptions = []
    for ep in exception_patterns:
        label = _member_label(ep.data_scope, extending_strategy, extending_dimension)
        category = (
            "NO_PATTERN"       if ep.pattern_type == "NO_PATTERN"    else
            "TYPE_CHANGE"      if ep.pattern_type == "OTHER_PATTERN" else
            "HIGHLIGHT_CHANGE"
        )
        exceptions.append({
            "member_label": label,
            "category":     category,
            "highlight":    str(ep.highlight) if ep.highlight else None,
            "pattern_type": ep.pattern_type,
        })

    ref_scope = hdp_scopes[0]
    if extending_strategy == "subspace":
        base_filters  = frozenset(
            (k, v) for k, v in ref_scope.subspace.filters if k != extending_dimension
        )
        base_subspace = Subspace(base_filters)
    else:
        base_subspace = ref_scope.subspace

    return MetaInsightCandidate(
        extending_strategy=extending_strategy,
        extending_dimension=extending_dimension,
        pattern_type=pattern_type,
        breakdown=ref_scope.breakdown if extending_strategy != "breakdown" else "(varies)",
        measure=ref_scope.measure    if extending_strategy != "measure"    else "(varies)",
        base_subspace=base_subspace,
        commonness_sets=commonness_sets,
        exceptions=exceptions,
        hdp_size=n,
        hdp_member_subspaces=[ds.subspace for ds in hdp_scopes],
    )


# =============================================================================
# UPDATED RUN_ENGINE: DuckDB + HDP deduplication
# =============================================================================

def run_engine(config: ViewConfig, time_budget_seconds: int = 900) -> tuple:
    """
    Phase 4a engine with two upgrades:
      1. DuckDB query layer (query_data_scope, ImpactCalculator)
      2. HDP deduplication set (skip exact-duplicate HDP evaluations)
    """
    print("=" * 70)
    print("ENGINE UPGRADE: DuckDB Query Layer + HDP Deduplication")
    print("=" * 70)

    # --- Load parquet into DuckDB in-memory table ---
    print(f"Loading {config.parquet_path} into DuckDB ...")
    con = duckdb.connect()
    con.execute(f"""
        CREATE TABLE view_data AS
        SELECT * FROM read_parquet('{config.parquet_path.replace(chr(92), '/')}')
    """)
    row_count = con.execute("SELECT COUNT(*) FROM view_data").fetchone()[0]
    col_count = len(con.execute("DESCRIBE view_data").fetchdf())
    print(f"  {row_count:,} rows, {col_count} cols")

    # Keep pandas df for generate_subspaces / extend_subspace (unique value enumeration)
    df = con.execute("SELECT * FROM view_data").fetchdf()

    # Pattern type partitions
    pattern_types_categorical = [pt for pt in PATTERN_EVALUATORS if pt not in TEMPORAL_ONLY_TYPES]
    pattern_types_temporal    = [pt for pt in PATTERN_EVALUATORS if pt not in CATEGORICAL_ONLY_TYPES]
    print(f"\nPattern types: {len(pattern_types_categorical)} categorical, "
          f"{len(pattern_types_temporal)} temporal  ({len(PATTERN_EVALUATORS)} total)")

    # Initialise
    query_cache    = QueryCache()
    pattern_cache  = PatternCache()
    impact_calc    = ImpactCalculator(con, config.impact_measures)
    candidates: list = []
    evaluated_hdps: set = set()   # Change 2: dedup set
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
                    pattern = detect_pattern(con, ds, pattern_type, query_cache, config)
                    pattern_cache.put(ds, pattern_type, pattern)

                if pattern.pattern_type == pattern_type:
                    patterns_found += 1

                    extensions = []
                    extensions.extend(extend_subspace(ds, df, config))
                    extensions.extend(extend_measure(ds, config))
                    extensions.extend(extend_breakdown(ds, config))

                    for ext_strategy, ext_dim, hdp_scopes in extensions:
                        # --- Change 2: HDP deduplication ---
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
                        candidate = evaluate_hdp(
                            hdp_scopes, pattern_type,
                            ext_strategy, ext_dim,
                            con, config, query_cache, pattern_cache,
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
        "ENGINE DIAGNOSTICS — DuckDB Query Layer + HDP Deduplication",
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
        os.path.join(BASE_DIR, "metainsights", "view1_duckdb_candidates.json"),
    )
    save_diagnostics(
        candidates,
        diagnostics,
        os.path.join(BASE_DIR, "reports", "engine_diagnostics_duckdb.txt"),
    )
