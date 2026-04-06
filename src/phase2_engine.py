# =============================================================================
# Phase 2: MetaInsight Engine - Single View, Single Pattern Type
# =============================================================================
# Implements the core MetaInsight mining pipeline on View 1 (Claims Lifecycle)
# using a single pattern type: Outstanding #1.
#
# Architecture:
#   Module A - View configuration and data scope enumeration
#   Module B - Pattern detector (Outstanding #1 evaluator + caches)
#   Module C - HDP construction and MetaInsight identification
#   Module D - Scorer (conciseness + impact)
#   Module E - Engine orchestrator and output
#
# Outputs:
#   metainsights/view1_candidates.json  - all scored MetaInsight candidates
#   reports/engine_diagnostics.txt      - search space stats, cache hit rates, timing
#
# Run from project root:
#   python src/phase2_engine.py
# =============================================================================

import os
import sys
import math
import json
import time
import heapq
from typing import Optional
from dataclasses import dataclass, field
from collections import Counter

import numpy as np
import pandas as pd

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# =============================================================================
# MODULE A: VIEW CONFIGURATION & DATA SCOPE ENUMERATION
# =============================================================================

@dataclass
class ViewConfig:
    """Configuration for a single analytical view passed to the engine."""
    name: str
    parquet_path: str

    dimensions: list            # categorical dimension columns
    temporal_dimensions: list   # temporal dimension columns (breakdown only)
    measures: list              # numeric measure columns
    impact_measures: list       # subset of measures used for impact scoring

    max_subspace_depth: int = 2  # max number of filters in a subspace
    tau: float = 0.5             # commonness proportion threshold
    min_impact: float = 0.01     # prune subspaces below this impact
    min_hdp_size: int = 3        # minimum HDP members to form a MetaInsight


# --- View 1 configuration ---
VIEW1_CONFIG = ViewConfig(
    name="Claims Lifecycle",
    parquet_path=os.path.join(BASE_DIR, "views", "view1_claims_lifecycle.parquet"),

    dimensions=[
        "division",          # 18 values
        "district",          # 75 values
        "hospital_type",     # 2 values
        "hospital_sub_type", # 8 values
        "specialty_code",    # 11 values
        "disease_category",  # 5 values
        "gender",            # 2 values
        "age_group",         # 4 values
        "admission_type",    # 2 values
        "discharge_type",    # 5 values
        "claim_status",      # 5 values
        "preauth_status",    # 4 values
        "bed_size_bucket",   # 4 values
    ],

    temporal_dimensions=[
        "admission_month",    # 36 values
        "admission_quarter",  # 13 values
        "admission_year",     # 4 values
    ],

    measures=[
        "case_count",
        "amount_claimed",
        "amount_approved",
        "amount_paid",
        "length_of_stay",
        "is_emergency",
        "is_death",
        "is_lama_dama",
        "settlement_tat_days",
        "query_count",
        "base_amount",
        "computed_final_amount",
    ],

    impact_measures=[
        "case_count",      # volume signal
        "amount_claimed",  # financial exposure
        "amount_paid",     # actual outflow
    ],

    max_subspace_depth=2,
    tau=0.5,
    min_impact=0.01,
    min_hdp_size=3,
)


# --- Core data structures ---

@dataclass(frozen=True)
class Subspace:
    """
    A set of dimension=value filters defining a slice of the data.
    Empty frozenset represents the full dataset (no filter applied).
    """
    filters: frozenset  # frozenset of (dim_name, value) tuples

    @property
    def depth(self) -> int:
        return len(self.filters)

    def __repr__(self):
        if not self.filters:
            return "{*}"
        return "{" + ", ".join(f"{k}:{v}" for k, v in sorted(self.filters)) + "}"


@dataclass(frozen=True)
class DataScope:
    """
    A 3-tuple (subspace, breakdown, measure) defining a specific analytical query.
    Corresponds to: SELECT breakdown, SUM(measure) ... WHERE subspace GROUP BY breakdown
    """
    subspace: Subspace
    breakdown: str   # dimension used for group-by
    measure: str     # column to aggregate

    def __repr__(self):
        return f"DS({self.subspace}, {self.breakdown}, {self.measure})"


