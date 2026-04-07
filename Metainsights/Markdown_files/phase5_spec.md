# Phase 5: Intra-View Ranking & Presentation (Layers 3 + 3P)

## Overview

This phase takes the raw MetaInsight candidates from each view (Phase 4b output) and produces a ranked, deduplicated top-k list per view. It implements the paper's ranking algorithm (Section 4.3): greedy second-order approximation of TotalUse maximisation, which selects candidates with high individual scores and low inter-MetaInsight redundancy.

This phase also adds the presentation layers:
- **Layer 2P:** Raw MetaInsight explorer (diagnostic view of all candidates)
- **Layer 3P:** Ranked per-view dashboard (curated output per view)

**Inputs:**
- `metainsights/view1_candidates.json`
- `metainsights/view2_candidates.json`
- `metainsights/view3_candidates.json`
- `metainsights/view4_candidates.json`

**Outputs:**
- `metainsights/view1_ranked.json` (top-k per view)
- `metainsights/view2_ranked.json`
- `metainsights/view3_ranked.json`
- `metainsights/view4_ranked.json`
- `reports/layer2p_raw_explorer.txt` (Layer 2P)
- `reports/layer3p_ranked_dashboard.txt` (Layer 3P)

**No new dependencies.**

---

## Part 1: Serialisation Update

Before ranking can work across a save/load boundary, `MetaInsightCandidate.to_dict()` must serialise `base_subspace` as structured data (not a string). Update in the engine code:

```python
# In MetaInsightCandidate.to_dict():
def to_dict(self) -> dict:
    return {
        "extending_strategy": self.extending_strategy,
        "extending_dimension": self.extending_dimension,
        "pattern_type": self.pattern_type,
        "breakdown": self.breakdown,
        "measure": self.measure,
        "base_subspace": list(self.base_subspace.filters),  # list of [dim, val] pairs
        "hdp_size": self.hdp_size,
        "commonness_sets": self.commonness_sets,
        "exceptions": self.exceptions,
        "conciseness": self.conciseness,
        "impact": self.impact,
        "score": self.score,
        "impact_measure_used": self.impact_measure_used,
    }
```

And the loader:

```python
def load_candidates(path: str) -> list[MetaInsightCandidate]:
    """Load candidates from JSON and reconstruct MetaInsightCandidate objects."""
    with open(path) as f:
        data = json.load(f)
    
    candidates = []
    for d in data:
        base_subspace = Subspace(frozenset(tuple(f) for f in d["base_subspace"]))
        
        c = MetaInsightCandidate(
            extending_strategy=d["extending_strategy"],
            extending_dimension=d["extending_dimension"],
            pattern_type=d["pattern_type"],
            breakdown=d["breakdown"],
            measure=d["measure"],
            base_subspace=base_subspace,
            commonness_sets=d["commonness_sets"],
            exceptions=d["exceptions"],
            hdp_size=d["hdp_size"],
            conciseness=d["conciseness"],
            impact=d["impact"],
            score=d["score"],
            impact_measure_used=d["impact_measure_used"],
        )
        candidates.append(c)
    
    return candidates
```

**Important:** After updating `to_dict()`, re-run Phase 4b (or at least re-save the candidates) so the JSON files contain the structured `base_subspace` format. The ranking code depends on being able to reconstruct `Subspace` objects from the JSON.

---

## Part 2: Inter-MetaInsight Overlap (Paper Section 4.3 + Appendix 9.4)

### 2.1 Overlap Ratio

```python
def compute_overlap_ratio(mi1: MetaInsightCandidate, mi2: MetaInsightCandidate) -> float:
    """
    Compute overlap ratio between two MetaInsight candidates.
    Returns [0, 1] where 0 = no overlap, 1 = fully redundant.
    
    Two MetaInsights can only overlap if they share the same extending strategy
    and pattern type. Otherwise overlap = 0.
    """
    if mi1.extending_strategy != mi2.extending_strategy:
        return 0.0
    
    if mi1.pattern_type != mi2.pattern_type:
        return 0.0
    
    strategy = mi1.extending_strategy
    
    if strategy == "subspace":
        return _subspace_overlap(mi1, mi2)
    elif strategy == "measure":
        return _measure_overlap(mi1, mi2)
    elif strategy == "breakdown":
        return _breakdown_overlap(mi1, mi2)
    
    return 0.0


def _subspace_overlap_coefficient(mi1: MetaInsightCandidate, mi2: MetaInsightCandidate) -> float:
    """Compute overlap coefficient of base subspace filters."""
    filters1 = set(mi1.base_subspace.filters)
    filters2 = set(mi2.base_subspace.filters)
    
    if len(filters1) == 0 and len(filters2) == 0:
        return 1.0  # both are {*}
    if len(filters1) == 0 or len(filters2) == 0:
        return 0.0  # one is {*}, other has filters
    
    intersection = len(filters1 & filters2)
    min_size = min(len(filters1), len(filters2))
    return intersection / min_size


def _subspace_overlap(mi1: MetaInsightCandidate, mi2: MetaInsightCandidate) -> float:
    """
    Overlap for subspace-extending MetaInsights.
    Weighted components: subspace similarity, same extending dim, same measure, same breakdown.
    """
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
```

