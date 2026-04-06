# =============================================================================
# Phase 4a: All Pattern Types on View 1
# =============================================================================
# Extends Phase 2 with 10 new pattern type evaluators (11 total).
# The engine architecture, caching, HDP construction, scoring, and
# orchestrator are unchanged from phase2_engine.py — only the pattern
# evaluator registry, detect_pattern, and run_engine loop are updated.
#
# New pattern types added:
#   Categorical: OUTSTANDING_LAST, TOP_TWO, LAST_TWO, EVENNESS, ATTRIBUTION
#   Temporal:    TREND, OUTLIER, SEASONALITY, CHANGE_POINT, UNIMODALITY
#
# Outputs:
#   metainsights/view1_all_patterns_candidates.json
#   reports/engine_diagnostics_all_patterns.txt
#
# Run from project root:
#   python src/phase4a_engine.py
# =============================================================================

import os
import sys
import math
import json
import time
import heapq
from typing import Optional

import warnings
import numpy as np
import pandas as pd
from scipy import stats

# Suppress benign scipy/numpy warnings from constant or near-constant time series
warnings.filterwarnings("ignore", category=stats.ConstantInputWarning)
warnings.filterwarnings("ignore", message=".*catastrophic cancellation.*")
warnings.filterwarnings("ignore", message=".*invalid value encountered in divide.*")

# ---------------------------------------------------------------------------
# Import all unchanged infrastructure from Phase 2
# ---------------------------------------------------------------------------
# Add src/ to path so the import works regardless of working directory
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from phase2_engine import (
    # Config & data structures
    ViewConfig, VIEW1_CONFIG,
    Subspace, DataScope, Highlight, BasicDataPattern,
    # Data scope utilities
    apply_subspace, generate_subspaces, generate_data_scopes,
    # Impact & priority queue
    ImpactCalculator, build_priority_queue,
    # Query infrastructure
    query_data_scope, QueryCache, PatternCache,
    # Phase 2 evaluator (kept in registry)
    evaluate_outstanding_1,
    # HDP construction
    extend_subspace, extend_measure, extend_breakdown,
    _member_label, MetaInsightCandidate, evaluate_hdp,
    # Scoring
    compute_conciseness, compute_impact, score_candidate,
    # Output helper (save_candidates unchanged)
    save_candidates,
)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# =============================================================================
# NEW PATTERN EVALUATORS
# =============================================================================
# All evaluators share the same interface:
#   evaluate_<type>(distribution: pd.Series) -> Optional[Highlight]
#
# distribution: Series indexed by breakdown values, values are aggregated measures.
# Returns Highlight if pattern detected, else None.
# =============================================================================

# -----------------------------------------------------------------------------
# Categorical pattern types (non-temporal breakdowns only)
# -----------------------------------------------------------------------------

def evaluate_outstanding_last(distribution: pd.Series) -> Optional[Highlight]:
    """
    Outstanding Last: one breakdown value is significantly lower than the rest.

    Criteria:
      1. z-score of the minimum relative to the rest <= -2.0
      2. Minimum is at most 0.67x the second-lowest value (inverse of 1.5x ratio)

    Highlight: (breakdown_value_with_lowest_aggregate,)
    """
    dist = distribution.dropna()
    if len(dist) < 3 or dist.sum() == 0:
        return None

    min_val   = dist.min()
    min_label = dist.idxmin()
    rest      = dist.drop(min_label)
    rest_mean = rest.mean()
    rest_std  = rest.std()

    if rest_std > 0:
        if (min_val - rest_mean) / rest_std > -2.0:
            return None
    else:
        if min_val >= rest_mean:
            return None

    second_min = rest.min()
    if second_min > 0 and min_val / second_min > 0.67:
        return None

    return Highlight(values=(min_label,))


