-- ============================================================================
-- View 2 — District-Month Performance Cube
-- ============================================================================
-- Grain: one row per (district x month). Five independent aggregates
-- (enrolment, cards, cases, claims, payments), each grouped to district x month
-- using a DIFFERENT date column, all attributed to the beneficiary's HOME
-- district. Combined with FULL OUTER joins; missing activity -> 0 for the 19
-- count/sum columns; ratio metrics use NULL on a zero denominator (except
-- public_private_ratio, which uses a +1 denominator).
-- ============================================================================

WITH benef_geo AS (
    SELECT b.beneficiary_id, b.household_id, b.created_at,
           h.home_district_code, h.home_division_name
    FROM stg_bm_beneficiary AS b
    LEFT JOIN stg_bm_household AS h ON b.household_id = h.household_id
),

-- Enrolment: new beneficiaries and households per district x month.
enrol AS (
    SELECT home_division_name AS division,
           home_district_code AS district,
           strftime(created_at, '%Y-%m') AS month,
           count(beneficiary_id)          AS new_beneficiaries,
           count(DISTINCT household_id)   AS new_households
    FROM benef_geo
    GROUP BY 1, 2, 3
),

-- District -> division backfill map (for district-months introduced by the
-- outer joins that have no enrolment row).
div_map AS (
    SELECT district, any_value(division) AS division
    FROM enrol
    GROUP BY district
),

-- Cards issued per district x month (beneficiary home district).
card AS (
    SELECT g.home_district_code AS district,
           strftime(cd.issued_at, '%Y-%m') AS month,
           count(cd.card_id) AS cards_issued
    FROM stg_bm_card AS cd
    LEFT JOIN benef_geo AS g ON cd.beneficiary_id = g.beneficiary_id
    GROUP BY 1, 2
),

