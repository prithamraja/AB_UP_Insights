"""
One-time initialisation of Supabase / PostgreSQL.

  cd backend
  python init_supabase.py

What it does:
  1. Creates the 21 data tables and COPYs CSV data into them
  2. Creates dashboard_cache and query_templates cache tables
  3. Prints a summary

Requires DATABASE_URL in .env or environment.
"""
from __future__ import annotations

import os
import sys
import io
import csv
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# Fix Windows console encoding so Unicode characters (✓/✗) don't crash prints
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
if sys.stderr.encoding and sys.stderr.encoding.lower() != "utf-8":
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

import psycopg2
import psycopg2.sql as sql

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "ab_data"

# ── Schema inferred from CSV headers ──────────────────────────────────────────
# Column types are guessed from names/suffixes. Adjust if DuckDB auto-detected
# differently for your specific dataset.

SCHEMAS: dict[str, list[tuple[str, str]]] = {
    "bm_household": [
        ("household_id", "VARCHAR PRIMARY KEY"),
        ("family_id", "VARCHAR"),
        ("entitlement_source", "VARCHAR"),
        ("home_state_code", "VARCHAR"),
        ("home_state_name", "VARCHAR"),
        ("home_district_code", "VARCHAR"),
        ("home_division_name", "VARCHAR"),
        ("home_block_name", "VARCHAR"),
        ("created_at", "TIMESTAMPTZ"),
    ],
    "bm_beneficiary": [
        ("beneficiary_id", "VARCHAR PRIMARY KEY"),
        ("household_id", "VARCHAR"),
        ("pmjay_id", "VARCHAR"),
        ("full_name", "TEXT"),
        ("father_or_spouse_name", "TEXT"),
        ("gender", "VARCHAR"),
        ("dob", "DATE"),
        ("yob", "INTEGER"),
        ("mobile", "VARCHAR"),
        ("address_text", "TEXT"),
        ("photo_uri", "TEXT"),
        ("bis_record_status", "VARCHAR"),
        ("ekyc_last_reference_id", "VARCHAR"),
        ("is_duplicate", "BOOLEAN"),
        ("created_at", "TIMESTAMPTZ"),
        ("updated_at", "TIMESTAMPTZ"),
    ],
    "bm_id_document": [
        ("id_doc_id", "VARCHAR PRIMARY KEY"),
        ("beneficiary_id", "VARCHAR"),
        ("doc_type", "VARCHAR"),
        ("doc_number_token", "VARCHAR"),
        ("captured_name", "TEXT"),
        ("captured_gender", "VARCHAR"),
        ("captured_age", "INTEGER"),
        ("captured_address_text", "TEXT"),
        ("doc_scan_uri", "TEXT"),
        ("created_at", "TIMESTAMPTZ"),
    ],
    "bm_enrolment_request": [
        ("enrolment_request_id", "VARCHAR PRIMARY KEY"),
        ("beneficiary_id", "VARCHAR"),
        ("reference_id", "VARCHAR"),
        ("submitted_by_role", "VARCHAR"),
        ("auth_mode", "VARCHAR"),
        ("submitted_at", "TIMESTAMPTZ"),
        ("status", "VARCHAR"),
        ("reviewed_at", "TIMESTAMPTZ"),
        ("rejection_reason", "TEXT"),
    ],
    "bm_card": [
        ("card_id", "VARCHAR PRIMARY KEY"),
        ("beneficiary_id", "VARCHAR"),
        ("card_status", "VARCHAR"),
        ("issued_at", "TIMESTAMPTZ"),
        ("card_pdf_uri", "TEXT"),
    ],
    "hm_hospital": [
        ("hospital_id", "VARCHAR PRIMARY KEY"),
        ("hem_reference_no", "VARCHAR"),
        ("hospital_name", "TEXT"),
        ("hospital_parent_type", "VARCHAR"),
        ("hospital_type", "VARCHAR"),
        ("hospital_sub_type", "VARCHAR"),
        ("establishment_year", "INTEGER"),
        ("state_name", "VARCHAR"),
        ("state_code", "VARCHAR"),
        ("district_name", "VARCHAR"),
        ("division_name", "VARCHAR"),
        ("block_name", "VARCHAR"),
        ("pincode", "VARCHAR"),
        ("geo_latitude", "DOUBLE PRECISION"),
        ("geo_longitude", "DOUBLE PRECISION"),
        ("org_head_name", "TEXT"),
        ("org_head_contact", "VARCHAR"),
        ("contact_email", "VARCHAR"),
        ("accreditation_board", "VARCHAR"),
        ("accreditation_level", "VARCHAR"),
        ("accreditation_valid_upto", "DATE"),
        ("delisted_from_gov_schemes", "BOOLEAN"),
        ("total_bed_strength", "INTEGER"),
        ("inpatient_beds", "INTEGER"),
        ("has_fully_equipped_ot", "BOOLEAN"),
        ("has_icu_with_ac", "BOOLEAN"),
        ("has_casualty", "BOOLEAN"),
        ("has_opd", "BOOLEAN"),
        ("has_hdu", "BOOLEAN"),
        ("has_general_ward", "BOOLEAN"),
        ("has_labour_room", "BOOLEAN"),
        ("created_at", "TIMESTAMPTZ"),
        ("updated_at", "TIMESTAMPTZ"),
    ],
    "hm_hospital_bank_account": [
        ("hospital_bank_id", "VARCHAR PRIMARY KEY"),
        ("hospital_id", "VARCHAR"),
        ("authorized_signatory_name", "TEXT"),
        ("bank_account_name", "TEXT"),
        ("account_number_token", "VARCHAR"),
        ("ifsc_code", "VARCHAR"),
        ("bank_name", "TEXT"),
        ("branch_name", "TEXT"),
        ("tds_exemption", "BOOLEAN"),
        ("cancelled_cheque_uri", "TEXT"),
    ],
    "hm_license_certificate": [
        ("hospital_license_id", "VARCHAR PRIMARY KEY"),
        ("hospital_id", "VARCHAR"),
        ("license_name", "TEXT"),
        ("certificate_no", "VARCHAR"),
        ("issue_date", "DATE"),
        ("expiry_date", "DATE"),
        ("attachment_uri", "TEXT"),
    ],
    "hm_specialty_offered": [
        ("hospital_specialty_id", "VARCHAR PRIMARY KEY"),
        ("hospital_id", "VARCHAR"),
        ("specialty_code", "VARCHAR"),
        ("specialty_name", "TEXT"),
        ("admissions_prev_fy", "INTEGER"),
        ("admissions_before_last_year", "INTEGER"),
    ],
    "hm_staff": [
        ("staff_id", "VARCHAR PRIMARY KEY"),
        ("hospital_id", "VARCHAR"),
        ("name", "TEXT"),
        ("registration_number", "VARCHAR"),
        ("qualifications", "TEXT"),
        ("phone", "VARCHAR"),
        ("email", "VARCHAR"),
        ("experience_years", "NUMERIC"),
        ("role_type", "VARCHAR"),
    ],
    "cm_case": [
        ("case_id", "VARCHAR PRIMARY KEY"),
        ("case_number", "VARCHAR"),
        ("beneficiary_id", "VARCHAR"),
        ("hospital_id", "VARCHAR"),
        ("hospital_district", "VARCHAR"),
        ("hospital_division", "VARCHAR"),
        ("home_state_code", "VARCHAR"),
        ("hospital_state_code", "VARCHAR"),
        ("is_portability", "BOOLEAN"),
        ("admission_datetime", "TIMESTAMPTZ"),
        ("admission_type", "VARCHAR"),
        ("discharge_datetime", "TIMESTAMPTZ"),
        ("discharge_type", "VARCHAR"),
        ("created_at", "TIMESTAMPTZ"),
    ],
    "cm_case_diagnosis": [
        ("case_diagnosis_id", "VARCHAR PRIMARY KEY"),
        ("case_id", "VARCHAR"),
        ("diagnosis_rank", "INTEGER"),
        ("diagnosis_type", "VARCHAR"),
        ("code_system", "VARCHAR"),
        ("icd_code", "VARCHAR"),
        ("diagnosis_text", "TEXT"),
        ("diagnosis_category", "VARCHAR"),
    ],
    "cm_preauth_request": [
        ("preauth_id", "VARCHAR PRIMARY KEY"),
        ("case_id", "VARCHAR"),
        ("initiated_by_role", "VARCHAR"),
        ("initiated_at", "TIMESTAMPTZ"),
        ("status", "VARCHAR"),
        ("auto_approval_type", "VARCHAR"),
        ("ppd_decision_at", "TIMESTAMPTZ"),
        ("last_query_at", "TIMESTAMPTZ"),
        ("last_query_response_at", "TIMESTAMPTZ"),
        ("cancelled_at", "TIMESTAMPTZ"),
        ("cancellation_reason", "TEXT"),
    ],
    "cm_preauth_procedure_line": [
        ("preauth_proc_id", "VARCHAR PRIMARY KEY"),
        ("preauth_id", "VARCHAR"),
        ("hbp_procedure_code", "VARCHAR"),
        ("clinician_staff_id", "VARCHAR"),
        ("units_or_days", "NUMERIC"),
        ("stratification_amount", "NUMERIC"),
        ("implant_amount", "NUMERIC"),
        ("incentive_amount", "NUMERIC"),
        ("base_amount", "NUMERIC"),
        ("computed_final_amount", "NUMERIC"),
        ("procedure_rank", "INTEGER"),
        ("payout_factor", "NUMERIC"),
        ("expected_payable_amount", "NUMERIC"),
        ("is_addon", "BOOLEAN"),
    ],
    "cm_discharge": [
        ("discharge_id", "VARCHAR PRIMARY KEY"),
        ("case_id", "VARCHAR"),
        ("discharge_stage", "VARCHAR"),
        ("surgery_date", "DATE"),
        ("discharge_date", "DATE"),
        ("lama_date", "DATE"),
        ("death_date", "DATE"),
        ("discharge_summary_uri", "TEXT"),
        ("post_surgery_photo_uri", "TEXT"),
        ("death_certificate_uri", "TEXT"),
        ("mortality_audit_report_uri", "TEXT"),
        ("provided_medicines_flag", "BOOLEAN"),
        ("biometric_auth_used", "BOOLEAN"),
    ],
    "cm_claim": [
        ("claim_id", "VARCHAR PRIMARY KEY"),
        ("case_id", "VARCHAR"),
        ("preauth_id", "VARCHAR"),
        ("submitted_at", "TIMESTAMPTZ"),
        ("claim_status", "VARCHAR"),
        ("hospital_bill_no", "VARCHAR"),
        ("hospital_bill_date", "DATE"),
        ("amount_claimed", "NUMERIC"),
        ("amount_approved", "NUMERIC"),
        ("query_count", "INTEGER"),
        ("settled_at", "TIMESTAMPTZ"),
        ("settlement_tat_days", "NUMERIC"),
        ("is_portability_claim", "BOOLEAN"),
    ],
    "cm_claim_document": [
        ("claim_doc_id", "VARCHAR PRIMARY KEY"),
        ("claim_id", "VARCHAR"),
        ("doc_type", "VARCHAR"),
        ("doc_uri", "TEXT"),
        ("uploaded_at", "TIMESTAMPTZ"),
    ],
    "cm_adjudication_event": [
        ("event_id", "VARCHAR PRIMARY KEY"),
        ("claim_id", "VARCHAR"),
        ("event_time", "TIMESTAMPTZ"),
        ("actor_role", "VARCHAR"),
        ("action", "VARCHAR"),
        ("reason_category", "VARCHAR"),
        ("notes", "TEXT"),
    ],
    "cm_payment": [
        ("payment_id", "VARCHAR PRIMARY KEY"),
        ("claim_id", "VARCHAR"),
        ("hospital_bank_id", "VARCHAR"),
        ("payment_date", "TIMESTAMPTZ"),
        ("amount_paid", "NUMERIC"),
        ("payment_mode", "VARCHAR"),
        ("utr_no", "VARCHAR"),
        ("payment_status", "VARCHAR"),
    ],
    "ref_hbp_procedure_master": [
        ("hbp_procedure_code", "VARCHAR PRIMARY KEY"),
        ("specialty_code", "VARCHAR"),
        ("specialty_name", "TEXT"),
        ("package_name", "TEXT"),
        ("procedure_name", "TEXT"),
        ("base_package_price", "NUMERIC"),
        ("has_stratification", "BOOLEAN"),
        ("has_implant_or_high_end", "BOOLEAN"),
        ("procedure_label", "VARCHAR"),
        ("reserved_public_hospitals_only", "BOOLEAN"),
    ],
    "ref_up_geography": [
        ("state_code", "VARCHAR"),
        ("state_name", "VARCHAR"),
        ("division_name", "VARCHAR"),
        ("district_name", "VARCHAR"),
        ("block_name", "VARCHAR"),
    ],
}

