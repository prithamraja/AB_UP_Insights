"""
35 Tier-2 parameterised query templates.
SQL uses ? positional placeholders (rewritten to $1, $2 … for PostgreSQL).
param_slots defines the ordered list of entities to extract and validate.
"""

# Reusable disease-category CTE snippet
_DIAG_CAT_CTE = """
WITH diag_cat AS (
    SELECT
        d.case_id,
        d.diagnosis_category AS category
    FROM cm_case_diagnosis d
    WHERE d.diagnosis_type = 'PRIMARY'
)
"""

TEMPLATE_CATALOG: dict[str, dict] = {

    # ── A. District Drilldowns (T01-T10) ──────────────────────────────────────

    "T01": {
        "abstract_question": "How many beneficiaries are enrolled in {district}?",
        "date_filter": None,  # enrollment is a cumulative snapshot
        "sql_template": """
SELECT
    h.home_district_code             AS district_name,
    COUNT(DISTINCT h.household_id)   AS households,
    COUNT(DISTINCT b.beneficiary_id) AS beneficiaries
FROM bm_household h
LEFT JOIN bm_beneficiary b ON h.household_id = b.household_id
WHERE h.home_district_code = ?
GROUP BY h.home_district_code
""",
        "param_slots": [{"name": "district", "entity_type": "district", "position": 1}],
        "result_ttl_seconds": 600,
    },

    "T02": {
        "abstract_question": "What is the claims summary for {district}?",
        "date_filter": {"alias": "c", "column": "admission_datetime"},
        "sql_template": """
SELECT
    c.hospital_district                      AS district_name,
    COUNT(DISTINCT c.case_id)                AS total_cases,
    COUNT(DISTINCT cl.claim_id)              AS total_claims,
    ROUND(SUM(cl.amount_claimed),  2)        AS total_claimed,
    ROUND(SUM(cl.amount_approved), 2)        AS total_approved,
    ROUND(AVG(cl.settlement_tat_days), 1)    AS avg_tat_days
FROM cm_case c
LEFT JOIN cm_claim cl ON c.case_id = cl.case_id
WHERE c.hospital_district = ?
GROUP BY c.hospital_district
""",
        "param_slots": [{"name": "district", "entity_type": "district", "position": 1}],
        "result_ttl_seconds": 600,
    },

    "T03": {
        "abstract_question": "What are the top hospitals in {district} by claim volume?",
        "date_filter": {"alias": "c", "column": "admission_datetime"},
        "sql_template": """
SELECT
    h.hospital_name,
    h.hospital_type,
    COUNT(DISTINCT c.case_id)           AS case_count,
    ROUND(SUM(cl.amount_claimed), 2)    AS total_claimed
FROM cm_case c
JOIN  hm_hospital h  ON c.hospital_id = h.hospital_id
LEFT JOIN cm_claim cl ON c.case_id    = cl.case_id
WHERE c.hospital_district = ?
GROUP BY h.hospital_id, h.hospital_name, h.hospital_type
ORDER BY case_count DESC

""",
        "param_slots": [{"name": "district", "entity_type": "district", "position": 1}],
        "result_ttl_seconds": 600,
    },

    "T04": {
        "abstract_question": "What is the disease burden in {district}?",
        "date_filter": {"alias": "c", "column": "admission_datetime"},
        "sql_template": """
SELECT
    d.diagnosis_category AS disease_category,
    COUNT(*) AS case_count,
    ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER(), 2) AS pct
FROM cm_case_diagnosis d
JOIN cm_case c ON d.case_id = c.case_id
WHERE c.hospital_district = ?
  AND d.diagnosis_type = 'PRIMARY'
GROUP BY 1
ORDER BY case_count DESC
""",
        "param_slots": [{"name": "district", "entity_type": "district", "position": 1}],
        "result_ttl_seconds": 600,
    },

    "T05": {
        "abstract_question": "What is the monthly case trend in {district}?",
        "date_filter": {"alias": "c", "column": "admission_datetime"},
        "sql_template": """
SELECT
    date_trunc('month', c.admission_datetime)::DATE  AS month,
    COUNT(*)                                          AS case_count
FROM cm_case c
WHERE c.hospital_district = ?
GROUP BY 1
ORDER BY 1
""",
        "param_slots": [{"name": "district", "entity_type": "district", "position": 1}],
        "result_ttl_seconds": 600,
    },

    "T06": {
        "abstract_question": "How many hospitals are empanelled in {district}?",
        "date_filter": None,  # hospital registry is static
        "sql_template": """
SELECT
    hospital_type,
    hospital_sub_type,
    COUNT(*)                AS hospital_count,
    SUM(total_bed_strength) AS total_beds
FROM hm_hospital
WHERE district_name = ?
GROUP BY hospital_type, hospital_sub_type
ORDER BY hospital_count DESC
""",
        "param_slots": [{"name": "district", "entity_type": "district", "position": 1}],
        "result_ttl_seconds": 900,
    },

    "T07": {
        "abstract_question": "What is the settlement TAT in {district}?",
        "date_filter": {"alias": "cl", "column": "submitted_at"},
        "sql_template": """
SELECT
    c.hospital_district  AS district_name,
    ROUND(AVG(cl.settlement_tat_days), 1)                                           AS avg_tat,
    ROUND(PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY cl.settlement_tat_days)::numeric, 1)  AS median_tat,
    ROUND(PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY cl.settlement_tat_days)::numeric, 1)  AS p95_tat,
    MAX(cl.settlement_tat_days)                                                      AS max_tat
FROM cm_claim cl
JOIN cm_case c ON cl.case_id = c.case_id
WHERE c.hospital_district = ?
  AND cl.settlement_tat_days IS NOT NULL
GROUP BY c.hospital_district
""",
        "param_slots": [{"name": "district", "entity_type": "district", "position": 1}],
        "result_ttl_seconds": 600,
    },

    "T08": {
        "abstract_question": "What is the rejection rate in {district}?",
        "date_filter": {"alias": "cl", "column": "submitted_at"},
        "sql_template": """
SELECT
    c.hospital_district  AS district_name,
    COUNT(cl.claim_id)   AS total_claims,
    COUNT(CASE WHEN cl.claim_status = 'REJECTED' THEN 1 END) AS rejected_claims,
    ROUND(
        COUNT(CASE WHEN cl.claim_status = 'REJECTED' THEN 1 END)
        * 100.0 / NULLIF(COUNT(cl.claim_id), 0),
        2
    ) AS rejection_rate_pct
FROM cm_claim cl
JOIN cm_case c ON cl.case_id = c.case_id
WHERE c.hospital_district = ?
GROUP BY c.hospital_district
""",
        "param_slots": [{"name": "district", "entity_type": "district", "position": 1}],
        "result_ttl_seconds": 600,
    },

    "T09": {
        "abstract_question": "What is the gender breakdown of beneficiaries in {district}?",
        "date_filter": None,  # enrollment snapshot
        "sql_template": """
SELECT
    b.gender,
    COUNT(*) AS count,
    ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER(), 2) AS pct
FROM bm_beneficiary b
JOIN bm_household h ON b.household_id = h.household_id
WHERE h.home_district_code = ?
GROUP BY b.gender
ORDER BY count DESC
""",
        "param_slots": [{"name": "district", "entity_type": "district", "position": 1}],
        "result_ttl_seconds": 900,
    },

    "T10": {
        "abstract_question": "Which blocks in {district} have the most cases?",
        "date_filter": {"alias": "c", "column": "admission_datetime"},
        "sql_template": """
SELECT
    h.block_name,
    h.district_name,
    COUNT(DISTINCT c.case_id)        AS case_count,
    ROUND(SUM(cl.amount_claimed), 2) AS total_claimed
FROM cm_case c
JOIN  hm_hospital h  ON c.hospital_id = h.hospital_id
LEFT JOIN cm_claim cl ON c.case_id    = cl.case_id
WHERE h.district_name = ?
GROUP BY h.block_name, h.district_name
ORDER BY case_count DESC

""",
        "param_slots": [{"name": "district", "entity_type": "district", "position": 1}],
        "result_ttl_seconds": 600,
    },

    # ── B. Block Drilldowns (T11-T14) ─────────────────────────────────────────

    "T11": {
        "abstract_question": "How many beneficiaries are enrolled in {block} of {district}?",
        "date_filter": None,  # enrollment snapshot
        "sql_template": """
SELECT
    h.home_block_name                AS block_name,
    h.home_district_code             AS district_name,
    COUNT(DISTINCT h.household_id)   AS households,
    COUNT(DISTINCT b.beneficiary_id) AS beneficiaries
FROM bm_household h
LEFT JOIN bm_beneficiary b ON h.household_id = b.household_id
WHERE h.home_block_name   = ?
  AND h.home_district_code = ?
GROUP BY h.home_block_name, h.home_district_code
""",
        "param_slots": [
            {"name": "block",    "entity_type": "block",    "position": 1},
            {"name": "district", "entity_type": "district", "position": 2},
        ],
        "result_ttl_seconds": 600,
    },

    "T12": {
        "abstract_question": "What is the claims summary for {block} of {district}?",
        "date_filter": {"alias": "c", "column": "admission_datetime"},
        "sql_template": """
SELECT
    h.block_name,
    h.district_name,
    COUNT(DISTINCT c.case_id)        AS total_cases,
    ROUND(SUM(cl.amount_claimed), 2) AS total_claimed
FROM cm_case c
JOIN  hm_hospital h  ON c.hospital_id = h.hospital_id
LEFT JOIN cm_claim cl ON c.case_id    = cl.case_id
WHERE h.block_name   = ?
  AND h.district_name = ?
GROUP BY h.block_name, h.district_name
""",
        "param_slots": [
            {"name": "block",    "entity_type": "block",    "position": 1},
            {"name": "district", "entity_type": "district", "position": 2},
        ],
        "result_ttl_seconds": 600,
    },

    "T13": {
        "abstract_question": "Which hospitals serve {block}?",
        "date_filter": None,  # hospital registry is static
        "sql_template": """
SELECT
    hospital_name,
    hospital_type,
    district_name,
    total_bed_strength
FROM hm_hospital
WHERE block_name = ?
ORDER BY hospital_name
""",
        "param_slots": [{"name": "block", "entity_type": "block", "position": 1}],
        "result_ttl_seconds": 900,
    },

    "T14": {
        "abstract_question": "What are the top diagnoses in {block} of {district}?",
        "date_filter": {"alias": "c", "column": "admission_datetime"},
        "sql_template": """
SELECT
    d.icd_code,
    d.diagnosis_text,
    COUNT(*) AS count
FROM cm_case_diagnosis d
JOIN cm_case c     ON d.case_id     = c.case_id
JOIN hm_hospital h ON c.hospital_id = h.hospital_id
WHERE h.block_name    = ?
  AND h.district_name = ?
  AND d.diagnosis_type = 'PRIMARY'
GROUP BY d.icd_code, d.diagnosis_text
ORDER BY count DESC

""",
        "param_slots": [
            {"name": "block",    "entity_type": "block",    "position": 1},
            {"name": "district", "entity_type": "district", "position": 2},
        ],
        "result_ttl_seconds": 600,
    },

    # ── C. Hospital Drilldowns (T15-T20) ──────────────────────────────────────

    "T15": {
        "abstract_question": "What is the performance summary of {hospital}?",
        "date_filter": {"alias": "c", "column": "admission_datetime"},
        "sql_template": """
SELECT
    h.hospital_name,
    h.hospital_type,
    h.district_name,
    h.total_bed_strength,
    COUNT(DISTINCT c.case_id)                                          AS total_cases,
    COUNT(DISTINCT cl.claim_id)                                        AS total_claims,
    ROUND(SUM(cl.amount_claimed), 2)                                   AS total_claimed,
    ROUND(AVG(cl.settlement_tat_days), 1)                              AS avg_tat,
    COUNT(CASE WHEN cl.claim_status = 'REJECTED' THEN 1 END)          AS rejected_claims
FROM hm_hospital h
LEFT JOIN cm_case  c  ON h.hospital_id = c.hospital_id
LEFT JOIN cm_claim cl ON c.case_id     = cl.case_id
WHERE h.hospital_name = ?
GROUP BY h.hospital_id, h.hospital_name, h.hospital_type,
         h.district_name, h.total_bed_strength
""",
        "param_slots": [{"name": "hospital", "entity_type": "hospital", "position": 1}],
        "result_ttl_seconds": 600,
    },

    "T16": {
        "abstract_question": "What specialties does {hospital} offer?",
        "date_filter": None,  # specialty registry is static
        "sql_template": """
SELECT
    s.specialty_code,
    s.specialty_name,
    s.admissions_prev_fy,
    s.admissions_before_last_year
FROM hm_specialty_offered s
JOIN hm_hospital h ON s.hospital_id = h.hospital_id
WHERE h.hospital_name = ?
ORDER BY s.admissions_prev_fy DESC
""",
        "param_slots": [{"name": "hospital", "entity_type": "hospital", "position": 1}],
        "result_ttl_seconds": 900,
    },

    "T17": {
        "abstract_question": "What is the monthly case trend for {hospital}?",
        "date_filter": {"alias": "c", "column": "admission_datetime"},
        "sql_template": """
SELECT
    date_trunc('month', c.admission_datetime)::DATE  AS month,
    COUNT(*)                                          AS case_count
FROM cm_case c
JOIN hm_hospital h ON c.hospital_id = h.hospital_id
WHERE h.hospital_name = ?
GROUP BY 1
ORDER BY 1
""",
        "param_slots": [{"name": "hospital", "entity_type": "hospital", "position": 1}],
        "result_ttl_seconds": 600,
    },

    "T18": {
        "abstract_question": "Is the license of {hospital} current?",
        "date_filter": None,  # license data is static
        "sql_template": """
SELECT
    h.hospital_name,
    l.license_name,
    l.certificate_no,
    l.issue_date,
    l.expiry_date,
    CASE WHEN l.expiry_date >= CURRENT_DATE THEN 'CURRENT' ELSE 'EXPIRED' END AS status
FROM hm_license_certificate l
JOIN hm_hospital h ON l.hospital_id = h.hospital_id
WHERE h.hospital_name = ?
ORDER BY l.expiry_date DESC
""",
        "param_slots": [{"name": "hospital", "entity_type": "hospital", "position": 1}],
        "result_ttl_seconds": 900,
    },

    "T19": {
        "abstract_question": "What is the claim approval rate for {hospital}?",
        "date_filter": {"alias": "cl", "column": "submitted_at"},
        "sql_template": """
SELECT
    h.hospital_name,
    COUNT(cl.claim_id)                                                                AS total_claims,
    COUNT(CASE WHEN cl.claim_status = 'APPROVED' THEN 1 END)                         AS approved,
    COUNT(CASE WHEN cl.claim_status = 'SETTLED'  THEN 1 END)                         AS settled,
    COUNT(CASE WHEN cl.claim_status = 'REJECTED' THEN 1 END)                         AS rejected,
    ROUND(
        COUNT(CASE WHEN cl.claim_status IN ('APPROVED','SETTLED') THEN 1 END)
        * 100.0 / NULLIF(COUNT(cl.claim_id), 0),
        2
    ) AS approval_rate_pct
FROM cm_claim cl
JOIN cm_case     c ON cl.case_id    = c.case_id
JOIN hm_hospital h ON c.hospital_id = h.hospital_id
WHERE h.hospital_name = ?
GROUP BY h.hospital_name
""",
        "param_slots": [{"name": "hospital", "entity_type": "hospital", "position": 1}],
        "result_ttl_seconds": 600,
    },

    "T20": {
        "abstract_question": "What are the top diagnoses treated at {hospital}?",
        "date_filter": {"alias": "c", "column": "admission_datetime"},
        "sql_template": """
SELECT
    d.icd_code,
    d.diagnosis_text,
    COUNT(*) AS count
FROM cm_case_diagnosis d
JOIN cm_case     c ON d.case_id     = c.case_id
JOIN hm_hospital h ON c.hospital_id = h.hospital_id
WHERE h.hospital_name = ?
  AND d.diagnosis_type = 'PRIMARY'
GROUP BY d.icd_code, d.diagnosis_text
ORDER BY count DESC

""",
        "param_slots": [{"name": "hospital", "entity_type": "hospital", "position": 1}],
        "result_ttl_seconds": 600,
    },

    # ── D. Specialty / Diagnosis Queries (T21-T25) ────────────────────────────

    "T21": {
        "abstract_question": "What is the utilization of {specialty} across UP?",
        "date_filter": {"alias": "c", "column": "admission_datetime"},
        "sql_template": """
SELECT
    r.specialty_code,
    r.specialty_name,
    COUNT(DISTINCT pl.preauth_id)           AS preauth_count,
    COUNT(DISTINCT c.case_id)               AS case_count,
    ROUND(SUM(pl.computed_final_amount), 2) AS total_amount
FROM cm_preauth_procedure_line pl
JOIN ref_hbp_procedure_master r ON pl.hbp_procedure_code = r.hbp_procedure_code
JOIN cm_preauth_request pr      ON pl.preauth_id         = pr.preauth_id
JOIN cm_case c                  ON pr.case_id            = c.case_id
WHERE r.specialty_code = ?
GROUP BY r.specialty_code, r.specialty_name
""",
        "param_slots": [{"name": "specialty", "entity_type": "specialty", "position": 1}],
        "result_ttl_seconds": 600,
    },

    "T22": {
        "abstract_question": "Which districts have the highest {specialty} cases?",
        "date_filter": {"alias": "c", "column": "admission_datetime"},
        "sql_template": """
SELECT
    c.hospital_district                     AS district_name,
    COUNT(DISTINCT c.case_id)               AS case_count,
    ROUND(SUM(pl.computed_final_amount), 2) AS total_amount
FROM cm_case c
JOIN cm_preauth_request pr     ON c.case_id          = pr.case_id
JOIN cm_preauth_procedure_line pl ON pr.preauth_id   = pl.preauth_id
JOIN ref_hbp_procedure_master r   ON pl.hbp_procedure_code = r.hbp_procedure_code
WHERE r.specialty_code = ?
GROUP BY c.hospital_district
ORDER BY case_count DESC

""",
        "param_slots": [{"name": "specialty", "entity_type": "specialty", "position": 1}],
        "result_ttl_seconds": 600,
    },

    "T23": {
        "abstract_question": "What is the trend for {diagnosis_category} cases?",
        "date_filter": {"alias": "c", "column": "admission_datetime"},
        "sql_template": _DIAG_CAT_CTE + """
SELECT
    date_trunc('month', c.admission_datetime)::DATE  AS month,
    COUNT(*)                                          AS case_count
FROM diag_cat dc
JOIN cm_case c ON dc.case_id = c.case_id
WHERE dc.category = ?
GROUP BY 1
ORDER BY 1
""",
        "param_slots": [{"name": "diagnosis_category", "entity_type": "diagnosis_category", "position": 1}],
        "result_ttl_seconds": 600,
    },

    "T24": {
        "abstract_question": "Which hospitals handle the most {specialty} cases?",
        "date_filter": {"alias": "c", "column": "admission_datetime"},
        "sql_template": """
SELECT
    h.hospital_name,
    h.district_name,
    h.hospital_type,
    COUNT(DISTINCT c.case_id)               AS case_count,
    ROUND(SUM(pl.computed_final_amount), 2) AS total_amount
FROM cm_case c
JOIN hm_hospital h                           ON c.hospital_id        = h.hospital_id
JOIN cm_preauth_request pr                   ON c.case_id            = pr.case_id
JOIN cm_preauth_procedure_line pl            ON pr.preauth_id        = pl.preauth_id
JOIN ref_hbp_procedure_master r              ON pl.hbp_procedure_code = r.hbp_procedure_code
WHERE r.specialty_code = ?
GROUP BY h.hospital_id, h.hospital_name, h.district_name, h.hospital_type
ORDER BY case_count DESC

""",
        "param_slots": [{"name": "specialty", "entity_type": "specialty", "position": 1}],
        "result_ttl_seconds": 600,
    },

    "T25": {
        "abstract_question": "What is the {specialty} utilization in {district}?",
        "date_filter": {"alias": "c", "column": "admission_datetime"},
        "sql_template": """
SELECT
    r.specialty_code,
    r.specialty_name,
    c.hospital_district                     AS district_name,
    COUNT(DISTINCT c.case_id)               AS case_count,
    ROUND(SUM(pl.computed_final_amount), 2) AS total_amount
FROM cm_case c
JOIN cm_preauth_request pr     ON c.case_id             = pr.case_id
JOIN cm_preauth_procedure_line pl ON pr.preauth_id      = pl.preauth_id
JOIN ref_hbp_procedure_master r   ON pl.hbp_procedure_code = r.hbp_procedure_code
WHERE r.specialty_code   = ?
  AND c.hospital_district = ?
GROUP BY r.specialty_code, r.specialty_name, c.hospital_district
""",
        "param_slots": [
            {"name": "specialty", "entity_type": "specialty", "position": 1},
            {"name": "district",  "entity_type": "district",  "position": 2},
        ],
        "result_ttl_seconds": 600,
    },

    # ── E. Comparative / Filtered (T26-T31) ───────────────────────────────────

    "T26": {
        "abstract_question": "Compare claims between {district} and {district_2}?",
        "date_filter": {"alias": "c", "column": "admission_datetime"},
        "sql_template": """
SELECT
    c.hospital_district                      AS district_name,
    COUNT(DISTINCT c.case_id)                AS total_cases,
    COUNT(DISTINCT cl.claim_id)              AS total_claims,
    ROUND(SUM(cl.amount_claimed),  2)        AS total_claimed,
    ROUND(SUM(cl.amount_approved), 2)        AS total_approved,
    COUNT(CASE WHEN cl.claim_status = 'REJECTED' THEN 1 END) AS rejected_claims
FROM cm_case c
LEFT JOIN cm_claim cl ON c.case_id = cl.case_id
WHERE c.hospital_district IN (?, ?)
GROUP BY c.hospital_district
ORDER BY total_cases DESC
""",
        "param_slots": [
            {"name": "district",   "entity_type": "district", "position": 1},
            {"name": "district_2", "entity_type": "district", "position": 2},
        ],
        "result_ttl_seconds": 600,
    },

    "T27": {
        "abstract_question": "What is the claim status breakdown for {district}?",
        "date_filter": {"alias": "c", "column": "admission_datetime"},
        "sql_template": """
SELECT
    cl.claim_status,
    COUNT(*) AS count,
    ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER(), 2) AS pct,
    ROUND(SUM(cl.amount_claimed), 2) AS total_claimed
FROM cm_claim cl
JOIN cm_case c ON cl.case_id = c.case_id
WHERE c.hospital_district = ?
GROUP BY cl.claim_status
ORDER BY count DESC
""",
        "param_slots": [{"name": "district", "entity_type": "district", "position": 1}],
        "result_ttl_seconds": 600,
    },

    "T28": {
        "abstract_question": "Show all {claim_status} claims in {district}?",
        "date_filter": {"alias": "c", "column": "admission_datetime"},
        "sql_template": """
SELECT
    cl.claim_id,
    c.case_number,
    h.hospital_name,
    cl.submitted_at,
    cl.amount_claimed,
    cl.amount_approved,
    cl.settlement_tat_days
FROM cm_claim cl
JOIN cm_case     c ON cl.case_id    = c.case_id
JOIN hm_hospital h ON c.hospital_id = h.hospital_id
WHERE cl.claim_status     = ?
  AND c.hospital_district = ?
ORDER BY cl.submitted_at DESC
LIMIT 100
""",
        "param_slots": [
            {"name": "claim_status", "entity_type": "claim_status", "position": 1},
            {"name": "district",     "entity_type": "district",     "position": 2},
        ],
        "result_ttl_seconds": 300,
    },

    "T29": {
        "abstract_question": "What is the public vs private split in {district}?",
        "date_filter": {"alias": "c", "column": "admission_datetime"},
        "sql_template": """
SELECT
    h.hospital_type,
    COUNT(DISTINCT c.case_id)                                               AS case_count,
    ROUND(COUNT(DISTINCT c.case_id) * 100.0
          / SUM(COUNT(DISTINCT c.case_id)) OVER(), 2)                      AS pct_cases,
    ROUND(SUM(cl.amount_claimed), 2)                                        AS total_claimed
FROM cm_case c
JOIN  hm_hospital h  ON c.hospital_id = h.hospital_id
LEFT JOIN cm_claim cl ON c.case_id    = cl.case_id
WHERE c.hospital_district = ?
GROUP BY h.hospital_type
ORDER BY case_count DESC
""",
        "param_slots": [{"name": "district", "entity_type": "district", "position": 1}],
        "result_ttl_seconds": 600,
    },

    "T30": {
        "abstract_question": "What is the portability volume from {district}?",
        "date_filter": {"alias": "c", "column": "admission_datetime"},
        "sql_template": """
SELECT
    c.hospital_state_code            AS destination_state,
    COUNT(*)                         AS portability_cases,
    ROUND(SUM(cl.amount_claimed), 2) AS total_claimed
FROM cm_case c
JOIN bm_beneficiary b ON c.beneficiary_id = b.beneficiary_id
JOIN bm_household   h ON b.household_id   = h.household_id
LEFT JOIN cm_claim cl ON c.case_id        = cl.case_id
WHERE c.is_portability    = true
  AND h.home_district_code = ?
GROUP BY c.hospital_state_code
ORDER BY portability_cases DESC
""",
        "param_slots": [{"name": "district", "entity_type": "district", "position": 1}],
        "result_ttl_seconds": 600,
    },

    "T31": {
        "abstract_question": "What are the {year} totals for {district}?",
        "date_filter": None,  # already year-filtered
        "sql_template": """
SELECT
    c.hospital_district                      AS district_name,
    CAST(EXTRACT(YEAR FROM c.admission_datetime) AS INTEGER) AS year,
    COUNT(DISTINCT c.case_id)                AS total_cases,
    COUNT(DISTINCT cl.claim_id)              AS total_claims,
    ROUND(SUM(cl.amount_claimed),  2)        AS total_claimed,
    ROUND(SUM(cl.amount_approved), 2)        AS total_approved
FROM cm_case c
LEFT JOIN cm_claim cl ON c.case_id = cl.case_id
WHERE CAST(EXTRACT(YEAR FROM c.admission_datetime) AS INTEGER) = CAST(? AS INTEGER)
  AND c.hospital_district = ?
GROUP BY c.hospital_district, 2
""",
        "param_slots": [
            {"name": "year",     "entity_type": "year",     "position": 1},
            {"name": "district", "entity_type": "district", "position": 2},
        ],
        "result_ttl_seconds": 600,
    },

    # ── F. Time-Filtered (T32-T35) ────────────────────────────────────────────

    "T32": {
        "abstract_question": "What were the total claims in {month} {year}?",
        "date_filter": None,  # already month/year-filtered
        "sql_template": """
SELECT
    CAST(EXTRACT(MONTH FROM submitted_at) AS INTEGER)  AS month,
    CAST(EXTRACT(YEAR  FROM submitted_at) AS INTEGER)  AS year,
    COUNT(*)                              AS total_claims,
    ROUND(SUM(amount_claimed),  2)        AS total_claimed,
    ROUND(SUM(amount_approved), 2)        AS total_approved,
    COUNT(CASE WHEN claim_status = 'REJECTED' THEN 1 END) AS rejected_claims
FROM cm_claim
WHERE CAST(EXTRACT(MONTH FROM submitted_at) AS INTEGER) = CAST(? AS INTEGER)
  AND CAST(EXTRACT(YEAR  FROM submitted_at) AS INTEGER) = CAST(? AS INTEGER)
GROUP BY 1, 2
""",
        "param_slots": [
            {"name": "month", "entity_type": "month", "position": 1},
            {"name": "year",  "entity_type": "year",  "position": 2},
        ],
        "result_ttl_seconds": 600,
    },

    "T33": {
        "abstract_question": "Which districts had the most cases in {year}?",
        "date_filter": None,  # already year-filtered
        "sql_template": """
SELECT
    c.hospital_district                AS district_name,
    COUNT(*)                           AS case_count,
    COUNT(DISTINCT cl.claim_id)        AS claim_count,
    ROUND(SUM(cl.amount_claimed), 2)   AS total_claimed
FROM cm_case c
LEFT JOIN cm_claim cl ON c.case_id = cl.case_id
WHERE CAST(EXTRACT(YEAR FROM c.admission_datetime) AS INTEGER) = CAST(? AS INTEGER)
GROUP BY c.hospital_district
ORDER BY case_count DESC

""",
        "param_slots": [{"name": "year", "entity_type": "year", "position": 1}],
        "result_ttl_seconds": 600,
    },

    "T34": {
        "abstract_question": "What was the rejection rate in {month} {year}?",
        "date_filter": None,  # already month/year-filtered
        "sql_template": """
SELECT
    CAST(EXTRACT(MONTH FROM submitted_at) AS INTEGER)  AS month,
    CAST(EXTRACT(YEAR  FROM submitted_at) AS INTEGER)  AS year,
    COUNT(*) AS total_claims,
    COUNT(CASE WHEN claim_status = 'REJECTED' THEN 1 END) AS rejected_claims,
    ROUND(
        COUNT(CASE WHEN claim_status = 'REJECTED' THEN 1 END)
        * 100.0 / NULLIF(COUNT(*), 0),
        2
    ) AS rejection_rate_pct
FROM cm_claim
WHERE CAST(EXTRACT(MONTH FROM submitted_at) AS INTEGER) = CAST(? AS INTEGER)
  AND CAST(EXTRACT(YEAR  FROM submitted_at) AS INTEGER) = CAST(? AS INTEGER)
GROUP BY 1, 2
""",
        "param_slots": [
            {"name": "month", "entity_type": "month", "position": 1},
            {"name": "year",  "entity_type": "year",  "position": 2},
        ],
        "result_ttl_seconds": 600,
    },

    "T35": {
        "abstract_question": "What is the seasonal pattern for {diagnosis_category}?",
        "date_filter": {"alias": "c", "column": "admission_datetime"},
        "sql_template": _DIAG_CAT_CTE + """
SELECT
    CAST(EXTRACT(MONTH FROM c.admission_datetime) AS INTEGER)  AS month,
    COUNT(*)                                                    AS case_count,
    ROUND(COUNT(*) * 1.0 / 3, 1)                               AS avg_annual_cases
FROM diag_cat dc
JOIN cm_case c ON dc.case_id = c.case_id
WHERE dc.category = ?
GROUP BY 1
ORDER BY 1
""",
        "param_slots": [{"name": "diagnosis_category", "entity_type": "diagnosis_category", "position": 1}],
        "result_ttl_seconds": 600,
    },

    # ── G. New District Parameterizations (T36-T47) ──────────────────────────

    "T36": {
        "abstract_question": "What is the age distribution of beneficiaries in {district}?",
        "date_filter": None,  # enrollment snapshot
        "sql_template": """
WITH ages AS (
    SELECT
        COALESCE(b.yob, EXTRACT(YEAR FROM b.dob)::INTEGER) AS birth_year
    FROM bm_beneficiary b
    JOIN bm_household h ON b.household_id = h.household_id
    WHERE h.home_district_code = ?
      AND COALESCE(b.yob, EXTRACT(YEAR FROM b.dob)::INTEGER) IS NOT NULL
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
        "param_slots": [{"name": "district", "entity_type": "district", "position": 1}],
        "result_ttl_seconds": 900,
    },

    "T37": {
        "abstract_question": "What is the enrollment source breakdown in {district}?",
        "date_filter": None,  # enrollment snapshot
        "sql_template": """
SELECT
    h.entitlement_source,
    COUNT(*) AS households,
    ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER(), 2) AS pct
FROM bm_household h
WHERE h.home_district_code = ?
GROUP BY h.entitlement_source
ORDER BY households DESC
""",
        "param_slots": [{"name": "district", "entity_type": "district", "position": 1}],
        "result_ttl_seconds": 900,
    },

    "T38": {
        "abstract_question": "What is the BIS record status in {district}?",
        "date_filter": None,  # enrollment snapshot
        "sql_template": """
SELECT
    b.bis_record_status,
    COUNT(*) AS count,
    ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER(), 2) AS pct
FROM bm_beneficiary b
JOIN bm_household h ON b.household_id = h.household_id
WHERE h.home_district_code = ?
GROUP BY b.bis_record_status
ORDER BY count DESC
""",
        "param_slots": [{"name": "district", "entity_type": "district", "position": 1}],
        "result_ttl_seconds": 900,
    },

    "T39": {
        "abstract_question": "How many beneficiaries have mobile numbers in {district}?",
        "date_filter": None,  # enrollment snapshot
        "sql_template": """
SELECT
    COUNT(*)        AS total_beneficiaries,
    COUNT(b.mobile) AS with_mobile,
    ROUND(COUNT(b.mobile) * 100.0 / COUNT(*), 2) AS mobile_pct
FROM bm_beneficiary b
JOIN bm_household h ON b.household_id = h.household_id
WHERE h.home_district_code = ?
""",
        "param_slots": [{"name": "district", "entity_type": "district", "position": 1}],
        "result_ttl_seconds": 900,
    },

    "T40": {
        "abstract_question": "What is the specialty coverage in {district}?",
        "date_filter": None,  # hospital registry is static
        "sql_template": """
SELECT
    s.specialty_code,
    s.specialty_name,
    COUNT(DISTINCT s.hospital_id) AS hospital_count,
    SUM(s.admissions_prev_fy)     AS admissions_prev_fy
FROM hm_specialty_offered s
JOIN hm_hospital h ON s.hospital_id = h.hospital_id
WHERE h.district_name = ?
GROUP BY s.specialty_code, s.specialty_name
ORDER BY hospital_count DESC
""",
        "param_slots": [{"name": "district", "entity_type": "district", "position": 1}],
        "result_ttl_seconds": 900,
    },

    "T41": {
        "abstract_question": "How many hospitals have expired licenses in {district}?",
        "date_filter": None,  # license data is static
        "sql_template": """
SELECT
    COUNT(DISTINCT l.hospital_id) AS total_hospitals_with_licenses,
    COUNT(DISTINCT CASE WHEN l.expiry_date < CURRENT_DATE THEN l.hospital_id END) AS expired,
    ROUND(
        COUNT(DISTINCT CASE WHEN l.expiry_date < CURRENT_DATE THEN l.hospital_id END)
        * 100.0 / NULLIF(COUNT(DISTINCT l.hospital_id), 0),
        2
    ) AS pct_expired
FROM hm_license_certificate l
JOIN hm_hospital h ON l.hospital_id = h.hospital_id
WHERE h.district_name = ?
""",
        "param_slots": [{"name": "district", "entity_type": "district", "position": 1}],
        "result_ttl_seconds": 900,
    },

    "T42": {
        "abstract_question": "What is the bed capacity in {district}?",
        "date_filter": None,  # hospital registry is static
        "sql_template": """
SELECT
    h.hospital_type,
    h.hospital_sub_type,
    COUNT(*)                              AS hospital_count,
    SUM(h.total_bed_strength)             AS total_beds,
    SUM(h.inpatient_beds)                 AS inpatient_beds,
    ROUND(AVG(h.total_bed_strength), 0)   AS avg_beds_per_hospital
FROM hm_hospital h
WHERE h.district_name = ?
GROUP BY h.hospital_type, h.hospital_sub_type
ORDER BY total_beds DESC
""",
        "param_slots": [{"name": "district", "entity_type": "district", "position": 1}],
        "result_ttl_seconds": 900,
    },

    "T43": {
        "abstract_question": "What is the staff-to-bed ratio in {district}?",
        "date_filter": None,  # hospital registry is static
        "sql_template": """
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
WHERE h.district_name = ?
GROUP BY h.hospital_type, h.hospital_sub_type
ORDER BY staff_per_bed DESC
""",
        "param_slots": [{"name": "district", "entity_type": "district", "position": 1}],
        "result_ttl_seconds": 900,
    },

    "T44": {
        "abstract_question": "What are the top procedures in {district}?",
        "date_filter": {"alias": "c", "column": "admission_datetime"},
        "sql_template": """
SELECT
    pl.hbp_procedure_code,
    p.procedure_name,
    p.specialty_code,
    COUNT(*)                                 AS usage_count,
    ROUND(SUM(pl.computed_final_amount), 2)  AS total_amount
FROM cm_preauth_procedure_line pl
JOIN ref_hbp_procedure_master p  ON pl.hbp_procedure_code = p.hbp_procedure_code
JOIN cm_preauth_request pr       ON pl.preauth_id         = pr.preauth_id
JOIN cm_case c                   ON pr.case_id            = c.case_id
WHERE c.hospital_district = ?
GROUP BY pl.hbp_procedure_code, p.procedure_name, p.specialty_code
ORDER BY usage_count DESC

""",
        "param_slots": [{"name": "district", "entity_type": "district", "position": 1}],
        "result_ttl_seconds": 600,
    },

    "T45": {
        "abstract_question": "What are the top diagnoses in {district}?",
        "date_filter": {"alias": "c", "column": "admission_datetime"},
        "sql_template": """
SELECT
    d.icd_code,
    d.diagnosis_text,
    COUNT(*) AS count
FROM cm_case_diagnosis d
JOIN cm_case c ON d.case_id = c.case_id
WHERE c.hospital_district = ?
  AND d.diagnosis_type = 'PRIMARY'
GROUP BY d.icd_code, d.diagnosis_text
ORDER BY count DESC

""",
        "param_slots": [{"name": "district", "entity_type": "district", "position": 1}],
        "result_ttl_seconds": 600,
    },

    "T46": {
        "abstract_question": "What is the discharge type distribution in {district}?",
        "date_filter": {"alias": "c", "column": "admission_datetime"},
        "sql_template": """
SELECT
    c.discharge_type,
    COUNT(*) AS count,
    ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER(), 2) AS pct
