# Phase 4a: All Pattern Types on View 1

## Overview

This phase adds 10 new pattern type evaluators to the existing Outstanding #1, giving 11 total. The engine runs on View 1 (Claims Lifecycle) with all 11 types enabled. The engine architecture, caching, HDP construction, scoring, and orchestrator from Phase 2 are unchanged — only the pattern evaluator registry and the `detect_pattern` function are modified.

**Inputs:** `views/view1_claims_lifecycle.parquet`  
**Outputs:**
- `metainsights/view1_all_patterns_candidates.json`
- `reports/engine_diagnostics_all_patterns.txt`

**New dependency:** `scipy` (for `scipy.stats` — used by Trend and Seasonality evaluators)

```bash
pip install scipy --break-system-packages
```

---

## Changes to Existing Code

### Updated Pattern Registry

```python
PATTERN_EVALUATORS = {
    "OUTSTANDING_1":    evaluate_outstanding_1,      # Phase 2 (unchanged)
    "OUTSTANDING_LAST": evaluate_outstanding_last,    # new
    "TOP_TWO":          evaluate_top_two,             # new
    "LAST_TWO":         evaluate_last_two,            # new
    "EVENNESS":         evaluate_evenness,            # new
    "ATTRIBUTION":      evaluate_attribution,         # new
    "TREND":            evaluate_trend,               # new
    "OUTLIER":          evaluate_outlier,             # new
    "SEASONALITY":      evaluate_seasonality,         # new
    "CHANGE_POINT":     evaluate_change_point,        # new
    "UNIMODALITY":      evaluate_unimodality,         # new
}

TEMPORAL_ONLY_TYPES = {
    "TREND", "OUTLIER", "SEASONALITY", "CHANGE_POINT", "UNIMODALITY"
}

CATEGORICAL_ONLY_TYPES = {
    "OUTSTANDING_1", "OUTSTANDING_LAST", "TOP_TWO", "LAST_TWO",
    "EVENNESS", "ATTRIBUTION"
}
```

### Updated `detect_pattern` Function

In Phase 2, the engine evaluated a single pattern type per data scope. Now it tries **all eligible types** and returns the first match. This follows the paper's definition: `dp(ds, type)` returns the pattern if `Evaluate(ds, type) = true`, otherwise checks other types.

```python
def detect_pattern(
    df: pd.DataFrame,
    data_scope: DataScope,
    pattern_type: str,
    query_cache: QueryCache,
    config: ViewConfig,
) -> BasicDataPattern:
    """
    Detect a specific pattern type in a data scope.

    If the requested type matches → return it.
    If it doesn't match but another type does → return OTHER_PATTERN.
    If no type matches → return NO_PATTERN.
    """
    is_temporal = data_scope.breakdown in config.temporal_dimensions

    # Check eligibility
    if pattern_type in TEMPORAL_ONLY_TYPES and not is_temporal:
        return BasicDataPattern(data_scope, "NO_PATTERN", None)
    if pattern_type in CATEGORICAL_ONLY_TYPES and is_temporal:
        return BasicDataPattern(data_scope, "NO_PATTERN", None)

    # Query (with cache)
    distribution = query_cache.get(data_scope)
    if distribution is None:
        distribution = query_data_scope(df, data_scope)
        query_cache.put(data_scope, distribution)

    if len(distribution) == 0:
        return BasicDataPattern(data_scope, "NO_PATTERN", None)

    # Try the requested type first
    evaluator = PATTERN_EVALUATORS[pattern_type]
    highlight = evaluator(distribution)
    if highlight is not None:
        return BasicDataPattern(data_scope, pattern_type, highlight)

    # Check if any OTHER eligible type matches
    for other_type, other_eval in PATTERN_EVALUATORS.items():
        if other_type == pattern_type:
            continue
        # Check eligibility for this alternative type
        if other_type in TEMPORAL_ONLY_TYPES and not is_temporal:
            continue
        if other_type in CATEGORICAL_ONLY_TYPES and is_temporal:
            continue

        other_highlight = other_eval(distribution)
        if other_highlight is not None:
            return BasicDataPattern(data_scope, "OTHER_PATTERN", None)

    return BasicDataPattern(data_scope, "NO_PATTERN", None)
```

