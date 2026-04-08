# Gamma Sensitivity Analysis

## view1

| Gamma | Universal | Actionable | TotalUse | Top Score |
|-------|-----------|------------|----------|-----------|
| 0.1 | 15 | 0 | 14.0474 | 0.9442 |
| 0.3 | 11 | 4 | 12.7735 | 0.9430 |
| 0.5 | 6 | 9 | 11.9034 | 0.9430 |
| 0.8 | 0 | 15 | 11.7642 | 0.9430 |

### gamma = 0.1

1. (score=0.9442) [universal] Across all hospital_sub_type values, length_of_stay is evenly distributed across division values
2. (score=0.9442) [universal] Across all division values, CARD and ORTH lead in amount_claimed among specialty_code values
3. (score=0.9442) [universal] Across all hospital_sub_type values, CARD has the highest base_amount among specialty_code values
4. (score=0.9442) [universal] Across all age_group values, INJURY has the lowest case_count among disease_category values
5. (score=0.9442) [universal] Across all preauth_status values, 15-25 and 26-40 are lowest in case_count among age_group values
6. (score=0.9442) [universal] Across all division values, NORMAL accounts for the majority of case_count among discharge_type values
7. (score=0.9442) [universal] Across all hospital_sub_type values, case_count has an outlier at 2023-02 (below) in admission_month
8. (score=0.9442) [universal] Across all bed_size_bucket values, case_count shows seasonal pattern (PERIOD_12) over admission_month
9. (score=0.9442) [universal] Across all division values, settlement_tat_days is evenly distributed across district values
10. (score=0.9442) [universal] Across all disease_category values, 41-60 and 60+ lead in base_amount among age_group values
11. (score=0.9442) [universal] Across all division values, NORMAL has the highest case_count among discharge_type values
12. (score=0.9442) [universal] Across all disease_category values, QUERY_RAISED and REJECTED are lowest in amount_claimed among preauth_status values
13. (score=0.9442) [universal] Across all division values, query_count is decreasing over admission_month
14. (score=0.9442) [universal] Across all temporal_grain values, query_count is decreasing over (varies)
15. (score=0.8284) [universal] Across all district values, APPROVED has the highest amount_claimed among claim_status values

### gamma = 0.3

1. (score=0.9430) [actionable] Across nearly all district values (74/75), NORMAL has the highest amount_paid among discharge_type values. Exception: Hamirpur (different pattern)
2. (score=0.9430) [actionable] Across nearly all district values (74/75), DAMA and LAMA lead in is_lama_dama among discharge_type values. Exception: Shamli (different pattern)
3. (score=0.9010) [actionable] Across nearly all district values (73/75), NORMAL accounts for the majority of amount_paid among discharge_type values. Exception: Hamirpur (different pattern); Sambhal (different pattern)
4. (score=0.8326) [universal] Across all hospital_sub_type values, length_of_stay is evenly distributed across division values
5. (score=0.8326) [universal] Across all age_group values, INJURY has the lowest case_count among disease_category values
6. (score=0.8326) [universal] Across all preauth_status values, 15-25 and 26-40 are lowest in case_count among age_group values
7. (score=0.8326) [universal] Across all hospital_sub_type values, case_count has an outlier at 2023-02 (below) in admission_month
8. (score=0.8326) [universal] Across all bed_size_bucket values, case_count shows seasonal pattern (PERIOD_12) over admission_month
9. (score=0.8326) [universal] Across all division values, settlement_tat_days is evenly distributed across district values
10. (score=0.8326) [universal] Across all hospital_sub_type values, CARD and ORTH lead in amount_claimed among specialty_code values
11. (score=0.8326) [universal] Across all disease_category values, CARD has the highest base_amount among specialty_code values
12. (score=0.8326) [universal] Across all disease_category values, QUERY_RAISED and REJECTED are lowest in amount_claimed among preauth_status values
13. (score=0.8326) [universal] Across all division values, query_count is decreasing over admission_month
14. (score=0.8326) [universal] Across all temporal_grain values, query_count is decreasing over (varies)
15. (score=0.8274) [actionable] Across nearly all district values (74/75), is_death is decreasing over admission_year. Exception: Chitrakoot (no clear pattern)

### gamma = 0.5

1. (score=0.9430) [actionable] Across nearly all district values (74/75), NORMAL has the highest amount_paid among discharge_type values. Exception: Hamirpur (different pattern)
2. (score=0.9430) [actionable] Across nearly all district values (74/75), DAMA and LAMA lead in is_lama_dama among discharge_type values. Exception: Shamli (different pattern)
3. (score=0.9010) [actionable] Across nearly all district values (73/75), NORMAL accounts for the majority of amount_paid among discharge_type values. Exception: Hamirpur (different pattern); Sambhal (different pattern)
4. (score=0.8274) [actionable] Across nearly all district values (74/75), QUERY_RAISED and REJECTED are lowest in case_count among preauth_status values. Exception: Mau (different pattern)
5. (score=0.8274) [actionable] Across nearly all district values (74/75), is_death is decreasing over admission_year. Exception: Chitrakoot (no clear pattern)
6. (score=0.8273) [actionable] Across nearly all division values (17/18), length_of_stay is evenly distributed across disease_category values. Exception: Chitrakoot (no clear pattern)
7. (score=0.8273) [actionable] Across nearly all division values (17/18), CARD and ORTH lead in base_amount among specialty_code values. Exception: Basti (different pattern)
8. (score=0.7548) [actionable] Across nearly all specialty_code values (10/11), VERY_LARGE (300+) has the lowest base_amount among bed_size_bucket values. Exception: CARD (different pattern)
9. (score=0.7258) [actionable] Across nearly all division values (17/18), CARD has the highest base_amount among specialty_code values. Exception: Azamgarh (different pattern)
10. (score=0.7211) [universal] Across all preauth_status values, 15-25 and 26-40 are lowest in amount_claimed among age_group values
11. (score=0.7211) [universal] Across all hospital_sub_type values, case_count has an outlier at 2023-02 (below) in admission_month
12. (score=0.7211) [universal] Across all bed_size_bucket values, case_count shows seasonal pattern (PERIOD_12) over admission_month
13. (score=0.7211) [universal] Across all age_group values, settlement_tat_days is evenly distributed across division values
14. (score=0.7211) [universal] Across all disease_category values, 15-25 has the lowest case_count among age_group values
15. (score=0.7211) [universal] Across all division values, query_count is decreasing over admission_month

### gamma = 0.8