TABLES = list(SCHEMAS.keys())


def _create_tables(cur) -> None:
    for table_name, columns in SCHEMAS.items():
        # DROP first in case of schema changes between runs
        cur.execute(f"DROP TABLE IF EXISTS {table_name} CASCADE")
        cols_def = ",\n    ".join(f"{c} {t}" for c, t in columns)
        # UNLOGGED: skips WAL for this table. Critical for small-volume managed
        # Postgres — a single-txn bulk load of 21 tables otherwise fills the WAL.
        # Data is truncated on PG crash, but seed is idempotent so we re-run.
        cur.execute(f"CREATE UNLOGGED TABLE {table_name} (\n    {cols_def}\n)")
    print(f"[init] Created {len(TABLES)} UNLOGGED data tables")


def _copy_csvs(conn) -> None:
    """Commit per table so accumulated WAL/temp space can be released between
    tables. Takes `conn` (not `cur`) so it can commit."""
    for table_name in TABLES:
        csv_path = DATA_DIR / f"{table_name}.csv"
        if not csv_path.exists():
            print(f"  ⚠ {table_name}.csv not found — skipping")
            continue
        cur = conn.cursor()
        with open(csv_path, "r", encoding="utf-8") as f:
            reader = csv.reader(f)
            headers = next(reader)  # consumes the header line from f
            # Note: WITH CSV (not WITH CSV HEADER) — csv.reader already advanced
            # past the header, so Postgres should not try to skip another line.
            cur.copy_expert(
                f"COPY {table_name} ({', '.join(headers)}) FROM STDIN WITH CSV",
                f,
            )
        cnt = cur.rowcount if cur.rowcount >= 0 else "?"
        cur.close()
        conn.commit()  # release WAL / temp files before next table
        print(f"  ✓ {table_name}: {cnt} rows")
    print(f"[init] CSV import complete")


def _create_cache_tables(cur) -> None:
    ddl_path = Path(__file__).parent / "sql" / "cache_tables.sql"
    if ddl_path.exists():
        import re
        raw = ddl_path.read_text()
        cleaned = re.sub(r'--[^\n]*', '', raw)
        for stmt in cleaned.split(";"):
            stmt = stmt.strip()
            if stmt:
                cur.execute(stmt)
    print(f"[init] Cache tables created")


def main() -> None:
    url = os.environ.get("DATABASE_URL", "")
    if not url:
        print("ERROR: DATABASE_URL not set")
        sys.exit(1)

    print(f"[init] Connecting to Supabase / PostgreSQL …")
    conn = psycopg2.connect(url)
    try:
        cur = conn.cursor()
        _create_tables(cur)
        conn.commit()  # commit DDL so each COPY starts in its own txn
        cur.close()

        _copy_csvs(conn)  # commits per table internally

        cur = conn.cursor()
        _create_cache_tables(cur)
        conn.commit()
        cur.close()
        print(f"\n[init] ✓ Supabase initialisation complete.")
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        print(f"\n[init] ✗ FAILED: {e}", file=sys.stderr)
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