@dataclass(frozen=True)
class Highlight:
    """
    Encodes the essential characteristic of a pattern.
    For Outstanding #1: the single breakdown value with the highest aggregate.
    """
    values: tuple  # tuple for hashability

    def __repr__(self):
        return str(self.values)


@dataclass(frozen=True)
class BasicDataPattern:
    """
    The result of evaluating one pattern type on one data scope.
    pattern_type is 'NO_PATTERN' when the pattern criteria are not met.
    """
    data_scope: DataScope
    pattern_type: str
    highlight: Optional[Highlight]


def apply_subspace(df: pd.DataFrame, subspace: Subspace) -> pd.DataFrame:
    """Filter df by all dimension=value conditions in the subspace."""
    result = df
    for dim, val in subspace.filters:
        result = result[result[dim] == val]
    return result


def generate_subspaces(config: ViewConfig, df: pd.DataFrame) -> list:
    """
    Generate all subspaces from depth 0 to max_subspace_depth.
    Only categorical dimensions (not temporal) are used as filters.
    Temporal dimensions are reserved for breakdowns only.
    """
    subspaces = [Subspace(frozenset())]  # depth 0: full dataset

    # Depth 1: one filter per (dimension, value) pair
    depth1 = []
    for dim in config.dimensions:
        for val in df[dim].dropna().unique():
            depth1.append(Subspace(frozenset([(dim, val)])))
    subspaces.extend(depth1)

    # Depth 2: combine pairs of depth-1 subspaces from different dimensions
    if config.max_subspace_depth >= 2:
        for i, s1 in enumerate(depth1):
            dim1 = next(iter(s1.filters))[0]
            for s2 in depth1[i + 1:]:
                dim2 = next(iter(s2.filters))[0]
                if dim1 != dim2:
                    subspaces.append(Subspace(s1.filters | s2.filters))

    return subspaces


def generate_data_scopes(subspace: Subspace, config: ViewConfig) -> list:
    """
    For a given subspace, enumerate all valid (breakdown, measure) combinations.
    Breakdown dimensions that are already used as filters are excluded.
    """
    filtered_dims = {dim for dim, _ in subspace.filters}
    available_breakdowns = [
        d for d in config.dimensions + config.temporal_dimensions
        if d not in filtered_dims
    ]
    return [
        DataScope(subspace, breakdown, measure)
        for breakdown in available_breakdowns
        for measure in config.measures
    ]


class ImpactCalculator:
    """
    Lazily computes and caches subspace-level impact values.
    Impact(subspace, measure) = SUM(measure in subspace) / SUM(measure in full df).
    """

    def __init__(self, df: pd.DataFrame, impact_measures: list):
        self._df = df
        self._totals = {m: df[m].sum() for m in impact_measures}
        self._impact_measures = impact_measures
        self._cache: dict = {}

    def get(self, subspace: Subspace) -> dict:
        if subspace in self._cache:
            return self._cache[subspace]
        filtered = apply_subspace(self._df, subspace)
        impacts = {}
        for m in self._impact_measures:
            total = self._totals[m]
            impacts[m] = filtered[m].sum() / total if total > 0 else 0.0
        self._cache[subspace] = impacts
        return impacts

    def max_impact(self, subspace: Subspace) -> float:
        return max(self.get(subspace).values())


def build_priority_queue(
    subspaces: list,
    impact_calc: ImpactCalculator,
    min_impact: float,
) -> list:
    """
    Build a max-heap of (neg_impact, tiebreaker, subspace) tuples.
    Subspaces below min_impact are pruned entirely.
    The tiebreaker counter avoids comparing Subspace objects (which don't
    implement __lt__, so heapq would raise TypeError without it).
    """
    queue = []
    counter = 0
    for subspace in subspaces:
        max_imp = impact_calc.max_impact(subspace)
        if max_imp >= min_impact:
            heapq.heappush(queue, (-max_imp, counter, subspace))
            counter += 1
    return queue