### Updated Engine Loop

The engine now iterates over all pattern types for each data scope:

```python
# In run_engine, replace the single pattern_type line with:
pattern_types_categorical = [
    pt for pt in PATTERN_EVALUATORS
    if pt not in TEMPORAL_ONLY_TYPES
]
pattern_types_temporal = [
    pt for pt in PATTERN_EVALUATORS
    if pt not in CATEGORICAL_ONLY_TYPES
]

# Inside the data scope loop:
for ds in data_scopes:
    scopes_evaluated += 1

    # Determine which pattern types to try based on breakdown
    is_temporal = ds.breakdown in config.temporal_dimensions
    active_types = pattern_types_temporal if is_temporal else pattern_types_categorical

    for pattern_type in active_types:
        pattern = detect_pattern(df, ds, pattern_type, query_cache, config)
        pattern_cache.put(ds, pattern_type, pattern)

        if pattern.pattern_type == pattern_type:
            patterns_found += 1

            # Extend into HDPs (same as Phase 2)
            extensions = []
            extensions.extend(extend_subspace(ds, df, config))
            extensions.extend(extend_measure(ds, config))
            extensions.extend(extend_breakdown(ds, config))

            for ext_strategy, ext_dim, hdp_scopes in extensions:
                hdps_evaluated += 1
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
```

---

## Pattern Type Evaluators

All evaluators share the same interface:

```python
def evaluate_<type>(distribution: pd.Series) -> Optional[Highlight]:
    """
    Takes a Series indexed by breakdown values with aggregated measure values.
    Returns Highlight if pattern detected, else None.
    """
```

### Existing: Outstanding #1

Unchanged from Phase 2. Detects when one breakdown value has a significantly higher aggregate.

---

### 1. Outstanding #Last

The minimum value is significantly lower than the rest.

```python
def evaluate_outstanding_last(distribution: pd.Series) -> Optional[Highlight]:
    """
    Criteria:
    - At least 3 breakdown values
    - Minimum is below mean - 2*std of the remaining values
    - Minimum is at most 0.67x (1/1.5) the second-lowest value

    Highlight: (breakdown_value_with_lowest_aggregate,)
    """
    if len(distribution) < 3:
        return None

    dist = distribution.dropna()
    if len(dist) < 3 or dist.sum() == 0:
        return None

    min_val = dist.min()
    min_label = dist.idxmin()

    rest = dist.drop(min_label)
    rest_mean = rest.mean()
    rest_std = rest.std()

    if rest_std > 0:
        z_score = (min_val - rest_mean) / rest_std
        if z_score > -2.0:
            return None
    else:
        if min_val >= rest_mean:
            return None

    second_min = rest.min()
    if second_min > 0 and min_val / second_min > 0.67:
        return None

    return Highlight(values=(min_label,))
```

---

### 2. Top-Two

Two breakdown values are significantly higher than the rest.

```python
def evaluate_top_two(distribution: pd.Series) -> Optional[Highlight]:
    """
    Criteria:
    - At least 4 breakdown values
    - Both top-2 values exceed mean + 1.5*std of the rest
    - 2nd highest is at least 1.3x the 3rd highest

    Highlight: (top1_label, top2_label) — sorted alphabetically for consistent hashing.
    """
    if len(distribution) < 4:
        return None

    dist = distribution.dropna()
    if len(dist) < 4 or dist.sum() == 0:
        return None

    sorted_dist = dist.sort_values(ascending=False)
    top1_label = sorted_dist.index[0]
    top2_label = sorted_dist.index[1]
    top1_val = sorted_dist.iloc[0]
    top2_val = sorted_dist.iloc[1]

    rest = dist.drop([top1_label, top2_label])
    rest_mean = rest.mean()
    rest_std = rest.std()

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

    # Sort labels for consistent highlight comparison across HDP members
    labels = tuple(sorted([top1_label, top2_label]))
    return Highlight(values=labels)
```