-- Cases admitted per district x month (patient home district, not hospital's).
cases AS (
    SELECT g.home_district_code AS district,
           strftime(c.admission_datetime, '%Y-%m') AS month,
           count(c.case_id)                                    AS cases_admitted,
           sum(c.is_emergency)                                 AS emergency_cases,
           sum(CASE WHEN c.is_portability THEN 1 ELSE 0 END)   AS portability_cases,
           sum(c.is_death)                                     AS deaths,
           sum(c.is_lama_dama)                                 AS lama_dama_cases,
           sum(CASE WHEN hosp.hospital_type = 'PUBLIC'  THEN 1 ELSE 0 END) AS public_cases,
           sum(CASE WHEN hosp.hospital_type = 'PRIVATE' THEN 1 ELSE 0 END) AS private_cases,
           count(DISTINCT c.hospital_id)                       AS unique_hospitals,
           avg(c.length_of_stay)                               AS avg_length_of_stay
    FROM stg_cm_case AS c
    LEFT JOIN benef_geo   AS g    ON c.beneficiary_id = g.beneficiary_id
    LEFT JOIN stg_hm_hospital AS hosp ON c.hospital_id = hosp.hospital_id
    GROUP BY 1, 2
),

-- Claims submitted per district x month (beneficiary home district).
claims AS (
    SELECT g.home_district_code AS district,
           strftime(cl.submitted_at, '%Y-%m') AS month,
           count(cl.claim_id)                                                       AS claims_submitted,
           sum(CASE WHEN cl.claim_status IN ('APPROVED', 'SETTLED') THEN 1 ELSE 0 END) AS claims_approved,
           sum(CASE WHEN cl.claim_status = 'REJECTED' THEN 1 ELSE 0 END)            AS claims_rejected,
           coalesce(sum(cl.amount_claimed), 0)                                      AS amount_claimed,
           coalesce(sum(cl.amount_approved), 0)                                     AS amount_approved,
           avg(cl.settlement_tat_days)                                             AS avg_settlement_tat
    FROM stg_cm_claim AS cl
    LEFT JOIN stg_cm_case AS c ON cl.case_id = c.case_id
    LEFT JOIN benef_geo   AS g ON c.beneficiary_id = g.beneficiary_id
    GROUP BY 1, 2
),

-- Payments per district x month (beneficiary home district).
pay AS (
    SELECT g.home_district_code AS district,
           strftime(p.payment_date, '%Y-%m') AS month,
           coalesce(sum(p.amount_paid), 0)                                  AS amount_paid,
           count(p.payment_id)                                             AS payment_count,
           sum(CASE WHEN p.payment_status = 'FAILED' THEN 1 ELSE 0 END)    AS payment_failures
    FROM stg_cm_payment AS p
    LEFT JOIN stg_cm_claim AS cl ON p.claim_id = cl.claim_id
    LEFT JOIN stg_cm_case  AS c  ON cl.case_id = c.case_id
    LEFT JOIN benef_geo    AS g  ON c.beneficiary_id = g.beneficiary_id
    GROUP BY 1, 2
),

-- Union every district x month via FULL OUTER joins (USING coalesces keys).
joined AS (
    SELECT * FROM enrol
    FULL JOIN cases  USING (district, month)
    FULL JOIN card   USING (district, month)
    FULL JOIN claims USING (district, month)
    FULL JOIN pay    USING (district, month)
),

-- Backfill division and zero-fill the 19 count/sum columns.
filled AS (
    SELECT
        coalesce(j.division, dm.division) AS division,
        j.district,
        j.month,
        coalesce(new_beneficiaries, 0) AS new_beneficiaries,
        coalesce(new_households,    0) AS new_households,
        coalesce(cases_admitted,    0) AS cases_admitted,
        coalesce(emergency_cases,   0) AS emergency_cases,
        coalesce(portability_cases, 0) AS portability_cases,
        coalesce(deaths,            0) AS deaths,
        coalesce(lama_dama_cases,   0) AS lama_dama_cases,
        coalesce(public_cases,      0) AS public_cases,
        coalesce(private_cases,     0) AS private_cases,
        coalesce(unique_hospitals,  0) AS unique_hospitals,
        avg_length_of_stay,                       -- NOT zero-filled (stays NULL)
        coalesce(cards_issued,      0) AS cards_issued,
        coalesce(claims_submitted,  0) AS claims_submitted,
        coalesce(claims_approved,   0) AS claims_approved,
        coalesce(claims_rejected,   0) AS claims_rejected,
        coalesce(amount_claimed,    0) AS amount_claimed,
        coalesce(amount_approved,   0) AS amount_approved,
        avg_settlement_tat,                       -- NOT zero-filled (stays NULL)
        coalesce(amount_paid,       0) AS amount_paid,
        coalesce(payment_count,     0) AS payment_count,
        coalesce(payment_failures,  0) AS payment_failures
    FROM joined AS j
    LEFT JOIN div_map AS dm ON j.district = dm.district
),

-- cumulative_beneficiaries = running SUM of new_beneficiaries per district by
-- month. Documented denominator choice: enrolment-based (created_at), NOT
-- card-based; this is the broader eligible-population view for coverage.
cumulative AS (
    SELECT *,
        sum(new_beneficiaries) OVER (
            PARTITION BY district ORDER BY month
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ) AS cumulative_beneficiaries
    FROM filled
)

SELECT
    division,
    district,
    month,
    CAST(new_beneficiaries AS DOUBLE)  AS new_beneficiaries,
    CAST(new_households     AS DOUBLE) AS new_households,
    CAST(cases_admitted     AS DOUBLE) AS cases_admitted,
    CAST(emergency_cases    AS DOUBLE) AS emergency_cases,
    CAST(portability_cases  AS BIGINT) AS portability_cases,
    CAST(deaths             AS DOUBLE) AS deaths,
    CAST(lama_dama_cases    AS DOUBLE) AS lama_dama_cases,
    CAST(public_cases       AS DOUBLE) AS public_cases,
    CAST(private_cases      AS DOUBLE) AS private_cases,
    CAST(unique_hospitals   AS DOUBLE) AS unique_hospitals,
    CAST(avg_length_of_stay AS DOUBLE) AS avg_length_of_stay,
    CAST(cards_issued       AS DOUBLE) AS cards_issued,
    CAST(claims_submitted   AS DOUBLE) AS claims_submitted,
    CAST(claims_approved    AS DOUBLE) AS claims_approved,
    CAST(claims_rejected    AS DOUBLE) AS claims_rejected,
    CAST(amount_claimed     AS DOUBLE) AS amount_claimed,
    CAST(amount_approved    AS DOUBLE) AS amount_approved,
    CAST(avg_settlement_tat AS DOUBLE) AS avg_settlement_tat,
    CAST(amount_paid        AS DOUBLE) AS amount_paid,
    CAST(payment_count      AS DOUBLE) AS payment_count,
    CAST(payment_failures   AS DOUBLE) AS payment_failures,
    CAST(cumulative_beneficiaries AS DOUBLE) AS cumulative_beneficiaries,
    CAST(year(strptime(month || '-01', '%Y-%m-%d')) AS VARCHAR) || 'Q'
        || CAST(quarter(strptime(month || '-01', '%Y-%m-%d')) AS VARCHAR) AS quarter,
    month[1:4]                          AS year,
    CAST(cases_admitted / nullif(cumulative_beneficiaries, 0) * 1000 AS DOUBLE) AS claims_per_1000_beneficiaries,
    CAST(claims_approved / nullif(claims_submitted, 0) AS DOUBLE)               AS approval_rate,
    CAST(emergency_cases / nullif(cases_admitted, 0) AS DOUBLE)                 AS emergency_share,
    CAST(deaths          / nullif(cases_admitted, 0) AS DOUBLE)                 AS death_rate,
    CAST(public_cases    / (private_cases + 1) AS DOUBLE)                       AS public_private_ratio,
    CAST(amount_claimed  / nullif(claims_submitted, 0) AS DOUBLE)               AS avg_claim_amount
FROM cumulative
ORDER BY district, month;