def evaluate_top_two(distribution: pd.Series) -> Optional[Highlight]:
    """
    Top-Two: two breakdown values are significantly higher than the rest.

    Criteria:
      1. Both top-2 values exceed mean + 1.5*std of the remaining values
      2. 2nd-highest is at least 1.3x the 3rd-highest

    Highlight: (top1_label, top2_label) — sorted alphabetically so that
    (GS, OBG) always hashes identically regardless of order.
    """
    dist = distribution.dropna()
    if len(dist) < 4 or dist.sum() == 0:
        return None

    sorted_dist = dist.sort_values(ascending=False)
    top1_label, top2_label = sorted_dist.index[0], sorted_dist.index[1]
    top1_val,   top2_val   = sorted_dist.iloc[0],  sorted_dist.iloc[1]

    rest      = dist.drop([top1_label, top2_label])
    rest_mean = rest.mean()
    rest_std  = rest.std()

    if rest_std > 0:
        if (top1_val - rest_mean) / rest_std < 1.5:
            return None
        if (top2_val - rest_mean) / rest_std < 1.5:
            return None
    else:
        if top2_val <= rest_mean:
            return None

    third_val = sorted_dist.iloc[2]
    if third_val > 0 and top2_val / third_val < 1.3:
        return None

    return Highlight(values=tuple(sorted([str(top1_label), str(top2_label)])))


def evaluate_last_two(distribution: pd.Series) -> Optional[Highlight]:
    """
    Last-Two: two breakdown values are significantly lower than the rest.

    Criteria:
      1. Both bottom-2 values are below mean - 1.5*std of the remaining values
      2. 2nd-lowest is at most 0.77x (1/1.3) the 3rd-lowest

    Highlight: (bot1_label, bot2_label) — sorted alphabetically.
    """
    dist = distribution.dropna()
    if len(dist) < 4 or dist.sum() == 0:
        return None

    sorted_dist = dist.sort_values(ascending=True)
    bot1_label, bot2_label = sorted_dist.index[0], sorted_dist.index[1]
    bot1_val,   bot2_val   = sorted_dist.iloc[0],  sorted_dist.iloc[1]

    rest      = dist.drop([bot1_label, bot2_label])
    rest_mean = rest.mean()
    rest_std  = rest.std()

    if rest_std > 0:
        if (bot1_val - rest_mean) / rest_std > -1.5:
            return None
        if (bot2_val - rest_mean) / rest_std > -1.5:
            return None
    else:
        if bot2_val >= rest_mean:
            return None

    third_val = sorted_dist.iloc[2]
    if third_val > 0 and bot2_val / third_val > 0.77:
        return None

    return Highlight(values=tuple(sorted([str(bot1_label), str(bot2_label)])))


def evaluate_evenness(distribution: pd.Series) -> Optional[Highlight]:
    """
    Evenness: all breakdown values are distributed approximately equally.

    Criteria:
      1. Coefficient of variation (std/mean) < 0.15
      2. No single value accounts for more than 2/n of the total
         (where n = number of breakdown values)

    Highlight: ("EVEN",) — constant, since the pattern is the absence of variation.
    """
    dist = distribution.dropna()
    if len(dist) < 3:
        return None

    mean = dist.mean()
    if mean == 0:
        return None

    if dist.std() / mean >= 0.15:
        return None

    n = len(dist)
    if dist.max() / dist.sum() > 2.0 / n:
        return None

    return Highlight(values=("EVEN",))


def evaluate_attribution(distribution: pd.Series) -> Optional[Highlight]:
    """
    Attribution: one breakdown value dominates — accounts for the majority.

    Criteria:
      1. Top value accounts for > 50% of the total
      2. Top value is at least 2x the second-highest

    Highlight: (dominant_breakdown_value,)

    Note: similar to OUTSTANDING_1 but distinguished by the > 50% share criterion
    (OUTSTANDING_1 is z-score based; ATTRIBUTION is share-of-total based).
    """
    dist = distribution.dropna()
    if len(dist) < 3 or dist.sum() == 0:
        return None

    total     = dist.sum()
    max_val   = dist.max()
    max_label = dist.idxmax()

    if max_val / total <= 0.5:
        return None

    second_max = dist.drop(max_label).max()
    if second_max > 0 and max_val / second_max < 2.0:
        return None

    return Highlight(values=(max_label,))