1. (score=0.9430) [actionable] Across nearly all district values (74/75), NORMAL has the highest amount_paid among discharge_type values. Exception: Hamirpur (different pattern)
2. (score=0.9430) [actionable] Across nearly all district values (74/75), DAMA and LAMA lead in is_lama_dama among discharge_type values. Exception: Shamli (different pattern)
3. (score=0.9010) [actionable] Across nearly all district values (73/75), NORMAL accounts for the majority of amount_paid among discharge_type values. Exception: Hamirpur (different pattern); Sambhal (different pattern)
4. (score=0.8274) [actionable] Across nearly all district values (74/75), QUERY_RAISED and REJECTED are lowest in case_count among preauth_status values. Exception: Mau (different pattern)
5. (score=0.8274) [actionable] Across nearly all district values (74/75), is_death is decreasing over admission_year. Exception: Chitrakoot (no clear pattern)
6. (score=0.8273) [actionable] Across nearly all division values (17/18), length_of_stay is evenly distributed across disease_category values. Exception: Chitrakoot (no clear pattern)
7. (score=0.8273) [actionable] Across nearly all division values (17/18), CARD and ORTH lead in base_amount among specialty_code values. Exception: Basti (different pattern)
8. (score=0.7548) [actionable] Across nearly all specialty_code values (10/11), VERY_LARGE (300+) has the lowest base_amount among bed_size_bucket values. Exception: CARD (different pattern)
9. (score=0.7258) [actionable] Across nearly all division values (17/18), CARD has the highest base_amount among specialty_code values. Exception: Azamgarh (different pattern)
10. (score=0.7192) [actionable] Across most division values (16/18), SMALL (<=30) and VERY_LARGE (300+) are lowest in amount_claimed among bed_size_bucket values. Exception: Aligarh (different pattern); Ayodhya (different pattern)
11. (score=0.7089) [actionable] Across nearly all division values (17/18), 15-25 has the lowest amount_claimed among age_group values. Exception: Jhansi (different pattern)
12. (score=0.8273) [actionable] Across nearly all division values (17/18), query_count is decreasing over admission_year. Exception: Basti (no clear pattern)
13. (score=0.6968) [actionable] Across most hospital_sub_type values (7/8), computed_final_amount has an outlier at 2023-02 (below) in admission_month. Exception: NGO (no clear pattern)
14. (score=0.6968) [actionable] Across most hospital_sub_type values (7/8), settlement_tat_days is evenly distributed across specialty_code values. Exception: PHC (no clear pattern)
15. (score=0.6623) [actionable] Across nearly all specialty_code values (10/11), APPROVED and AUTO_APPROVED lead in query_count among preauth_status values. Exception: ENT (different pattern)

### Changes vs baseline (gamma=0.1)

**gamma=0.3**: 6 entered, 6 exited
  + [actionable] OUTSTANDING_1 on amount_paid via district
  + [actionable] TOP_TWO on is_lama_dama via district
  + [actionable] ATTRIBUTION on amount_paid via district
  + [universal] TOP_TWO on amount_claimed via hospital_sub_type
  + [universal] OUTSTANDING_1 on base_amount via disease_category
  + [actionable] TREND on is_death via district
  - [universal] TOP_TWO on amount_claimed via division
  - [universal] OUTSTANDING_1 on base_amount via hospital_sub_type
  - [universal] ATTRIBUTION on case_count via division
  - [universal] TOP_TWO on base_amount via disease_category
  - [universal] OUTSTANDING_1 on case_count via division
  - [universal] OUTSTANDING_1 on amount_claimed via district

**gamma=0.5**: 12 entered, 12 exited
  + [actionable] OUTSTANDING_1 on amount_paid via district
  + [actionable] TOP_TWO on is_lama_dama via district
  + [actionable] ATTRIBUTION on amount_paid via district
  + [actionable] LAST_TWO on case_count via district
  + [actionable] TREND on is_death via district
  + [actionable] EVENNESS on length_of_stay via division
  + [actionable] TOP_TWO on base_amount via division
  + [actionable] OUTSTANDING_LAST on base_amount via specialty_code
  + [actionable] OUTSTANDING_1 on base_amount via division
  + [universal] LAST_TWO on amount_claimed via preauth_status
  + [universal] EVENNESS on settlement_tat_days via age_group
  + [universal] OUTSTANDING_LAST on case_count via disease_category
  - [universal] EVENNESS on length_of_stay via hospital_sub_type
  - [universal] TOP_TWO on amount_claimed via division
  - [universal] OUTSTANDING_1 on base_amount via hospital_sub_type
  - [universal] OUTSTANDING_LAST on case_count via age_group
  - [universal] LAST_TWO on case_count via preauth_status
  - [universal] ATTRIBUTION on case_count via division
  - [universal] EVENNESS on settlement_tat_days via division
  - [universal] TOP_TWO on base_amount via disease_category
  - [universal] OUTSTANDING_1 on case_count via division
  - [universal] LAST_TWO on amount_claimed via disease_category
  - [universal] TREND on query_count via temporal_grain
  - [universal] OUTSTANDING_1 on amount_claimed via district

**gamma=0.8**: 15 entered, 15 exited
  + [actionable] OUTSTANDING_1 on amount_paid via district
  + [actionable] TOP_TWO on is_lama_dama via district
  + [actionable] ATTRIBUTION on amount_paid via district
  + [actionable] LAST_TWO on case_count via district
  + [actionable] TREND on is_death via district
  + [actionable] EVENNESS on length_of_stay via division
  + [actionable] TOP_TWO on base_amount via division
  + [actionable] OUTSTANDING_LAST on base_amount via specialty_code
  + [actionable] OUTSTANDING_1 on base_amount via division
  + [actionable] LAST_TWO on amount_claimed via division
  + [actionable] OUTSTANDING_LAST on amount_claimed via division
  + [actionable] TREND on query_count via division
  + [actionable] OUTLIER on computed_final_amount via hospital_sub_type
  + [actionable] EVENNESS on settlement_tat_days via hospital_sub_type
  + [actionable] TOP_TWO on query_count via specialty_code
  - [universal] EVENNESS on length_of_stay via hospital_sub_type
  - [universal] TOP_TWO on amount_claimed via division
  - [universal] OUTSTANDING_1 on base_amount via hospital_sub_type
  - [universal] OUTSTANDING_LAST on case_count via age_group
  - [universal] LAST_TWO on case_count via preauth_status
  - [universal] ATTRIBUTION on case_count via division
  - [universal] OUTLIER on case_count via hospital_sub_type
  - [universal] SEASONALITY on case_count via bed_size_bucket
  - [universal] EVENNESS on settlement_tat_days via division
  - [universal] TOP_TWO on base_amount via disease_category
  - [universal] OUTSTANDING_1 on case_count via division
  - [universal] LAST_TWO on amount_claimed via disease_category
  - [universal] TREND on query_count via division
  - [universal] TREND on query_count via temporal_grain
  - [universal] OUTSTANDING_1 on amount_claimed via district

---

## view2

| Gamma | Universal | Actionable | TotalUse | Top Score |
|-------|-----------|------------|----------|-----------|
| 0.1 | 9 | 6 | 9.4033 | 0.9442 |
| 0.3 | 8 | 7 | 8.7043 | 0.9430 |
| 0.5 | 6 | 9 | 8.1769 | 0.9430 |
| 0.8 | 1 | 14 | 7.8510 | 0.9430 |

### gamma = 0.1