### 2.2 Pairwise Overlap (Paper Equation 20)

```python
def compute_pairwise_overlap(mi1: MetaInsightCandidate, mi2: MetaInsightCandidate) -> float:
    """
    |I1 ∩ I2| = min(|I1|, |I2|) × r(I1, I2)
    Where |I| = score, r = overlap ratio.
    """
    r = compute_overlap_ratio(mi1, mi2)
    return min(mi1.score, mi2.score) * r
```

---

## Part 3: Greedy Ranking Algorithm (Paper Section 4.3)

### 3.1 TotalUse Approximation (Paper Equation 22)

```python
def compute_total_use_approx(selected: list[MetaInsightCandidate]) -> float:
    """
    TotalUse_approx = sum(|Ii|) - sum(|Ii ∩ Ij|) for all pairs i < j
    """
    total = sum(mi.score for mi in selected)
    for i in range(len(selected)):
        for j in range(i + 1, len(selected)):
            total -= compute_pairwise_overlap(selected[i], selected[j])
    return total
```

### 3.2 Greedy Selection

```python
def rank_metainsights(
    candidates: list[MetaInsightCandidate],
    k: int = 15,
) -> list[MetaInsightCandidate]:
    """
    Greedy algorithm to select top-k MetaInsights maximising TotalUse_approx.
    
    1. Start with the highest-scoring candidate
    2. At each step, add the candidate that increases TotalUse the most
    3. Stop when k candidates selected or no candidate increases TotalUse
    """
    if not candidates:
        return []
    
    sorted_candidates = sorted(candidates, key=lambda c: c.score, reverse=True)
    
    selected: list[MetaInsightCandidate] = [sorted_candidates[0]]
    remaining = set(range(1, len(sorted_candidates)))
    
    for step in range(1, k):
        if not remaining:
            break
        
        best_marginal = -float("inf")
        best_idx = None
        
        for idx in remaining:
            candidate = sorted_candidates[idx]
            
            # Marginal gain = score - overlaps with already selected
            marginal = candidate.score
            for sel in selected:
                marginal -= compute_pairwise_overlap(candidate, sel)
            
            if marginal > best_marginal:
                best_marginal = marginal
                best_idx = idx
        
        if best_marginal <= 0:
            break
        
        selected.append(sorted_candidates[best_idx])
        remaining.remove(best_idx)
    
    return selected
```

### 3.3 Pre-filter for Efficiency

```python
def prefilter_candidates(
    candidates: list[MetaInsightCandidate],
    max_candidates: int = 5000,
) -> list[MetaInsightCandidate]:
    """Keep only top-N by score. Low scorers have near-zero chance of selection."""
    if len(candidates) <= max_candidates:
        return candidates
    sorted_cands = sorted(candidates, key=lambda c: c.score, reverse=True)
    return sorted_cands[:max_candidates]
```

---

## Part 4: Natural Language Summaries

```python
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
        candidate.breakdown, candidate.measure
    )
    
    ext_dim = candidate.extending_dimension
    proportion = cs["proportion"]
    count = cs["count"]
    hdp_size = candidate.hdp_size
    
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
                    candidate.breakdown, candidate.measure
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


def _pattern_type_to_text(pattern_type: str, highlight: str, breakdown: str, measure: str) -> str:
    """Convert pattern type + highlight into readable text."""
    try:
        import ast
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
        return templates.get(pattern_type, lambda: f"{pattern_type} on {measure}")()
    except (IndexError, TypeError):
        return f"{pattern_type} pattern on {measure} across {breakdown}"
```

---

## Part 5: Layer 2P — Raw MetaInsight Explorer

