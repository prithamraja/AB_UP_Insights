# Phase 2b Summary

## Files Created

- `analytics/bench_hospital_procedure_summary.parquet` -- 101 rows x 33 cols
- `analytics/bench_cost.parquet` -- 101 rows x 30 cols
- `analytics/bench_los.parquet` -- 101 rows x 17 cols
- `analytics/bench_outcomes.parquet` -- 101 rows x 14 cols
- `analytics/bench_claims_quality.parquet` -- 101 rows x 22 cols
- `analytics/bench_trends.parquet` -- 99 rows x 27 cols
- `analytics/bench_hospital_scorecard.parquet` -- 96 rows x 29 cols

## Flag Counts

- Cost outliers (high): 3
- Cost outliers (low): 0
- High approval gap: 49
- Above package rate: 44
- Long stay outliers: 1
- Short stay outliers: 2
- High LAMA/DAMA: 4
- Excellent retention: 0
- Poor claims quality: 1
- Clean claims: 0
- Declining hospitals: 0
- Improving hospitals: 0

## Top 10 Hospitals Needing Review


## Assumptions

- Minimum 5 cases per hospital-procedure to be included in benchmarks.
- Peer groups: procedure x hospital_type (PUBLIC/PRIVATE).
- Mortality rates deliberately excluded (0.4% event rate too sparse for hospital-level inference).
- Trend detection requires >= 4 active months; uses weighted linear regression.
- Trend materiality threshold: slope must change metric by > 5% of mean per month.
- Claims quality score: average of 3 inverted min-max-normalized components within peer group.
- LAMA/DAMA z-scores nulled when peer group base rate < 1% (sparsity guard).
- Small peer group flag set when < 3 hospitals in the peer group.