1. (score=0.9442) [universal] Across all division values, claims_per_1000_beneficiaries is evenly distributed across district values
2. (score=0.9442) [universal] Across all division values, new_beneficiaries is decreasing over month
3. (score=0.9442) [universal] Across all division values, new_beneficiaries shows seasonal pattern (PERIOD_3) over month
4. (score=0.9442) [universal] Across all division values, cases_admitted has a significant shift at 2023-03 in month
5. (score=0.9442) [universal] Across all temporal_grain values, cumulative_beneficiaries is increasing over (varies)
6. (score=0.9442) [universal] Across all division values, new_beneficiaries forms a peak at 2023 over year
7. (score=0.9442) [universal] Across all district values, cumulative_beneficiaries is increasing over quarter
8. (score=0.9442) [universal] Across all district values, cumulative_beneficiaries shows seasonal pattern (PERIOD_3) over quarter
9. (score=0.9430) [actionable] Across nearly all district values (74/75), claims_per_1000_beneficiaries has a significant shift at 2023Q1 in quarter. Exception: Balrampur (claims_per_1000_beneficiaries has a significant shift at 2023Q2 in quarter)
10. (score=0.4877) [actionable] Across most temporal_grain values (2/3), new_beneficiaries shows seasonal pattern (PERIOD_3) over (varies). Exception: year (different pattern)
11. (score=0.4470) [actionable] Across most measure values (20/26), (varies) shows seasonal pattern (PERIOD_3) over month. Exceptions: portability_cases ((varies) shows seasonal pattern (PERIOD_4) over month); payment_failures ((varies) shows seasonal pattern (PERIOD_4) over month); approval_rate (different pattern) and 3 others
12. (score=0.9442) [universal] Across all district values, new_households forms a peak at 2023 over year
13. (score=0.2894) [actionable] Across most measure values (17/26), (varies) has a significant shift at 2023-03 in month. Exceptions: new_beneficiaries ((varies) has a significant shift at 2025-06 in month); new_households ((varies) has a significant shift at 2025-06 in month); cards_issued ((varies) has a significant shift at 2025-06 in month) and 6 others
14. (score=0.4877) [actionable] Across most temporal_grain values (2/3), new_beneficiaries is decreasing over (varies). Exception: year (different pattern)
15. (score=0.4877) [actionable] Across most temporal_grain values (2/3), new_households shows seasonal pattern (PERIOD_3) over (varies). Exception: year (different pattern)

### gamma = 0.3

1. (score=0.9430) [actionable] Across nearly all district values (74/75), cards_issued shows seasonal pattern (PERIOD_3) over month. Exception: Mahoba (cards_issued shows seasonal pattern (PERIOD_4) over month)
2. (score=0.9430) [actionable] Across nearly all district values (74/75), claims_per_1000_beneficiaries has a significant shift at 2023Q1 in quarter. Exception: Balrampur (claims_per_1000_beneficiaries has a significant shift at 2023Q2 in quarter)
3. (score=0.8326) [universal] Across all division values, claims_per_1000_beneficiaries is evenly distributed across district values
4. (score=0.8326) [universal] Across all division values, new_beneficiaries is decreasing over month
5. (score=0.8326) [universal] Across all temporal_grain values, cumulative_beneficiaries is increasing over (varies)
6. (score=0.8326) [universal] Across all division values, new_beneficiaries forms a peak at 2023 over year
7. (score=0.8326) [universal] Across all division values, cases_admitted has a significant shift at 2023-03 in month
8. (score=0.8326) [universal] Across all district values, cumulative_beneficiaries is increasing over quarter
9. (score=0.8326) [universal] Across all division values, cumulative_beneficiaries shows seasonal pattern (PERIOD_3) over quarter
10. (score=0.4877) [actionable] Across most temporal_grain values (2/3), new_beneficiaries shows seasonal pattern (PERIOD_3) over (varies). Exception: year (different pattern)
11. (score=0.4470) [actionable] Across most measure values (20/26), (varies) shows seasonal pattern (PERIOD_3) over month. Exceptions: portability_cases ((varies) shows seasonal pattern (PERIOD_4) over month); payment_failures ((varies) shows seasonal pattern (PERIOD_4) over month); approval_rate (different pattern) and 3 others
12. (score=0.8326) [universal] Across all district values, new_households forms a peak at 2023 over year
13. (score=0.2894) [actionable] Across most measure values (17/26), (varies) has a significant shift at 2023-03 in month. Exceptions: new_beneficiaries ((varies) has a significant shift at 2025-06 in month); new_households ((varies) has a significant shift at 2025-06 in month); cards_issued ((varies) has a significant shift at 2025-06 in month) and 6 others
14. (score=0.4877) [actionable] Across most temporal_grain values (2/3), new_beneficiaries is decreasing over (varies). Exception: year (different pattern)
15. (score=0.4877) [actionable] Across most temporal_grain values (2/3), new_households shows seasonal pattern (PERIOD_3) over (varies). Exception: year (different pattern)

### gamma = 0.5

1. (score=0.9430) [actionable] Across nearly all district values (74/75), cards_issued shows seasonal pattern (PERIOD_3) over month. Exception: Mahoba (cards_issued shows seasonal pattern (PERIOD_4) over month)
2. (score=0.9430) [actionable] Across nearly all district values (74/75), claims_per_1000_beneficiaries has a significant shift at 2023Q1 in quarter. Exception: Balrampur (claims_per_1000_beneficiaries has a significant shift at 2023Q2 in quarter)
3. (score=0.8273) [actionable] Across nearly all division values (17/18), payment_count is increasing over month. Exception: Prayagraj (different pattern)
4. (score=0.7211) [universal] Across all division values, claims_per_1000_beneficiaries is evenly distributed across district values
5. (score=0.7211) [universal] Across all temporal_grain values, cumulative_beneficiaries is increasing over (varies)
6. (score=0.7211) [universal] Across all division values, new_beneficiaries forms a peak at 2023 over year
7. (score=0.8273) [actionable] Across nearly all division values (17/18), public_cases has a significant shift at 2023-03 in month. Exception: Aligarh (public_cases has a significant shift at 2023-04 in month)
8. (score=0.4877) [actionable] Across most temporal_grain values (2/3), new_beneficiaries shows seasonal pattern (PERIOD_3) over (varies). Exception: year (different pattern)
9. (score=0.4470) [actionable] Across most measure values (20/26), (varies) shows seasonal pattern (PERIOD_3) over month. Exceptions: portability_cases ((varies) shows seasonal pattern (PERIOD_4) over month); payment_failures ((varies) shows seasonal pattern (PERIOD_4) over month); approval_rate (different pattern) and 3 others
10. (score=0.7211) [universal] Across all district values, cumulative_beneficiaries is increasing over quarter
11. (score=0.7211) [universal] Across all division values, cumulative_beneficiaries shows seasonal pattern (PERIOD_3) over quarter
12. (score=0.7211) [universal] Across all district values, new_households forms a peak at 2023 over year
13. (score=0.2894) [actionable] Across most measure values (17/26), (varies) has a significant shift at 2023-03 in month. Exceptions: new_beneficiaries ((varies) has a significant shift at 2025-06 in month); new_households ((varies) has a significant shift at 2025-06 in month); cards_issued ((varies) has a significant shift at 2025-06 in month) and 6 others
14. (score=0.4877) [actionable] Across most temporal_grain values (2/3), new_beneficiaries is decreasing over (varies). Exception: year (different pattern)
15. (score=0.4877) [actionable] Across most temporal_grain values (2/3), new_households shows seasonal pattern (PERIOD_3) over (varies). Exception: year (different pattern)

### gamma = 0.8