```python
def generate_layer2p_report(
    all_candidates: dict[str, list[MetaInsightCandidate]],
    output_path: str,
):
    """Generate diagnostic report of all raw candidates per view."""
    lines = [
        "=" * 70,
        "LAYER 2P — RAW METAINSIGHT EXPLORER",
        "=" * 70, "",
    ]
    
    for view_name, candidates in all_candidates.items():
        lines.append(f"{'=' * 70}")
        lines.append(f"VIEW: {view_name}  |  Total candidates: {len(candidates):,}")
        lines.append(f"{'=' * 70}")
        
        if not candidates:
            lines.append("  (no candidates)\n")
            continue
        
        scores = [c.score for c in candidates]
        lines.append(f"\nScore distribution:")
        lines.append(f"  Max={max(scores):.4f}  Median={sorted(scores)[len(scores)//2]:.4f}  "
                    f"Min={min(scores):.4f}  Mean={sum(scores)/len(scores):.4f}")
        
        # Pattern type breakdown
        type_counts: dict[str, int] = {}
        type_actionable: dict[str, int] = {}
        for c in candidates:
            type_counts[c.pattern_type] = type_counts.get(c.pattern_type, 0) + 1
            if c.exceptions:
                type_actionable[c.pattern_type] = type_actionable.get(c.pattern_type, 0) + 1
        
        lines.append(f"\n  {'Pattern Type':<25} {'Total':>8} {'Actionable':>12} {'Top Score':>10}")
        lines.append(f"  {'-'*55}")
        for pt in sorted(type_counts, key=lambda x: -type_counts[x]):
            top = max((c.score for c in candidates if c.pattern_type == pt), default=0)
            lines.append(f"  {pt:<25} {type_counts[pt]:>8,} "
                        f"{type_actionable.get(pt, 0):>12,} {top:>10.4f}")
        
        # Strategy breakdown
        strat_counts: dict[str, int] = {}
        for c in candidates:
            strat_counts[c.extending_strategy] = strat_counts.get(c.extending_strategy, 0) + 1
        lines.append(f"\nExtending strategies:")
        for s, n in sorted(strat_counts.items(), key=lambda x: -x[1]):
            lines.append(f"  {s}: {n:,}")
        
        # Universal vs actionable
        universal = sum(1 for c in candidates if not c.exceptions)
        lines.append(f"\nUniversal: {universal:,}  |  Actionable: {len(candidates)-universal:,}")
        
        lines.append("")
    
    with open(output_path, "w") as f:
        f.write("\n".join(lines))
    print(f"Layer 2P report -> {output_path}")
```

---

## Part 6: Layer 3P — Ranked Per-View Dashboard

```python
def generate_layer3p_report(
    all_ranked: dict[str, list[MetaInsightCandidate]],
    all_candidates: dict[str, list[MetaInsightCandidate]],
    output_path: str,
):
    """Generate the ranked dashboard with full detail and NL summaries."""
    lines = [
        "=" * 70,
        "LAYER 3P — RANKED PER-VIEW DASHBOARD",
        "=" * 70, "",
    ]
    
    for view_name in all_ranked:
        ranked = all_ranked[view_name]
        total = len(all_candidates[view_name])
        
        lines.append(f"{'=' * 70}")
        lines.append(f"VIEW: {view_name}  |  Selected {len(ranked)} from {total:,} candidates")
        lines.append(f"{'=' * 70}")
        
        # Diversity profile
        types_repr = sorted(set(c.pattern_type for c in ranked))
        dims_repr = sorted(set(c.extending_dimension for c in ranked))
        measures_repr = sorted(set(c.measure for c in ranked if c.measure != "(varies)"))
        
        lines.append(f"\nDiversity:")
        lines.append(f"  Pattern types ({len(types_repr)}): {', '.join(types_repr)}")
        lines.append(f"  Extending dims ({len(dims_repr)}): {', '.join(dims_repr)}")
        lines.append(f"  Measures ({len(measures_repr)}): {', '.join(measures_repr[:8])}"
                    + (f" +{len(measures_repr)-8} more" if len(measures_repr) > 8 else ""))
        
        # TotalUse stats
        total_use = compute_total_use_approx(ranked)
        sum_scores = sum(c.score for c in ranked)
        lines.append(f"\nTotalUse: {total_use:.4f}  |  Sum of scores: {sum_scores:.4f}  "
                    f"|  Redundancy penalty: {sum_scores - total_use:.4f}")
        
        # Ranked list
        lines.append(f"\n--- Ranked MetaInsights ---\n")
        
        for rank, c in enumerate(ranked, 1):
            lines.append(f"  #{rank}  score={c.score:.4f}  "
                        f"(conciseness={c.conciseness:.4f}, impact={c.impact:.4f})")
            lines.append(f"    {c.extending_strategy} on {c.extending_dimension}  |  "
                        f"{c.pattern_type}  |  breakdown={c.breakdown}  |  measure={c.measure}")
            lines.append(f"    Subspace: {c.base_subspace}  |  HDP: {c.hdp_size}")
            
            for cs in c.commonness_sets:
                members = ", ".join(cs["members"][:6])
                more = f" +{len(cs['members'])-6} more" if len(cs["members"]) > 6 else ""
                lines.append(f"    Commonness: [{cs['pattern_type']}] {cs['highlight']}  "
                           f"({cs['count']}/{c.hdp_size} = {cs['proportion']:.0%})")
                lines.append(f"      Members: {members}{more}")
            
            if c.exceptions:
                lines.append(f"    Exceptions ({len(c.exceptions)}):")
                for exc in c.exceptions[:4]:
                    lines.append(f"      {exc['member_label']:<25} {exc['category']:<20} "
                               f"{exc['highlight'] or ''}")
                if len(c.exceptions) > 4:
                    lines.append(f"      ... +{len(c.exceptions)-4} more")
            
            nl = generate_nl_summary(c)
            lines.append(f"    >> {nl}")
            lines.append("")
        
        lines.append("")
    
    with open(output_path, "w") as f:
        f.write("\n".join(lines))
    print(f"Layer 3P report -> {output_path}")
```