---

### 3. Last-Two

Two breakdown values are significantly lower than the rest.

```python
def evaluate_last_two(distribution: pd.Series) -> Optional[Highlight]:
    """
    Criteria:
    - At least 4 breakdown values
    - Both bottom-2 values are below mean - 1.5*std of the rest
    - 2nd lowest is at most 0.77x (1/1.3) the 3rd lowest

    Highlight: (bot1_label, bot2_label) — sorted alphabetically.
    """
    if len(distribution) < 4:
        return None

    dist = distribution.dropna()
    if len(dist) < 4 or dist.sum() == 0:
        return None

    sorted_dist = dist.sort_values(ascending=True)
    bot1_label = sorted_dist.index[0]
    bot2_label = sorted_dist.index[1]
    bot1_val = sorted_dist.iloc[0]
    bot2_val = sorted_dist.iloc[1]

    rest = dist.drop([bot1_label, bot2_label])
    rest_mean = rest.mean()
    rest_std = rest.std()

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

    labels = tuple(sorted([bot1_label, bot2_label]))
    return Highlight(values=labels)
```

---

### 4. Evenness

All breakdown values are distributed approximately evenly.

```python
def evaluate_evenness(distribution: pd.Series) -> Optional[Highlight]:
    """
    Criteria:
    - At least 3 breakdown values
    - Coefficient of variation (std/mean) < 0.15
    - No single value dominates (max/sum < 2/n where n = number of values)

    Highlight: ("EVEN",) — constant, since the pattern is the absence of variation.
    """
    if len(distribution) < 3:
        return None

    dist = distribution.dropna()
    if len(dist) < 3:
        return None

    mean = dist.mean()
    if mean == 0:
        return None

    cv = dist.std() / mean
    if cv >= 0.15:
        return None

    n = len(dist)
    max_share = dist.max() / dist.sum()
    if max_share > 2.0 / n:
        return None

    return Highlight(values=("EVEN",))
```

---

### 5. Attribution

One breakdown value dominates the aggregate (accounts for the majority).

```python
def evaluate_attribution(distribution: pd.Series) -> Optional[Highlight]:
    """
    Criteria:
    - At least 3 breakdown values
    - Top value accounts for > 50% of total
    - Top value is at least 2x the second highest

    Highlight: (dominant_breakdown_value,)
    """
    if len(distribution) < 3:
        return None

    dist = distribution.dropna()
    if len(dist) < 3 or dist.sum() == 0:
        return None

    total = dist.sum()
    max_val = dist.max()
    max_label = dist.idxmax()

    # Must account for > 50% of total
    if max_val / total <= 0.5:
        return None

    # Must be at least 2x the second highest
    rest = dist.drop(max_label)
    second_max = rest.max()
    if second_max > 0 and max_val / second_max < 2.0:
        return None

    return Highlight(values=(max_label,))
```

---

### 6. Trend

Upward or downward trend in a time series.

```python
from scipy import stats

def evaluate_trend(distribution: pd.Series) -> Optional[Highlight]:
    """
    Criteria:
    - At least 4 time points
    - Mann-Kendall test p-value < 0.05 (significant monotonic trend)
    - Alternatively: Spearman correlation |r| > 0.5 with p < 0.05
    - Direction: "INCREASING" or "DECREASING"

    Highlight: ("INCREASING",) or ("DECREASING",)

    Note: The distribution index should be sorted temporally (which it is,
    since query_data_scope returns sort_index()).
    """
    if len(distribution) < 4:
        return None

    dist = distribution.dropna()
    if len(dist) < 4:
        return None

    values = dist.values.astype(float)

    # Use Spearman rank correlation as trend test
    # (simpler than full Mann-Kendall, captures monotonic trends)
    x = np.arange(len(values))
    rho, p_value = stats.spearmanr(x, values)

    if p_value >= 0.05:
        return None

    if abs(rho) < 0.5:
        return None

    direction = "INCREASING" if rho > 0 else "DECREASING"
    return Highlight(values=(direction,))
```