1. (score=0.9430) [actionable] Across nearly all district values (74/75), cards_issued shows seasonal pattern (PERIOD_3) over month. Exception: Mahoba (cards_issued shows seasonal pattern (PERIOD_4) over month)
2. (score=0.9430) [actionable] Across nearly all district values (74/75), claims_per_1000_beneficiaries has a significant shift at 2023Q1 in quarter. Exception: Balrampur (claims_per_1000_beneficiaries has a significant shift at 2023Q2 in quarter)
3. (score=0.8273) [actionable] Across nearly all division values (17/18), payment_count is increasing over month. Exception: Prayagraj (different pattern)
4. (score=0.7192) [actionable] Across most division values (16/18), avg_claim_amount is evenly distributed across district values. Exception: Moradabad (no clear pattern); Chitrakoot (no clear pattern)
5. (score=0.6840) [actionable] Across most district values (65/75), claims_per_1000_beneficiaries forms a peak at 2023 over year. Exceptions: Bareilly (no clear pattern); Basti (no clear pattern); Deoria (no clear pattern) and 7 others
6. (score=0.5537) [universal] Across all temporal_grain values, cumulative_beneficiaries is increasing over (varies)
7. (score=0.8273) [actionable] Across nearly all division values (17/18), public_cases has a significant shift at 2023-03 in month. Exception: Aligarh (public_cases has a significant shift at 2023-04 in month)
8. (score=0.4877) [actionable] Across most temporal_grain values (2/3), new_beneficiaries shows seasonal pattern (PERIOD_3) over (varies). Exception: year (different pattern)
9. (score=0.4470) [actionable] Across most measure values (20/26), (varies) shows seasonal pattern (PERIOD_3) over month. Exceptions: portability_cases ((varies) shows seasonal pattern (PERIOD_4) over month); payment_failures ((varies) shows seasonal pattern (PERIOD_4) over month); approval_rate (different pattern) and 3 others
10. (score=0.6840) [actionable] Across most district values (65/75), new_beneficiaries is decreasing over quarter. Exceptions: Ayodhya (different pattern); Banda (different pattern); Etah (different pattern) and 7 others
11. (score=0.6373) [actionable] Across most division values (15/18), new_beneficiaries shows seasonal pattern (PERIOD_3) over quarter. Exception: Azamgarh (different pattern); Varanasi (different pattern); Saharanpur (different pattern)
12. (score=0.2894) [actionable] Across most measure values (17/26), (varies) has a significant shift at 2023-03 in month. Exceptions: new_beneficiaries ((varies) has a significant shift at 2025-06 in month); new_households ((varies) has a significant shift at 2025-06 in month); cards_issued ((varies) has a significant shift at 2025-06 in month) and 6 others
13. (score=0.4621) [actionable] Across most division values (11/18), new_households forms a peak at 2023Q2 over quarter. Exceptions: Agra (new_households forms a peak at 2023Q3 over quarter); Azamgarh (new_households forms a peak at 2023Q3 over quarter); Chitrakoot (new_households forms a peak at 2023Q3 over quarter) and 4 others
14. (score=0.4877) [actionable] Across most temporal_grain values (2/3), new_beneficiaries is decreasing over (varies). Exception: year (different pattern)
15. (score=0.4877) [actionable] Across most temporal_grain values (2/3), new_households shows seasonal pattern (PERIOD_3) over (varies). Exception: year (different pattern)

### Changes vs baseline (gamma=0.1)

**gamma=0.3**: 2 entered, 2 exited
  + [actionable] SEASONALITY on cards_issued via district
  + [universal] SEASONALITY on cumulative_beneficiaries via division
  - [universal] SEASONALITY on new_beneficiaries via division
  - [universal] SEASONALITY on cumulative_beneficiaries via district

**gamma=0.5**: 4 entered, 4 exited
  + [actionable] SEASONALITY on cards_issued via district
  + [actionable] TREND on payment_count via division
  + [actionable] CHANGE_POINT on public_cases via division
  + [universal] SEASONALITY on cumulative_beneficiaries via division
  - [universal] TREND on new_beneficiaries via division
  - [universal] SEASONALITY on new_beneficiaries via division
  - [universal] CHANGE_POINT on cases_admitted via division
  - [universal] SEASONALITY on cumulative_beneficiaries via district

**gamma=0.8**: 8 entered, 8 exited
  + [actionable] SEASONALITY on cards_issued via district
  + [actionable] TREND on payment_count via division
  + [actionable] EVENNESS on avg_claim_amount via division
  + [actionable] UNIMODALITY on claims_per_1000_beneficiaries via district
  + [actionable] CHANGE_POINT on public_cases via division
  + [actionable] TREND on new_beneficiaries via district
  + [actionable] SEASONALITY on new_beneficiaries via division
  + [actionable] UNIMODALITY on new_households via division
  - [universal] EVENNESS on claims_per_1000_beneficiaries via division
  - [universal] TREND on new_beneficiaries via division
  - [universal] SEASONALITY on new_beneficiaries via division
  - [universal] CHANGE_POINT on cases_admitted via division
  - [universal] UNIMODALITY on new_beneficiaries via division
  - [universal] TREND on cumulative_beneficiaries via district
  - [universal] SEASONALITY on cumulative_beneficiaries via district
  - [universal] UNIMODALITY on new_households via district

---

## view3

| Gamma | Universal | Actionable | TotalUse | Top Score |
|-------|-----------|------------|----------|-----------|
| 0.1 | 11 | 4 | 9.7046 | 0.9442 |
| 0.3 | 9 | 6 | 8.9402 | 0.9430 |
| 0.5 | 4 | 11 | 8.4339 | 0.9430 |
| 0.8 | 2 | 13 | 8.0676 | 0.9430 |

### gamma = 0.1

1. (score=0.9442) [universal] Across all division values, CARD and ORTH lead in amount_claimed among specialty_code values
2. (score=0.9442) [universal] Across all hospital_sub_type values, total_staff is evenly distributed across specialty_code values
3. (score=0.9442) [universal] Across all hospital_sub_type values, BURNS and DERM are lowest in cases_per_bed among specialty_code values
4. (score=0.9442) [universal] Across all specialty_code values, LARGE (101-300) has the highest total_bed_strength among bed_size_bucket values
5. (score=0.9442) [universal] Across all specialty_code values, LARGE (101-300) accounts for the majority of total_bed_strength among bed_size_bucket values
6. (score=0.9442) [universal] Across all bed_size_bucket values, avg_experience_years is evenly distributed across division values
7. (score=0.5646) [universal] Across all specialty_code values, SMALL (<=30) has the lowest total_bed_strength among bed_size_bucket values
8. (score=0.5646) [universal] Across all specialty_code values, total_licenses is evenly distributed across bed_size_bucket values
9. (score=0.5083) [actionable] Across most measure values (14/20), (varies) is evenly distributed across hospital_sub_type values. Exceptions: total_bed_strength (no clear pattern); inpatient_beds (no clear pattern); preauth_rejected (no clear pattern) and 3 others
10. (score=0.5939) [universal] Across all hospital_sub_type values, CARD and ORTH lead in amount_approved among specialty_code values
11. (score=0.5646) [universal] Across all division values, SMALL (<=30) has the highest cases_per_bed among bed_size_bucket values
12. (score=0.5646) [universal] Across all division values, SMALL (<=30) accounts for the majority of cases_per_bed among bed_size_bucket values
13. (score=0.4583) [actionable] Across most measure values (12/20), SMALL (<=30) and VERY_LARGE (300+) are lowest in (varies) among bed_size_bucket values. Exceptions: total_bed_strength (different pattern); inpatient_beds (different pattern); total_staff (different pattern) and 5 others
14. (score=0.4461) [actionable] Across most measure values (11/20), VERY_LARGE (300+) has the lowest (varies) among bed_size_bucket values. Exceptions: total_bed_strength (different pattern); inpatient_beds (different pattern); total_staff (different pattern) and 6 others
15. (score=0.6840) [actionable] Across most specialty_code values (13/15), LARGE (101-300) and MEDIUM (31-100) lead in admissions_before_last_year among bed_size_bucket values. Exception: DERM (different pattern); PSYCH (different pattern)

