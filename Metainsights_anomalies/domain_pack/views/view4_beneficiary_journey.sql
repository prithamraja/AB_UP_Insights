-- ============================================================================
-- View 4 — Beneficiary Journey   (grain: one row per beneficiary_id)
-- ============================================================================
-- Enrolment quality, scheme-access equity, demographic utilisation. Anchored on
-- bm_beneficiary. Latest enrolment request and latest card per beneficiary;
-- document + claim rollups fill 0 where absent. Intermediate join columns
-- (household_id, created_at, card_issued_at, first_admission_date) are dropped
-- from the final output.
-- ============================================================================

WITH enrol_latest AS (
    SELECT beneficiary_id, status AS enrolment_status, auth_mode
    FROM stg_bm_enrolment_request
    QUALIFY row_number() OVER (PARTITION BY beneficiary_id ORDER BY submitted_at DESC) = 1
),

card_latest AS (
    SELECT beneficiary_id, card_status, issued_at AS card_issued_at
    FROM stg_bm_card
    QUALIFY row_number() OVER (PARTITION BY beneficiary_id ORDER BY issued_at DESC) = 1
),

doc_agg AS (
    SELECT beneficiary_id,
           count(id_doc_id)                                       AS document_count,
           max(CASE WHEN doc_type = 'AADHAAR' THEN 1 ELSE 0 END)  AS has_aadhaar
    FROM stg_bm_id_document
    GROUP BY beneficiary_id
),

-- Claim history per beneficiary. cm_case LEFT join cm_claim (not deduped, as in
-- the old view). sums use coalesce->0 to mirror pandas' min_count=0 behaviour
-- (an all-NULL amount group sums to 0.0, not NULL).
benef_claims AS (
    SELECT c.beneficiary_id,
           count(c.case_id)                     AS claim_count,
           coalesce(sum(cl.amount_claimed), 0)  AS total_amount_claimed,
           coalesce(sum(cl.amount_approved), 0) AS total_amount_approved,
           min(c.admission_datetime)            AS first_admission_date
    FROM stg_cm_case AS c
    LEFT JOIN stg_cm_claim AS cl ON c.case_id = cl.case_id
    GROUP BY c.beneficiary_id
),

joined AS (
    SELECT
        b.beneficiary_id,
        b.gender,
        b.age_group,
        b.bis_record_status,
        b.is_duplicate,
        h.home_division_name AS division,
        h.home_district_code AS district,
        h.entitlement_source,
        el.enrolment_status,
        el.auth_mode,
        cardl.card_status,
        coalesce(d.document_count, 0) AS document_count,
        coalesce(d.has_aadhaar, 0)    AS has_aadhaar,
        coalesce(bc.claim_count, 0)   AS claim_count,
        bc.total_amount_claimed,
        bc.total_amount_approved,
        b.created_at,
        cardl.card_issued_at,
        bc.first_admission_date
    FROM stg_bm_beneficiary AS b
    LEFT JOIN stg_bm_household AS h     ON b.household_id  = h.household_id
    LEFT JOIN enrol_latest     AS el    ON b.beneficiary_id = el.beneficiary_id
    LEFT JOIN card_latest      AS cardl ON b.beneficiary_id = cardl.beneficiary_id
    LEFT JOIN doc_agg          AS d     ON b.beneficiary_id = d.beneficiary_id
    LEFT JOIN benef_claims     AS bc    ON b.beneficiary_id = bc.beneficiary_id
)

SELECT
    beneficiary_id,
    gender,
    age_group,
    bis_record_status,
    is_duplicate,
    division,
    district,
    entitlement_source,
    enrolment_status,
    auth_mode,
    card_status,
    CAST(document_count AS BIGINT)          AS document_count,
    CAST(has_aadhaar AS BIGINT)             AS has_aadhaar,
    CAST(claim_count AS BIGINT)             AS claim_count,
    CAST(total_amount_claimed AS DOUBLE)    AS total_amount_claimed,
    CAST(total_amount_approved AS DOUBLE)   AS total_amount_approved,
    CAST(CASE WHEN claim_count > 0 THEN 1 ELSE 0 END AS BIGINT) AS has_claim,
    CASE
        WHEN document_count = 0 THEN 'NO_DOCS'
        WHEN document_count = 1 THEN '1_DOC'
        WHEN document_count <= 3 THEN '2-3_DOCS'
        ELSE '4+_DOCS'
    END                                     AS document_count_bucket,
    CAST((epoch(card_issued_at) - epoch(created_at)) / 86400.0 AS DOUBLE)            AS days_enrolment_to_card,
    CAST((epoch(first_admission_date) - epoch(card_issued_at)) / 86400.0 AS DOUBLE) AS days_card_to_first_claim,
    CAST(CASE WHEN claim_count > 0 THEN 1 ELSE 0 END AS BIGINT) AS claim_rate
FROM joined;
