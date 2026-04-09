"""
Database factory — picks the right backend adapter from env config.

Env vars:
  DB_ENGINE      = "pandas" (default) | "supabase"
  DATABASE_URL   = required when DB_ENGINE=supabase  (e.g. postgresql://user:pass@host:5432/db)
"""
from __future__ import annotations

import os
from pathlib import Path

try:
    from .db_adapters import PandasAdapter, SupabaseAdapter
except ImportError:
    from db_adapters import PandasAdapter, SupabaseAdapter

# ── Shared constants ─────────────────────────────────────────────────────────

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "ab_data"

TABLES = [
    "bm_household","bm_beneficiary","bm_id_document","bm_enrolment_request","bm_card",
    "hm_hospital","hm_hospital_bank_account","hm_license_certificate",
    "hm_specialty_offered","hm_staff",
    "cm_case","cm_case_diagnosis","cm_preauth_request","cm_preauth_procedure_line",
    "cm_discharge","cm_claim","cm_claim_document","cm_adjudication_event","cm_payment",
    "ref_hbp_procedure_master","ref_up_geography",
]

_adapter: PandasAdapter | SupabaseAdapter | None = None


def get_adapter() -> PandasAdapter | SupabaseAdapter:
    """Singleton factory — creates the adapter on first call."""
    global _adapter
    if _adapter is not None:
        return _adapter

    engine = os.environ.get("DB_ENGINE", "pandas").lower()

    if engine == "supabase":
        url = os.environ.get("DATABASE_URL", "")
        if not url:
            raise RuntimeError(
                "DB_ENGINE=supabase but DATABASE_URL is not set. "
                "Add it to your .env or environment variables."
            )
        _adapter = SupabaseAdapter(url)

        # Ensure cache tables exist on first connect
        ddl_path = Path(__file__).parent / "sql" / "cache_tables.sql"
        if ddl_path.exists():
            import re
            raw = ddl_path.read_text()
            cleaned = re.sub(r'--[^\n]*', '', raw)
            for stmt in cleaned.split(";"):
                stmt = stmt.strip()
                if stmt:
                    _adapter.execute_ddl(stmt)

        print(f"[db] Using Supabase (PostgreSQL) backend")
        return _adapter

    # ── Pandas + DuckDB in-memory (default) ──────────────────────────────────
    _adapter = PandasAdapter(DATA_DIR, TABLES)

    # Ensure cache tables exist
    ddl_path = Path(__file__).parent / "sql" / "cache_tables.sql"
    if ddl_path.exists():
        import re
        raw = ddl_path.read_text()
        cleaned = re.sub(r'--[^\n]*', '', raw)
        for stmt in cleaned.split(";"):
            stmt = stmt.strip()
            if stmt:
                _adapter.execute_ddl(stmt)

    print(f"[db] Loaded {len(_adapter.dataframes)} CSV tables via pandas (in-memory)")
    return _adapter
