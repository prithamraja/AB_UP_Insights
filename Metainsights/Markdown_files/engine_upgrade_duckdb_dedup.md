# Engine Upgrade: DuckDB Query Layer + HDP Deduplication

## Overview

Two targeted changes to the existing Phase 4a engine. No changes to pattern evaluators, HDP construction logic, scoring, or output format. The engine produces identical analytical results — just faster and without duplicate candidates.

**Change 1:** Replace pandas query layer with DuckDB  
**Change 2:** Add HDP deduplication set to skip redundant evaluations

**New dependency:**
```bash
pip install duckdb --break-system-packages
```

---

## Change 1: DuckDB Query Layer

### What Changes

Three components currently use pandas for filtering and aggregation:
1. `query_data_scope` — filters by subspace, groups by breakdown, sums measure
2. `ImpactCalculator.get` — filters by subspace, sums each impact measure
3. `apply_subspace` — utility used by the above two

All three are replaced with DuckDB SQL queries against an in-memory DuckDB table.

### Implementation

#### 1.1 Engine Initialisation

Replace the DataFrame load with a DuckDB connection:

```python
import duckdb

def run_engine(config: ViewConfig, time_budget_seconds: int = 900):
    print(f"Loading {config.parquet_path} into DuckDB...")
    
    # Load parquet into DuckDB in-memory table
    con = duckdb.connect()
    con.execute(f"""
        CREATE TABLE view_data AS 
        SELECT * FROM read_parquet('{config.parquet_path}')
    """)
    
    row_count = con.execute("SELECT COUNT(*) FROM view_data").fetchone()[0]
    col_count = len(con.execute("SELECT * FROM view_data LIMIT 0").description)
    print(f"  {row_count:,} rows, {col_count} cols")
    
    # Also keep a pandas DataFrame for subspace generation
    # (we need unique values per dimension — cheap on small data)
    df = con.execute("SELECT * FROM view_data").fetchdf()
    
    # Initialise caches and calculator with DuckDB connection
    query_cache = QueryCache()
    pattern_cache = PatternCache()
    impact_calc = ImpactCalculator(con, config.impact_measures)
    
    # ... rest of engine unchanged, but pass `con` instead of `df` 
    # to query_data_scope and detect_pattern
```

**Note:** We keep a pandas DataFrame (`df`) for `generate_subspaces` which needs `df[dim].dropna().unique()` to enumerate dimension values. This is a one-time operation on load and doesn't need DuckDB. For 500M rows, this could be replaced with `SELECT DISTINCT dim FROM view_data`, but for our current data sizes it's fine either way.

#### 1.2 Replace `query_data_scope`

```python
def query_data_scope(con: duckdb.DuckDBPyConnection, data_scope: DataScope) -> pd.Series:
    """
    Execute: SELECT breakdown, SUM(measure) FROM view_data
             WHERE subspace_filters GROUP BY breakdown ORDER BY breakdown
    
    Returns a pandas Series indexed by breakdown values.
    """
    # Build WHERE clause
    conditions = []
    for dim, val in data_scope.subspace.filters:
        # Escape single quotes in values
        escaped_val = str(val).replace("'", "''")
        conditions.append(f"\"{dim}\" = '{escaped_val}'")
    
    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    
    sql = f"""
        SELECT "{data_scope.breakdown}" AS breakdown_val, 
               SUM("{data_scope.measure}") AS agg_val
        FROM view_data
        {where_clause}
        GROUP BY "{data_scope.breakdown}"
        ORDER BY "{data_scope.breakdown}"
    """
    
    result = con.execute(sql).fetchdf()
    
    if len(result) == 0:
        return pd.Series(dtype=float)
    
    return result.set_index("breakdown_val")["agg_val"]
```

**Key details:**
- Column names are quoted with double quotes (`"district"`) to handle any special characters or reserved words
- Values are escaped for SQL injection safety (single quotes)
- Returns the same pandas Series interface that all pattern evaluators expect
- DuckDB automatically parallelises the query across available cores

#### 1.3 Replace `ImpactCalculator`