### gamma = 0.3

1. (score=0.9430) [actionable] Across nearly all district values (74/75), CARD and ORTH lead in amount_claimed among specialty_code values. Exception: Shamli (CARD and OBG lead in amount_claimed among specialty_code values)
2. (score=0.8326) [universal] Across all hospital_sub_type values, total_staff is evenly distributed across specialty_code values
3. (score=0.8326) [universal] Across all hospital_sub_type values, BURNS and DERM are lowest in cases_per_bed among specialty_code values
4. (score=0.8326) [universal] Across all specialty_code values, LARGE (101-300) has the highest total_bed_strength among bed_size_bucket values
5. (score=0.8326) [universal] Across all specialty_code values, LARGE (101-300) accounts for the majority of total_bed_strength among bed_size_bucket values
6. (score=0.5332) [actionable] Across most specialty_code values (11/15), VERY_LARGE (300+) has the lowest cases_treated among bed_size_bucket values. Exceptions: BURNS (no clear pattern); DERM (no clear pattern); NEPHRO (no clear pattern) and 1 others
7. (score=0.5083) [actionable] Across most measure values (14/20), (varies) is evenly distributed across hospital_sub_type values. Exceptions: total_bed_strength (no clear pattern); inpatient_beds (no clear pattern); preauth_rejected (no clear pattern) and 3 others
8. (score=0.8326) [universal] Across all bed_size_bucket values, avg_experience_years is evenly distributed across division values
9. (score=0.4979) [universal] Across all specialty_code values, total_licenses is evenly distributed across bed_size_bucket values
10. (score=0.4583) [actionable] Across most measure values (12/20), SMALL (<=30) and VERY_LARGE (300+) are lowest in (varies) among bed_size_bucket values. Exceptions: total_bed_strength (different pattern); inpatient_beds (different pattern); total_staff (different pattern) and 5 others
11. (score=0.4461) [actionable] Across most measure values (11/20), VERY_LARGE (300+) has the lowest (varies) among bed_size_bucket values. Exceptions: total_bed_strength (different pattern); inpatient_beds (different pattern); total_staff (different pattern) and 6 others
12. (score=0.5237) [universal] Across all hospital_sub_type values, CARD and ORTH lead in amount_approved among specialty_code values
13. (score=0.7192) [actionable] Across most division values (16/18), MEDIUM (31-100) and SMALL (<=30) lead in cases_per_bed among bed_size_bucket values. Exception: Ayodhya (different pattern); Saharanpur (different pattern)
14. (score=0.4979) [universal] Across all division values, SMALL (<=30) has the highest cases_per_bed among bed_size_bucket values
15. (score=0.4979) [universal] Across all division values, SMALL (<=30) accounts for the majority of cases_per_bed among bed_size_bucket values

### gamma = 0.5

1. (score=0.9430) [actionable] Across nearly all district values (74/75), CARD and ORTH lead in amount_claimed among specialty_code values. Exception: Shamli (CARD and OBG lead in amount_claimed among specialty_code values)
2. (score=0.8273) [actionable] Across nearly all division values (17/18), avg_experience_years is evenly distributed across specialty_code values. Exception: Agra (different pattern)
3. (score=0.8273) [actionable] Across nearly all division values (17/18), SMALL (<=30) accounts for the majority of cases_per_bed among bed_size_bucket values. Exception: Jhansi (different pattern)
4. (score=0.7211) [universal] Across all hospital_sub_type values, BURNS and DERM are lowest in cases_per_bed among specialty_code values
5. (score=0.7211) [universal] Across all specialty_code values, LARGE (101-300) has the highest total_bed_strength among bed_size_bucket values
6. (score=0.5332) [actionable] Across most specialty_code values (11/15), VERY_LARGE (300+) has the lowest cases_treated among bed_size_bucket values. Exceptions: BURNS (no clear pattern); DERM (no clear pattern); NEPHRO (no clear pattern) and 1 others
7. (score=0.5083) [actionable] Across most measure values (14/20), (varies) is evenly distributed across hospital_sub_type values. Exceptions: total_bed_strength (no clear pattern); inpatient_beds (no clear pattern); preauth_rejected (no clear pattern) and 3 others
8. (score=0.8028) [actionable] Across nearly all specialty_code values (14/15), total_licenses is evenly distributed across hospital_sub_type values. Exception: BURNS (no clear pattern)
9. (score=0.4583) [actionable] Across most measure values (12/20), SMALL (<=30) and VERY_LARGE (300+) are lowest in (varies) among bed_size_bucket values. Exceptions: total_bed_strength (different pattern); inpatient_beds (different pattern); total_staff (different pattern) and 5 others
10. (score=0.4461) [actionable] Across most measure values (11/20), VERY_LARGE (300+) has the lowest (varies) among bed_size_bucket values. Exceptions: total_bed_strength (different pattern); inpatient_beds (different pattern); total_staff (different pattern) and 6 others
11. (score=0.7192) [actionable] Across most division values (16/18), MEDIUM (31-100) and SMALL (<=30) lead in cases_per_bed among bed_size_bucket values. Exception: Ayodhya (different pattern); Saharanpur (different pattern)
12. (score=0.6840) [actionable] Across most specialty_code values (13/15), SMALL (<=30) and VERY_LARGE (300+) are lowest in admissions_before_last_year among bed_size_bucket values. Exception: DERM (different pattern); PSYCH (different pattern)
13. (score=0.4535) [universal] Across all hospital_sub_type values, CARD and ORTH lead in amount_approved among specialty_code values
14. (score=0.4382) [actionable] Across most hospital_sub_type values (7/8), total_staff is evenly distributed across specialty_code values. Exception: Trust (different pattern)
15. (score=0.4312) [universal] Across all bed_size_bucket values, avg_experience_years is evenly distributed across division values

### gamma = 0.8