# -----------------------------------------------------------------------------
# Temporal pattern types (temporal breakdowns only)
# -----------------------------------------------------------------------------

def evaluate_trend(distribution: pd.Series) -> Optional[Highlight]:
    """
    Trend: significant monotonic upward or downward trend in the time series.

    Method: Spearman rank correlation against the integer time index.
    Criteria:
      1. |rho| > 0.5
      2. p-value < 0.05

    Note: distribution.sort_index() is called inside query_data_scope so
    temporal order is preserved when the index is a string like "2023-04".

    Highlight: ("INCREASING",) or ("DECREASING",)
    """
    dist = distribution.dropna()
    if len(dist) < 4:
        return None

    values = dist.values.astype(float)
    x      = np.arange(len(values))
    rho, p = stats.spearmanr(x, values)

    if p >= 0.05 or abs(rho) < 0.5:
        return None

    return Highlight(values=("INCREASING" if rho > 0 else "DECREASING",))


def evaluate_outlier(distribution: pd.Series) -> Optional[Highlight]:
    """
    Outlier: one or more time points are statistical outliers (3-sigma rule).

    Criteria:
      1. At least 5 time points
      2. |value - mean| > 3 * std for the outlier(s)
      3. At most 20% of points are outliers (otherwise it's structural, not anomalous)

    Highlight: tuple of ((label, direction), ...) sorted by label for consistency.
    Direction is "ABOVE" or "BELOW".
    """
    dist = distribution.dropna()
    if len(dist) < 5:
        return None

    mean = dist.mean()
    std  = dist.std()
    if std == 0:
        return None

    outliers = []
    for label, value in dist.items():
        z = (value - mean) / std
        if abs(z) > 3.0:
            outliers.append((str(label), "ABOVE" if z > 0 else "BELOW"))

    if not outliers or len(outliers) > 0.2 * len(dist):
        return None

    return Highlight(values=tuple(sorted(outliers)))


def evaluate_seasonality(distribution: pd.Series) -> Optional[Highlight]:
    """
    Seasonality: repeating periodic pattern in the time series.

    Method: autocorrelation at fixed lags (3, 4, 6, 12) corresponding to
    quarterly, tri-annual, semi-annual, and annual cycles for monthly data.

    Criteria:
      1. At least 12 time points
      2. Autocorrelation at any candidate lag > 0.4
      3. Lag must be < n/2 to be statistically meaningful

    Highlight: ("PERIOD_<lag>",) — the strongest seasonal period found.
    """
    dist = distribution.dropna()
    if len(dist) < 12:
        return None

    values = dist.values.astype(float)
    n      = len(values)
    mean   = values.mean()
    std    = values.std()
    if std == 0:
        return None

    normed   = (values - mean) / std
    best_lag = None
    best_acf = 0.0

    for lag in [3, 4, 6, 12]:
        if lag > n // 2:  # allow lag == n//2 (e.g. lag=12 on n=24)
            continue
        acf = np.corrcoef(normed[:n - lag], normed[lag:])[0, 1]
        if np.isnan(acf):
            continue
        if acf > 0.4 and acf > best_acf:
            best_acf = acf
            best_lag = lag

    if best_lag is None:
        return None

    return Highlight(values=(f"PERIOD_{best_lag}",))


def evaluate_change_point(distribution: pd.Series) -> Optional[Highlight]:
    """
    Change Point: significant shift in the mean value at some point.

    Method: exhaustive split search with Welch's t-test at each candidate split.
    Criteria:
      1. At least 6 time points
      2. Both sides of the split have at least 3 points
      3. Best split has p-value < 0.01

    Highlight: (change_point_label,) — the time point where the new regime begins.
    """
    dist = distribution.dropna()
    if len(dist) < 6:
        return None

    values = dist.values.astype(float)
    labels = dist.index.tolist()
    best_p   = 1.0
    best_idx = None

    for split in range(3, len(values) - 2):
        _, p = stats.ttest_ind(values[:split], values[split:], equal_var=False)
        if p < best_p:
            best_p   = p
            best_idx = split

    if best_p >= 0.01 or best_idx is None:
        return None

    return Highlight(values=(str(labels[best_idx]),))


