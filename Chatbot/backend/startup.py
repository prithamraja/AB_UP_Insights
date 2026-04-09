"""
Run this ONCE before starting the server (or when data changes).

  cd backend
  python startup.py

What it does:
  1. Creates cache tables (in-memory for pandas, persistent for Supabase)
  2. Executes all 36 Tier-1 SQL queries and stores results in dashboard_cache
  3. Stores template definitions in query_templates
  4. Prints a summary

Pass --force to re-run even if data already exists.
"""
import sys
import io
import json
import time
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# Fix Windows console encoding for Unicode characters
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import os

from db_factory import get_adapter


import logging
_log = logging.getLogger(__name__)


def run_dashboard_queries(adapter, catalog: dict) -> dict[str, list[dict]]:
    results = {}
    for qid, entry in catalog.items():
        try:
            rel  = adapter.execute(entry["sql"])
            cols = rel.description
            rows = [dict(zip(cols, r)) for r in rel.fetchmany(500)]
            results[qid] = rows
        except Exception as e:
            _log.warning("  %s FAILED: %s", qid, e)
            results[qid] = []
    return results


def seed(adapter, force: bool = False) -> None:
    from query_router.dashboard_catalog import DASHBOARD_CATALOG
    from query_router.template_catalog  import TEMPLATE_CATALOG

    # ── Check if already seeded ───────────────────────────────────────────────
    existing = adapter.execute("SELECT COUNT(*) FROM dashboard_cache").fetchone()[0]
    if existing > 0 and not force:
        _log.info("dashboard_cache already has %d rows — skipping seed", existing)
        return

    _log.info("Executing %d Tier-1 SQL queries...", len(DASHBOARD_CATALOG))
    t0 = time.time()
    query_results = run_dashboard_queries(adapter, DASHBOARD_CATALOG)
    fresh = sum(1 for v in query_results.values() if v)
    _log.info("Done in %.1fs — %d fresh, %d empty/failed, %d total rows",
              time.time() - t0, fresh,
              len(query_results) - fresh,
              sum(len(v) for v in query_results.values()))

    d_ids = list(DASHBOARD_CATALOG.keys())
    t_ids = list(TEMPLATE_CATALOG.keys())

    # ── Upsert dashboard_cache ────────────────────────────────────────────────
    _log.info("Writing dashboard_cache (%d entries)...", len(d_ids))
    adapter.execute("DELETE FROM dashboard_cache")
    for qid in d_ids:
        entry  = DASHBOARD_CATALOG[qid]
        rows   = query_results.get(qid, [])
        status = "FRESH" if rows else "ERROR"
        adapter.execute(
            """INSERT INTO dashboard_cache
               (query_id, question, sql, result, row_count, computed_at, status)
               VALUES (?, ?, ?, ?, ?, now(), ?)""",
            [
                qid,
                entry["question"],
                entry["sql"].strip(),
                json.dumps(rows, default=str),
                len(rows),
                status,
            ],
        )

    # ── Upsert query_templates ────────────────────────────────────────────────
    _log.info("Writing query_templates (%d entries)...", len(t_ids))
    adapter.execute("DELETE FROM query_templates")
    for tid in t_ids:
        entry = TEMPLATE_CATALOG[tid]
        adapter.execute(
            """INSERT INTO query_templates
               (template_id, abstract_question, sql_template, param_slots, result_ttl_seconds)
               VALUES (?, ?, ?, ?, ?)""",
            [
                tid,
                entry["abstract_question"],
                entry["sql_template"].strip(),
                json.dumps(entry["param_slots"]),
                entry.get("result_ttl_seconds", 600),
            ],
        )

    _log.info("Seeded %d dashboard queries + %d templates.", len(d_ids), len(t_ids))


if __name__ == "__main__":
    force = "--force" in sys.argv
    adapter = get_adapter()
    seed(adapter, force=force)