```python
class ImpactCalculator:
    """Lazily computes and caches subspace impacts using DuckDB."""
    
    def __init__(self, con: duckdb.DuckDBPyConnection, impact_measures: list[str]):
        self._con = con
        self._impact_measures = impact_measures
        self._cache: dict[Subspace, dict[str, float]] = {}
        
        # Pre-compute totals (one query, done once)
        sum_exprs = ", ".join(f'SUM("{m}") AS "{m}"' for m in impact_measures)
        totals_row = con.execute(f"SELECT {sum_exprs} FROM view_data").fetchone()
        self._totals = {
            m: totals_row[i] if totals_row[i] is not None else 0.0
            for i, m in enumerate(impact_measures)
        }
    
    def get(self, subspace: Subspace) -> dict[str, float]:
        if subspace in self._cache:
            return self._cache[subspace]
        
        # Build WHERE clause
        conditions = []
        for dim, val in subspace.filters:
            escaped_val = str(val).replace("'", "''")
            conditions.append(f"\"{dim}\" = '{escaped_val}'")
        
        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        
        sum_exprs = ", ".join(f'SUM("{m}") AS "{m}"' for m in self._impact_measures)
        row = self._con.execute(
            f"SELECT {sum_exprs} FROM view_data {where_clause}"
        ).fetchone()
        
        impacts = {}
        for i, m in enumerate(self._impact_measures):
            total = self._totals[m]
            val = row[i] if row[i] is not None else 0.0
            impacts[m] = val / total if total > 0 else 0.0
        
        self._cache[subspace] = impacts
        return impacts
    
    def max_impact(self, subspace: Subspace) -> float:
        return max(self.get(subspace).values())
```

#### 1.4 Update `detect_pattern` Signature

```python
def detect_pattern(
    con: duckdb.DuckDBPyConnection,   # was: df: pd.DataFrame
    data_scope: DataScope,
    pattern_type: str,
    query_cache: QueryCache,
    config: ViewConfig,
) -> BasicDataPattern:
    """Unchanged logic, just passes `con` to query_data_scope."""
    
    # ... eligibility checks unchanged ...
    
    # Query (with cache)
    distribution = query_cache.get(data_scope)
    if distribution is None:
        distribution = query_data_scope(con, data_scope)  # was: (df, data_scope)
        query_cache.put(data_scope, distribution)
    
    # ... rest unchanged ...
```

#### 1.5 Update `evaluate_hdp` Signature

```python
def evaluate_hdp(
    hdp_scopes: list[DataScope],
    pattern_type: str,
    extending_strategy: str,
    extending_dimension: str,
    con: duckdb.DuckDBPyConnection,   # was: df: pd.DataFrame
    config: ViewConfig,
    query_cache: QueryCache,
    pattern_cache: PatternCache,
) -> Optional[MetaInsightCandidate]:
    """Unchanged logic, just passes `con` to detect_pattern."""
    # ... all internal logic unchanged ...
    # detect_pattern calls now pass `con` instead of `df`
```

#### 1.6 Remove `apply_subspace`

The `apply_subspace` function is no longer needed. It was only used by `query_data_scope` and `ImpactCalculator`, both of which now use DuckDB SQL directly. Delete it.

**Exception:** If `generate_subspaces` or `extend_subspace` use `apply_subspace` to check for empty results (some subspaces may filter to zero rows), keep it or replace those checks with a DuckDB count query. However, looking at the Phase 2 code, `generate_subspaces` only uses `df[dim].dropna().unique()` which doesn't need `apply_subspace`, and `extend_subspace` uses `df[extend_dim].dropna().unique()` which also doesn't. So `apply_subspace` can be fully removed.

#### 1.7 Keep the Query Cache

The query cache still provides value even with DuckDB. A cached pandas Series lookup is ~0 cost vs ~5-50ms for a DuckDB query. Over millions of lookups, this adds up. Keep the `QueryCache` class unchanged — it sits between the engine and `query_data_scope`, same as before.

---

## Change 2: HDP Deduplication

### What Changes

Before calling `evaluate_hdp`, check whether this exact HDP (same member subspaces, same pattern type) has already been evaluated. If so, skip it.

### Implementation

#### 2.1 Add `evaluated_hdps` Set

In `run_engine`, initialise a set alongside the existing caches:

```python
    # Initialise
    query_cache = QueryCache()
    pattern_cache = PatternCache()
    impact_calc = ImpactCalculator(con, config.impact_measures)
    candidates: list[MetaInsightCandidate] = []
    evaluated_hdps: set = set()     # NEW
    hdps_skipped = 0                # NEW — for diagnostics
```

#### 2.2 Check Before `evaluate_hdp`

In the engine loop, add the dedup check:

```python
    for ext_strategy, ext_dim, hdp_scopes in extensions:
        # --- HDP dedup check ---
        hdp_key = (
            frozenset(ds.subspace for ds in hdp_scopes),
            pattern_type,
            hdp_scopes[0].breakdown if ext_strategy != "breakdown" else "(varies)",
            hdp_scopes[0].measure if ext_strategy != "measure" else "(varies)",
        )
        if hdp_key in evaluated_hdps:
            hdps_skipped += 1
            continue
        evaluated_hdps.add(hdp_key)
        # --- end dedup check ---
        
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
```