1. (score=0.9430) [actionable] Across nearly all district values (74/75), CARD and ORTH lead in amount_claimed among specialty_code values. Exception: Shamli (CARD and OBG lead in amount_claimed among specialty_code values)
2. (score=0.8273) [actionable] Across nearly all division values (17/18), avg_experience_years is evenly distributed across specialty_code values. Exception: Agra (different pattern)
3. (score=0.8273) [actionable] Across nearly all division values (17/18), SMALL (<=30) accounts for the majority of cases_per_bed among bed_size_bucket values. Exception: Jhansi (different pattern)
4. (score=0.6840) [actionable] Across most specialty_code values (13/15), SMALL (<=30) and VERY_LARGE (300+) are lowest in admissions_before_last_year among bed_size_bucket values. Exception: DERM (different pattern); PSYCH (different pattern)
5. (score=0.5537) [universal] Across all specialty_code values, LARGE (101-300) has the highest total_bed_strength among bed_size_bucket values
6. (score=0.5332) [actionable] Across most specialty_code values (11/15), VERY_LARGE (300+) has the lowest cases_treated among bed_size_bucket values. Exceptions: BURNS (no clear pattern); DERM (no clear pattern); NEPHRO (no clear pattern) and 1 others
7. (score=0.5083) [actionable] Across most measure values (14/20), (varies) is evenly distributed across hospital_sub_type values. Exceptions: total_bed_strength (no clear pattern); inpatient_beds (no clear pattern); preauth_rejected (no clear pattern) and 3 others
8. (score=0.8028) [actionable] Across nearly all specialty_code values (14/15), total_licenses is evenly distributed across hospital_sub_type values. Exception: BURNS (no clear pattern)
9. (score=0.4583) [actionable] Across most measure values (12/20), SMALL (<=30) and VERY_LARGE (300+) are lowest in (varies) among bed_size_bucket values. Exceptions: total_bed_strength (different pattern); inpatient_beds (different pattern); total_staff (different pattern) and 5 others
10. (score=0.4461) [actionable] Across most measure values (11/20), VERY_LARGE (300+) has the lowest (varies) among bed_size_bucket values. Exceptions: total_bed_strength (different pattern); inpatient_beds (different pattern); total_staff (different pattern) and 6 others
11. (score=0.7192) [actionable] Across most division values (16/18), MEDIUM (31-100) and SMALL (<=30) lead in cases_per_bed among bed_size_bucket values. Exception: Ayodhya (different pattern); Saharanpur (different pattern)
12. (score=0.4382) [actionable] Across most hospital_sub_type values (7/8), total_staff is evenly distributed across specialty_code values. Exception: Trust (different pattern)
13. (score=0.3370) [actionable] Across most measure values (12/20), LARGE (101-300) and MEDIUM (31-100) lead in (varies) among bed_size_bucket values. Exceptions: cases_per_bed (MEDIUM (31-100) and SMALL (<=30) lead in (varies) among bed_size_bucket values); total_bed_strength (different pattern); inpatient_beds (different pattern) and 5 others
14. (score=0.5537) [universal] Across all hospital_sub_type values, BURNS and DERM are lowest in cases_per_bed among specialty_code values
15. (score=0.3897) [actionable] Across nearly all specialty_code values (14/15), LARGE (101-300) accounts for the majority of zero_claim_flag among bed_size_bucket values. Exception: OBG (no clear pattern)

### Changes vs baseline (gamma=0.1)

**gamma=0.3**: 3 entered, 3 exited
  + [actionable] TOP_TWO on amount_claimed via district
  + [actionable] OUTSTANDING_LAST on cases_treated via specialty_code
  + [actionable] TOP_TWO on cases_per_bed via division
  - [universal] TOP_TWO on amount_claimed via division
  - [universal] OUTSTANDING_LAST on total_bed_strength via specialty_code
  - [actionable] TOP_TWO on admissions_before_last_year via specialty_code

**gamma=0.5**: 9 entered, 9 exited
  + [actionable] TOP_TWO on amount_claimed via district
  + [actionable] EVENNESS on avg_experience_years via division
  + [actionable] ATTRIBUTION on cases_per_bed via division
  + [actionable] OUTSTANDING_LAST on cases_treated via specialty_code
  + [actionable] EVENNESS on total_licenses via specialty_code
  + [actionable] TOP_TWO on cases_per_bed via division
  + [actionable] LAST_TWO on admissions_before_last_year via specialty_code
  + [actionable] EVENNESS on total_staff via hospital_sub_type
  + [universal] EVENNESS on avg_experience_years via bed_size_bucket
  - [universal] TOP_TWO on amount_claimed via division
  - [universal] EVENNESS on total_staff via hospital_sub_type
  - [universal] ATTRIBUTION on total_bed_strength via specialty_code
  - [universal] EVENNESS on avg_experience_years via bed_size_bucket
  - [universal] OUTSTANDING_LAST on total_bed_strength via specialty_code
  - [universal] EVENNESS on total_licenses via specialty_code
  - [universal] OUTSTANDING_1 on cases_per_bed via division
  - [universal] ATTRIBUTION on cases_per_bed via division
  - [actionable] TOP_TWO on admissions_before_last_year via specialty_code

**gamma=0.8**: 10 entered, 10 exited
  + [actionable] TOP_TWO on amount_claimed via district
  + [actionable] EVENNESS on avg_experience_years via division
  + [actionable] ATTRIBUTION on cases_per_bed via division
  + [actionable] LAST_TWO on admissions_before_last_year via specialty_code
  + [actionable] OUTSTANDING_LAST on cases_treated via specialty_code
  + [actionable] EVENNESS on total_licenses via specialty_code
  + [actionable] TOP_TWO on cases_per_bed via division
  + [actionable] EVENNESS on total_staff via hospital_sub_type
  + [actionable] TOP_TWO on (varies) via measure
  + [actionable] ATTRIBUTION on zero_claim_flag via specialty_code
  - [universal] TOP_TWO on amount_claimed via division
  - [universal] EVENNESS on total_staff via hospital_sub_type
  - [universal] ATTRIBUTION on total_bed_strength via specialty_code
  - [universal] EVENNESS on avg_experience_years via bed_size_bucket
  - [universal] OUTSTANDING_LAST on total_bed_strength via specialty_code
  - [universal] EVENNESS on total_licenses via specialty_code
  - [universal] TOP_TWO on amount_approved via hospital_sub_type
  - [universal] OUTSTANDING_1 on cases_per_bed via division
  - [universal] ATTRIBUTION on cases_per_bed via division
  - [actionable] TOP_TWO on admissions_before_last_year via specialty_code

---

## view4

| Gamma | Universal | Actionable | TotalUse | Top Score |
|-------|-----------|------------|----------|-----------|
| 0.1 | 15 | 0 | 12.3523 | 0.9442 |
| 0.3 | 13 | 2 | 11.1134 | 0.9430 |
| 0.5 | 8 | 7 | 10.1800 | 0.9430 |
| 0.8 | 3 | 12 | 9.4551 | 0.9430 |

### gamma = 0.1

1. (score=0.9442) [universal] Across all age_group values, document_count is evenly distributed across division values
2. (score=0.9442) [universal] Across all entitlement_source values, 15-25 has the lowest claim_count among age_group values
3. (score=0.9442) [universal] Across all entitlement_source values, 15-25 and 26-40 are lowest in claim_count among age_group values
4. (score=0.9442) [universal] Across all age_group values, SECC has the highest claim_count among entitlement_source values
5. (score=0.9442) [universal] Across all age_group values, SECC accounts for the majority of claim_count among entitlement_source values
6. (score=0.9442) [universal] Across all age_group values, AUTO_APPROVED and ISA_APPROVED lead in claim_count among enrolment_status values
7. (score=0.8257) [universal] Across all bis_record_status values, has_aadhaar is evenly distributed across district values
8. (score=0.8257) [universal] Across all enrolment_status values, GOLD has the highest has_claim among bis_record_status values
9. (score=0.8257) [universal] Across all district values, REJECTED has the lowest has_claim among enrolment_status values
10. (score=0.8257) [universal] Across all age_group values, REJECTED and SHA_APPROVED are lowest in has_claim among enrolment_status values
11. (score=0.7555) [universal] Across all district values, days_enrolment_to_card is evenly distributed across age_group values
12. (score=0.7555) [universal] Across all district values, ACTIVE accounts for the majority of has_claim among card_status values
13. (score=0.7555) [universal] Across all district values, ACTIVE has the highest claim_count among card_status values
14. (score=0.7555) [universal] Across all entitlement_source values, AUTO_APPROVED and ISA_APPROVED lead in has_claim among enrolment_status values
15. (score=0.8257) [universal] Across all bis_record_status values, SECC accounts for the majority of has_claim among entitlement_source values