# =============================================================================
# MODULE B: PATTERN DETECTOR
# =============================================================================

def query_data_scope(df: pd.DataFrame, data_scope: DataScope) -> pd.Series:
    """
    Execute: SELECT breakdown, SUM(measure) FROM df
             WHERE <subspace filters> GROUP BY breakdown
    Returns a Series indexed by breakdown values, sorted by index.
    """
    filtered = apply_subspace(df, data_scope.subspace)
    if len(filtered) == 0:
        return pd.Series(dtype=float)
    return filtered.groupby(data_scope.breakdown)[data_scope.measure].sum().sort_index()


class QueryCache:
    """LRU-less cache for groupby query results keyed by DataScope."""

    def __init__(self):
        self._cache: dict = {}
        self._aug_cache: dict = {}  # augmented 2-col groupby cache
        self.hits = 0
        self.misses = 0

    def get(self, data_scope: DataScope) -> Optional[pd.Series]:
        key = (data_scope.subspace, data_scope.breakdown, data_scope.measure)
        if key in self._cache:
            self.hits += 1
            return self._cache[key]
        self.misses += 1
        return None

    def put(self, data_scope: DataScope, result: pd.Series):
        key = (data_scope.subspace, data_scope.breakdown, data_scope.measure)
        self._cache[key] = result

    def prefetch_subspace_hdp(
        self,
        df: pd.DataFrame,
        hdp_scopes: list,
        ext_dim: str,
    ):
        """
        Augmented-query optimisation (paper Section 4.2.2).

        For a subspace-extending HDP, all members differ only in the value of
        ext_dim. Instead of one filter+groupby per member, we do a single
        two-column groupby over (breakdown, ext_dim) on the base-filtered data,
        then slice per ext_dim value. This gives an N-fold speedup where N is
        the number of HDP members (up to 75 for the district dimension).
        """
        if not hdp_scopes:
            return
        ref_ds   = hdp_scopes[0]
        breakdown = ref_ds.breakdown
        measure   = ref_ds.measure

        # Base subspace: all filters except the varying ext_dim
        base_filters  = frozenset(
            (k, v) for k, v in ref_ds.subspace.filters if k != ext_dim
        )
        base_subspace = Subspace(base_filters)
        aug_key       = (base_subspace, breakdown, ext_dim, measure)

        if aug_key not in self._aug_cache:
            filtered = apply_subspace(df, base_subspace)
            if len(filtered) == 0 or ext_dim not in filtered.columns:
                return
            self._aug_cache[aug_key] = (
                filtered.groupby([breakdown, ext_dim])[measure].sum()
            )

        aug_result = self._aug_cache[aug_key]

        # Slice per member and populate the individual scope cache
        for ds in hdp_scopes:
            scope_key = (ds.subspace, breakdown, measure)
            if scope_key in self._cache:
                continue  # already cached from prior evaluation
            ext_val = next(
                (v for k, v in ds.subspace.filters if k == ext_dim), None
            )
            if ext_val is None:
                continue
            try:
                member_series = aug_result.xs(ext_val, level=ext_dim)
            except KeyError:
                member_series = pd.Series(dtype=float)
            self._cache[scope_key] = member_series
            # Count as a hit since the augmented query did the work
            self.hits += 1

    @property
    def hit_rate(self) -> float:
        total = self.hits + self.misses
        return self.hits / total if total > 0 else 0.0


class PatternCache:
    """Cache for pattern evaluation results keyed by (DataScope, pattern_type)."""

    def __init__(self):
        self._cache: dict = {}
        self.hits = 0
        self.misses = 0

    def get(self, data_scope: DataScope, pattern_type: str) -> Optional[BasicDataPattern]:
        key = (data_scope, pattern_type)
        if key in self._cache:
            self.hits += 1
            return self._cache[key]
        self.misses += 1
        return None

    def put(self, data_scope: DataScope, pattern_type: str, pattern: BasicDataPattern):
        self._cache[(data_scope, pattern_type)] = pattern

    @property
    def hit_rate(self) -> float:
        total = self.hits + self.misses
        return self.hits / total if total > 0 else 0.0