---

## Part 7: Running Phase 5

```python
import json

if __name__ == "__main__":
    import os
    
    os.makedirs("metainsights", exist_ok=True)
    os.makedirs("reports", exist_ok=True)
    
    views = ["view1", "view2", "view3", "view4"]
    k = 15
    
    all_candidates = {}
    all_ranked = {}
    
    for view_name in views:
        path = f"metainsights/{view_name}_candidates.json"
        print(f"\nLoading {path}...")
        candidates = load_candidates(path)
        print(f"  {len(candidates):,} candidates loaded")
        
        filtered = prefilter_candidates(candidates, max_candidates=5000)
        print(f"  {len(filtered):,} after pre-filter")
        
        ranked = rank_metainsights(filtered, k=k)
        print(f"  {len(ranked)} selected for top-{k}")
        
        all_candidates[view_name] = candidates
        all_ranked[view_name] = ranked
        
        # Save ranked list
        ranked_data = [c.to_dict() for c in ranked]
        with open(f"metainsights/{view_name}_ranked.json", "w") as f:
            json.dump(ranked_data, f, indent=2, default=str)
    
    generate_layer2p_report(all_candidates, "reports/layer2p_raw_explorer.txt")
    generate_layer3p_report(all_ranked, all_candidates, "reports/layer3p_ranked_dashboard.txt")
    
    # Print summary
    print(f"\n{'=' * 70}")
    print("Phase 5 Summary")
    print(f"{'=' * 70}")
    for view_name in views:
        ranked = all_ranked[view_name]
        total = len(all_candidates[view_name])
        types = set(c.pattern_type for c in ranked)
        print(f"  {view_name}: {len(ranked)} selected from {total:,}  "
              f"| types: {', '.join(sorted(types))}")
```

---

## Validation Checklist

- [ ] All 4 views produce ranked lists (up to 15 each)
- [ ] Top-ranked candidates are diverse: multiple pattern types, extending dimensions, measures
- [ ] Redundancy penalty > 0 for each view (ranking removes redundancy)
- [ ] No two adjacent ranked candidates have overlap ratio > 0.8
- [ ] Natural language summaries are readable and grammatically correct
- [ ] Layer 2P shows complete statistics for all raw candidates
- [ ] Layer 3P shows diversity profile and full ranked list per view
- [ ] Ranking completes in under 30 seconds total (all 4 views)

### Spot Checks

- [ ] #1 ranked per view was in the top 3 by raw score
- [ ] At least one candidate ranked by raw score in top-5 was excluded from ranked list — verify it overlaps with something already selected
- [ ] At least one candidate not in top-10 by raw score appears in ranked list — verify it adds diversity

### What to bring back

1. `reports/layer2p_raw_explorer.txt`
2. `reports/layer3p_ranked_dashboard.txt`
3. Per-view: diversity profile (how many pattern types, extending dims, measures in top-15)
4. One example of redundancy elimination per view
5. Any NL summary issues