FROM cm_case c
WHERE c.hospital_district = ?
  AND c.discharge_type IS NOT NULL
GROUP BY c.discharge_type
ORDER BY count DESC
""",
        "param_slots": [{"name": "district", "entity_type": "district", "position": 1}],
        "result_ttl_seconds": 600,
    },

    "T47": {
        "abstract_question": "What is the financial summary for {district}?",
        "date_filter": {"alias": "c", "column": "admission_datetime"},
        "sql_template": """
SELECT
    ROUND(SUM(CASE WHEN cl.claim_status = 'SETTLED'
                   THEN cl.amount_approved ELSE 0 END), 2)                        AS total_settled,
    ROUND(SUM(CASE WHEN cl.claim_status IN ('APPROVED','QUERY_RAISED','PENDING')
                   THEN cl.amount_approved ELSE 0 END), 2)                        AS total_pending,
    ROUND(SUM(CASE WHEN cl.claim_status = 'REJECTED'
                   THEN cl.amount_claimed ELSE 0 END), 2)                         AS total_rejected,
    ROUND(SUM(COALESCE(cl.amount_claimed, 0)), 2)                                 AS grand_total_claimed
FROM cm_claim cl
JOIN cm_case c ON cl.case_id = c.case_id
WHERE c.hospital_district = ?
""",
        "param_slots": [{"name": "district", "entity_type": "district", "position": 1}],
        "result_ttl_seconds": 600,
    },

    # ── H. Block-level Parameterizations (T48-T69) ───────────────────────────
    # Enrollment: join via bm_household.home_block_name
    # Hospital/Case/Claim: join via hm_hospital.block_name

    "T48": {
        "abstract_question": "How many beneficiaries are enrolled in {block}?",
        "date_filter": None,
        "sql_template": """
SELECT
    h.home_block_name                AS block_name,
    COUNT(DISTINCT h.household_id)   AS households,
    COUNT(DISTINCT b.beneficiary_id) AS beneficiaries
FROM bm_household h
LEFT JOIN bm_beneficiary b ON h.household_id = b.household_id
WHERE h.home_block_name = ?
GROUP BY h.home_block_name
""",
        "param_slots": [{"name": "block", "entity_type": "block", "position": 1}],
        "result_ttl_seconds": 900,
    },

    "T49": {
        "abstract_question": "What is the gender breakdown of beneficiaries in {block}?",
        "date_filter": None,
        "sql_template": """
SELECT
    b.gender,
    COUNT(*) AS count,
    ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER(), 2) AS pct
FROM bm_beneficiary b
JOIN bm_household h ON b.household_id = h.household_id
WHERE h.home_block_name = ?
GROUP BY b.gender
ORDER BY count DESC
""",
        "param_slots": [{"name": "block", "entity_type": "block", "position": 1}],
        "result_ttl_seconds": 900,
    },

    "T50": {
        "abstract_question": "What is the age distribution of beneficiaries in {block}?",
        "date_filter": None,
        "sql_template": """