def evaluate_outstanding_1(distribution: pd.Series) -> Optional[Highlight]:
    """
    Outstanding #1: one breakdown value has a significantly higher aggregate
    than all others.

    Criteria:
      1. At least 3 breakdown values with a non-zero total.
      2. Top value's z-score relative to the rest >= 2.0.
      3. Top value is at least 1.5x the second-highest value.

    Returns Highlight((top_label,)) if criteria are met, else None.
    """
    dist = distribution.dropna()
    if len(dist) < 3 or dist.sum() == 0:
        return None

    max_val   = dist.max()
    max_label = dist.idxmax()
    rest      = dist.drop(max_label)

    # Condition 1: z-score of the top value vs the rest
    rest_mean = rest.mean()
    rest_std  = rest.std()
    if rest_std > 0:
        if (max_val - rest_mean) / rest_std < 2.0:
            return None
    else:
        # All others are identical; max must be strictly greater
        if max_val <= rest_mean:
            return None

    # Condition 2: dominance ratio vs second-highest
    second_max = rest.max()
    if second_max > 0 and max_val / second_max < 1.5:
        return None

    return Highlight(values=(max_label,))


# Pattern evaluator registry (Phase 4 adds more types here)
PATTERN_EVALUATORS = {
    "OUTSTANDING_1": evaluate_outstanding_1,
}

# Temporal-only types: only valid when the breakdown is a temporal dimension
TEMPORAL_ONLY_TYPES = {"TREND", "OUTLIER", "SEASONALITY", "CHANGE_POINT", "UNIMODALITY"}


def detect_pattern(
    df: pd.DataFrame,
    data_scope: DataScope,
    pattern_type: str,
    query_cache: QueryCache,
    config: ViewConfig,
) -> BasicDataPattern:
    """
    Detect a specific pattern type in a data scope, using the query cache.
    Returns BasicDataPattern with NO_PATTERN if criteria are not met.
    """
    # Temporal-only patterns require a temporal breakdown
    if pattern_type in TEMPORAL_ONLY_TYPES:
        if data_scope.breakdown not in config.temporal_dimensions:
            return BasicDataPattern(data_scope, "NO_PATTERN", None)

    # Query (cached)
    distribution = query_cache.get(data_scope)
    if distribution is None:
        distribution = query_data_scope(df, data_scope)
        query_cache.put(data_scope, distribution)

    if len(distribution) == 0:
        return BasicDataPattern(data_scope, "NO_PATTERN", None)

    highlight = PATTERN_EVALUATORS[pattern_type](distribution)
    if highlight is not None:
        return BasicDataPattern(data_scope, pattern_type, highlight)

    return BasicDataPattern(data_scope, "NO_PATTERN", None)


# =============================================================================
# MODULE C: HDP CONSTRUCTION & METAINSIGHT IDENTIFICATION
# =============================================================================

def extend_subspace(
    data_scope: DataScope,
    df: pd.DataFrame,
    config: ViewConfig,
) -> list:
    """
    Generate sibling HDP groups by varying a filter dimension.

    Strategy 1 (vary existing filter):
      For each dimension already in the subspace, replace its value with every
      possible value in that dimension's domain. Sibling scopes share the same
      non-varying filters, breakdown, and measure.
      Example: ({specialty:OBG, gender:M}, district, cases)
        -> vary specialty -> ({specialty:OBG,...}, district, cases) x 11 siblings

    Strategy 2 (add a new filter dimension):
      For subspaces below max depth, introduce each unused dimension as a new
      filter, creating siblings for each value.
      Example: ({*}, district, cases)
        -> add specialty -> ({specialty:OBG}, district, cases) x 11 siblings

    Returns list of (strategy, extending_dimension, [DataScope...]).
    """
    results = []
    breakdown = data_scope.breakdown
    measure   = data_scope.measure
    current_filters = dict(data_scope.subspace.filters)

    # Strategy 1: vary each dimension already in the subspace
    for filter_dim in current_filters:
        base_filters = frozenset(
            (k, v) for k, v in current_filters.items() if k != filter_dim
        )
        siblings = [
            DataScope(Subspace(base_filters | frozenset([(filter_dim, val)])), breakdown, measure)
            for val in df[filter_dim].dropna().unique()
        ]
        if len(siblings) >= config.min_hdp_size:
            results.append(("subspace", filter_dim, siblings))

    # Strategy 2: add a new filter dimension (only when below max depth)
    if data_scope.subspace.depth < config.max_subspace_depth:
        excluded = set(current_filters.keys()) | {breakdown}
        for extend_dim in config.dimensions:
            if extend_dim in excluded:
                continue
            siblings = [
                DataScope(
                    Subspace(data_scope.subspace.filters | frozenset([(extend_dim, val)])),
                    breakdown, measure,
                )
                for val in df[extend_dim].dropna().unique()
            ]
            if len(siblings) >= config.min_hdp_size:
                results.append(("subspace", extend_dim, siblings))

    return results


