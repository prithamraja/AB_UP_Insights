# Phase 2 Product 1 Summary

## Files Created

- `analytics/gap_utilization_scores.parquet` — 641 rows x 20 cols
- `analytics/gap_specialty_matrix.parquet` — 7,138 rows x 16 cols
- `analytics/gap_disease_burden.parquet` — 3,717 rows x 11 cols
- `analytics/gap_portability_flows.parquet` — 641 rows x 10 cols
- `analytics/gap_district_patient_flows.parquet` — 5,080 rows x 5 cols
- `analytics/gap_card_dropoff.parquet` — 641 rows x 13 cols
- `analytics/gap_repeat_utilization.parquet` — 641 rows x 13 cols
- `analytics/gap_seasonal_patterns.parquet` — 23,076 rows x 8 cols
- `analytics/gap_seasonal_summary.parquet` — 641 rows x 9 cols
- `analytics/gap_delisted_impact.parquet` — 23 rows x 16 cols

## Key Findings

### Top 10 High-Enrolment Low-Utilization Blocks
- Mohanlalganj, Lucknow: 652 enrolled, 0.084 utilization
- Chinhat, Lucknow: 599 enrolled, 0.083 utilization
- Baragaon, Varanasi: 575 enrolled, 0.083 utilization
- Chiraigaon, Varanasi: 556 enrolled, 0.083 utilization
- Sarbanandapur, Kanpur Nagar: 554 enrolled, 0.081 utilization
- Lakhimpur Block 1, Lakhimpur Kheri: 516 enrolled, 0.072 utilization
- Bahraich Block 7, Bahraich: 514 enrolled, 0.076 utilization
- Bulandshahr Block 3, Bulandshahr: 513 enrolled, 0.090 utilization
- Moradabad Block 7, Moradabad: 512 enrolled, 0.088 utilization
- Bijnor Block 3, Bijnor: 505 enrolled, 0.087 utilization

### Top 5 Specialty Gaps (no local supply)
- OBG: 1010 unmet cases
- GS: 999 unmet cases
- MED: 805 unmet cases
- ORTH: 804 unmet cases
- CARD: 791 unmet cases

### Top 5 District-to-District Patient Flows
- Prayagraj -> Prayagraj: 28 cases
- Prayagraj -> Bareilly: 26 cases
- Prayagraj -> Gorakhpur: 26 cases
- Prayagraj -> Hardoi: 26 cases
- Prayagraj -> Aligarh: 23 cases

## Assumptions

- ICD-10 classification: first-match prefix logic; order: NCD > COMMUNICABLE > MATERNAL > SURGICAL > INJURY > OTHER.
- Portability destinations use cm_case.hospital_district (no block/division).
- Seasonality threshold: >= 12 total cases AND >= 6 non-zero months per block.
- Treatment failure flag: >= 5 repeat beneficiaries AND > 50% same-proc-same-hosp pairs.
- Revenue leakage = amount_claimed on NO_SUPPLY rows only.
- 'Nearest block with supply': alphabetically first block in same district offering that specialty.
- Lost specialties = specialties only offered by the delisted hospital in that block (no other hospital offers it).