### gamma = 0.3

1. (score=0.9430) [actionable] Across nearly all district values (74/75), SECC has the highest claim_count among entitlement_source values. Exception: Lalitpur (different pattern)
2. (score=0.9430) [actionable] Across nearly all district values (74/75), days_enrolment_to_card is evenly distributed across card_status values. Exception: Chitrakoot (no clear pattern)
3. (score=0.8326) [universal] Across all entitlement_source values, 15-25 has the lowest claim_count among age_group values
4. (score=0.8326) [universal] Across all entitlement_source values, 15-25 and 26-40 are lowest in claim_count among age_group values
5. (score=0.8326) [universal] Across all age_group values, SECC accounts for the majority of claim_count among entitlement_source values
6. (score=0.8326) [universal] Across all age_group values, AUTO_APPROVED and ISA_APPROVED lead in claim_count among enrolment_status values
7. (score=0.7282) [universal] Across all age_group values, document_count is evenly distributed across division values
8. (score=0.7282) [universal] Across all age_group values, GOLD has the highest has_claim among bis_record_status values
9. (score=0.7282) [universal] Across all district values, REJECTED has the lowest has_claim among enrolment_status values
10. (score=0.7282) [universal] Across all age_group values, REJECTED and SHA_APPROVED are lowest in has_claim among enrolment_status values
11. (score=0.6663) [universal] Across all district values, ACTIVE accounts for the majority of has_claim among card_status values
12. (score=0.6663) [universal] Across all division values, has_aadhaar is evenly distributed across district values
13. (score=0.6663) [universal] Across all division values, ACTIVE has the highest claim_count among card_status values
14. (score=0.6663) [universal] Across all entitlement_source values, AUTO_APPROVED and ISA_APPROVED lead in has_claim among enrolment_status values
15. (score=0.7282) [universal] Across all bis_record_status values, SECC accounts for the majority of has_claim among entitlement_source values

### gamma = 0.5

1. (score=0.9430) [actionable] Across nearly all district values (74/75), SECC has the highest claim_count among entitlement_source values. Exception: Lalitpur (different pattern)
2. (score=0.9430) [actionable] Across nearly all district values (74/75), days_enrolment_to_card is evenly distributed across card_status values. Exception: Chitrakoot (no clear pattern)
3. (score=0.8273) [actionable] Across nearly all division values (17/18), REJECTED and SHA_APPROVED are lowest in claim_count among enrolment_status values. Exception: Mirzapur (different pattern)
4. (score=0.7504) [actionable] Across nearly all district values (68/75), REJECTED has the lowest has_claim among enrolment_status values. Exceptions: Lalitpur (different pattern); Amethi (different pattern); Etawah (different pattern) and 4 others
5. (score=0.7267) [actionable] Across most district values (67/75), SECC accounts for the majority of claim_count among entitlement_source values. Exceptions: Lalitpur (different pattern); Muzaffarnagar (different pattern); Gautam Buddha Nagar (different pattern) and 5 others
6. (score=0.7235) [actionable] Across nearly all division values (17/18), claim_rate is evenly distributed across entitlement_source values. Exception: Saharanpur (no clear pattern)
7. (score=0.7211) [universal] Across all age_group values, AUTO_APPROVED and ISA_APPROVED lead in claim_count among enrolment_status values
8. (score=0.6306) [universal] Across all bis_record_status values, 15-25 has the lowest claim_count among age_group values
9. (score=0.6306) [universal] Across all enrolment_status values, 15-25 and 26-40 are lowest in has_claim among age_group values
10. (score=0.6306) [universal] Across all age_group values, GOLD has the highest has_claim among bis_record_status values
11. (score=0.5770) [universal] Across all division values, ACTIVE accounts for the majority of has_claim among card_status values
12. (score=0.5770) [universal] Across all entitlement_source values, document_count is evenly distributed across division values
13. (score=0.5185) [actionable] Across most measure values (5/7), (varies) is evenly distributed across division values. Exception: claim_count (different pattern); has_claim (different pattern)
14. (score=0.5770) [universal] Across all division values, ACTIVE has the highest claim_count among card_status values
15. (score=0.5770) [universal] Across all entitlement_source values, AUTO_APPROVED and ISA_APPROVED lead in has_claim among enrolment_status values

### gamma = 0.8

1. (score=0.9430) [actionable] Across nearly all district values (74/75), SECC has the highest claim_count among entitlement_source values. Exception: Lalitpur (different pattern)
2. (score=0.9430) [actionable] Across nearly all district values (74/75), days_enrolment_to_card is evenly distributed across card_status values. Exception: Chitrakoot (no clear pattern)
3. (score=0.8273) [actionable] Across nearly all division values (17/18), REJECTED and SHA_APPROVED are lowest in claim_count among enrolment_status values. Exception: Mirzapur (different pattern)
4. (score=0.7504) [actionable] Across nearly all district values (68/75), REJECTED has the lowest has_claim among enrolment_status values. Exceptions: Lalitpur (different pattern); Amethi (different pattern); Etawah (different pattern) and 4 others
5. (score=0.7267) [actionable] Across most district values (67/75), SECC accounts for the majority of claim_count among entitlement_source values. Exceptions: Lalitpur (different pattern); Muzaffarnagar (different pattern); Gautam Buddha Nagar (different pattern) and 5 others
6. (score=0.7235) [actionable] Across nearly all division values (17/18), claim_rate is evenly distributed across entitlement_source values. Exception: Saharanpur (no clear pattern)
7. (score=0.7192) [actionable] Across most division values (16/18), AUTO_APPROVED and ISA_APPROVED lead in has_claim among enrolment_status values. Exception: Basti (different pattern); Mirzapur (different pattern)
8. (score=0.5185) [actionable] Across most measure values (5/7), (varies) is evenly distributed across division values. Exception: claim_count (different pattern); has_claim (different pattern)
9. (score=0.8273) [actionable] Across nearly all division values (17/18), GOLD has the highest has_claim among bis_record_status values. Exception: Aligarh (different pattern)
10. (score=0.4842) [universal] Across all bis_record_status values, 15-25 has the lowest claim_count among age_group values
11. (score=0.4842) [universal] Across all enrolment_status values, 15-25 and 26-40 are lowest in has_claim among age_group values
12. (score=0.4787) [actionable] Across most enrolment_status values (3/4), Lucknow and Meerut lead in claim_count among division values. Exception: REJECTED (no clear pattern)
13. (score=0.6620) [actionable] Across nearly all division values (17/18), days_card_to_first_claim is evenly distributed across age_group values. Exception: Basti (no clear pattern)
14. (score=0.4534) [actionable] Across most measure values (5/7), (varies) is evenly distributed across district values. Exception: claim_count (no clear pattern); has_claim (no clear pattern)
15. (score=0.4431) [universal] Across all division values, ACTIVE accounts for the majority of has_claim among card_status values

### Changes vs baseline (gamma=0.1)