def evaluate_unimodality(distribution: pd.Series) -> Optional[Highlight]:
    """
    Unimodality: time series forms a single peak (inverted-U) or valley (U-shape).

    Method: identify the global extremum, then check that values monotonically
    increase toward it from the left and decrease away on the right (peak),
    or vice versa (valley). 70% tolerance on step direction allows real-world noise.

    Criteria:
      1. At least 5 time points
      2. Extremum is not at the edges (interior only)
      3. >= 70% of left-side steps go in the correct direction
      4. >= 70% of right-side steps go in the correct direction

    Highlight: ("PEAK", extremum_label) or ("VALLEY", extremum_label)
    """
    dist = distribution.dropna()
    if len(dist) < 5:
        return None

    values = dist.values.astype(float)
    labels = dist.index.tolist()
    n      = len(values)

    best_shape = None
    best_label = None
    best_score = 0.0

    for shape, ext_fn, left_dir, right_dir in [
        ("PEAK",   np.argmax, lambda d: d > 0, lambda d: d < 0),
        ("VALLEY", np.argmin, lambda d: d < 0, lambda d: d > 0),
    ]:
        idx = ext_fn(values)
        if not (1 <= idx <= n - 2):
            continue

        left_diffs  = np.diff(values[:idx + 1])
        right_diffs = np.diff(values[idx:])

        left_ok  = (np.sum(left_dir(left_diffs))  / len(left_diffs))  if len(left_diffs)  > 0 else 0
        right_ok = (np.sum(right_dir(right_diffs)) / len(right_diffs)) if len(right_diffs) > 0 else 0

        score = (left_ok + right_ok) / 2
        if left_ok >= 0.7 and right_ok >= 0.7 and score > best_score:
            best_shape = shape
            best_label = str(labels[idx])
            best_score = score

    if best_shape is None:
        return None

    return Highlight(values=(best_shape, best_label))


# =============================================================================
# UPDATED PATTERN REGISTRY
# =============================================================================

PATTERN_EVALUATORS = {
    "OUTSTANDING_1":    evaluate_outstanding_1,     # Phase 2 (unchanged)
    "OUTSTANDING_LAST": evaluate_outstanding_last,
    "TOP_TWO":          evaluate_top_two,
    "LAST_TWO":         evaluate_last_two,
    "EVENNESS":         evaluate_evenness,
    "ATTRIBUTION":      evaluate_attribution,
    "TREND":            evaluate_trend,
    "OUTLIER":          evaluate_outlier,
    "SEASONALITY":      evaluate_seasonality,
    "CHANGE_POINT":     evaluate_change_point,
    "UNIMODALITY":      evaluate_unimodality,
}

# Temporal types: only valid when the breakdown is a temporal dimension
TEMPORAL_ONLY_TYPES = {
    "TREND", "OUTLIER", "SEASONALITY", "CHANGE_POINT", "UNIMODALITY"
}

# Categorical types: only valid when the breakdown is a categorical dimension
CATEGORICAL_ONLY_TYPES = {
    "OUTSTANDING_1", "OUTSTANDING_LAST", "TOP_TWO", "LAST_TWO",
    "EVENNESS", "ATTRIBUTION"
}

# ---------------------------------------------------------------------------
# Patch phase2_engine so evaluate_hdp uses the updated registry and detect_pattern.
# evaluate_hdp in phase2_engine calls its module-local detect_pattern and
# PATTERN_EVALUATORS; without this patch it only knows OUTSTANDING_1.
# ---------------------------------------------------------------------------
import phase2_engine as _p2
_p2.PATTERN_EVALUATORS  = PATTERN_EVALUATORS
_p2.TEMPORAL_ONLY_TYPES = TEMPORAL_ONLY_TYPES


# =============================================================================
# UPDATED DETECT_PATTERN
# =============================================================================