---

### 7. Outlier

One or more time points are statistical outliers.

```python
def evaluate_outlier(distribution: pd.Series) -> Optional[Highlight]:
    """
    Criteria:
    - At least 5 time points (need enough for baseline)
    - Outliers detected by 3-sigma rule: |value - mean| > 3 * std
    - At most 20% of points can be outliers (otherwise it's not an outlier pattern)

    Highlight: tuple of (position, direction) pairs.
    E.g., (("2024-07", "ABOVE"), ("2023-01", "BELOW"))
    Positions sorted chronologically.
    """
    if len(distribution) < 5:
        return None

    dist = distribution.dropna()
    if len(dist) < 5:
        return None

    mean = dist.mean()
    std = dist.std()

    if std == 0:
        return None

    outliers = []
    for label, value in dist.items():
        z = (value - mean) / std
        if abs(z) > 3.0:
            direction = "ABOVE" if z > 0 else "BELOW"
            outliers.append((str(label), direction))

    if len(outliers) == 0:
        return None

    # Too many outliers → not really an outlier pattern
    if len(outliers) > 0.2 * len(dist):
        return None

    return Highlight(values=tuple(outliers))
```

---

### 8. Seasonality

Repeating pattern in the time series.

```python
def evaluate_seasonality(distribution: pd.Series) -> Optional[Highlight]:
    """
    Criteria:
    - At least 12 time points (need enough for at least one full cycle)
    - Autocorrelation at lag L is significant (> 0.4)
    - Check lags 3, 4, 6, 12 (quarterly, tri-annual, semi-annual, annual patterns)

    Highlight: ("PERIOD_<lag>",) e.g., ("PERIOD_12",) for annual seasonality.
    Returns the strongest seasonal period found.
    """
    if len(distribution) < 12:
        return None

    dist = distribution.dropna()
    if len(dist) < 12:
        return None

    values = dist.values.astype(float)
    n = len(values)

    # Normalise
    mean = values.mean()
    std = values.std()
    if std == 0:
        return None
    normed = (values - mean) / std

    best_lag = None
    best_acf = 0.0

    for lag in [3, 4, 6, 12]:
        if lag >= n // 2:
            continue

        # Compute autocorrelation at this lag
        acf = np.corrcoef(normed[:n - lag], normed[lag:])[0, 1]

        if np.isnan(acf):
            continue

        if acf > 0.4 and acf > best_acf:
            best_acf = acf
            best_lag = lag

    if best_lag is None:
        return None

    return Highlight(values=(f"PERIOD_{best_lag}",))
```

---

### 9. Change Point

A significant shift in the mean value at some point in the time series.

```python
def evaluate_change_point(distribution: pd.Series) -> Optional[Highlight]:
    """
    Criteria:
    - At least 6 time points
    - Split the series at each point; compare mean of left vs right
    - Use a t-test; the split with the lowest p-value (if p < 0.01) is the change point
    - Both sides must have at least 3 points

    Highlight: (change_point_label,) — the time point where the change occurs.
    """
    if len(distribution) < 6:
        return None

    dist = distribution.dropna()
    if len(dist) < 6:
        return None

    values = dist.values.astype(float)
    labels = dist.index.tolist()

    best_p = 1.0
    best_idx = None

    # Try each split point (ensure at least 3 on each side)
    for split in range(3, len(values) - 2):
        left = values[:split]
        right = values[split:]

        t_stat, p_value = stats.ttest_ind(left, right, equal_var=False)

        if p_value < best_p:
            best_p = p_value
            best_idx = split

    if best_p >= 0.01:
        return None

    if best_idx is None:
        return None

    change_label = str(labels[best_idx])
    return Highlight(values=(change_label,))
```

