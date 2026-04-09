from dotenv import load_dotenv
load_dotenv()

import os
import json
from datetime import date

def _last_year_range() -> tuple[str, str]:
    y = date.today().year - 1
    return f"{y}-01-01", f"{y}-12-31"
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
from openai import OpenAI

from db_factory import get_adapter
from query_router.entity_validator  import EntityValidator
from query_router.router            import route
from query_router.dashboard_catalog import DASHBOARD_CATALOG
from query_router.template_catalog  import TEMPLATE_CATALOG

app = FastAPI(title="AB UP Chatbot API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Singletons ────────────────────────────────────────────────────────────────
_validator:           EntityValidator | None       = None
_openai_client:       OpenAI | None                = None
_dashboard_results:   dict[str, list[dict]]        = {}
_dashboard_questions: dict[str, str]               = {}
_template_map:        dict[str, dict]              = {}
_default_start_date:  str
_default_end_date:    str
_default_start_date, _default_end_date = _last_year_range()


@app.on_event("startup")
def startup():
    global _validator, _openai_client
    global _dashboard_results, _dashboard_questions, _template_map
    global _default_start_date, _default_end_date

    adapter = get_adapter()
    print("[startup] DB ready")

    # Auto-seed cache (in-memory adapter needs seeding on each start)
    from startup import seed as seed_cache
    seed_cache(adapter, force=False)

    print(f"[startup] Default date range: {_default_start_date} to {_default_end_date}")

    oai_key = os.environ.get("OPENAI_API_KEY", "")
    if not oai_key:
        print("[startup] WARNING: OPENAI_API_KEY not set — /query endpoint disabled")
        return

    _openai_client = OpenAI(api_key=oai_key)
    _validator     = EntityValidator(adapter)

    # Load pre-computed dashboard results from cache
    rows = adapter.execute(
        "SELECT query_id, result FROM dashboard_cache WHERE status = 'FRESH'"
    ).fetchall()
    for qid, result_json in rows:
        if result_json:
            try:
                _dashboard_results[qid] = json.loads(result_json)
            except Exception:
                pass

    _dashboard_questions = {k: v["question"] for k, v in DASHBOARD_CATALOG.items()}
    _template_map        = {k: v for k, v in TEMPLATE_CATALOG.items()}

    print(f"[startup] Router ready — "
          f"{len(_dashboard_results)} cached results, "
          f"{len(_template_map)} templates")


# ── Models ────────────────────────────────────────────────────────────────────

class QueryRequest(BaseModel):
    message:    str
    session_id: Optional[str] = None
    start_date: Optional[str] = None   # YYYY-MM-DD; defaults to last full month of data
    end_date:   Optional[str] = None   # YYYY-MM-DD

class QueryResponse(BaseModel):
    tier:               str
    answer:             str
    result:             Optional[list[dict]] = None
    query_id:           Optional[str]        = None
    query_description:  Optional[str]        = None
    intent:             Optional[str]        = None
    entities:           Optional[list[dict]] = None
    date_range:          dict                 = {}   # {"start_date": "...", "end_date": "...", "is_default": bool}
    date_filter_applied: bool                = False
    latency_ms:         float


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {
        "status": "ok",
        "router": {
            "cached_results": len(_dashboard_results),
            "templates":      len(_template_map),
        }
    }

@app.get("/debug/cache")
def debug_cache():
    adapter = get_adapter()
    total = adapter.execute("SELECT COUNT(*) FROM dashboard_cache").fetchone()[0]
    fresh = adapter.execute("SELECT COUNT(*) FROM dashboard_cache WHERE status='FRESH'").fetchone()[0]
    sample = adapter.execute(
        "SELECT query_id, status, row_count FROM dashboard_cache ORDER BY query_id"
    ).fetchall()
    return {
        "cache_table_total": total,
        "cache_table_fresh": fresh,
        "in_memory_dict_size": len(_dashboard_results),
        "sample": [{"qid": r[0], "status": r[1], "rows": r[2]} for r in sample[:20]],
    }

@app.post("/query", response_model=QueryResponse)
def query_endpoint(req: QueryRequest):
    if _openai_client is None:
        raise HTTPException(
            status_code=503,
            detail="Router not initialised. Add OPENAI_API_KEY to .env."
        )
    # Resolve date range — use request values or fall back to detected defaults
    is_default = req.start_date is None and req.end_date is None
    start_date = req.start_date or _default_start_date
    end_date   = req.end_date   or _default_end_date

    try:
        result = route(
            req.message,
            validator=_validator,
            openai_client=_openai_client,
            cache_conn=get_adapter(),
            dashboard_results=_dashboard_results,
            template_map=_template_map,
            dashboard_questions=_dashboard_questions,
            start_date=start_date,
            end_date=end_date,
            session_id=req.session_id,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    # Build human-readable answer
    if result.tier.value in ("tier1", "tier2"):
        answer = result.query_description or result.query_id or "Query matched."
    else:
        answer = result.fallback_message or "I couldn't find an answer to that."

    return QueryResponse(
        tier=result.tier,
        answer=answer,
        result=result.result,
        query_id=result.query_id,
        query_description=result.query_description,
        intent=result.intent,
        entities=[
            {"slot": e.slot_name, "value": e.resolved_value, "confidence": e.confidence}
            for e in (result.entities or [])
        ],
        date_range={
            "start_date": start_date,
            "end_date":   end_date,
            "is_default": is_default,
        },
        date_filter_applied=result.date_filter_applied,
        latency_ms=result.total_latency_ms,
    )