def detect_pattern(
    df: pd.DataFrame,
    data_scope: DataScope,
    pattern_type: str,
    query_cache: QueryCache,
    config: ViewConfig,
) -> BasicDataPattern:
    """
    Detect a specific pattern type in a data scope.

    Returns:
      BasicDataPattern(pattern_type)  if the requested type matches
      BasicDataPattern("OTHER_PATTERN") if a different type matches instead
      BasicDataPattern("NO_PATTERN")   if no type matches

    The OTHER_PATTERN return means an HDP member will be categorised as a
    TYPE_CHANGE exception — more informative than NO_PATTERN.
    """
    is_temporal = data_scope.breakdown in config.temporal_dimensions

    # Eligibility check for the requested type
    if pattern_type in TEMPORAL_ONLY_TYPES and not is_temporal:
        return BasicDataPattern(data_scope, "NO_PATTERN", None)
    if pattern_type in CATEGORICAL_ONLY_TYPES and is_temporal:
        return BasicDataPattern(data_scope, "NO_PATTERN", None)

    # Query (cached)
    distribution = query_cache.get(data_scope)
    if distribution is None:
        distribution = query_data_scope(df, data_scope)
        query_cache.put(data_scope, distribution)

    if len(distribution) == 0:
        return BasicDataPattern(data_scope, "NO_PATTERN", None)

    # Try the requested type
    highlight = PATTERN_EVALUATORS[pattern_type](distribution)
    if highlight is not None:
        return BasicDataPattern(data_scope, pattern_type, highlight)

    # Check whether any OTHER eligible type matches (TYPE_CHANGE exception signal)
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


# Patch the remaining module-level name so evaluate_hdp picks up our version
_p2.detect_pattern = detect_pattern


# =============================================================================
# UPDATED RUN_ENGINE
# =============================================================================

def run_engine(config: ViewConfig, time_budget_seconds: int = 900) -> tuple:
    """
    Main MetaInsight mining loop with all 11 pattern types.

    Changes from Phase 2:
      - Iterates over all eligible pattern types per data scope
        (categorical types for categorical breakdowns, temporal for temporal)
      - detect_pattern now returns OTHER_PATTERN when a different type matches
      - Diagnostics include per-type candidate count
    """
    print("=" * 70)
    print("PHASE 4a: MetaInsight Engine — All Pattern Types")
    print("=" * 70)
    print(f"Loading {config.parquet_path} ...")
    df = pd.read_parquet(config.parquet_path)
    print(f"  {len(df):,} rows x {len(df.columns)} cols")

    query_cache   = QueryCache()
    pattern_cache = PatternCache()
    impact_calc   = ImpactCalculator(df, config.impact_measures)
    candidates: list = []

    # Partition pattern types by breakdown eligibility
    pattern_types_categorical = [
        pt for pt in PATTERN_EVALUATORS if pt not in TEMPORAL_ONLY_TYPES
    ]
    pattern_types_temporal = [
        pt for pt in PATTERN_EVALUATORS if pt not in CATEGORICAL_ONLY_TYPES
    ]
    print(f"\nPattern types:")
    print(f"  Categorical ({len(pattern_types_categorical)}): {pattern_types_categorical}")
    print(f"  Temporal    ({len(pattern_types_temporal)}):    {pattern_types_temporal}")

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
    start_time        = time.time()
    scopes_evaluated  = 0
    patterns_found    = 0
    hdps_evaluated    = 0
    metainsights_found = 0

    print(f"\nMining (budget: {time_budget_seconds}s) ...")

    while queue and (time.time() - start_time) < time_budget_seconds:
        neg_impact, _, subspace = heapq.heappop(queue)
        data_scopes = generate_data_scopes(subspace, config)

        for ds in data_scopes:
            # Honour time budget inside inner loop (avoids overshoot on large subspaces)
            if (time.time() - start_time) >= time_budget_seconds:
                break

            scopes_evaluated += 1
            is_temporal  = ds.breakdown in config.temporal_dimensions
            active_types = pattern_types_temporal if is_temporal else pattern_types_categorical

            for pattern_type in active_types:
                # Check pattern cache before running evaluator
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
                        hdps_evaluated += 1
                        # Augmented-query prefetch for subspace-extending HDPs
                        if ext_strategy == "subspace":
                            query_cache.prefetch_subspace_hdp(df, hdp_scopes, ext_dim)
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

    print(f"\nMining complete in {elapsed:.1f}s")
    print(f"  Scopes evaluated:      {scopes_evaluated:,}")
    print(f"  Patterns found:        {patterns_found:,}")
    print(f"  HDPs evaluated:        {hdps_evaluated:,}")
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
        "query_cache":      query_cache,
        "pattern_cache":    pattern_cache,
        "type_counts":      type_counts,
    }
    return candidates, diagnostics


