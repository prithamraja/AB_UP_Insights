from dotenv import load_dotenv
load_dotenv()

import os
import json
import time
from uuid import uuid4
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
from query_router.router            import (
    route,
    requery_template,
    serve_frame_edit,
    serve_pending_answer,
)
from query_router.vector_retriever  import VectorRetriever
from query_router.dashboard_catalog import DASHBOARD_CATALOG
from query_router.template_catalog  import TEMPLATE_CATALOG
from query_router.config            import USE_VECTOR_RETRIEVAL
from query_router.models            import (
    Chip,
    Clarification,
    ContextFrame,
    OperationRequest,
    OperationResult,
    RouteResult,
)
from query_router.context_store     import ContextStore, build_context_frame
from query_router.column_metadata   import build_catalog_column_metadata
from query_router.operations        import run_operation
from query_router.followup_classifier import (
    catalog_question_patterns,
    classify_followup,
    matches_catalog_question,
)
from query_router.suggestions       import suggest_followups
from query_router.echo              import echo_answer

_context_store = ContextStore()
_catalog_column_metadata = build_catalog_column_metadata(DASHBOARD_CATALOG, TEMPLATE_CATALOG)

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
_retriever:           VectorRetriever | None       = None
_dashboard_results:   dict[str, list[dict]]        = {}
_dashboard_questions: dict[str, str]               = {}
_template_map:        dict[str, dict]              = {}
_catalog_patterns:    list                         = []  # compiled catalog-question shapes
_default_start_date:  str
_default_end_date:    str
_default_start_date, _default_end_date = _last_year_range()


@app.on_event("startup")
def startup():
    global _validator, _openai_client, _retriever
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
    _catalog_patterns.extend(catalog_question_patterns(
        [t["abstract_question"] for t in _template_map.values()]
        + list(_dashboard_questions.values())
    ))

    # Build the vector-retrieval index (embeds the catalog once; cached to .tmp)
    if USE_VECTOR_RETRIEVAL:
        try:
            _retriever = VectorRetriever(_openai_client, DASHBOARD_CATALOG, TEMPLATE_CATALOG)
            print(f"[startup] Vector retriever ready — {len(_retriever.ids)} catalog entries")
        except Exception as e:
            print(f"[startup] WARNING: vector retriever failed to build ({e}) — "
                  "falling back to intent classification")
            _retriever = None

    print(f"[startup] Router ready — "
          f"{len(_dashboard_results)} cached results, "
          f"{len(_template_map)} templates, "
          f"mode={'vector' if _retriever else 'intent'}")


# ── Models ────────────────────────────────────────────────────────────────────

class QueryRequest(BaseModel):
    message:    str
    session_id: Optional[str] = None
    reset_context: bool = False
    start_date: Optional[str] = None   # YYYY-MM-DD; defaults to last full month of data
    end_date:   Optional[str] = None   # YYYY-MM-DD
    from_chip:  bool = False           # tapped chip: text we generated — skip the
                                       # follow-up classifier, go straight to matching

class QueryResponse(BaseModel):
    session_id:          str
    context_frame:       Optional[ContextFrame] = None
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
    operation:          Optional[str]        = None  # set when the answer is an operation result
    operation_mode:     Optional[str]        = None  # client | requery | rejected
    clarification:      Optional[Clarification] = None
    suggestions:        Optional[list[Chip]]    = None


def _looks_like_slot_answer(message: str) -> bool:
    """A bare answer to a pending clarification ('lucknow', 'Sharma Hospital
    Agra'), not a fresh question. Long messages route normally."""
    return len(message.strip().strip("?.!").split()) <= 6


def _catalog_question(query_id: Optional[str]) -> Optional[str]:
    if not query_id:
        return None
    if query_id in _template_map:
        return _template_map[query_id]["abstract_question"]
    return _dashboard_questions.get(query_id)


class OperationCallRequest(OperationRequest):
    session_id:    str
    result_set_id: str  # guard: must match the current frame's table


