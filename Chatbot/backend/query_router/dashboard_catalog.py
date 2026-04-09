"""
36 Tier-1 dashboard queries.
Each entry: question (natural language) + sql (PostgreSQL-compatible, no parameters).
"""

DASHBOARD_CATALOG: dict[str, dict] = {

    # ── Enrollment & Coverage (D01-D08) ──────────────────────────────────────

    "D01": {
        "question": "How many households and beneficiaries are enrolled in UP?",
        "sql": """
SELECT
    COUNT(DISTINCT h.household_id)                                          AS total_households,
    COUNT(DISTINCT b.beneficiary_id)                                        AS total_beneficiaries,
    COUNT(DISTINCT CASE WHEN c.card_status = 'ACTIVE' THEN c.card_id END)  AS active_cards
FROM bm_household h
LEFT JOIN bm_beneficiary b ON h.household_id = b.household_id
LEFT JOIN bm_card c        ON b.beneficiary_id = c.beneficiary_id
""",
    },

    "D02": {
        "question": "What is the district-wise enrollment summary?",
        "sql": """
SELECT
    h.home_district_code                                                     AS district_name,
    h.home_division_name                                                     AS division_name,
    COUNT(DISTINCT h.household_id)                                           AS households,
    COUNT(DISTINCT b.beneficiary_id)                                         AS beneficiaries,
    COUNT(DISTINCT CASE WHEN c.card_status = 'ACTIVE' THEN c.card_id END)   AS active_cards
FROM bm_household h
LEFT JOIN bm_beneficiary b ON h.household_id   = b.household_id
LEFT JOIN bm_card c        ON b.beneficiary_id = c.beneficiary_id
GROUP BY h.home_district_code, h.home_division_name
ORDER BY beneficiaries DESC
""",
    },

    "D03": {
        "question": "What is the division-wise enrollment summary?",
        "sql": """
SELECT
    h.home_division_name             AS division_name,
    COUNT(DISTINCT h.household_id)   AS households,
    COUNT(DISTINCT b.beneficiary_id) AS beneficiaries
FROM bm_household h
LEFT JOIN bm_beneficiary b ON h.household_id = b.household_id
GROUP BY h.home_division_name
ORDER BY beneficiaries DESC
""",
    },

    "D04": {
        "question": "What is the gender breakdown of enrolled beneficiaries?",
        "sql": """
SELECT
    gender,
    COUNT(*) AS count,
    ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER(), 2) AS pct
FROM bm_beneficiary
GROUP BY gender
ORDER BY count DESC
""",
    },

    "D05": {
        "question": "What is the age distribution of beneficiaries?",
        "sql": """
WITH ages AS (
    SELECT
        COALESCE(yob, EXTRACT(YEAR FROM dob)::INTEGER) AS birth_year
    FROM bm_beneficiary
    WHERE COALESCE(yob, EXTRACT(YEAR FROM dob)::INTEGER) IS NOT NULL
),
bucketed AS (
    SELECT
        CASE
            WHEN (EXTRACT(YEAR FROM CURRENT_DATE)::INTEGER - birth_year) < 18 THEN '0-17'
            WHEN (EXTRACT(YEAR FROM CURRENT_DATE)::INTEGER - birth_year) < 46 THEN '18-45'
            WHEN (EXTRACT(YEAR FROM CURRENT_DATE)::INTEGER - birth_year) < 66 THEN '46-65'
            ELSE '65+'
        END AS age_bucket
    FROM ages
)
SELECT
    age_bucket,
    COUNT(*) AS count,
    ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER(), 2) AS pct
FROM bucketed
GROUP BY age_bucket
ORDER BY age_bucket
""",
    },

    "D06": {
        "question": "What is the enrollment source breakdown?",
        "sql": """
SELECT
    entitlement_source,
    COUNT(*) AS households,
    ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER(), 2) AS pct
FROM bm_household
GROUP BY entitlement_source
ORDER BY households DESC
""",
    },

    "D07": {
        "question": "What is the BIS record status distribution?",
        "sql": """
SELECT
    bis_record_status,
    COUNT(*) AS count,
    ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER(), 2) AS pct
FROM bm_beneficiary
GROUP BY bis_record_status
ORDER BY count DESC
""",
    },

    "D08": {
        "question": "How many beneficiaries have mobile numbers on file?",
        "sql": """
SELECT
    COUNT(*)        AS total_beneficiaries,
    COUNT(mobile)   AS with_mobile,
    ROUND(COUNT(mobile) * 100.0 / COUNT(*), 2) AS mobile_pct
FROM bm_beneficiary
""",
    },

    # ── Hospital Network (D09-D15) ────────────────────────────────────────────

    "D09": {
        "question": "How many empanelled hospitals are there, public vs private?",
        "sql": """
SELECT
    hospital_type,
    COUNT(*) AS count,
    ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER(), 2) AS pct
FROM hm_hospital
GROUP BY hospital_type
ORDER BY count DESC
""",
    },

    "D10": {
        "question": "What is the district-wise hospital count?",
        "sql": """
SELECT
    district_name,
    division_name,
    COUNT(*) AS hospital_count
FROM hm_hospital
GROUP BY district_name, division_name
ORDER BY hospital_count DESC
""",
    },

    "D11": {
        "question": "Which districts have the highest hospital density?",
        "sql": """
SELECT
    h.district_name,
    COUNT(DISTINCT h.hospital_id)    AS hospital_count,
    COUNT(DISTINCT b.beneficiary_id) AS beneficiary_count,
    ROUND(
        COUNT(DISTINCT h.hospital_id) * 100000.0
        / NULLIF(COUNT(DISTINCT b.beneficiary_id), 0),
        2
    ) AS hospitals_per_lakh
FROM hm_hospital h
LEFT JOIN bm_household hh  ON h.district_name = hh.home_district_code
LEFT JOIN bm_beneficiary b ON hh.household_id = b.household_id
GROUP BY h.district_name
HAVING COUNT(DISTINCT b.beneficiary_id) > 0
ORDER BY hospitals_per_lakh DESC

""",
    },

    "D12": {
        "question": "What is the specialty coverage across hospitals?",
        "sql": """
SELECT
    specialty_code,
    specialty_name,
    COUNT(DISTINCT hospital_id) AS hospital_count,
    SUM(admissions_prev_fy)     AS admissions_prev_fy
FROM hm_specialty_offered
GROUP BY specialty_code, specialty_name
ORDER BY hospital_count DESC
""",
    },

    "D13": {
        "question": "How many hospitals have expired licenses?",
        "sql": """
SELECT
    COUNT(DISTINCT hospital_id) AS total_hospitals_with_licenses,
    COUNT(DISTINCT CASE WHEN expiry_date < CURRENT_DATE THEN hospital_id END) AS expired,
    ROUND(
        COUNT(DISTINCT CASE WHEN expiry_date < CURRENT_DATE THEN hospital_id END)
        * 100.0 / NULLIF(COUNT(DISTINCT hospital_id), 0),
        2
    ) AS pct_expired
FROM hm_license_certificate
""",
    },

    "D14": {
        "question": "What is the bed capacity summary by hospital type?",
        "sql": """
SELECT
    hospital_type,
    hospital_sub_type,
    COUNT(*)                              AS hospital_count,
    SUM(total_bed_strength)               AS total_beds,
    SUM(inpatient_beds)                   AS inpatient_beds,
    ROUND(AVG(total_bed_strength), 0)     AS avg_beds_per_hospital
FROM hm_hospital
GROUP BY hospital_type, hospital_sub_type
ORDER BY total_beds DESC
""",
    },

    "D15": {
        "question": "What is the staff-to-bed ratio across hospital types?",
        "sql": """
SELECT
    h.hospital_type,
    h.hospital_sub_type,
    COUNT(DISTINCT h.hospital_id)   AS hospitals,
    SUM(h.total_bed_strength)       AS total_beds,
    COUNT(s.staff_id)               AS total_staff,
    ROUND(
        COUNT(s.staff_id) * 1.0
        / NULLIF(SUM(h.total_bed_strength), 0),
        3
    ) AS staff_per_bed
FROM hm_hospital h
LEFT JOIN hm_staff s ON h.hospital_id = s.hospital_id
GROUP BY h.hospital_type, h.hospital_sub_type
ORDER BY staff_per_bed DESC
""",
    },

    # ── Claims & Utilization (D16-D27) ────────────────────────────────────────

    "D16": {
        "question": "What is the total number of cases and total claim amount?",
        "sql": """
SELECT
    COUNT(DISTINCT c.case_id)            AS total_cases,
    COUNT(DISTINCT cl.claim_id)          AS total_claims,
    ROUND(SUM(cl.amount_claimed),  2)    AS total_amount_claimed,
    ROUND(SUM(cl.amount_approved), 2)    AS total_amount_approved
FROM cm_case c
LEFT JOIN cm_claim cl ON c.case_id = cl.case_id
""",
    },

    "D17": {
        "question": "What is the monthly case volume trend?",
        "sql": """
SELECT
    date_trunc('month', admission_datetime)::DATE  AS month,
    COUNT(*)                                        AS case_count
FROM cm_case
WHERE admission_datetime >= '2022-01-01'
  AND admission_datetime <  '2025-01-01'
GROUP BY 1
ORDER BY 1
""",
    },

    "D18": {
        "question": "What is the district-wise claims summary?",
        "sql": """
SELECT
    c.hospital_district                      AS district_name,
    c.hospital_division                      AS division_name,
    COUNT(DISTINCT c.case_id)                AS total_cases,
    COUNT(DISTINCT cl.claim_id)              AS total_claims,
    ROUND(SUM(cl.amount_claimed),  2)        AS amount_claimed,
    ROUND(SUM(cl.amount_approved), 2)        AS amount_approved
FROM cm_case c
LEFT JOIN cm_claim cl ON c.case_id = cl.case_id
GROUP BY c.hospital_district, c.hospital_division
ORDER BY total_cases DESC
""",
    },

    "D19": {
        "question": "What is the division-wise claims summary?",
        "sql": """
SELECT
    c.hospital_division                      AS division_name,
    COUNT(DISTINCT c.case_id)                AS total_cases,
    COUNT(DISTINCT cl.claim_id)              AS total_claims,
    ROUND(SUM(cl.amount_claimed),  2)        AS amount_claimed,
    ROUND(SUM(cl.amount_approved), 2)        AS amount_approved
FROM cm_case c
LEFT JOIN cm_claim cl ON c.case_id = cl.case_id
GROUP BY c.hospital_division
ORDER BY total_cases DESC
""",
    },

    "D20": {
        "question": "What is the claim status distribution?",
        "sql": """
SELECT
    claim_status,
    COUNT(*) AS count,
    ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER(), 2) AS pct,
    ROUND(SUM(amount_claimed), 2) AS total_claimed
FROM cm_claim
GROUP BY claim_status
ORDER BY count DESC
""",
    },

    "D21": {
        "question": "What is the specialty-wise utilization?",
        "sql": """
SELECT
    r.specialty_code,
    r.specialty_name,
    COUNT(DISTINCT pl.preauth_id)            AS preauth_count,
    ROUND(SUM(pl.computed_final_amount), 2)  AS total_amount
FROM cm_preauth_procedure_line pl
JOIN ref_hbp_procedure_master r ON pl.hbp_procedure_code = r.hbp_procedure_code
GROUP BY r.specialty_code, r.specialty_name
ORDER BY preauth_count DESC
""",
    },

    "D22": {
        "question": "What are the top procedures by volume?",
        "sql": """
SELECT
    pl.hbp_procedure_code,
    p.procedure_name,
    p.specialty_code,
    COUNT(*)                                 AS usage_count,
    ROUND(SUM(pl.computed_final_amount), 2)  AS total_amount
FROM cm_preauth_procedure_line pl
JOIN ref_hbp_procedure_master p ON pl.hbp_procedure_code = p.hbp_procedure_code
GROUP BY pl.hbp_procedure_code, p.procedure_name, p.specialty_code
ORDER BY usage_count DESC

""",
    },

    "D23": {
        "question": "What are the top diagnoses by volume?",
        "sql": """
SELECT
    icd_code,
    diagnosis_text,
    COUNT(*) AS count
FROM cm_case_diagnosis
WHERE diagnosis_type = 'PRIMARY'
GROUP BY icd_code, diagnosis_text
ORDER BY count DESC

""",
    },

    "D24": {
        "question": "What is the disease category breakdown?",
        "sql": """
SELECT
    diagnosis_category,
    COUNT(*) AS case_count,
    ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER(), 2) AS pct
FROM cm_case_diagnosis
WHERE diagnosis_type = 'PRIMARY'
GROUP BY 1
ORDER BY case_count DESC
""",
    },

    "D25": {
        "question": "What is the public vs private hospital utilization split?",
        "sql": """
SELECT
    h.hospital_type,
    COUNT(DISTINCT c.case_id)                                              AS total_cases,
    ROUND(COUNT(DISTINCT c.case_id) * 100.0
          / SUM(COUNT(DISTINCT c.case_id)) OVER(), 2)                     AS pct_cases,
    ROUND(SUM(cl.amount_claimed), 2)                                       AS total_claimed
FROM cm_case c
JOIN  hm_hospital h  ON c.hospital_id = h.hospital_id
LEFT JOIN cm_claim cl ON c.case_id    = cl.case_id
GROUP BY h.hospital_type
ORDER BY total_cases DESC
""",
    },

    "D26": {
        "question": "What is the discharge type distribution?",
        "sql": """
SELECT
    discharge_type,
    COUNT(*) AS count,
    ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER(), 2) AS pct
FROM cm_case
WHERE discharge_type IS NOT NULL
GROUP BY discharge_type
ORDER BY count DESC
""",
    },

    "D27": {
        "question": "What is the seasonal admission pattern?",
        "sql": """
SELECT
    EXTRACT(MONTH FROM admission_datetime)::INTEGER  AS month,
    ROUND(COUNT(*) * 1.0 / 3, 1)                    AS avg_monthly_cases
FROM cm_case
WHERE admission_datetime >= '2022-01-01'
  AND admission_datetime <  '2025-01-01'
GROUP BY 1
ORDER BY 1
""",
    },

    # ── Portability (D28-D30) ─────────────────────────────────────────────────

    "D28": {
        "question": "How many portability cases are there and to which states?",
        "sql": """
SELECT
    hospital_state_code  AS destination_state,
    COUNT(*)             AS case_count,
    ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER(), 2) AS pct
FROM cm_case
WHERE is_portability = true
GROUP BY hospital_state_code
ORDER BY case_count DESC
""",
    },

    "D29": {
        "question": "What is the portability claim amount vs intrastate?",
        "sql": """
SELECT
    is_portability_claim,
    COUNT(*)                             AS claim_count,
    ROUND(SUM(amount_claimed),  2)       AS total_claimed,
    ROUND(AVG(amount_claimed),  2)       AS avg_claimed,
    ROUND(SUM(amount_approved), 2)       AS total_approved
FROM cm_claim
GROUP BY is_portability_claim
ORDER BY is_portability_claim
""",
    },

    "D30": {
        "question": "What is the portability trend by month?",
        "sql": """
SELECT
    date_trunc('month', admission_datetime)::DATE  AS month,
    COUNT(*)                                        AS portability_cases
FROM cm_case
WHERE is_portability = true
GROUP BY 1
ORDER BY 1
""",
    },

    # ── Financial & TAT (D31-D36) ─────────────────────────────────────────────

    "D31": {
        "question": "What is the overall settlement TAT distribution?",
        "sql": """
SELECT
    ROUND(AVG(settlement_tat_days), 1)                                          AS avg_tat,
    ROUND(PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY settlement_tat_days)::numeric, 1) AS median_tat,
    ROUND(PERCENTILE_CONT(0.65) WITHIN GROUP (ORDER BY settlement_tat_days)::numeric, 1) AS p65_tat,
    ROUND(PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY settlement_tat_days)::numeric, 1) AS p95_tat,
    MAX(settlement_tat_days)                                                     AS max_tat
FROM cm_claim
WHERE settlement_tat_days IS NOT NULL
""",
    },

    "D32": {
        "question": "What is the settlement TAT portability vs intrastate?",
        "sql": """
SELECT
    is_portability_claim,
    ROUND(PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY settlement_tat_days)::numeric, 1) AS median_tat,
    ROUND(PERCENTILE_CONT(0.65) WITHIN GROUP (ORDER BY settlement_tat_days)::numeric, 1) AS p65_tat,
    ROUND(PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY settlement_tat_days)::numeric, 1) AS p95_tat,
    MAX(settlement_tat_days)                                                     AS max_tat
FROM cm_claim
WHERE settlement_tat_days IS NOT NULL
GROUP BY is_portability_claim
ORDER BY is_portability_claim
""",
    },

    "D33": {
        "question": "What is the district-wise average settlement TAT?",
        "sql": """
SELECT
    c.hospital_district                  AS district_name,
    ROUND(AVG(cl.settlement_tat_days), 1) AS avg_tat_days,
    ROUND(PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY cl.settlement_tat_days)::numeric, 1) AS median_tat,
    COUNT(cl.claim_id)                    AS settled_claims
FROM cm_claim cl
JOIN cm_case c ON cl.case_id = c.case_id
WHERE cl.settlement_tat_days IS NOT NULL
GROUP BY c.hospital_district
ORDER BY avg_tat_days DESC
""",
    },

    "D34": {
        "question": "What is the monthly rejection rate trend?",
        "sql": """
SELECT
    date_trunc('month', submitted_at)::DATE                                   AS month,
    COUNT(*)                                                                   AS total_claims,
    COUNT(CASE WHEN claim_status = 'REJECTED' THEN 1 END)                     AS rejected_claims,
    ROUND(
        COUNT(CASE WHEN claim_status = 'REJECTED' THEN 1 END)
        * 100.0 / NULLIF(COUNT(*), 0),
        2
    )                                                                          AS rejection_rate_pct
FROM cm_claim
GROUP BY 1
ORDER BY 1
""",
    },

    "D35": {
        "question": "What is the total amount paid, pending, and rejected?",
        "sql": """
SELECT
    ROUND(SUM(CASE WHEN claim_status = 'SETTLED'
                   THEN amount_approved ELSE 0 END), 2)                          AS total_settled,
    ROUND(SUM(CASE WHEN claim_status IN ('APPROVED','QUERY_RAISED','PENDING')
                   THEN amount_approved ELSE 0 END), 2)                          AS total_pending,
    ROUND(SUM(CASE WHEN claim_status = 'REJECTED'
                   THEN amount_claimed ELSE 0 END), 2)                           AS total_rejected,
    ROUND(SUM(COALESCE(amount_claimed, 0)), 2)                                   AS grand_total_claimed
FROM cm_claim
""",
    },

    "D36": {
        "question": "What are the top hospitals by claim amount?",
        "sql": """
SELECT
    h.hospital_name,
    h.district_name,
    h.hospital_type,
    COUNT(DISTINCT cl.claim_id)          AS claim_count,
    ROUND(SUM(cl.amount_claimed),  2)    AS total_claimed,
    ROUND(SUM(cl.amount_approved), 2)    AS total_approved
FROM cm_claim cl
JOIN cm_case     c ON cl.case_id    = c.case_id
JOIN hm_hospital h ON c.hospital_id = h.hospital_id
GROUP BY h.hospital_id, h.hospital_name, h.district_name, h.hospital_type
ORDER BY total_claimed DESC

""",
    },

    # ── Enrolment Quality & Card Analytics (D37-D45) ──────────────────────────

    "D37": {
        "question": "What percentage of enrolled beneficiaries have never utilized the scheme?",
        "sql": """
SELECT
    COUNT(DISTINCT b.beneficiary_id)                                              AS total_enrolled,
    COUNT(DISTINCT CASE WHEN c.case_id IS NULL THEN b.beneficiary_id END)        AS never_utilized,
    ROUND(
        COUNT(DISTINCT CASE WHEN c.case_id IS NULL THEN b.beneficiary_id END)
        * 100.0 / NULLIF(COUNT(DISTINCT b.beneficiary_id), 0),
        2
    )                                                                              AS never_utilized_pct
FROM bm_beneficiary b
LEFT JOIN cm_case c ON b.beneficiary_id = c.beneficiary_id
""",
    },

    "D38": {
        "question": "What is the average time from beneficiary enrolment to card issuance across districts?",
        "sql": """
SELECT
    h.home_district_code                                                       AS district_name,
    h.home_division_name                                                       AS division_name,
    COUNT(DISTINCT er.beneficiary_id)                                          AS enrolments_with_card,
    ROUND(AVG(DATE_DIFF('day', er.submitted_at::DATE, cd.issued_at::DATE)), 1) AS avg_days_to_card,
    ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (
        ORDER BY DATE_DIFF('day', er.submitted_at::DATE, cd.issued_at::DATE)
    ), 1)                                                                       AS median_days_to_card
FROM bm_enrolment_request er
JOIN bm_card cd        ON er.beneficiary_id = cd.beneficiary_id
JOIN bm_beneficiary b  ON er.beneficiary_id = b.beneficiary_id
JOIN bm_household h    ON b.household_id    = h.household_id
WHERE er.submitted_at IS NOT NULL
  AND cd.issued_at    IS NOT NULL
  AND cd.issued_at::DATE >= er.submitted_at::DATE
GROUP BY h.home_district_code, h.home_division_name
ORDER BY avg_days_to_card DESC
""",
    },

    "D39": {
        "question": "What is the enrolment request rejection rate and top rejection reasons?",
        "sql": """
WITH overall AS (
    SELECT
        COUNT(*)                                                              AS total_requests,
        COUNT(CASE WHEN status = 'REJECTED' THEN 1 END)                      AS rejected_count,
        ROUND(
            COUNT(CASE WHEN status = 'REJECTED' THEN 1 END) * 100.0
            / NULLIF(COUNT(*), 0),
            2
        )                                                                     AS rejection_rate_pct
    FROM bm_enrolment_request
),
reasons AS (
    SELECT
        COALESCE(rejection_reason, 'UNSPECIFIED') AS rejection_reason,
        COUNT(*)                                   AS count,
        ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER(), 2) AS pct
    FROM bm_enrolment_request
    WHERE status = 'REJECTED'
    GROUP BY rejection_reason
    ORDER BY count DESC
    LIMIT 15
)
SELECT
    o.total_requests,
    o.rejected_count,
    o.rejection_rate_pct,
    r.rejection_reason,
    r.count            AS reason_count,
    r.pct              AS reason_pct
FROM overall o
CROSS JOIN reasons r
ORDER BY r.count DESC
""",
    },

    "D40": {
        "question": "What is the breakdown of authentication modes used for enrolment?",
        "sql": """
SELECT
    auth_mode,
    COUNT(*)                                                        AS count,
    ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER(), 2)             AS pct
FROM bm_enrolment_request
GROUP BY auth_mode
ORDER BY count DESC
""",
    },

    "D41": {
        "question": "What percentage of beneficiaries have incomplete profiles (missing DOB or mobile or photo)?",
        "sql": """
SELECT
    COUNT(*)                                                                       AS total_beneficiaries,
    COUNT(CASE WHEN yob IS NULL AND dob IS NULL THEN 1 END)                       AS missing_dob_count,
    ROUND(COUNT(CASE WHEN yob IS NULL AND dob IS NULL THEN 1 END)
          * 100.0 / NULLIF(COUNT(*), 0), 2)                                       AS missing_dob_pct,
    COUNT(CASE WHEN mobile IS NULL THEN 1 END)                                    AS missing_mobile_count,
    ROUND(COUNT(CASE WHEN mobile IS NULL THEN 1 END)
          * 100.0 / NULLIF(COUNT(*), 0), 2)                                       AS missing_mobile_pct,
    COUNT(CASE WHEN photo_uri IS NULL THEN 1 END)                                 AS missing_photo_count,
    ROUND(COUNT(CASE WHEN photo_uri IS NULL THEN 1 END)
          * 100.0 / NULLIF(COUNT(*), 0), 2)                                       AS missing_photo_pct,
    COUNT(CASE WHEN (yob IS NULL AND dob IS NULL)
                 OR mobile IS NULL
                 OR photo_uri IS NULL THEN 1 END)                                  AS any_field_missing_count,
    ROUND(COUNT(CASE WHEN (yob IS NULL AND dob IS NULL)
                        OR mobile IS NULL
                        OR photo_uri IS NULL THEN 1 END)
          * 100.0 / NULLIF(COUNT(*), 0), 2)                                       AS any_field_missing_pct
FROM bm_beneficiary
""",
    },

    "D42": {
        "question": "How many duplicate beneficiary records exist and what is the district-wise distribution?",
        "sql": """
SELECT
    h.home_district_code                                                AS district_name,
    h.home_division_name                                                AS division_name,
    COUNT(DISTINCT b.beneficiary_id)                                    AS duplicate_count,
    ROUND(COUNT(DISTINCT b.beneficiary_id) * 100.0
          / SUM(COUNT(DISTINCT b.beneficiary_id)) OVER(), 2)           AS pct_of_all_dupes
FROM bm_beneficiary b
JOIN bm_household h ON b.household_id = h.household_id
WHERE b.is_duplicate = TRUE
GROUP BY h.home_district_code, h.home_division_name
ORDER BY duplicate_count DESC
LIMIT 50
""",
    },

    "D43": {
        "question": "What is the card status distribution (active vs inactive vs disabled)?",
        "sql": """
SELECT
    card_status,
    COUNT(*)                                                        AS count,
    ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER(), 2)             AS pct
FROM bm_card
GROUP BY card_status
ORDER BY count DESC
""",
    },

    "D44": {
        "question": "What is the month-over-month new enrolment trend from 2022 to 2026?",
        "sql": """
SELECT
    date_trunc('month', submitted_at)::DATE                         AS enrolment_month,
    COUNT(*)                                                         AS new_enrolments,
    COUNT(CASE WHEN status = 'ISA_APPROVED' THEN 1 END)             AS isa_approved,
    COUNT(CASE WHEN status = 'AUTO_APPROVED' THEN 1 END)            AS auto_approved,
    COUNT(CASE WHEN status = 'REJECTED' THEN 1 END)                 AS rejected
FROM bm_enrolment_request
WHERE submitted_at >= '2022-01-01'
  AND submitted_at <  '2026-12-31'
GROUP BY 1
ORDER BY 1
""",
    },

    "D45": {
        "question": "What is the beneficiary-to-hospital ratio across districts?",
        "sql": """
WITH bene_dist AS (
    SELECT
        h.home_district_code                        AS district_name,
        COUNT(DISTINCT b.beneficiary_id)            AS beneficiary_count
    FROM bm_household h
    JOIN bm_beneficiary b ON h.household_id = b.household_id
    GROUP BY h.home_district_code
),
hosp_dist AS (
    SELECT
        district_name,
        COUNT(DISTINCT hospital_id)                 AS hospital_count
    FROM hm_hospital
    GROUP BY district_name
)
SELECT
    bd.district_name,
    bd.beneficiary_count,
    COALESCE(hd.hospital_count, 0)                 AS hospital_count,
    ROUND(bd.beneficiary_count * 1.0
          / NULLIF(hd.hospital_count, 0), 1)       AS beneficiaries_per_hospital
FROM bene_dist bd
LEFT JOIN hosp_dist hd ON bd.district_name = hd.district_name
ORDER BY beneficiaries_per_hospital DESC
LIMIT 50
""",
    },

    # ── Hospital Quality & Infrastructure (D46-D53) ───────────────────────────

    "D46": {
        "question": "Which hospitals are performing procedures in specialties they do not officially offer?",
        "sql": """
WITH procedure_specialties AS (
    SELECT
        ca.hospital_id,
        pm.specialty_code,
        COUNT(*)              AS procedure_count
    FROM cm_preauth_procedure_line pl
    JOIN cm_preauth_request pr  ON pl.preauth_id        = pr.preauth_id
    JOIN cm_case ca             ON pr.case_id           = ca.case_id
    JOIN ref_hbp_procedure_master pm ON pl.hbp_procedure_code = pm.hbp_procedure_code
    GROUP BY ca.hospital_id, pm.specialty_code
),
offered_specialties AS (
    SELECT hospital_id, specialty_code
    FROM hm_specialty_offered
)
SELECT
    h.hospital_name,
    h.district_name,
    h.hospital_type,
    ps.specialty_code          AS unauthorized_specialty_code,
    ps.procedure_count
FROM procedure_specialties ps
JOIN hm_hospital h ON ps.hospital_id = h.hospital_id
WHERE NOT EXISTS (
    SELECT 1
    FROM offered_specialties os
    WHERE os.hospital_id    = ps.hospital_id
      AND os.specialty_code = ps.specialty_code
)
ORDER BY ps.procedure_count DESC
LIMIT 50
""",
    },

    "D47": {
        "question": "Which hospitals have a case volume that exceeds their bed capacity (cases per bed per month)?",
        "sql": """
WITH monthly_cases AS (
    SELECT
        hospital_id,
        date_trunc('month', admission_datetime)::DATE AS month,
        COUNT(*)                                       AS monthly_case_count
    FROM cm_case
    WHERE admission_datetime IS NOT NULL
    GROUP BY hospital_id, date_trunc('month', admission_datetime)::DATE
),
avg_monthly AS (
    SELECT
        hospital_id,
        ROUND(AVG(monthly_case_count), 2) AS avg_monthly_cases
    FROM monthly_cases
    GROUP BY hospital_id
)
SELECT
    h.hospital_name,
    h.district_name,
    h.hospital_type,
    h.total_bed_strength,
    am.avg_monthly_cases,
    ROUND(am.avg_monthly_cases / NULLIF(h.total_bed_strength, 0), 3) AS cases_per_bed_per_month
FROM avg_monthly am
JOIN hm_hospital h ON am.hospital_id = h.hospital_id
WHERE h.total_bed_strength > 0
  AND am.avg_monthly_cases / NULLIF(h.total_bed_strength, 0) > 1.0
ORDER BY cases_per_bed_per_month DESC
LIMIT 50
""",
    },

    "D48": {
        "question": "What is the hospital accreditation status distribution (NABH/NABL/JCI vs none)?",
        "sql": """
SELECT
    COALESCE(accreditation_board, 'NONE')                          AS accreditation_board,
    COUNT(*)                                                        AS hospital_count,
    ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER(), 2)             AS pct
FROM hm_hospital
GROUP BY COALESCE(accreditation_board, 'NONE')
ORDER BY hospital_count DESC
""",
    },

    "D49": {
        "question": "Does hospital accreditation correlate with claim approval rates?",
        "sql": """
SELECT
    CASE
        WHEN h.accreditation_board IS NOT NULL THEN 'Accredited'
        ELSE 'Not Accredited'
    END                                                                    AS accreditation_status,
    COUNT(DISTINCT h.hospital_id)                                          AS hospital_count,
    COUNT(cl.claim_id)                                                     AS total_claims,
    ROUND(AVG(
        cl.amount_approved / NULLIF(cl.amount_claimed, 0) * 100.0
    ), 1)                                                                   AS avg_approval_rate_pct
FROM hm_hospital h
JOIN cm_case c   ON h.hospital_id = c.hospital_id
JOIN cm_claim cl ON c.case_id     = cl.case_id
WHERE cl.amount_claimed > 0
GROUP BY 1
ORDER BY avg_approval_rate_pct DESC
""",
    },

    "D50": {
        "question": "What percentage of hospitals lack critical infrastructure (ICU, OT, HDU)?",
        "sql": """
SELECT
    COUNT(*)                                                                            AS total_hospitals,
    COUNT(CASE WHEN has_icu_with_ac = FALSE THEN 1 END)                                AS no_icu,
    ROUND(COUNT(CASE WHEN has_icu_with_ac = FALSE THEN 1 END) * 100.0
          / NULLIF(COUNT(*), 0), 2)                                                    AS pct_no_icu,
    COUNT(CASE WHEN has_fully_equipped_ot = FALSE THEN 1 END)                          AS no_ot,
    ROUND(COUNT(CASE WHEN has_fully_equipped_ot = FALSE THEN 1 END) * 100.0
          / NULLIF(COUNT(*), 0), 2)                                                    AS pct_no_ot,
    COUNT(CASE WHEN has_hdu = FALSE THEN 1 END)                                        AS no_hdu,
    ROUND(COUNT(CASE WHEN has_hdu = FALSE THEN 1 END) * 100.0
          / NULLIF(COUNT(*), 0), 2)                                                    AS pct_no_hdu,
    COUNT(CASE WHEN has_icu_with_ac = FALSE
                AND has_fully_equipped_ot = FALSE
                AND has_hdu = FALSE THEN 1 END)                                         AS missing_all_three,
    ROUND(COUNT(CASE WHEN has_icu_with_ac = FALSE
                       AND has_fully_equipped_ot = FALSE
                       AND has_hdu = FALSE THEN 1 END) * 100.0
          / NULLIF(COUNT(*), 0), 2)                                                    AS pct_missing_all_three
FROM hm_hospital
""",
    },

    "D51": {
        "question": "Which hospitals have been delisted but still have recent cases?",
        "sql": """
SELECT
    h.hospital_name,
    h.district_name,
    h.hospital_type,
    COUNT(DISTINCT c.case_id)                                         AS recent_case_count,
    MAX(c.admission_datetime)::DATE                                   AS latest_admission
FROM hm_hospital h
JOIN cm_case c ON h.hospital_id = c.hospital_id
WHERE h.delisted_from_gov_schemes = TRUE
  AND c.admission_datetime >= (CURRENT_DATE - INTERVAL '12 months')
GROUP BY h.hospital_id, h.hospital_name, h.district_name, h.hospital_type
ORDER BY recent_case_count DESC
LIMIT 20
""",
    },

    "D52": {
        "question": "What is the hospital-wise average length of stay compared to state average by procedure?",
        "sql": """
WITH case_los AS (
    SELECT
        ca.hospital_id,
        pm.hbp_procedure_code,
        pm.procedure_name,
        DATE_DIFF('day', ca.admission_datetime::DATE, ca.discharge_datetime::DATE) AS los_days
    FROM cm_case ca
    JOIN cm_preauth_request pr  ON ca.case_id           = pr.case_id
    JOIN cm_preauth_procedure_line pl ON pr.preauth_id  = pl.preauth_id
    JOIN ref_hbp_procedure_master pm  ON pl.hbp_procedure_code = pm.hbp_procedure_code
    WHERE ca.admission_datetime IS NOT NULL
      AND ca.discharge_datetime IS NOT NULL
      AND pl.procedure_rank = 1
),
state_avg AS (
    SELECT
        hbp_procedure_code,
        ROUND(AVG(los_days), 2) AS state_avg_los
    FROM case_los
    GROUP BY hbp_procedure_code
),
hosp_avg AS (
    SELECT
        hospital_id,
        hbp_procedure_code,
        procedure_name,
        ROUND(AVG(los_days), 2)  AS hosp_avg_los,
        COUNT(*)                  AS case_count
    FROM case_los
    GROUP BY hospital_id, hbp_procedure_code, procedure_name
)
SELECT
    h.hospital_name,
    h.district_name,
    ha.hbp_procedure_code,
    ha.procedure_name,
    ha.case_count,
    ha.hosp_avg_los,
    sa.state_avg_los,
    ROUND(ha.hosp_avg_los - sa.state_avg_los, 2) AS deviation_days
FROM hosp_avg ha
JOIN state_avg sa   ON ha.hbp_procedure_code = sa.hbp_procedure_code
JOIN hm_hospital h  ON ha.hospital_id        = h.hospital_id
WHERE ha.case_count >= 5
ORDER BY ABS(ha.hosp_avg_los - sa.state_avg_los) DESC
LIMIT 20
""",
    },

    "D53": {
        "question": "What is the clinician workload distribution — cases per doctor across hospitals?",
        "sql": """
WITH clinician_cases AS (
    SELECT
        pl.clinician_staff_id,
        COUNT(DISTINCT ca.case_id) AS case_count
    FROM cm_preauth_procedure_line pl
    JOIN cm_preauth_request pr ON pl.preauth_id = pr.preauth_id
    JOIN cm_case ca            ON pr.case_id    = ca.case_id
    WHERE pl.clinician_staff_id IS NOT NULL
    GROUP BY pl.clinician_staff_id
)
SELECT
    h.hospital_name,
    h.district_name,
    h.hospital_type,
    COUNT(DISTINCT s.staff_id)                                                            AS doctor_count,
    ROUND(AVG(cc.case_count), 1)                                                          AS avg_cases_per_doctor,
    MIN(cc.case_count)                                                                    AS min_cases,
    MAX(cc.case_count)                                                                    AS max_cases,
    ROUND(PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY cc.case_count), 1)                AS p75_cases,
    ROUND(PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY cc.case_count), 1)                AS p95_cases
FROM hm_staff s
JOIN hm_hospital h       ON s.hospital_id        = h.hospital_id
JOIN clinician_cases cc  ON s.staff_id            = cc.clinician_staff_id
GROUP BY h.hospital_id, h.hospital_name, h.district_name, h.hospital_type
ORDER BY avg_cases_per_doctor DESC
LIMIT 50
""",
    },

    # ── Financial Analytics (D54-D63) ─────────────────────────────────────────

    "D54": {
        "question": "What is the gap between total amount claimed and total amount approved?",
        "sql": """
SELECT
    ROUND(SUM(amount_claimed),  2)                                                    AS total_claimed,
    ROUND(SUM(amount_approved), 2)                                                    AS total_approved,
    ROUND(SUM(amount_claimed) - SUM(amount_approved), 2)                              AS gap_amount,
    ROUND(
        (SUM(amount_claimed) - SUM(amount_approved))
        * 100.0 / NULLIF(SUM(amount_claimed), 0),
        2
    )                                                                                  AS gap_pct
FROM cm_claim
WHERE amount_claimed IS NOT NULL
  AND amount_approved IS NOT NULL
""",
    },

    "D55": {
        "question": "What is the average claim value by procedure and how does it vary across hospitals?",
        "sql": """
SELECT
    pm.hbp_procedure_code,
    pm.procedure_name,
    pm.specialty_name,
    COUNT(DISTINCT cl.claim_id)                     AS claim_count,
    ROUND(AVG(cl.amount_approved), 2)               AS avg_approved,
    ROUND(MIN(cl.amount_approved), 2)               AS min_approved,
    ROUND(MAX(cl.amount_approved), 2)               AS max_approved,
    ROUND(STDDEV(cl.amount_approved), 2)            AS stddev_approved
FROM cm_claim cl
JOIN cm_case ca            ON cl.case_id           = ca.case_id
JOIN cm_preauth_request pr ON ca.case_id           = pr.case_id
JOIN cm_preauth_procedure_line pl ON pr.preauth_id = pl.preauth_id
JOIN ref_hbp_procedure_master pm  ON pl.hbp_procedure_code = pm.hbp_procedure_code
WHERE pl.procedure_rank = 1
  AND cl.amount_approved IS NOT NULL
GROUP BY pm.hbp_procedure_code, pm.procedure_name, pm.specialty_name
ORDER BY avg_approved DESC
LIMIT 20
""",
    },

    "D56": {
        "question": "What is the aging analysis of pending claims (0-7 days, 7-14, 14-30, 30+)?",
        "sql": """
WITH pending AS (
    SELECT
        claim_id,
        amount_claimed,
        DATE_DIFF('day', submitted_at::DATE, CURRENT_DATE) AS age_days
    FROM cm_claim
    WHERE claim_status = 'PENDING'
      AND submitted_at IS NOT NULL
)
SELECT
    CASE
        WHEN age_days <= 7  THEN '0-7 days'
        WHEN age_days <= 14 THEN '7-14 days'
        WHEN age_days <= 30 THEN '14-30 days'
        ELSE '30+ days'
    END                                                           AS age_bucket,
    COUNT(*)                                                      AS claim_count,
    ROUND(SUM(amount_claimed), 2)                                 AS total_amount_claimed,
    ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER(), 2)            AS pct_of_pending
FROM pending
GROUP BY 1
ORDER BY
    CASE
        WHEN age_bucket = '0-7 days'   THEN 1
        WHEN age_bucket = '7-14 days'  THEN 2
        WHEN age_bucket = '14-30 days' THEN 3
        ELSE 4
    END
""",
    },

    "D57": {
        "question": "What is the total failed payment amount and which hospitals are affected?",
        "sql": """
SELECT
    h.hospital_name,
    h.district_name,
    h.hospital_type,
    COUNT(DISTINCT p.payment_id)            AS failed_payment_count,
    ROUND(SUM(p.amount_paid), 2)            AS total_failed_amount
FROM cm_payment p
JOIN cm_claim cl  ON p.claim_id     = cl.claim_id
JOIN cm_case ca   ON cl.case_id     = ca.case_id
JOIN hm_hospital h ON ca.hospital_id = h.hospital_id
WHERE p.payment_status = 'FAILED'
GROUP BY h.hospital_id, h.hospital_name, h.district_name, h.hospital_type
ORDER BY total_failed_amount DESC
LIMIT 20
""",
    },

    "D58": {
        "question": "What is the average number of documents submitted per claim and does it correlate with approval rate?",
        "sql": """
WITH doc_counts AS (
    SELECT
        claim_id,
        COUNT(*) AS doc_count
    FROM cm_claim_document
    GROUP BY claim_id
),
bucketed AS (
    SELECT
        cl.claim_id,
        cl.claim_status,
        cl.amount_claimed,
        cl.amount_approved,
        COALESCE(dc.doc_count, 0) AS doc_count,
        CASE
            WHEN COALESCE(dc.doc_count, 0) = 0 THEN '0 docs'
            WHEN dc.doc_count <= 2            THEN '1-2 docs'
            WHEN dc.doc_count <= 5            THEN '3-5 docs'
            WHEN dc.doc_count <= 10           THEN '6-10 docs'
            ELSE '11+ docs'
        END AS doc_bucket
    FROM cm_claim cl
    LEFT JOIN doc_counts dc ON cl.claim_id = dc.claim_id
)
SELECT
    doc_bucket,
    COUNT(*)                                                                      AS claim_count,
    ROUND(AVG(doc_count), 1)                                                      AS avg_docs,
    ROUND(AVG(
        CASE WHEN claim_status IN ('APPROVED','SETTLED')
             THEN 1.0 ELSE 0.0 END
    ) * 100.0, 2)                                                                 AS approval_rate_pct,
    ROUND(AVG(
        amount_approved / NULLIF(amount_claimed, 0) * 100.0
    ), 2)                                                                          AS avg_amount_approval_pct
FROM bucketed
GROUP BY doc_bucket
ORDER BY
    CASE doc_bucket
        WHEN '0 docs'   THEN 1
        WHEN '1-2 docs' THEN 2
        WHEN '3-5 docs' THEN 3
        WHEN '6-10 docs' THEN 4
        ELSE 5
    END
""",
    },

    "D59": {
        "question": "What is the query rate during adjudication and what are the top reasons?",
        "sql": """
WITH query_claims AS (
    SELECT DISTINCT claim_id
    FROM cm_adjudication_event
    WHERE action = 'QUERY_RAISED'
       OR reason_category IS NOT NULL
),
top_reasons AS (
    SELECT
        COALESCE(reason_category, 'UNSPECIFIED') AS reason_category,
        COUNT(DISTINCT claim_id)                  AS claim_count,
        ROUND(COUNT(DISTINCT claim_id) * 100.0
              / SUM(COUNT(DISTINCT claim_id)) OVER(), 2) AS pct
    FROM cm_adjudication_event
    WHERE reason_category IS NOT NULL
    GROUP BY reason_category
    ORDER BY claim_count DESC
    LIMIT 10
),
overall AS (
    SELECT
        COUNT(DISTINCT cl.claim_id)                                               AS total_claims,
        COUNT(DISTINCT qc.claim_id)                                               AS queried_claims,
        ROUND(COUNT(DISTINCT qc.claim_id) * 100.0
              / NULLIF(COUNT(DISTINCT cl.claim_id), 0), 2)                        AS query_rate_pct
    FROM cm_claim cl
    LEFT JOIN query_claims qc ON cl.claim_id = qc.claim_id
)
SELECT
    o.total_claims,
    o.queried_claims,
    o.query_rate_pct,
    r.reason_category,
    r.claim_count       AS reason_claim_count,
    r.pct               AS reason_pct
FROM overall o
CROSS JOIN top_reasons r
ORDER BY r.claim_count DESC
""",
    },

    "D60": {
        "question": "What are the top reasons for claim rejection?",
        "sql": """
SELECT
    COALESCE(ae.reason_category, 'UNSPECIFIED')   AS reason_category,
    COUNT(DISTINCT ae.claim_id)                    AS rejected_claim_count,
    ROUND(COUNT(DISTINCT ae.claim_id) * 100.0
          / SUM(COUNT(DISTINCT ae.claim_id)) OVER(), 2) AS pct
FROM cm_adjudication_event ae
JOIN cm_claim cl ON ae.claim_id = cl.claim_id
WHERE cl.claim_status = 'REJECTED'
GROUP BY ae.reason_category
ORDER BY rejected_claim_count DESC
LIMIT 10
""",
    },

    "D61": {
        "question": "What is the month-over-month trend in total claims expenditure?",
        "sql": """
SELECT
    date_trunc('month', ca.admission_datetime)::DATE   AS month,
    COUNT(DISTINCT cl.claim_id)                         AS claim_count,
    ROUND(SUM(cl.amount_approved), 2)                   AS monthly_paid,
    ROUND(SUM(cl.amount_claimed), 2)                    AS monthly_claimed
FROM cm_claim cl
JOIN cm_case ca ON cl.case_id = ca.case_id
WHERE ca.admission_datetime IS NOT NULL
  AND ca.admission_datetime >= '2022-01-01'
GROUP BY 1
ORDER BY 1
""",
    },

    "D62": {
        "question": "What is the per-beneficiary spend by district?",
        "sql": """
SELECT
    h.home_district_code                                                     AS district_name,
    h.home_division_name                                                     AS division_name,
    COUNT(DISTINCT b.beneficiary_id)                                         AS treated_beneficiaries,
    ROUND(SUM(cl.amount_approved), 2)                                        AS total_approved,
    ROUND(SUM(cl.amount_approved)
          / NULLIF(COUNT(DISTINCT b.beneficiary_id), 0), 2)                 AS spend_per_beneficiary
FROM cm_case ca
JOIN cm_claim cl       ON ca.case_id        = cl.case_id
JOIN bm_beneficiary b  ON ca.beneficiary_id = b.beneficiary_id
JOIN bm_household h    ON b.household_id    = h.household_id
WHERE cl.amount_approved IS NOT NULL
GROUP BY h.home_district_code, h.home_division_name
ORDER BY spend_per_beneficiary DESC
""",
    },

    "D63": {
        "question": "Which are the top 20 hospitals by total payment received?",
        "sql": """
SELECT
    h.hospital_name,
    h.district_name,
    h.hospital_type,
    COUNT(DISTINCT p.payment_id)             AS payment_count,
    ROUND(SUM(p.amount_paid), 2)             AS total_payment_received
FROM cm_payment p
JOIN cm_claim cl  ON p.claim_id     = cl.claim_id
JOIN cm_case ca   ON cl.case_id     = ca.case_id
JOIN hm_hospital h ON ca.hospital_id = h.hospital_id
WHERE p.payment_status = 'SUCCESS'
GROUP BY h.hospital_id, h.hospital_name, h.district_name, h.hospital_type
ORDER BY total_payment_received DESC
LIMIT 20
""",
    },

    # ── Pre-Auth & Procedures (D64-D69) ───────────────────────────────────────

    "D64": {
        "question": "What is the pre-auth auto-approval rate vs manual approval vs query vs rejection?",
        "sql": """
SELECT
    status,
    COUNT(*)                                                        AS count,
    ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER(), 2)             AS pct
FROM cm_preauth_request
GROUP BY status
ORDER BY count DESC
""",
    },

    "D65": {
        "question": "What is the average pre-auth turnaround time?",
        "sql": """
SELECT
    ROUND(AVG(DATE_DIFF('day', initiated_at::DATE, ppd_decision_at::DATE)), 1)                   AS avg_tat_days,
    ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (
        ORDER BY DATE_DIFF('day', initiated_at::DATE, ppd_decision_at::DATE)
    ), 1)                                                                                          AS median_tat_days,
    ROUND(PERCENTILE_CONT(0.9) WITHIN GROUP (
        ORDER BY DATE_DIFF('day', initiated_at::DATE, ppd_decision_at::DATE)
    ), 1)                                                                                          AS p90_tat_days,
    MIN(DATE_DIFF('day', initiated_at::DATE, ppd_decision_at::DATE))                              AS min_tat_days,
    MAX(DATE_DIFF('day', initiated_at::DATE, ppd_decision_at::DATE))                              AS max_tat_days
FROM cm_preauth_request
WHERE ppd_decision_at IS NOT NULL
  AND initiated_at    IS NOT NULL
""",
    },

    "D66": {
        "question": "How many pre-auths were force-approved due to TAT breach?",
        "sql": """
WITH force_approved AS (
    SELECT
        date_trunc('month', initiated_at)::DATE AS month,
        COUNT(*)                                 AS force_approved_count
    FROM cm_preauth_request
    WHERE status            = 'AUTO_APPROVED'
      AND auto_approval_type IS NOT NULL
    GROUP BY 1
)
SELECT
    (SELECT COUNT(*) FROM cm_preauth_request
     WHERE status = 'AUTO_APPROVED' AND auto_approval_type IS NOT NULL) AS total_force_approved,
    (SELECT COUNT(*) FROM cm_preauth_request)                           AS total_preauths,
    ROUND(
        (SELECT COUNT(*) FROM cm_preauth_request
         WHERE status = 'AUTO_APPROVED' AND auto_approval_type IS NOT NULL) * 100.0
        / NULLIF((SELECT COUNT(*) FROM cm_preauth_request), 0),
        2
    )                                                                    AS force_approved_pct,
    f.month,
    f.force_approved_count
FROM force_approved f
ORDER BY f.month
""",
    },

    "D68": {
        "question": "What is the average number of procedures per case and contribution of add-ons to total cost?",
        "sql": """
WITH case_procedures AS (
    SELECT
        pr.case_id,
        COUNT(pl.preauth_proc_id)                                          AS total_procedures,
        SUM(CASE WHEN pl.is_addon = TRUE  THEN pl.computed_final_amount ELSE 0 END) AS addon_cost,
        SUM(CASE WHEN pl.is_addon = FALSE THEN pl.computed_final_amount ELSE 0 END) AS base_cost,
        SUM(pl.computed_final_amount)                                      AS total_cost
    FROM cm_preauth_request pr
    JOIN cm_preauth_procedure_line pl ON pr.preauth_id = pl.preauth_id
    GROUP BY pr.case_id
)
SELECT
    COUNT(DISTINCT case_id)                                                  AS total_cases,
    ROUND(AVG(total_procedures), 2)                                          AS avg_procedures_per_case,
    ROUND(SUM(addon_cost), 2)                                                AS total_addon_cost,
    ROUND(SUM(base_cost), 2)                                                 AS total_base_cost,
    ROUND(SUM(total_cost), 2)                                                AS total_cost,
    ROUND(SUM(addon_cost) * 100.0 / NULLIF(SUM(total_cost), 0), 2)         AS addon_cost_pct
FROM case_procedures
""",
    },

    "D69": {
        "question": "Which hospitals have the highest add-on procedure rate?",
        "sql": """
WITH hosp_procedures AS (
    SELECT
        ca.hospital_id,
        COUNT(pl.preauth_proc_id)                                            AS total_procedures,
        COUNT(CASE WHEN pl.is_addon = TRUE THEN 1 END)                       AS addon_procedures
    FROM cm_preauth_procedure_line pl
    JOIN cm_preauth_request pr ON pl.preauth_id  = pr.preauth_id
    JOIN cm_case ca            ON pr.case_id     = ca.case_id
    GROUP BY ca.hospital_id
)
SELECT
    h.hospital_name,
    h.district_name,
    h.hospital_type,
    hp.total_procedures,
    hp.addon_procedures,
    ROUND(hp.addon_procedures * 100.0 / NULLIF(hp.total_procedures, 0), 2) AS addon_rate_pct
FROM hosp_procedures hp
JOIN hm_hospital h ON hp.hospital_id = h.hospital_id
WHERE hp.total_procedures >= 10
ORDER BY addon_rate_pct DESC
LIMIT 20
""",
    },

    # ── Fraud & Anomaly Detection (D72, D76, D77) ─────────────────────────────

    "D72": {
        "question": "Are there beneficiaries with multiple admissions at different hospitals within 7 days?",
        "sql": """
WITH ranked_cases AS (
    SELECT
        beneficiary_id,
        hospital_id,
        admission_datetime,
        LAG(admission_datetime) OVER (
            PARTITION BY beneficiary_id ORDER BY admission_datetime
        ) AS prev_admission_datetime,
        LAG(hospital_id) OVER (
            PARTITION BY beneficiary_id ORDER BY admission_datetime
        ) AS prev_hospital_id
    FROM cm_case
    WHERE admission_datetime IS NOT NULL
),
multi_admit AS (
    SELECT
        beneficiary_id,
        COUNT(*) AS suspicious_pair_count
    FROM ranked_cases
    WHERE prev_admission_datetime IS NOT NULL
      AND hospital_id <> prev_hospital_id
      AND DATE_DIFF('day', prev_admission_datetime::DATE, admission_datetime::DATE) < 7
      AND DATE_DIFF('day', prev_admission_datetime::DATE, admission_datetime::DATE) >= 0
    GROUP BY beneficiary_id
)
SELECT
    COUNT(DISTINCT beneficiary_id)   AS beneficiaries_with_multi_admit,
    SUM(suspicious_pair_count)       AS total_suspicious_pairs,
    (SELECT COUNT(DISTINCT beneficiary_id) FROM cm_case) AS total_treated_beneficiaries,
    ROUND(
        COUNT(DISTINCT beneficiary_id) * 100.0
        / NULLIF((SELECT COUNT(DISTINCT beneficiary_id) FROM cm_case), 0),
        2
    )                                AS pct_of_treated
FROM multi_admit
""",
    },

    "D76": {
        "question": "Which hospitals have the highest claim amount per case relative to state average for the same procedure?",
        "sql": """
WITH hosp_proc_avg AS (
    SELECT
        ca.hospital_id,
        pm.hbp_procedure_code,
        pm.procedure_name,
        ROUND(AVG(cl.amount_approved), 2)  AS hosp_avg_approved,
        COUNT(DISTINCT ca.case_id)          AS case_count
    FROM cm_case ca
    JOIN cm_claim cl            ON ca.case_id           = cl.case_id
    JOIN cm_preauth_request pr  ON ca.case_id           = pr.case_id
    JOIN cm_preauth_procedure_line pl ON pr.preauth_id  = pl.preauth_id
    JOIN ref_hbp_procedure_master pm  ON pl.hbp_procedure_code = pm.hbp_procedure_code
    WHERE pl.procedure_rank = 1
      AND cl.amount_approved IS NOT NULL
    GROUP BY ca.hospital_id, pm.hbp_procedure_code, pm.procedure_name
),
state_proc_avg AS (
    SELECT
        hbp_procedure_code,
        ROUND(AVG(hosp_avg_approved), 2) AS state_avg_approved
    FROM hosp_proc_avg
    GROUP BY hbp_procedure_code
)
SELECT
    h.hospital_name,
    h.district_name,
    h.hospital_type,
    hp.hbp_procedure_code,
    hp.procedure_name,
    hp.case_count,
    hp.hosp_avg_approved,
    sp.state_avg_approved,
    ROUND(hp.hosp_avg_approved / NULLIF(sp.state_avg_approved, 0), 3) AS ratio_to_state_avg
FROM hosp_proc_avg hp
JOIN state_proc_avg sp ON hp.hbp_procedure_code = sp.hbp_procedure_code
JOIN hm_hospital h     ON hp.hospital_id        = h.hospital_id
WHERE hp.case_count >= 5
  AND hp.hosp_avg_approved / NULLIF(sp.state_avg_approved, 0) > 1.5
ORDER BY ratio_to_state_avg DESC
LIMIT 20
""",
    },

    "D77": {
        "question": "What is the rate of readmissions within 30 days for the same diagnosis?",
        "sql": """
WITH case_diag AS (
    SELECT
        ca.case_id,
        ca.beneficiary_id,
        ca.admission_datetime,
        d.discharge_date,
        cd.diagnosis_category
    FROM cm_case ca
    JOIN cm_discharge d        ON ca.case_id = d.case_id
    JOIN cm_case_diagnosis cd  ON ca.case_id = cd.case_id
    WHERE cd.diagnosis_type    = 'PRIMARY'
      AND ca.admission_datetime IS NOT NULL
      AND d.discharge_date      IS NOT NULL
),
readmits AS (
    SELECT
        a.case_id                          AS readmit_case_id,
        a.beneficiary_id
    FROM case_diag a
    JOIN case_diag b
        ON  a.beneficiary_id     = b.beneficiary_id
        AND a.diagnosis_category = b.diagnosis_category
        AND a.case_id           <> b.case_id
        AND DATE_DIFF('day', b.discharge_date::DATE, a.admission_datetime::DATE) BETWEEN 1 AND 30
)
SELECT
    COUNT(DISTINCT ca.case_id)                                              AS total_cases,
    COUNT(DISTINCT r.readmit_case_id)                                       AS readmission_cases,
    ROUND(
        COUNT(DISTINCT r.readmit_case_id) * 100.0
        / NULLIF(COUNT(DISTINCT ca.case_id), 0),
        2
    )                                                                        AS readmission_rate_pct
FROM cm_case ca
LEFT JOIN readmits r ON ca.case_id = r.readmit_case_id
""",
    },

    # ── Equity & Demographics (D78-D85) ───────────────────────────────────────

    "D78": {
        "question": "What is the male vs female ratio of treated patients by district?",
        "sql": """
SELECT
    h.home_district_code                                                        AS district_name,
    h.home_division_name                                                        AS division_name,
    COUNT(DISTINCT CASE WHEN b.gender = 'MALE'   THEN ca.case_id END)          AS male_cases,
    COUNT(DISTINCT CASE WHEN b.gender = 'FEMALE' THEN ca.case_id END)          AS female_cases,
    COUNT(DISTINCT ca.case_id)                                                  AS total_cases,
    ROUND(
        COUNT(DISTINCT CASE WHEN b.gender = 'MALE' THEN ca.case_id END) * 100.0
        / NULLIF(COUNT(DISTINCT ca.case_id), 0),
        2
    )                                                                            AS male_pct,
    ROUND(
        COUNT(DISTINCT CASE WHEN b.gender = 'FEMALE' THEN ca.case_id END) * 100.0
        / NULLIF(COUNT(DISTINCT ca.case_id), 0),
        2
    )                                                                            AS female_pct
FROM cm_case ca
JOIN bm_beneficiary b ON ca.beneficiary_id = b.beneficiary_id
JOIN bm_household h   ON b.household_id    = h.household_id
GROUP BY h.home_district_code, h.home_division_name
ORDER BY total_cases DESC
""",
    },

    "D79": {
        "question": "Are elderly beneficiaries (65+) utilizing the scheme proportionally to their enrolment?",
        "sql": """
WITH enrolment AS (
    SELECT
        COUNT(*) AS total_enrolled,
        COUNT(CASE WHEN (EXTRACT(YEAR FROM CURRENT_DATE)::INTEGER - yob) >= 65 THEN 1 END) AS elderly_enrolled
    FROM bm_beneficiary
    WHERE yob IS NOT NULL
),
utilization AS (
    SELECT
        COUNT(DISTINCT ca.beneficiary_id) AS total_treated,
        COUNT(DISTINCT CASE
            WHEN (EXTRACT(YEAR FROM CURRENT_DATE)::INTEGER - b.yob) >= 65
            THEN ca.beneficiary_id
        END)                              AS elderly_treated
    FROM cm_case ca
    JOIN bm_beneficiary b ON ca.beneficiary_id = b.beneficiary_id
    WHERE b.yob IS NOT NULL
)
SELECT
    e.total_enrolled,
    e.elderly_enrolled,
    ROUND(e.elderly_enrolled * 100.0 / NULLIF(e.total_enrolled, 0), 2)   AS enrolment_elderly_pct,
    u.total_treated,
    u.elderly_treated,
    ROUND(u.elderly_treated * 100.0 / NULLIF(u.total_treated, 0), 2)     AS utilization_elderly_pct,
    ROUND(
        (u.elderly_treated * 100.0 / NULLIF(u.total_treated, 0))
        - (e.elderly_enrolled * 100.0 / NULLIF(e.total_enrolled, 0)),
        2
    )                                                                       AS utilization_vs_enrolment_gap_pp
FROM enrolment e
CROSS JOIN utilization u
""",
    },

    "D80": {
        "question": "Which blocks have zero or near-zero hospital admissions?",
        "sql": """
WITH block_cases AS (
    SELECT
        h.home_block_name                        AS block_name,
        h.home_district_code                     AS district_name,
        h.home_division_name                     AS division_name,
        COUNT(DISTINCT ca.case_id)               AS case_count
    FROM bm_household h
    LEFT JOIN bm_beneficiary b ON h.household_id    = b.household_id
    LEFT JOIN cm_case ca       ON b.beneficiary_id  = ca.beneficiary_id
    GROUP BY h.home_block_name, h.home_district_code, h.home_division_name
)
SELECT
    g.block_name,
    g.district_name,
    g.division_name,
    COALESCE(bc.case_count, 0) AS case_count
FROM ref_up_geography g
LEFT JOIN block_cases bc
    ON  g.block_name    = bc.block_name
    AND g.district_name = bc.district_name
WHERE COALESCE(bc.case_count, 0) < 5
ORDER BY case_count ASC, g.district_name, g.block_name
LIMIT 50
""",
    },

    "D82": {
        "question": "Is there a difference in claim approval rates between public and private hospitals?",
        "sql": """
SELECT
    h.hospital_type,
    COUNT(DISTINCT h.hospital_id)                                              AS hospital_count,
    COUNT(cl.claim_id)                                                         AS total_claims,
    ROUND(AVG(
        cl.amount_approved / NULLIF(cl.amount_claimed, 0) * 100.0
    ), 1)                                                                       AS avg_approval_rate_pct,
    ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (
        ORDER BY cl.amount_approved / NULLIF(cl.amount_claimed, 0) * 100.0
    ), 1)                                                                       AS median_approval_rate_pct
FROM hm_hospital h
JOIN cm_case ca  ON h.hospital_id = ca.hospital_id
JOIN cm_claim cl ON ca.case_id    = cl.case_id
WHERE cl.amount_claimed > 0
GROUP BY h.hospital_type
ORDER BY avg_approval_rate_pct DESC
""",
    },

    "D83": {
        "question": "Is there a difference in settlement TAT between public and private hospitals?",
        "sql": """
SELECT
    h.hospital_type,
    COUNT(DISTINCT h.hospital_id)                                                           AS hospital_count,
    COUNT(cl.claim_id)                                                                      AS settled_claims,
    ROUND(AVG(cl.settlement_tat_days), 1)                                                   AS avg_tat_days,
    ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY cl.settlement_tat_days), 1)          AS median_tat_days,
    ROUND(PERCENTILE_CONT(0.9) WITHIN GROUP (ORDER BY cl.settlement_tat_days), 1)          AS p90_tat_days,
    MAX(cl.settlement_tat_days)                                                             AS max_tat_days
FROM cm_claim cl
JOIN cm_case ca   ON cl.case_id     = ca.case_id
JOIN hm_hospital h ON ca.hospital_id = h.hospital_id
WHERE cl.settlement_tat_days IS NOT NULL
GROUP BY h.hospital_type
ORDER BY avg_tat_days DESC
""",
    },

    "D84": {
        "question": "Do utilization patterns differ by entitlement source (SECC vs STATE_DB vs RSBY)?",
        "sql": """
WITH enrolled AS (
    SELECT
        h.entitlement_source,
        COUNT(DISTINCT b.beneficiary_id) AS enrolled_count
    FROM bm_household h
    JOIN bm_beneficiary b ON h.household_id = b.household_id
    GROUP BY h.entitlement_source
),
utilized AS (
    SELECT
        h.entitlement_source,
        COUNT(DISTINCT ca.case_id)            AS total_cases,
        COUNT(DISTINCT ca.beneficiary_id)     AS treated_beneficiaries,
        ROUND(AVG(cl.amount_approved), 2)     AS avg_claim_value
    FROM bm_household h
    JOIN bm_beneficiary b ON h.household_id   = b.household_id
    JOIN cm_case ca       ON b.beneficiary_id = ca.beneficiary_id
    JOIN cm_claim cl      ON ca.case_id       = cl.case_id
    WHERE cl.amount_approved IS NOT NULL
    GROUP BY h.entitlement_source
)
SELECT
    e.entitlement_source,
    e.enrolled_count,
    COALESCE(u.total_cases, 0)            AS total_cases,
    COALESCE(u.treated_beneficiaries, 0)  AS treated_beneficiaries,
    ROUND(COALESCE(u.total_cases, 0) * 1000.0
          / NULLIF(e.enrolled_count, 0), 2) AS cases_per_1000_enrolled,
    COALESCE(u.avg_claim_value, 0)        AS avg_claim_value
FROM enrolled e
LEFT JOIN utilized u ON e.entitlement_source = u.entitlement_source
ORDER BY cases_per_1000_enrolled DESC
""",
    },

    "D85": {
        "question": "Are there gender disparities in types of procedures accessed?",
        "sql": """
WITH proc_gender AS (
    SELECT
        pm.hbp_procedure_code,
        pm.procedure_name,
        pm.specialty_name,
        b.gender,
        COUNT(DISTINCT ca.case_id) AS case_count
    FROM cm_case ca
    JOIN bm_beneficiary b          ON ca.beneficiary_id = b.beneficiary_id
    JOIN cm_preauth_request pr     ON ca.case_id        = pr.case_id
    JOIN cm_preauth_procedure_line pl ON pr.preauth_id  = pl.preauth_id
    JOIN ref_hbp_procedure_master pm  ON pl.hbp_procedure_code = pm.hbp_procedure_code
    WHERE pl.procedure_rank = 1
    GROUP BY pm.hbp_procedure_code, pm.procedure_name, pm.specialty_name, b.gender
),
top_procs AS (
    SELECT hbp_procedure_code
    FROM proc_gender
    GROUP BY hbp_procedure_code
    ORDER BY SUM(case_count) DESC
    LIMIT 10
)
SELECT
    pg.hbp_procedure_code,
    pg.procedure_name,
    pg.specialty_name,
    SUM(CASE WHEN pg.gender = 'MALE'   THEN pg.case_count ELSE 0 END) AS male_cases,
    SUM(CASE WHEN pg.gender = 'FEMALE' THEN pg.case_count ELSE 0 END) AS female_cases,
    SUM(pg.case_count)                                                  AS total_cases
FROM proc_gender pg
WHERE pg.hbp_procedure_code IN (SELECT hbp_procedure_code FROM top_procs)
GROUP BY pg.hbp_procedure_code, pg.procedure_name, pg.specialty_name
ORDER BY total_cases DESC
""",
    },

    # ── Discharge Outcomes (D86-D89) ──────────────────────────────────────────

    "D86": {
        "question": "What is the overall mortality rate and which hospitals or procedures have the highest?",
        "sql": """
WITH hosp_mortality AS (
    SELECT
        ca.hospital_id,
        COUNT(DISTINCT ca.case_id)                                           AS total_cases,
        COUNT(DISTINCT CASE WHEN d.death_date IS NOT NULL THEN ca.case_id END) AS death_cases,
        ROUND(
            COUNT(DISTINCT CASE WHEN d.death_date IS NOT NULL THEN ca.case_id END) * 100.0
            / NULLIF(COUNT(DISTINCT ca.case_id), 0),
            2
        )                                                                     AS mortality_rate_pct
    FROM cm_case ca
    JOIN cm_discharge d ON ca.case_id = d.case_id
    GROUP BY ca.hospital_id
    HAVING COUNT(DISTINCT ca.case_id) >= 10
)
SELECT
    h.hospital_name,
    h.district_name,
    h.hospital_type,
    hm.total_cases,
    hm.death_cases,
    hm.mortality_rate_pct
FROM hosp_mortality hm
JOIN hm_hospital h ON hm.hospital_id = h.hospital_id
ORDER BY hm.mortality_rate_pct DESC
LIMIT 10
""",
    },

    "D87": {
        "question": "Which hospitals have the highest LAMA/DAMA rate?",
        "sql": """
WITH hosp_lama AS (
    SELECT
        ca.hospital_id,
        COUNT(DISTINCT ca.case_id)                                               AS total_cases,
        COUNT(DISTINCT CASE WHEN d.lama_date IS NOT NULL THEN ca.case_id END)    AS lama_cases,
        ROUND(
            COUNT(DISTINCT CASE WHEN d.lama_date IS NOT NULL THEN ca.case_id END) * 100.0
            / NULLIF(COUNT(DISTINCT ca.case_id), 0),
            2
        )                                                                         AS lama_rate_pct
    FROM cm_case ca
    JOIN cm_discharge d ON ca.case_id = d.case_id
    GROUP BY ca.hospital_id
    HAVING COUNT(DISTINCT ca.case_id) >= 10
)
SELECT
    h.hospital_name,
    h.district_name,
    h.hospital_type,
    hl.total_cases,
    hl.lama_cases,
    hl.lama_rate_pct
FROM hosp_lama hl
JOIN hm_hospital h ON hl.hospital_id = h.hospital_id
ORDER BY hl.lama_rate_pct DESC
LIMIT 20
""",
    },

    "D88": {
        "question": "What proportion of discharges had biometric authentication?",
        "sql": """
WITH overall AS (
    SELECT
        COUNT(*)                                                         AS total_discharges,
        COUNT(CASE WHEN biometric_auth_used = TRUE THEN 1 END)          AS biometric_discharges,
        ROUND(COUNT(CASE WHEN biometric_auth_used = TRUE THEN 1 END) * 100.0
              / NULLIF(COUNT(*), 0), 2)                                  AS biometric_pct
    FROM cm_discharge
),
by_type AS (
    SELECT
        h.hospital_type,
        COUNT(d.discharge_id)                                                   AS total_discharges,
        COUNT(CASE WHEN d.biometric_auth_used = TRUE THEN 1 END)               AS biometric_discharges,
        ROUND(COUNT(CASE WHEN d.biometric_auth_used = TRUE THEN 1 END) * 100.0
              / NULLIF(COUNT(d.discharge_id), 0), 2)                            AS biometric_pct
    FROM cm_discharge d
    JOIN cm_case ca    ON d.case_id     = ca.case_id
    JOIN hm_hospital h ON ca.hospital_id = h.hospital_id
    GROUP BY h.hospital_type
)
SELECT
    'STATE_WIDE'     AS hospital_type,
    o.total_discharges,
    o.biometric_discharges,
    o.biometric_pct
FROM overall o
UNION ALL
SELECT
    bt.hospital_type,
    bt.total_discharges,
    bt.biometric_discharges,
    bt.biometric_pct
FROM by_type bt
ORDER BY hospital_type
""",
    },

    "D89": {
        "question": "What proportion of discharges had medicines provided to the patient?",
        "sql": """
WITH overall AS (
    SELECT
        COUNT(*)                                                          AS total_discharges,
        COUNT(CASE WHEN provided_medicines_flag = TRUE THEN 1 END)       AS medicines_provided_count,
        ROUND(COUNT(CASE WHEN provided_medicines_flag = TRUE THEN 1 END) * 100.0
              / NULLIF(COUNT(*), 0), 2)                                   AS medicines_provided_pct
    FROM cm_discharge
),
by_type AS (
    SELECT
        h.hospital_type,
        COUNT(d.discharge_id)                                                       AS total_discharges,
        COUNT(CASE WHEN d.provided_medicines_flag = TRUE THEN 1 END)               AS medicines_provided_count,
        ROUND(COUNT(CASE WHEN d.provided_medicines_flag = TRUE THEN 1 END) * 100.0
              / NULLIF(COUNT(d.discharge_id), 0), 2)                               AS medicines_provided_pct
    FROM cm_discharge d
    JOIN cm_case ca    ON d.case_id     = ca.case_id
    JOIN hm_hospital h ON ca.hospital_id = h.hospital_id
    GROUP BY h.hospital_type
)
SELECT
    'STATE_WIDE'   AS hospital_type,
    o.total_discharges,
    o.medicines_provided_count,
    o.medicines_provided_pct
FROM overall o
UNION ALL
SELECT
    bt.hospital_type,
    bt.total_discharges,
    bt.medicines_provided_count,
    bt.medicines_provided_pct
FROM by_type bt
ORDER BY hospital_type
""",
    },

    # ── Disease Burden & Epidemiology (D90-D94) ───────────────────────────────

    "D90": {
        "question": "How does the communicable vs NCD vs maternal disease mix vary across divisions?",
        "sql": """
SELECT
    h.home_division_name                                                     AS division_name,
    cd.diagnosis_category,
    COUNT(DISTINCT ca.case_id)                                               AS case_count,
    ROUND(COUNT(DISTINCT ca.case_id) * 100.0
          / SUM(COUNT(DISTINCT ca.case_id)) OVER (PARTITION BY h.home_division_name), 2) AS pct_within_division
FROM cm_case_diagnosis cd
JOIN cm_case ca       ON cd.case_id        = ca.case_id
JOIN bm_beneficiary b ON ca.beneficiary_id = b.beneficiary_id
JOIN bm_household h   ON b.household_id    = h.household_id
WHERE cd.diagnosis_type = 'PRIMARY'
GROUP BY h.home_division_name, cd.diagnosis_category
ORDER BY h.home_division_name, case_count DESC
""",
    },

    "D91": {
        "question": "Which districts have the highest maternal/neonatal case rates?",
        "sql": """
WITH enrolled_women AS (
    SELECT
        h.home_district_code            AS district_name,
        COUNT(DISTINCT b.beneficiary_id) AS enrolled_female_count
    FROM bm_household h
    JOIN bm_beneficiary b ON h.household_id = b.household_id
    WHERE b.gender = 'FEMALE'
    GROUP BY h.home_district_code
),
maternal_cases AS (
    SELECT
        h.home_district_code            AS district_name,
        COUNT(DISTINCT ca.case_id)       AS maternal_case_count
    FROM cm_case_diagnosis cd
    JOIN cm_case ca       ON cd.case_id        = ca.case_id
    JOIN bm_beneficiary b ON ca.beneficiary_id = b.beneficiary_id
    JOIN bm_household h   ON b.household_id    = h.household_id
    WHERE cd.diagnosis_category = 'MATERNAL_NEONATAL'
      AND cd.diagnosis_type     = 'PRIMARY'
      AND b.gender              = 'FEMALE'
    GROUP BY h.home_district_code
)
SELECT
    ew.district_name,
    ew.enrolled_female_count,
    COALESCE(mc.maternal_case_count, 0)                                         AS maternal_case_count,
    ROUND(COALESCE(mc.maternal_case_count, 0) * 1000.0
          / NULLIF(ew.enrolled_female_count, 0), 2)                             AS maternal_rate_per_1000_women
FROM enrolled_women ew
LEFT JOIN maternal_cases mc ON ew.district_name = mc.district_name
ORDER BY maternal_rate_per_1000_women DESC
""",
    },

    "D92": {
        "question": "Which districts have the highest communicable disease case loads?",
        "sql": """
SELECT
    ca.hospital_district                   AS district_name,
    COUNT(DISTINCT ca.case_id)             AS communicable_case_count
FROM cm_case_diagnosis cd
JOIN cm_case ca ON cd.case_id = ca.case_id
WHERE cd.diagnosis_category = 'COMMUNICABLE'
  AND cd.diagnosis_type     = 'PRIMARY'
GROUP BY ca.hospital_district
ORDER BY communicable_case_count DESC
LIMIT 20
""",
    },

    "D93": {
        "question": "Is there a seasonal pattern in communicable disease cases?",
        "sql": """
SELECT
    EXTRACT(MONTH FROM ca.admission_datetime)::INTEGER  AS month_number,
    COUNT(DISTINCT ca.case_id)                           AS communicable_cases
FROM cm_case_diagnosis cd
JOIN cm_case ca ON cd.case_id = ca.case_id
WHERE cd.diagnosis_category = 'COMMUNICABLE'
  AND cd.diagnosis_type     = 'PRIMARY'
  AND ca.admission_datetime IS NOT NULL
GROUP BY 1
ORDER BY 1
""",
    },

    "D94": {
        "question": "What is the injury caseload distribution across districts?",
        "sql": """
SELECT
    ca.hospital_district                   AS district_name,
    COUNT(DISTINCT ca.case_id)             AS injury_case_count,
    ROUND(COUNT(DISTINCT ca.case_id) * 100.0
          / SUM(COUNT(DISTINCT ca.case_id)) OVER(), 2) AS pct_of_total_injury
FROM cm_case_diagnosis cd
JOIN cm_case ca ON cd.case_id = ca.case_id
WHERE cd.diagnosis_category = 'INJURY'
  AND cd.diagnosis_type     = 'PRIMARY'
GROUP BY ca.hospital_district
ORDER BY injury_case_count DESC
""",
    },

    # ── Programme Funnel & Operational KPIs (D95-D98) ─────────────────────────

    "D95": {
        "question": "What is the overall enrolment-to-treatment funnel?",
        "sql": """
WITH enrolled AS (
    SELECT COUNT(DISTINCT beneficiary_id) AS cnt FROM bm_beneficiary
),
card_issued AS (
    SELECT COUNT(DISTINCT beneficiary_id) AS cnt FROM bm_card
),
admitted AS (
    SELECT COUNT(DISTINCT beneficiary_id) AS cnt FROM cm_case
),
claimed AS (
    SELECT COUNT(DISTINCT ca.beneficiary_id) AS cnt
    FROM cm_claim cl
    JOIN cm_case ca ON cl.case_id = ca.case_id
    WHERE cl.claim_status <> 'PENDING'
),
paid AS (
    SELECT COUNT(DISTINCT ca.beneficiary_id) AS cnt
    FROM cm_payment p
    JOIN cm_claim cl  ON p.claim_id     = cl.claim_id
    JOIN cm_case ca   ON cl.case_id     = ca.case_id
    WHERE p.payment_status = 'SUCCESS'
)
SELECT
    'Step 1: Enrolled'        AS funnel_step,
    e.cnt                      AS beneficiary_count,
    100.0                      AS pct_of_enrolled,
    NULL::DOUBLE               AS pct_of_prev_step
FROM enrolled e
UNION ALL
SELECT
    'Step 2: Card Issued',
    ci.cnt,
    ROUND(ci.cnt * 100.0 / NULLIF(e.cnt, 0), 2),
    ROUND(ci.cnt * 100.0 / NULLIF(e.cnt, 0), 2)
FROM card_issued ci, enrolled e
UNION ALL
SELECT
    'Step 3: Admitted',
    ad.cnt,
    ROUND(ad.cnt * 100.0 / NULLIF(e.cnt, 0), 2),
    ROUND(ad.cnt * 100.0 / NULLIF(ci.cnt, 0), 2)
FROM admitted ad, enrolled e, card_issued ci
UNION ALL
SELECT
    'Step 4: Claimed',
    cl_cnt.cnt,
    ROUND(cl_cnt.cnt * 100.0 / NULLIF(e.cnt, 0), 2),
    ROUND(cl_cnt.cnt * 100.0 / NULLIF(ad.cnt, 0), 2)
FROM claimed cl_cnt, enrolled e, admitted ad
UNION ALL
SELECT
    'Step 5: Paid',
    pd.cnt,
    ROUND(pd.cnt * 100.0 / NULLIF(e.cnt, 0), 2),
    ROUND(pd.cnt * 100.0 / NULLIF(cl_cnt.cnt, 0), 2)
FROM paid pd, enrolled e, claimed cl_cnt
""",
    },

    "D96": {
        "question": "What is the average time from admission to discharge to claim submission to settlement?",
        "sql": """
SELECT
    ROUND(AVG(DATE_DIFF('day',
        ca.admission_datetime::DATE,
        ca.discharge_datetime::DATE
    )), 1)                                                    AS avg_admission_to_discharge_days,
    ROUND(AVG(DATE_DIFF('day',
        ca.discharge_datetime::DATE,
        cl.submitted_at::DATE
    )), 1)                                                    AS avg_discharge_to_submission_days,
    ROUND(AVG(DATE_DIFF('day',
        cl.submitted_at::DATE,
        cl.settled_at::DATE
    )), 1)                                                    AS avg_submission_to_settlement_days,
    ROUND(AVG(DATE_DIFF('day',
        ca.admission_datetime::DATE,
        cl.settled_at::DATE
    )), 1)                                                    AS avg_total_cycle_days
FROM cm_case ca
JOIN cm_claim cl ON ca.case_id = cl.case_id
WHERE ca.admission_datetime IS NOT NULL
  AND ca.discharge_datetime IS NOT NULL
  AND cl.submitted_at       IS NOT NULL
  AND cl.settled_at         IS NOT NULL
""",
    },

    "D97": {
        "question": "What is the payout factor distribution across cases?",
        "sql": """
SELECT
    payout_factor,
    COUNT(*)                                                        AS occurrence_count,
    ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER(), 2)             AS pct,
    ROUND(SUM(computed_final_amount), 2)                           AS total_amount,
    ROUND(AVG(base_amount), 2)                                     AS avg_base_amount,
    ROUND(AVG(computed_final_amount), 2)                           AS avg_final_amount
FROM cm_preauth_procedure_line
WHERE payout_factor IS NOT NULL
GROUP BY payout_factor
ORDER BY payout_factor
""",
    },

    "D98": {
        "question": "What is the concentration of scheme expenditure — do the top 10% of hospitals account for what share of total payments?",
        "sql": """
WITH hosp_payments AS (
    SELECT
        h.hospital_id,
        h.hospital_name,
        h.district_name,
        h.hospital_type,
        SUM(p.amount_paid)          AS total_paid
    FROM cm_payment p
    JOIN cm_claim cl  ON p.claim_id      = cl.claim_id
    JOIN cm_case ca   ON cl.case_id      = ca.case_id
    JOIN hm_hospital h ON ca.hospital_id = h.hospital_id
    WHERE p.payment_status = 'SUCCESS'
    GROUP BY h.hospital_id, h.hospital_name, h.district_name, h.hospital_type
),
ranked AS (
    SELECT
        hospital_id,
        hospital_name,
        district_name,
        hospital_type,
        total_paid,
        RANK() OVER (ORDER BY total_paid DESC)                       AS pay_rank,
        COUNT(*) OVER ()                                              AS total_hospitals,
        SUM(total_paid) OVER ()                                       AS grand_total_paid,
        SUM(total_paid) OVER (ORDER BY total_paid DESC
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)        AS cumulative_paid
    FROM hosp_payments
),
concentration AS (
    SELECT
        CASE
            WHEN pay_rank <= CEIL(total_hospitals * 0.10) THEN 'Top 10%'
            WHEN pay_rank <= CEIL(total_hospitals * 0.20) THEN 'Next 10% (11-20%)'
            WHEN pay_rank <= CEIL(total_hospitals * 0.50) THEN 'Middle 30% (21-50%)'
            ELSE 'Bottom 50%'
        END                                               AS hospital_tier,
        COUNT(*)                                          AS hospital_count,
        ROUND(SUM(total_paid), 2)                         AS tier_total_paid,
        ROUND(SUM(total_paid) * 100.0
              / NULLIF(MAX(grand_total_paid), 0), 2)      AS share_of_total_pct
    FROM ranked
    GROUP BY 1
)
SELECT
    hospital_tier,
    hospital_count,
    tier_total_paid,
    share_of_total_pct
FROM concentration
ORDER BY share_of_total_pct DESC
""",
    },

    # ── Tier-1 Expanded: Geography & Access (D99-D115) ────────────────────────

    "D99": {
        "question": "What is the district-wise active vs inactive vs disabled card rate?",
        "sql": """
SELECT
    h.home_district_code                                                          AS district,
    COUNT(CASE WHEN c.card_status = 'ACTIVE'   THEN 1 END)                       AS active,
    COUNT(CASE WHEN c.card_status = 'INACTIVE' THEN 1 END)                       AS inactive,
    COUNT(CASE WHEN c.card_status = 'DISABLED' THEN 1 END)                       AS disabled,
    COUNT(c.card_id)                                                              AS total,
    ROUND(
        COUNT(CASE WHEN c.card_status = 'ACTIVE' THEN 1 END)
        * 100.0 / NULLIF(COUNT(c.card_id), 0), 1
    )                                                                             AS active_pct
FROM bm_card c
JOIN bm_beneficiary b ON c.beneficiary_id = b.beneficiary_id
JOIN bm_household   h ON b.household_id   = h.household_id
GROUP BY h.home_district_code
ORDER BY total DESC
""",
    },

    "D100": {
        "question": "What is the district-wise beneficiary profile completeness rate (DOB, mobile, photo)?",
        "sql": """
SELECT
    h.home_district_code                                                             AS district,
    COUNT(DISTINCT b.beneficiary_id)                                                 AS total_beneficiaries,
    ROUND(
        COUNT(DISTINCT CASE WHEN b.yob IS NOT NULL THEN b.beneficiary_id END)
        * 100.0 / NULLIF(COUNT(DISTINCT b.beneficiary_id), 0), 1
    )                                                                                AS dob_completeness_pct,
    ROUND(
        COUNT(DISTINCT CASE WHEN b.mobile IS NOT NULL THEN b.beneficiary_id END)
        * 100.0 / NULLIF(COUNT(DISTINCT b.beneficiary_id), 0), 1
    )                                                                                AS mobile_completeness_pct,
    ROUND(
        COUNT(DISTINCT CASE WHEN b.photo_uri IS NOT NULL THEN b.beneficiary_id END)
        * 100.0 / NULLIF(COUNT(DISTINCT b.beneficiary_id), 0), 1
    )                                                                                AS photo_completeness_pct
FROM bm_beneficiary b
JOIN bm_household h ON b.household_id = h.household_id
GROUP BY h.home_district_code
ORDER BY total_beneficiaries DESC
""",
    },

    "D101": {
        "question": "Which districts have the highest beneficiaries per empanelled hospital?",
        "sql": """
WITH benef_dist AS (
    SELECT h.home_district_code AS district, COUNT(DISTINCT b.beneficiary_id) AS beneficiaries
    FROM bm_household h
    JOIN bm_beneficiary b ON h.household_id = b.household_id
    GROUP BY h.home_district_code
),
hosp_dist AS (
    SELECT district_name AS district, COUNT(DISTINCT hospital_id) AS hospitals
    FROM hm_hospital
    GROUP BY district_name
)
SELECT
    b.district,
    b.beneficiaries,
    COALESCE(hd.hospitals, 0)                                                        AS hospitals,
    ROUND(b.beneficiaries * 1.0 / NULLIF(hd.hospitals, 0), 1)                       AS beneficiaries_per_hospital
FROM benef_dist b
LEFT JOIN hosp_dist hd ON b.district = hd.district
ORDER BY beneficiaries_per_hospital DESC NULLS LAST
LIMIT 30
""",
    },

    "D102": {
        "question": "What is the district-wise bed capacity per 1,000 enrolled beneficiaries?",
        "sql": """
WITH beds_dist AS (
    SELECT district_name AS district, SUM(total_bed_strength) AS total_beds
    FROM hm_hospital
    GROUP BY district_name
),
benef_dist AS (
    SELECT h.home_district_code AS district, COUNT(DISTINCT b.beneficiary_id) AS beneficiaries
    FROM bm_household h
    JOIN bm_beneficiary b ON h.household_id = b.household_id
    GROUP BY h.home_district_code
)
SELECT
    bd.district,
    bd.total_beds,
    bnd.beneficiaries,
    ROUND(bd.total_beds * 1000.0 / NULLIF(bnd.beneficiaries, 0), 2)              AS beds_per_1000_beneficiaries
FROM beds_dist bd
LEFT JOIN benef_dist bnd ON bd.district = bnd.district
ORDER BY beds_per_1000_beneficiaries DESC NULLS LAST
""",
    },

    "D103": {
        "question": "What is the district-wise case rate per 1,000 enrolled beneficiaries?",
        "sql": """
WITH cases_dist AS (
    SELECT hospital_district AS district, COUNT(DISTINCT case_id) AS total_cases
    FROM cm_case
    GROUP BY hospital_district
),
benef_dist AS (
    SELECT h.home_district_code AS district, COUNT(DISTINCT b.beneficiary_id) AS beneficiaries
    FROM bm_household h
    JOIN bm_beneficiary b ON h.household_id = b.household_id
    GROUP BY h.home_district_code
)
SELECT
    bd.district,
    COALESCE(cd.total_cases, 0)                                                   AS total_cases,
    bd.beneficiaries,
    ROUND(COALESCE(cd.total_cases, 0) * 1000.0 / NULLIF(bd.beneficiaries, 0), 2) AS cases_per_1000_enrolled
FROM benef_dist bd
LEFT JOIN cases_dist cd ON bd.district = cd.district
ORDER BY cases_per_1000_enrolled DESC NULLS LAST
""",
    },

    "D104": {
        "question": "Which blocks have the highest case rate per 1,000 enrolled beneficiaries?",
        "sql": """
WITH cases_block AS (
    SELECT hh.home_block_name AS block, COUNT(DISTINCT cs.case_id) AS total_cases
    FROM cm_case cs
    JOIN bm_beneficiary b  ON cs.beneficiary_id = b.beneficiary_id
    JOIN bm_household   hh ON b.household_id    = hh.household_id
    GROUP BY hh.home_block_name
),
benef_block AS (
    SELECT h.home_block_name AS block, COUNT(DISTINCT b.beneficiary_id) AS beneficiaries
    FROM bm_household h
    JOIN bm_beneficiary b ON h.household_id = b.household_id
    GROUP BY h.home_block_name
)
SELECT
    bb.block,
    COALESCE(cb.total_cases, 0)                                                    AS total_cases,
    bb.beneficiaries,
    ROUND(COALESCE(cb.total_cases, 0) * 1000.0 / NULLIF(bb.beneficiaries, 0), 2)  AS cases_per_1000_enrolled
FROM benef_block bb
LEFT JOIN cases_block cb ON bb.block = cb.block
ORDER BY cases_per_1000_enrolled DESC NULLS LAST
LIMIT 30
""",
    },

    "D105": {
        "question": "Which districts issue Ayushman cards within 30 days of enrolment most consistently?",
        "sql": """
WITH enrol AS (
    SELECT er.beneficiary_id, MIN(er.submitted_at) AS first_submitted
    FROM bm_enrolment_request er
    WHERE er.status IN ('ISA_APPROVED', 'AUTO_APPROVED')
    GROUP BY er.beneficiary_id
),
issued AS (
    SELECT c.beneficiary_id, MIN(c.issued_at) AS first_issued
    FROM bm_card c
    GROUP BY c.beneficiary_id
),
combined AS (
    SELECT
        hh.home_district_code AS district,
        DATE_DIFF('day', e.first_submitted::DATE, i.first_issued::DATE) AS days_to_issue
    FROM enrol e
    JOIN issued i     ON e.beneficiary_id = i.beneficiary_id
    JOIN bm_beneficiary b  ON e.beneficiary_id = b.beneficiary_id
    JOIN bm_household   hh ON b.household_id   = hh.household_id
    WHERE i.first_issued IS NOT NULL AND e.first_submitted IS NOT NULL
)
SELECT
    district,
    COUNT(*)                                                                        AS total_issued,
    COUNT(CASE WHEN days_to_issue <= 30 THEN 1 END)                                AS issued_within_30d,
    ROUND(
        COUNT(CASE WHEN days_to_issue <= 30 THEN 1 END) * 100.0 / NULLIF(COUNT(*), 0), 1
    )                                                                               AS pct_within_30d
FROM combined
GROUP BY district
ORDER BY pct_within_30d DESC NULLS LAST
LIMIT 30
""",
    },

    "D106": {
        "question": "Which districts have the highest share of beneficiaries whose first admission occurred within 30 days of enrolment?",
        "sql": """
WITH first_enrol AS (
    SELECT beneficiary_id, MIN(submitted_at) AS first_submitted
    FROM bm_enrolment_request
    WHERE status IN ('ISA_APPROVED', 'AUTO_APPROVED')
    GROUP BY beneficiary_id
),
first_admit AS (
    SELECT beneficiary_id, MIN(admission_datetime) AS first_admission
    FROM cm_case
    GROUP BY beneficiary_id
)
SELECT
    hh.home_district_code                                                           AS district,
    COUNT(DISTINCT b.beneficiary_id)                                                AS enrolled_with_case,
    COUNT(DISTINCT CASE
        WHEN DATE_DIFF('day', fe.first_submitted::DATE, fa.first_admission::DATE) <= 30
        THEN b.beneficiary_id
    END)                                                                            AS admitted_within_30d,
    ROUND(
        COUNT(DISTINCT CASE
            WHEN DATE_DIFF('day', fe.first_submitted::DATE, fa.first_admission::DATE) <= 30
            THEN b.beneficiary_id
        END) * 100.0 / NULLIF(COUNT(DISTINCT b.beneficiary_id), 0), 1
    )                                                                               AS pct_admitted_within_30d
FROM bm_beneficiary b
JOIN bm_household hh   ON b.household_id   = hh.household_id
JOIN first_enrol  fe   ON b.beneficiary_id = fe.beneficiary_id
JOIN first_admit  fa   ON b.beneficiary_id = fa.beneficiary_id
GROUP BY hh.home_district_code
ORDER BY pct_admitted_within_30d DESC NULLS LAST
""",
    },

    "D107": {
        "question": "Which districts have the highest share of out-of-district treatment?",
        "sql": """
SELECT
    hh.home_district_code                                                           AS home_district,
    COUNT(DISTINCT cs.case_id)                                                      AS total_cases,
    COUNT(DISTINCT CASE WHEN cs.hospital_district != hh.home_district_code THEN cs.case_id END) AS out_of_district_cases,
    ROUND(
        COUNT(DISTINCT CASE WHEN cs.hospital_district != hh.home_district_code THEN cs.case_id END)
        * 100.0 / NULLIF(COUNT(DISTINCT cs.case_id), 0), 1
    )                                                                               AS out_of_district_pct
FROM cm_case cs
JOIN bm_beneficiary b  ON cs.beneficiary_id = b.beneficiary_id
JOIN bm_household   hh ON b.household_id    = hh.household_id
GROUP BY hh.home_district_code
ORDER BY out_of_district_pct DESC NULLS LAST
""",
    },

    "D108": {
        "question": "Which districts are net exporters and net importers of patients?",
        "sql": """
WITH outflows AS (
    SELECT hh.home_district_code AS district, COUNT(*) AS outflow
    FROM cm_case cs
    JOIN bm_beneficiary b  ON cs.beneficiary_id = b.beneficiary_id
    JOIN bm_household   hh ON b.household_id    = hh.household_id
    WHERE cs.hospital_district != hh.home_district_code
    GROUP BY hh.home_district_code
),
inflows AS (
    SELECT cs.hospital_district AS district, COUNT(*) AS inflow
    FROM cm_case cs
    JOIN bm_beneficiary b  ON cs.beneficiary_id = b.beneficiary_id
    JOIN bm_household   hh ON b.household_id    = hh.household_id
    WHERE cs.hospital_district != hh.home_district_code
    GROUP BY cs.hospital_district
),
all_districts AS (
    SELECT district FROM outflows
    UNION
    SELECT district FROM inflows
)
SELECT
    ad.district,
    COALESCE(i.inflow, 0)                              AS inflow,
    COALESCE(o.outflow, 0)                             AS outflow,
    COALESCE(i.inflow, 0) - COALESCE(o.outflow, 0)    AS net_flow,
    CASE
        WHEN COALESCE(i.inflow, 0) - COALESCE(o.outflow, 0) > 0 THEN 'NET_IMPORTER'
        WHEN COALESCE(i.inflow, 0) - COALESCE(o.outflow, 0) < 0 THEN 'NET_EXPORTER'
        ELSE 'BALANCED'
    END                                                AS flow_type
FROM all_districts ad
LEFT JOIN inflows  i ON ad.district = i.district
LEFT JOIN outflows o ON ad.district = o.district
ORDER BY net_flow DESC
""",
    },

    "D109": {
        "question": "What is the district-to-district patient flow matrix for treatment?",
        "sql": """
SELECT
    hh.home_district_code   AS home_district,
    cs.hospital_district    AS treatment_district,
    COUNT(DISTINCT cs.case_id) AS case_count
FROM cm_case cs
JOIN bm_beneficiary b  ON cs.beneficiary_id = b.beneficiary_id
JOIN bm_household   hh ON b.household_id    = hh.household_id
WHERE cs.hospital_district != hh.home_district_code
GROUP BY hh.home_district_code, cs.hospital_district
ORDER BY case_count DESC
LIMIT 30
""",
    },

    "D110": {
        "question": "Which districts rely most heavily on private hospitals for treatment?",
        "sql": """
SELECT
    hh.home_district_code                                                           AS home_district,
    COUNT(DISTINCT cs.case_id)                                                      AS total_cases,
    COUNT(DISTINCT CASE WHEN h.hospital_type = 'PRIVATE' THEN cs.case_id END)       AS private_cases,
    ROUND(
        COUNT(DISTINCT CASE WHEN h.hospital_type = 'PRIVATE' THEN cs.case_id END)
        * 100.0 / NULLIF(COUNT(DISTINCT cs.case_id), 0), 1
    )                                                                               AS private_pct
FROM cm_case cs
JOIN hm_hospital   h   ON cs.hospital_id    = h.hospital_id
JOIN bm_beneficiary b  ON cs.beneficiary_id = b.beneficiary_id
JOIN bm_household   hh ON b.household_id    = hh.household_id
GROUP BY hh.home_district_code
ORDER BY private_pct DESC NULLS LAST
LIMIT 20
""",
    },

    "D111": {
        "question": "Which districts rely most heavily on public hospitals for treatment?",
        "sql": """
SELECT
    hh.home_district_code                                                          AS home_district,
    COUNT(DISTINCT cs.case_id)                                                     AS total_cases,
    COUNT(DISTINCT CASE WHEN h.hospital_type = 'PUBLIC' THEN cs.case_id END)       AS public_cases,
    ROUND(
        COUNT(DISTINCT CASE WHEN h.hospital_type = 'PUBLIC' THEN cs.case_id END)
        * 100.0 / NULLIF(COUNT(DISTINCT cs.case_id), 0), 1
    )                                                                              AS public_pct
FROM cm_case cs
JOIN hm_hospital   h   ON cs.hospital_id    = h.hospital_id
JOIN bm_beneficiary b  ON cs.beneficiary_id = b.beneficiary_id
JOIN bm_household   hh ON b.household_id    = hh.household_id
GROUP BY hh.home_district_code
ORDER BY public_pct DESC NULLS LAST
LIMIT 20
""",
    },

    "D112": {
        "question": "Which districts are most dependent on their top 3 hospitals for total claim volume?",
        "sql": """
WITH hospital_cases AS (
    SELECT
        cs.hospital_district                                AS district,
        cs.hospital_id,
        COUNT(DISTINCT cs.case_id)                          AS case_count
    FROM cm_case cs
    GROUP BY cs.hospital_district, cs.hospital_id
),
ranked AS (
    SELECT
        district,
        hospital_id,
        case_count,
        ROW_NUMBER() OVER (PARTITION BY district ORDER BY case_count DESC) AS rn,
        SUM(case_count) OVER (PARTITION BY district)                       AS district_total
    FROM hospital_cases
)
SELECT
    district,
    SUM(CASE WHEN rn <= 3 THEN case_count ELSE 0 END)                             AS top3_cases,
    MAX(district_total)                                                            AS district_total,
    ROUND(
        SUM(CASE WHEN rn <= 3 THEN case_count ELSE 0 END)
        * 100.0 / NULLIF(MAX(district_total), 0), 1
    )                                                                              AS top3_concentration_pct
FROM ranked
GROUP BY district
ORDER BY top3_concentration_pct DESC NULLS LAST
LIMIT 20
""",
    },

    "D113": {
        "question": "Which hospitals account for the largest intra-district share of claims?",
        "sql": """
WITH hospital_cases AS (
    SELECT
        cs.hospital_id,
        cs.hospital_district                                                        AS district,
        COUNT(DISTINCT cs.case_id)                                                  AS case_count
    FROM cm_case cs
    GROUP BY cs.hospital_id, cs.hospital_district
),
district_totals AS (
    SELECT district, SUM(case_count) AS district_total
    FROM hospital_cases
    GROUP BY district
)
SELECT
    hc.hospital_id,
    h.hospital_name,
    hc.district,
    h.hospital_type,
    hc.case_count,
    dt.district_total,
    ROUND(hc.case_count * 100.0 / NULLIF(dt.district_total, 0), 1)                AS intra_district_share_pct
FROM hospital_cases hc
JOIN district_totals dt ON hc.district = dt.district
JOIN hm_hospital     h  ON hc.hospital_id = h.hospital_id
ORDER BY intra_district_share_pct DESC NULLS LAST
LIMIT 20
""",
    },

    # ── Tier-1 Expanded: Procedures & Specialties (D116-D119) ────────────────

    "D116": {
        "question": "What is the procedure-wise spend, claimed amount, approved amount, and haircut summary?",
        "sql": """
SELECT
    pm.procedure_name,
    pm.specialty_code,
    COUNT(DISTINCT pl.preauth_id)                                                  AS preauth_count,
    ROUND(SUM(cl.amount_claimed), 2)                                               AS total_claimed,
    ROUND(SUM(cl.amount_approved), 2)                                              AS total_approved,
    ROUND(SUM(cl.amount_claimed) - SUM(cl.amount_approved), 2)                    AS haircut_amount,
    ROUND(
        (SUM(cl.amount_claimed) - SUM(cl.amount_approved))
        * 100.0 / NULLIF(SUM(cl.amount_claimed), 0), 1
    )                                                                              AS haircut_pct
FROM cm_preauth_procedure_line pl
JOIN ref_hbp_procedure_master pm ON pl.hbp_procedure_code = pm.hbp_procedure_code
JOIN cm_preauth_request       pr ON pl.preauth_id         = pr.preauth_id
JOIN cm_case                  cs ON pr.case_id            = cs.case_id
JOIN cm_claim                 cl ON cs.case_id            = cl.case_id
GROUP BY pm.procedure_name, pm.specialty_code
ORDER BY total_approved DESC NULLS LAST
LIMIT 20
""",
    },

    "D117": {
        "question": "Which procedures have the highest query rates and rejection rates?",
        "sql": """
SELECT
    pm.procedure_name,
    pm.specialty_code,
    COUNT(DISTINCT cl.claim_id)                                                    AS total_claims,
    COUNT(DISTINCT CASE WHEN cl.claim_status = 'QUERY_RAISED' THEN cl.claim_id END) AS query_count,
    COUNT(DISTINCT CASE WHEN cl.claim_status = 'REJECTED'     THEN cl.claim_id END) AS rejected_count,
    ROUND(
        COUNT(DISTINCT CASE WHEN cl.claim_status = 'QUERY_RAISED' THEN cl.claim_id END)
        * 100.0 / NULLIF(COUNT(DISTINCT cl.claim_id), 0), 1
    )                                                                              AS query_rate_pct,
    ROUND(
        COUNT(DISTINCT CASE WHEN cl.claim_status = 'REJECTED' THEN cl.claim_id END)
        * 100.0 / NULLIF(COUNT(DISTINCT cl.claim_id), 0), 1
    )                                                                              AS rejection_rate_pct
FROM cm_preauth_procedure_line pl
JOIN ref_hbp_procedure_master pm ON pl.hbp_procedure_code = pm.hbp_procedure_code
JOIN cm_preauth_request       pr ON pl.preauth_id         = pr.preauth_id
JOIN cm_case                  cs ON pr.case_id            = cs.case_id
JOIN cm_claim                 cl ON cs.case_id            = cl.case_id
GROUP BY pm.procedure_name, pm.specialty_code
HAVING COUNT(DISTINCT cl.claim_id) >= 10
ORDER BY query_rate_pct DESC NULLS LAST
LIMIT 15
""",
    },

    "D118": {
        "question": "What is the specialty-wise approval rate, rejection rate, and settlement TAT?",
        "sql": """
SELECT
    pm.specialty_code,
    pm.specialty_name,
    COUNT(DISTINCT cl.claim_id)                                                    AS total_claims,
    ROUND(
        COUNT(DISTINCT CASE WHEN cl.claim_status IN ('APPROVED','SETTLED') THEN cl.claim_id END)
        * 100.0 / NULLIF(COUNT(DISTINCT cl.claim_id), 0), 1
    )                                                                              AS approval_rate_pct,
    ROUND(
        COUNT(DISTINCT CASE WHEN cl.claim_status = 'REJECTED' THEN cl.claim_id END)
        * 100.0 / NULLIF(COUNT(DISTINCT cl.claim_id), 0), 1
    )                                                                              AS rejection_rate_pct,
    ROUND(AVG(cl.settlement_tat_days), 1)                                          AS avg_tat_days
FROM cm_preauth_procedure_line pl
JOIN ref_hbp_procedure_master pm ON pl.hbp_procedure_code = pm.hbp_procedure_code
JOIN cm_preauth_request       pr ON pl.preauth_id         = pr.preauth_id
JOIN cm_case                  cs ON pr.case_id            = cs.case_id
JOIN cm_claim                 cl ON cs.case_id            = cl.case_id
GROUP BY pm.specialty_code, pm.specialty_name
ORDER BY total_claims DESC
""",
    },

    "D119": {
        "question": "What are the top diagnosis-procedure combinations by total spend?",
        "sql": """
SELECT
    d.diagnosis_category,
    pm.procedure_name,
    COUNT(DISTINCT cs.case_id)                                                     AS case_count,
    ROUND(SUM(cl.amount_approved), 2)                                              AS total_approved
FROM cm_case_diagnosis d
JOIN cm_case                  cs ON d.case_id            = cs.case_id
JOIN cm_preauth_request       pr ON cs.case_id           = pr.case_id
JOIN cm_preauth_procedure_line pl ON pr.preauth_id       = pl.preauth_id
JOIN ref_hbp_procedure_master pm ON pl.hbp_procedure_code = pm.hbp_procedure_code
JOIN cm_claim                 cl ON cs.case_id           = cl.case_id
WHERE d.diagnosis_type = 'PRIMARY'
GROUP BY d.diagnosis_category, pm.procedure_name
ORDER BY total_approved DESC NULLS LAST
LIMIT 20
""",
    },

    # ── Tier-1 Expanded: Disease Epidemiology (D120-D122) ────────────────────

    "D120": {
        "question": "Which districts have the highest maternal/neonatal case rate per 1,000 enrolled women?",
        "sql": """
WITH maternal_cases AS (
    SELECT cs.hospital_district AS district, COUNT(DISTINCT cs.case_id) AS mat_cases
    FROM cm_case_diagnosis d
    JOIN cm_case cs ON d.case_id = cs.case_id
    JOIN bm_beneficiary b ON cs.beneficiary_id = b.beneficiary_id
    WHERE d.diagnosis_type = 'PRIMARY'
      AND d.diagnosis_category = 'MATERNAL_NEONATAL'
      AND b.gender = 'FEMALE'
    GROUP BY cs.hospital_district
),
enrolled_women AS (
    SELECT hh.home_district_code AS district, COUNT(DISTINCT b.beneficiary_id) AS women_count
    FROM bm_beneficiary b
    JOIN bm_household hh ON b.household_id = hh.household_id
    WHERE b.gender = 'FEMALE'
    GROUP BY hh.home_district_code
)
SELECT
    ew.district,
    COALESCE(mc.mat_cases, 0)                                                      AS maternal_cases,
    ew.women_count                                                                 AS enrolled_women,
    ROUND(COALESCE(mc.mat_cases, 0) * 1000.0 / NULLIF(ew.women_count, 0), 2)      AS rate_per_1000_women
FROM enrolled_women ew
LEFT JOIN maternal_cases mc ON ew.district = mc.district
ORDER BY rate_per_1000_women DESC NULLS LAST
""",
    },

    "D121": {
        "question": "Which districts have the highest NCD case rate per 1,000 enrolled beneficiaries?",
        "sql": """
WITH ncd_cases AS (
    SELECT cs.hospital_district AS district, COUNT(DISTINCT cs.case_id) AS ncd_cases
    FROM cm_case_diagnosis d
    JOIN cm_case cs ON d.case_id = cs.case_id
    WHERE d.diagnosis_type = 'PRIMARY'
      AND d.diagnosis_category = 'NCD'
    GROUP BY cs.hospital_district
),
enrolled AS (
    SELECT hh.home_district_code AS district, COUNT(DISTINCT b.beneficiary_id) AS beneficiaries
    FROM bm_household hh
    JOIN bm_beneficiary b ON hh.household_id = b.household_id
    GROUP BY hh.home_district_code
)
SELECT
    en.district,
    COALESCE(nc.ncd_cases, 0)                                                      AS ncd_cases,
    en.beneficiaries,
    ROUND(COALESCE(nc.ncd_cases, 0) * 1000.0 / NULLIF(en.beneficiaries, 0), 2)    AS ncd_rate_per_1000
FROM enrolled en
LEFT JOIN ncd_cases nc ON en.district = nc.district
ORDER BY ncd_rate_per_1000 DESC NULLS LAST
""",
    },

    "D122": {
        "question": "Which districts have the highest communicable disease case rate per 1,000 enrolled beneficiaries?",
        "sql": """
WITH comm_cases AS (
    SELECT cs.hospital_district AS district, COUNT(DISTINCT cs.case_id) AS comm_cases
    FROM cm_case_diagnosis d
    JOIN cm_case cs ON d.case_id = cs.case_id
    WHERE d.diagnosis_type = 'PRIMARY'
      AND d.diagnosis_category = 'COMMUNICABLE'
    GROUP BY cs.hospital_district
),
enrolled AS (
    SELECT hh.home_district_code AS district, COUNT(DISTINCT b.beneficiary_id) AS beneficiaries
    FROM bm_household hh
    JOIN bm_beneficiary b ON hh.household_id = b.household_id
    GROUP BY hh.home_district_code
)
SELECT
    en.district,
    COALESCE(cc.comm_cases, 0)                                                     AS communicable_cases,
    en.beneficiaries,
    ROUND(COALESCE(cc.comm_cases, 0) * 1000.0 / NULLIF(en.beneficiaries, 0), 2)   AS comm_rate_per_1000
FROM enrolled en
LEFT JOIN comm_cases cc ON en.district = cc.district
ORDER BY comm_rate_per_1000 DESC NULLS LAST
""",
    },

    # ── Tier-1 Expanded: Access Gaps (D123-D124) ─────────────────────────────

    "D123": {
        "question": "Which blocks have high enrolled population but no empanelled hospital?",
        "sql": """
WITH blocks_with_hospitals AS (
    SELECT DISTINCT block_name FROM hm_hospital WHERE block_name IS NOT NULL
),
block_beneficiaries AS (
    SELECT hh.home_block_name AS block_name, COUNT(DISTINCT b.beneficiary_id) AS beneficiaries
    FROM bm_household hh
    JOIN bm_beneficiary b ON hh.household_id = b.household_id
    GROUP BY hh.home_block_name
)
SELECT
    bb.block_name,
    bb.beneficiaries
FROM block_beneficiaries bb
LEFT JOIN blocks_with_hospitals bwh ON bb.block_name = bwh.block_name
WHERE bwh.block_name IS NULL
  AND bb.beneficiaries > 100
ORDER BY bb.beneficiaries DESC
""",
    },

    "D124": {
        "question": "Which blocks have no empanelled hospitals but still generate high case volumes?",
        "sql": """
WITH blocks_with_hospitals AS (
    SELECT DISTINCT block_name FROM hm_hospital WHERE block_name IS NOT NULL
),
block_cases AS (
    SELECT hh.home_block_name AS block_name, COUNT(DISTINCT cs.case_id) AS case_count
    FROM cm_case cs
    JOIN bm_beneficiary b  ON cs.beneficiary_id = b.beneficiary_id
    JOIN bm_household   hh ON b.household_id    = hh.household_id
    GROUP BY hh.home_block_name
)
SELECT
    bc.block_name,
    bc.case_count
FROM block_cases bc
LEFT JOIN blocks_with_hospitals bwh ON bc.block_name = bwh.block_name
WHERE bwh.block_name IS NULL
ORDER BY bc.case_count DESC
LIMIT 20
""",
    },

    # ── Tier-1 Expanded: Portability (D125-D126) ─────────────────────────────

    "D125": {
        "question": "What is the portability destination mix by home district?",
        "sql": """
SELECT
    hh.home_district_code   AS home_district,
    cs.hospital_division    AS destination_division,
    COUNT(DISTINCT cs.case_id) AS portability_cases,
    ROUND(
        COUNT(DISTINCT cs.case_id) * 100.0
        / SUM(COUNT(DISTINCT cs.case_id)) OVER (PARTITION BY hh.home_district_code), 1
    )                       AS pct_of_home_district_portability
FROM cm_case cs
JOIN bm_beneficiary b  ON cs.beneficiary_id = b.beneficiary_id
JOIN bm_household   hh ON b.household_id    = hh.household_id
WHERE cs.is_portability = TRUE
GROUP BY hh.home_district_code, cs.hospital_division
ORDER BY home_district, portability_cases DESC
""",
    },

    "D126": {
        "question": "What is the portability spend leakage by district and specialty?",
        "sql": """
SELECT
    hh.home_district_code                                                          AS home_district,
    pm.specialty_code,
    pm.specialty_name,
    COUNT(DISTINCT cs.case_id)                                                     AS portability_cases,
    ROUND(SUM(cl.amount_approved), 2)                                              AS spend_leakage
FROM cm_case cs
JOIN bm_beneficiary            b  ON cs.beneficiary_id  = b.beneficiary_id
JOIN bm_household              hh ON b.household_id     = hh.household_id
JOIN cm_claim                  cl ON cs.case_id         = cl.case_id
JOIN cm_preauth_request        pr ON cs.case_id         = pr.case_id
JOIN cm_preauth_procedure_line pl ON pr.preauth_id      = pl.preauth_id
JOIN ref_hbp_procedure_master  pm ON pl.hbp_procedure_code = pm.hbp_procedure_code
WHERE cs.is_portability = TRUE
GROUP BY hh.home_district_code, pm.specialty_code, pm.specialty_name
ORDER BY spend_leakage DESC NULLS LAST
""",
    },

    # ── Tier-1 Expanded: Payment & Claims Quality (D127-D129) ────────────────

    "D127": {
        "question": "Which hospitals have the highest failed-payment frequency and amount?",
        "sql": """
SELECT
    h.hospital_id,
    h.hospital_name,
    h.district_name,
    h.hospital_type,
    COUNT(DISTINCT p.claim_id)                                                     AS failed_payment_count,
    ROUND(SUM(p.amount_paid), 2)                                                   AS failed_amount
FROM cm_payment p
JOIN cm_claim    cl ON p.claim_id    = cl.claim_id
JOIN cm_case     cs ON cl.case_id   = cs.case_id
JOIN hm_hospital h  ON cs.hospital_id = h.hospital_id
WHERE p.payment_status = 'FAILED'
GROUP BY h.hospital_id, h.hospital_name, h.district_name, h.hospital_type
ORDER BY failed_payment_count DESC NULLS LAST
LIMIT 20
""",
    },

    "D128": {
        "question": "Which hospitals have the highest rate of claim queries?",
        "sql": """
SELECT
    h.hospital_id,
    h.hospital_name,
    h.district_name,
    h.hospital_type,
    COUNT(DISTINCT cl.claim_id)                                                    AS total_claims,
    COUNT(DISTINCT CASE WHEN cl.claim_status = 'QUERY_RAISED' THEN cl.claim_id END) AS query_claims,
    ROUND(
        COUNT(DISTINCT CASE WHEN cl.claim_status = 'QUERY_RAISED' THEN cl.claim_id END)
        * 100.0 / NULLIF(COUNT(DISTINCT cl.claim_id), 0), 1
    )                                                                              AS query_rate_pct
FROM cm_claim cl
JOIN cm_case     cs ON cl.case_id   = cs.case_id
JOIN hm_hospital h  ON cs.hospital_id = h.hospital_id
GROUP BY h.hospital_id, h.hospital_name, h.district_name, h.hospital_type
HAVING COUNT(DISTINCT cl.claim_id) >= 10
ORDER BY query_rate_pct DESC NULLS LAST
LIMIT 20
""",
    },

    "D129": {
        "question": "Which hospitals have the highest rate of diagnosis-package mismatch queries or rejections?",
        "sql": """
SELECT
    h.hospital_id,
    h.hospital_name,
    h.district_name,
    h.hospital_type,
    ae.reason_category,
    COUNT(DISTINCT cl.claim_id)                                                    AS affected_claims,
    ROUND(
        COUNT(DISTINCT cl.claim_id) * 100.0
        / NULLIF(COUNT(DISTINCT cl.claim_id) OVER (PARTITION BY h.hospital_id), 0), 1
    )                                                                              AS pct_of_hospital_claims
FROM cm_adjudication_event ae
JOIN cm_claim    cl ON ae.claim_id   = cl.claim_id
JOIN cm_case     cs ON cl.case_id   = cs.case_id
JOIN hm_hospital h  ON cs.hospital_id = h.hospital_id
WHERE ae.reason_category ILIKE '%mismatch%'
   OR ae.reason_category ILIKE '%diagnosis%'
GROUP BY h.hospital_id, h.hospital_name, h.district_name, h.hospital_type, ae.reason_category
ORDER BY affected_claims DESC NULLS LAST
LIMIT 20
""",
    },

    # ── Tier-1 Expanded: Clinical Quality (D130-D133) ────────────────────────

    "D130": {
        "question": "Which hospitals have the highest 30-day readmission rates?",
        "sql": """
WITH case_discharge AS (
    SELECT
        cs.case_id,
        cs.beneficiary_id,
        cs.hospital_id,
        cs.discharge_datetime,
        LAG(cs.discharge_datetime) OVER (
            PARTITION BY cs.beneficiary_id ORDER BY cs.admission_datetime
        ) AS prev_discharge
    FROM cm_case cs
    WHERE cs.discharge_datetime IS NOT NULL
),
readmits AS (
    SELECT
        hospital_id,
        case_id,
        CASE
            WHEN DATE_DIFF('day', prev_discharge::DATE, discharge_datetime::DATE) <= 30
             AND prev_discharge IS NOT NULL
            THEN 1 ELSE 0
        END AS is_readmit
    FROM case_discharge
)
SELECT
    h.hospital_id,
    h.hospital_name,
    h.district_name,
    h.hospital_type,
    COUNT(DISTINCT r.case_id)                                                      AS total_cases,
    SUM(r.is_readmit)                                                              AS readmissions,
    ROUND(SUM(r.is_readmit) * 100.0 / NULLIF(COUNT(DISTINCT r.case_id), 0), 1)    AS readmission_rate_pct
FROM readmits r
JOIN hm_hospital h ON r.hospital_id = h.hospital_id
GROUP BY h.hospital_id, h.hospital_name, h.district_name, h.hospital_type
HAVING COUNT(DISTINCT r.case_id) >= 50
ORDER BY readmission_rate_pct DESC NULLS LAST
LIMIT 20
""",
    },

    "D131": {
        "question": "What is the mortality rate by diagnosis category?",
        "sql": """
SELECT
    d.diagnosis_category,
    COUNT(DISTINCT cs.case_id)                                                     AS total_cases,
    COUNT(DISTINCT CASE WHEN dis.death_date IS NOT NULL THEN cs.case_id END)       AS deaths,
    ROUND(
        COUNT(DISTINCT CASE WHEN dis.death_date IS NOT NULL THEN cs.case_id END)
        * 100.0 / NULLIF(COUNT(DISTINCT cs.case_id), 0), 2
    )                                                                              AS mortality_rate_pct
FROM cm_case_diagnosis d
JOIN cm_case    cs  ON d.case_id  = cs.case_id
JOIN cm_discharge dis ON cs.case_id = dis.case_id
WHERE d.diagnosis_type = 'PRIMARY'
GROUP BY d.diagnosis_category
ORDER BY mortality_rate_pct DESC NULLS LAST
""",
    },

    "D133": {
        "question": "What is the district-wise rate of biometric authentication at discharge and medicine provision?",
        "sql": """
SELECT
    cs.hospital_district                                                           AS district,
    COUNT(DISTINCT cs.case_id)                                                     AS total_discharges,
    COUNT(DISTINCT CASE WHEN dis.biometric_auth_used = TRUE THEN cs.case_id END)   AS biometric_auth_count,
    COUNT(DISTINCT CASE WHEN dis.provided_medicines_flag = TRUE THEN cs.case_id END) AS medicines_provided_count,
    ROUND(
        COUNT(DISTINCT CASE WHEN dis.biometric_auth_used = TRUE THEN cs.case_id END)
        * 100.0 / NULLIF(COUNT(DISTINCT cs.case_id), 0), 1
    )                                                                              AS biometric_rate_pct,
    ROUND(
        COUNT(DISTINCT CASE WHEN dis.provided_medicines_flag = TRUE THEN cs.case_id END)
        * 100.0 / NULLIF(COUNT(DISTINCT cs.case_id), 0), 1
    )                                                                              AS medicine_provision_rate_pct
FROM cm_case cs
JOIN cm_discharge dis ON cs.case_id = dis.case_id
GROUP BY cs.hospital_district
ORDER BY total_discharges DESC
""",
    },

    "D134": {
        "question": "What is the average lag from discharge to claim submission by district?",
        "sql": """
SELECT
    cs.hospital_district                                                           AS district,
    COUNT(DISTINCT cl.claim_id)                                                    AS claim_count,
    ROUND(AVG(DATE_DIFF('day', cs.discharge_datetime::DATE, cl.submitted_at::DATE)), 1) AS avg_lag_days,
    ROUND(
        PERCENTILE_CONT(0.50) WITHIN GROUP (
            ORDER BY DATE_DIFF('day', cs.discharge_datetime::DATE, cl.submitted_at::DATE)
        ), 1
    )                                                                              AS median_lag_days
FROM cm_case cs
JOIN cm_claim cl ON cs.case_id = cl.case_id
WHERE cs.discharge_datetime IS NOT NULL
  AND cl.submitted_at IS NOT NULL
GROUP BY cs.hospital_district
ORDER BY avg_lag_days DESC NULLS LAST
LIMIT 30
""",
    },

    # ── Tier-1 Expanded: Fraud & Integrity (D135-D137) ───────────────────────

    "D135": {
        "question": "Which clinicians have the highest case volumes and what procedures are they associated with?",
        "sql": """
WITH clinician_cases AS (
    SELECT
        pl.clinician_staff_id,
        COUNT(DISTINCT pr.case_id) AS case_count
    FROM cm_preauth_procedure_line pl
    JOIN cm_preauth_request pr ON pl.preauth_id = pr.preauth_id
    GROUP BY pl.clinician_staff_id
),
top_procedure AS (
    SELECT DISTINCT ON (pl.clinician_staff_id)
        pl.clinician_staff_id,
        pm.procedure_name AS top_procedure
    FROM cm_preauth_procedure_line pl
    JOIN ref_hbp_procedure_master pm ON pl.hbp_procedure_code = pm.hbp_procedure_code
    ORDER BY pl.clinician_staff_id,
             COUNT(pl.preauth_id) OVER (PARTITION BY pl.clinician_staff_id, pl.hbp_procedure_code) DESC
)
SELECT
    cc.clinician_staff_id,
    s.name                                                                         AS clinician_name,
    s.hospital_id,
    h.hospital_name,
    cc.case_count,
    tp.top_procedure
FROM clinician_cases cc
JOIN hm_staff        s  ON cc.clinician_staff_id = s.staff_id
JOIN hm_hospital     h  ON s.hospital_id         = h.hospital_id
LEFT JOIN top_procedure tp ON cc.clinician_staff_id = tp.clinician_staff_id
ORDER BY cc.case_count DESC NULLS LAST
LIMIT 20
""",
    },

    "D136": {
        "question": "Which districts show reserved public-hospital-only procedures being billed by private hospitals?",
        "sql": """
SELECT
    cs.hospital_district                                                           AS district,
    pm.hbp_procedure_code,
    pm.procedure_name,
    COUNT(DISTINCT cs.case_id)                                                     AS private_cases,
    COUNT(DISTINCT h.hospital_id)                                                  AS private_hospitals_billing
FROM ref_hbp_procedure_master  pm
JOIN cm_preauth_procedure_line pl ON pm.hbp_procedure_code = pl.hbp_procedure_code
JOIN cm_preauth_request        pr ON pl.preauth_id         = pr.preauth_id
JOIN cm_case                   cs ON pr.case_id            = cs.case_id
JOIN hm_hospital               h  ON cs.hospital_id        = h.hospital_id
WHERE pm.reserved_public_hospitals_only = TRUE
  AND h.hospital_type = 'PRIVATE'
GROUP BY cs.hospital_district, pm.hbp_procedure_code, pm.procedure_name
ORDER BY private_cases DESC NULLS LAST
""",
    },

    "D137": {
        "question": "Which districts have the highest combination of duplicate beneficiaries and enrolment rejections?",
        "sql": """
WITH dup_rate AS (
    SELECT
        hh.home_district_code                                                      AS district,
        COUNT(DISTINCT b.beneficiary_id)                                           AS total_beneficiaries,
        COUNT(DISTINCT CASE WHEN b.is_duplicate = TRUE THEN b.beneficiary_id END)  AS duplicate_count,
        ROUND(
            COUNT(DISTINCT CASE WHEN b.is_duplicate = TRUE THEN b.beneficiary_id END)
            * 100.0 / NULLIF(COUNT(DISTINCT b.beneficiary_id), 0), 1
        )                                                                          AS duplicate_rate_pct
    FROM bm_beneficiary b
    JOIN bm_household hh ON b.household_id = hh.household_id
    GROUP BY hh.home_district_code
),
rejection_rate AS (
    SELECT
        hh.home_district_code                                                      AS district,
        COUNT(DISTINCT er.enrolment_request_id)                                    AS total_requests,
        COUNT(DISTINCT CASE WHEN er.status = 'REJECTED' THEN er.enrolment_request_id END) AS rejected_count,
        ROUND(
            COUNT(DISTINCT CASE WHEN er.status = 'REJECTED' THEN er.enrolment_request_id END)
            * 100.0 / NULLIF(COUNT(DISTINCT er.enrolment_request_id), 0), 1
        )                                                                          AS rejection_rate_pct
    FROM bm_enrolment_request er
    JOIN bm_beneficiary b  ON er.beneficiary_id = b.beneficiary_id
    JOIN bm_household   hh ON b.household_id    = hh.household_id
    GROUP BY hh.home_district_code
)
SELECT
    dr.district,
    dr.total_beneficiaries,
    dr.duplicate_rate_pct,
    rr.rejection_rate_pct,
    RANK() OVER (ORDER BY dr.duplicate_rate_pct DESC NULLS LAST)  AS dup_rank,
    RANK() OVER (ORDER BY rr.rejection_rate_pct DESC NULLS LAST)  AS rej_rank
FROM dup_rate dr
LEFT JOIN rejection_rate rr ON dr.district = rr.district
ORDER BY (dr.duplicate_rate_pct + COALESCE(rr.rejection_rate_pct, 0)) DESC NULLS LAST
LIMIT 20
""",
    },

    # ── Tier-1 Expanded: Concentration & Equity (D138-D143) ──────────────────

    "D138": {
        "question": "What share of each district's total spend goes to its top 5 hospitals?",
        "sql": """
WITH hospital_spend AS (
    SELECT
        cs.hospital_district                                                       AS district,
        cs.hospital_id,
        SUM(cl.amount_approved)                                                    AS hospital_spend
    FROM cm_case cs
    JOIN cm_claim cl ON cs.case_id = cl.case_id
    GROUP BY cs.hospital_district, cs.hospital_id
),
ranked AS (
    SELECT
        district,
        hospital_id,
        hospital_spend,
        ROW_NUMBER() OVER (PARTITION BY district ORDER BY hospital_spend DESC)    AS rn,
        SUM(hospital_spend) OVER (PARTITION BY district)                          AS district_total
    FROM hospital_spend
)
SELECT
    district,
    ROUND(SUM(CASE WHEN rn <= 5 THEN hospital_spend ELSE 0 END), 2)               AS top5_spend,
    ROUND(MAX(district_total), 2)                                                  AS district_total_spend,
    ROUND(
        SUM(CASE WHEN rn <= 5 THEN hospital_spend ELSE 0 END)
        * 100.0 / NULLIF(MAX(district_total), 0), 1
    )                                                                              AS top5_concentration_pct
FROM ranked
GROUP BY district
ORDER BY top5_concentration_pct DESC NULLS LAST
""",
    },

    "D139": {
        "question": "Which districts are above state average on utilization but below state average on approval rate?",
        "sql": """
WITH district_metrics AS (
    SELECT
        hh.home_district_code                                                      AS district,
        COUNT(DISTINCT b.beneficiary_id)                                           AS enrolled,
        COUNT(DISTINCT cs.case_id)                                                 AS total_cases,
        ROUND(COUNT(DISTINCT cs.case_id) * 1000.0 / NULLIF(COUNT(DISTINCT b.beneficiary_id), 0), 2) AS utilization_per_1000,
        ROUND(AVG(cl.amount_approved * 100.0 / NULLIF(cl.amount_claimed, 0)), 1)   AS avg_approval_rate_pct
    FROM bm_household   hh
    JOIN bm_beneficiary b  ON hh.household_id   = b.household_id
    LEFT JOIN cm_case   cs ON b.beneficiary_id  = cs.beneficiary_id
    LEFT JOIN cm_claim  cl ON cs.case_id        = cl.case_id
    GROUP BY hh.home_district_code
),
state_avgs AS (
    SELECT
        AVG(utilization_per_1000)  AS state_avg_utilization,
        AVG(avg_approval_rate_pct) AS state_avg_approval_rate
    FROM district_metrics
)
SELECT
    dm.district,
    dm.enrolled,
    dm.total_cases,
    dm.utilization_per_1000,
    dm.avg_approval_rate_pct,
    sa.state_avg_utilization,
    sa.state_avg_approval_rate
FROM district_metrics dm
CROSS JOIN state_avgs sa
WHERE dm.utilization_per_1000   > sa.state_avg_utilization
  AND dm.avg_approval_rate_pct  < sa.state_avg_approval_rate
ORDER BY dm.utilization_per_1000 DESC NULLS LAST
""",
    },

    "D140": {
        "question": "Which districts are below state average on utilization and above state average on settlement TAT?",
        "sql": """
WITH district_metrics AS (
    SELECT
        hh.home_district_code                                                      AS district,
        COUNT(DISTINCT b.beneficiary_id)                                           AS enrolled,
        COUNT(DISTINCT cs.case_id)                                                 AS total_cases,
        ROUND(COUNT(DISTINCT cs.case_id) * 1000.0 / NULLIF(COUNT(DISTINCT b.beneficiary_id), 0), 2) AS utilization_per_1000,
        ROUND(AVG(cl.settlement_tat_days), 1)                                      AS avg_tat_days
    FROM bm_household   hh
    JOIN bm_beneficiary b  ON hh.household_id   = b.household_id
    LEFT JOIN cm_case   cs ON b.beneficiary_id  = cs.beneficiary_id
    LEFT JOIN cm_claim  cl ON cs.case_id        = cl.case_id
    WHERE cl.settlement_tat_days IS NOT NULL
    GROUP BY hh.home_district_code
),
state_avgs AS (
    SELECT
        AVG(utilization_per_1000) AS state_avg_utilization,
        AVG(avg_tat_days)         AS state_avg_tat
    FROM district_metrics
)
SELECT
    dm.district,
    dm.enrolled,
    dm.total_cases,
    dm.utilization_per_1000,
    dm.avg_tat_days,
    ROUND(sa.state_avg_utilization, 2) AS state_avg_utilization,
    ROUND(sa.state_avg_tat, 1)         AS state_avg_tat
FROM district_metrics dm
CROSS JOIN state_avgs sa
WHERE dm.utilization_per_1000 < sa.state_avg_utilization
  AND dm.avg_tat_days          > sa.state_avg_tat
ORDER BY dm.avg_tat_days DESC NULLS LAST
""",
    },

    "D141": {
        "question": "Which blocks have the weakest access profile based on enrolment, utilization, hospital presence, and out-of-block care?",
        "sql": """
WITH block_enrolled AS (
    SELECT hh.home_block_name AS block, COUNT(DISTINCT b.beneficiary_id) AS enrolled
    FROM bm_household hh
    JOIN bm_beneficiary b ON hh.household_id = b.household_id
    GROUP BY hh.home_block_name
),
block_cases AS (
    SELECT hh.home_block_name AS block, COUNT(DISTINCT cs.case_id) AS total_cases
    FROM cm_case cs
    JOIN bm_beneficiary b  ON cs.beneficiary_id = b.beneficiary_id
    JOIN bm_household   hh ON b.household_id    = hh.household_id
    GROUP BY hh.home_block_name
),
block_outside AS (
    SELECT hh.home_block_name AS block,
           COUNT(DISTINCT CASE WHEN cs.hospital_id NOT IN (
               SELECT hospital_id FROM hm_hospital WHERE block_name = hh.home_block_name
           ) THEN cs.case_id END) AS outside_cases
    FROM cm_case cs
    JOIN bm_beneficiary b  ON cs.beneficiary_id = b.beneficiary_id
    JOIN bm_household   hh ON b.household_id    = hh.household_id
    GROUP BY hh.home_block_name
),
block_hospitals AS (
    SELECT block_name AS block, COUNT(DISTINCT hospital_id) AS hospital_count
    FROM hm_hospital
    GROUP BY block_name
)
SELECT
    be.block,
    be.enrolled,
    COALESCE(bc.total_cases, 0)                                                    AS total_cases,
    COALESCE(bh.hospital_count, 0)                                                 AS hospitals_in_block,
    ROUND(COALESCE(bc.total_cases, 0) * 1000.0 / NULLIF(be.enrolled, 0), 2)       AS case_rate_per_1000,
    ROUND(
        COALESCE(bo.outside_cases, 0) * 100.0 / NULLIF(COALESCE(bc.total_cases, 0), 0), 1
    )                                                                              AS pct_treated_outside_block
FROM block_enrolled be
LEFT JOIN block_cases    bc ON be.block = bc.block
LEFT JOIN block_hospitals bh ON be.block = bh.block
LEFT JOIN block_outside  bo ON be.block = bo.block
WHERE be.enrolled > 0
ORDER BY
    COALESCE(bh.hospital_count, 0) ASC,
    case_rate_per_1000 ASC NULLS LAST,
    be.enrolled DESC
LIMIT 20
""",
    },

    "D142": {
        "question": "Which districts are strongest and weakest on enrolment-to-treatment conversion rates?",
        "sql": """
WITH enrolled AS (
    SELECT hh.home_district_code AS district, COUNT(DISTINCT b.beneficiary_id) AS enrolled
    FROM bm_household hh
    JOIN bm_beneficiary b ON hh.household_id = b.household_id
    GROUP BY hh.home_district_code
),
treated AS (
    SELECT hh.home_district_code AS district, COUNT(DISTINCT b.beneficiary_id) AS treated
    FROM cm_case cs
    JOIN bm_beneficiary b  ON cs.beneficiary_id = b.beneficiary_id
    JOIN bm_household   hh ON b.household_id    = hh.household_id
    GROUP BY hh.home_district_code
)
SELECT
    en.district,
    en.enrolled,
    COALESCE(tr.treated, 0)                                                        AS treated,
    ROUND(COALESCE(tr.treated, 0) * 100.0 / NULLIF(en.enrolled, 0), 2)            AS conversion_rate_pct
FROM enrolled en
LEFT JOIN treated tr ON en.district = tr.district
ORDER BY conversion_rate_pct DESC NULLS LAST
""",
    },

    "D143": {
        "question": "Which districts have the highest concentration of scheme expenditure in a single hospital?",
        "sql": """
WITH hospital_spend AS (
    SELECT
        cs.hospital_district                                                       AS district,
        cs.hospital_id,
        SUM(cl.amount_approved)                                                    AS hospital_spend
    FROM cm_case cs
    JOIN cm_claim cl ON cs.case_id = cl.case_id
    GROUP BY cs.hospital_district, cs.hospital_id
),
district_totals AS (
    SELECT district, SUM(hospital_spend) AS district_total
    FROM hospital_spend
    GROUP BY district
),
top_hospital AS (
    SELECT
        hs.district,
        MAX(hs.hospital_spend) AS top_hospital_spend
    FROM hospital_spend hs
    GROUP BY hs.district
)
SELECT
    dt.district,
    ROUND(dt.district_total, 2)                                                    AS district_total_spend,
    ROUND(th.top_hospital_spend, 2)                                                AS top_hospital_spend,
    ROUND(th.top_hospital_spend * 100.0 / NULLIF(dt.district_total, 0), 1)        AS top_hospital_concentration_pct
FROM district_totals dt
JOIN top_hospital th ON dt.district = th.district
ORDER BY top_hospital_concentration_pct DESC NULLS LAST
LIMIT 20
""",
    },
}