def extend_measure(data_scope: DataScope, config: ViewConfig) -> list:
    """
    Generate a sibling HDP group by varying the measure while keeping
    subspace and breakdown fixed.
    """
    siblings = [
        DataScope(data_scope.subspace, data_scope.breakdown, m)
        for m in config.measures
    ]
    if len(siblings) >= config.min_hdp_size:
        return [("measure", "measure", siblings)]
    return []


def extend_breakdown(data_scope: DataScope, config: ViewConfig) -> list:
    """
    Generate a sibling HDP group by varying the breakdown across all
    temporal dimensions, keeping subspace and measure fixed.
    (With only 3 temporal dimensions this yields size-3 HDPs - small but valid.)
    """
    siblings = [
        DataScope(data_scope.subspace, b, data_scope.measure)
        for b in config.temporal_dimensions
    ]
    if len(siblings) >= config.min_hdp_size:
        return [("breakdown", "temporal_grain", siblings)]
    return []


def _member_label(
    data_scope: DataScope,
    extending_strategy: str,
    extending_dimension: str,
) -> str:
    """Extract the label that identifies this member within its HDP."""
    if extending_strategy == "subspace":
        for dim, val in data_scope.subspace.filters:
            if dim == extending_dimension:
                return str(val)
        return "?"
    elif extending_strategy == "measure":
        return data_scope.measure
    elif extending_strategy == "breakdown":
        return data_scope.breakdown
    return "?"


@dataclass
class MetaInsightCandidate:
    """A candidate MetaInsight with HDP definition, partition results, and scores."""
    extending_strategy: str   # "subspace", "measure", or "breakdown"
    extending_dimension: str  # which dimension was varied to form the HDP
    pattern_type: str
    breakdown: str            # shared breakdown, or "(varies)" for breakdown-extending
    measure: str              # shared measure, or "(varies)" for measure-extending
    base_subspace: Subspace   # the subspace portion NOT varied across the HDP

    commonness_sets: list     # [{highlight, pattern_type, members, count, proportion}]
    exceptions: list          # [{member_label, category, highlight, pattern_type}]
    hdp_size: int

    hdp_member_subspaces: list = field(default_factory=list)  # excluded from JSON

    # Filled by Module D
    conciseness: float = 0.0
    impact: float = 0.0
    score: float = 0.0
    impact_measure_used: str = ""

    def to_dict(self) -> dict:
        return {
            "extending_strategy":  self.extending_strategy,
            "extending_dimension": self.extending_dimension,
            "pattern_type":        self.pattern_type,
            "breakdown":           self.breakdown,
            "measure":             self.measure,
            "base_subspace":       str(self.base_subspace),
            "hdp_size":            self.hdp_size,
            "commonness_sets":     self.commonness_sets,
            "exceptions":          self.exceptions,
            "conciseness":         round(self.conciseness, 6),
            "impact":              round(self.impact, 6),
            "score":               round(self.score, 6),
            "impact_measure_used": self.impact_measure_used,
        }


