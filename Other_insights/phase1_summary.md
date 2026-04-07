# Phase 1 Summary

## Files Created

- `intermediate/int_demand_supply.parquet` — 23,076 rows × 31 cols
- `intermediate/int_hospital_performance.parquet` — 22,147 rows × 33 cols
- `intermediate/int_enrolment_monthly.parquet` — 26,480 rows × 8 cols
- `intermediate/int_specialty_gap.parquet` — 7,138 rows × 13 cols

## Anomalies / Notes

- None detected

## Assumptions

- Geography spine built from `ref_up_geography`; months from `cm_case.admission_month`.
- Demand block = beneficiary's HOME block (from `bm_household`), not hospital location.
- Supply columns are static (not time-varying) — joined uniformly across all months.
- Enrolment columns are static snapshots, not monthly-varying in `int_demand_supply`.
- `claims_per_case` aggregates all claims per case to prevent row explosion.
- Hospital performance uses only the active (non-rejected/cancelled) preauth, latest by `initiated_at`.
- Only `procedure_rank = 1` used for procedure grouping; add-ons excluded.
- `total_amount_approved` in `claims_per_case` set to NaN when no claim is approved (avoids misleading 0 sum).
- Cases with no matched preauth/procedure are included in `int_hospital_performance` under null procedure group.