**Why the key includes breakdown and measure:** Two HDPs with the same member subspaces but different breakdowns or measures are genuinely different HDPs (they analyse different data). The key must distinguish them. For subspace-extending HDPs, breakdown and measure are shared across members. For measure-extending, the measure varies (so we use a placeholder). For breakdown-extending, the breakdown varies.

#### 2.3 Update Diagnostics

Add the dedup stats to the engine output:

```python
    # In the print summary at the end of run_engine:
    print(f"  HDPs skipped (dedup):   {hdps_skipped:,}")
    print(f"  HDP dedup hit rate:     {hdps_skipped / (hdps_evaluated + hdps_skipped):.1%}"
          if (hdps_evaluated + hdps_skipped) > 0 else "")
    
    # In the diagnostics dict:
    diagnostics = {
        "elapsed": elapsed,
        "scopes_evaluated": scopes_evaluated,
        "patterns_found": patterns_found,
        "hdps_evaluated": hdps_evaluated,
        "hdps_skipped": hdps_skipped,
        "query_cache": query_cache,
        "pattern_cache": pattern_cache,
    }
```

Also update `save_diagnostics` to include:

```python
    lines.append(f"HDPs skipped (dedup): {diagnostics['hdps_skipped']:,}")
    total_hdps = diagnostics['hdps_evaluated'] + diagnostics['hdps_skipped']
    if total_hdps > 0:
        lines.append(f"HDP dedup hit rate: "
                     f"{diagnostics['hdps_skipped'] / total_hdps:.1%}")
```

---

## What NOT to Change

Everything else stays the same:

- `ViewConfig` — unchanged
- `VIEW1_CONFIG` — unchanged
- All 11 pattern evaluators — unchanged
- `Subspace`, `DataScope`, `Highlight`, `BasicDataPattern` — unchanged
- `MetaInsightCandidate` — unchanged
- `QueryCache`, `PatternCache` — unchanged
- `generate_subspaces`, `generate_data_scopes` — unchanged
- `extend_subspace`, `extend_measure`, `extend_breakdown` — unchanged  
  (these use `df[dim].dropna().unique()` — keep using the pandas DataFrame loaded at init for this)
- `evaluate_hdp` internal logic — unchanged (just receives `con` instead of `df`)
- All scoring functions — unchanged
- Priority queue — unchanged
- `save_candidates`, `save_diagnostics` — minor additions for dedup stats only

---

## Running the Updated Engine

```python
if __name__ == "__main__":
    import os

    os.makedirs("metainsights", exist_ok=True)
    os.makedirs("reports", exist_ok=True)

    candidates, diagnostics = run_engine(VIEW1_CONFIG, time_budget_seconds=900)

    save_candidates(candidates, "metainsights/view1_duckdb_candidates.json")
    save_diagnostics(candidates, diagnostics, "reports/engine_diagnostics_duckdb.txt")
```

---

## Validation Checklist

Run on View 1 with the same 900-second budget and compare against Phase 4a results:

- [ ] **Candidate quality preserved:** Top candidates should have the same pattern types, highlights, commonness/exception structure as Phase 4a. Scores should be identical (same scoring logic, same data).
- [ ] **Candidate count decreased:** Fewer candidates than Phase 4a's 16,175 (duplicates removed). Expect 4,000-7,000 unique candidates.
- [ ] **No new pattern types or missing types:** Same 10 active types + CHANGE_POINT still zero.
- [ ] **HDP dedup hit rate > 50%:** Confirms significant duplicate elimination. Expect 60-70%.
- [ ] **More scopes evaluated:** With dedup freeing up time budget, the engine should explore more subspaces. Expect scopes_evaluated > 4,356 (Phase 4a's count).
- [ ] **DuckDB query performance:** Query cache hit rate may be lower (engine explores more territory) but each miss is faster. Total elapsed should be ≤ 900s.
- [ ] **Zero analytical differences:** Pick 5 candidates from Phase 4a's top-30. Verify they appear in the new results with identical scores, commonness sets, and exceptions.

### What to bring back

1. `reports/engine_diagnostics_duckdb.txt`
2. Comparison: scopes_evaluated, candidates count, HDP dedup hit rate
3. Confirmation that top candidates match Phase 4a
4. Any errors