WITH ages AS (
    SELECT
        COALESCE(b.yob, EXTRACT(YEAR FROM b.dob)::INTEGER) AS birth_year
    FROM bm_beneficiary b
    JOIN bm_household h ON b.household_id = h.household_id
    WHERE h.home_block_name = ?
      AND COALESCE(b.yob, EXTRACT(YEAR FROM b.dob)::INTEGER) IS NOT NULL
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
        "param_slots": [{"name": "block", "entity_type": "block", "position": 1}],
        "result_ttl_seconds": 900,
    },

    "T51": {
        "abstract_question": "What is the enrollment source breakdown in {block}?",
        "date_filter": None,
        "sql_template": """
SELECT
    h.entitlement_source,
    COUNT(*) AS households,
    ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER(), 2) AS pct
FROM bm_household h
WHERE h.home_block_name = ?
GROUP BY h.entitlement_source
ORDER BY households DESC
""",
        "param_slots": [{"name": "block", "entity_type": "block", "position": 1}],
        "result_ttl_seconds": 900,
    },

    "T52": {
        "abstract_question": "What is the BIS record status in {block}?",
        "date_filter": None,
        "sql_template": """
SELECT
    b.bis_record_status,
    COUNT(*) AS count,
    ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER(), 2) AS pct
FROM bm_beneficiary b
JOIN bm_household h ON b.household_id = h.household_id
WHERE h.home_block_name = ?
GROUP BY b.bis_record_status
ORDER BY count DESC
""",
        "param_slots": [{"name": "block", "entity_type": "block", "position": 1}],
        "result_ttl_seconds": 900,
    },

    "T53": {
        "abstract_question": "How many beneficiaries have mobile numbers in {block}?",
        "date_filter": None,
        "sql_template": """
SELECT
    COUNT(*)        AS total_beneficiaries,
    COUNT(b.mobile) AS with_mobile,
    ROUND(COUNT(b.mobile) * 100.0 / COUNT(*), 2) AS mobile_pct
FROM bm_beneficiary b
JOIN bm_household h ON b.household_id = h.household_id
WHERE h.home_block_name = ?
""",
        "param_slots": [{"name": "block", "entity_type": "block", "position": 1}],
        "result_ttl_seconds": 900,
    },

    "T54": {
        "abstract_question": "What is the specialty coverage in {block}?",
        "date_filter": None,
        "sql_template": """
SELECT
    s.specialty_code,
    s.specialty_name,
    COUNT(DISTINCT s.hospital_id) AS hospital_count,
    SUM(s.admissions_prev_fy)     AS admissions_prev_fy
FROM hm_specialty_offered s
JOIN hm_hospital h ON s.hospital_id = h.hospital_id
WHERE h.block_name = ?
GROUP BY s.specialty_code, s.specialty_name
ORDER BY hospital_count DESC
""",
        "param_slots": [{"name": "block", "entity_type": "block", "position": 1}],
        "result_ttl_seconds": 900,
    },

    "T55": {
        "abstract_question": "How many hospitals have expired licenses in {block}?",
        "date_filter": None,
        "sql_template": """
SELECT
    COUNT(DISTINCT l.hospital_id) AS total_hospitals_with_licenses,
    COUNT(DISTINCT CASE WHEN l.expiry_date < CURRENT_DATE THEN l.hospital_id END) AS expired,
    ROUND(
        COUNT(DISTINCT CASE WHEN l.expiry_date < CURRENT_DATE THEN l.hospital_id END)
        * 100.0 / NULLIF(COUNT(DISTINCT l.hospital_id), 0),
        2
    ) AS pct_expired
FROM hm_license_certificate l
JOIN hm_hospital h ON l.hospital_id = h.hospital_id
WHERE h.block_name = ?
""",
        "param_slots": [{"name": "block", "entity_type": "block", "position": 1}],
        "result_ttl_seconds": 900,
    },

    "T56": {
        "abstract_question": "What is the bed capacity in {block}?",
        "date_filter": None,
        "sql_template": """
SELECT
    h.hospital_type,
    h.hospital_sub_type,
    COUNT(*)                              AS hospital_count,
    SUM(h.total_bed_strength)             AS total_beds,
    SUM(h.inpatient_beds)                 AS inpatient_beds,
    ROUND(AVG(h.total_bed_strength), 0)   AS avg_beds_per_hospital
FROM hm_hospital h
WHERE h.block_name = ?
GROUP BY h.hospital_type, h.hospital_sub_type
ORDER BY total_beds DESC
""",
        "param_slots": [{"name": "block", "entity_type": "block", "position": 1}],
        "result_ttl_seconds": 900,
    },

    "T57": {
        "abstract_question": "What is the staff-to-bed ratio in {block}?",
        "date_filter": None,
        "sql_template": """
SELECT
    h.hospital_type,
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
WHERE h.block_name = ?
GROUP BY h.hospital_type
ORDER BY staff_per_bed DESC
""",
        "param_slots": [{"name": "block", "entity_type": "block", "position": 1}],
        "result_ttl_seconds": 900,
    },

    "T58": {
        "abstract_question": "What is the monthly case trend in {block}?",
        "date_filter": {"alias": "c", "column": "admission_datetime"},
        "sql_template": """
SELECT
    date_trunc('month', c.admission_datetime)::DATE  AS month,
    COUNT(*)                                          AS case_count
FROM cm_case c
JOIN hm_hospital h ON c.hospital_id = h.hospital_id
WHERE h.block_name = ?
GROUP BY 1
ORDER BY 1
""",
        "param_slots": [{"name": "block", "entity_type": "block", "position": 1}],
        "result_ttl_seconds": 600,
    },

    "T59": {
        "abstract_question": "What is the claims summary for {block}?",
        "date_filter": {"alias": "c", "column": "admission_datetime"},
        "sql_template": """
SELECT
    h.block_name,
    COUNT(DISTINCT c.case_id)                AS total_cases,
    COUNT(DISTINCT cl.claim_id)              AS total_claims,
    ROUND(SUM(cl.amount_claimed),  2)        AS total_claimed,
    ROUND(SUM(cl.amount_approved), 2)        AS total_approved,
    ROUND(AVG(cl.settlement_tat_days), 1)    AS avg_tat_days
FROM cm_case c
JOIN  hm_hospital h  ON c.hospital_id = h.hospital_id
LEFT JOIN cm_claim cl ON c.case_id    = cl.case_id
WHERE h.block_name = ?
GROUP BY h.block_name
""",
        "param_slots": [{"name": "block", "entity_type": "block", "position": 1}],
        "result_ttl_seconds": 600,
    },

    "T60": {
        "abstract_question": "What is the claim status breakdown for {block}?",
        "date_filter": {"alias": "c", "column": "admission_datetime"},
        "sql_template": """
SELECT
    cl.claim_status,
    COUNT(*) AS count,
    ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER(), 2) AS pct,
    ROUND(SUM(cl.amount_claimed), 2) AS total_claimed
FROM cm_claim cl
JOIN cm_case     c ON cl.case_id    = c.case_id
JOIN hm_hospital h ON c.hospital_id = h.hospital_id
WHERE h.block_name = ?
GROUP BY cl.claim_status
ORDER BY count DESC
""",
        "param_slots": [{"name": "block", "entity_type": "block", "position": 1}],
        "result_ttl_seconds": 600,
    },

    "T61": {
        "abstract_question": "What is the settlement TAT in {block}?",
        "date_filter": {"alias": "cl", "column": "submitted_at"},
        "sql_template": """
SELECT
    h.block_name,
    ROUND(AVG(cl.settlement_tat_days), 1)                                           AS avg_tat,
    ROUND(PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY cl.settlement_tat_days)::numeric, 1)  AS median_tat,
    ROUND(PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY cl.settlement_tat_days)::numeric, 1)  AS p95_tat,
    MAX(cl.settlement_tat_days)                                                      AS max_tat
FROM cm_claim cl
JOIN cm_case     c ON cl.case_id    = c.case_id
JOIN hm_hospital h ON c.hospital_id = h.hospital_id
WHERE h.block_name = ?
  AND cl.settlement_tat_days IS NOT NULL
GROUP BY h.block_name
""",
        "param_slots": [{"name": "block", "entity_type": "block", "position": 1}],
        "result_ttl_seconds": 600,
    },

    "T62": {
        "abstract_question": "What is the rejection rate in {block}?",
        "date_filter": {"alias": "cl", "column": "submitted_at"},
        "sql_template": """
SELECT
    h.block_name,
    COUNT(cl.claim_id)   AS total_claims,
    COUNT(CASE WHEN cl.claim_status = 'REJECTED' THEN 1 END) AS rejected_claims,
    ROUND(
        COUNT(CASE WHEN cl.claim_status = 'REJECTED' THEN 1 END)
        * 100.0 / NULLIF(COUNT(cl.claim_id), 0),
        2
    ) AS rejection_rate_pct
FROM cm_claim cl
JOIN cm_case     c ON cl.case_id    = c.case_id
JOIN hm_hospital h ON c.hospital_id = h.hospital_id
WHERE h.block_name = ?
GROUP BY h.block_name
""",
        "param_slots": [{"name": "block", "entity_type": "block", "position": 1}],
        "result_ttl_seconds": 600,
    },

    "T63": {
        "abstract_question": "What is the public vs private split in {block}?",
        "date_filter": {"alias": "c", "column": "admission_datetime"},
        "sql_template": """
SELECT
    h.hospital_type,
    COUNT(DISTINCT c.case_id)                                               AS case_count,
    ROUND(COUNT(DISTINCT c.case_id) * 100.0
          / SUM(COUNT(DISTINCT c.case_id)) OVER(), 2)                      AS pct_cases,
    ROUND(SUM(cl.amount_claimed), 2)                                        AS total_claimed
FROM cm_case c
JOIN  hm_hospital h  ON c.hospital_id = h.hospital_id
LEFT JOIN cm_claim cl ON c.case_id    = cl.case_id
WHERE h.block_name = ?
GROUP BY h.hospital_type
ORDER BY case_count DESC
""",
        "param_slots": [{"name": "block", "entity_type": "block", "position": 1}],
        "result_ttl_seconds": 600,
    },

    "T64": {
        "abstract_question": "What are the top hospitals in {block} by claim volume?",
        "date_filter": {"alias": "c", "column": "admission_datetime"},
        "sql_template": """
SELECT
    h.hospital_name,
    h.hospital_type,
    COUNT(DISTINCT c.case_id)           AS case_count,
    ROUND(SUM(cl.amount_claimed), 2)    AS total_claimed
FROM cm_case c
JOIN  hm_hospital h  ON c.hospital_id = h.hospital_id
LEFT JOIN cm_claim cl ON c.case_id    = cl.case_id
WHERE h.block_name = ?
GROUP BY h.hospital_id, h.hospital_name, h.hospital_type
ORDER BY case_count DESC

""",
        "param_slots": [{"name": "block", "entity_type": "block", "position": 1}],
        "result_ttl_seconds": 600,
    },

    "T65": {
        "abstract_question": "What are the top procedures in {block}?",
        "date_filter": {"alias": "c", "column": "admission_datetime"},
        "sql_template": """
SELECT
    pl.hbp_procedure_code,
    p.procedure_name,
    p.specialty_code,
    COUNT(*)                                 AS usage_count,
    ROUND(SUM(pl.computed_final_amount), 2)  AS total_amount
FROM cm_preauth_procedure_line pl
JOIN ref_hbp_procedure_master p  ON pl.hbp_procedure_code = p.hbp_procedure_code
JOIN cm_preauth_request pr       ON pl.preauth_id         = pr.preauth_id
JOIN cm_case c                   ON pr.case_id            = c.case_id
JOIN hm_hospital h               ON c.hospital_id        = h.hospital_id
WHERE h.block_name = ?
GROUP BY pl.hbp_procedure_code, p.procedure_name, p.specialty_code
ORDER BY usage_count DESC

""",
        "param_slots": [{"name": "block", "entity_type": "block", "position": 1}],
        "result_ttl_seconds": 600,
    },

    "T66": {
        "abstract_question": "What are the top diagnoses in {block}?",
        "date_filter": {"alias": "c", "column": "admission_datetime"},
        "sql_template": """
SELECT
    d.icd_code,
    d.diagnosis_text,
    COUNT(*) AS count
FROM cm_case_diagnosis d
JOIN cm_case     c ON d.case_id     = c.case_id
JOIN hm_hospital h ON c.hospital_id = h.hospital_id
WHERE h.block_name = ?
  AND d.diagnosis_type = 'PRIMARY'
GROUP BY d.icd_code, d.diagnosis_text
ORDER BY count DESC

""",
        "param_slots": [{"name": "block", "entity_type": "block", "position": 1}],
        "result_ttl_seconds": 600,
    },

    "T67": {
        "abstract_question": "What is the disease burden in {block}?",
        "date_filter": {"alias": "c", "column": "admission_datetime"},
        "sql_template": """
SELECT
    d.diagnosis_category AS disease_category,
    COUNT(*) AS case_count,
    ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER(), 2) AS pct
FROM cm_case_diagnosis d
JOIN cm_case     c ON d.case_id     = c.case_id
JOIN hm_hospital h ON c.hospital_id = h.hospital_id
WHERE h.block_name = ?
  AND d.diagnosis_type = 'PRIMARY'
GROUP BY 1
ORDER BY case_count DESC
""",
        "param_slots": [{"name": "block", "entity_type": "block", "position": 1}],
        "result_ttl_seconds": 600,
    },

    "T68": {
        "abstract_question": "What is the discharge type distribution in {block}?",
        "date_filter": {"alias": "c", "column": "admission_datetime"},
        "sql_template": """
SELECT
    c.discharge_type,
    COUNT(*) AS count,
    ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER(), 2) AS pct
FROM cm_case c
JOIN hm_hospital h ON c.hospital_id = h.hospital_id
WHERE h.block_name = ?
  AND c.discharge_type IS NOT NULL
GROUP BY c.discharge_type
ORDER BY count DESC
""",
        "param_slots": [{"name": "block", "entity_type": "block", "position": 1}],
        "result_ttl_seconds": 600,
    },

    "T69": {
        "abstract_question": "What is the financial summary for {block}?",
        "date_filter": {"alias": "c", "column": "admission_datetime"},
        "sql_template": """
SELECT
    ROUND(SUM(CASE WHEN cl.claim_status = 'SETTLED'
                   THEN cl.amount_approved ELSE 0 END), 2)                        AS total_settled,
    ROUND(SUM(CASE WHEN cl.claim_status IN ('APPROVED','QUERY_RAISED','PENDING')
                   THEN cl.amount_approved ELSE 0 END), 2)                        AS total_pending,
    ROUND(SUM(CASE WHEN cl.claim_status = 'REJECTED'
                   THEN cl.amount_claimed ELSE 0 END), 2)                         AS total_rejected,
    ROUND(SUM(COALESCE(cl.amount_claimed, 0)), 2)                                 AS grand_total_claimed
FROM cm_claim cl
JOIN cm_case     c ON cl.case_id    = c.case_id
JOIN hm_hospital h ON c.hospital_id = h.hospital_id
WHERE h.block_name = ?
""",
        "param_slots": [{"name": "block", "entity_type": "block", "position": 1}],
        "result_ttl_seconds": 600,
    },

    # ── I. Extended District Variants (T70-T99) ───────────────────────────────

    "T70": {
        "abstract_question": "What percentage of beneficiaries in {district} have never utilized the scheme?",
        "date_filter": None,
        "sql_template": """
WITH enrolled AS (
    SELECT b.beneficiary_id
    FROM bm_beneficiary b
    JOIN bm_household h ON b.household_id = h.household_id
    WHERE h.home_district_code = ?
),
utilized AS (
    SELECT DISTINCT c.beneficiary_id
    FROM cm_case c
    WHERE c.beneficiary_id IN (SELECT beneficiary_id FROM enrolled)
)
SELECT
    COUNT(e.beneficiary_id)                                                       AS total_enrolled,
    COUNT(u.beneficiary_id)                                                       AS ever_utilized,
    COUNT(e.beneficiary_id) - COUNT(u.beneficiary_id)                            AS never_utilized,
    ROUND(
        (COUNT(e.beneficiary_id) - COUNT(u.beneficiary_id))
        * 100.0 / NULLIF(COUNT(e.beneficiary_id), 0),
        1
    )                                                                             AS never_utilized_pct
FROM enrolled e
LEFT JOIN utilized u ON e.beneficiary_id = u.beneficiary_id
""",
        "param_slots": [{"name": "district", "entity_type": "district", "position": 1}],
        "result_ttl_seconds": 600,
    },

    "T71": {
        "abstract_question": "What is the average time from enrolment to card issuance in {district}?",
        "date_filter": None,
        "sql_template": """
SELECT
    h.home_district_code                                                          AS district_name,
    COUNT(DISTINCT er.enrolment_request_id)                                       AS total_enrolments,
    COUNT(DISTINCT CASE WHEN ca.issued_at IS NOT NULL THEN er.enrolment_request_id END) AS with_card,
    ROUND(AVG(DATE_DIFF('day', er.submitted_at::DATE, ca.issued_at::DATE)), 1)    AS avg_days_to_card,
    ROUND(
        PERCENTILE_CONT(0.50) WITHIN GROUP (
            ORDER BY DATE_DIFF('day', er.submitted_at::DATE, ca.issued_at::DATE)
        ),
        1
    )                                                                             AS median_days_to_card
FROM bm_enrolment_request er
JOIN bm_beneficiary b  ON er.beneficiary_id = b.beneficiary_id
JOIN bm_household   h  ON b.household_id    = h.household_id
LEFT JOIN bm_card   ca ON er.beneficiary_id = ca.beneficiary_id
WHERE h.home_district_code = ?
  AND ca.issued_at IS NOT NULL
GROUP BY h.home_district_code
""",
        "param_slots": [{"name": "district", "entity_type": "district", "position": 1}],
        "result_ttl_seconds": 600,
    },

    "T72": {
        "abstract_question": "How many duplicate beneficiary records exist in {district}?",
        "date_filter": None,
        "sql_template": """
SELECT
    h.home_district_code                                                         AS district_name,
    COUNT(b.beneficiary_id)                                                      AS total_beneficiaries,
    COUNT(CASE WHEN b.is_duplicate = TRUE THEN 1 END)                            AS duplicate_count,
    ROUND(
        COUNT(CASE WHEN b.is_duplicate = TRUE THEN 1 END)
        * 100.0 / NULLIF(COUNT(b.beneficiary_id), 0),
        2
    )                                                                            AS duplicate_rate_pct
FROM bm_beneficiary b
JOIN bm_household h ON b.household_id = h.household_id
WHERE h.home_district_code = ?
GROUP BY h.home_district_code
""",
        "param_slots": [{"name": "district", "entity_type": "district", "position": 1}],
        "result_ttl_seconds": 600,
    },

    "T73": {
        "abstract_question": "What is the card status distribution in {district}?",
        "date_filter": None,
        "sql_template": """
SELECT
    ca.card_status,
    COUNT(*)                                                                     AS card_count,
    ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER(), 2)                           AS pct
FROM bm_card ca
JOIN bm_beneficiary b ON ca.beneficiary_id = b.beneficiary_id
JOIN bm_household   h ON b.household_id    = h.household_id
WHERE h.home_district_code = ?
GROUP BY ca.card_status
ORDER BY card_count DESC
""",
        "param_slots": [{"name": "district", "entity_type": "district", "position": 1}],
        "result_ttl_seconds": 600,
    },

    "T74": {
        "abstract_question": "What is the enrolment request rejection rate in {district}?",
        "date_filter": None,
        "sql_template": """
SELECT
    h.home_district_code                                                         AS district_name,
    COUNT(er.enrolment_request_id)                                               AS total_requests,
    COUNT(CASE WHEN er.status = 'REJECTED' THEN 1 END)                          AS rejected,
    ROUND(
        COUNT(CASE WHEN er.status = 'REJECTED' THEN 1 END)
        * 100.0 / NULLIF(COUNT(er.enrolment_request_id), 0),
        2
    )                                                                            AS rejection_rate_pct
FROM bm_enrolment_request er
JOIN bm_beneficiary b ON er.beneficiary_id = b.beneficiary_id
JOIN bm_household   h ON b.household_id    = h.household_id
WHERE h.home_district_code = ?
GROUP BY h.home_district_code
""",
        "param_slots": [{"name": "district", "entity_type": "district", "position": 1}],
        "result_ttl_seconds": 600,
    },

    "T75": {
        "abstract_question": "What is the authentication mode breakdown for enrolments in {district}?",
        "date_filter": None,
        "sql_template": """
SELECT
    er.auth_mode,
    COUNT(*)                                                                     AS request_count,
    ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER(), 2)                           AS pct
FROM bm_enrolment_request er
JOIN bm_beneficiary b ON er.beneficiary_id = b.beneficiary_id
JOIN bm_household   h ON b.household_id    = h.household_id
WHERE h.home_district_code = ?
GROUP BY er.auth_mode
ORDER BY request_count DESC
""",
        "param_slots": [{"name": "district", "entity_type": "district", "position": 1}],
        "result_ttl_seconds": 600,
    },

    "T76": {
        "abstract_question": "What is the pre-auth approval vs rejection vs query distribution in {district}?",
        "date_filter": {"alias": "pa", "column": "initiated_at"},
        "sql_template": """
SELECT
    pa.status,
    COUNT(*)                                                                     AS request_count,
    ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER(), 2)                           AS pct
FROM cm_preauth_request pa
JOIN cm_case c ON pa.case_id = c.case_id
WHERE c.hospital_district = ?
GROUP BY pa.status
ORDER BY request_count DESC
""",
        "param_slots": [{"name": "district", "entity_type": "district", "position": 1}],
        "result_ttl_seconds": 600,
    },

    "T77": {
        "abstract_question": "What is the average pre-auth turnaround time in {district}?",
        "date_filter": {"alias": "pa", "column": "initiated_at"},
        "sql_template": """
SELECT
    c.hospital_district                                                          AS district_name,
    COUNT(pa.preauth_id)                                                         AS total_preauths,
    ROUND(
        AVG(DATE_DIFF('day', pa.initiated_at::DATE, pa.ppd_decision_at::DATE)),
        1
    )                                                                            AS avg_tat_days,
    ROUND(
        PERCENTILE_CONT(0.50) WITHIN GROUP (
            ORDER BY DATE_DIFF('day', pa.initiated_at::DATE, pa.ppd_decision_at::DATE)
        ),
        1
    )                                                                            AS median_tat_days
FROM cm_preauth_request pa
JOIN cm_case c ON pa.case_id = c.case_id
WHERE c.hospital_district = ?
  AND pa.ppd_decision_at IS NOT NULL
GROUP BY c.hospital_district
""",
        "param_slots": [{"name": "district", "entity_type": "district", "position": 1}],
        "result_ttl_seconds": 600,
    },

    "T78": {
        "abstract_question": "What is the gap between amount claimed and amount approved in {district}?",
        "date_filter": {"alias": "c", "column": "admission_datetime"},
        "sql_template": """
SELECT
    c.hospital_district                                                           AS district_name,
    ROUND(SUM(cl.amount_claimed),  2)                                             AS total_claimed,
    ROUND(SUM(cl.amount_approved), 2)                                             AS total_approved,
    ROUND(SUM(cl.amount_claimed) - SUM(cl.amount_approved), 2)                   AS gap_amount,
    ROUND(
        (SUM(cl.amount_claimed) - SUM(cl.amount_approved))
        * 100.0 / NULLIF(SUM(cl.amount_claimed), 0),
        1
    )                                                                             AS gap_pct
FROM cm_claim cl
JOIN cm_case c ON cl.case_id = c.case_id
WHERE c.hospital_district = ?
GROUP BY c.hospital_district
""",
        "param_slots": [{"name": "district", "entity_type": "district", "position": 1}],
        "result_ttl_seconds": 600,
    },

    "T79": {
        "abstract_question": "What is the average claim value by procedure in {district}?",
        "date_filter": {"alias": "c", "column": "admission_datetime"},
        "sql_template": """
SELECT
    pl.hbp_procedure_code,
    p.procedure_name,
    p.specialty_name,
    COUNT(DISTINCT cl.claim_id)                                                   AS claim_count,
    ROUND(AVG(cl.amount_approved), 2)                                             AS avg_approved_amount
FROM cm_preauth_procedure_line pl
JOIN ref_hbp_procedure_master p   ON pl.hbp_procedure_code = p.hbp_procedure_code
JOIN cm_preauth_request pr        ON pl.preauth_id         = pr.preauth_id
JOIN cm_case c                    ON pr.case_id            = c.case_id
JOIN cm_claim cl                  ON c.case_id             = cl.case_id
WHERE c.hospital_district = ?
GROUP BY pl.hbp_procedure_code, p.procedure_name, p.specialty_name
ORDER BY avg_approved_amount DESC
LIMIT 20
""",
        "param_slots": [{"name": "district", "entity_type": "district", "position": 1}],
        "result_ttl_seconds": 600,
    },

    "T80": {
        "abstract_question": "What is the aging analysis of pending claims in {district}?",
        "date_filter": None,
        "sql_template": """
SELECT
    CASE
        WHEN DATE_DIFF('day', cl.submitted_at::DATE, CURRENT_DATE) <= 30  THEN '0-30 days'
        WHEN DATE_DIFF('day', cl.submitted_at::DATE, CURRENT_DATE) <= 60  THEN '31-60 days'
        WHEN DATE_DIFF('day', cl.submitted_at::DATE, CURRENT_DATE) <= 90  THEN '61-90 days'
        WHEN DATE_DIFF('day', cl.submitted_at::DATE, CURRENT_DATE) <= 180 THEN '91-180 days'
        ELSE '180+ days'
    END                                                                           AS aging_bucket,
    COUNT(cl.claim_id)                                                            AS claim_count,
    ROUND(SUM(cl.amount_claimed), 2)                                              AS total_claimed
FROM cm_claim cl
JOIN cm_case c ON cl.case_id = c.case_id
WHERE c.hospital_district = ?
  AND cl.claim_status = 'PENDING'
GROUP BY 1
ORDER BY MIN(DATE_DIFF('day', cl.submitted_at::DATE, CURRENT_DATE))
""",
        "param_slots": [{"name": "district", "entity_type": "district", "position": 1}],
        "result_ttl_seconds": 600,
    },

    "T81": {
        "abstract_question": "What is the per-beneficiary spend in {district}?",
        "date_filter": {"alias": "c", "column": "admission_datetime"},
        "sql_template": """
SELECT
    c.hospital_district                                                           AS district_name,
    COUNT(DISTINCT c.beneficiary_id)                                              AS unique_beneficiaries,
    ROUND(SUM(cl.amount_approved), 2)                                             AS total_approved,
    ROUND(
        SUM(cl.amount_approved) / NULLIF(COUNT(DISTINCT c.beneficiary_id), 0),
        2
    )                                                                             AS spend_per_beneficiary
FROM cm_case c
LEFT JOIN cm_claim cl ON c.case_id = cl.case_id
WHERE c.hospital_district = ?
GROUP BY c.hospital_district
""",
        "param_slots": [{"name": "district", "entity_type": "district", "position": 1}],
        "result_ttl_seconds": 600,
    },

    "T82": {
        "abstract_question": "Which hospitals in {district} are treating specialties they do not officially offer?",
        "date_filter": None,
        "sql_template": """
SELECT
    h.hospital_name,
    h.hospital_type,
    p.specialty_code                                                              AS treated_specialty,
    p.specialty_name                                                              AS treated_specialty_name,
    COUNT(DISTINCT c.case_id)                                                     AS case_count
FROM cm_preauth_procedure_line pl
JOIN ref_hbp_procedure_master p  ON pl.hbp_procedure_code = p.hbp_procedure_code
JOIN cm_preauth_request pr       ON pl.preauth_id         = pr.preauth_id
JOIN cm_case c                   ON pr.case_id            = c.case_id
JOIN hm_hospital h               ON c.hospital_id         = h.hospital_id
WHERE c.hospital_district = ?
  AND NOT EXISTS (
      SELECT 1 FROM hm_specialty_offered so
      WHERE so.hospital_id   = h.hospital_id
        AND so.specialty_code = p.specialty_code
  )
GROUP BY h.hospital_name, h.hospital_type, p.specialty_code, p.specialty_name
ORDER BY case_count DESC
""",
        "param_slots": [{"name": "district", "entity_type": "district", "position": 1}],
        "result_ttl_seconds": 600,
    },

    "T83": {
        "abstract_question": "Which hospitals in {district} have case volumes exceeding their bed capacity?",
        "date_filter": {"alias": "c", "column": "admission_datetime"},
        "sql_template": """
SELECT
    h.hospital_name,
    h.hospital_type,
    h.inpatient_beds,
    COUNT(DISTINCT c.case_id)                                                     AS case_count,
    ROUND(
        COUNT(DISTINCT c.case_id) * 1.0 / NULLIF(h.inpatient_beds, 0),
        2
    )                                                                             AS cases_per_bed_ratio
FROM cm_case c
JOIN hm_hospital h ON c.hospital_id = h.hospital_id
WHERE c.hospital_district = ?
GROUP BY h.hospital_id, h.hospital_name, h.hospital_type, h.inpatient_beds
HAVING ROUND(
    COUNT(DISTINCT c.case_id) * 1.0 / NULLIF(h.inpatient_beds, 0),
    2
) > 0.5
ORDER BY cases_per_bed_ratio DESC
""",
        "param_slots": [{"name": "district", "entity_type": "district", "position": 1}],
        "result_ttl_seconds": 600,
    },

    "T84": {
        "abstract_question": "What is the accreditation status of hospitals in {district}?",
        "date_filter": None,
        "sql_template": """
SELECT
    h.hospital_name,
    h.hospital_type,
    h.accreditation_board,
    h.accreditation_level,
    h.accreditation_valid_upto,
    CASE
        WHEN h.accreditation_valid_upto IS NULL THEN 'NOT_ACCREDITED'
        WHEN h.accreditation_valid_upto >= CURRENT_DATE THEN 'VALID'
        ELSE 'EXPIRED'
    END                                                                           AS accreditation_status
FROM hm_hospital h
WHERE h.district_name = ?
ORDER BY h.hospital_name
""",
        "param_slots": [{"name": "district", "entity_type": "district", "position": 1}],
        "result_ttl_seconds": 900,
    },

    "T85": {
        "abstract_question": "What is the clinician workload (cases per doctor) in {district}?",
        "date_filter": {"alias": "c", "column": "admission_datetime"},
        "sql_template": """
WITH clinician_cases AS (
    SELECT
        pl.clinician_staff_id,
        COUNT(DISTINCT c.case_id) AS case_count
    FROM cm_preauth_procedure_line pl
    JOIN cm_preauth_request pr ON pl.preauth_id = pr.preauth_id
    JOIN cm_case c             ON pr.case_id    = c.case_id
    WHERE c.hospital_district = ?
      AND pl.clinician_staff_id IS NOT NULL
    GROUP BY pl.clinician_staff_id
)
SELECT
    COUNT(cc.clinician_staff_id)                                                  AS total_clinicians,
    ROUND(AVG(cc.case_count), 1)                                                  AS avg_cases_per_clinician,
    MAX(cc.case_count)                                                            AS max_cases_per_clinician,
    ROUND(
        PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY cc.case_count),
        1
    )                                                                             AS median_cases_per_clinician
FROM clinician_cases cc
""",
        "param_slots": [{"name": "district", "entity_type": "district", "position": 1}],
        "result_ttl_seconds": 600,
    },

    "T86": {
        "abstract_question": "What is the emergency vs elective admission ratio in {district}?",
        "date_filter": {"alias": "c", "column": "admission_datetime"},
        "sql_template": """
SELECT
    c.admission_type,
    COUNT(*)                                                                      AS case_count,
    ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER(), 1)                            AS pct
FROM cm_case c
WHERE c.hospital_district = ?
GROUP BY c.admission_type
ORDER BY case_count DESC
""",
        "param_slots": [{"name": "district", "entity_type": "district", "position": 1}],
        "result_ttl_seconds": 600,
    },

    "T87": {
        "abstract_question": "What is the average length of stay by procedure in {district}?",
        "date_filter": {"alias": "c", "column": "admission_datetime"},
        "sql_template": """
SELECT
    p.hbp_procedure_code,
    p.procedure_name,
    p.specialty_name,
    COUNT(DISTINCT c.case_id)                                                     AS case_count,
    ROUND(
        AVG(DATE_DIFF('day', c.admission_datetime::DATE, c.discharge_datetime::DATE)),
        1
    )                                                                             AS avg_los_days
FROM cm_preauth_procedure_line pl
JOIN ref_hbp_procedure_master p  ON pl.hbp_procedure_code = p.hbp_procedure_code
JOIN cm_preauth_request pr       ON pl.preauth_id         = pr.preauth_id
JOIN cm_case c                   ON pr.case_id            = c.case_id
WHERE c.hospital_district = ?
  AND c.discharge_datetime IS NOT NULL
GROUP BY p.hbp_procedure_code, p.procedure_name, p.specialty_name
ORDER BY avg_los_days DESC
LIMIT 20
""",
        "param_slots": [{"name": "district", "entity_type": "district", "position": 1}],
        "result_ttl_seconds": 600,
    },

    "T88": {
        "abstract_question": "Which hospitals in {district} have the highest LAMA/DAMA rate?",
        "date_filter": None,
        "sql_template": """
SELECT
    h.hospital_name,
    h.hospital_type,
    COUNT(d.case_id)                                                              AS total_discharges,
    COUNT(CASE WHEN d.lama_date IS NOT NULL THEN 1 END)                          AS lama_count,
    ROUND(
        COUNT(CASE WHEN d.lama_date IS NOT NULL THEN 1 END)
        * 100.0 / NULLIF(COUNT(d.case_id), 0),
        2
    )                                                                             AS lama_rate_pct
FROM cm_discharge d
JOIN cm_case c     ON d.case_id     = c.case_id
JOIN hm_hospital h ON c.hospital_id = h.hospital_id
WHERE c.hospital_district = ?
GROUP BY h.hospital_id, h.hospital_name, h.hospital_type
ORDER BY lama_rate_pct DESC
LIMIT 10
""",
        "param_slots": [{"name": "district", "entity_type": "district", "position": 1}],
        "result_ttl_seconds": 600,
    },

    "T89": {
        "abstract_question": "What is the mortality rate by hospital in {district}?",
        "date_filter": None,
        "sql_template": """
SELECT
    h.hospital_name,
    h.hospital_type,
    COUNT(d.case_id)                                                              AS total_discharges,
    COUNT(CASE WHEN d.death_date IS NOT NULL THEN 1 END)                         AS death_count,
    ROUND(
        COUNT(CASE WHEN d.death_date IS NOT NULL THEN 1 END)
        * 100.0 / NULLIF(COUNT(d.case_id), 0),
        2
    )                                                                             AS mortality_rate_pct
FROM cm_discharge d
JOIN cm_case c     ON d.case_id     = c.case_id
JOIN hm_hospital h ON c.hospital_id = h.hospital_id
WHERE c.hospital_district = ?
GROUP BY h.hospital_id, h.hospital_name, h.hospital_type
ORDER BY mortality_rate_pct DESC
LIMIT 10
""",
        "param_slots": [{"name": "district", "entity_type": "district", "position": 1}],
        "result_ttl_seconds": 600,
    },

    "T90": {
        "abstract_question": "What is the male vs female treatment ratio in {district}?",
        "date_filter": {"alias": "c", "column": "admission_datetime"},
        "sql_template": """
SELECT
    b.gender,
    COUNT(DISTINCT c.case_id)                                                     AS case_count,
    ROUND(COUNT(DISTINCT c.case_id) * 100.0 / SUM(COUNT(DISTINCT c.case_id)) OVER(), 1) AS pct
FROM cm_case c
JOIN bm_beneficiary b ON c.beneficiary_id = b.beneficiary_id
WHERE c.hospital_district = ?
GROUP BY b.gender
ORDER BY case_count DESC
""",
        "param_slots": [{"name": "district", "entity_type": "district", "position": 1}],
        "result_ttl_seconds": 600,
    },

    "T91": {
        "abstract_question": "Are elderly beneficiaries (65+) in {district} utilizing the scheme proportionally?",
        "date_filter": None,
        "sql_template": """
WITH enrolled AS (
    SELECT
        b.beneficiary_id,
        CASE
            WHEN (EXTRACT(YEAR FROM CURRENT_DATE)::INTEGER - b.yob) >= 65 THEN 'elderly'
            ELSE 'non_elderly'
        END AS age_group
    FROM bm_beneficiary b
    JOIN bm_household h ON b.household_id = h.household_id
    WHERE h.home_district_code = ?
      AND b.yob IS NOT NULL
),
treated AS (
    SELECT
        c.beneficiary_id,
        CASE
            WHEN (EXTRACT(YEAR FROM CURRENT_DATE)::INTEGER - b.yob) >= 65 THEN 'elderly'
            ELSE 'non_elderly'
        END AS age_group
    FROM cm_case c
    JOIN bm_beneficiary b ON c.beneficiary_id = b.beneficiary_id
    JOIN bm_household   h ON b.household_id    = h.household_id
    WHERE h.home_district_code = ?
      AND b.yob IS NOT NULL
)
SELECT
    e.age_group,
    COUNT(DISTINCT e.beneficiary_id)                                              AS enrolled_count,
    ROUND(COUNT(DISTINCT e.beneficiary_id) * 100.0 / SUM(COUNT(DISTINCT e.beneficiary_id)) OVER(), 1) AS pct_of_enrolled,
    COUNT(DISTINCT t.beneficiary_id)                                              AS treated_count,
    ROUND(COUNT(DISTINCT t.beneficiary_id) * 100.0 / NULLIF(SUM(COUNT(DISTINCT t.beneficiary_id)) OVER(), 0), 1) AS pct_of_treated
FROM enrolled e
LEFT JOIN treated t ON e.beneficiary_id = t.beneficiary_id AND e.age_group = t.age_group
GROUP BY e.age_group
""",
        "param_slots": [
            {"name": "district", "entity_type": "district", "position": 1},
            {"name": "district", "entity_type": "district", "position": 2},
        ],
        "result_ttl_seconds": 600,
    },

    "T92": {
        "abstract_question": "What proportion of cases in {district} involve patients travelling from other districts?",
        "date_filter": {"alias": "c", "column": "admission_datetime"},
        "sql_template": """
SELECT
    c.hospital_district                                                           AS hospital_district,
    COUNT(DISTINCT c.case_id)                                                     AS total_cases,
    COUNT(DISTINCT CASE WHEN h.home_district_code != c.hospital_district THEN c.case_id END) AS cross_district_cases,
    ROUND(
        COUNT(DISTINCT CASE WHEN h.home_district_code != c.hospital_district THEN c.case_id END)
        * 100.0 / NULLIF(COUNT(DISTINCT c.case_id), 0),
        1
    )                                                                             AS cross_district_pct
FROM cm_case c
JOIN bm_beneficiary b ON c.beneficiary_id = b.beneficiary_id
JOIN bm_household   h ON b.household_id   = h.household_id
WHERE c.hospital_district = ?
GROUP BY c.hospital_district
""",
        "param_slots": [{"name": "district", "entity_type": "district", "position": 1}],
        "result_ttl_seconds": 600,
    },

    "T93": {
        "abstract_question": "What is the communicable vs NCD vs maternal disease mix in {district}?",
        "date_filter": {"alias": "c", "column": "admission_datetime"},
        "sql_template": """
SELECT
    d.diagnosis_category,
    COUNT(*)                                                                      AS case_count,
    ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER(), 1)                            AS pct
FROM cm_case_diagnosis d
JOIN cm_case c ON d.case_id = c.case_id
WHERE c.hospital_district = ?
  AND d.diagnosis_type = 'PRIMARY'
GROUP BY d.diagnosis_category
ORDER BY case_count DESC
""",
        "param_slots": [{"name": "district", "entity_type": "district", "position": 1}],
        "result_ttl_seconds": 600,
    },

    "T94": {
        "abstract_question": "What is the rate of readmissions within 30 days in {district}?",
        "date_filter": {"alias": "c", "column": "admission_datetime"},
        "sql_template": """
WITH ordered_cases AS (
    SELECT
        c.case_id,
        c.beneficiary_id,
        c.admission_datetime,
        c.discharge_datetime,
        LAG(c.discharge_datetime) OVER (
            PARTITION BY c.beneficiary_id
            ORDER BY c.admission_datetime
        ) AS prev_discharge_datetime
    FROM cm_case c
    WHERE c.hospital_district = ?
)
SELECT
    COUNT(*)                                                                      AS total_cases,
    COUNT(CASE
        WHEN prev_discharge_datetime IS NOT NULL
         AND DATE_DIFF('day', prev_discharge_datetime::DATE, admission_datetime::DATE) <= 30
        THEN 1
    END)                                                                          AS readmission_count,
    ROUND(
        COUNT(CASE
            WHEN prev_discharge_datetime IS NOT NULL
             AND DATE_DIFF('day', prev_discharge_datetime::DATE, admission_datetime::DATE) <= 30
            THEN 1
        END) * 100.0 / NULLIF(COUNT(*), 0),
        1
    )                                                                             AS readmission_rate_pct
FROM ordered_cases
""",
        "param_slots": [{"name": "district", "entity_type": "district", "position": 1}],
        "result_ttl_seconds": 600,
    },

    "T96": {
        "abstract_question": "What is the failed payment amount for hospitals in {district}?",
        "date_filter": None,
        "sql_template": """
SELECT
    h.hospital_name,
    h.hospital_type,
    COUNT(p.claim_id)                                                             AS failed_payment_count,
    ROUND(SUM(p.amount_paid), 2)                                                  AS total_failed_amount
FROM cm_payment p
JOIN cm_claim cl ON p.claim_id    = cl.claim_id
JOIN cm_case  c  ON cl.case_id    = c.case_id
JOIN hm_hospital h ON c.hospital_id = h.hospital_id
WHERE p.payment_status = 'FAILED'
  AND c.hospital_district = ?
GROUP BY h.hospital_id, h.hospital_name, h.hospital_type
ORDER BY total_failed_amount DESC
""",
        "param_slots": [{"name": "district", "entity_type": "district", "position": 1}],
        "result_ttl_seconds": 600,
    },

    "T97": {
        "abstract_question": "What is the biometric authentication rate at discharge in {district}?",
        "date_filter": None,
        "sql_template": """
SELECT
    h.hospital_name,
    h.hospital_type,
    COUNT(d.case_id)                                                              AS total_discharges,
    COUNT(CASE WHEN d.biometric_auth_used = TRUE THEN 1 END)                     AS biometric_count,
    ROUND(
        COUNT(CASE WHEN d.biometric_auth_used = TRUE THEN 1 END)
        * 100.0 / NULLIF(COUNT(d.case_id), 0),
        1
    )                                                                             AS biometric_rate_pct
FROM cm_discharge d
JOIN cm_case c     ON d.case_id     = c.case_id
JOIN hm_hospital h ON c.hospital_id = h.hospital_id
WHERE c.hospital_district = ?
GROUP BY h.hospital_id, h.hospital_name, h.hospital_type
ORDER BY biometric_rate_pct DESC
""",
        "param_slots": [{"name": "district", "entity_type": "district", "position": 1}],
        "result_ttl_seconds": 600,
    },

    "T98": {
        "abstract_question": "What is the medicine provision rate at discharge in {district}?",
        "date_filter": None,
        "sql_template": """
SELECT
    h.hospital_name,
    h.hospital_type,
    COUNT(d.case_id)                                                              AS total_discharges,
    COUNT(CASE WHEN d.provided_medicines_flag = TRUE THEN 1 END)                 AS medicines_provided_count,
    ROUND(
        COUNT(CASE WHEN d.provided_medicines_flag = TRUE THEN 1 END)
        * 100.0 / NULLIF(COUNT(d.case_id), 0),
        1
    )                                                                             AS medicine_provision_rate_pct
FROM cm_discharge d
JOIN cm_case c     ON d.case_id     = c.case_id
JOIN hm_hospital h ON c.hospital_id = h.hospital_id
WHERE c.hospital_district = ?
GROUP BY h.hospital_id, h.hospital_name, h.hospital_type
ORDER BY medicine_provision_rate_pct DESC
""",
        "param_slots": [{"name": "district", "entity_type": "district", "position": 1}],
        "result_ttl_seconds": 600,
    },

    "T99": {
        "abstract_question": "What is the enrolment-to-treatment funnel for {district}?",
        "date_filter": None,
        "sql_template": """
WITH enrolled AS (
    SELECT COUNT(DISTINCT h.household_id) AS cnt
    FROM bm_household h
    WHERE h.home_district_code = ?
),
card_issued AS (
    SELECT COUNT(DISTINCT ca.card_id) AS cnt
    FROM bm_card ca
    JOIN bm_beneficiary b ON ca.beneficiary_id = b.beneficiary_id
    JOIN bm_household   h ON b.household_id    = h.household_id
    WHERE h.home_district_code = ?
),
admitted AS (
    SELECT COUNT(DISTINCT c.case_id) AS cnt
    FROM cm_case c
    JOIN bm_beneficiary b ON c.beneficiary_id = b.beneficiary_id
    JOIN bm_household   h ON b.household_id   = h.household_id
    WHERE h.home_district_code = ?
),
claimed AS (
    SELECT COUNT(DISTINCT cl.claim_id) AS cnt
    FROM cm_claim cl
    JOIN cm_case c ON cl.case_id = c.case_id
    JOIN bm_beneficiary b ON c.beneficiary_id = b.beneficiary_id
    JOIN bm_household   h ON b.household_id   = h.household_id
    WHERE h.home_district_code = ?
),
paid AS (
    SELECT COUNT(DISTINCT p.claim_id) AS cnt
    FROM cm_payment p
    JOIN cm_claim cl ON p.claim_id = cl.claim_id
    JOIN cm_case c   ON cl.case_id = c.case_id
    JOIN bm_beneficiary b ON c.beneficiary_id = b.beneficiary_id
    JOIN bm_household   h ON b.household_id   = h.household_id
    WHERE h.home_district_code = ?
      AND p.payment_status = 'SUCCESS'
)
SELECT
    'enrolled_households'  AS funnel_step, 1 AS step_order, enrolled.cnt  AS count,
    100.0                                                                         AS pct_of_enrolled
FROM enrolled
UNION ALL
SELECT 'cards_issued',     2, card_issued.cnt,
    ROUND(card_issued.cnt * 100.0 / NULLIF(enrolled.cnt, 0), 1)
FROM card_issued, enrolled
UNION ALL
SELECT 'admitted',         3, admitted.cnt,
    ROUND(admitted.cnt * 100.0 / NULLIF(enrolled.cnt, 0), 1)
FROM admitted, enrolled
UNION ALL
SELECT 'claimed',          4, claimed.cnt,
    ROUND(claimed.cnt * 100.0 / NULLIF(enrolled.cnt, 0), 1)
FROM claimed, enrolled
UNION ALL
SELECT 'paid',             5, paid.cnt,
    ROUND(paid.cnt * 100.0 / NULLIF(enrolled.cnt, 0), 1)
FROM paid, enrolled
ORDER BY step_order
""",
        "param_slots": [
            {"name": "district", "entity_type": "district", "position": 1},
            {"name": "district", "entity_type": "district", "position": 2},
            {"name": "district", "entity_type": "district", "position": 3},
            {"name": "district", "entity_type": "district", "position": 4},
            {"name": "district", "entity_type": "district", "position": 5},
        ],
        "result_ttl_seconds": 600,
    },

    # ── J. Block Variants (T100-T111) ────────────────────────────────────────

    "T100": {
        "abstract_question": "What percentage of beneficiaries in {block} have never utilized the scheme?",
        "date_filter": None,
        "sql_template": """
WITH enrolled AS (
    SELECT b.beneficiary_id
    FROM bm_beneficiary b
    JOIN bm_household h ON b.household_id = h.household_id
    WHERE h.home_block_name = ?
),
utilized AS (
    SELECT DISTINCT c.beneficiary_id
    FROM cm_case c
    WHERE c.beneficiary_id IN (SELECT beneficiary_id FROM enrolled)
)
SELECT
    COUNT(e.beneficiary_id)                                                       AS total_enrolled,
    COUNT(u.beneficiary_id)                                                       AS ever_utilized,
    COUNT(e.beneficiary_id) - COUNT(u.beneficiary_id)                            AS never_utilized,
    ROUND(
        (COUNT(e.beneficiary_id) - COUNT(u.beneficiary_id))
        * 100.0 / NULLIF(COUNT(e.beneficiary_id), 0),
        1
    )                                                                             AS never_utilized_pct
FROM enrolled e
LEFT JOIN utilized u ON e.beneficiary_id = u.beneficiary_id
""",
        "param_slots": [{"name": "block", "entity_type": "block", "position": 1}],
        "result_ttl_seconds": 600,
    },

    "T101": {
        "abstract_question": "What is the card status distribution in {block}?",
        "date_filter": None,
        "sql_template": """
SELECT
    ca.card_status,
    COUNT(*)                                                                     AS card_count,
    ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER(), 2)                           AS pct
FROM bm_card ca
JOIN bm_beneficiary b ON ca.beneficiary_id = b.beneficiary_id
JOIN bm_household   h ON b.household_id    = h.household_id
WHERE h.home_block_name = ?
GROUP BY ca.card_status
ORDER BY card_count DESC
""",
        "param_slots": [{"name": "block", "entity_type": "block", "position": 1}],
        "result_ttl_seconds": 600,
    },

    "T102": {
        "abstract_question": "How many duplicate beneficiary records exist in {block}?",
        "date_filter": None,
        "sql_template": """
SELECT
    h.home_block_name                                                            AS block_name,
    COUNT(b.beneficiary_id)                                                      AS total_beneficiaries,
    COUNT(CASE WHEN b.is_duplicate = TRUE THEN 1 END)                            AS duplicate_count,
    ROUND(
        COUNT(CASE WHEN b.is_duplicate = TRUE THEN 1 END)
        * 100.0 / NULLIF(COUNT(b.beneficiary_id), 0),
        2
    )                                                                            AS duplicate_rate_pct
FROM bm_beneficiary b
JOIN bm_household h ON b.household_id = h.household_id
WHERE h.home_block_name = ?
GROUP BY h.home_block_name
""",
        "param_slots": [{"name": "block", "entity_type": "block", "position": 1}],
        "result_ttl_seconds": 600,
    },

    "T103": {
        "abstract_question": "What is the male vs female treatment ratio in {block}?",
        "date_filter": {"alias": "c", "column": "admission_datetime"},
        "sql_template": """
SELECT
    b.gender,
    COUNT(DISTINCT c.case_id)                                                     AS case_count,
    ROUND(COUNT(DISTINCT c.case_id) * 100.0 / SUM(COUNT(DISTINCT c.case_id)) OVER(), 1) AS pct
FROM cm_case c
JOIN bm_beneficiary b ON c.beneficiary_id = b.beneficiary_id
JOIN bm_household   h ON b.household_id   = h.household_id
WHERE h.home_block_name = ?
GROUP BY b.gender
ORDER BY case_count DESC
""",
        "param_slots": [{"name": "block", "entity_type": "block", "position": 1}],
        "result_ttl_seconds": 600,
    },

    "T104": {
        "abstract_question": "What is the emergency vs elective admission ratio in {block}?",
        "date_filter": {"alias": "c", "column": "admission_datetime"},
        "sql_template": """
SELECT
    c.admission_type,
    COUNT(*)                                                                      AS case_count,
    ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER(), 1)                            AS pct
FROM cm_case c
JOIN bm_beneficiary b ON c.beneficiary_id = b.beneficiary_id
JOIN bm_household   h ON b.household_id   = h.household_id
WHERE h.home_block_name = ?
GROUP BY c.admission_type
ORDER BY case_count DESC
""",
        "param_slots": [{"name": "block", "entity_type": "block", "position": 1}],
        "result_ttl_seconds": 600,
    },

    "T105": {
        "abstract_question": "What is the pre-auth approval distribution in {block}?",
        "date_filter": {"alias": "pa", "column": "initiated_at"},
        "sql_template": """
SELECT
    pa.status,
    COUNT(*)                                                                     AS request_count,
    ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER(), 2)                           AS pct
FROM cm_preauth_request pa
JOIN cm_case c        ON pa.case_id      = c.case_id
JOIN bm_beneficiary b ON c.beneficiary_id = b.beneficiary_id
JOIN bm_household   h ON b.household_id   = h.household_id
WHERE h.home_block_name = ?
GROUP BY pa.status
ORDER BY request_count DESC
""",
        "param_slots": [{"name": "block", "entity_type": "block", "position": 1}],
        "result_ttl_seconds": 600,
    },

    "T106": {
        "abstract_question": "What is the average claim value in {block}?",
        "date_filter": {"alias": "c", "column": "admission_datetime"},
        "sql_template": """
SELECT
    h.home_block_name                                                            AS block_name,
    COUNT(DISTINCT cl.claim_id)                                                  AS total_claims,
    ROUND(AVG(cl.amount_claimed),  2)                                            AS avg_claimed,
    ROUND(AVG(cl.amount_approved), 2)                                            AS avg_approved,
    ROUND(SUM(cl.amount_approved), 2)                                            AS total_approved
FROM cm_claim cl
JOIN cm_case        c ON cl.case_id       = c.case_id
JOIN bm_beneficiary b ON c.beneficiary_id = b.beneficiary_id
JOIN bm_household   h ON b.household_id   = h.household_id
WHERE h.home_block_name = ?
GROUP BY h.home_block_name
""",
        "param_slots": [{"name": "block", "entity_type": "block", "position": 1}],
        "result_ttl_seconds": 600,
    },

    "T107": {
        "abstract_question": "What is the mortality rate in {block}?",
        "date_filter": None,
        "sql_template": """
SELECT
    h.home_block_name                                                            AS block_name,
    COUNT(d.case_id)                                                             AS total_discharges,
    COUNT(CASE WHEN d.death_date IS NOT NULL THEN 1 END)                        AS death_count,
    ROUND(
        COUNT(CASE WHEN d.death_date IS NOT NULL THEN 1 END)
        * 100.0 / NULLIF(COUNT(d.case_id), 0),
        2
    )                                                                            AS mortality_rate_pct
FROM cm_discharge d
JOIN cm_case        c ON d.case_id        = c.case_id
JOIN bm_beneficiary b ON c.beneficiary_id = b.beneficiary_id
JOIN bm_household   h ON b.household_id   = h.household_id
WHERE h.home_block_name = ?
GROUP BY h.home_block_name
""",
        "param_slots": [{"name": "block", "entity_type": "block", "position": 1}],
        "result_ttl_seconds": 600,
    },

    "T108": {
        "abstract_question": "What is the LAMA/DAMA rate in {block}?",
        "date_filter": None,
        "sql_template": """
SELECT
    h.home_block_name                                                            AS block_name,
    COUNT(d.case_id)                                                             AS total_discharges,
    COUNT(CASE WHEN d.lama_date IS NOT NULL THEN 1 END)                         AS lama_count,
    ROUND(
        COUNT(CASE WHEN d.lama_date IS NOT NULL THEN 1 END)
        * 100.0 / NULLIF(COUNT(d.case_id), 0),
        2
    )                                                                            AS lama_rate_pct
FROM cm_discharge d
JOIN cm_case        c ON d.case_id        = c.case_id
JOIN bm_beneficiary b ON c.beneficiary_id = b.beneficiary_id
JOIN bm_household   h ON b.household_id   = h.household_id
WHERE h.home_block_name = ?
GROUP BY h.home_block_name
""",
        "param_slots": [{"name": "block", "entity_type": "block", "position": 1}],
        "result_ttl_seconds": 600,
    },

    "T109": {
        "abstract_question": "What is the communicable vs NCD disease mix in {block}?",
        "date_filter": {"alias": "c", "column": "admission_datetime"},
        "sql_template": """
SELECT
    d.diagnosis_category,
    COUNT(*)                                                                      AS case_count,
    ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER(), 1)                            AS pct
FROM cm_case_diagnosis d
JOIN cm_case        c ON d.case_id        = c.case_id
JOIN bm_beneficiary b ON c.beneficiary_id = b.beneficiary_id
JOIN bm_household   h ON b.household_id   = h.household_id
WHERE h.home_block_name = ?
  AND d.diagnosis_type = 'PRIMARY'
GROUP BY d.diagnosis_category
ORDER BY case_count DESC
""",
        "param_slots": [{"name": "block", "entity_type": "block", "position": 1}],
        "result_ttl_seconds": 600,
    },

    "T110": {
        "abstract_question": "What is the portability volume from {block}?",
        "date_filter": {"alias": "c", "column": "admission_datetime"},
        "sql_template": """
SELECT
    c.hospital_state_code                                                        AS destination_state,
    COUNT(DISTINCT c.case_id)                                                    AS portability_cases,
    ROUND(SUM(cl.amount_claimed), 2)                                             AS total_claimed
FROM cm_case c
JOIN bm_beneficiary b ON c.beneficiary_id = b.beneficiary_id
JOIN bm_household   h ON b.household_id   = h.household_id
LEFT JOIN cm_claim cl ON c.case_id        = cl.case_id
WHERE c.is_portability = TRUE
  AND h.home_block_name = ?
GROUP BY c.hospital_state_code
ORDER BY portability_cases DESC
""",
        "param_slots": [{"name": "block", "entity_type": "block", "position": 1}],
        "result_ttl_seconds": 600,
    },

    "T111": {
        "abstract_question": "What is the enrolment-to-treatment funnel for {block}?",
        "date_filter": None,
        "sql_template": """
WITH enrolled AS (
    SELECT COUNT(DISTINCT h.household_id) AS cnt
    FROM bm_household h
    WHERE h.home_block_name = ?
),
card_issued AS (
    SELECT COUNT(DISTINCT ca.card_id) AS cnt
    FROM bm_card ca
    JOIN bm_beneficiary b ON ca.beneficiary_id = b.beneficiary_id
    JOIN bm_household   h ON b.household_id    = h.household_id
    WHERE h.home_block_name = ?
),
admitted AS (
    SELECT COUNT(DISTINCT c.case_id) AS cnt
    FROM cm_case c
    JOIN bm_beneficiary b ON c.beneficiary_id = b.beneficiary_id
    JOIN bm_household   h ON b.household_id   = h.household_id
    WHERE h.home_block_name = ?
),
claimed AS (
    SELECT COUNT(DISTINCT cl.claim_id) AS cnt
    FROM cm_claim cl
    JOIN cm_case c ON cl.case_id = c.case_id
    JOIN bm_beneficiary b ON c.beneficiary_id = b.beneficiary_id
    JOIN bm_household   h ON b.household_id   = h.household_id
    WHERE h.home_block_name = ?
),
paid AS (
    SELECT COUNT(DISTINCT p.claim_id) AS cnt
    FROM cm_payment p
    JOIN cm_claim cl ON p.claim_id = cl.claim_id
    JOIN cm_case c   ON cl.case_id = c.case_id
    JOIN bm_beneficiary b ON c.beneficiary_id = b.beneficiary_id
    JOIN bm_household   h ON b.household_id   = h.household_id
    WHERE h.home_block_name = ?
      AND p.payment_status = 'SUCCESS'
)
SELECT
    'enrolled_households'  AS funnel_step, 1 AS step_order, enrolled.cnt  AS count,
    100.0                                                                        AS pct_of_enrolled
FROM enrolled
UNION ALL
SELECT 'cards_issued',     2, card_issued.cnt,
    ROUND(card_issued.cnt * 100.0 / NULLIF(enrolled.cnt, 0), 1)
FROM card_issued, enrolled
UNION ALL
SELECT 'admitted',         3, admitted.cnt,
    ROUND(admitted.cnt * 100.0 / NULLIF(enrolled.cnt, 0), 1)
FROM admitted, enrolled
UNION ALL
SELECT 'claimed',          4, claimed.cnt,
    ROUND(claimed.cnt * 100.0 / NULLIF(enrolled.cnt, 0), 1)
FROM claimed, enrolled
UNION ALL
SELECT 'paid',             5, paid.cnt,
    ROUND(paid.cnt * 100.0 / NULLIF(enrolled.cnt, 0), 1)
FROM paid, enrolled
ORDER BY step_order
""",
        "param_slots": [
            {"name": "block", "entity_type": "block", "position": 1},
            {"name": "block", "entity_type": "block", "position": 2},
            {"name": "block", "entity_type": "block", "position": 3},
            {"name": "block", "entity_type": "block", "position": 4},
            {"name": "block", "entity_type": "block", "position": 5},
        ],
        "result_ttl_seconds": 600,
    },

    # ── K. Comparison Templates (T112-T127) ──────────────────────────────────

    "T112": {
        "abstract_question": "Compare enrolment rates between {district} and {district_2}?",
        "date_filter": None,
        "sql_template": """
SELECT
    h.home_district_code                          AS district_name,
    COUNT(DISTINCT h.household_id)                AS households,
    COUNT(DISTINCT b.beneficiary_id)              AS beneficiaries,
    COUNT(DISTINCT CASE WHEN ca.card_status = 'ACTIVE' THEN ca.card_id END) AS active_cards
FROM bm_household h
LEFT JOIN bm_beneficiary b ON h.household_id   = b.household_id
LEFT JOIN bm_card ca       ON b.beneficiary_id = ca.beneficiary_id
WHERE h.home_district_code IN (?, ?)
GROUP BY h.home_district_code
ORDER BY beneficiaries DESC
""",
        "param_slots": [
            {"name": "district",   "entity_type": "district", "position": 1},
            {"name": "district_2", "entity_type": "district", "position": 2},
        ],
        "result_ttl_seconds": 600,
    },

    "T113": {
        "abstract_question": "Compare claim approval rates between {district} and {district_2}?",
        "date_filter": {"alias": "c", "column": "admission_datetime"},
        "sql_template": """
SELECT
    c.hospital_district                                                           AS district_name,
    COUNT(cl.claim_id)                                                            AS total_claims,
    ROUND(
        AVG(cl.amount_approved / NULLIF(cl.amount_claimed, 0) * 100),
        1
    )                                                                             AS avg_approval_rate_pct
FROM cm_claim cl
JOIN cm_case c ON cl.case_id = c.case_id
WHERE c.hospital_district IN (?, ?)
GROUP BY c.hospital_district
ORDER BY avg_approval_rate_pct DESC
""",
        "param_slots": [
            {"name": "district",   "entity_type": "district", "position": 1},
            {"name": "district_2", "entity_type": "district", "position": 2},
        ],
        "result_ttl_seconds": 600,
    },

    "T114": {
        "abstract_question": "Compare settlement TAT between {district} and {district_2}?",
        "date_filter": {"alias": "c", "column": "admission_datetime"},
        "sql_template": """
SELECT
    c.hospital_district                                                           AS district_name,
    ROUND(AVG(cl.settlement_tat_days), 1)                                         AS avg_tat_days,
    ROUND(
        PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY cl.settlement_tat_days),
        1
    )                                                                             AS median_tat_days
FROM cm_claim cl
JOIN cm_case c ON cl.case_id = c.case_id
WHERE c.hospital_district IN (?, ?)
  AND cl.settlement_tat_days IS NOT NULL
GROUP BY c.hospital_district
ORDER BY avg_tat_days
""",
        "param_slots": [
            {"name": "district",   "entity_type": "district", "position": 1},
            {"name": "district_2", "entity_type": "district", "position": 2},
        ],
        "result_ttl_seconds": 600,
    },

    "T115": {
        "abstract_question": "Compare per-beneficiary spend between {district} and {district_2}?",
        "date_filter": {"alias": "c", "column": "admission_datetime"},
        "sql_template": """
SELECT
    c.hospital_district                                                           AS district_name,
    COUNT(DISTINCT c.beneficiary_id)                                              AS unique_beneficiaries,
    ROUND(SUM(cl.amount_approved), 2)                                             AS total_approved,
    ROUND(
        SUM(cl.amount_approved) / NULLIF(COUNT(DISTINCT c.beneficiary_id), 0),
        2
    )                                                                             AS spend_per_beneficiary
FROM cm_case c
LEFT JOIN cm_claim cl ON c.case_id = cl.case_id
WHERE c.hospital_district IN (?, ?)
GROUP BY c.hospital_district
ORDER BY spend_per_beneficiary DESC
""",
        "param_slots": [
            {"name": "district",   "entity_type": "district", "position": 1},
            {"name": "district_2", "entity_type": "district", "position": 2},
        ],
        "result_ttl_seconds": 600,
    },

    "T118": {
        "abstract_question": "Compare utilization rates between {district} and {district_2}?",
        "date_filter": {"alias": "c", "column": "admission_datetime"},
        "sql_template": """
WITH enrolled AS (
    SELECT
        h.home_district_code AS district_name,
        COUNT(DISTINCT b.beneficiary_id) AS enrolled_count
    FROM bm_household h
    LEFT JOIN bm_beneficiary b ON h.household_id = b.household_id
    WHERE h.home_district_code IN (?, ?)
    GROUP BY h.home_district_code
),
treated AS (
    SELECT
        c.hospital_district AS district_name,
        COUNT(DISTINCT c.case_id) AS case_count
    FROM cm_case c
    WHERE c.hospital_district IN (?, ?)
    GROUP BY c.hospital_district
)
SELECT
    e.district_name,
    e.enrolled_count,
    COALESCE(t.case_count, 0)                                                     AS case_count,
    ROUND(
        COALESCE(t.case_count, 0) * 1000.0 / NULLIF(e.enrolled_count, 0),
        1
    )                                                                             AS cases_per_1000_enrolled
FROM enrolled e
LEFT JOIN treated t ON e.district_name = t.district_name
ORDER BY cases_per_1000_enrolled DESC
""",
        "param_slots": [
            {"name": "district",   "entity_type": "district", "position": 1},
            {"name": "district_2", "entity_type": "district", "position": 2},
            {"name": "district",   "entity_type": "district", "position": 3},
            {"name": "district_2", "entity_type": "district", "position": 4},
        ],
        "result_ttl_seconds": 600,
    },

    "T119": {
        "abstract_question": "Compare mortality and LAMA/DAMA rates between {district} and {district_2}?",
        "date_filter": None,
        "sql_template": """
SELECT
    c.hospital_district                                                           AS district_name,
    COUNT(d.case_id)                                                              AS total_discharges,
    ROUND(
        COUNT(CASE WHEN d.death_date IS NOT NULL THEN 1 END)
        * 100.0 / NULLIF(COUNT(d.case_id), 0),
        2
    )                                                                             AS mortality_rate_pct,
    ROUND(
        COUNT(CASE WHEN d.lama_date IS NOT NULL THEN 1 END)
        * 100.0 / NULLIF(COUNT(d.case_id), 0),
        2
    )                                                                             AS lama_rate_pct
FROM cm_discharge d
JOIN cm_case c ON d.case_id = c.case_id
WHERE c.hospital_district IN (?, ?)
GROUP BY c.hospital_district
ORDER BY mortality_rate_pct DESC
""",
        "param_slots": [
            {"name": "district",   "entity_type": "district", "position": 1},
            {"name": "district_2", "entity_type": "district", "position": 2},
        ],
        "result_ttl_seconds": 600,
    },

    "T120": {
        "abstract_question": "Compare public vs private hospital utilization between {district} and {district_2}?",
        "date_filter": {"alias": "c", "column": "admission_datetime"},
        "sql_template": """
SELECT
    c.hospital_district                                                           AS district_name,
    h.hospital_type,
    COUNT(DISTINCT c.case_id)                                                     AS case_count,
    ROUND(
        COUNT(DISTINCT c.case_id) * 100.0
        / SUM(COUNT(DISTINCT c.case_id)) OVER (PARTITION BY c.hospital_district),
        1
    )                                                                             AS pct_of_district_cases
FROM cm_case c
JOIN hm_hospital h ON c.hospital_id = h.hospital_id
WHERE c.hospital_district IN (?, ?)
GROUP BY c.hospital_district, h.hospital_type
ORDER BY c.hospital_district, case_count DESC
""",
        "param_slots": [
            {"name": "district",   "entity_type": "district", "position": 1},
            {"name": "district_2", "entity_type": "district", "position": 2},
        ],
        "result_ttl_seconds": 600,
    },

    "T121": {
        "abstract_question": "Compare pre-auth rejection rates between {district} and {district_2}?",
        "date_filter": None,
        "sql_template": """
SELECT
    c.hospital_district                                                           AS district_name,
    COUNT(pa.preauth_id)                                                          AS total_preauths,
    COUNT(CASE WHEN pa.status = 'REJECTED' THEN 1 END)                           AS rejected_count,
    ROUND(
        COUNT(CASE WHEN pa.status = 'REJECTED' THEN 1 END)
        * 100.0 / NULLIF(COUNT(pa.preauth_id), 0),
        2
    )                                                                             AS rejection_rate_pct
FROM cm_preauth_request pa
JOIN cm_case c ON pa.case_id = c.case_id
WHERE c.hospital_district IN (?, ?)
GROUP BY c.hospital_district
ORDER BY rejection_rate_pct DESC
""",
        "param_slots": [
            {"name": "district",   "entity_type": "district", "position": 1},
            {"name": "district_2", "entity_type": "district", "position": 2},
        ],
        "result_ttl_seconds": 600,
    },

    "T122": {
        "abstract_question": "Compare average claim value between {district} and {district_2}?",
        "date_filter": {"alias": "c", "column": "admission_datetime"},
        "sql_template": """
SELECT
    c.hospital_district                                                           AS district_name,
    COUNT(cl.claim_id)                                                            AS total_claims,
    ROUND(AVG(cl.amount_approved), 2)                                             AS avg_approved_amount,
    ROUND(AVG(cl.amount_claimed),  2)                                             AS avg_claimed_amount
FROM cm_claim cl
JOIN cm_case c ON cl.case_id = c.case_id
WHERE c.hospital_district IN (?, ?)
GROUP BY c.hospital_district
ORDER BY avg_approved_amount DESC
""",
        "param_slots": [
            {"name": "district",   "entity_type": "district", "position": 1},
            {"name": "district_2", "entity_type": "district", "position": 2},
        ],
        "result_ttl_seconds": 600,
    },

    "T123": {
        "abstract_question": "Compare emergency admission ratios between {district} and {district_2}?",
        "date_filter": {"alias": "c", "column": "admission_datetime"},
        "sql_template": """
SELECT
    c.hospital_district                                                           AS district_name,
    COUNT(*)                                                                      AS total_cases,
    COUNT(CASE WHEN c.admission_type = 'EMERGENCY' THEN 1 END)                   AS emergency_cases,
    ROUND(
        COUNT(CASE WHEN c.admission_type = 'EMERGENCY' THEN 1 END)
        * 100.0 / NULLIF(COUNT(*), 0),
        1
    )                                                                             AS emergency_pct
FROM cm_case c
WHERE c.hospital_district IN (?, ?)
GROUP BY c.hospital_district
ORDER BY emergency_pct DESC
""",
        "param_slots": [
            {"name": "district",   "entity_type": "district", "position": 1},
            {"name": "district_2", "entity_type": "district", "position": 2},
        ],
        "result_ttl_seconds": 600,
    },

    "T124": {
        "abstract_question": "Compare rejection rates between {district} and {district_2}?",
        "date_filter": {"alias": "c", "column": "admission_datetime"},
        "sql_template": """
SELECT
    c.hospital_district                                                           AS district_name,
    COUNT(cl.claim_id)                                                            AS total_claims,
    COUNT(CASE WHEN cl.claim_status = 'REJECTED' THEN 1 END)                     AS rejected_claims,
    ROUND(
        COUNT(CASE WHEN cl.claim_status = 'REJECTED' THEN 1 END)
        * 100.0 / NULLIF(COUNT(cl.claim_id), 0),
        2
    )                                                                             AS rejection_rate_pct
FROM cm_claim cl
JOIN cm_case c ON cl.case_id = c.case_id
WHERE c.hospital_district IN (?, ?)
GROUP BY c.hospital_district
ORDER BY rejection_rate_pct DESC
""",
        "param_slots": [
            {"name": "district",   "entity_type": "district", "position": 1},
            {"name": "district_2", "entity_type": "district", "position": 2},
        ],
        "result_ttl_seconds": 600,
    },

    "T125": {
        "abstract_question": "Compare the top procedures between {district} and {district_2}?",
        "date_filter": {"alias": "c", "column": "admission_datetime"},
        "sql_template": """
WITH ranked AS (
    SELECT
        c.hospital_district,
        p.hbp_procedure_code,
        p.procedure_name,
        COUNT(*)                                                                  AS usage_count,
        ROW_NUMBER() OVER (
            PARTITION BY c.hospital_district
            ORDER BY COUNT(*) DESC
        )                                                                         AS rnk
    FROM cm_preauth_procedure_line pl
    JOIN ref_hbp_procedure_master p  ON pl.hbp_procedure_code = p.hbp_procedure_code
    JOIN cm_preauth_request pr       ON pl.preauth_id         = pr.preauth_id
    JOIN cm_case c                   ON pr.case_id            = c.case_id
    WHERE c.hospital_district IN (?, ?)
    GROUP BY c.hospital_district, p.hbp_procedure_code, p.procedure_name
)
SELECT
    hbp_procedure_code,
    procedure_name,
    MAX(CASE WHEN hospital_district = ? THEN usage_count END)                    AS district_1_count,
    MAX(CASE WHEN hospital_district = ? THEN usage_count END)                    AS district_2_count
FROM ranked
WHERE rnk <= 10
GROUP BY hbp_procedure_code, procedure_name
ORDER BY COALESCE(MAX(CASE WHEN hospital_district = ? THEN usage_count END), 0)
       + COALESCE(MAX(CASE WHEN hospital_district = ? THEN usage_count END), 0) DESC
""",
        "param_slots": [
            {"name": "district",   "entity_type": "district", "position": 1},
            {"name": "district_2", "entity_type": "district", "position": 2},
            {"name": "district",   "entity_type": "district", "position": 3},
            {"name": "district_2", "entity_type": "district", "position": 4},
            {"name": "district",   "entity_type": "district", "position": 5},
            {"name": "district_2", "entity_type": "district", "position": 6},
        ],
        "result_ttl_seconds": 600,
    },

    "T126": {
        "abstract_question": "Compare the top diagnoses between {district} and {district_2}?",
        "date_filter": {"alias": "c", "column": "admission_datetime"},
        "sql_template": """
WITH ranked AS (
    SELECT
        c.hospital_district,
        d.diagnosis_text,
        d.icd_code,
        COUNT(*)                                                                  AS case_count,
        ROW_NUMBER() OVER (
            PARTITION BY c.hospital_district
            ORDER BY COUNT(*) DESC
        )                                                                         AS rnk
    FROM cm_case_diagnosis d
    JOIN cm_case c ON d.case_id = c.case_id
    WHERE c.hospital_district IN (?, ?)
      AND d.diagnosis_type = 'PRIMARY'
    GROUP BY c.hospital_district, d.diagnosis_text, d.icd_code
)
SELECT
    icd_code,
    diagnosis_text,
    MAX(CASE WHEN hospital_district = ? THEN case_count END)                     AS district_1_count,
    MAX(CASE WHEN hospital_district = ? THEN case_count END)                     AS district_2_count
FROM ranked
WHERE rnk <= 10
GROUP BY icd_code, diagnosis_text
ORDER BY COALESCE(MAX(CASE WHEN hospital_district = ? THEN case_count END), 0)
       + COALESCE(MAX(CASE WHEN hospital_district = ? THEN case_count END), 0) DESC
""",
        "param_slots": [
            {"name": "district",   "entity_type": "district", "position": 1},
            {"name": "district_2", "entity_type": "district", "position": 2},
            {"name": "district",   "entity_type": "district", "position": 3},
            {"name": "district_2", "entity_type": "district", "position": 4},
            {"name": "district",   "entity_type": "district", "position": 5},
            {"name": "district_2", "entity_type": "district", "position": 6},
        ],
        "result_ttl_seconds": 600,
    },

    "T127": {
        "abstract_question": "Compare portability volumes between {district} and {district_2}?",
        "date_filter": {"alias": "c", "column": "admission_datetime"},
        "sql_template": """
SELECT
    h.home_district_code                                                          AS home_district,
    COUNT(DISTINCT c.case_id)                                                     AS portability_cases,
    ROUND(SUM(cl.amount_approved), 2)                                             AS total_approved
FROM cm_case c
JOIN bm_beneficiary b ON c.beneficiary_id = b.beneficiary_id
JOIN bm_household   h ON b.household_id   = h.household_id
LEFT JOIN cm_claim cl ON c.case_id        = cl.case_id
WHERE c.is_portability = TRUE
  AND h.home_district_code IN (?, ?)
GROUP BY h.home_district_code
ORDER BY portability_cases DESC
""",
        "param_slots": [
            {"name": "district",   "entity_type": "district", "position": 1},
            {"name": "district_2", "entity_type": "district", "position": 2},
        ],
        "result_ttl_seconds": 600,
    },

    # ── L. Division Templates (T128-T140) ─────────────────────────────────────

    "T128": {
        "abstract_question": "What is the enrolment summary for {division}?",
        "date_filter": None,
        "sql_template": """
SELECT
    h.home_division_name                          AS division_name,
    COUNT(DISTINCT h.household_id)                AS households,
    COUNT(DISTINCT b.beneficiary_id)              AS beneficiaries,
    COUNT(DISTINCT CASE WHEN ca.card_status = 'ACTIVE' THEN ca.card_id END) AS active_cards
FROM bm_household h
LEFT JOIN bm_beneficiary b ON h.household_id   = b.household_id
LEFT JOIN bm_card ca       ON b.beneficiary_id = ca.beneficiary_id
WHERE h.home_division_name = ?
GROUP BY h.home_division_name
""",
        "param_slots": [{"name": "division", "entity_type": "division", "position": 1}],
        "result_ttl_seconds": 600,
    },

    "T129": {
        "abstract_question": "What is the claims summary for {division}?",
        "date_filter": {"alias": "c", "column": "admission_datetime"},
        "sql_template": """
SELECT
    c.hospital_division                              AS division_name,
    COUNT(DISTINCT c.case_id)                        AS total_cases,
    COUNT(DISTINCT cl.claim_id)                      AS total_claims,
    ROUND(SUM(cl.amount_claimed),  2)                AS total_claimed,
    ROUND(SUM(cl.amount_approved), 2)                AS total_approved,
    ROUND(AVG(cl.settlement_tat_days), 1)            AS avg_tat_days
FROM cm_case c
LEFT JOIN cm_claim cl ON c.case_id = cl.case_id
WHERE c.hospital_division = ?
GROUP BY c.hospital_division
""",
        "param_slots": [{"name": "division", "entity_type": "division", "position": 1}],
        "result_ttl_seconds": 600,
    },

    "T132": {
        "abstract_question": "What is the settlement TAT in {division}?",
        "date_filter": {"alias": "c", "column": "admission_datetime"},
        "sql_template": """
SELECT
    c.hospital_division                                                           AS division_name,
    ROUND(AVG(cl.settlement_tat_days), 1)                                         AS avg_tat_days,
    ROUND(
        PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY cl.settlement_tat_days),
        1
    )                                                                             AS median_tat_days,
    ROUND(
        PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY cl.settlement_tat_days),
        1
    )                                                                             AS p95_tat_days
FROM cm_claim cl
JOIN cm_case c ON cl.case_id = c.case_id
WHERE c.hospital_division = ?
  AND cl.settlement_tat_days IS NOT NULL
GROUP BY c.hospital_division
""",
        "param_slots": [{"name": "division", "entity_type": "division", "position": 1}],
        "result_ttl_seconds": 600,
    },

    "T133": {
        "abstract_question": "What is the public vs private split in {division}?",
        "date_filter": {"alias": "c", "column": "admission_datetime"},
        "sql_template": """
SELECT
    h.hospital_type,
    COUNT(DISTINCT c.case_id)                                                     AS case_count,
    ROUND(COUNT(DISTINCT c.case_id) * 100.0 / SUM(COUNT(DISTINCT c.case_id)) OVER(), 1) AS pct_cases,
    ROUND(SUM(cl.amount_claimed), 2)                                              AS total_claimed
FROM cm_case c
JOIN  hm_hospital h  ON c.hospital_id = h.hospital_id
LEFT JOIN cm_claim cl ON c.case_id    = cl.case_id
WHERE c.hospital_division = ?
GROUP BY h.hospital_type
ORDER BY case_count DESC
""",
        "param_slots": [{"name": "division", "entity_type": "division", "position": 1}],
        "result_ttl_seconds": 600,
    },

    "T134": {
        "abstract_question": "What is the claim approval rate in {division}?",
        "date_filter": {"alias": "c", "column": "admission_datetime"},
        "sql_template": """
SELECT
    c.hospital_division                                                           AS division_name,
    COUNT(cl.claim_id)                                                            AS total_claims,
    ROUND(
        AVG(cl.amount_approved / NULLIF(cl.amount_claimed, 0) * 100),
        1
    )                                                                             AS avg_approval_rate_pct
FROM cm_claim cl
JOIN cm_case c ON cl.case_id = c.case_id
WHERE c.hospital_division = ?
GROUP BY c.hospital_division
""",
        "param_slots": [{"name": "division", "entity_type": "division", "position": 1}],
        "result_ttl_seconds": 600,
    },

    "T135": {
        "abstract_question": "What is the monthly case trend in {division}?",
        "date_filter": {"alias": "c", "column": "admission_datetime"},
        "sql_template": """
SELECT
    date_trunc('month', c.admission_datetime)::DATE  AS month,
    COUNT(*)                                          AS case_count
FROM cm_case c
WHERE c.hospital_division = ?
GROUP BY 1
ORDER BY 1
""",
        "param_slots": [{"name": "division", "entity_type": "division", "position": 1}],
        "result_ttl_seconds": 600,
    },

    "T136": {
        "abstract_question": "What are the top hospitals in {division} by claim volume?",
        "date_filter": {"alias": "c", "column": "admission_datetime"},
        "sql_template": """
SELECT
    h.hospital_name,
    h.hospital_type,
    h.district_name,
    COUNT(DISTINCT c.case_id)                AS case_count,
    ROUND(SUM(cl.amount_claimed), 2)         AS total_claimed
FROM cm_case c
JOIN  hm_hospital h  ON c.hospital_id = h.hospital_id
LEFT JOIN cm_claim cl ON c.case_id    = cl.case_id
WHERE c.hospital_division = ?
GROUP BY h.hospital_id, h.hospital_name, h.hospital_type, h.district_name
ORDER BY case_count DESC
LIMIT 10
""",
        "param_slots": [{"name": "division", "entity_type": "division", "position": 1}],
        "result_ttl_seconds": 600,
    },

    "T137": {
        "abstract_question": "What are the top procedures in {division}?",
        "date_filter": {"alias": "c", "column": "admission_datetime"},
        "sql_template": """
SELECT
    pl.hbp_procedure_code,
    p.procedure_name,
    p.specialty_name,
    COUNT(*)                                 AS usage_count,
    ROUND(SUM(pl.computed_final_amount), 2)  AS total_amount
FROM cm_preauth_procedure_line pl
JOIN ref_hbp_procedure_master p  ON pl.hbp_procedure_code = p.hbp_procedure_code
JOIN cm_preauth_request pr       ON pl.preauth_id         = pr.preauth_id
JOIN cm_case c                   ON pr.case_id            = c.case_id
WHERE c.hospital_division = ?
GROUP BY pl.hbp_procedure_code, p.procedure_name, p.specialty_name
ORDER BY usage_count DESC
LIMIT 10
""",
        "param_slots": [{"name": "division", "entity_type": "division", "position": 1}],
        "result_ttl_seconds": 600,
    },

    "T138": {
        "abstract_question": "What are the top diagnoses in {division}?",
        "date_filter": {"alias": "c", "column": "admission_datetime"},
        "sql_template": """
SELECT
    d.icd_code,
    d.diagnosis_text,
    COUNT(*) AS case_count
FROM cm_case_diagnosis d
JOIN cm_case c ON d.case_id = c.case_id
WHERE c.hospital_division = ?
  AND d.diagnosis_type = 'PRIMARY'
GROUP BY d.icd_code, d.diagnosis_text
ORDER BY case_count DESC
LIMIT 10
""",
        "param_slots": [{"name": "division", "entity_type": "division", "position": 1}],
        "result_ttl_seconds": 600,
    },

    "T139": {
        "abstract_question": "What is the per-beneficiary spend in {division}?",
        "date_filter": {"alias": "c", "column": "admission_datetime"},
        "sql_template": """
SELECT
    c.hospital_division                                                           AS division_name,
    COUNT(DISTINCT c.beneficiary_id)                                              AS unique_beneficiaries,
    ROUND(SUM(cl.amount_approved), 2)                                             AS total_approved,
    ROUND(
        SUM(cl.amount_approved) / NULLIF(COUNT(DISTINCT c.beneficiary_id), 0),
        2
    )                                                                             AS spend_per_beneficiary
FROM cm_case c
LEFT JOIN cm_claim cl ON c.case_id = cl.case_id
WHERE c.hospital_division = ?
GROUP BY c.hospital_division
""",
        "param_slots": [{"name": "division", "entity_type": "division", "position": 1}],
        "result_ttl_seconds": 600,
    },

    "T140": {
        "abstract_question": "Compare claims between {division} and {division_2}?",
        "date_filter": {"alias": "c", "column": "admission_datetime"},
        "sql_template": """
SELECT
    c.hospital_division                              AS division_name,
    COUNT(DISTINCT c.case_id)                        AS total_cases,
    COUNT(DISTINCT cl.claim_id)                      AS total_claims,
    ROUND(SUM(cl.amount_claimed),  2)                AS total_claimed,
    ROUND(SUM(cl.amount_approved), 2)                AS total_approved,
    COUNT(CASE WHEN cl.claim_status = 'REJECTED' THEN 1 END) AS rejected_claims
FROM cm_case c
LEFT JOIN cm_claim cl ON c.case_id = cl.case_id
WHERE c.hospital_division IN (?, ?)
GROUP BY c.hospital_division
ORDER BY total_cases DESC
""",
        "param_slots": [
            {"name": "division",   "entity_type": "division",   "position": 1},
            {"name": "division_2", "entity_type": "division_2", "position": 2},
        ],
        "result_ttl_seconds": 600,
    },

    # ── M. Hospital-Specific Templates (T142-T153) ────────────────────────────

    "T142": {
        "abstract_question": "What is the add-on procedure rate for {hospital}?",
        "date_filter": {"alias": "c", "column": "admission_datetime"},
        "sql_template": """
SELECT
    h.hospital_name,
    COUNT(pl.preauth_id)                                                          AS total_procedures,
    COUNT(CASE WHEN pl.is_addon = TRUE THEN 1 END)                               AS addon_procedures,
    ROUND(
        COUNT(CASE WHEN pl.is_addon = TRUE THEN 1 END)
        * 100.0 / NULLIF(COUNT(pl.preauth_id), 0),
        1
    )                                                                             AS addon_pct
FROM cm_preauth_procedure_line pl
JOIN cm_preauth_request pr ON pl.preauth_id  = pr.preauth_id
JOIN cm_case c             ON pr.case_id     = c.case_id
JOIN hm_hospital h         ON c.hospital_id  = h.hospital_id
WHERE h.hospital_name = ?
GROUP BY h.hospital_name
""",
        "param_slots": [{"name": "hospital", "entity_type": "hospital", "position": 1}],
        "result_ttl_seconds": 600,
    },

    "T143": {
        "abstract_question": "What is the average length of stay at {hospital} vs state average?",
        "date_filter": {"alias": "c", "column": "admission_datetime"},
        "sql_template": """
WITH hospital_los AS (
    SELECT
        h.hospital_name,
        ROUND(
            AVG(DATE_DIFF('day', c.admission_datetime::DATE, c.discharge_datetime::DATE)),
            1
        ) AS avg_los_days
    FROM cm_case c
    JOIN hm_hospital h ON c.hospital_id = h.hospital_id
    WHERE h.hospital_name = ?
      AND c.discharge_datetime IS NOT NULL
    GROUP BY h.hospital_name
),
state_los AS (
    SELECT
        ROUND(
            AVG(DATE_DIFF('day', c.admission_datetime::DATE, c.discharge_datetime::DATE)),
            1
        ) AS state_avg_los_days
    FROM cm_case c
    WHERE c.discharge_datetime IS NOT NULL
)
SELECT
    hl.hospital_name,
    hl.avg_los_days                                                               AS hospital_avg_los_days,
    sl.state_avg_los_days,
    ROUND(hl.avg_los_days - sl.state_avg_los_days, 1)                            AS diff_from_state_avg
FROM hospital_los hl, state_los sl
""",
        "param_slots": [{"name": "hospital", "entity_type": "hospital", "position": 1}],
        "result_ttl_seconds": 600,
    },

    "T144": {
        "abstract_question": "What is the LAMA/DAMA rate at {hospital}?",
        "date_filter": None,
        "sql_template": """
SELECT
    h.hospital_name,
    COUNT(d.case_id)                                                              AS total_discharges,
    COUNT(CASE WHEN d.lama_date IS NOT NULL THEN 1 END)                          AS lama_count,
    ROUND(
        COUNT(CASE WHEN d.lama_date IS NOT NULL THEN 1 END)
        * 100.0 / NULLIF(COUNT(d.case_id), 0),
        2
    )                                                                             AS lama_rate_pct
FROM cm_discharge d
JOIN cm_case c     ON d.case_id     = c.case_id
JOIN hm_hospital h ON c.hospital_id = h.hospital_id
WHERE h.hospital_name = ?
GROUP BY h.hospital_name
""",
        "param_slots": [{"name": "hospital", "entity_type": "hospital", "position": 1}],
        "result_ttl_seconds": 600,
    },

    "T145": {
        "abstract_question": "What is the mortality rate at {hospital}?",
        "date_filter": None,
        "sql_template": """
SELECT
    h.hospital_name,
    COUNT(d.case_id)                                                              AS total_discharges,
    COUNT(CASE WHEN d.death_date IS NOT NULL THEN 1 END)                         AS death_count,
    ROUND(
        COUNT(CASE WHEN d.death_date IS NOT NULL THEN 1 END)
        * 100.0 / NULLIF(COUNT(d.case_id), 0),
        2
    )                                                                             AS mortality_rate_pct
FROM cm_discharge d
JOIN cm_case c     ON d.case_id     = c.case_id
JOIN hm_hospital h ON c.hospital_id = h.hospital_id
WHERE h.hospital_name = ?
GROUP BY h.hospital_name
""",
        "param_slots": [{"name": "hospital", "entity_type": "hospital", "position": 1}],
        "result_ttl_seconds": 600,
    },

    "T146": {
        "abstract_question": "What is the emergency vs elective ratio at {hospital}?",
        "date_filter": {"alias": "c", "column": "admission_datetime"},
        "sql_template": """
SELECT
    c.admission_type,
    COUNT(*)                                                                      AS case_count,
    ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER(), 1)                            AS pct
FROM cm_case c
JOIN hm_hospital h ON c.hospital_id = h.hospital_id
WHERE h.hospital_name = ?
GROUP BY c.admission_type
ORDER BY case_count DESC
""",
        "param_slots": [{"name": "hospital", "entity_type": "hospital", "position": 1}],
        "result_ttl_seconds": 600,
    },

    "T147": {
        "abstract_question": "What is the average claim value at {hospital} vs state average?",
        "date_filter": {"alias": "c", "column": "admission_datetime"},
        "sql_template": """
WITH hospital_avg AS (
    SELECT
        h.hospital_name,
        ROUND(AVG(cl.amount_approved), 2) AS avg_approved
    FROM cm_claim cl
    JOIN cm_case c     ON cl.case_id    = c.case_id
    JOIN hm_hospital h ON c.hospital_id = h.hospital_id
    WHERE h.hospital_name = ?
    GROUP BY h.hospital_name
),
state_avg AS (
    SELECT ROUND(AVG(cl.amount_approved), 2) AS state_avg_approved
    FROM cm_claim cl
)
SELECT
    ha.hospital_name,
    ha.avg_approved                                                               AS hospital_avg_claim,
    sa.state_avg_approved                                                         AS state_avg_claim,
    ROUND(ha.avg_approved - sa.state_avg_approved, 2)                            AS diff_from_state_avg
FROM hospital_avg ha, state_avg sa
""",
        "param_slots": [{"name": "hospital", "entity_type": "hospital", "position": 1}],
        "result_ttl_seconds": 600,
    },

    "T148": {
        "abstract_question": "How many clinicians are registered at {hospital} vs case volume?",
        "date_filter": None,
        "sql_template": """
SELECT
    h.hospital_name,
    COUNT(DISTINCT s.staff_id)                                                    AS total_clinicians,
    COUNT(DISTINCT c.case_id)                                                     AS total_cases,
    ROUND(
        COUNT(DISTINCT c.case_id) * 1.0 / NULLIF(COUNT(DISTINCT s.staff_id), 0),
        1
    )                                                                             AS cases_per_clinician
FROM hm_hospital h
LEFT JOIN hm_staff s ON h.hospital_id = s.hospital_id
LEFT JOIN cm_case  c ON h.hospital_id = c.hospital_id
WHERE h.hospital_name = ?
GROUP BY h.hospital_name
""",
        "param_slots": [{"name": "hospital", "entity_type": "hospital", "position": 1}],
        "result_ttl_seconds": 600,
    },

    "T149": {
        "abstract_question": "What is the pre-auth rejection rate at {hospital}?",
        "date_filter": None,
        "sql_template": """
SELECT
    h.hospital_name,
    COUNT(pa.preauth_id)                                                          AS total_preauths,
    COUNT(CASE WHEN pa.status = 'REJECTED' THEN 1 END)                           AS rejected_count,
    ROUND(
        COUNT(CASE WHEN pa.status = 'REJECTED' THEN 1 END)
        * 100.0 / NULLIF(COUNT(pa.preauth_id), 0),
        2
    )                                                                             AS rejection_rate_pct
FROM cm_preauth_request pa
JOIN cm_case c     ON pa.case_id    = c.case_id
JOIN hm_hospital h ON c.hospital_id = h.hospital_id
WHERE h.hospital_name = ?
GROUP BY h.hospital_name
""",
        "param_slots": [{"name": "hospital", "entity_type": "hospital", "position": 1}],
        "result_ttl_seconds": 600,
    },

    "T150": {
        "abstract_question": "What are the bank account and payment details for {hospital}?",
        "date_filter": None,
        "sql_template": """
SELECT
    h.hospital_name,
    ba.bank_name,
    ba.ifsc_code,
    ba.account_number_token,
    ba.authorized_signatory_name
FROM hm_hospital h
JOIN hm_hospital_bank_account ba ON h.hospital_id = ba.hospital_id
WHERE h.hospital_name = ?
ORDER BY ba.hospital_bank_id
""",
        "param_slots": [{"name": "hospital", "entity_type": "hospital", "position": 1}],
        "result_ttl_seconds": 900,
    },

    "T151": {
        "abstract_question": "What is the failed payment amount for {hospital}?",
        "date_filter": None,
        "sql_template": """
SELECT
    h.hospital_name,
    COUNT(p.claim_id)                                                             AS failed_payment_count,
    ROUND(SUM(p.amount_paid), 2)                                                  AS total_failed_amount
FROM cm_payment p
JOIN cm_claim cl ON p.claim_id    = cl.claim_id
JOIN cm_case  c  ON cl.case_id    = c.case_id
JOIN hm_hospital h ON c.hospital_id = h.hospital_id
WHERE p.payment_status = 'FAILED'
  AND h.hospital_name = ?
GROUP BY h.hospital_name
""",
        "param_slots": [{"name": "hospital", "entity_type": "hospital", "position": 1}],
        "result_ttl_seconds": 600,
    },

    "T152": {
        "abstract_question": "What is the bed occupancy estimate for {hospital}?",
        "date_filter": None,
        "sql_template": """
WITH recent_cases AS (
    SELECT COUNT(DISTINCT c.case_id) AS case_count_30d
    FROM cm_case c
    JOIN hm_hospital h ON c.hospital_id = h.hospital_id
    WHERE h.hospital_name = ?
      AND c.admission_datetime >= (CURRENT_DATE - INTERVAL '30 days')
)
SELECT
    h.hospital_name,
    h.inpatient_beds,
    rc.case_count_30d                                                             AS admissions_last_30_days,
    ROUND(
        rc.case_count_30d * 100.0 / NULLIF(h.inpatient_beds * 30, 0),
        1
    )                                                                             AS estimated_avg_daily_occupancy_pct
FROM hm_hospital h, recent_cases rc
WHERE h.hospital_name = ?
""",
        "param_slots": [
            {"name": "hospital", "entity_type": "hospital", "position": 1},
            {"name": "hospital", "entity_type": "hospital", "position": 2},
        ],
        "result_ttl_seconds": 600,
    },

    "T153": {
        "abstract_question": "What is the readmission rate at {hospital}?",
        "date_filter": None,
        "sql_template": """
WITH ordered_cases AS (
    SELECT
        c.case_id,
        c.beneficiary_id,
        c.admission_datetime,
        c.discharge_datetime,
        LAG(c.discharge_datetime) OVER (
            PARTITION BY c.beneficiary_id
            ORDER BY c.admission_datetime
        ) AS prev_discharge_datetime
    FROM cm_case c
    JOIN hm_hospital h ON c.hospital_id = h.hospital_id
    WHERE h.hospital_name = ?
)
SELECT
    COUNT(*)                                                                      AS total_cases,
    COUNT(CASE
        WHEN prev_discharge_datetime IS NOT NULL
         AND DATE_DIFF('day', prev_discharge_datetime::DATE, admission_datetime::DATE) <= 30
        THEN 1
    END)                                                                          AS readmission_count,
    ROUND(
        COUNT(CASE
            WHEN prev_discharge_datetime IS NOT NULL
             AND DATE_DIFF('day', prev_discharge_datetime::DATE, admission_datetime::DATE) <= 30
            THEN 1
        END) * 100.0 / NULLIF(COUNT(*), 0),
        1
    )                                                                             AS readmission_rate_pct
FROM ordered_cases
""",
        "param_slots": [{"name": "hospital", "entity_type": "hospital", "position": 1}],
        "result_ttl_seconds": 600,
    },

    # ── N. Specialty Templates (T154-T159) ────────────────────────────────────

    "T154": {
        "abstract_question": "What is the average claim value for {specialty} cases?",
        "date_filter": {"alias": "c", "column": "admission_datetime"},
        "sql_template": """
SELECT
    r.specialty_code,
    r.specialty_name,
    COUNT(DISTINCT cl.claim_id)                                                   AS claim_count,
    ROUND(AVG(cl.amount_approved), 2)                                             AS avg_approved_amount,
    ROUND(AVG(cl.amount_claimed),  2)                                             AS avg_claimed_amount
FROM cm_preauth_procedure_line pl
JOIN ref_hbp_procedure_master r  ON pl.hbp_procedure_code = r.hbp_procedure_code
JOIN cm_preauth_request pr       ON pl.preauth_id         = pr.preauth_id
JOIN cm_case c                   ON pr.case_id            = c.case_id
JOIN cm_claim cl                 ON c.case_id             = cl.case_id
WHERE r.specialty_code = ?
GROUP BY r.specialty_code, r.specialty_name
""",
        "param_slots": [{"name": "specialty", "entity_type": "specialty", "position": 1}],
        "result_ttl_seconds": 600,
    },

    "T155": {
        "abstract_question": "What is the claim approval rate for {specialty} cases?",
        "date_filter": {"alias": "c", "column": "admission_datetime"},
        "sql_template": """
SELECT
    r.specialty_code,
    r.specialty_name,
    COUNT(DISTINCT cl.claim_id)                                                   AS total_claims,
    ROUND(
        AVG(cl.amount_approved / NULLIF(cl.amount_claimed, 0) * 100),
        1
    )                                                                             AS avg_approval_rate_pct
FROM cm_preauth_procedure_line pl
JOIN ref_hbp_procedure_master r  ON pl.hbp_procedure_code = r.hbp_procedure_code
JOIN cm_preauth_request pr       ON pl.preauth_id         = pr.preauth_id
JOIN cm_case c                   ON pr.case_id            = c.case_id
JOIN cm_claim cl                 ON c.case_id             = cl.case_id
WHERE r.specialty_code = ?
GROUP BY r.specialty_code, r.specialty_name
""",
        "param_slots": [{"name": "specialty", "entity_type": "specialty", "position": 1}],
        "result_ttl_seconds": 600,
    },

    "T156": {
        "abstract_question": "What is the average length of stay for {specialty} cases?",
        "date_filter": {"alias": "c", "column": "admission_datetime"},
        "sql_template": """
SELECT
    r.specialty_code,
    r.specialty_name,
    COUNT(DISTINCT c.case_id)                                                     AS case_count,
    ROUND(
        AVG(DATE_DIFF('day', c.admission_datetime::DATE, c.discharge_datetime::DATE)),
        1
    )                                                                             AS avg_los_days
FROM cm_preauth_procedure_line pl
JOIN ref_hbp_procedure_master r  ON pl.hbp_procedure_code = r.hbp_procedure_code
JOIN cm_preauth_request pr       ON pl.preauth_id         = pr.preauth_id
JOIN cm_case c                   ON pr.case_id            = c.case_id
WHERE r.specialty_code = ?
  AND c.discharge_datetime IS NOT NULL
GROUP BY r.specialty_code, r.specialty_name
""",
        "param_slots": [{"name": "specialty", "entity_type": "specialty", "position": 1}],
        "result_ttl_seconds": 600,
    },

    "T157": {
        "abstract_question": "What is the mortality rate for {specialty} cases?",
        "date_filter": None,
        "sql_template": """
SELECT
    r.specialty_code,
    r.specialty_name,
    COUNT(DISTINCT c.case_id)                                                     AS total_cases,
    COUNT(DISTINCT CASE WHEN d.death_date IS NOT NULL THEN d.case_id END)        AS death_count,
    ROUND(
        COUNT(DISTINCT CASE WHEN d.death_date IS NOT NULL THEN d.case_id END)
        * 100.0 / NULLIF(COUNT(DISTINCT c.case_id), 0),
        2
    )                                                                             AS mortality_rate_pct
FROM cm_preauth_procedure_line pl
JOIN ref_hbp_procedure_master r  ON pl.hbp_procedure_code = r.hbp_procedure_code
JOIN cm_preauth_request pr       ON pl.preauth_id         = pr.preauth_id
JOIN cm_case c                   ON pr.case_id            = c.case_id
LEFT JOIN cm_discharge d         ON c.case_id             = d.case_id
WHERE r.specialty_code = ?
GROUP BY r.specialty_code, r.specialty_name
""",
        "param_slots": [{"name": "specialty", "entity_type": "specialty", "position": 1}],
        "result_ttl_seconds": 600,
    },

    "T158": {
        "abstract_question": "What is the settlement TAT for {specialty} cases?",
        "date_filter": {"alias": "c", "column": "admission_datetime"},
        "sql_template": """
SELECT
    r.specialty_code,
    r.specialty_name,
    COUNT(DISTINCT cl.claim_id)                                                   AS claim_count,
    ROUND(AVG(cl.settlement_tat_days), 1)                                         AS avg_tat_days,
    ROUND(
        PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY cl.settlement_tat_days),
        1
    )                                                                             AS median_tat_days
FROM cm_preauth_procedure_line pl
JOIN ref_hbp_procedure_master r  ON pl.hbp_procedure_code = r.hbp_procedure_code
JOIN cm_preauth_request pr       ON pl.preauth_id         = pr.preauth_id
JOIN cm_case c                   ON pr.case_id            = c.case_id
JOIN cm_claim cl                 ON c.case_id             = cl.case_id
WHERE r.specialty_code = ?
  AND cl.settlement_tat_days IS NOT NULL
GROUP BY r.specialty_code, r.specialty_name
""",
        "param_slots": [{"name": "specialty", "entity_type": "specialty", "position": 1}],
        "result_ttl_seconds": 600,
    },

    "T159": {
        "abstract_question": "What is the {specialty} utilization in {block}?",
        "date_filter": {"alias": "c", "column": "admission_datetime"},
        "sql_template": """
SELECT
    r.specialty_code,
    r.specialty_name,
    h.home_block_name                                                             AS block_name,
    COUNT(DISTINCT c.case_id)                                                     AS case_count,
    ROUND(SUM(pl.computed_final_amount), 2)                                       AS total_amount
FROM cm_preauth_procedure_line pl
JOIN ref_hbp_procedure_master r  ON pl.hbp_procedure_code = r.hbp_procedure_code
JOIN cm_preauth_request pr       ON pl.preauth_id         = pr.preauth_id
JOIN cm_case c                   ON pr.case_id            = c.case_id
JOIN bm_beneficiary b            ON c.beneficiary_id      = b.beneficiary_id
JOIN bm_household   h            ON b.household_id        = h.household_id
WHERE r.specialty_code    = ?
  AND h.home_block_name   = ?
GROUP BY r.specialty_code, r.specialty_name, h.home_block_name
""",
        "param_slots": [
            {"name": "specialty", "entity_type": "specialty", "position": 1},
            {"name": "block",     "entity_type": "block",     "position": 2},
        ],
        "result_ttl_seconds": 600,
    },

    # ── O. Diagnosis Category Templates (T160-T161) ───────────────────────────

    "T160": {
        "abstract_question": "What is the trend for {diagnosis_category} in {district}?",
        "date_filter": {"alias": "c", "column": "admission_datetime"},
        "sql_template": """
SELECT
    date_trunc('month', c.admission_datetime)::DATE  AS month,
    COUNT(*)                                          AS case_count
FROM cm_case_diagnosis d
JOIN cm_case c ON d.case_id = c.case_id
WHERE d.diagnosis_category = ?
  AND c.hospital_district  = ?
  AND d.diagnosis_type = 'PRIMARY'
GROUP BY 1
ORDER BY 1
""",
        "param_slots": [
            {"name": "diagnosis_category", "entity_type": "diagnosis_category", "position": 1},
            {"name": "district",           "entity_type": "district",           "position": 2},
        ],
        "result_ttl_seconds": 600,
    },

    "T161": {
        "abstract_question": "What is the trend for {diagnosis_category} in {division}?",
        "date_filter": {"alias": "c", "column": "admission_datetime"},
        "sql_template": """
SELECT
    date_trunc('month', c.admission_datetime)::DATE  AS month,
    COUNT(*)                                          AS case_count
FROM cm_case_diagnosis d
JOIN cm_case c ON d.case_id = c.case_id
WHERE d.diagnosis_category = ?
  AND c.hospital_division  = ?
  AND d.diagnosis_type = 'PRIMARY'
GROUP BY 1
ORDER BY 1
""",
        "param_slots": [
            {"name": "diagnosis_category", "entity_type": "diagnosis_category", "position": 1},
            {"name": "division",           "entity_type": "division",           "position": 2},
        ],
        "result_ttl_seconds": 600,
    },

    # ── P. Time Templates (T162-T167) ────────────────────────────────────────

    "T162": {
        "abstract_question": "What is the enrolment summary for {year}?",
        "date_filter": None,
        "sql_template": """
SELECT
    CAST(EXTRACT(MONTH FROM er.submitted_at::DATE) AS INTEGER)   AS month,
    COUNT(er.enrolment_request_id)                               AS enrolment_count,
    COUNT(CASE WHEN er.status = 'ISA_APPROVED'  THEN 1 END)     AS isa_approved,
    COUNT(CASE WHEN er.status = 'AUTO_APPROVED' THEN 1 END)     AS auto_approved,
    COUNT(CASE WHEN er.status = 'REJECTED'      THEN 1 END)     AS rejected
FROM bm_enrolment_request er
WHERE CAST(EXTRACT(YEAR FROM er.submitted_at::DATE) AS INTEGER) = CAST(? AS INTEGER)
GROUP BY 1
ORDER BY 1
""",
        "param_slots": [{"name": "year", "entity_type": "year", "position": 1}],
        "result_ttl_seconds": 600,
    },

    "T163": {
        "abstract_question": "What is the financial summary for {year}?",
        "date_filter": None,
        "sql_template": """
SELECT
    CAST(EXTRACT(YEAR FROM c.admission_datetime::DATE) AS INTEGER) AS year,
    COUNT(DISTINCT c.case_id)                                      AS total_cases,
    COUNT(DISTINCT cl.claim_id)                                    AS total_claims,
    ROUND(SUM(cl.amount_claimed),  2)                              AS total_claimed,
    ROUND(SUM(cl.amount_approved), 2)                              AS total_approved,
    COUNT(CASE WHEN cl.claim_status = 'REJECTED' THEN 1 END)      AS rejected_claims
FROM cm_case c
LEFT JOIN cm_claim cl ON c.case_id = cl.case_id
WHERE CAST(EXTRACT(YEAR FROM c.admission_datetime::DATE) AS INTEGER) = CAST(? AS INTEGER)
GROUP BY 1
""",
        "param_slots": [{"name": "year", "entity_type": "year", "position": 1}],
        "result_ttl_seconds": 600,
    },

    "T164": {
        "abstract_question": "What was the pre-auth rejection rate in {month} {year}?",
        "date_filter": None,
        "sql_template": """
SELECT
    CAST(EXTRACT(MONTH FROM pa.initiated_at::DATE) AS INTEGER)    AS month,
    CAST(EXTRACT(YEAR  FROM pa.initiated_at::DATE) AS INTEGER)    AS year,
    COUNT(pa.preauth_id)                                           AS total_preauths,
    COUNT(CASE WHEN pa.status = 'REJECTED' THEN 1 END)            AS rejected_count,
    ROUND(
        COUNT(CASE WHEN pa.status = 'REJECTED' THEN 1 END)
        * 100.0 / NULLIF(COUNT(pa.preauth_id), 0),
        2
    )                                                              AS rejection_rate_pct
FROM cm_preauth_request pa
WHERE CAST(EXTRACT(MONTH FROM pa.initiated_at::DATE) AS INTEGER) = CAST(? AS INTEGER)
  AND CAST(EXTRACT(YEAR  FROM pa.initiated_at::DATE) AS INTEGER) = CAST(? AS INTEGER)
GROUP BY 1, 2
""",
        "param_slots": [
            {"name": "month", "entity_type": "month", "position": 1},
            {"name": "year",  "entity_type": "year",  "position": 2},
        ],
        "result_ttl_seconds": 600,
    },

    "T165": {
        "abstract_question": "What was the settlement TAT in {month} {year}?",
        "date_filter": None,
        "sql_template": """
SELECT
    CAST(EXTRACT(MONTH FROM c.admission_datetime::DATE) AS INTEGER)  AS month,
    CAST(EXTRACT(YEAR  FROM c.admission_datetime::DATE) AS INTEGER)  AS year,
    COUNT(cl.claim_id)                                                AS total_claims,
    ROUND(AVG(cl.settlement_tat_days), 1)                             AS avg_tat_days,
    ROUND(
        PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY cl.settlement_tat_days),
        1
    )                                                                 AS median_tat_days
FROM cm_claim cl
JOIN cm_case c ON cl.case_id = c.case_id
WHERE CAST(EXTRACT(MONTH FROM c.admission_datetime::DATE) AS INTEGER) = CAST(? AS INTEGER)
  AND CAST(EXTRACT(YEAR  FROM c.admission_datetime::DATE) AS INTEGER) = CAST(? AS INTEGER)
  AND cl.settlement_tat_days IS NOT NULL
GROUP BY 1, 2
""",
        "param_slots": [
            {"name": "month", "entity_type": "month", "position": 1},
            {"name": "year",  "entity_type": "year",  "position": 2},
        ],
        "result_ttl_seconds": 600,
    },

    "T166": {
        "abstract_question": "What were the top procedures in {year}?",
        "date_filter": None,
        "sql_template": """
SELECT
    pl.hbp_procedure_code,
    p.procedure_name,
    p.specialty_name,
    COUNT(*)                                 AS usage_count,
    ROUND(SUM(pl.computed_final_amount), 2)  AS total_amount
FROM cm_preauth_procedure_line pl
JOIN ref_hbp_procedure_master p  ON pl.hbp_procedure_code = p.hbp_procedure_code
JOIN cm_preauth_request pr       ON pl.preauth_id         = pr.preauth_id
JOIN cm_case c                   ON pr.case_id            = c.case_id
WHERE CAST(EXTRACT(YEAR FROM c.admission_datetime::DATE) AS INTEGER) = CAST(? AS INTEGER)
GROUP BY pl.hbp_procedure_code, p.procedure_name, p.specialty_name
ORDER BY usage_count DESC
LIMIT 10
""",
        "param_slots": [{"name": "year", "entity_type": "year", "position": 1}],
        "result_ttl_seconds": 600,
    },

    "T167": {
        "abstract_question": "What is the quarterly claims trend for {year}?",
        "date_filter": None,
        "sql_template": """
SELECT
    CAST(EXTRACT(YEAR    FROM c.admission_datetime::DATE) AS INTEGER) AS year,
    CAST(EXTRACT(QUARTER FROM c.admission_datetime::DATE) AS INTEGER) AS quarter,
    COUNT(DISTINCT c.case_id)                                         AS total_cases,
    COUNT(DISTINCT cl.claim_id)                                       AS total_claims,
    ROUND(SUM(cl.amount_claimed),  2)                                 AS total_claimed,
    ROUND(SUM(cl.amount_approved), 2)                                 AS total_approved
FROM cm_case c
LEFT JOIN cm_claim cl ON c.case_id = cl.case_id
WHERE CAST(EXTRACT(YEAR FROM c.admission_datetime::DATE) AS INTEGER) = CAST(? AS INTEGER)
GROUP BY 1, 2
ORDER BY 1, 2
""",
        "param_slots": [{"name": "year", "entity_type": "year", "position": 1}],
        "result_ttl_seconds": 600,
    },

    # ── Q. District Expanded Analytics (T168-T226) ────────────────────────────

    "T168": {
        "abstract_question": "What is the active vs inactive vs disabled card rate in {district}?",
        "date_filter": None,
        "sql_template": """
SELECT
    ca.card_status,
    COUNT(*)                                                                     AS card_count,
    ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER(), 1)                           AS pct
FROM bm_card ca
JOIN bm_beneficiary b ON ca.beneficiary_id = b.beneficiary_id
JOIN bm_household   h ON b.household_id    = h.household_id
WHERE h.home_district_code = ?
GROUP BY ca.card_status
ORDER BY card_count DESC
""",
        "param_slots": [{"name": "district", "entity_type": "district", "position": 1}],
        "result_ttl_seconds": 600,
    },

    "T169": {
        "abstract_question": "What is the beneficiary profile completeness rate in {district}?",
        "date_filter": None,
        "sql_template": """
SELECT
    COUNT(*)                                                                         AS total_beneficiaries,
    COUNT(b.yob)                                                                     AS with_yob,
    COUNT(b.mobile)                                                                  AS with_mobile,
    COUNT(b.photo_uri)                                                               AS with_photo,
    ROUND(COUNT(b.yob)       * 100.0 / NULLIF(COUNT(*), 0), 1)                      AS yob_completeness_pct,
    ROUND(COUNT(b.mobile)    * 100.0 / NULLIF(COUNT(*), 0), 1)                      AS mobile_completeness_pct,
    ROUND(COUNT(b.photo_uri) * 100.0 / NULLIF(COUNT(*), 0), 1)                      AS photo_completeness_pct
FROM bm_beneficiary b
JOIN bm_household h ON b.household_id = h.household_id
WHERE h.home_district_code = ?
""",
        "param_slots": [{"name": "district", "entity_type": "district", "position": 1}],
        "result_ttl_seconds": 600,
    },

    "T170": {
        "abstract_question": "What is the beneficiaries per empanelled hospital ratio in {district}?",
        "date_filter": None,
        "sql_template": """
WITH enrolled AS (
    SELECT COUNT(DISTINCT b.beneficiary_id) AS beneficiary_count
    FROM bm_beneficiary b
    JOIN bm_household h ON b.household_id = h.household_id
    WHERE h.home_district_code = ?
),
hospitals AS (
    SELECT COUNT(DISTINCT hospital_id) AS hospital_count
    FROM hm_hospital
    WHERE district_name = ?
)
SELECT
    e.beneficiary_count,
    h.hospital_count,
    ROUND(e.beneficiary_count * 1.0 / NULLIF(h.hospital_count, 0), 1) AS beneficiaries_per_hospital
FROM enrolled e, hospitals h
""",
        "param_slots": [
            {"name": "district", "entity_type": "district", "position": 1},
            {"name": "district", "entity_type": "district", "position": 2},
        ],
        "result_ttl_seconds": 600,
    },

    "T171": {
        "abstract_question": "What is the bed capacity per 1,000 enrolled beneficiaries in {district}?",
        "date_filter": None,
        "sql_template": """
WITH beds AS (
    SELECT SUM(total_bed_strength) AS total_beds
    FROM hm_hospital
    WHERE district_name = ?
),
enrolled AS (
    SELECT COUNT(DISTINCT b.beneficiary_id) AS beneficiary_count
    FROM bm_beneficiary b
    JOIN bm_household h ON b.household_id = h.household_id
    WHERE h.home_district_code = ?
)
SELECT
    b.total_beds,
    e.beneficiary_count,
    ROUND(b.total_beds * 1000.0 / NULLIF(e.beneficiary_count, 0), 2) AS beds_per_1000_enrolled
FROM beds b, enrolled e
""",
        "param_slots": [
            {"name": "district", "entity_type": "district", "position": 1},
            {"name": "district", "entity_type": "district", "position": 2},
        ],
        "result_ttl_seconds": 600,
    },

    "T172": {
        "abstract_question": "What is the case rate per 1,000 enrolled beneficiaries in {district}?",
        "date_filter": {"alias": "c", "column": "admission_datetime"},
        "sql_template": """
WITH cases AS (
    SELECT COUNT(DISTINCT c.case_id) AS case_count
    FROM cm_case c
    WHERE c.hospital_district = ?
),
enrolled AS (
    SELECT COUNT(DISTINCT b.beneficiary_id) AS beneficiary_count
    FROM bm_beneficiary b
    JOIN bm_household h ON b.household_id = h.household_id
    WHERE h.home_district_code = ?
)
SELECT
    ca.case_count,
    e.beneficiary_count,
    ROUND(ca.case_count * 1000.0 / NULLIF(e.beneficiary_count, 0), 1) AS cases_per_1000_enrolled
FROM cases ca, enrolled e
""",
        "param_slots": [
            {"name": "district", "entity_type": "district", "position": 1},
            {"name": "district", "entity_type": "district", "position": 2},
        ],
        "result_ttl_seconds": 600,
    },

    "T173": {
        "abstract_question": "What share of beneficiaries in {district} received cards within 30 days of enrolment?",
        "date_filter": None,
        "sql_template": """
SELECT
    COUNT(DISTINCT er.enrolment_request_id)                                          AS total_enrolments,
    COUNT(DISTINCT CASE
        WHEN DATE_DIFF('day', er.submitted_at::DATE, ca.issued_at::DATE) <= 30
        THEN er.enrolment_request_id
    END)                                                                             AS within_30_days,
    ROUND(
        COUNT(DISTINCT CASE
            WHEN DATE_DIFF('day', er.submitted_at::DATE, ca.issued_at::DATE) <= 30
            THEN er.enrolment_request_id
        END) * 100.0 / NULLIF(COUNT(DISTINCT er.enrolment_request_id), 0),
        1
    )                                                                                AS within_30_days_pct
FROM bm_enrolment_request er
JOIN bm_beneficiary b  ON er.beneficiary_id = b.beneficiary_id
JOIN bm_household   h  ON b.household_id    = h.household_id
JOIN bm_card        ca ON er.beneficiary_id = ca.beneficiary_id
WHERE h.home_district_code = ?
  AND ca.issued_at IS NOT NULL
""",
        "param_slots": [{"name": "district", "entity_type": "district", "position": 1}],
        "result_ttl_seconds": 600,
    },

    "T174": {
        "abstract_question": "What share of claimants in {district} were admitted within 30 days of enrolment?",
        "date_filter": None,
        "sql_template": """
WITH first_enrolment AS (
    SELECT
        er.beneficiary_id,
        MIN(er.submitted_at) AS first_submitted_at
    FROM bm_enrolment_request er
    JOIN bm_beneficiary b ON er.beneficiary_id = b.beneficiary_id
    JOIN bm_household   h ON b.household_id    = h.household_id
    WHERE h.home_district_code = ?
    GROUP BY er.beneficiary_id
),
first_admission AS (
    SELECT
        c.beneficiary_id,
        MIN(c.admission_datetime) AS first_admission_at
    FROM cm_case c
    GROUP BY c.beneficiary_id
)
SELECT
    COUNT(DISTINCT fe.beneficiary_id)                                               AS total_claimants,
    COUNT(DISTINCT CASE
        WHEN DATE_DIFF('day', fe.first_submitted_at::DATE, fa.first_admission_at::DATE) <= 30
        THEN fe.beneficiary_id
    END)                                                                             AS within_30_days,
    ROUND(
        COUNT(DISTINCT CASE
            WHEN DATE_DIFF('day', fe.first_submitted_at::DATE, fa.first_admission_at::DATE) <= 30
            THEN fe.beneficiary_id
        END) * 100.0 / NULLIF(COUNT(DISTINCT fe.beneficiary_id), 0),
        1
    )                                                                                AS within_30_days_pct
FROM first_enrolment fe
JOIN first_admission fa ON fe.beneficiary_id = fa.beneficiary_id
""",
        "param_slots": [{"name": "district", "entity_type": "district", "position": 1}],
        "result_ttl_seconds": 600,
    },

    "T175": {
        "abstract_question": "What share of cases from {district} were treated outside the district?",
        "date_filter": {"alias": "c", "column": "admission_datetime"},
        "sql_template": """
SELECT
    COUNT(DISTINCT c.case_id)                                                        AS total_cases,
    COUNT(DISTINCT CASE WHEN c.hospital_district != h.home_district_code THEN c.case_id END) AS out_of_district,
    ROUND(
        COUNT(DISTINCT CASE WHEN c.hospital_district != h.home_district_code THEN c.case_id END)
        * 100.0 / NULLIF(COUNT(DISTINCT c.case_id), 0),
        1
    )                                                                                AS out_of_district_pct
FROM cm_case c
JOIN bm_beneficiary b ON c.beneficiary_id = b.beneficiary_id
JOIN bm_household   h ON b.household_id   = h.household_id
WHERE h.home_district_code = ?
""",
        "param_slots": [{"name": "district", "entity_type": "district", "position": 1}],
        "result_ttl_seconds": 600,
    },

    "T176": {
        "abstract_question": "Which districts send the most patients into {district} for treatment?",
        "date_filter": {"alias": "c", "column": "admission_datetime"},
        "sql_template": """
SELECT
    h.home_district_code                                                            AS source_district,
    COUNT(DISTINCT c.case_id)                                                       AS case_count,
    ROUND(COUNT(DISTINCT c.case_id) * 100.0 / SUM(COUNT(DISTINCT c.case_id)) OVER(), 1) AS pct
FROM cm_case c
JOIN bm_beneficiary b ON c.beneficiary_id = b.beneficiary_id
JOIN bm_household   h ON b.household_id   = h.household_id
WHERE c.hospital_district = ?
  AND h.home_district_code != ?
GROUP BY h.home_district_code
ORDER BY case_count DESC
LIMIT 10
""",
        "param_slots": [
            {"name": "district", "entity_type": "district", "position": 1},
            {"name": "district", "entity_type": "district", "position": 2},
        ],
        "result_ttl_seconds": 600,
    },

    "T177": {
        "abstract_question": "Which hospitals in {district} have the highest share of district claims?",
        "date_filter": {"alias": "c", "column": "admission_datetime"},
        "sql_template": """
SELECT
    h.hospital_id,
    h.hospital_name,
    h.hospital_type,
    COUNT(DISTINCT c.case_id)                                                        AS case_count,
    ROUND(COUNT(DISTINCT c.case_id) * 100.0 / SUM(COUNT(DISTINCT c.case_id)) OVER(), 1) AS district_share_pct
FROM cm_case c
JOIN hm_hospital h ON c.hospital_id = h.hospital_id
WHERE c.hospital_district = ?
GROUP BY h.hospital_id, h.hospital_name, h.hospital_type
ORDER BY case_count DESC
LIMIT 10
""",
        "param_slots": [{"name": "district", "entity_type": "district", "position": 1}],
        "result_ttl_seconds": 600,
    },

    "T178": {
        "abstract_question": "What share of {district} total spend goes to its top 5 hospitals?",
        "date_filter": {"alias": "c", "column": "admission_datetime"},
        "sql_template": """
WITH hospital_spend AS (
    SELECT
        h.hospital_id,
        h.hospital_name,
        ROUND(SUM(cl.amount_approved), 2) AS hospital_spend
    FROM cm_case c
    JOIN hm_hospital h ON c.hospital_id = h.hospital_id
    LEFT JOIN cm_claim cl ON c.case_id = cl.case_id
    WHERE c.hospital_district = ?
    GROUP BY h.hospital_id, h.hospital_name
),
total AS (
    SELECT SUM(hospital_spend) AS total_spend FROM hospital_spend
),
ranked AS (
    SELECT
        hospital_id,
        hospital_name,
        hospital_spend,
        ROW_NUMBER() OVER (ORDER BY hospital_spend DESC) AS rnk
    FROM hospital_spend
)
SELECT
    r.hospital_name,
    r.hospital_spend,
    ROUND(r.hospital_spend * 100.0 / NULLIF(t.total_spend, 0), 1) AS share_pct,
    t.total_spend
FROM ranked r, total t
WHERE r.rnk <= 5
ORDER BY r.rnk
""",
        "param_slots": [{"name": "district", "entity_type": "district", "position": 1}],
        "result_ttl_seconds": 600,
    },

    "T179": {
        "abstract_question": "Which blocks in {district} have no empanelled hospital?",
        "date_filter": None,
        "sql_template": """
SELECT
    g.block_name
FROM ref_up_geography g
WHERE g.district_name = ?
  AND NOT EXISTS (
      SELECT 1 FROM hm_hospital h
      WHERE h.block_name = g.block_name
        AND h.district_name = g.district_name
  )
GROUP BY g.block_name
ORDER BY g.block_name
""",
        "param_slots": [{"name": "district", "entity_type": "district", "position": 1}],
        "result_ttl_seconds": 900,
    },

    "T180": {
        "abstract_question": "Which blocks in {district} have the lowest utilization rate per 1,000 enrolled beneficiaries?",
        "date_filter": {"alias": "c", "column": "admission_datetime"},
        "sql_template": """
WITH enrolled AS (
    SELECT
        h.home_block_name                        AS block_name,
        COUNT(DISTINCT b.beneficiary_id)         AS beneficiary_count
    FROM bm_household h
    LEFT JOIN bm_beneficiary b ON h.household_id = b.household_id
    WHERE h.home_district_code = ?
    GROUP BY h.home_block_name
),
cases AS (
    SELECT
        hh.home_block_name                       AS block_name,
        COUNT(DISTINCT c.case_id)                AS case_count
    FROM cm_case c
    JOIN bm_beneficiary b  ON c.beneficiary_id = b.beneficiary_id
    JOIN bm_household   hh ON b.household_id   = hh.household_id
    WHERE hh.home_district_code = ?
    GROUP BY hh.home_block_name
)
SELECT
    e.block_name,
    e.beneficiary_count,
    COALESCE(ca.case_count, 0)                                                       AS case_count,
    ROUND(COALESCE(ca.case_count, 0) * 1000.0 / NULLIF(e.beneficiary_count, 0), 1) AS cases_per_1000
FROM enrolled e
LEFT JOIN cases ca ON e.block_name = ca.block_name
ORDER BY cases_per_1000 ASC
LIMIT 15
""",
        "param_slots": [
            {"name": "district", "entity_type": "district", "position": 1},
            {"name": "district", "entity_type": "district", "position": 2},
        ],
        "result_ttl_seconds": 600,
    },

    "T181": {
        "abstract_question": "Which blocks in {district} have the highest utilization rate per 1,000 enrolled beneficiaries?",
        "date_filter": {"alias": "c", "column": "admission_datetime"},
        "sql_template": """
WITH enrolled AS (
    SELECT
        h.home_block_name                        AS block_name,
        COUNT(DISTINCT b.beneficiary_id)         AS beneficiary_count
    FROM bm_household h
    LEFT JOIN bm_beneficiary b ON h.household_id = b.household_id
    WHERE h.home_district_code = ?
    GROUP BY h.home_block_name
),
cases AS (
    SELECT
        hh.home_block_name                       AS block_name,
        COUNT(DISTINCT c.case_id)                AS case_count
    FROM cm_case c
    JOIN bm_beneficiary b  ON c.beneficiary_id = b.beneficiary_id
    JOIN bm_household   hh ON b.household_id   = hh.household_id
    WHERE hh.home_district_code = ?
    GROUP BY hh.home_block_name
)
SELECT
    e.block_name,
    e.beneficiary_count,
    COALESCE(ca.case_count, 0)                                                       AS case_count,
    ROUND(COALESCE(ca.case_count, 0) * 1000.0 / NULLIF(e.beneficiary_count, 0), 1) AS cases_per_1000
FROM enrolled e
LEFT JOIN cases ca ON e.block_name = ca.block_name
ORDER BY cases_per_1000 DESC
LIMIT 15
""",
        "param_slots": [
            {"name": "district", "entity_type": "district", "position": 1},
            {"name": "district", "entity_type": "district", "position": 2},
        ],
        "result_ttl_seconds": 600,
    },

    "T182": {
        "abstract_question": "Which blocks in {district} have high enrolment but near-zero admissions?",
        "date_filter": None,
        "sql_template": """
WITH enrolled AS (
    SELECT
        h.home_block_name                        AS block_name,
        COUNT(DISTINCT b.beneficiary_id)         AS beneficiary_count
    FROM bm_household h
    LEFT JOIN bm_beneficiary b ON h.household_id = b.household_id
    WHERE h.home_district_code = ?
    GROUP BY h.home_block_name
),
cases AS (
    SELECT
        hh.home_block_name                       AS block_name,
        COUNT(DISTINCT c.case_id)                AS case_count
    FROM cm_case c
    JOIN bm_beneficiary b  ON c.beneficiary_id = b.beneficiary_id
    JOIN bm_household   hh ON b.household_id   = hh.household_id
    WHERE hh.home_district_code = ?
    GROUP BY hh.home_block_name
)
SELECT
    e.block_name,
    e.beneficiary_count,
    COALESCE(ca.case_count, 0) AS case_count
FROM enrolled e
LEFT JOIN cases ca ON e.block_name = ca.block_name
WHERE COALESCE(ca.case_count, 0) < 5
  AND e.beneficiary_count > 500
ORDER BY e.beneficiary_count DESC
""",
        "param_slots": [
            {"name": "district", "entity_type": "district", "position": 1},
            {"name": "district", "entity_type": "district", "position": 2},
        ],
        "result_ttl_seconds": 600,
    },

    "T183": {
        "abstract_question": "What is the maternal/neonatal case rate per 1,000 enrolled women in {district}?",
        "date_filter": {"alias": "c", "column": "admission_datetime"},
        "sql_template": """
WITH mat_cases AS (
    SELECT COUNT(DISTINCT c.case_id) AS case_count
    FROM cm_case_diagnosis d
    JOIN cm_case c ON d.case_id = c.case_id
    WHERE c.hospital_district = ?
      AND d.diagnosis_category = 'MATERNAL_NEONATAL'
      AND d.diagnosis_type = 'PRIMARY'
),
enrolled_women AS (
    SELECT COUNT(DISTINCT b.beneficiary_id) AS women_count
    FROM bm_beneficiary b
    JOIN bm_household h ON b.household_id = h.household_id
    WHERE h.home_district_code = ?
      AND b.gender = 'FEMALE'
)
SELECT
    mc.case_count                                                                    AS maternal_neonatal_cases,
    ew.women_count                                                                   AS enrolled_women,
    ROUND(mc.case_count * 1000.0 / NULLIF(ew.women_count, 0), 1)                    AS cases_per_1000_women
FROM mat_cases mc, enrolled_women ew
""",
        "param_slots": [
            {"name": "district", "entity_type": "district", "position": 1},
            {"name": "district", "entity_type": "district", "position": 2},
        ],
        "result_ttl_seconds": 600,
    },

    "T184": {
        "abstract_question": "What is the NCD case rate per 1,000 enrolled beneficiaries in {district}?",
        "date_filter": {"alias": "c", "column": "admission_datetime"},
        "sql_template": """
WITH ncd_cases AS (
    SELECT COUNT(DISTINCT c.case_id) AS case_count
    FROM cm_case_diagnosis d
    JOIN cm_case c ON d.case_id = c.case_id
    WHERE c.hospital_district = ?
      AND d.diagnosis_category = 'NCD'
      AND d.diagnosis_type = 'PRIMARY'
),
enrolled AS (
    SELECT COUNT(DISTINCT b.beneficiary_id) AS beneficiary_count
    FROM bm_beneficiary b
    JOIN bm_household h ON b.household_id = h.household_id
    WHERE h.home_district_code = ?
)
SELECT
    nc.case_count                                                                    AS ncd_cases,
    e.beneficiary_count,
    ROUND(nc.case_count * 1000.0 / NULLIF(e.beneficiary_count, 0), 1)               AS ncd_cases_per_1000
FROM ncd_cases nc, enrolled e
""",
        "param_slots": [
            {"name": "district", "entity_type": "district", "position": 1},
            {"name": "district", "entity_type": "district", "position": 2},
        ],
        "result_ttl_seconds": 600,
    },

    "T185": {
        "abstract_question": "What is the communicable disease case rate per 1,000 enrolled beneficiaries in {district}?",
        "date_filter": {"alias": "c", "column": "admission_datetime"},
        "sql_template": """
WITH comm_cases AS (
    SELECT COUNT(DISTINCT c.case_id) AS case_count
    FROM cm_case_diagnosis d
    JOIN cm_case c ON d.case_id = c.case_id
    WHERE c.hospital_district = ?
      AND d.diagnosis_category = 'COMMUNICABLE'
      AND d.diagnosis_type = 'PRIMARY'
),
enrolled AS (
    SELECT COUNT(DISTINCT b.beneficiary_id) AS beneficiary_count
    FROM bm_beneficiary b
    JOIN bm_household h ON b.household_id = h.household_id
    WHERE h.home_district_code = ?
)
SELECT
    cc.case_count                                                                    AS communicable_cases,
    e.beneficiary_count,
    ROUND(cc.case_count * 1000.0 / NULLIF(e.beneficiary_count, 0), 1)               AS comm_cases_per_1000
FROM comm_cases cc, enrolled e
""",
        "param_slots": [
            {"name": "district", "entity_type": "district", "position": 1},
            {"name": "district", "entity_type": "district", "position": 2},
        ],
        "result_ttl_seconds": 600,
    },

    "T186": {
        "abstract_question": "What is the district-to-district patient inflow and outflow pattern for {district}?",
        "date_filter": {"alias": "c", "column": "admission_datetime"},
        "sql_template": """
WITH inflows AS (
    SELECT
        h.home_district_code                     AS source_district,
        COUNT(DISTINCT c.case_id)                AS inflow_cases
    FROM cm_case c
    JOIN bm_beneficiary b ON c.beneficiary_id = b.beneficiary_id
    JOIN bm_household   h ON b.household_id   = h.household_id
    WHERE c.hospital_district = ?
      AND h.home_district_code != ?
    GROUP BY h.home_district_code
),
outflows AS (
    SELECT
        c.hospital_district                      AS destination_district,
        COUNT(DISTINCT c.case_id)                AS outflow_cases
    FROM cm_case c
    JOIN bm_beneficiary b ON c.beneficiary_id = b.beneficiary_id
    JOIN bm_household   h ON b.household_id   = h.household_id
    WHERE h.home_district_code = ?
      AND c.hospital_district != ?
    GROUP BY c.hospital_district
)
SELECT 'INFLOW'  AS flow_type, source_district      AS other_district, inflow_cases  AS case_count FROM inflows
UNION ALL
SELECT 'OUTFLOW' AS flow_type, destination_district AS other_district, outflow_cases AS case_count FROM outflows
ORDER BY flow_type, case_count DESC
""",
        "param_slots": [
            {"name": "district", "entity_type": "district", "position": 1},
            {"name": "district", "entity_type": "district", "position": 2},
            {"name": "district", "entity_type": "district", "position": 3},
            {"name": "district", "entity_type": "district", "position": 4},
        ],
        "result_ttl_seconds": 600,
    },

    "T187": {
        "abstract_question": "What are the top destination states for portability cases originating from {district}?",
        "date_filter": {"alias": "c", "column": "admission_datetime"},
        "sql_template": """
SELECT
    c.hospital_state_code                                                            AS destination_state,
    COUNT(DISTINCT c.case_id)                                                        AS portability_cases,
    ROUND(COUNT(DISTINCT c.case_id) * 100.0 / SUM(COUNT(DISTINCT c.case_id)) OVER(), 1) AS pct
FROM cm_case c
JOIN bm_beneficiary b ON c.beneficiary_id = b.beneficiary_id
JOIN bm_household   h ON b.household_id   = h.household_id
WHERE c.is_portability = TRUE
  AND h.home_district_code = ?
GROUP BY c.hospital_state_code
ORDER BY portability_cases DESC
LIMIT 10
""",
        "param_slots": [{"name": "district", "entity_type": "district", "position": 1}],
        "result_ttl_seconds": 600,
    },

    "T190": {
        "abstract_question": "Which hospitals in {district} have expired licenses but recent case activity?",
        "date_filter": None,
        "sql_template": """
SELECT
    h.hospital_name,
    h.hospital_type,
    l.expiry_date,
    COUNT(DISTINCT c.case_id) AS recent_cases
FROM hm_license_certificate l
JOIN hm_hospital h ON l.hospital_id = h.hospital_id
LEFT JOIN cm_case c ON h.hospital_id = c.hospital_id
    AND c.admission_datetime >= (CURRENT_DATE - INTERVAL '365 days')
WHERE h.district_name = ?
  AND l.expiry_date < CURRENT_DATE
GROUP BY h.hospital_id, h.hospital_name, h.hospital_type, l.expiry_date
HAVING COUNT(DISTINCT c.case_id) > 0
ORDER BY recent_cases DESC
LIMIT 10
""",
        "param_slots": [{"name": "district", "entity_type": "district", "position": 1}],
        "result_ttl_seconds": 600,
    },

    "T191": {
        "abstract_question": "Which hospitals in {district} have the highest diagnosis-package mismatch rate?",
        "date_filter": None,
        "sql_template": """
SELECT
    h.hospital_name,
    h.hospital_type,
    COUNT(DISTINCT cl.claim_id)                                                      AS total_claims,
    COUNT(DISTINCT CASE WHEN ae.reason_category ILIKE '%mismatch%' THEN ae.claim_id END) AS mismatch_claims,
    ROUND(
        COUNT(DISTINCT CASE WHEN ae.reason_category ILIKE '%mismatch%' THEN ae.claim_id END)
        * 100.0 / NULLIF(COUNT(DISTINCT cl.claim_id), 0),
        1
    )                                                                                AS mismatch_rate_pct
FROM cm_claim cl
LEFT JOIN cm_adjudication_event ae ON cl.claim_id = ae.claim_id
JOIN cm_case c     ON cl.case_id    = c.case_id
JOIN hm_hospital h ON c.hospital_id = h.hospital_id
WHERE c.hospital_district = ?
GROUP BY h.hospital_id, h.hospital_name, h.hospital_type
ORDER BY mismatch_rate_pct DESC
LIMIT 10
""",
        "param_slots": [{"name": "district", "entity_type": "district", "position": 1}],
        "result_ttl_seconds": 600,
    },

    "T192": {
        "abstract_question": "Which hospitals in {district} have the highest missing-document query rate?",
        "date_filter": None,
        "sql_template": """
SELECT
    h.hospital_name,
    h.hospital_type,
    COUNT(DISTINCT cl.claim_id)                                                      AS total_claims,
    COUNT(DISTINCT CASE WHEN cl.claim_status = 'QUERY_RAISED' THEN cl.claim_id END) AS query_raised_claims,
    ROUND(
        COUNT(DISTINCT CASE WHEN cl.claim_status = 'QUERY_RAISED' THEN cl.claim_id END)
        * 100.0 / NULLIF(COUNT(DISTINCT cl.claim_id), 0),
        1
    )                                                                                AS query_rate_pct
FROM cm_claim cl
JOIN cm_case c     ON cl.case_id    = c.case_id
JOIN hm_hospital h ON c.hospital_id = h.hospital_id
WHERE c.hospital_district = ?
GROUP BY h.hospital_id, h.hospital_name, h.hospital_type
ORDER BY query_rate_pct DESC
LIMIT 10
""",
        "param_slots": [{"name": "district", "entity_type": "district", "position": 1}],
        "result_ttl_seconds": 600,
    },

    "T193": {
        "abstract_question": "Which hospitals in {district} have the highest failed-payment amount?",
        "date_filter": None,
        "sql_template": """
SELECT
    h.hospital_name,
    h.hospital_type,
    COUNT(DISTINCT p.claim_id)                                                       AS failed_payment_count,
    ROUND(SUM(p.amount_paid), 2)                                                     AS total_failed_amount
FROM cm_payment p
JOIN cm_claim cl   ON p.claim_id    = cl.claim_id
JOIN cm_case c     ON cl.case_id    = c.case_id
JOIN hm_hospital h ON c.hospital_id = h.hospital_id
WHERE p.payment_status = 'FAILED'
  AND c.hospital_district = ?
GROUP BY h.hospital_id, h.hospital_name, h.hospital_type
ORDER BY total_failed_amount DESC
LIMIT 10
""",
        "param_slots": [{"name": "district", "entity_type": "district", "position": 1}],
        "result_ttl_seconds": 600,
    },

    "T195": {
        "abstract_question": "Which hospitals in {district} have the highest readmission rate within 30 days?",
        "date_filter": None,
        "sql_template": """
WITH ordered_cases AS (
    SELECT
        c.case_id,
        c.beneficiary_id,
        c.hospital_id,
        c.admission_datetime,
        LAG(c.discharge_datetime) OVER (
            PARTITION BY c.beneficiary_id
            ORDER BY c.admission_datetime
        ) AS prev_discharge_datetime
    FROM cm_case c
    WHERE c.hospital_district = ?
)
SELECT
    h.hospital_name,
    h.hospital_type,
    COUNT(*)                                                                         AS total_cases,
    COUNT(CASE
        WHEN prev_discharge_datetime IS NOT NULL
         AND DATE_DIFF('day', prev_discharge_datetime::DATE, admission_datetime::DATE) <= 30
        THEN 1
    END)                                                                             AS readmission_count,
    ROUND(
        COUNT(CASE
            WHEN prev_discharge_datetime IS NOT NULL
             AND DATE_DIFF('day', prev_discharge_datetime::DATE, admission_datetime::DATE) <= 30
            THEN 1
        END) * 100.0 / NULLIF(COUNT(*), 0),
        1
    )                                                                                AS readmission_rate_pct
FROM ordered_cases oc
JOIN hm_hospital h ON oc.hospital_id = h.hospital_id
GROUP BY h.hospital_id, h.hospital_name, h.hospital_type
ORDER BY readmission_rate_pct DESC
LIMIT 10
""",
        "param_slots": [{"name": "district", "entity_type": "district", "position": 1}],
        "result_ttl_seconds": 600,
    },

    "T196": {
        "abstract_question": "Which procedures in {district} have the largest gap between amount claimed and amount approved?",
        "date_filter": {"alias": "c", "column": "admission_datetime"},
        "sql_template": """
SELECT
    p.hbp_procedure_code,
    p.procedure_name,
    p.specialty_name,
    COUNT(DISTINCT c.case_id)                                                        AS case_count,
    ROUND(SUM(cl.amount_claimed),  2)                                                AS total_claimed,
    ROUND(SUM(cl.amount_approved), 2)                                                AS total_approved,
    ROUND(SUM(cl.amount_claimed) - SUM(cl.amount_approved), 2)                      AS total_gap
FROM cm_preauth_procedure_line pl
JOIN ref_hbp_procedure_master p  ON pl.hbp_procedure_code = p.hbp_procedure_code
JOIN cm_preauth_request pr       ON pl.preauth_id         = pr.preauth_id
JOIN cm_case c                   ON pr.case_id            = c.case_id
JOIN cm_claim cl                 ON c.case_id             = cl.case_id
WHERE c.hospital_district = ?
GROUP BY p.hbp_procedure_code, p.procedure_name, p.specialty_name
ORDER BY total_gap DESC
LIMIT 10
""",
        "param_slots": [{"name": "district", "entity_type": "district", "position": 1}],
        "result_ttl_seconds": 600,
    },

    "T197": {
        "abstract_question": "Which procedures in {district} have the highest query and rejection rates?",
        "date_filter": {"alias": "c", "column": "admission_datetime"},
        "sql_template": """
SELECT
    p.hbp_procedure_code,
    p.procedure_name,
    COUNT(DISTINCT cl.claim_id)                                                      AS total_claims,
    ROUND(
        COUNT(DISTINCT CASE WHEN cl.claim_status = 'QUERY_RAISED' THEN cl.claim_id END)
        * 100.0 / NULLIF(COUNT(DISTINCT cl.claim_id), 0),
        1
    )                                                                                AS query_rate_pct,
    ROUND(
        COUNT(DISTINCT CASE WHEN cl.claim_status = 'REJECTED' THEN cl.claim_id END)
        * 100.0 / NULLIF(COUNT(DISTINCT cl.claim_id), 0),
        1
    )                                                                                AS rejection_rate_pct
FROM cm_preauth_procedure_line pl
JOIN ref_hbp_procedure_master p  ON pl.hbp_procedure_code = p.hbp_procedure_code
JOIN cm_preauth_request pr       ON pl.preauth_id         = pr.preauth_id
JOIN cm_case c                   ON pr.case_id            = c.case_id
JOIN cm_claim cl                 ON c.case_id             = cl.case_id
WHERE c.hospital_district = ?
GROUP BY p.hbp_procedure_code, p.procedure_name
ORDER BY (query_rate_pct + rejection_rate_pct) DESC
LIMIT 15
""",
        "param_slots": [{"name": "district", "entity_type": "district", "position": 1}],
        "result_ttl_seconds": 600,
    },

    "T198": {
        "abstract_question": "What is the biometric authentication rate at discharge in {district} by hospital?",
        "date_filter": None,
        "sql_template": """
SELECT
    h.hospital_name,
    h.hospital_type,
    COUNT(d.case_id)                                                                 AS total_discharges,
    COUNT(CASE WHEN d.biometric_auth_used = TRUE THEN 1 END)                        AS biometric_count,
    ROUND(
        COUNT(CASE WHEN d.biometric_auth_used = TRUE THEN 1 END)
        * 100.0 / NULLIF(COUNT(d.case_id), 0),
        1
    )                                                                                AS biometric_rate_pct
FROM cm_discharge d
JOIN cm_case c     ON d.case_id     = c.case_id
JOIN hm_hospital h ON c.hospital_id = h.hospital_id
WHERE c.hospital_district = ?
GROUP BY h.hospital_id, h.hospital_name, h.hospital_type
ORDER BY biometric_rate_pct DESC
""",
        "param_slots": [{"name": "district", "entity_type": "district", "position": 1}],
        "result_ttl_seconds": 600,
    },

    "T199": {
        "abstract_question": "What is the medicine provision rate at discharge in {district} by hospital?",
        "date_filter": None,
        "sql_template": """
SELECT
    h.hospital_name,
    h.hospital_type,
    COUNT(d.case_id)                                                                 AS total_discharges,
    COUNT(CASE WHEN d.provided_medicines_flag = TRUE THEN 1 END)                    AS medicines_count,
    ROUND(
        COUNT(CASE WHEN d.provided_medicines_flag = TRUE THEN 1 END)
        * 100.0 / NULLIF(COUNT(d.case_id), 0),
        1
    )                                                                                AS medicine_rate_pct
FROM cm_discharge d
JOIN cm_case c     ON d.case_id     = c.case_id
JOIN hm_hospital h ON c.hospital_id = h.hospital_id
WHERE c.hospital_district = ?
GROUP BY h.hospital_id, h.hospital_name, h.hospital_type
ORDER BY medicine_rate_pct DESC
""",
        "param_slots": [{"name": "district", "entity_type": "district", "position": 1}],
        "result_ttl_seconds": 600,
    },

    "T200": {
        "abstract_question": "What is the average lag from discharge to claim submission in {district}?",
        "date_filter": None,
        "sql_template": """
SELECT
    c.hospital_district                                                              AS district_name,
    COUNT(DISTINCT cl.claim_id)                                                      AS total_claims,
    ROUND(
        AVG(DATE_DIFF('day', c.discharge_datetime::DATE, cl.submitted_at::DATE)),
        1
    )                                                                                AS avg_lag_days
FROM cm_case c
JOIN cm_claim cl ON c.case_id = cl.case_id
WHERE c.hospital_district = ?
  AND c.discharge_datetime IS NOT NULL
  AND cl.submitted_at IS NOT NULL
GROUP BY c.hospital_district
""",
        "param_slots": [{"name": "district", "entity_type": "district", "position": 1}],
        "result_ttl_seconds": 600,
    },

    "T201": {
        "abstract_question": "What is the average lag from claim approval to payment in {district}?",
        "date_filter": None,
        "sql_template": """
SELECT
    c.hospital_district                                                              AS district_name,
    COUNT(DISTINCT p.claim_id)                                                       AS paid_claims,
    ROUND(
        AVG(DATE_DIFF('day', cl.settled_at::DATE, p.payment_date::DATE)),
        1
    )                                                                                AS avg_approval_to_payment_days
FROM cm_claim cl
JOIN cm_case c    ON cl.case_id  = c.case_id
JOIN cm_payment p ON cl.claim_id = p.claim_id
WHERE c.hospital_district = ?
  AND cl.claim_status IN ('APPROVED', 'SETTLED')
  AND cl.settled_at IS NOT NULL
  AND p.payment_date IS NOT NULL
GROUP BY c.hospital_district
""",
        "param_slots": [{"name": "district", "entity_type": "district", "position": 1}],
        "result_ttl_seconds": 600,
    },

    "T202": {
        "abstract_question": "Which clinicians in {district} have the highest case volumes?",
        "date_filter": None,
        "sql_template": """
SELECT
    s.name                                                                           AS clinician_name,
    s.role_type,
    h.hospital_name,
    COUNT(DISTINCT c.case_id)                                                        AS case_count
FROM cm_preauth_procedure_line pl
JOIN hm_staff            s  ON pl.clinician_staff_id = s.staff_id
JOIN cm_preauth_request  pr ON pl.preauth_id         = pr.preauth_id
JOIN cm_case             c  ON pr.case_id            = c.case_id
JOIN hm_hospital         h  ON c.hospital_id         = h.hospital_id
WHERE c.hospital_district = ?
  AND pl.clinician_staff_id IS NOT NULL
GROUP BY s.staff_id, s.name, s.role_type, h.hospital_name
ORDER BY case_count DESC
LIMIT 10
""",
        "param_slots": [{"name": "district", "entity_type": "district", "position": 1}],
        "result_ttl_seconds": 600,
    },

    "T203": {
        "abstract_question": "Which clinicians in {district} are associated with the highest-value procedures?",
        "date_filter": None,
        "sql_template": """
SELECT
    s.name                                                                           AS clinician_name,
    s.role_type,
    h.hospital_name,
    COUNT(DISTINCT c.case_id)                                                        AS case_count,
    ROUND(AVG(cl.amount_approved), 2)                                                AS avg_approved_amount
FROM cm_preauth_procedure_line pl
JOIN hm_staff            s  ON pl.clinician_staff_id = s.staff_id
JOIN cm_preauth_request  pr ON pl.preauth_id         = pr.preauth_id
JOIN cm_case             c  ON pr.case_id            = c.case_id
JOIN hm_hospital         h  ON c.hospital_id         = h.hospital_id
JOIN cm_claim            cl ON c.case_id             = cl.case_id
WHERE c.hospital_district = ?
  AND pl.clinician_staff_id IS NOT NULL
GROUP BY s.staff_id, s.name, s.role_type, h.hospital_name
ORDER BY avg_approved_amount DESC
LIMIT 10
""",
        "param_slots": [{"name": "district", "entity_type": "district", "position": 1}],
        "result_ttl_seconds": 600,
    },

    "T204": {
        "abstract_question": "Which private hospitals in {district} are billing procedures reserved for public hospitals only?",
        "date_filter": None,
        "sql_template": """
SELECT
    h.hospital_name,
    h.hospital_type,
    p.hbp_procedure_code,
    p.procedure_name,
    COUNT(DISTINCT c.case_id)                                                        AS case_count
FROM ref_hbp_procedure_master p
JOIN cm_preauth_procedure_line pl ON p.hbp_procedure_code = pl.hbp_procedure_code
JOIN cm_preauth_request pr        ON pl.preauth_id        = pr.preauth_id
JOIN cm_case c                    ON pr.case_id           = c.case_id
JOIN hm_hospital h                ON c.hospital_id        = h.hospital_id
WHERE p.reserved_public_hospitals_only = TRUE
  AND h.hospital_type = 'PRIVATE'
  AND c.hospital_district = ?
GROUP BY h.hospital_id, h.hospital_name, h.hospital_type, p.hbp_procedure_code, p.procedure_name
ORDER BY case_count DESC
""",
        "param_slots": [{"name": "district", "entity_type": "district", "position": 1}],
        "result_ttl_seconds": 600,
    },

    "T205": {
        "abstract_question": "What is the concentration of scheme expenditure within {district}?",
        "date_filter": {"alias": "c", "column": "admission_datetime"},
        "sql_template": """
WITH hospital_spend AS (
    SELECT
        h.hospital_id,
        h.hospital_name,
        ROUND(SUM(cl.amount_approved), 2) AS spend,
        ROW_NUMBER() OVER (ORDER BY SUM(cl.amount_approved) DESC) AS rnk
    FROM cm_case c
    JOIN hm_hospital h ON c.hospital_id = h.hospital_id
    LEFT JOIN cm_claim cl ON c.case_id = cl.case_id
    WHERE c.hospital_district = ?
    GROUP BY h.hospital_id, h.hospital_name
),
total AS (SELECT SUM(spend) AS total_spend FROM hospital_spend)
SELECT
    hs.rnk,
    hs.hospital_name,
    hs.spend,
    ROUND(hs.spend * 100.0 / NULLIF(t.total_spend, 0), 1)                           AS share_pct,
    ROUND(SUM(hs.spend) OVER (ORDER BY hs.rnk) * 100.0 / NULLIF(t.total_spend, 0), 1) AS cumulative_share_pct
FROM hospital_spend hs, total t
WHERE hs.rnk <= 10
ORDER BY hs.rnk
""",
        "param_slots": [{"name": "district", "entity_type": "district", "position": 1}],
        "result_ttl_seconds": 600,
    },

    "T206": {
        "abstract_question": "How does {district} compare with the state average on utilization, approval rate, and settlement TAT?",
        "date_filter": {"alias": "c", "column": "admission_datetime"},
        "sql_template": """
WITH state_metrics AS (
    SELECT
        ROUND(COUNT(DISTINCT c.case_id) * 1000.0 / NULLIF(COUNT(DISTINCT b.beneficiary_id), 0), 1) AS utilization_per_1000,
        ROUND(AVG(cl.amount_approved / NULLIF(cl.amount_claimed, 0) * 100), 1)                     AS approval_rate_pct,
        ROUND(AVG(cl.settlement_tat_days), 1)                                                       AS avg_tat_days
    FROM cm_case c
    LEFT JOIN cm_claim cl      ON c.case_id       = cl.case_id
    LEFT JOIN bm_beneficiary b ON c.beneficiary_id = b.beneficiary_id
),
district_metrics AS (
    SELECT
        ROUND(COUNT(DISTINCT c.case_id) * 1000.0 / NULLIF(
            (SELECT COUNT(DISTINCT b2.beneficiary_id)
             FROM bm_beneficiary b2
             JOIN bm_household h2 ON b2.household_id = h2.household_id
             WHERE h2.home_district_code = ?), 0), 1)                                              AS utilization_per_1000,
        ROUND(AVG(cl.amount_approved / NULLIF(cl.amount_claimed, 0) * 100), 1)                     AS approval_rate_pct,
        ROUND(AVG(cl.settlement_tat_days), 1)                                                       AS avg_tat_days
    FROM cm_case c
    LEFT JOIN cm_claim cl ON c.case_id = cl.case_id
    WHERE c.hospital_district = ?
)
SELECT
    'utilization_per_1000'  AS metric,
    sm.utilization_per_1000 AS state_avg,
    dm.utilization_per_1000 AS district_value,
    ROUND(dm.utilization_per_1000 - sm.utilization_per_1000, 1) AS difference
FROM state_metrics sm, district_metrics dm
UNION ALL
SELECT 'approval_rate_pct', sm.approval_rate_pct, dm.approval_rate_pct,
    ROUND(dm.approval_rate_pct - sm.approval_rate_pct, 1)
FROM state_metrics sm, district_metrics dm
UNION ALL
SELECT 'avg_tat_days', sm.avg_tat_days, dm.avg_tat_days,
    ROUND(dm.avg_tat_days - sm.avg_tat_days, 1)
FROM state_metrics sm, district_metrics dm
""",
        "param_slots": [
            {"name": "district", "entity_type": "district", "position": 1},
            {"name": "district", "entity_type": "district", "position": 2},
        ],
        "result_ttl_seconds": 600,
    },

    "T207": {
        "abstract_question": "How does {district} compare with the state average on public vs private treatment share?",
        "date_filter": {"alias": "c", "column": "admission_datetime"},
        "sql_template": """
WITH state_split AS (
    SELECT
        h.hospital_type,
        ROUND(COUNT(DISTINCT c.case_id) * 100.0 / SUM(COUNT(DISTINCT c.case_id)) OVER(), 1) AS state_pct
    FROM cm_case c
    JOIN hm_hospital h ON c.hospital_id = h.hospital_id
    GROUP BY h.hospital_type
),
district_split AS (
    SELECT
        h.hospital_type,
        ROUND(COUNT(DISTINCT c.case_id) * 100.0 / SUM(COUNT(DISTINCT c.case_id)) OVER(), 1) AS district_pct
    FROM cm_case c
    JOIN hm_hospital h ON c.hospital_id = h.hospital_id
    WHERE c.hospital_district = ?
    GROUP BY h.hospital_type
)
SELECT
    ss.hospital_type,
    ss.state_pct,
    COALESCE(ds.district_pct, 0) AS district_pct,
    ROUND(COALESCE(ds.district_pct, 0) - ss.state_pct, 1) AS difference
FROM state_split ss
LEFT JOIN district_split ds ON ss.hospital_type = ds.hospital_type
ORDER BY ss.hospital_type
""",
        "param_slots": [{"name": "district", "entity_type": "district", "position": 1}],
        "result_ttl_seconds": 600,
    },

    "T208": {
        "abstract_question": "What is the duplicate-beneficiary rate in {district} by enrolment source?",
        "date_filter": None,
        "sql_template": """
SELECT
    h.entitlement_source,
    COUNT(b.beneficiary_id)                                                          AS total_beneficiaries,
    COUNT(CASE WHEN b.is_duplicate = TRUE THEN 1 END)                               AS duplicate_count,
    ROUND(
        COUNT(CASE WHEN b.is_duplicate = TRUE THEN 1 END)
        * 100.0 / NULLIF(COUNT(b.beneficiary_id), 0),
        1
    )                                                                                AS duplicate_rate_pct
FROM bm_beneficiary b
JOIN bm_household h ON b.household_id = h.household_id
WHERE h.home_district_code = ?
GROUP BY h.entitlement_source
ORDER BY duplicate_rate_pct DESC
""",
        "param_slots": [{"name": "district", "entity_type": "district", "position": 1}],
        "result_ttl_seconds": 600,
    },

    "T209": {
        "abstract_question": "What is the enrolment rejection rate in {district} by submitted_by_role?",
        "date_filter": None,
        "sql_template": """
SELECT
    er.submitted_by_role,
    COUNT(er.enrolment_request_id)                                                   AS total_requests,
    COUNT(CASE WHEN er.status = 'REJECTED' THEN 1 END)                              AS rejected,
    ROUND(
        COUNT(CASE WHEN er.status = 'REJECTED' THEN 1 END)
        * 100.0 / NULLIF(COUNT(er.enrolment_request_id), 0),
        1
    )                                                                                AS rejection_rate_pct
FROM bm_enrolment_request er
JOIN bm_beneficiary b ON er.beneficiary_id = b.beneficiary_id
JOIN bm_household   h ON b.household_id    = h.household_id
WHERE h.home_district_code = ?
GROUP BY er.submitted_by_role
ORDER BY rejection_rate_pct DESC
""",
        "param_slots": [{"name": "district", "entity_type": "district", "position": 1}],
        "result_ttl_seconds": 600,
    },

    "T210": {
        "abstract_question": "What is the enrolment rejection rate in {district} by authentication mode?",
        "date_filter": None,
        "sql_template": """
SELECT
    er.auth_mode,
    COUNT(er.enrolment_request_id)                                                   AS total_requests,
    COUNT(CASE WHEN er.status = 'REJECTED' THEN 1 END)                              AS rejected,
    ROUND(
        COUNT(CASE WHEN er.status = 'REJECTED' THEN 1 END)
        * 100.0 / NULLIF(COUNT(er.enrolment_request_id), 0),
        1
    )                                                                                AS rejection_rate_pct
FROM bm_enrolment_request er
JOIN bm_beneficiary b ON er.beneficiary_id = b.beneficiary_id
JOIN bm_household   h ON b.household_id    = h.household_id
WHERE h.home_district_code = ?
GROUP BY er.auth_mode
ORDER BY rejection_rate_pct DESC
""",
        "param_slots": [{"name": "district", "entity_type": "district", "position": 1}],
        "result_ttl_seconds": 600,
    },

    "T211": {
        "abstract_question": "What is the profile-completeness rate in {district} by entitlement source?",
        "date_filter": None,
        "sql_template": """
SELECT
    h.entitlement_source,
    COUNT(b.beneficiary_id)                                                          AS total_beneficiaries,
    ROUND(COUNT(b.yob)       * 100.0 / NULLIF(COUNT(b.beneficiary_id), 0), 1)       AS yob_pct,
    ROUND(COUNT(b.mobile)    * 100.0 / NULLIF(COUNT(b.beneficiary_id), 0), 1)       AS mobile_pct,
    ROUND(COUNT(b.photo_uri) * 100.0 / NULLIF(COUNT(b.beneficiary_id), 0), 1)       AS photo_pct,
    ROUND(
        (COUNT(b.yob) + COUNT(b.mobile) + COUNT(b.photo_uri))
        * 100.0 / NULLIF(COUNT(b.beneficiary_id) * 3, 0),
        1
    )                                                                                AS overall_completeness_pct
FROM bm_beneficiary b
JOIN bm_household h ON b.household_id = h.household_id
WHERE h.home_district_code = ?
GROUP BY h.entitlement_source
ORDER BY overall_completeness_pct DESC
""",
        "param_slots": [{"name": "district", "entity_type": "district", "position": 1}],
        "result_ttl_seconds": 600,
    },

    "T212": {
        "abstract_question": "Which hospitals in {district} are most dependent on portability cases?",
        "date_filter": {"alias": "c", "column": "admission_datetime"},
        "sql_template": """
SELECT
    h.hospital_name,
    h.hospital_type,
    COUNT(DISTINCT c.case_id)                                                        AS total_cases,
    COUNT(DISTINCT CASE WHEN c.is_portability = TRUE THEN c.case_id END)            AS portability_cases,
    ROUND(
        COUNT(DISTINCT CASE WHEN c.is_portability = TRUE THEN c.case_id END)
        * 100.0 / NULLIF(COUNT(DISTINCT c.case_id), 0),
        1
    )                                                                                AS portability_pct
FROM cm_case c
JOIN hm_hospital h ON c.hospital_id = h.hospital_id
WHERE c.hospital_district = ?
GROUP BY h.hospital_id, h.hospital_name, h.hospital_type
ORDER BY portability_pct DESC
LIMIT 10
""",
        "param_slots": [{"name": "district", "entity_type": "district", "position": 1}],
        "result_ttl_seconds": 600,
    },

    "T213": {
        "abstract_question": "What share of cases in {district} are handled by accredited hospitals?",
        "date_filter": {"alias": "c", "column": "admission_datetime"},
        "sql_template": """
SELECT
    COUNT(DISTINCT c.case_id)                                                        AS total_cases,
    COUNT(DISTINCT CASE WHEN h.accreditation_board IS NOT NULL THEN c.case_id END)  AS accredited_hospital_cases,
    ROUND(
        COUNT(DISTINCT CASE WHEN h.accreditation_board IS NOT NULL THEN c.case_id END)
        * 100.0 / NULLIF(COUNT(DISTINCT c.case_id), 0),
        1
    )                                                                                AS accredited_share_pct
FROM cm_case c
JOIN hm_hospital h ON c.hospital_id = h.hospital_id
WHERE c.hospital_district = ?
""",
        "param_slots": [{"name": "district", "entity_type": "district", "position": 1}],
        "result_ttl_seconds": 600,
    },

    "T214": {
        "abstract_question": "What is the average claim haircut in {district} by hospital type?",
        "date_filter": {"alias": "c", "column": "admission_datetime"},
        "sql_template": """
SELECT
    h.hospital_type,
    COUNT(DISTINCT cl.claim_id)                                                      AS total_claims,
    ROUND(
        AVG((cl.amount_claimed - cl.amount_approved) / NULLIF(cl.amount_claimed, 0) * 100),
        1
    )                                                                                AS avg_haircut_pct
FROM cm_claim cl
JOIN cm_case c     ON cl.case_id    = c.case_id
JOIN hm_hospital h ON c.hospital_id = h.hospital_id
WHERE c.hospital_district = ?
GROUP BY h.hospital_type
ORDER BY avg_haircut_pct DESC
""",
        "param_slots": [{"name": "district", "entity_type": "district", "position": 1}],
        "result_ttl_seconds": 600,
    },

    "T215": {
        "abstract_question": "What is the average settlement TAT in {district} by hospital type?",
        "date_filter": {"alias": "c", "column": "admission_datetime"},
        "sql_template": """
SELECT
    h.hospital_type,
    COUNT(DISTINCT cl.claim_id)                                                      AS total_claims,
    ROUND(AVG(cl.settlement_tat_days), 1)                                            AS avg_tat_days,
    ROUND(
        PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY cl.settlement_tat_days),
        1
    )                                                                                AS median_tat_days
FROM cm_claim cl
JOIN cm_case c     ON cl.case_id    = c.case_id
JOIN hm_hospital h ON c.hospital_id = h.hospital_id
WHERE c.hospital_district = ?
  AND cl.settlement_tat_days IS NOT NULL
GROUP BY h.hospital_type
ORDER BY avg_tat_days
""",
        "param_slots": [{"name": "district", "entity_type": "district", "position": 1}],
        "result_ttl_seconds": 600,
    },

    "T216": {
        "abstract_question": "What is the mortality rate in {district} by diagnosis category?",
        "date_filter": None,
        "sql_template": """
SELECT
    d.diagnosis_category,
    COUNT(DISTINCT c.case_id)                                                        AS total_cases,
    COUNT(DISTINCT CASE WHEN dis.death_date IS NOT NULL THEN dis.case_id END)       AS death_count,
    ROUND(
        COUNT(DISTINCT CASE WHEN dis.death_date IS NOT NULL THEN dis.case_id END)
        * 100.0 / NULLIF(COUNT(DISTINCT c.case_id), 0),
        2
    )                                                                                AS mortality_rate_pct
FROM cm_case_diagnosis d
JOIN cm_case c       ON d.case_id  = c.case_id
LEFT JOIN cm_discharge dis ON c.case_id = dis.case_id
WHERE c.hospital_district = ?
  AND d.diagnosis_type = 'PRIMARY'
GROUP BY d.diagnosis_category
ORDER BY mortality_rate_pct DESC
""",
        "param_slots": [{"name": "district", "entity_type": "district", "position": 1}],
        "result_ttl_seconds": 600,
    },

    "T217": {
        "abstract_question": "What is the LAMA/DAMA rate in {district} by diagnosis category?",
        "date_filter": None,
        "sql_template": """
SELECT
    d.diagnosis_category,
    COUNT(DISTINCT c.case_id)                                                        AS total_cases,
    COUNT(DISTINCT CASE WHEN dis.lama_date IS NOT NULL THEN dis.case_id END)        AS lama_count,
    ROUND(
        COUNT(DISTINCT CASE WHEN dis.lama_date IS NOT NULL THEN dis.case_id END)
        * 100.0 / NULLIF(COUNT(DISTINCT c.case_id), 0),
        2
    )                                                                                AS lama_rate_pct
FROM cm_case_diagnosis d
JOIN cm_case c          ON d.case_id  = c.case_id
LEFT JOIN cm_discharge dis ON c.case_id = dis.case_id
WHERE c.hospital_district = ?
  AND d.diagnosis_type = 'PRIMARY'
GROUP BY d.diagnosis_category
ORDER BY lama_rate_pct DESC
""",
        "param_slots": [{"name": "district", "entity_type": "district", "position": 1}],
        "result_ttl_seconds": 600,
    },

    "T218": {
        "abstract_question": "What is the average length of stay in {district} by diagnosis category?",
        "date_filter": {"alias": "c", "column": "admission_datetime"},
        "sql_template": """
SELECT
    d.diagnosis_category,
    COUNT(DISTINCT c.case_id)                                                        AS total_cases,
    ROUND(
        AVG(DATE_DIFF('day', c.admission_datetime::DATE, c.discharge_datetime::DATE)),
        1
    )                                                                                AS avg_los_days
FROM cm_case_diagnosis d
JOIN cm_case c ON d.case_id = c.case_id
WHERE c.hospital_district = ?
  AND d.diagnosis_type = 'PRIMARY'
  AND c.discharge_datetime IS NOT NULL
GROUP BY d.diagnosis_category
ORDER BY avg_los_days DESC
""",
        "param_slots": [{"name": "district", "entity_type": "district", "position": 1}],
        "result_ttl_seconds": 600,
    },

    "T219": {
        "abstract_question": "What are the top diagnosis-procedure combinations in {district} by spend?",
        "date_filter": {"alias": "c", "column": "admission_datetime"},
        "sql_template": """
SELECT
    d.diagnosis_category,
    p.procedure_name,
    COUNT(DISTINCT c.case_id)                                                        AS case_count,
    ROUND(SUM(cl.amount_approved), 2)                                                AS total_approved
FROM cm_case_diagnosis d
JOIN cm_case c                    ON d.case_id            = c.case_id
JOIN cm_preauth_request pr        ON c.case_id            = pr.case_id
JOIN cm_preauth_procedure_line pl ON pr.preauth_id        = pl.preauth_id
JOIN ref_hbp_procedure_master p   ON pl.hbp_procedure_code = p.hbp_procedure_code
JOIN cm_claim cl                  ON c.case_id            = cl.case_id
WHERE c.hospital_district = ?
  AND d.diagnosis_type = 'PRIMARY'
GROUP BY d.diagnosis_category, p.procedure_name
ORDER BY total_approved DESC
LIMIT 10
""",
        "param_slots": [{"name": "district", "entity_type": "district", "position": 1}],
        "result_ttl_seconds": 600,
    },

    "T220": {
        "abstract_question": "What is the procedure mix in {district} for public vs private hospitals?",
        "date_filter": {"alias": "c", "column": "admission_datetime"},
        "sql_template": """
WITH ranked AS (
    SELECT
        h.hospital_type,
        p.procedure_name,
        COUNT(*)                                                                     AS usage_count,
        ROW_NUMBER() OVER (PARTITION BY h.hospital_type ORDER BY COUNT(*) DESC)     AS rnk
    FROM cm_preauth_procedure_line pl
    JOIN ref_hbp_procedure_master p  ON pl.hbp_procedure_code = p.hbp_procedure_code
    JOIN cm_preauth_request pr       ON pl.preauth_id         = pr.preauth_id
    JOIN cm_case c                   ON pr.case_id            = c.case_id
    JOIN hm_hospital h               ON c.hospital_id         = h.hospital_id
    WHERE c.hospital_district = ?
    GROUP BY h.hospital_type, p.procedure_name
)
SELECT hospital_type, procedure_name, usage_count
FROM ranked
WHERE rnk <= 10
ORDER BY hospital_type, rnk
""",
        "param_slots": [{"name": "district", "entity_type": "district", "position": 1}],
        "result_ttl_seconds": 600,
    },

    "T221": {
        "abstract_question": "Which hospitals in {district} have case volume per bed far above district average?",
        "date_filter": {"alias": "c", "column": "admission_datetime"},
        "sql_template": """
WITH hospital_stats AS (
    SELECT
        h.hospital_id,
        h.hospital_name,
        h.hospital_type,
        h.total_bed_strength,
        COUNT(DISTINCT c.case_id)                                                    AS case_count,
        ROUND(COUNT(DISTINCT c.case_id) * 1.0 / NULLIF(h.total_bed_strength, 0), 2) AS cases_per_bed
    FROM cm_case c
    JOIN hm_hospital h ON c.hospital_id = h.hospital_id
    WHERE c.hospital_district = ?
    GROUP BY h.hospital_id, h.hospital_name, h.hospital_type, h.total_bed_strength
),
district_avg AS (
    SELECT AVG(cases_per_bed) AS avg_cases_per_bed FROM hospital_stats
)
SELECT
    hs.hospital_name,
    hs.hospital_type,
    hs.total_bed_strength,
    hs.case_count,
    hs.cases_per_bed,
    da.avg_cases_per_bed                                                             AS district_avg,
    ROUND(hs.cases_per_bed / NULLIF(da.avg_cases_per_bed, 0), 2)                    AS ratio_to_avg
FROM hospital_stats hs, district_avg da
WHERE hs.cases_per_bed > da.avg_cases_per_bed * 1.5
ORDER BY ratio_to_avg DESC
""",
        "param_slots": [{"name": "district", "entity_type": "district", "position": 1}],
        "result_ttl_seconds": 600,
    },

    "T223": {
        "abstract_question": "What share of beneficiaries in {district} are enrolled but without cards issued yet?",
        "date_filter": None,
        "sql_template": """
SELECT
    COUNT(DISTINCT b.beneficiary_id)                                                 AS total_enrolled,
    COUNT(DISTINCT CASE WHEN ca.card_id IS NOT NULL THEN b.beneficiary_id END)      AS with_card,
    COUNT(DISTINCT CASE WHEN ca.card_id IS NULL THEN b.beneficiary_id END)          AS without_card,
    ROUND(
        COUNT(DISTINCT CASE WHEN ca.card_id IS NULL THEN b.beneficiary_id END)
        * 100.0 / NULLIF(COUNT(DISTINCT b.beneficiary_id), 0),
        1
    )                                                                                AS no_card_pct
FROM bm_beneficiary b
JOIN bm_household h ON b.household_id = h.household_id
LEFT JOIN bm_card ca ON b.beneficiary_id = ca.beneficiary_id
WHERE h.home_district_code = ?
""",
        "param_slots": [{"name": "district", "entity_type": "district", "position": 1}],
        "result_ttl_seconds": 600,
    },

    "T224": {
        "abstract_question": "Which blocks in {district} have the highest share of beneficiaries without cards?",
        "date_filter": None,
        "sql_template": """
SELECT
    h.home_block_name                                                                AS block_name,
    COUNT(DISTINCT b.beneficiary_id)                                                 AS total_enrolled,
    COUNT(DISTINCT CASE WHEN ca.card_id IS NULL THEN b.beneficiary_id END)          AS without_card,
    ROUND(
        COUNT(DISTINCT CASE WHEN ca.card_id IS NULL THEN b.beneficiary_id END)
        * 100.0 / NULLIF(COUNT(DISTINCT b.beneficiary_id), 0),
        1
    )                                                                                AS no_card_pct
FROM bm_beneficiary b
JOIN bm_household h ON b.household_id = h.household_id
LEFT JOIN bm_card ca ON b.beneficiary_id = ca.beneficiary_id
WHERE h.home_district_code = ?
GROUP BY h.home_block_name
ORDER BY no_card_pct DESC
LIMIT 10
""",
        "param_slots": [{"name": "district", "entity_type": "district", "position": 1}],
        "result_ttl_seconds": 600,
    },

    "T225": {
        "abstract_question": "Which blocks in {district} contribute the most portability cases?",
        "date_filter": {"alias": "c", "column": "admission_datetime"},
        "sql_template": """
SELECT
    h.home_block_name                                                                AS block_name,
    COUNT(DISTINCT c.case_id)                                                        AS portability_cases,
    ROUND(COUNT(DISTINCT c.case_id) * 100.0 / SUM(COUNT(DISTINCT c.case_id)) OVER(), 1) AS pct
FROM cm_case c
JOIN bm_beneficiary b ON c.beneficiary_id = b.beneficiary_id
JOIN bm_household   h ON b.household_id   = h.household_id
WHERE c.is_portability = TRUE
  AND h.home_district_code = ?
GROUP BY h.home_block_name
ORDER BY portability_cases DESC
LIMIT 10
""",
        "param_slots": [{"name": "district", "entity_type": "district", "position": 1}],
        "result_ttl_seconds": 600,
    },

    "T226": {
        "abstract_question": "Which blocks in {district} have the highest out-of-district treatment share?",
        "date_filter": {"alias": "c", "column": "admission_datetime"},
        "sql_template": """
SELECT
    h.home_block_name                                                                AS block_name,
    COUNT(DISTINCT c.case_id)                                                        AS total_cases,
    COUNT(DISTINCT CASE WHEN c.hospital_district != h.home_district_code THEN c.case_id END) AS out_of_district,
    ROUND(
        COUNT(DISTINCT CASE WHEN c.hospital_district != h.home_district_code THEN c.case_id END)
        * 100.0 / NULLIF(COUNT(DISTINCT c.case_id), 0),
        1
    )                                                                                AS out_of_district_pct
FROM cm_case c
JOIN bm_beneficiary b ON c.beneficiary_id = b.beneficiary_id
JOIN bm_household   h ON b.household_id   = h.household_id
WHERE h.home_district_code = ?
GROUP BY h.home_block_name
ORDER BY out_of_district_pct DESC
LIMIT 10
""",
        "param_slots": [{"name": "district", "entity_type": "district", "position": 1}],
        "result_ttl_seconds": 600,
    },

    # ── R. Block Expanded Analytics (T227-T254) ───────────────────────────────

    "T227": {
        "abstract_question": "What is the active vs inactive vs disabled card rate in {block}?",
        "date_filter": None,
        "sql_template": """
SELECT
    ca.card_status,
    COUNT(*)                                                                         AS card_count,
    ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER(), 1)                               AS pct
FROM bm_card ca
JOIN bm_beneficiary b ON ca.beneficiary_id = b.beneficiary_id
JOIN bm_household   h ON b.household_id    = h.household_id
WHERE h.home_block_name = ?
GROUP BY ca.card_status
ORDER BY card_count DESC
""",
        "param_slots": [{"name": "block", "entity_type": "block", "position": 1}],
        "result_ttl_seconds": 600,
    },

    "T228": {
        "abstract_question": "What is the beneficiary profile completeness rate in {block}?",
        "date_filter": None,
        "sql_template": """
SELECT
    COUNT(*)                                                                         AS total_beneficiaries,
    ROUND(COUNT(b.yob)       * 100.0 / NULLIF(COUNT(*), 0), 1)                      AS yob_completeness_pct,
    ROUND(COUNT(b.mobile)    * 100.0 / NULLIF(COUNT(*), 0), 1)                      AS mobile_completeness_pct,
    ROUND(COUNT(b.photo_uri) * 100.0 / NULLIF(COUNT(*), 0), 1)                      AS photo_completeness_pct
FROM bm_beneficiary b
JOIN bm_household h ON b.household_id = h.household_id
WHERE h.home_block_name = ?
""",
        "param_slots": [{"name": "block", "entity_type": "block", "position": 1}],
        "result_ttl_seconds": 600,
    },

    "T229": {
        "abstract_question": "What is the beneficiaries per empanelled hospital ratio in {block}?",
        "date_filter": None,
        "sql_template": """
WITH enrolled AS (
    SELECT COUNT(DISTINCT b.beneficiary_id) AS beneficiary_count
    FROM bm_beneficiary b
    JOIN bm_household h ON b.household_id = h.household_id
    WHERE h.home_block_name = ?
),
hospitals AS (
    SELECT COUNT(DISTINCT hospital_id) AS hospital_count
    FROM hm_hospital
    WHERE block_name = ?
)
SELECT
    e.beneficiary_count,
    h.hospital_count,
    ROUND(e.beneficiary_count * 1.0 / NULLIF(h.hospital_count, 0), 1) AS beneficiaries_per_hospital
FROM enrolled e, hospitals h
""",
        "param_slots": [
            {"name": "block", "entity_type": "block", "position": 1},
            {"name": "block", "entity_type": "block", "position": 2},
        ],
        "result_ttl_seconds": 600,
    },

    "T230": {
        "abstract_question": "What is the case rate per 1,000 enrolled beneficiaries in {block}?",
        "date_filter": {"alias": "c", "column": "admission_datetime"},
        "sql_template": """
WITH cases AS (
    SELECT COUNT(DISTINCT c.case_id) AS case_count
    FROM cm_case c
    JOIN bm_beneficiary b ON c.beneficiary_id = b.beneficiary_id
    JOIN bm_household   h ON b.household_id   = h.household_id
    WHERE h.home_block_name = ?
),
enrolled AS (
    SELECT COUNT(DISTINCT b.beneficiary_id) AS beneficiary_count
    FROM bm_beneficiary b
    JOIN bm_household h ON b.household_id = h.household_id
    WHERE h.home_block_name = ?
)
SELECT
    ca.case_count,
    e.beneficiary_count,
    ROUND(ca.case_count * 1000.0 / NULLIF(e.beneficiary_count, 0), 1) AS cases_per_1000_enrolled
FROM cases ca, enrolled e
""",
        "param_slots": [
            {"name": "block", "entity_type": "block", "position": 1},
            {"name": "block", "entity_type": "block", "position": 2},
        ],
        "result_ttl_seconds": 600,
    },

    "T231": {
        "abstract_question": "What share of beneficiaries in {block} received cards within 30 days of enrolment?",
        "date_filter": None,
        "sql_template": """
SELECT
    COUNT(DISTINCT er.enrolment_request_id)                                          AS total_enrolments,
    COUNT(DISTINCT CASE
        WHEN DATE_DIFF('day', er.submitted_at::DATE, ca.issued_at::DATE) <= 30
        THEN er.enrolment_request_id
    END)                                                                             AS within_30_days,
    ROUND(
        COUNT(DISTINCT CASE
            WHEN DATE_DIFF('day', er.submitted_at::DATE, ca.issued_at::DATE) <= 30
            THEN er.enrolment_request_id
        END) * 100.0 / NULLIF(COUNT(DISTINCT er.enrolment_request_id), 0),
        1
    )                                                                                AS within_30_days_pct
FROM bm_enrolment_request er
JOIN bm_beneficiary b  ON er.beneficiary_id = b.beneficiary_id
JOIN bm_household   h  ON b.household_id    = h.household_id
JOIN bm_card        ca ON er.beneficiary_id = ca.beneficiary_id
WHERE h.home_block_name = ?
  AND ca.issued_at IS NOT NULL
""",
        "param_slots": [{"name": "block", "entity_type": "block", "position": 1}],
        "result_ttl_seconds": 600,
    },

    "T232": {
        "abstract_question": "What share of claimants in {block} were admitted within 30 days of enrolment?",
        "date_filter": None,
        "sql_template": """
WITH first_enrolment AS (
    SELECT
        er.beneficiary_id,
        MIN(er.submitted_at) AS first_submitted_at
    FROM bm_enrolment_request er
    JOIN bm_beneficiary b ON er.beneficiary_id = b.beneficiary_id
    JOIN bm_household   h ON b.household_id    = h.household_id
    WHERE h.home_block_name = ?
    GROUP BY er.beneficiary_id
),
first_admission AS (
    SELECT
        c.beneficiary_id,
        MIN(c.admission_datetime) AS first_admission_at
    FROM cm_case c
    GROUP BY c.beneficiary_id
)
SELECT
    COUNT(DISTINCT fe.beneficiary_id)                                                AS total_claimants,
    COUNT(DISTINCT CASE
        WHEN DATE_DIFF('day', fe.first_submitted_at::DATE, fa.first_admission_at::DATE) <= 30
        THEN fe.beneficiary_id
    END)                                                                             AS within_30_days,
    ROUND(
        COUNT(DISTINCT CASE
            WHEN DATE_DIFF('day', fe.first_submitted_at::DATE, fa.first_admission_at::DATE) <= 30
            THEN fe.beneficiary_id
        END) * 100.0 / NULLIF(COUNT(DISTINCT fe.beneficiary_id), 0),
        1
    )                                                                                AS within_30_days_pct
FROM first_enrolment fe
JOIN first_admission fa ON fe.beneficiary_id = fa.beneficiary_id
""",
        "param_slots": [{"name": "block", "entity_type": "block", "position": 1}],
        "result_ttl_seconds": 600,
    },

    "T233": {
        "abstract_question": "What share of cases from {block} were treated outside the home block?",
        "date_filter": {"alias": "c", "column": "admission_datetime"},
        "sql_template": """
SELECT
    COUNT(DISTINCT c.case_id)                                                        AS total_cases,
    COUNT(DISTINCT CASE WHEN hosp.block_name != h.home_block_name THEN c.case_id END) AS out_of_block,
    ROUND(
        COUNT(DISTINCT CASE WHEN hosp.block_name != h.home_block_name THEN c.case_id END)
        * 100.0 / NULLIF(COUNT(DISTINCT c.case_id), 0),
        1
    )                                                                                AS out_of_block_pct
FROM cm_case c
JOIN bm_beneficiary b ON c.beneficiary_id = b.beneficiary_id
JOIN bm_household   h ON b.household_id   = h.household_id
JOIN hm_hospital hosp ON c.hospital_id    = hosp.hospital_id
WHERE h.home_block_name = ?
""",
        "param_slots": [{"name": "block", "entity_type": "block", "position": 1}],
        "result_ttl_seconds": 600,
    },

    "T234": {
        "abstract_question": "What share of cases from {block} were treated outside the home district?",
        "date_filter": {"alias": "c", "column": "admission_datetime"},
        "sql_template": """
SELECT
    COUNT(DISTINCT c.case_id)                                                        AS total_cases,
    COUNT(DISTINCT CASE WHEN c.hospital_district != h.home_district_code THEN c.case_id END) AS out_of_district,
    ROUND(
        COUNT(DISTINCT CASE WHEN c.hospital_district != h.home_district_code THEN c.case_id END)
        * 100.0 / NULLIF(COUNT(DISTINCT c.case_id), 0),
        1
    )                                                                                AS out_of_district_pct
FROM cm_case c
JOIN bm_beneficiary b ON c.beneficiary_id = b.beneficiary_id
JOIN bm_household   h ON b.household_id   = h.household_id
WHERE h.home_block_name = ?
""",
        "param_slots": [{"name": "block", "entity_type": "block", "position": 1}],
        "result_ttl_seconds": 600,
    },

    "T235": {
        "abstract_question": "Which hospitals receive the most patients from {block}?",
        "date_filter": {"alias": "c", "column": "admission_datetime"},
        "sql_template": """
SELECT
    hosp.hospital_name,
    hosp.hospital_type,
    hosp.district_name,
    COUNT(DISTINCT c.case_id)                                                        AS case_count
FROM cm_case c
JOIN bm_beneficiary b ON c.beneficiary_id = b.beneficiary_id
JOIN bm_household   h ON b.household_id   = h.household_id
JOIN hm_hospital hosp ON c.hospital_id    = hosp.hospital_id
WHERE h.home_block_name = ?
GROUP BY hosp.hospital_id, hosp.hospital_name, hosp.hospital_type, hosp.district_name
ORDER BY case_count DESC
LIMIT 10
""",
        "param_slots": [{"name": "block", "entity_type": "block", "position": 1}],
        "result_ttl_seconds": 600,
    },

    # ── T. Block disease / outcome / comparison (T237-T254) ──────────────────

    "T237": {
        "abstract_question": "What is the maternal/neonatal case rate per 1,000 enrolled women in {block}?",
        "date_filter": {"alias": "c", "column": "admission_datetime"},
        "sql_template": """
WITH maternal AS (
    SELECT COUNT(DISTINCT c.case_id) AS case_count
    FROM cm_case c
    JOIN bm_beneficiary b   ON c.beneficiary_id = b.beneficiary_id
    JOIN bm_household h     ON b.household_id   = h.household_id
    JOIN cm_case_diagnosis d ON c.case_id       = d.case_id
    WHERE h.home_block_name = ?
      AND d.diagnosis_category = 'MATERNAL_NEONATAL'
      AND d.diagnosis_type = 'PRIMARY'
),
enrolled_women AS (
    SELECT COUNT(DISTINCT b.beneficiary_id) AS enrolled_count
    FROM bm_beneficiary b
    JOIN bm_household h ON b.household_id = h.household_id
    WHERE h.home_block_name = ?
      AND b.gender = 'FEMALE'
)
SELECT
    m.case_count                                                              AS maternal_cases,
    e.enrolled_count                                                          AS enrolled_women,
    ROUND(m.case_count * 1000.0 / NULLIF(e.enrolled_count, 0), 2)           AS rate_per_1000_women
FROM maternal m, enrolled_women e
""",
        "param_slots": [
            {"name": "block", "entity_type": "block", "position": 1},
            {"name": "block", "entity_type": "block", "position": 2},
        ],
        "result_ttl_seconds": 600,
    },

    "T238": {
        "abstract_question": "What is the NCD case rate per 1,000 enrolled beneficiaries in {block}?",
        "date_filter": {"alias": "c", "column": "admission_datetime"},
        "sql_template": """
WITH ncd AS (
    SELECT COUNT(DISTINCT c.case_id) AS case_count
    FROM cm_case c
    JOIN bm_beneficiary b   ON c.beneficiary_id = b.beneficiary_id
    JOIN bm_household h     ON b.household_id   = h.household_id
    JOIN cm_case_diagnosis d ON c.case_id       = d.case_id
    WHERE h.home_block_name = ?
      AND d.diagnosis_category = 'NCD'
      AND d.diagnosis_type = 'PRIMARY'
),
enrolled AS (
    SELECT COUNT(DISTINCT b.beneficiary_id) AS enrolled_count
    FROM bm_beneficiary b
    JOIN bm_household h ON b.household_id = h.household_id
    WHERE h.home_block_name = ?
)
SELECT
    n.case_count                                                           AS ncd_cases,
    e.enrolled_count,
    ROUND(n.case_count * 1000.0 / NULLIF(e.enrolled_count, 0), 2)        AS rate_per_1000_enrolled
FROM ncd n, enrolled e
""",
        "param_slots": [
            {"name": "block", "entity_type": "block", "position": 1},
            {"name": "block", "entity_type": "block", "position": 2},
        ],
        "result_ttl_seconds": 600,
    },

    "T239": {
        "abstract_question": "What is the communicable disease case rate per 1,000 enrolled beneficiaries in {block}?",
        "date_filter": {"alias": "c", "column": "admission_datetime"},
        "sql_template": """
WITH comm AS (
    SELECT COUNT(DISTINCT c.case_id) AS case_count
    FROM cm_case c
    JOIN bm_beneficiary b   ON c.beneficiary_id = b.beneficiary_id
    JOIN bm_household h     ON b.household_id   = h.household_id
    JOIN cm_case_diagnosis d ON c.case_id       = d.case_id
    WHERE h.home_block_name = ?
      AND d.diagnosis_category = 'COMMUNICABLE'
      AND d.diagnosis_type = 'PRIMARY'
),
enrolled AS (
    SELECT COUNT(DISTINCT b.beneficiary_id) AS enrolled_count
    FROM bm_beneficiary b
    JOIN bm_household h ON b.household_id = h.household_id
    WHERE h.home_block_name = ?
)
SELECT
    c.case_count                                                           AS communicable_cases,
    e.enrolled_count,
    ROUND(c.case_count * 1000.0 / NULLIF(e.enrolled_count, 0), 2)        AS rate_per_1000_enrolled
FROM comm c, enrolled e
""",
        "param_slots": [
            {"name": "block", "entity_type": "block", "position": 1},
            {"name": "block", "entity_type": "block", "position": 2},
        ],
        "result_ttl_seconds": 600,
    },

    "T240": {
        "abstract_question": "What is the biometric authentication rate at discharge for cases originating from {block}?",
        "date_filter": None,
        "sql_template": """
SELECT
    COUNT(DISTINCT d.discharge_id)                                                          AS total_discharges,
    COUNT(DISTINCT CASE WHEN d.biometric_auth_used = TRUE THEN d.discharge_id END)         AS biometric_auths,
    ROUND(
        COUNT(DISTINCT CASE WHEN d.biometric_auth_used = TRUE THEN d.discharge_id END)
        * 100.0 / NULLIF(COUNT(DISTINCT d.discharge_id), 0), 1
    )                                                                                       AS biometric_rate_pct
FROM cm_discharge d
JOIN cm_case c       ON d.case_id       = c.case_id
JOIN bm_beneficiary b ON c.beneficiary_id = b.beneficiary_id
JOIN bm_household h  ON b.household_id  = h.household_id
WHERE h.home_block_name = ?
""",
        "param_slots": [{"name": "block", "entity_type": "block", "position": 1}],
        "result_ttl_seconds": 600,
    },

    "T241": {
        "abstract_question": "What is the medicine provision rate at discharge for cases originating from {block}?",
        "date_filter": None,
        "sql_template": """
SELECT
    COUNT(DISTINCT d.discharge_id)                                                          AS total_discharges,
    COUNT(DISTINCT CASE WHEN d.provided_medicines_flag = TRUE THEN d.discharge_id END)     AS medicine_provided,
    ROUND(
        COUNT(DISTINCT CASE WHEN d.provided_medicines_flag = TRUE THEN d.discharge_id END)
        * 100.0 / NULLIF(COUNT(DISTINCT d.discharge_id), 0), 1
    )                                                                                       AS medicine_provision_rate_pct
FROM cm_discharge d
JOIN cm_case c       ON d.case_id        = c.case_id
JOIN bm_beneficiary b ON c.beneficiary_id = b.beneficiary_id
JOIN bm_household h  ON b.household_id   = h.household_id
WHERE h.home_block_name = ?
""",
        "param_slots": [{"name": "block", "entity_type": "block", "position": 1}],
        "result_ttl_seconds": 600,
    },

    "T242": {
        "abstract_question": "What is the average lag from discharge to claim submission for cases from {block}?",
        "date_filter": None,
        "sql_template": """
SELECT
    ROUND(AVG(DATE_DIFF('day', c.discharge_datetime::DATE, cl.submitted_at::DATE)), 1)  AS avg_lag_days,
    ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (
        ORDER BY DATE_DIFF('day', c.discharge_datetime::DATE, cl.submitted_at::DATE)
    ), 1)                                                                                AS median_lag_days,
    COUNT(DISTINCT c.case_id)                                                            AS total_cases
FROM cm_case c
JOIN cm_claim cl      ON c.case_id       = cl.case_id
JOIN bm_beneficiary b ON c.beneficiary_id = b.beneficiary_id
JOIN bm_household h   ON b.household_id   = h.household_id
WHERE h.home_block_name = ?
  AND c.discharge_datetime IS NOT NULL
  AND cl.submitted_at IS NOT NULL
""",
        "param_slots": [{"name": "block", "entity_type": "block", "position": 1}],
        "result_ttl_seconds": 600,
    },

    "T243": {
        "abstract_question": "What is the concentration of scheme usage for {block} across hospitals?",
        "date_filter": {"alias": "c", "column": "admission_datetime"},
        "sql_template": """
WITH block_total AS (
    SELECT COUNT(DISTINCT c.case_id) AS total_cases
    FROM cm_case c
    JOIN bm_beneficiary b ON c.beneficiary_id = b.beneficiary_id
    JOIN bm_household h   ON b.household_id   = h.household_id
    WHERE h.home_block_name = ?
),
by_hospital AS (
    SELECT
        hosp.hospital_name,
        hosp.hospital_type,
        hosp.district_name,
        COUNT(DISTINCT c.case_id) AS case_count
    FROM cm_case c
    JOIN bm_beneficiary b ON c.beneficiary_id = b.beneficiary_id
    JOIN bm_household h   ON b.household_id   = h.household_id
    JOIN hm_hospital hosp ON c.hospital_id    = hosp.hospital_id
    WHERE h.home_block_name = ?
    GROUP BY hosp.hospital_id, hosp.hospital_name, hosp.hospital_type, hosp.district_name
)
SELECT
    bh.hospital_name,
    bh.hospital_type,
    bh.district_name,
    bh.case_count,
    ROUND(bh.case_count * 100.0 / NULLIF(bt.total_cases, 0), 1) AS share_pct
FROM by_hospital bh, block_total bt
ORDER BY bh.case_count DESC
LIMIT 15
""",
        "param_slots": [
            {"name": "block", "entity_type": "block", "position": 1},
            {"name": "block", "entity_type": "block", "position": 2},
        ],
        "result_ttl_seconds": 600,
    },

    "T244": {
        "abstract_question": "How does {block} compare with the district average on utilization, rejection rate, and settlement TAT?",
        "date_filter": {"alias": "c", "column": "admission_datetime"},
        "sql_template": """
WITH block_district AS (
    SELECT h.home_district_code AS district
    FROM bm_household h
    WHERE h.home_block_name = ?
    LIMIT 1
),
block_metrics AS (
    SELECT
        COUNT(DISTINCT c.case_id)                                                          AS block_cases,
        ROUND(AVG(CASE WHEN cl.claim_status = 'REJECTED' THEN 1.0 ELSE 0.0 END) * 100, 1) AS block_rejection_rate,
        ROUND(AVG(cl.settlement_tat_days), 1)                                              AS block_avg_tat
    FROM cm_case c
    JOIN cm_claim cl      ON c.case_id       = cl.case_id
    JOIN bm_beneficiary b ON c.beneficiary_id = b.beneficiary_id
    JOIN bm_household h   ON b.household_id   = h.household_id
    WHERE h.home_block_name = ?
),
district_metrics AS (
    SELECT
        COUNT(DISTINCT c.case_id)                                                          AS district_cases,
        ROUND(AVG(CASE WHEN cl.claim_status = 'REJECTED' THEN 1.0 ELSE 0.0 END) * 100, 1) AS district_rejection_rate,
        ROUND(AVG(cl.settlement_tat_days), 1)                                              AS district_avg_tat
    FROM cm_case c
    JOIN cm_claim cl      ON c.case_id       = cl.case_id
    JOIN bm_beneficiary b ON c.beneficiary_id = b.beneficiary_id
    JOIN bm_household h   ON b.household_id   = h.household_id
    JOIN block_district bd ON h.home_district_code = bd.district
)
SELECT
    bm.block_cases,
    dm.district_cases,
    bm.block_rejection_rate,
    dm.district_rejection_rate,
    bm.block_avg_tat,
    dm.district_avg_tat
FROM block_metrics bm, district_metrics dm
""",
        "param_slots": [
            {"name": "block", "entity_type": "block", "position": 1},
            {"name": "block", "entity_type": "block", "position": 2},
        ],
        "result_ttl_seconds": 600,
    },

    "T245": {
        "abstract_question": "How does {block} compare with the district average on public vs private treatment share?",
        "date_filter": {"alias": "c", "column": "admission_datetime"},
        "sql_template": """
WITH block_district AS (
    SELECT h.home_district_code AS district
    FROM bm_household h
    WHERE h.home_block_name = ?
    LIMIT 1
),
block_split AS (
    SELECT
        hosp.hospital_type,
        COUNT(DISTINCT c.case_id) AS case_count
    FROM cm_case c
    JOIN bm_beneficiary b ON c.beneficiary_id = b.beneficiary_id
    JOIN bm_household h   ON b.household_id   = h.household_id
    JOIN hm_hospital hosp ON c.hospital_id    = hosp.hospital_id
    WHERE h.home_block_name = ?
    GROUP BY hosp.hospital_type
),
district_split AS (
    SELECT
        hosp.hospital_type,
        COUNT(DISTINCT c.case_id) AS case_count
    FROM cm_case c
    JOIN bm_beneficiary b ON c.beneficiary_id = b.beneficiary_id
    JOIN bm_household h   ON b.household_id   = h.household_id
    JOIN hm_hospital hosp ON c.hospital_id    = hosp.hospital_id
    JOIN block_district bd ON h.home_district_code = bd.district
    GROUP BY hosp.hospital_type
),
bt AS (SELECT SUM(case_count) AS total FROM block_split),
dt AS (SELECT SUM(case_count) AS total FROM district_split)
SELECT
    COALESCE(bs.hospital_type, ds.hospital_type)              AS hospital_type,
    bs.case_count                                             AS block_cases,
    ROUND(bs.case_count * 100.0 / NULLIF(bt.total,0), 1)     AS block_pct,
    ds.case_count                                             AS district_cases,
    ROUND(ds.case_count * 100.0 / NULLIF(dt.total,0), 1)     AS district_pct
FROM block_split bs
FULL OUTER JOIN district_split ds ON bs.hospital_type = ds.hospital_type
CROSS JOIN bt CROSS JOIN dt
ORDER BY block_cases DESC NULLS LAST
""",
        "param_slots": [
            {"name": "block", "entity_type": "block", "position": 1},
            {"name": "block", "entity_type": "block", "position": 2},
        ],
        "result_ttl_seconds": 600,
    },

    "T246": {
        "abstract_question": "What share of beneficiaries in {block} are enrolled but do not yet have cards issued?",
        "date_filter": None,
        "sql_template": """
SELECT
    COUNT(DISTINCT b.beneficiary_id)                                                 AS total_enrolled,
    COUNT(DISTINCT CASE WHEN bc.card_id IS NULL THEN b.beneficiary_id END)          AS no_card,
    ROUND(
        COUNT(DISTINCT CASE WHEN bc.card_id IS NULL THEN b.beneficiary_id END)
        * 100.0 / NULLIF(COUNT(DISTINCT b.beneficiary_id), 0), 1
    )                                                                                AS no_card_pct
FROM bm_beneficiary b
JOIN bm_household h  ON b.household_id  = h.household_id
LEFT JOIN bm_card bc ON b.beneficiary_id = bc.beneficiary_id
WHERE h.home_block_name = ?
""",
        "param_slots": [{"name": "block", "entity_type": "block", "position": 1}],
        "result_ttl_seconds": 600,
    },

    "T247": {
        "abstract_question": "Which hospitals most frequently treat beneficiaries from {block} for portability cases?",
        "date_filter": {"alias": "c", "column": "admission_datetime"},
        "sql_template": """
SELECT
    hosp.hospital_name,
    hosp.hospital_type,
    hosp.district_name,
    COUNT(DISTINCT c.case_id) AS portability_cases
FROM cm_case c
JOIN bm_beneficiary b ON c.beneficiary_id = b.beneficiary_id
JOIN bm_household h   ON b.household_id   = h.household_id
JOIN hm_hospital hosp ON c.hospital_id    = hosp.hospital_id
WHERE h.home_block_name = ?
  AND c.is_portability = TRUE
GROUP BY hosp.hospital_id, hosp.hospital_name, hosp.hospital_type, hosp.district_name
ORDER BY portability_cases DESC
LIMIT 10
""",
        "param_slots": [{"name": "block", "entity_type": "block", "position": 1}],
        "result_ttl_seconds": 600,
    },

    "T248": {
        "abstract_question": "What are the top diagnosis-procedure combinations for beneficiaries from {block}?",
        "date_filter": {"alias": "c", "column": "admission_datetime"},
        "sql_template": """
SELECT
    diag.diagnosis_category,
    proc.procedure_name,
    COUNT(DISTINCT c.case_id)          AS case_count,
    ROUND(SUM(cl.amount_approved), 2)  AS total_approved
FROM cm_case c
JOIN bm_beneficiary b          ON c.beneficiary_id  = b.beneficiary_id
JOIN bm_household h            ON b.household_id    = h.household_id
JOIN cm_case_diagnosis diag    ON c.case_id          = diag.case_id
JOIN cm_preauth_request pa     ON c.case_id          = pa.case_id
JOIN cm_preauth_procedure_line pl ON pa.preauth_id   = pl.preauth_id
JOIN ref_hbp_procedure_master proc ON pl.hbp_procedure_code = proc.hbp_procedure_code
LEFT JOIN cm_claim cl          ON c.case_id          = cl.case_id
WHERE h.home_block_name = ?
  AND diag.diagnosis_type = 'PRIMARY'
GROUP BY diag.diagnosis_category, proc.procedure_name
ORDER BY total_approved DESC NULLS LAST
LIMIT 15
""",
        "param_slots": [{"name": "block", "entity_type": "block", "position": 1}],
        "result_ttl_seconds": 600,
    },

    "T249": {
        "abstract_question": "What is the duplicate-beneficiary rate in {block} by enrolment source?",
        "date_filter": None,
        "sql_template": """
SELECT
    h.entitlement_source,
    COUNT(DISTINCT b.beneficiary_id)                                                AS total_beneficiaries,
    COUNT(DISTINCT CASE WHEN b.is_duplicate = TRUE THEN b.beneficiary_id END)      AS duplicates,
    ROUND(
        COUNT(DISTINCT CASE WHEN b.is_duplicate = TRUE THEN b.beneficiary_id END)
        * 100.0 / NULLIF(COUNT(DISTINCT b.beneficiary_id), 0), 2
    )                                                                               AS duplicate_rate_pct
FROM bm_beneficiary b
JOIN bm_household h ON b.household_id = h.household_id
WHERE h.home_block_name = ?
GROUP BY h.entitlement_source
ORDER BY duplicate_rate_pct DESC
""",
        "param_slots": [{"name": "block", "entity_type": "block", "position": 1}],
        "result_ttl_seconds": 600,
    },

    "T250": {
        "abstract_question": "What is the enrolment rejection rate in {block} by authentication mode?",
        "date_filter": None,
        "sql_template": """
SELECT
    er.auth_mode,
    COUNT(*)                                                                         AS total_requests,
    COUNT(CASE WHEN er.status = 'REJECTED' THEN 1 END)                              AS rejected,
    ROUND(COUNT(CASE WHEN er.status = 'REJECTED' THEN 1 END) * 100.0 / COUNT(*), 1) AS rejection_rate_pct
FROM bm_enrolment_request er
JOIN bm_beneficiary b ON er.beneficiary_id = b.beneficiary_id
JOIN bm_household h   ON b.household_id    = h.household_id
WHERE h.home_block_name = ?
GROUP BY er.auth_mode
ORDER BY rejection_rate_pct DESC
""",
        "param_slots": [{"name": "block", "entity_type": "block", "position": 1}],
        "result_ttl_seconds": 600,
    },

    "T251": {
        "abstract_question": "What is the profile-completeness rate in {block} by entitlement source?",
        "date_filter": None,
        "sql_template": """
SELECT
    h.entitlement_source,
    COUNT(DISTINCT b.beneficiary_id)                                                              AS total_beneficiaries,
    ROUND(COUNT(DISTINCT CASE WHEN b.yob IS NOT NULL OR b.dob IS NOT NULL THEN b.beneficiary_id END) * 100.0 / NULLIF(COUNT(DISTINCT b.beneficiary_id), 0), 1) AS dob_pct,
    ROUND(COUNT(DISTINCT CASE WHEN b.mobile IS NOT NULL THEN b.beneficiary_id END) * 100.0 / NULLIF(COUNT(DISTINCT b.beneficiary_id), 0), 1)                   AS mobile_pct,
    ROUND(COUNT(DISTINCT CASE WHEN b.photo_uri IS NOT NULL THEN b.beneficiary_id END) * 100.0 / NULLIF(COUNT(DISTINCT b.beneficiary_id), 0), 1)               AS photo_pct
FROM bm_beneficiary b
JOIN bm_household h ON b.household_id = h.household_id
WHERE h.home_block_name = ?
GROUP BY h.entitlement_source
ORDER BY total_beneficiaries DESC
""",
        "param_slots": [{"name": "block", "entity_type": "block", "position": 1}],
        "result_ttl_seconds": 600,
    },

    "T252": {
        "abstract_question": "Are beneficiaries from {block} more likely to use public or private hospitals?",
        "date_filter": {"alias": "c", "column": "admission_datetime"},
        "sql_template": """
SELECT
    hosp.hospital_type,
    COUNT(DISTINCT c.case_id)                                                        AS case_count,
    ROUND(COUNT(DISTINCT c.case_id) * 100.0 / NULLIF(SUM(COUNT(DISTINCT c.case_id)) OVER(), 0), 1) AS share_pct
FROM cm_case c
JOIN bm_beneficiary b ON c.beneficiary_id = b.beneficiary_id
JOIN bm_household h   ON b.household_id   = h.household_id
JOIN hm_hospital hosp ON c.hospital_id    = hosp.hospital_id
WHERE h.home_block_name = ?
GROUP BY hosp.hospital_type
ORDER BY case_count DESC
""",
        "param_slots": [{"name": "block", "entity_type": "block", "position": 1}],
        "result_ttl_seconds": 600,
    },

    "T253": {
        "abstract_question": "Which hospitals account for the majority of total spend for beneficiaries from {block}?",
        "date_filter": {"alias": "c", "column": "admission_datetime"},
        "sql_template": """
SELECT
    hosp.hospital_name,
    hosp.hospital_type,
    hosp.district_name,
    COUNT(DISTINCT c.case_id)                  AS case_count,
    ROUND(SUM(cl.amount_approved), 2)          AS total_approved,
    ROUND(SUM(cl.amount_approved) * 100.0 / NULLIF(SUM(SUM(cl.amount_approved)) OVER(), 0), 1) AS spend_share_pct
FROM cm_case c
JOIN bm_beneficiary b ON c.beneficiary_id = b.beneficiary_id
JOIN bm_household h   ON b.household_id   = h.household_id
JOIN hm_hospital hosp ON c.hospital_id    = hosp.hospital_id
LEFT JOIN cm_claim cl ON c.case_id        = cl.case_id
WHERE h.home_block_name = ?
GROUP BY hosp.hospital_id, hosp.hospital_name, hosp.hospital_type, hosp.district_name
ORDER BY total_approved DESC NULLS LAST
LIMIT 15
""",
        "param_slots": [{"name": "block", "entity_type": "block", "position": 1}],
        "result_ttl_seconds": 600,
    },

    "T254": {
        "abstract_question": "Which hospitals account for the majority of total admissions for beneficiaries from {block}?",
        "date_filter": {"alias": "c", "column": "admission_datetime"},
        "sql_template": """
SELECT
    hosp.hospital_name,
    hosp.hospital_type,
    hosp.district_name,
    COUNT(DISTINCT c.case_id)                  AS case_count,
    ROUND(COUNT(DISTINCT c.case_id) * 100.0 / NULLIF(SUM(COUNT(DISTINCT c.case_id)) OVER(), 0), 1) AS admission_share_pct
FROM cm_case c
JOIN bm_beneficiary b ON c.beneficiary_id = b.beneficiary_id
JOIN bm_household h   ON b.household_id   = h.household_id
JOIN hm_hospital hosp ON c.hospital_id    = hosp.hospital_id
WHERE h.home_block_name = ?
GROUP BY hosp.hospital_id, hosp.hospital_name, hosp.hospital_type, hosp.district_name
ORDER BY case_count DESC
LIMIT 15
""",
        "param_slots": [{"name": "block", "entity_type": "block", "position": 1}],
        "result_ttl_seconds": 600,
    },

    # ── U. Detailed district comparison templates (T255-T283) ─────────────────

    "T255": {
        "abstract_question": "Compare the active-card rate between {district} and {district_2}?",
        "date_filter": None,
        "sql_template": """
SELECT
    h.home_district_code                                                               AS district,
    COUNT(DISTINCT b.beneficiary_id)                                                   AS total_enrolled,
    COUNT(DISTINCT CASE WHEN bc.card_status = 'ACTIVE' THEN bc.card_id END)           AS active_cards,
    ROUND(COUNT(DISTINCT CASE WHEN bc.card_status = 'ACTIVE' THEN bc.card_id END) * 100.0
        / NULLIF(COUNT(DISTINCT b.beneficiary_id), 0), 1)                             AS active_card_rate_pct
FROM bm_household h
JOIN bm_beneficiary b  ON h.household_id  = b.household_id
LEFT JOIN bm_card bc   ON b.beneficiary_id = bc.beneficiary_id
WHERE h.home_district_code IN (?, ?)
GROUP BY h.home_district_code
ORDER BY active_card_rate_pct DESC
""",
        "param_slots": [
            {"name": "district",   "entity_type": "district",   "position": 1},
            {"name": "district_2", "entity_type": "district_2", "position": 2},
        ],
        "result_ttl_seconds": 600,
    },

    "T256": {
        "abstract_question": "Compare beneficiary profile completeness between {district} and {district_2}?",
        "date_filter": None,
        "sql_template": """
SELECT
    h.home_district_code                                                                                                                        AS district,
    COUNT(DISTINCT b.beneficiary_id)                                                                                                            AS total_beneficiaries,
    ROUND(COUNT(DISTINCT CASE WHEN b.yob IS NOT NULL OR b.dob IS NOT NULL THEN b.beneficiary_id END) * 100.0 / NULLIF(COUNT(DISTINCT b.beneficiary_id),0), 1) AS dob_pct,
    ROUND(COUNT(DISTINCT CASE WHEN b.mobile IS NOT NULL THEN b.beneficiary_id END) * 100.0 / NULLIF(COUNT(DISTINCT b.beneficiary_id),0), 1)     AS mobile_pct,
    ROUND(COUNT(DISTINCT CASE WHEN b.photo_uri IS NOT NULL THEN b.beneficiary_id END) * 100.0 / NULLIF(COUNT(DISTINCT b.beneficiary_id),0), 1) AS photo_pct
FROM bm_beneficiary b
JOIN bm_household h ON b.household_id = h.household_id
WHERE h.home_district_code IN (?, ?)
GROUP BY h.home_district_code
ORDER BY dob_pct DESC
""",
        "param_slots": [
            {"name": "district",   "entity_type": "district",   "position": 1},
            {"name": "district_2", "entity_type": "district_2", "position": 2},
        ],
        "result_ttl_seconds": 600,
    },

    "T257": {
        "abstract_question": "Compare beneficiaries per empanelled hospital between {district} and {district_2}?",
        "date_filter": None,
        "sql_template": """
WITH benef AS (
    SELECT h.home_district_code AS district, COUNT(DISTINCT b.beneficiary_id) AS beneficiary_count
    FROM bm_beneficiary b JOIN bm_household h ON b.household_id = h.household_id
    WHERE h.home_district_code IN (?, ?)
    GROUP BY h.home_district_code
),
hosps AS (
    SELECT district_name AS district, COUNT(DISTINCT hospital_id) AS hospital_count
    FROM hm_hospital
    WHERE district_name IN (?, ?)
    GROUP BY district_name
)
SELECT
    b.district,
    b.beneficiary_count,
    COALESCE(h.hospital_count, 0)                                                        AS hospital_count,
    ROUND(b.beneficiary_count * 1.0 / NULLIF(COALESCE(h.hospital_count, 0), 0), 1)     AS beneficiaries_per_hospital
FROM benef b
LEFT JOIN hosps h ON b.district = h.district
ORDER BY beneficiaries_per_hospital DESC
""",
        "param_slots": [
            {"name": "district",   "entity_type": "district",   "position": 1},
            {"name": "district_2", "entity_type": "district_2", "position": 2},
            {"name": "district",   "entity_type": "district",   "position": 3},
            {"name": "district_2", "entity_type": "district_2", "position": 4},
        ],
        "result_ttl_seconds": 600,
    },

    "T258": {
        "abstract_question": "Compare bed capacity per 1,000 enrolled beneficiaries between {district} and {district_2}?",
        "date_filter": None,
        "sql_template": """
WITH benef AS (
    SELECT h.home_district_code AS district, COUNT(DISTINCT b.beneficiary_id) AS beneficiary_count
    FROM bm_beneficiary b JOIN bm_household h ON b.household_id = h.household_id
    WHERE h.home_district_code IN (?, ?)
    GROUP BY h.home_district_code
),
beds AS (
    SELECT district_name AS district, SUM(total_bed_strength) AS total_beds
    FROM hm_hospital
    WHERE district_name IN (?, ?)
    GROUP BY district_name
)
SELECT
    b.district,
    b.beneficiary_count,
    COALESCE(bd.total_beds, 0)                                                          AS total_beds,
    ROUND(COALESCE(bd.total_beds, 0) * 1000.0 / NULLIF(b.beneficiary_count, 0), 1)    AS beds_per_1000_enrolled
FROM benef b
LEFT JOIN beds bd ON b.district = bd.district
ORDER BY beds_per_1000_enrolled DESC
""",
        "param_slots": [
            {"name": "district",   "entity_type": "district",   "position": 1},
            {"name": "district_2", "entity_type": "district_2", "position": 2},
            {"name": "district",   "entity_type": "district",   "position": 3},
            {"name": "district_2", "entity_type": "district_2", "position": 4},
        ],
        "result_ttl_seconds": 600,
    },

    "T259": {
        "abstract_question": "Compare case rates per 1,000 enrolled beneficiaries between {district} and {district_2}?",
        "date_filter": {"alias": "c", "column": "admission_datetime"},
        "sql_template": """
WITH cases AS (
    SELECT c.hospital_district AS district, COUNT(DISTINCT c.case_id) AS case_count
    FROM cm_case c
    WHERE c.hospital_district IN (?, ?)
    GROUP BY c.hospital_district
),
benef AS (
    SELECT h.home_district_code AS district, COUNT(DISTINCT b.beneficiary_id) AS beneficiary_count
    FROM bm_beneficiary b JOIN bm_household h ON b.household_id = h.household_id
    WHERE h.home_district_code IN (?, ?)
    GROUP BY h.home_district_code
)
SELECT
    COALESCE(c.district, b.district)                                                AS district,
    COALESCE(c.case_count, 0)                                                       AS case_count,
    COALESCE(b.beneficiary_count, 0)                                                AS beneficiary_count,
    ROUND(COALESCE(c.case_count, 0) * 1000.0 / NULLIF(b.beneficiary_count, 0), 1)  AS cases_per_1000
FROM cases c
FULL OUTER JOIN benef b ON c.district = b.district
ORDER BY cases_per_1000 DESC
""",
        "param_slots": [
            {"name": "district",   "entity_type": "district",   "position": 1},
            {"name": "district_2", "entity_type": "district_2", "position": 2},
            {"name": "district",   "entity_type": "district",   "position": 3},
            {"name": "district_2", "entity_type": "district_2", "position": 4},
        ],
        "result_ttl_seconds": 600,
    },

    "T260": {
        "abstract_question": "Compare card issuance within 30 days between {district} and {district_2}?",
        "date_filter": None,
        "sql_template": """
SELECT
    h.home_district_code                                                                 AS district,
    COUNT(DISTINCT er.beneficiary_id)                                                    AS total_enrolments,
    COUNT(DISTINCT CASE WHEN DATE_DIFF('day', er.submitted_at::DATE, bc.issued_at::DATE) <= 30 THEN er.beneficiary_id END) AS issued_within_30d,
    ROUND(COUNT(DISTINCT CASE WHEN DATE_DIFF('day', er.submitted_at::DATE, bc.issued_at::DATE) <= 30 THEN er.beneficiary_id END)
        * 100.0 / NULLIF(COUNT(DISTINCT er.beneficiary_id), 0), 1)                     AS pct_within_30d
FROM bm_enrolment_request er
JOIN bm_beneficiary b   ON er.beneficiary_id = b.beneficiary_id
JOIN bm_household h     ON b.household_id    = h.household_id
LEFT JOIN bm_card bc    ON er.beneficiary_id = bc.beneficiary_id
WHERE h.home_district_code IN (?, ?)
GROUP BY h.home_district_code
ORDER BY pct_within_30d DESC
""",
        "param_slots": [
            {"name": "district",   "entity_type": "district",   "position": 1},
            {"name": "district_2", "entity_type": "district_2", "position": 2},
        ],
        "result_ttl_seconds": 600,
    },

    "T261": {
        "abstract_question": "Compare the share of claimants admitted within 30 days of enrolment between {district} and {district_2}?",
        "date_filter": None,
        "sql_template": """
WITH first_enrolment AS (
    SELECT beneficiary_id, MIN(submitted_at)::DATE AS first_enrolment_date
    FROM bm_enrolment_request
    GROUP BY beneficiary_id
),
first_admission AS (
    SELECT beneficiary_id, MIN(admission_datetime)::DATE AS first_admission_date
    FROM cm_case
    GROUP BY beneficiary_id
)
SELECT
    h.home_district_code                                                                         AS district,
    COUNT(DISTINCT b.beneficiary_id)                                                             AS ever_admitted,
    COUNT(DISTINCT CASE WHEN DATE_DIFF('day', fe.first_enrolment_date, fa.first_admission_date) <= 30 THEN b.beneficiary_id END) AS admitted_within_30d,
    ROUND(COUNT(DISTINCT CASE WHEN DATE_DIFF('day', fe.first_enrolment_date, fa.first_admission_date) <= 30 THEN b.beneficiary_id END)
        * 100.0 / NULLIF(COUNT(DISTINCT b.beneficiary_id), 0), 1)                              AS pct_within_30d
FROM bm_beneficiary b
JOIN bm_household h        ON b.household_id   = h.household_id
JOIN first_enrolment fe    ON b.beneficiary_id = fe.beneficiary_id
JOIN first_admission fa    ON b.beneficiary_id = fa.beneficiary_id
WHERE h.home_district_code IN (?, ?)
GROUP BY h.home_district_code
ORDER BY pct_within_30d DESC
""",
        "param_slots": [
            {"name": "district",   "entity_type": "district",   "position": 1},
            {"name": "district_2", "entity_type": "district_2", "position": 2},
        ],
        "result_ttl_seconds": 600,
    },

    "T262": {
        "abstract_question": "Compare out-of-district treatment share between {district} and {district_2}?",
        "date_filter": {"alias": "c", "column": "admission_datetime"},
        "sql_template": """
SELECT
    h.home_district_code                                                                                                            AS home_district,
    COUNT(DISTINCT c.case_id)                                                                                                       AS total_cases,
    COUNT(DISTINCT CASE WHEN c.hospital_district != h.home_district_code THEN c.case_id END)                                       AS out_of_district,
    ROUND(COUNT(DISTINCT CASE WHEN c.hospital_district != h.home_district_code THEN c.case_id END) * 100.0 / NULLIF(COUNT(DISTINCT c.case_id),0), 1) AS out_of_district_pct
FROM cm_case c
JOIN bm_beneficiary b ON c.beneficiary_id = b.beneficiary_id
JOIN bm_household h   ON b.household_id   = h.household_id
WHERE h.home_district_code IN (?, ?)
GROUP BY h.home_district_code
ORDER BY out_of_district_pct DESC
""",
        "param_slots": [
            {"name": "district",   "entity_type": "district",   "position": 1},
            {"name": "district_2", "entity_type": "district_2", "position": 2},
        ],
        "result_ttl_seconds": 600,
    },

    "T263": {
        "abstract_question": "Compare net patient inflow/outflow between {district} and {district_2}?",
        "date_filter": {"alias": "c", "column": "admission_datetime"},
        "sql_template": """
WITH flows AS (
    SELECT
        h.home_district_code   AS home_district,
        c.hospital_district    AS treat_district,
        COUNT(DISTINCT c.case_id) AS case_count
    FROM cm_case c
    JOIN bm_beneficiary b ON c.beneficiary_id = b.beneficiary_id
    JOIN bm_household h   ON b.household_id   = h.household_id
    WHERE h.home_district_code IN (?, ?) OR c.hospital_district IN (?, ?)
    GROUP BY h.home_district_code, c.hospital_district
),
inflows AS (
    SELECT treat_district AS district, SUM(case_count) AS inflow
    FROM flows WHERE home_district != treat_district AND treat_district IN (?, ?)
    GROUP BY treat_district
),
outflows AS (
    SELECT home_district AS district, SUM(case_count) AS outflow
    FROM flows WHERE home_district != treat_district AND home_district IN (?, ?)
    GROUP BY home_district
)
SELECT
    COALESCE(i.district, o.district)  AS district,
    COALESCE(i.inflow, 0)             AS patient_inflow,
    COALESCE(o.outflow, 0)            AS patient_outflow,
    COALESCE(i.inflow, 0) - COALESCE(o.outflow, 0) AS net_flow
FROM inflows i
FULL OUTER JOIN outflows o ON i.district = o.district
ORDER BY net_flow DESC
""",
        "param_slots": [
            {"name": "district",   "entity_type": "district",   "position": 1},
            {"name": "district_2", "entity_type": "district_2", "position": 2},
            {"name": "district",   "entity_type": "district",   "position": 3},
            {"name": "district_2", "entity_type": "district_2", "position": 4},
            {"name": "district",   "entity_type": "district",   "position": 5},
            {"name": "district_2", "entity_type": "district_2", "position": 6},
            {"name": "district",   "entity_type": "district",   "position": 7},
            {"name": "district_2", "entity_type": "district_2", "position": 8},
        ],
        "result_ttl_seconds": 600,
    },

    "T264": {
        "abstract_question": "Compare dependence on top 5 hospitals between {district} and {district_2}?",
        "date_filter": {"alias": "c", "column": "admission_datetime"},
        "sql_template": """
WITH district_totals AS (
    SELECT hospital_district AS district, COUNT(DISTINCT case_id) AS total_cases
    FROM cm_case WHERE hospital_district IN (?, ?)
    GROUP BY hospital_district
),
hospital_cases AS (
    SELECT
        c.hospital_district AS district,
        c.hospital_id,
        COUNT(DISTINCT c.case_id) AS case_count,
        ROW_NUMBER() OVER (PARTITION BY c.hospital_district ORDER BY COUNT(DISTINCT c.case_id) DESC) AS rn
    FROM cm_case c
    WHERE c.hospital_district IN (?, ?)
    GROUP BY c.hospital_district, c.hospital_id
)
SELECT
    hc.district,
    dt.total_cases,
    SUM(hc.case_count)                                                              AS top5_cases,
    ROUND(SUM(hc.case_count) * 100.0 / NULLIF(dt.total_cases, 0), 1)              AS top5_share_pct
FROM hospital_cases hc
JOIN district_totals dt ON hc.district = dt.district
WHERE hc.rn <= 5
GROUP BY hc.district, dt.total_cases
ORDER BY top5_share_pct DESC
""",
        "param_slots": [
            {"name": "district",   "entity_type": "district",   "position": 1},
            {"name": "district_2", "entity_type": "district_2", "position": 2},
            {"name": "district",   "entity_type": "district",   "position": 3},
            {"name": "district_2", "entity_type": "district_2", "position": 4},
        ],
        "result_ttl_seconds": 600,
    },

    "T265": {
        "abstract_question": "Compare portability destination patterns between {district} and {district_2}?",
        "date_filter": {"alias": "c", "column": "admission_datetime"},
        "sql_template": """
SELECT
    h.home_district_code                       AS home_district,
    c.hospital_division                        AS destination_division,
    COUNT(DISTINCT c.case_id)                  AS portability_cases,
    ROUND(SUM(cl.amount_approved), 2)          AS total_approved
FROM cm_case c
JOIN bm_beneficiary b ON c.beneficiary_id = b.beneficiary_id
JOIN bm_household h   ON b.household_id   = h.household_id
LEFT JOIN cm_claim cl ON c.case_id        = cl.case_id
WHERE h.home_district_code IN (?, ?)
  AND c.is_portability = TRUE
GROUP BY h.home_district_code, c.hospital_division
ORDER BY home_district, portability_cases DESC
""",
        "param_slots": [
            {"name": "district",   "entity_type": "district",   "position": 1},
            {"name": "district_2", "entity_type": "district_2", "position": 2},
        ],
        "result_ttl_seconds": 600,
    },

    "T266": {
        "abstract_question": "Compare public vs private treatment share by specialty between {district} and {district_2}?",
        "date_filter": {"alias": "c", "column": "admission_datetime"},
        "sql_template": """
SELECT
    c.hospital_district,
    hosp.hospital_type,
    proc.specialty_code,
    COUNT(DISTINCT c.case_id) AS case_count
FROM cm_case c
JOIN hm_hospital hosp                     ON c.hospital_id  = hosp.hospital_id
JOIN cm_preauth_request pa                ON c.case_id      = pa.case_id
JOIN cm_preauth_procedure_line pl         ON pa.preauth_id  = pl.preauth_id
JOIN ref_hbp_procedure_master proc        ON pl.hbp_procedure_code = proc.hbp_procedure_code
WHERE c.hospital_district IN (?, ?)
GROUP BY c.hospital_district, hosp.hospital_type, proc.specialty_code
ORDER BY c.hospital_district, proc.specialty_code, case_count DESC
""",
        "param_slots": [
            {"name": "district",   "entity_type": "district",   "position": 1},
            {"name": "district_2", "entity_type": "district_2", "position": 2},
        ],
        "result_ttl_seconds": 600,
    },

    "T267": {
        "abstract_question": "Compare maternal/neonatal case rates between {district} and {district_2}?",
        "date_filter": {"alias": "c", "column": "admission_datetime"},
        "sql_template": """
WITH maternal AS (
    SELECT c.hospital_district AS district, COUNT(DISTINCT c.case_id) AS case_count
    FROM cm_case c JOIN cm_case_diagnosis d ON c.case_id = d.case_id
    WHERE c.hospital_district IN (?, ?) AND d.diagnosis_category = 'MATERNAL_NEONATAL' AND d.diagnosis_type = 'PRIMARY'
    GROUP BY c.hospital_district
),
enrolled_women AS (
    SELECT h.home_district_code AS district, COUNT(DISTINCT b.beneficiary_id) AS enrolled_count
    FROM bm_beneficiary b JOIN bm_household h ON b.household_id = h.household_id
    WHERE h.home_district_code IN (?, ?) AND b.gender = 'FEMALE'
    GROUP BY h.home_district_code
)
SELECT
    m.district,
    m.case_count AS maternal_cases,
    e.enrolled_count AS enrolled_women,
    ROUND(m.case_count * 1000.0 / NULLIF(e.enrolled_count, 0), 2) AS rate_per_1000_women
FROM maternal m LEFT JOIN enrolled_women e ON m.district = e.district
ORDER BY rate_per_1000_women DESC
""",
        "param_slots": [
            {"name": "district",   "entity_type": "district",   "position": 1},
            {"name": "district_2", "entity_type": "district_2", "position": 2},
            {"name": "district",   "entity_type": "district",   "position": 3},
            {"name": "district_2", "entity_type": "district_2", "position": 4},
        ],
        "result_ttl_seconds": 600,
    },

    "T268": {
        "abstract_question": "Compare NCD case rates between {district} and {district_2}?",
        "date_filter": {"alias": "c", "column": "admission_datetime"},
        "sql_template": """
WITH ncd AS (
    SELECT c.hospital_district AS district, COUNT(DISTINCT c.case_id) AS case_count
    FROM cm_case c JOIN cm_case_diagnosis d ON c.case_id = d.case_id
    WHERE c.hospital_district IN (?, ?) AND d.diagnosis_category = 'NCD' AND d.diagnosis_type = 'PRIMARY'
    GROUP BY c.hospital_district
),
enrolled AS (
    SELECT h.home_district_code AS district, COUNT(DISTINCT b.beneficiary_id) AS enrolled_count
    FROM bm_beneficiary b JOIN bm_household h ON b.household_id = h.household_id
    WHERE h.home_district_code IN (?, ?)
    GROUP BY h.home_district_code
)
SELECT
    n.district,
    n.case_count AS ncd_cases,
    e.enrolled_count,
    ROUND(n.case_count * 1000.0 / NULLIF(e.enrolled_count, 0), 2) AS rate_per_1000_enrolled
FROM ncd n LEFT JOIN enrolled e ON n.district = e.district
ORDER BY rate_per_1000_enrolled DESC
""",
        "param_slots": [
            {"name": "district",   "entity_type": "district",   "position": 1},
            {"name": "district_2", "entity_type": "district_2", "position": 2},
            {"name": "district",   "entity_type": "district",   "position": 3},
            {"name": "district_2", "entity_type": "district_2", "position": 4},
        ],
        "result_ttl_seconds": 600,
    },

    "T269": {
        "abstract_question": "Compare communicable disease case rates between {district} and {district_2}?",
        "date_filter": {"alias": "c", "column": "admission_datetime"},
        "sql_template": """
WITH comm AS (
    SELECT c.hospital_district AS district, COUNT(DISTINCT c.case_id) AS case_count
    FROM cm_case c JOIN cm_case_diagnosis d ON c.case_id = d.case_id
    WHERE c.hospital_district IN (?, ?) AND d.diagnosis_category = 'COMMUNICABLE' AND d.diagnosis_type = 'PRIMARY'
    GROUP BY c.hospital_district
),
enrolled AS (
    SELECT h.home_district_code AS district, COUNT(DISTINCT b.beneficiary_id) AS enrolled_count
    FROM bm_beneficiary b JOIN bm_household h ON b.household_id = h.household_id
    WHERE h.home_district_code IN (?, ?)
    GROUP BY h.home_district_code
)
SELECT
    c.district,
    c.case_count AS communicable_cases,
    e.enrolled_count,
    ROUND(c.case_count * 1000.0 / NULLIF(e.enrolled_count, 0), 2) AS rate_per_1000_enrolled
FROM comm c LEFT JOIN enrolled e ON c.district = e.district
ORDER BY rate_per_1000_enrolled DESC
""",
        "param_slots": [
            {"name": "district",   "entity_type": "district",   "position": 1},
            {"name": "district_2", "entity_type": "district_2", "position": 2},
            {"name": "district",   "entity_type": "district",   "position": 3},
            {"name": "district_2", "entity_type": "district_2", "position": 4},
        ],
        "result_ttl_seconds": 600,
    },

    "T270": {
        "abstract_question": "Compare duplicate-beneficiary rates between {district} and {district_2}?",
        "date_filter": None,
        "sql_template": """
SELECT
    h.home_district_code                                                                          AS district,
    COUNT(DISTINCT b.beneficiary_id)                                                              AS total_beneficiaries,
    COUNT(DISTINCT CASE WHEN b.is_duplicate = TRUE THEN b.beneficiary_id END)                    AS duplicates,
    ROUND(COUNT(DISTINCT CASE WHEN b.is_duplicate = TRUE THEN b.beneficiary_id END) * 100.0
        / NULLIF(COUNT(DISTINCT b.beneficiary_id), 0), 2)                                        AS duplicate_rate_pct
FROM bm_beneficiary b
JOIN bm_household h ON b.household_id = h.household_id
WHERE h.home_district_code IN (?, ?)
GROUP BY h.home_district_code
ORDER BY duplicate_rate_pct DESC
""",
        "param_slots": [
            {"name": "district",   "entity_type": "district",   "position": 1},
            {"name": "district_2", "entity_type": "district_2", "position": 2},
        ],
        "result_ttl_seconds": 600,
    },

    "T271": {
        "abstract_question": "Compare enrolment rejection rates by authentication mode between {district} and {district_2}?",
        "date_filter": None,
        "sql_template": """
SELECT
    h.home_district_code                                                                          AS district,
    er.auth_mode,
    COUNT(*)                                                                                      AS total_requests,
    COUNT(CASE WHEN er.status = 'REJECTED' THEN 1 END)                                           AS rejected,
    ROUND(COUNT(CASE WHEN er.status = 'REJECTED' THEN 1 END) * 100.0 / COUNT(*), 1)             AS rejection_rate_pct
FROM bm_enrolment_request er
JOIN bm_beneficiary b ON er.beneficiary_id = b.beneficiary_id
JOIN bm_household h   ON b.household_id    = h.household_id
WHERE h.home_district_code IN (?, ?)
GROUP BY h.home_district_code, er.auth_mode
ORDER BY district, rejection_rate_pct DESC
""",
        "param_slots": [
            {"name": "district",   "entity_type": "district",   "position": 1},
            {"name": "district_2", "entity_type": "district_2", "position": 2},
        ],
        "result_ttl_seconds": 600,
    },

    "T272": {
        "abstract_question": "Compare profile-completeness rates between {district} and {district_2}?",
        "date_filter": None,
        "sql_template": """
SELECT
    h.home_district_code                                                                                                                         AS district,
    COUNT(DISTINCT b.beneficiary_id)                                                                                                             AS total_beneficiaries,
    ROUND(COUNT(DISTINCT CASE WHEN b.yob IS NOT NULL OR b.dob IS NOT NULL THEN b.beneficiary_id END) * 100.0 / NULLIF(COUNT(DISTINCT b.beneficiary_id),0), 1) AS dob_pct,
    ROUND(COUNT(DISTINCT CASE WHEN b.mobile IS NOT NULL THEN b.beneficiary_id END) * 100.0 / NULLIF(COUNT(DISTINCT b.beneficiary_id),0), 1)      AS mobile_pct,
    ROUND(COUNT(DISTINCT CASE WHEN b.photo_uri IS NOT NULL THEN b.beneficiary_id END) * 100.0 / NULLIF(COUNT(DISTINCT b.beneficiary_id),0), 1)  AS photo_pct
FROM bm_beneficiary b
JOIN bm_household h ON b.household_id = h.household_id
WHERE h.home_district_code IN (?, ?)
GROUP BY h.home_district_code
ORDER BY dob_pct DESC
""",
        "param_slots": [
            {"name": "district",   "entity_type": "district",   "position": 1},
            {"name": "district_2", "entity_type": "district_2", "position": 2},
        ],
        "result_ttl_seconds": 600,
    },

    "T273": {
        "abstract_question": "Compare average claim haircuts between {district} and {district_2}?",
        "date_filter": {"alias": "c", "column": "admission_datetime"},
        "sql_template": """
SELECT
    c.hospital_district                                                                        AS district,
    ROUND(AVG((cl.amount_claimed - cl.amount_approved) / NULLIF(cl.amount_claimed, 0) * 100), 1) AS avg_haircut_pct,
    ROUND(SUM(cl.amount_claimed), 2)                                                           AS total_claimed,
    ROUND(SUM(cl.amount_approved), 2)                                                          AS total_approved,
    ROUND(SUM(cl.amount_claimed - cl.amount_approved), 2)                                      AS total_haircut
FROM cm_claim cl
JOIN cm_case c ON cl.case_id = c.case_id
WHERE c.hospital_district IN (?, ?)
GROUP BY c.hospital_district
ORDER BY avg_haircut_pct DESC
""",
        "param_slots": [
            {"name": "district",   "entity_type": "district",   "position": 1},
            {"name": "district_2", "entity_type": "district_2", "position": 2},
        ],
        "result_ttl_seconds": 600,
    },

    "T274": {
        "abstract_question": "Compare failed-payment amounts between {district} and {district_2}?",
        "date_filter": None,
        "sql_template": """
SELECT
    c.hospital_district                              AS district,
    COUNT(DISTINCT p.payment_id)                     AS failed_payments,
    ROUND(SUM(p.amount_paid), 2)                     AS failed_amount
FROM cm_payment p
JOIN cm_claim cl  ON p.claim_id   = cl.claim_id
JOIN cm_case c    ON cl.case_id   = c.case_id
WHERE p.payment_status = 'FAILED'
  AND c.hospital_district IN (?, ?)
GROUP BY c.hospital_district
ORDER BY failed_amount DESC
""",
        "param_slots": [
            {"name": "district",   "entity_type": "district",   "position": 1},
            {"name": "district_2", "entity_type": "district_2", "position": 2},
        ],
        "result_ttl_seconds": 600,
    },

    "T275": {
        "abstract_question": "Compare diagnosis-package mismatch rates between {district} and {district_2}?",
        "date_filter": None,
        "sql_template": """
SELECT
    c.hospital_district                                                                   AS district,
    COUNT(DISTINCT cl.claim_id)                                                           AS total_claims,
    COUNT(DISTINCT CASE WHEN ae.reason_category ILIKE '%mismatch%' OR ae.reason_category ILIKE '%diagnosis%' THEN cl.claim_id END) AS mismatch_queries,
    ROUND(COUNT(DISTINCT CASE WHEN ae.reason_category ILIKE '%mismatch%' OR ae.reason_category ILIKE '%diagnosis%' THEN cl.claim_id END)
        * 100.0 / NULLIF(COUNT(DISTINCT cl.claim_id), 0), 2)                            AS mismatch_rate_pct
FROM cm_claim cl
JOIN cm_case c ON cl.case_id = c.case_id
LEFT JOIN cm_adjudication_event ae ON cl.claim_id = ae.claim_id
WHERE c.hospital_district IN (?, ?)
GROUP BY c.hospital_district
ORDER BY mismatch_rate_pct DESC
""",
        "param_slots": [
            {"name": "district",   "entity_type": "district",   "position": 1},
            {"name": "district_2", "entity_type": "district_2", "position": 2},
        ],
        "result_ttl_seconds": 600,
    },

    "T276": {
        "abstract_question": "Compare missing-document query rates between {district} and {district_2}?",
        "date_filter": {"alias": "c", "column": "admission_datetime"},
        "sql_template": """
SELECT
    c.hospital_district                                                                   AS district,
    COUNT(DISTINCT cl.claim_id)                                                           AS total_claims,
    COUNT(DISTINCT CASE WHEN cl.claim_status = 'QUERY_RAISED' THEN cl.claim_id END)      AS query_raised,
    ROUND(COUNT(DISTINCT CASE WHEN cl.claim_status = 'QUERY_RAISED' THEN cl.claim_id END)
        * 100.0 / NULLIF(COUNT(DISTINCT cl.claim_id), 0), 1)                             AS query_rate_pct
FROM cm_claim cl
JOIN cm_case c ON cl.case_id = c.case_id
WHERE c.hospital_district IN (?, ?)
GROUP BY c.hospital_district
ORDER BY query_rate_pct DESC
""",
        "param_slots": [
            {"name": "district",   "entity_type": "district",   "position": 1},
            {"name": "district_2", "entity_type": "district_2", "position": 2},
        ],
        "result_ttl_seconds": 600,
    },

    "T277": {
        "abstract_question": "Compare readmission rates between {district} and {district_2}?",
        "date_filter": {"alias": "c", "column": "admission_datetime"},
        "sql_template": """
WITH admissions AS (
    SELECT
        c.case_id,
        c.beneficiary_id,
        c.hospital_district,
        c.admission_datetime::DATE AS admit_date,
        c.discharge_datetime::DATE AS discharge_date,
        LAG(c.discharge_datetime::DATE) OVER (
            PARTITION BY c.beneficiary_id, c.hospital_district
            ORDER BY c.admission_datetime
        ) AS prev_discharge
    FROM cm_case c
    WHERE c.hospital_district IN (?, ?)
)
SELECT
    hospital_district                                                                              AS district,
    COUNT(DISTINCT case_id)                                                                        AS total_cases,
    COUNT(DISTINCT CASE WHEN DATE_DIFF('day', prev_discharge, admit_date) <= 30 THEN case_id END) AS readmissions,
    ROUND(COUNT(DISTINCT CASE WHEN DATE_DIFF('day', prev_discharge, admit_date) <= 30 THEN case_id END) * 100.0
        / NULLIF(COUNT(DISTINCT case_id), 0), 2)                                                  AS readmission_rate_pct
FROM admissions
GROUP BY hospital_district
ORDER BY readmission_rate_pct DESC
""",
        "param_slots": [
            {"name": "district",   "entity_type": "district",   "position": 1},
            {"name": "district_2", "entity_type": "district_2", "position": 2},
        ],
        "result_ttl_seconds": 600,
    },

    "T278": {
        "abstract_question": "Compare biometric-authentication rates at discharge between {district} and {district_2}?",
        "date_filter": None,
        "sql_template": """
SELECT
    c.hospital_district                                                                          AS district,
    COUNT(DISTINCT d.discharge_id)                                                               AS total_discharges,
    COUNT(DISTINCT CASE WHEN d.biometric_auth_used = TRUE THEN d.discharge_id END)              AS biometric_auths,
    ROUND(COUNT(DISTINCT CASE WHEN d.biometric_auth_used = TRUE THEN d.discharge_id END) * 100.0
        / NULLIF(COUNT(DISTINCT d.discharge_id), 0), 1)                                         AS biometric_rate_pct
FROM cm_discharge d
JOIN cm_case c ON d.case_id = c.case_id
WHERE c.hospital_district IN (?, ?)
GROUP BY c.hospital_district
ORDER BY biometric_rate_pct DESC
""",
        "param_slots": [
            {"name": "district",   "entity_type": "district",   "position": 1},
            {"name": "district_2", "entity_type": "district_2", "position": 2},
        ],
        "result_ttl_seconds": 600,
    },

    "T279": {
        "abstract_question": "Compare medicine-provision rates at discharge between {district} and {district_2}?",
        "date_filter": None,
        "sql_template": """
SELECT
    c.hospital_district                                                                          AS district,
    COUNT(DISTINCT d.discharge_id)                                                               AS total_discharges,
    COUNT(DISTINCT CASE WHEN d.provided_medicines_flag = TRUE THEN d.discharge_id END)          AS medicine_provided,
    ROUND(COUNT(DISTINCT CASE WHEN d.provided_medicines_flag = TRUE THEN d.discharge_id END) * 100.0
        / NULLIF(COUNT(DISTINCT d.discharge_id), 0), 1)                                         AS medicine_provision_rate_pct
FROM cm_discharge d
JOIN cm_case c ON d.case_id = c.case_id
WHERE c.hospital_district IN (?, ?)
GROUP BY c.hospital_district
ORDER BY medicine_provision_rate_pct DESC
""",
        "param_slots": [
            {"name": "district",   "entity_type": "district",   "position": 1},
            {"name": "district_2", "entity_type": "district_2", "position": 2},
        ],
        "result_ttl_seconds": 600,
    },

    "T280": {
        "abstract_question": "Compare the concentration of scheme expenditure between {district} and {district_2}?",
        "date_filter": {"alias": "c", "column": "admission_datetime"},
        "sql_template": """
WITH district_totals AS (
    SELECT c.hospital_district AS district, SUM(cl.amount_approved) AS total_spend
    FROM cm_case c JOIN cm_claim cl ON c.case_id = cl.case_id
    WHERE c.hospital_district IN (?, ?)
    GROUP BY c.hospital_district
),
hospital_spend AS (
    SELECT
        c.hospital_district AS district,
        c.hospital_id,
        SUM(cl.amount_approved) AS hosp_spend,
        ROW_NUMBER() OVER (PARTITION BY c.hospital_district ORDER BY SUM(cl.amount_approved) DESC) AS rn
    FROM cm_case c JOIN cm_claim cl ON c.case_id = cl.case_id
    WHERE c.hospital_district IN (?, ?)
    GROUP BY c.hospital_district, c.hospital_id
)
SELECT
    hs.district,
    dt.total_spend,
    SUM(CASE WHEN hs.rn = 1 THEN hs.hosp_spend END)                              AS top1_spend,
    SUM(CASE WHEN hs.rn <= 3 THEN hs.hosp_spend END)                             AS top3_spend,
    SUM(CASE WHEN hs.rn <= 5 THEN hs.hosp_spend END)                             AS top5_spend,
    ROUND(SUM(CASE WHEN hs.rn <= 5 THEN hs.hosp_spend END) * 100.0 / NULLIF(dt.total_spend,0), 1) AS top5_share_pct
FROM hospital_spend hs
JOIN district_totals dt ON hs.district = dt.district
GROUP BY hs.district, dt.total_spend
ORDER BY top5_share_pct DESC
""",
        "param_slots": [
            {"name": "district",   "entity_type": "district",   "position": 1},
            {"name": "district_2", "entity_type": "district_2", "position": 2},
            {"name": "district",   "entity_type": "district",   "position": 3},
            {"name": "district_2", "entity_type": "district_2", "position": 4},
        ],
        "result_ttl_seconds": 600,
    },

    "T281": {
        "abstract_question": "Compare mortality by diagnosis category between {district} and {district_2}?",
        "date_filter": None,
        "sql_template": """
SELECT
    c.hospital_district                                                             AS district,
    diag.diagnosis_category,
    COUNT(DISTINCT c.case_id)                                                       AS total_cases,
    COUNT(DISTINCT CASE WHEN d.death_date IS NOT NULL THEN c.case_id END)          AS deaths,
    ROUND(COUNT(DISTINCT CASE WHEN d.death_date IS NOT NULL THEN c.case_id END) * 100.0
        / NULLIF(COUNT(DISTINCT c.case_id), 0), 2)                                 AS mortality_rate_pct
FROM cm_case c
JOIN cm_discharge d        ON c.case_id = d.case_id
JOIN cm_case_diagnosis diag ON c.case_id = diag.case_id
WHERE c.hospital_district IN (?, ?)
  AND diag.diagnosis_type = 'PRIMARY'
GROUP BY c.hospital_district, diag.diagnosis_category
ORDER BY c.hospital_district, mortality_rate_pct DESC
""",
        "param_slots": [
            {"name": "district",   "entity_type": "district",   "position": 1},
            {"name": "district_2", "entity_type": "district_2", "position": 2},
        ],
        "result_ttl_seconds": 600,
    },

    "T282": {
        "abstract_question": "Compare average length of stay by diagnosis category between {district} and {district_2}?",
        "date_filter": {"alias": "c", "column": "admission_datetime"},
        "sql_template": """
SELECT
    c.hospital_district                                                                          AS district,
    diag.diagnosis_category,
    COUNT(DISTINCT c.case_id)                                                                    AS case_count,
    ROUND(AVG(DATE_DIFF('day', c.admission_datetime::DATE, c.discharge_datetime::DATE)), 1)     AS avg_los_days
FROM cm_case c
JOIN cm_case_diagnosis diag ON c.case_id = diag.case_id
WHERE c.hospital_district IN (?, ?)
  AND c.discharge_datetime IS NOT NULL
  AND diag.diagnosis_type = 'PRIMARY'
GROUP BY c.hospital_district, diag.diagnosis_category
ORDER BY c.hospital_district, avg_los_days DESC
""",
        "param_slots": [
            {"name": "district",   "entity_type": "district",   "position": 1},
            {"name": "district_2", "entity_type": "district_2", "position": 2},
        ],
        "result_ttl_seconds": 600,
    },

    "T283": {
        "abstract_question": "Compare procedure mix in public vs private hospitals between {district} and {district_2}?",
        "date_filter": {"alias": "c", "column": "admission_datetime"},
        "sql_template": """
SELECT
    c.hospital_district                         AS district,
    hosp.hospital_type,
    proc.specialty_code,
    proc.procedure_name,
    COUNT(DISTINCT c.case_id)                   AS case_count
FROM cm_case c
JOIN hm_hospital hosp                  ON c.hospital_id          = hosp.hospital_id
JOIN cm_preauth_request pa             ON c.case_id              = pa.case_id
JOIN cm_preauth_procedure_line pl      ON pa.preauth_id          = pl.preauth_id
JOIN ref_hbp_procedure_master proc     ON pl.hbp_procedure_code  = proc.hbp_procedure_code
WHERE c.hospital_district IN (?, ?)
GROUP BY c.hospital_district, hosp.hospital_type, proc.specialty_code, proc.procedure_name
ORDER BY c.hospital_district, hosp.hospital_type, case_count DESC
""",
        "param_slots": [
            {"name": "district",   "entity_type": "district",   "position": 1},
            {"name": "district_2", "entity_type": "district_2", "position": 2},
        ],
        "result_ttl_seconds": 600,
    },

    # ── V. District ranking / composite templates (T284-T291) ────────────────

    "T284": {
        "abstract_question": "Where does {district} rank statewide on utilization, approval rate, rejection rate, and settlement TAT?",
        "date_filter": {"alias": "c", "column": "admission_datetime"},
        "sql_template": """
WITH district_metrics AS (
    SELECT
        c.hospital_district                                                               AS district,
        COUNT(DISTINCT c.case_id)                                                         AS total_cases,
        ROUND(AVG(CASE WHEN cl.claim_status IN ('APPROVED','SETTLED') THEN 1.0 ELSE 0.0 END) * 100, 1) AS approval_rate,
        ROUND(AVG(CASE WHEN cl.claim_status = 'REJECTED' THEN 1.0 ELSE 0.0 END) * 100, 1) AS rejection_rate,
        ROUND(AVG(cl.settlement_tat_days), 1)                                             AS avg_tat
    FROM cm_case c
    JOIN cm_claim cl ON c.case_id = cl.case_id
    GROUP BY c.hospital_district
),
ranked AS (
    SELECT *,
        RANK() OVER (ORDER BY total_cases    DESC) AS utilization_rank,
        RANK() OVER (ORDER BY approval_rate  DESC) AS approval_rank,
        RANK() OVER (ORDER BY rejection_rate ASC)  AS rejection_rank,
        RANK() OVER (ORDER BY avg_tat        ASC)  AS tat_rank
    FROM district_metrics
)
SELECT
    district,
    total_cases,
    utilization_rank,
    approval_rate,
    approval_rank,
    rejection_rate,
    rejection_rank,
    avg_tat,
    tat_rank
FROM ranked
WHERE district = ?
""",
        "param_slots": [{"name": "district", "entity_type": "district", "position": 1}],
        "result_ttl_seconds": 600,
    },

    "T285": {
        "abstract_question": "Which blocks in {district} rank worst on the enrolment-to-treatment funnel?",
        "date_filter": None,
        "sql_template": """
WITH enrolled AS (
    SELECT h.home_block_name AS block, COUNT(DISTINCT b.beneficiary_id) AS enrolled_count
    FROM bm_beneficiary b JOIN bm_household h ON b.household_id = h.household_id
    WHERE h.home_district_code = ?
    GROUP BY h.home_block_name
),
admitted AS (
    SELECT h.home_block_name AS block, COUNT(DISTINCT c.case_id) AS admitted_count
    FROM cm_case c
    JOIN bm_beneficiary b ON c.beneficiary_id = b.beneficiary_id
    JOIN bm_household h   ON b.household_id   = h.household_id
    WHERE h.home_district_code = ?
    GROUP BY h.home_block_name
)
SELECT
    e.block,
    e.enrolled_count,
    COALESCE(a.admitted_count, 0)                                                         AS admitted_count,
    ROUND(COALESCE(a.admitted_count, 0) * 100.0 / NULLIF(e.enrolled_count, 0), 2)       AS conversion_rate_pct
FROM enrolled e
LEFT JOIN admitted a ON e.block = a.block
ORDER BY conversion_rate_pct ASC
LIMIT 10
""",
        "param_slots": [
            {"name": "district", "entity_type": "district", "position": 1},
            {"name": "district", "entity_type": "district", "position": 2},
        ],
        "result_ttl_seconds": 600,
    },

    "T288": {
        "abstract_question": "Which blocks in {district} rank best on approval rate and settlement TAT?",
        "date_filter": {"alias": "c", "column": "admission_datetime"},
        "sql_template": """
SELECT
    h.home_block_name                                                                            AS block,
    COUNT(DISTINCT c.case_id)                                                                    AS total_cases,
    ROUND(AVG(CASE WHEN cl.claim_status IN ('APPROVED','SETTLED') THEN 1.0 ELSE 0.0 END)*100,1) AS approval_rate_pct,
    ROUND(AVG(cl.settlement_tat_days), 1)                                                        AS avg_tat_days
FROM cm_case c
JOIN cm_claim cl      ON c.case_id        = cl.case_id
JOIN bm_beneficiary b ON c.beneficiary_id = b.beneficiary_id
JOIN bm_household h   ON b.household_id   = h.household_id
WHERE h.home_district_code = ?
GROUP BY h.home_block_name
HAVING COUNT(DISTINCT c.case_id) >= 10
ORDER BY approval_rate_pct DESC, avg_tat_days ASC
LIMIT 10
""",
        "param_slots": [{"name": "district", "entity_type": "district", "position": 1}],
        "result_ttl_seconds": 600,
    },

    "T290": {
        "abstract_question": "Which blocks in {district} rank worst on profile completeness and card issuance lag?",
        "date_filter": None,
        "sql_template": """
WITH profile AS (
    SELECT
        h.home_block_name                                                                        AS block,
        COUNT(DISTINCT b.beneficiary_id)                                                         AS total_beneficiaries,
        ROUND(COUNT(DISTINCT CASE WHEN b.yob IS NOT NULL OR b.dob IS NOT NULL THEN b.beneficiary_id END) * 100.0
            / NULLIF(COUNT(DISTINCT b.beneficiary_id), 0), 1)                                   AS dob_pct,
        ROUND(COUNT(DISTINCT CASE WHEN b.mobile IS NOT NULL THEN b.beneficiary_id END) * 100.0
            / NULLIF(COUNT(DISTINCT b.beneficiary_id), 0), 1)                                   AS mobile_pct
    FROM bm_beneficiary b
    JOIN bm_household h ON b.household_id = h.household_id
    WHERE h.home_district_code = ?
    GROUP BY h.home_block_name
),
card_lag AS (
    SELECT
        h.home_block_name AS block,
        ROUND(AVG(DATE_DIFF('day', er.submitted_at::DATE, bc.issued_at::DATE)), 1) AS avg_card_lag_days
    FROM bm_enrolment_request er
    JOIN bm_beneficiary b ON er.beneficiary_id = b.beneficiary_id
    JOIN bm_household h   ON b.household_id    = h.household_id
    LEFT JOIN bm_card bc  ON er.beneficiary_id = bc.beneficiary_id
    WHERE h.home_district_code = ?
      AND bc.issued_at IS NOT NULL
    GROUP BY h.home_block_name
)
SELECT
    p.block,
    p.total_beneficiaries,
    p.dob_pct,
    p.mobile_pct,
    COALESCE(cl.avg_card_lag_days, 0) AS avg_card_lag_days
FROM profile p
LEFT JOIN card_lag cl ON p.block = cl.block
ORDER BY dob_pct ASC, mobile_pct ASC
LIMIT 10
""",
        "param_slots": [
            {"name": "district", "entity_type": "district", "position": 1},
            {"name": "district", "entity_type": "district", "position": 2},
        ],
        "result_ttl_seconds": 600,
    },

    "T291": {
        "abstract_question": "Which blocks in {district} rank best on maternal and neonatal access?",
        "date_filter": {"alias": "c", "column": "admission_datetime"},
        "sql_template": """
WITH enrolled_women AS (
    SELECT h.home_block_name AS block, COUNT(DISTINCT b.beneficiary_id) AS enrolled_count
    FROM bm_beneficiary b JOIN bm_household h ON b.household_id = h.household_id
    WHERE h.home_district_code = ?
      AND b.gender = 'FEMALE'
    GROUP BY h.home_block_name
),
maternal_cases AS (
    SELECT h.home_block_name AS block, COUNT(DISTINCT c.case_id) AS case_count
    FROM cm_case c
    JOIN bm_beneficiary b   ON c.beneficiary_id = b.beneficiary_id
    JOIN bm_household h     ON b.household_id   = h.household_id
    JOIN cm_case_diagnosis d ON c.case_id       = d.case_id
    WHERE h.home_district_code = ?
      AND d.diagnosis_category = 'MATERNAL_NEONATAL'
      AND d.diagnosis_type = 'PRIMARY'
    GROUP BY h.home_block_name
)
SELECT
    ew.block,
    ew.enrolled_count                                                              AS enrolled_women,
    COALESCE(mc.case_count, 0)                                                    AS maternal_cases,
    ROUND(COALESCE(mc.case_count, 0) * 1000.0 / NULLIF(ew.enrolled_count, 0), 2) AS rate_per_1000_women
FROM enrolled_women ew
LEFT JOIN maternal_cases mc ON ew.block = mc.block
ORDER BY rate_per_1000_women DESC
LIMIT 10
""",
        "param_slots": [
            {"name": "district", "entity_type": "district", "position": 1},
            {"name": "district", "entity_type": "district", "position": 2},
        ],
        "result_ttl_seconds": 600,
    },
}
