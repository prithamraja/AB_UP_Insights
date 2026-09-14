-- ============================================================================
-- derived_columns.sql — staging layer for the PM-JAY domain pack
-- ============================================================================
-- Executed by build_views.py (step 2: "Apply derived columns"), AFTER the
-- typed base views (one per table, named exactly like the table) have been
-- registered from the CSVs.
--
-- Every table gets a `stg_<table>` view so the view SQL files can reference a
-- single, uniform namespace (`stg_*`). Tables that need no derived columns get
-- a pass-through `SELECT *`.
--
-- Two dataset-wide reference points are used below (NOT wall-clock "today"):
--   ref_year = MAX(year(admission_datetime)) across cm_case   -> age_group
--   ref_date = MAX(admission_datetime)        across cm_case   -> is_expired
-- Both are written as scalar subqueries so they stay declarative.
-- ============================================================================


-- ── bm_beneficiary: age_group ───────────────────────────────────────────────
-- Age = ref_year - yob (ref_year is the latest admission year in the dataset,
-- not the current year). Buckets per handoff; null yob -> UNKNOWN.
CREATE OR REPLACE VIEW stg_bm_beneficiary AS
SELECT
    *,
    CASE
        WHEN yob IS NULL THEN 'UNKNOWN'
        WHEN (SELECT max(year(admission_datetime)) FROM cm_case) - yob < 1  THEN 'INFANT'
        WHEN (SELECT max(year(admission_datetime)) FROM cm_case) - yob <= 5  THEN '1-5'
        WHEN (SELECT max(year(admission_datetime)) FROM cm_case) - yob <= 14 THEN '6-14'
        WHEN (SELECT max(year(admission_datetime)) FROM cm_case) - yob <= 25 THEN '15-25'
        WHEN (SELECT max(year(admission_datetime)) FROM cm_case) - yob <= 40 THEN '26-40'
        WHEN (SELECT max(year(admission_datetime)) FROM cm_case) - yob <= 60 THEN '41-60'
        ELSE '60+'
    END AS age_group
FROM bm_beneficiary;


-- ── cm_case: temporal dimensions, length of stay, binary flags ──────────────
-- Period strings must render exactly like pandas: month 'YYYY-MM',
-- quarter 'YYYYQn'. Flags are integer 0/1 (the engine SUMs them). LOS is
-- fractional days.
CREATE OR REPLACE VIEW stg_cm_case AS
SELECT
    *,
    strftime(admission_datetime, '%Y-%m')                                    AS admission_month,
    CAST(year(admission_datetime) AS VARCHAR) || 'Q'
        || CAST(quarter(admission_datetime) AS VARCHAR)                      AS admission_quarter,
    CAST(year(admission_datetime) AS VARCHAR)                                AS admission_year,
    (epoch(discharge_datetime) - epoch(admission_datetime)) / 86400.0        AS length_of_stay,
    CASE WHEN admission_type = 'EMERGENCY' THEN 1 ELSE 0 END                 AS is_emergency,
    CASE WHEN discharge_type = 'DEATH' THEN 1 ELSE 0 END                     AS is_death,
    CASE WHEN discharge_type IN ('LAMA', 'DAMA') THEN 1 ELSE 0 END           AS is_lama_dama
FROM cm_case;


-- ── cm_case_diagnosis: disease_category (ICD-10 first-letter mapping) ────────
CREATE OR REPLACE VIEW stg_cm_case_diagnosis AS
SELECT
    *,
    CASE
        WHEN icd_code IS NULL THEN 'UNKNOWN'
        WHEN upper(trim(icd_code))[1] IN ('O', 'P')                     THEN 'MATERNAL_NEONATAL'
        WHEN upper(trim(icd_code))[1] IN ('A', 'B')                     THEN 'COMMUNICABLE'
        WHEN upper(trim(icd_code))[1] IN ('S', 'T')                     THEN 'INJURY'
        WHEN upper(trim(icd_code))[1] IN ('I','E','J','N','C','D')      THEN 'NCD'
        WHEN upper(trim(icd_code))[1] IN ('K','H','G','M','L')          THEN 'SURGICAL'
        ELSE 'OTHER'
    END AS disease_category
FROM cm_case_diagnosis;


-- ── hm_hospital: bed_size_bucket ────────────────────────────────────────────
-- Exact strings including the parenthetical (the engine treats them as
-- categorical labels).
CREATE OR REPLACE VIEW stg_hm_hospital AS
SELECT
    *,
    CASE
        WHEN total_bed_strength IS NULL THEN 'UNKNOWN'
        WHEN total_bed_strength <= 30   THEN 'SMALL (<=30)'
        WHEN total_bed_strength <= 100  THEN 'MEDIUM (31-100)'
        WHEN total_bed_strength <= 300  THEN 'LARGE (101-300)'
        ELSE 'VERY_LARGE (300+)'
    END AS bed_size_bucket
FROM hm_hospital;


-- ── hm_license_certificate: is_expired ──────────────────────────────────────
-- Integer flag; expiry_date earlier than the dataset reference date
-- (MAX admission_datetime), not the wall clock. Null expiry -> 0 (matches the
-- old script, where NaT < ref evaluated False).
CREATE OR REPLACE VIEW stg_hm_license_certificate AS
SELECT
    *,
    CASE
        WHEN expiry_date < (SELECT max(admission_datetime) FROM cm_case) THEN 1
        ELSE 0
    END AS is_expired
FROM hm_license_certificate;


-- ── Pass-through staging views (no derived columns) ─────────────────────────
CREATE OR REPLACE VIEW stg_ref_up_geography          AS SELECT * FROM ref_up_geography;
CREATE OR REPLACE VIEW stg_ref_hbp_procedure_master  AS SELECT * FROM ref_hbp_procedure_master;
CREATE OR REPLACE VIEW stg_bm_household              AS SELECT * FROM bm_household;
CREATE OR REPLACE VIEW stg_bm_id_document            AS SELECT * FROM bm_id_document;
CREATE OR REPLACE VIEW stg_bm_enrolment_request      AS SELECT * FROM bm_enrolment_request;
CREATE OR REPLACE VIEW stg_bm_card                   AS SELECT * FROM bm_card;
CREATE OR REPLACE VIEW stg_hm_hospital_bank_account  AS SELECT * FROM hm_hospital_bank_account;
CREATE OR REPLACE VIEW stg_hm_specialty_offered      AS SELECT * FROM hm_specialty_offered;
CREATE OR REPLACE VIEW stg_hm_staff                  AS SELECT * FROM hm_staff;
CREATE OR REPLACE VIEW stg_cm_preauth_request        AS SELECT * FROM cm_preauth_request;
CREATE OR REPLACE VIEW stg_cm_preauth_procedure_line AS SELECT * FROM cm_preauth_procedure_line;
CREATE OR REPLACE VIEW stg_cm_discharge              AS SELECT * FROM cm_discharge;
CREATE OR REPLACE VIEW stg_cm_claim                  AS SELECT * FROM cm_claim;
CREATE OR REPLACE VIEW stg_cm_claim_document         AS SELECT * FROM cm_claim_document;
CREATE OR REPLACE VIEW stg_cm_adjudication_event     AS SELECT * FROM cm_adjudication_event;
CREATE OR REPLACE VIEW stg_cm_payment                AS SELECT * FROM cm_payment;
