-- ============================================================================
-- View 1 — Claims Lifecycle   (grain: one row per case_id, ~22,500 rows)
-- ============================================================================
-- Full transactional journey from admission to payment, anchored on cm_case.
-- All joins are LEFT. Dedup rules:
--   * primary diagnosis only   (diagnosis_rank = 1)
--   * primary procedure line   (procedure_rank = 1)
--   * multiple claims per case -> keep the FIRST by submitted_at
--   * multiple preauths per case -> keep the LATEST by initiated_at
--   * payments aggregated per claim: SUM(amount_paid), modal payment_status
-- `division`/`district` are the beneficiary's HOME geography (bm_household);
-- `hospital_division`/`hospital_district` are the hospital's (native on cm_case).
-- ============================================================================

WITH diag_primary AS (
    SELECT case_id, icd_code, disease_category
    FROM stg_cm_case_diagnosis
    WHERE diagnosis_rank = 1
),

ppl_primary AS (
    SELECT preauth_id, hbp_procedure_code,
           base_amount, computed_final_amount, expected_payable_amount
    FROM stg_cm_preauth_procedure_line
    WHERE procedure_rank = 1
),

-- Multiple claims per case -> keep the first submitted.
claim_first AS (
    SELECT case_id, claim_id, claim_status,
           amount_claimed, amount_approved, settlement_tat_days, query_count
    FROM stg_cm_claim
    QUALIFY row_number() OVER (PARTITION BY case_id ORDER BY submitted_at) = 1
),

-- Multiple preauths per case (re-submissions after queries) -> keep the latest.
preauth_deduped AS (
    SELECT preauth_id, case_id, status AS preauth_status
    FROM stg_cm_preauth_request
    QUALIFY row_number() OVER (PARTITION BY case_id ORDER BY initiated_at DESC) = 1
),

-- Payments aggregated per claim: sum paid, modal status.
payment_agg AS (
    SELECT claim_id,
           sum(amount_paid)     AS amount_paid,
           mode(payment_status) AS payment_status
    FROM stg_cm_payment
    GROUP BY claim_id
)

SELECT
    c.case_id                                       AS case_id,
    h.home_division_name                            AS division,
    h.home_district_code                            AS district,
    c.hospital_division                             AS hospital_division,
    c.hospital_district                             AS hospital_district,
    hosp.hospital_type                              AS hospital_type,
    hosp.hospital_sub_type                          AS hospital_sub_type,
    ref.specialty_code                              AS specialty_code,
    ref.specialty_name                              AS specialty_name,
    ref.procedure_name                              AS procedure_name,
    diag.disease_category                           AS disease_category,
    diag.icd_code                                   AS icd_code,
    b.gender                                        AS gender,
    b.age_group                                     AS age_group,
    c.admission_type                                AS admission_type,
    c.discharge_type                                AS discharge_type,
    c.is_portability                                AS is_portability,
    cl.claim_status                                 AS claim_status,
    pa.preauth_status                               AS preauth_status,
    pay.payment_status                              AS payment_status,
    hosp.accreditation_level                        AS accreditation_level,
    hosp.bed_size_bucket                            AS bed_size_bucket,
    c.admission_month                               AS admission_month,
    c.admission_quarter                             AS admission_quarter,
    c.admission_year                                AS admission_year,
    CAST(c.length_of_stay AS DOUBLE)                AS length_of_stay,
    CAST(c.is_emergency AS BIGINT)                  AS is_emergency,
    CAST(c.is_death AS BIGINT)                      AS is_death,
    CAST(c.is_lama_dama AS BIGINT)                  AS is_lama_dama,
    CAST(ppl.base_amount AS DOUBLE)                 AS base_amount,
    CAST(ppl.computed_final_amount AS DOUBLE)       AS computed_final_amount,
    CAST(ppl.expected_payable_amount AS DOUBLE)     AS expected_payable_amount,
    CAST(cl.amount_claimed AS DOUBLE)               AS amount_claimed,
    CAST(cl.amount_approved AS DOUBLE)              AS amount_approved,
    CAST(pay.amount_paid AS DOUBLE)                 AS amount_paid,
    CAST(cl.settlement_tat_days AS DOUBLE)          AS settlement_tat_days,
    CAST(cl.query_count AS BIGINT)                  AS query_count,
    CAST(1 AS BIGINT)                               AS case_count
FROM stg_cm_case                 AS c
LEFT JOIN stg_bm_beneficiary     AS b    ON c.beneficiary_id = b.beneficiary_id
LEFT JOIN stg_bm_household       AS h    ON b.household_id     = h.household_id
LEFT JOIN stg_hm_hospital        AS hosp ON c.hospital_id      = hosp.hospital_id
LEFT JOIN diag_primary           AS diag ON c.case_id          = diag.case_id
LEFT JOIN preauth_deduped        AS pa   ON c.case_id          = pa.case_id
LEFT JOIN ppl_primary            AS ppl  ON pa.preauth_id      = ppl.preauth_id
LEFT JOIN stg_ref_hbp_procedure_master AS ref ON ppl.hbp_procedure_code = ref.hbp_procedure_code
LEFT JOIN claim_first            AS cl   ON c.case_id          = cl.case_id
LEFT JOIN payment_agg            AS pay  ON cl.claim_id        = pay.claim_id;