def evaluate_hdp(
    hdp_scopes: list,
    pattern_type: str,
    extending_strategy: str,
    extending_dimension: str,
    df: pd.DataFrame,
    config: ViewConfig,
    query_cache: QueryCache,
    pattern_cache: PatternCache,
) -> Optional[MetaInsightCandidate]:
    """
    Evaluate all data scopes in an HDP.
    Partitions results into commonness sets and exceptions.
    Returns MetaInsightCandidate if at least one commonness set is found, else None.

    Includes early-termination pruning: if enough members have been evaluated
    that no group can possibly reach the tau threshold with remaining members,
    we abort and return None immediately.
    """
    n       = len(hdp_scopes)
    tau     = config.tau
    patterns = []

    for ds in hdp_scopes:
        cached = pattern_cache.get(ds, pattern_type)
        if cached is not None:
            patterns.append(cached)
        else:
            p = detect_pattern(df, ds, pattern_type, query_cache, config)
            pattern_cache.put(ds, pattern_type, p)
            patterns.append(p)

        # Early termination: check if any group can still reach tau
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

    # Partition by (pattern_type, highlight)
    groups: dict = {}
    no_pattern_list    = []
    other_pattern_list = []

    for p in patterns:
        if p.pattern_type == "NO_PATTERN":
            no_pattern_list.append(p)
        elif p.pattern_type == "OTHER_PATTERN":
            other_pattern_list.append(p)
        else:
            key = (p.pattern_type, p.highlight)
            groups.setdefault(key, []).append(p)

    # Identify commonness sets (proportion > tau)
    commonness_sets   = []
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

    # Categorise exceptions
    exceptions = []
    for ep in exception_patterns:
        label = _member_label(ep.data_scope, extending_strategy, extending_dimension)
        if ep.pattern_type == "NO_PATTERN":
            category = "NO_PATTERN"
        elif ep.pattern_type == "OTHER_PATTERN":
            category = "TYPE_CHANGE"
        else:
            category = "HIGHLIGHT_CHANGE"
        exceptions.append({
            "member_label": label,
            "category":     category,
            "highlight":    str(ep.highlight) if ep.highlight else None,
            "pattern_type": ep.pattern_type,
        })

    # Derive base_subspace: the subspace portion not varied across the HDP
    ref_scope = hdp_scopes[0]
    if extending_strategy == "subspace":
        base_filters = frozenset(
            (k, v) for k, v in ref_scope.subspace.filters
            if k != extending_dimension
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
# MODULE D: SCORER
# =============================================================================

def compute_conciseness(candidate: MetaInsightCandidate, config: ViewConfig) -> float:
    """
    Entropy-based conciseness score (paper equations 13-16).

    S = -(sum(alpha_i * log2(alpha_i)) + r * sum(beta_j * log2(beta_j)))

    Where:
      alpha_i = proportion of each commonness set
      beta_j  = proportion of each exception category
      r       = 1.0  (balance between commonness and exception entropy)
      k       = 3    (exception categories: HIGHLIGHT_CHANGE, TYPE_CHANGE, NO_PATTERN)
      gamma   = 0.1  (actionability penalty when there are no exceptions)

    Conciseness = 1 - (S + gamma * I(no_exceptions)) / S*

    S* (upper bound, Lemma 4.1) for tau=0.5, r=1.0, k=3:
      threshold = (1 - tau) * e / tau^(1/r) = 0.5 * e / 0.5 = e ~ 2.718
      k=3 >= e, so: S* = -tau*log2(tau) - r*(1-tau)*log2((1-tau)/k) ~ 1.792
    """
    n     = candidate.hdp_size
    tau   = config.tau
    r     = 1.0
    k     = 3
    gamma = 0.1

    # Commonness proportions (alpha)
    alphas = [cs["proportion"] for cs in candidate.commonness_sets]

    # Exception category proportions (beta)
    exc_cats: dict = {}
    for exc in candidate.exceptions:
        exc_cats[exc["category"]] = exc_cats.get(exc["category"], 0) + 1
    betas = [count / n for count in exc_cats.values()]

    # Entropy S
    s = 0.0
    for a in alphas:
        if a > 0:
            s -= a * math.log2(a)
    for b in betas:
        if b > 0:
            s -= r * b * math.log2(b)

    # Actionability regularisation: penalise when there are no exceptions
    has_exceptions = len(candidate.exceptions) > 0
    s_reg = s + gamma * (0.0 if has_exceptions else 1.0)

    # S* upper bound
    tau_r     = tau ** (1.0 / r)
    threshold = (1 - tau) * math.e / tau_r

    if k < threshold:
        s_star = (
            -math.log2(tau)
            + r * (k * tau_r / math.e) * math.log2(math.e / (k * tau_r))
        )
    else:
        s_star = (
            -tau * math.log2(tau)
            - r * (1 - tau) * math.log2((1 - tau) / k)
        )

    return max(0.0, 1.0 - s_reg / s_star) if s_star > 0 else 1.0


def compute_impact(
    candidate: MetaInsightCandidate,
    impact_calc: ImpactCalculator,
    config: ViewConfig,
) -> tuple:
    """
    Impact = sum of subspace-level impacts across HDP members (paper eq. 17).
    For measure/breakdown-extending, all members share one subspace.
    Selects the impact measure that yields the highest value.
    Returns (impact_value, impact_measure_name).
    """
    best_impact  = 0.0
    best_measure = config.impact_measures[0]

    for impact_m in config.impact_measures:
        if candidate.extending_strategy == "subspace":
            # Sum across all member subspaces, capped at 1.0
            total = min(
                1.0,
                sum(
                    impact_calc.get(s).get(impact_m, 0.0)
                    for s in candidate.hdp_member_subspaces
                ),
            )
        else:
            total = impact_calc.get(candidate.base_subspace).get(impact_m, 0.0)

        if total > best_impact:
            best_impact  = total
            best_measure = impact_m

    return best_impact, best_measure


def score_candidate(
    candidate: MetaInsightCandidate,
    impact_calc: ImpactCalculator,
    config: ViewConfig,
) -> MetaInsightCandidate:
    """Compute and attach conciseness, impact, and combined score. Returns candidate."""
    candidate.conciseness = compute_conciseness(candidate, config)
    candidate.impact, candidate.impact_measure_used = compute_impact(
        candidate, impact_calc, config
    )
    candidate.score = candidate.conciseness * candidate.impact
    return candidate


# =============================================================================
# MODULE E: ENGINE ORCHESTRATOR & OUTPUT
# =============================================================================

def run_engine(config: ViewConfig, time_budget_seconds: int = 600) -> tuple:
    """
    Main MetaInsight mining loop. Returns (candidates, diagnostics).

    Flow:
      1. Load view parquet
      2. Enumerate subspaces (depth 0-2)
      3. Build impact-ordered priority queue; prune low-impact subspaces
      4. For each subspace (high-impact first):
           a. Generate data scopes (breakdown x measure)
           b. Detect Outstanding #1 pattern on each scope
           c. On pattern hit, extend into HDPs via subspace/measure/breakdown strategies
           d. Evaluate and score each HDP
      5. Sort all candidates by score descending
    """
    print("=" * 70)
    print("PHASE 2: MetaInsight Engine")
    print("=" * 70)
    print(f"Loading {config.parquet_path} ...")
    df = pd.read_parquet(config.parquet_path)
    print(f"  {len(df):,} rows x {len(df.columns)} cols")

    query_cache   = QueryCache()
    pattern_cache = PatternCache()
    impact_calc   = ImpactCalculator(df, config.impact_measures)
    candidates: list = []

    # Step 1: subspace enumeration
    print("\nGenerating subspaces ...")
    subspaces = generate_subspaces(config, df)
    d0 = 1
    d1 = sum(1 for s in subspaces if s.depth == 1)
    d2 = sum(1 for s in subspaces if s.depth == 2)
    print(f"  depth-0: {d0}  depth-1: {d1}  depth-2: {d2}  total: {len(subspaces):,}")

    # Step 2: priority queue
    print("Building priority queue ...")
    queue = build_priority_queue(subspaces, impact_calc, config.min_impact)
    print(f"  {len(queue):,} subspaces retained after impact pruning (min={config.min_impact})")

    # Step 3: mining loop
    pattern_type = "OUTSTANDING_1"
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
            # Check budget inside the inner loop so we don't overshoot on large subspaces
            if (time.time() - start_time) >= time_budget_seconds:
                break
            scopes_evaluated += 1

            pattern = detect_pattern(df, ds, pattern_type, query_cache, config)
            pattern_cache.put(ds, pattern_type, pattern)

            if pattern.pattern_type == pattern_type:
                patterns_found += 1

                # Generate all extending strategies for this data scope
                extensions = []
                extensions.extend(extend_subspace(ds, df, config))
                extensions.extend(extend_measure(ds, config))
                extensions.extend(extend_breakdown(ds, config))

                for ext_strategy, ext_dim, hdp_scopes in extensions:
                    hdps_evaluated += 1
                    # Pre-populate query cache for all HDP members in one shot
                    # (augmented-query optimisation; measure/breakdown HDPs share
                    # one subspace so they're already cached from scope detection)
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

    # Verify S* value for default params (validation checklist item)
    tau, r, k = config.tau, 1.0, 3
    tau_r     = tau ** (1.0 / r)
    threshold = (1 - tau) * math.e / tau_r
    s_star    = (
        -tau * math.log2(tau) - r * (1 - tau) * math.log2((1 - tau) / k)
        if k >= threshold else
        -math.log2(tau) + r * (k * tau_r / math.e) * math.log2(math.e / (k * tau_r))
    )
    print(f"  S* (tau={tau}, r={r}, k={k}): {s_star:.4f}  (expected ~1.792)")

    diagnostics = {
        "elapsed":          elapsed,
        "scopes_evaluated": scopes_evaluated,
        "patterns_found":   patterns_found,
        "hdps_evaluated":   hdps_evaluated,
        "query_cache":      query_cache,
        "pattern_cache":    pattern_cache,
    }
    return candidates, diagnostics


def save_candidates(candidates: list, output_path: str):
    """Serialise all MetaInsight candidates to JSON."""
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump([c.to_dict() for c in candidates], f, indent=2, default=str)
    print(f"Saved {len(candidates):,} candidates -> {output_path}")


def save_diagnostics(candidates: list, diagnostics: dict, output_path: str):
    """Write a human-readable diagnostics report."""
    qc = diagnostics["query_cache"]
    pc = diagnostics["pattern_cache"]

    lines = [
        "=" * 70,
        "METAINSIGHT ENGINE DIAGNOSTICS",
        "=" * 70,
        f"Time elapsed:     {diagnostics['elapsed']:.1f}s",
        f"Scopes evaluated: {diagnostics['scopes_evaluated']:,}",
        f"Patterns found:   {diagnostics['patterns_found']:,}",
        f"HDPs evaluated:   {diagnostics['hdps_evaluated']:,}",
        f"MetaInsights:     {len(candidates):,}",
        f"Query cache:      {qc.hits:,} hits / {qc.misses:,} misses ({qc.hit_rate:.1%})",
        f"Pattern cache:    {pc.hits:,} hits / {pc.misses:,} misses ({pc.hit_rate:.1%})",
        "",
        "--- Score Distribution ---",
    ]

    if candidates:
        lines += [
            f"  Max:    {candidates[0].score:.4f}",
            f"  Median: {candidates[len(candidates) // 2].score:.4f}",
            f"  Min:    {candidates[-1].score:.4f}",
            f"  Total above 0.1: {sum(1 for c in candidates if c.score >= 0.1)}",
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
            members_str = ", ".join(cs["members"][:8])
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
            lines.append("    Exceptions:  none (all commonness)")

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"Diagnostics saved -> {output_path}")


# =============================================================================
# ENTRY POINT
# =============================================================================

if __name__ == "__main__":
    candidates, diagnostics = run_engine(VIEW1_CONFIG, time_budget_seconds=600)

    save_candidates(
        candidates,
        os.path.join(BASE_DIR, "metainsights", "view1_candidates.json"),
    )
    save_diagnostics(
        candidates,
        diagnostics,
        os.path.join(BASE_DIR, "reports", "engine_diagnostics.txt"),
    )