**gamma=0.3**: 6 entered, 6 exited
  + [actionable] OUTSTANDING_1 on claim_count via district
  + [actionable] EVENNESS on days_enrolment_to_card via district
  + [universal] EVENNESS on document_count via age_group
  + [universal] OUTSTANDING_1 on has_claim via age_group
  + [universal] EVENNESS on has_aadhaar via division
  + [universal] OUTSTANDING_1 on claim_count via division
  - [universal] EVENNESS on document_count via age_group
  - [universal] OUTSTANDING_1 on claim_count via age_group
  - [universal] EVENNESS on has_aadhaar via bis_record_status
  - [universal] OUTSTANDING_1 on has_claim via enrolment_status
  - [universal] EVENNESS on days_enrolment_to_card via district
  - [universal] OUTSTANDING_1 on claim_count via district

**gamma=0.5**: 13 entered, 13 exited
  + [actionable] OUTSTANDING_1 on claim_count via district
  + [actionable] EVENNESS on days_enrolment_to_card via district
  + [actionable] LAST_TWO on claim_count via division
  + [actionable] OUTSTANDING_LAST on has_claim via district
  + [actionable] ATTRIBUTION on claim_count via district
  + [actionable] EVENNESS on claim_rate via division
  + [universal] OUTSTANDING_LAST on claim_count via bis_record_status
  + [universal] LAST_TWO on has_claim via enrolment_status
  + [universal] OUTSTANDING_1 on has_claim via age_group
  + [universal] ATTRIBUTION on has_claim via division
  + [universal] EVENNESS on document_count via entitlement_source
  + [actionable] EVENNESS on (varies) via measure
  + [universal] OUTSTANDING_1 on claim_count via division
  - [universal] EVENNESS on document_count via age_group
  - [universal] OUTSTANDING_LAST on claim_count via entitlement_source
  - [universal] LAST_TWO on claim_count via entitlement_source
  - [universal] OUTSTANDING_1 on claim_count via age_group
  - [universal] ATTRIBUTION on claim_count via age_group
  - [universal] EVENNESS on has_aadhaar via bis_record_status
  - [universal] OUTSTANDING_1 on has_claim via enrolment_status
  - [universal] OUTSTANDING_LAST on has_claim via district
  - [universal] LAST_TWO on has_claim via age_group
  - [universal] EVENNESS on days_enrolment_to_card via district
  - [universal] ATTRIBUTION on has_claim via district
  - [universal] OUTSTANDING_1 on claim_count via district
  - [universal] ATTRIBUTION on has_claim via bis_record_status

**gamma=0.8**: 15 entered, 15 exited
  + [actionable] OUTSTANDING_1 on claim_count via district
  + [actionable] EVENNESS on days_enrolment_to_card via district
  + [actionable] LAST_TWO on claim_count via division
  + [actionable] OUTSTANDING_LAST on has_claim via district
  + [actionable] ATTRIBUTION on claim_count via district
  + [actionable] EVENNESS on claim_rate via division
  + [actionable] TOP_TWO on has_claim via division
  + [actionable] EVENNESS on (varies) via measure
  + [actionable] OUTSTANDING_1 on has_claim via division
  + [universal] OUTSTANDING_LAST on claim_count via bis_record_status
  + [universal] LAST_TWO on has_claim via enrolment_status
  + [actionable] TOP_TWO on claim_count via enrolment_status
  + [actionable] EVENNESS on days_card_to_first_claim via division
  + [actionable] EVENNESS on (varies) via measure
  + [universal] ATTRIBUTION on has_claim via division
  - [universal] EVENNESS on document_count via age_group
  - [universal] OUTSTANDING_LAST on claim_count via entitlement_source
  - [universal] LAST_TWO on claim_count via entitlement_source
  - [universal] OUTSTANDING_1 on claim_count via age_group
  - [universal] ATTRIBUTION on claim_count via age_group
  - [universal] TOP_TWO on claim_count via age_group
  - [universal] EVENNESS on has_aadhaar via bis_record_status
  - [universal] OUTSTANDING_1 on has_claim via enrolment_status
  - [universal] OUTSTANDING_LAST on has_claim via district
  - [universal] LAST_TWO on has_claim via age_group
  - [universal] EVENNESS on days_enrolment_to_card via district
  - [universal] ATTRIBUTION on has_claim via district
  - [universal] OUTSTANDING_1 on claim_count via district
  - [universal] TOP_TWO on has_claim via entitlement_source
  - [universal] ATTRIBUTION on has_claim via bis_record_status

---


# Executive Summary

### Overall takeaway

The rankings start to change in a meaningful way at **gamma = 0.3**, and the shift is **gradual at first, then more noticeable by 0.5, and strongest by 0.8**. At 0.1, the top-15 are dominated by universal insights in every view. By 0.3, several actionable insights begin to break into the top ranks, but universal patterns still remain common. By 0.5, the balance has clearly shifted toward actionable insights in most views. By 0.8, the top-15 is mostly or entirely actionable in three of the four views, showing that the gamma setting is now strongly rewarding exception-driven patterns.

### Which views are most sensitive

**View 1** and **View 2** are the most sensitive to gamma. In view 1, the top-15 moves from **15 universal / 0 actionable** at 0.1 to **0 universal / 15 actionable** at 0.8. View 2 shows a similar but slightly less extreme shift, moving from **9 universal / 6 actionable** to **1 universal / 14 actionable**. These two views clearly respond strongly to the actionability penalty and become much more exception-focused as gamma rises.

**View 4** is also highly sensitive, with a steady move from universal to actionable insights, especially after 0.3. **View 3** is the least sensitive. Even at 0.8, it still keeps 2 universal insights in the top-15, and its change is more mixed. In practice, view 3 seems to contain several strong structural patterns that remain useful even when universal insights are penalised.

### What rises and what falls

Higher gamma promotes insights that describe **patterns that hold in most districts or divisions but break in a few places**. These are the kinds of findings that can guide operational follow-up, because they point to places worth checking. What gets pushed down are broad, stable patterns that apply everywhere. Those are still informative, but they are less helpful when the goal is to find local problems, anomalies, or targetable variations.

At high gamma, the system increasingly surfaces patterns involving **district-level exceptions, year-on-year trends, change points, and uneven behaviour across only some subgroups**. It demotes universal patterns such as broad seasonality, general ranking patterns, and global evenness relationships.

### Concrete examples that matter

One important actionable insight in view 1 is that **NORMAL discharge type has the highest amount paid in 74 of 75 districts, with Hamirpur behaving differently**. A programme officer should care because this suggests a near-system-wide rule with one clear exception. That exception could reflect local coding, care mix, or claims handling issues that deserve review.

A second example from view 2 is that **cards issued show a seasonal pattern in almost all districts, except Mahoba where the pattern differs**. This matters because card issuance is a frontline administrative process. If one district breaks the common seasonal cycle, it may indicate a local service bottleneck, campaign timing issue, or data quality problem.

A third example from view 4 is that **SECC households have the highest claim count in nearly all districts, except Lalitpur**. This is useful because SECC is a major entitlement group. A district that diverges from the norm may be missing eligible claims, facing enrolment problems, or behaving differently in access and utilisation.

### Recommended gamma

I would recommend **gamma = 0.5** as the best default, with **0.3 to 0.5** as a practical working range. At 0.3, the rankings begin to surface actionable insights without over-tilting away from stable patterns. At 0.5, the system gives a much better balance: it promotes useful exceptions, but still keeps some universal insights that provide context and guard against overreacting to outliers. I would avoid setting gamma straight to 0.8 unless the explicit goal is to prioritise investigation and operational triage over broad descriptive coverage.