def _requery_for_frame(frame: ContextFrame, start_date: str, end_date: str):
    """Compare hook: re-run the frame's template with one parameter swapped."""
    if frame.time_range.grain == "day" and frame.time_range.start and frame.time_range.end:
        start_date, end_date = frame.time_range.start, frame.time_range.end

    def requery(slot: str, value: str) -> list[dict]:
        return requery_template(
            frame.template_id,
            template_map=_template_map,
            cache_conn=get_adapter(),
            validator=_validator,
            bound_params=frame.bound_params,
            swap_slot=slot,
            swap_value=value,
            start_date=start_date,
            end_date=end_date,
        )

    return requery


def _execute_operation(
    op_request: OperationRequest,
    session_id: str,
    start_date: str,
    end_date: str,
) -> tuple[ContextFrame, OperationResult] | None:
    stored = _context_store.get_with_rows(session_id)
    if stored is None:
        return None
    frame, rows = stored
    result = run_operation(
        op_request, frame, rows,
        requery=_requery_for_frame(frame, start_date, end_date),
    )
    return frame, result


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
    session_id = req.session_id or str(uuid4())
    if req.reset_context:
        _context_store.reset(session_id)

    result: RouteResult | None = None

    # Resume a pending clarification first: the system just asked a question
    # ("For which district?"), so a short reply that validates as the missing
    # slot answers it. Anything else clears the pending state (one-shot) and
    # routes normally.
    # A chip tap sends text we generated from the catalog — it is a complete
    # question by construction, never a slot answer or a follow-up fragment.
    pending = _context_store.take_pending(session_id)
    if pending is not None and not req.from_chip and _looks_like_slot_answer(req.message):
        answer_text = req.message.strip().strip("?.!")
        try:
            _validator.validate(answer_text, pending.slot_type)
        except Exception:
            pass  # not an answer to what we asked — treat as a new message
        else:
            try:
                result = serve_pending_answer(
                    pending, answer_text,
                    template_map=_template_map,
                    cache_conn=get_adapter(),
                    validator=_validator,
                    dashboard_results=_dashboard_results,
                    dashboard_questions=_dashboard_questions,
                    start_date=start_date,
                    end_date=end_date,
                )
            except Exception:
                result = None  # resumption failed — fall through to matching

    # Follow-up classification against the current frame (spec Section 4):
    # frame edit → re-query same template; operation → compute on the table;
    # new question → standard catalog matching.
    followup_started = time.monotonic()
    current_frame = _context_store.get(session_id) if result is None else None
    if current_frame is not None and (
        req.from_chip
        # A message that is word-for-word a catalog question (typed or tapped)
        # can never be a frame edit or an operation — don't let the classifier
        # capture it ("How many hospitals are empanelled…?" is not a count).
        or matches_catalog_question(req.message, _catalog_patterns)
    ):
        current_frame = None
    if current_frame is not None:
        decision = classify_followup(req.message, current_frame, _openai_client)

        if decision.kind == "operation" and decision.operation is not None:
            executed = _execute_operation(decision.operation, session_id, start_date, end_date)
            if executed is not None:
                frame, op_result = executed
                return QueryResponse(
                    session_id=session_id,
                    context_frame=frame,
                    tier="operation",
                    answer=op_result.answer,
                    result=op_result.result,
                    query_id=frame.template_id,
                    date_range={
                        "start_date": start_date,
                        "end_date":   end_date,
                        "is_default": is_default,
                    },
                    latency_ms=(time.monotonic() - followup_started) * 1000,
                    operation=op_result.operation,
                    operation_mode=op_result.mode.value,
                )

        if decision.kind == "frame_edit" and decision.edit is not None:
            edit = decision.edit
            edit_start, edit_end = start_date, end_date
            if edit.start_date and edit.end_date:
                edit_start, edit_end = edit.start_date, edit.end_date
            elif current_frame.time_range.grain == "day" and current_frame.time_range.start:
                edit_start = current_frame.time_range.start
                edit_end   = current_frame.time_range.end
            try:
                result = serve_frame_edit(
                    current_frame,
                    edit_slot=edit.slot,
                    edit_value=edit.value,
                    template_map=_template_map,
                    cache_conn=get_adapter(),
                    validator=_validator,
                    dashboard_results=_dashboard_results,
                    dashboard_questions=_dashboard_questions,
                    user_query=req.message,
                    start_date=edit_start,
                    end_date=edit_end,
                )
                start_date, end_date = edit_start, edit_end
            except Exception:
                result = None  # edit didn't apply — fall through to matching

    if result is None:
        try:
            result = route(
                req.message,
                validator=_validator,
                openai_client=_openai_client,
                cache_conn=get_adapter(),
                dashboard_results=_dashboard_results,
                template_map=_template_map,
                dashboard_questions=_dashboard_questions,
                retriever=_retriever,
                start_date=start_date,
                end_date=end_date,
                session_id=session_id,
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    # Remember any clarification we just asked, so the next reply can resume it
    if result.pending is not None:
        _context_store.set_pending(session_id, result.pending)

    if result.query_id and result.result is not None:
        frame = build_context_frame(
            result,
            _catalog_column_metadata.get(result.query_id),
            _catalog_question(result.query_id),
        )
        if frame is not None:
            result.context_frame = _context_store.set_frame(
                session_id, frame, rows=result.result
            )
    else:
        result.context_frame = _context_store.get(session_id)

    # Build human-readable answer + next-question chips
    suggestions: list[Chip] | None = None
    if result.tier.value in ("tier1", "tier2"):
        answer = echo_answer(result)
        if result.context_frame is not None:
            suggestions = suggest_followups(result.context_frame) or None
    elif result.tier.value == "clarify":
        answer = result.clarification.prompt if result.clarification else "Could you clarify what you mean?"
    else:
        answer = result.fallback_message or "I couldn't find an answer to that."

    return QueryResponse(
        session_id=session_id,
        context_frame=result.context_frame,
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
        clarification=result.clarification,
        suggestions=suggestions,
    )


class ContextRequest(BaseModel):
    session_id: str


@app.post("/context/reset")
def context_reset(req: ContextRequest):
    """Explicit new-question affordance: drop the frame and history."""
    _context_store.reset(req.session_id)
    return {"session_id": req.session_id, "reset": True}


@app.post("/context/pop", response_model=QueryResponse)
def context_pop(req: ContextRequest):
    """Breadcrumb back: restore the previous frame and its exact table."""
    popped = _context_store.pop(req.session_id)
    if popped is None:
        raise HTTPException(status_code=409, detail="No earlier question to go back to.")
    frame, rows = popped

    base = frame.template_question or frame.template_id
    answer = "Back to: " + base

    return QueryResponse(
        session_id=req.session_id,
        context_frame=frame,
        tier="tier2" if frame.template_id.startswith("T") else "tier1",
        answer=answer,
        result=rows,
        query_id=frame.template_id,
        latency_ms=0.0,
        suggestions=suggest_followups(frame) or None,
    )


@app.post("/operation", response_model=QueryResponse)
def operation_endpoint(req: OperationCallRequest):
    """Typed operation invoked from UI affordances on the current result table."""
    if _openai_client is None:
        raise HTTPException(
            status_code=503,
            detail="Router not initialised. Add OPENAI_API_KEY to .env."
        )
    started = time.monotonic()
    start_date, end_date = _default_start_date, _default_end_date

    stored = _context_store.get_with_rows(req.session_id)
    if stored is None:
        raise HTTPException(
            status_code=409,
            detail="No active result to operate on — ask a question first.",
        )
    frame, rows = stored
    # Stale-table guard must run before any computation or requery
    if req.result_set_id != frame.result_set.id:
        raise HTTPException(
            status_code=409,
            detail="That table is no longer the active result — re-run the question first.",
        )

    op_result = run_operation(
        OperationRequest(**req.model_dump(exclude={"session_id", "result_set_id"})),
        frame, rows,
        requery=_requery_for_frame(frame, start_date, end_date),
    )

    return QueryResponse(
        session_id=req.session_id,
        context_frame=frame,
        tier="operation",
        answer=op_result.answer,
        result=op_result.result,
        query_id=frame.template_id,
        latency_ms=(time.monotonic() - started) * 1000,
        operation=op_result.operation,
        operation_mode=op_result.mode.value,
    )