---

### 10. Unimodality

The time series forms a U-shaped valley or an inverted-U peak.

```python
def evaluate_unimodality(distribution: pd.Series) -> Optional[Highlight]:
    """
    Criteria:
    - At least 5 time points
    - Identify the global extremum (max or min)
    - Check that values monotonically increase toward the extremum from the left
      AND monotonically decrease from the extremum to the right (for a peak),
      or vice versa for a valley
    - Allow some tolerance: at least 70% of left-side steps are in the correct
      direction AND at least 70% of right-side steps are correct

    Highlight: ("PEAK", extremum_label) or ("VALLEY", extremum_label)
    """
    if len(distribution) < 5:
        return None

    dist = distribution.dropna()
    if len(dist) < 5:
        return None

    values = dist.values.astype(float)
    labels = dist.index.tolist()
    n = len(values)

    # Check for peak (max in the interior)
    max_idx = np.argmax(values)
    min_idx = np.argmin(values)

    best_shape = None
    best_label = None
    best_score = 0.0

    # Try peak
    if 1 <= max_idx <= n - 2:  # extremum not at edges
        left = values[:max_idx]
        right = values[max_idx:]

        # Count increasing steps on left
        left_diffs = np.diff(left)
        left_correct = np.sum(left_diffs > 0) / len(left_diffs) if len(left_diffs) > 0 else 0

        # Count decreasing steps on right
        right_diffs = np.diff(right)
        right_correct = np.sum(right_diffs < 0) / len(right_diffs) if len(right_diffs) > 0 else 0

        score = (left_correct + right_correct) / 2
        if left_correct >= 0.7 and right_correct >= 0.7 and score > best_score:
            best_shape = "PEAK"
            best_label = str(labels[max_idx])
            best_score = score

    # Try valley
    if 1 <= min_idx <= n - 2:
        left = values[:min_idx]
        right = values[min_idx:]

        left_diffs = np.diff(left)
        left_correct = np.sum(left_diffs < 0) / len(left_diffs) if len(left_diffs) > 0 else 0

        right_diffs = np.diff(right)
        right_correct = np.sum(right_diffs > 0) / len(right_diffs) if len(right_diffs) > 0 else 0

        score = (left_correct + right_correct) / 2
        if left_correct >= 0.7 and right_correct >= 0.7 and score > best_score:
            best_shape = "VALLEY"
            best_label = str(labels[min_idx])
            best_score = score

    if best_shape is None:
        return None

    return Highlight(values=(best_shape, best_label))
```

---

## Pattern Eligibility Summary

| Pattern Type | Categorical Breakdown | Temporal Breakdown | Min Breakdown Values |
|---|---|---|---|
| OUTSTANDING_1 | Yes | No | 3 |
| OUTSTANDING_LAST | Yes | No | 3 |
| TOP_TWO | Yes | No | 4 |
| LAST_TWO | Yes | No | 4 |
| EVENNESS | Yes | No | 3 |
| ATTRIBUTION | Yes | No | 3 |
| TREND | No | Yes | 4 |
| OUTLIER | No | Yes | 5 |
| SEASONALITY | No | Yes | 12 |
| CHANGE_POINT | No | Yes | 6 |
| UNIMODALITY | No | Yes | 5 |

For View 1's temporal dimensions:
- `admission_month` (~36 values): all temporal types eligible
- `admission_quarter` (~13 values): all temporal types eligible
- `admission_year` (~4 values): only TREND eligible (others need ≥5 or ≥6)

---

## Running Phase 4a

```python
if __name__ == "__main__":
    import os

    os.makedirs("metainsights", exist_ok=True)
    os.makedirs("reports", exist_ok=True)

    # Run with all pattern types on View 1
    # Increase time budget — more pattern types means more work per scope
    candidates, diagnostics = run_engine(VIEW1_CONFIG, time_budget_seconds=900)

    save_candidates(candidates, "metainsights/view1_all_patterns_candidates.json")
    save_diagnostics(candidates, diagnostics, "reports/engine_diagnostics_all_patterns.txt")
```