# =============================================================================
# UPDATED SAVE_DIAGNOSTICS (adds pattern type breakdown)
# =============================================================================

def save_diagnostics(candidates: list, diagnostics: dict, output_path: str):
    """Write engine diagnostics report including per-pattern-type counts."""
    qc = diagnostics["query_cache"]
    pc = diagnostics["pattern_cache"]
    tc = diagnostics.get("type_counts", {})

    lines = [
        "=" * 70,
        "METAINSIGHT ENGINE DIAGNOSTICS — ALL PATTERN TYPES",
        "=" * 70,
        f"Time elapsed:     {diagnostics['elapsed']:.1f}s",
        f"Scopes evaluated: {diagnostics['scopes_evaluated']:,}",
        f"Patterns found:   {diagnostics['patterns_found']:,}",
        f"HDPs evaluated:   {diagnostics['hdps_evaluated']:,}",
        f"MetaInsights:     {len(candidates):,}",
        f"Query cache:      {qc.hits:,} hits / {qc.misses:,} misses ({qc.hit_rate:.1%})",
        f"Pattern cache:    {pc.hits:,} hits / {pc.misses:,} misses ({pc.hit_rate:.1%})",
        "",
        "--- Candidates by Pattern Type ---",
    ]
    for pt, cnt in sorted(tc.items(), key=lambda x: -x[1]):
        bar = "#" * (cnt // 200)
        lines.append(f"  {pt:20s}: {cnt:6,}  {bar}")

    zero_types = [pt for pt in PATTERN_EVALUATORS if pt not in tc]
    if zero_types:
        lines.append(f"\n  Zero-candidate types: {zero_types}")

    lines += [
        "",
        "--- Score Distribution ---",
    ]
    if candidates:
        lines += [
            f"  Max:    {candidates[0].score:.4f}",
            f"  Median: {candidates[len(candidates) // 2].score:.4f}",
            f"  Min:    {candidates[-1].score:.4f}",
            f"  Total above 0.1: {sum(1 for c in candidates if c.score >= 0.1):,}",
        ]
    else:
        lines.append("  (no candidates)")

    lines += ["", "--- Top 20 MetaInsights ---"]
    for i, c in enumerate(candidates[:20]):
        lines.append(f"\n  #{i + 1}  score={c.score:.4f}  "
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
                members_str += f" ... (+{len(cs['members']) - 8})"
            lines.append(f"    Commonness:  {cs['highlight']}  "
                         f"({cs['count']}/{c.hdp_size} = {cs['proportion']:.0%})")
            lines.append(f"      Members:   {members_str}")
        if c.exceptions:
            lines.append(f"    Exceptions ({len(c.exceptions)}):")
            for exc in c.exceptions[:5]:
                lines.append(f"      - {exc['member_label']}: {exc['category']} "
                             f"(highlight={exc['highlight']})")
            if len(c.exceptions) > 5:
                lines.append(f"      ... and {len(c.exceptions) - 5} more")
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
        os.path.join(BASE_DIR, "metainsights", "view1_all_patterns_candidates.json"),
    )
    save_diagnostics(
        candidates,
        diagnostics,
        os.path.join(BASE_DIR, "reports", "engine_diagnostics_all_patterns.txt"),
    )
