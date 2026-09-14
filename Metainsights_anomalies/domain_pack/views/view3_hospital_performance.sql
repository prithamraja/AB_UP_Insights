-- ============================================================================
-- View 3 — Hospital Performance
-- ============================================================================
-- Grain: one row per (hospital x specialty offered). ANCHORED on
-- hm_specialty_offered and LEFT-joined to activity, so a hospital that offers a
-- specialty but treated zero cases still appears with cases_treated = 0 and
-- zero_claim_flag = 1 — the underutilisation signal an inner join would erase.
--
-- Specialty of a case = case -> preauth -> primary procedure line
-- (procedure_rank = 1) -> ref_hbp_procedure_master.specialty_code. The activity
-- join chain is deliberately NOT deduped (it mirrors the old pandas view, where
-- multiple preauths/claims/payments per case inflate the per-cell counts).
-- ============================================================================

WITH ppl_primary AS (
    SELECT preauth_id, hbp_procedure_code
    FROM stg_cm_preauth_procedure_line
    WHERE procedure_rank = 1
),

-- case -> preauth -> primary procedure -> specialty -> claim -> payment
hosp_spec_raw AS (
    SELECT
        c.hospital_id,
        ref.specialty_code,
        c.case_id,
        c.is_emergency,
        c.is_death,
        pr.status         AS preauth_status,
        cl.claim_status,
        cl.amount_claimed,
        cl.amount_approved,
        cl.settlement_tat_days,
        p.amount_paid
    FROM stg_cm_case AS c
    LEFT JOIN stg_cm_preauth_request AS pr  ON c.case_id = pr.case_id
    LEFT JOIN ppl_primary            AS ppl ON pr.preauth_id = ppl.preauth_id
    LEFT JOIN stg_ref_hbp_procedure_master AS ref ON ppl.hbp_procedure_code = ref.hbp_procedure_code
    LEFT JOIN stg_cm_claim           AS cl  ON c.case_id = cl.case_id
    LEFT JOIN stg_cm_payment         AS p   ON cl.claim_id = p.claim_id
),

hosp_spec_agg AS (
    SELECT
        hospital_id,
        specialty_code,
        count(case_id)                                                                AS cases_treated,
        sum(CASE WHEN preauth_status IN ('AUTO_APPROVED', 'APPROVED') THEN 1 ELSE 0 END) AS preauth_approved,
        sum(CASE WHEN preauth_status = 'REJECTED' THEN 1 ELSE 0 END)                  AS preauth_rejected,
        sum(CASE WHEN claim_status IN ('APPROVED', 'SETTLED') THEN 1 ELSE 0 END)      AS claims_approved,
        coalesce(sum(amount_claimed), 0)                                              AS amount_claimed,
        coalesce(sum(amount_approved), 0)                                             AS amount_approved,
        coalesce(sum(amount_paid), 0)                                                 AS amount_paid,
        avg(settlement_tat_days)                                                      AS avg_settlement_tat,
        sum(is_emergency)                                                             AS emergency_count,
        sum(is_death)                                                                 AS death_count
    FROM hosp_spec_raw
    GROUP BY hospital_id, specialty_code
),

hosp_staff AS (
    SELECT hospital_id,
           count(staff_id)       AS total_staff,
           avg(experience_years) AS avg_experience_years
    FROM stg_hm_staff
    GROUP BY hospital_id
),

hosp_license AS (
    SELECT hospital_id,
           count(hospital_license_id)                        AS total_licenses,
           sum(is_expired)                                   AS expired_licenses,
           sum(CASE WHEN is_expired = 0 THEN 1 ELSE 0 END)   AS active_licenses
    FROM stg_hm_license_certificate
    GROUP BY hospital_id
)

SELECT
    so.hospital_specialty_id                              AS hospital_specialty_id,
    so.hospital_id                                        AS hospital_id,
    so.specialty_code                                     AS specialty_code,
    so.specialty_name                                     AS specialty_name,
    CAST(so.admissions_prev_fy AS BIGINT)                 AS admissions_prev_fy,
    CAST(so.admissions_before_last_year AS BIGINT)        AS admissions_before_last_year,
    hosp.division_name                                    AS division,
    hosp.district_name                                    AS district,
    hosp.hospital_type                                    AS hospital_type,
    hosp.hospital_sub_type                                AS hospital_sub_type,
    hosp.accreditation_level                              AS accreditation_level,
    hosp.bed_size_bucket                                  AS bed_size_bucket,
    CAST(hosp.total_bed_strength AS BIGINT)               AS total_bed_strength,
    CAST(hosp.inpatient_beds AS BIGINT)                   AS inpatient_beds,
    hosp.has_fully_equipped_ot                            AS has_ot,
    hosp.has_icu_with_ac                                  AS has_icu,
    CAST(coalesce(a.cases_treated, 0) AS DOUBLE)          AS cases_treated,
    CAST(a.preauth_approved AS DOUBLE)                    AS preauth_approved,
    CAST(a.preauth_rejected AS DOUBLE)                    AS preauth_rejected,
    CAST(a.claims_approved AS DOUBLE)                     AS claims_approved,
    CAST(a.amount_claimed AS DOUBLE)                      AS amount_claimed,
    CAST(a.amount_approved AS DOUBLE)                     AS amount_approved,
    CAST(a.amount_paid AS DOUBLE)                         AS amount_paid,
    CAST(a.avg_settlement_tat AS DOUBLE)                  AS avg_settlement_tat,
    CAST(a.emergency_count AS DOUBLE)                     AS emergency_count,
    CAST(a.death_count AS DOUBLE)                         AS death_count,
    CAST(st.total_staff AS BIGINT)                        AS total_staff,
    CAST(st.avg_experience_years AS DOUBLE)               AS avg_experience_years,
    CAST(lic.total_licenses AS BIGINT)                    AS total_licenses,
    CAST(lic.expired_licenses AS BIGINT)                  AS expired_licenses,
    CAST(lic.active_licenses AS BIGINT)                   AS active_licenses,
    CAST(CASE WHEN coalesce(a.cases_treated, 0) = 0 THEN 1 ELSE 0 END AS BIGINT) AS zero_claim_flag,
    CAST(coalesce(a.cases_treated, 0) / nullif(hosp.total_bed_strength, 0) AS DOUBLE) AS cases_per_bed
FROM stg_hm_specialty_offered AS so
LEFT JOIN stg_hm_hospital AS hosp ON so.hospital_id = hosp.hospital_id
LEFT JOIN hosp_spec_agg   AS a    ON so.hospital_id = a.hospital_id AND so.specialty_code = a.specialty_code
LEFT JOIN hosp_staff      AS st   ON so.hospital_id = st.hospital_id
LEFT JOIN hosp_license    AS lic  ON so.hospital_id = lic.hospital_id;