**Time budget:** Increased to 900 seconds (15 minutes). Each data scope now evaluates up to 6 pattern types (categorical) or 5 types (temporal) instead of 1. The pattern cache mitigates some of this, but the search space per scope is ~5-6x larger.

---

## Validation Checklist

After running:

- [ ] Engine completes within 15 minutes
- [ ] Significantly more candidates than Phase 2 (expect 30,000-100,000+)
- [ ] Multiple pattern types appear in the top 20 candidates (not just OUTSTANDING_1)
- [ ] Temporal pattern types appear (TREND, UNIMODALITY, CHANGE_POINT at minimum)
- [ ] SEASONALITY may or may not appear — depends on whether the synthetic data has seasonal patterns in monthly breakdowns
- [ ] OUTLIER may be rare — 3-sigma is a strict threshold
- [ ] EVENNESS candidates should exist (some measures are uniformly distributed across certain dimensions)
- [ ] ATTRIBUTION candidates should exist (e.g., NORMAL dominates discharge_type)
- [ ] S_star still ≈ 1.792 (scoring unchanged)
- [ ] No pattern type produces highlights with `None` values (would indicate evaluator bug)
- [ ] Spot-check: verify 1-2 candidates of each new type against raw data

### Diagnostics to include

In addition to the standard diagnostics, add a **pattern type breakdown**:

```python
# Add to diagnostics output:
type_counts = {}
for c in candidates:
    pt = c.pattern_type
    type_counts[pt] = type_counts.get(pt, 0) + 1

lines.append("\n--- Candidates by Pattern Type ---")
for pt, count in sorted(type_counts.items(), key=lambda x: -x[1]):
    lines.append(f"  {pt}: {count:,}")
```

### What to bring back

1. `metainsights/view1_all_patterns_candidates.json` (top 30)
2. `reports/engine_diagnostics_all_patterns.txt`
3. The pattern type breakdown (how many candidates per type)
4. Any pattern types that produced zero candidates
5. Any errors

---

## Notes

1. **The `detect_pattern` OTHER_PATTERN check loops through all types.** This is intentional — it determines whether a data scope has *any* pattern (just not the one requested). In an HDP, a member tagged OTHER_PATTERN becomes a TYPE_CHANGE exception, which is more informative than NO_PATTERN. However, this loop is potentially expensive. If performance is an issue, it can be gated behind a flag or skipped for now (just return NO_PATTERN instead of checking others).

2. **Highlight consistency for similarity.** For Top-Two and Last-Two, labels are alphabetically sorted in the highlight tuple. This ensures that if two HDP members both identify (GS, OBG) as the top two, the highlights match regardless of which was first vs second. Without sorting, (GS, OBG) ≠ (OBG, GS) and the similarity check would fail.

3. **Outlier highlights include position AND direction.** Two outlier patterns are similar only if they have outliers at the same positions with the same directions. This is strict — an HDP member with an above-outlier in July and another with a below-outlier in July are NOT similar. This is correct per the paper's definition (same type AND same highlight).

4. **Seasonality checks fixed lags (3, 4, 6, 12).** These correspond to quarterly, tri-annual, semi-annual, and annual cycles for monthly data. For quarterly breakdown data, only lag 4 (annual) would be meaningful — but quarterly breakdown has only 13 points, and lag 4 requires at least 12, so it barely qualifies. The evaluator handles this via the `lag >= n // 2` guard.

5. **Unimodality uses a 70% tolerance.** Real data rarely has perfect monotonic slopes. The 70% threshold allows some noise while still requiring a clear peak or valley shape. If this produces too many false positives, increase to 80%.

6. **Change Point uses Welch's t-test** (`equal_var=False`) which is more robust when the two segments have different variances — common in real-world time series where a regime change affects volatility as well as mean.
