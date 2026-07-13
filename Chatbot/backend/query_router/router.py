"""
Router with two selectable front-ends (see config.USE_VECTOR_RETRIEVAL):

  Template-direct (default):
    Step 1 — vector_retrieve(query, k)          → top-K candidate query_ids
    Step 2 — rerank(query, candidates)          → (query_id | no_match, near-miss ids)
    Step 3 — extract_entities(query, slots)     → {slot: raw_value}   (slots come
             from the chosen template's param_slots)

  Legacy intent path (USE_VECTOR_RETRIEVAL=False, or no retriever available):
    Step 1 — classify_intent(query)             → intent
    Step 2 — extract_entities(query, slots)     → {slot: raw_value}
    Step 3 — INTENT_LOOKUP[(intent, entities)]  → query_id

Both front-ends converge on _serve_query_id(), which validates params, injects
the optional date filter, executes/serves, and builds the RouteResult.
"""
import re
import time
import json
import hashlib

from .models            import (
    Chip,
    Clarification,
    ClarificationNeeded,
    EntityNotFound,
    ExtractedEntity,
    PendingClarification,
    RouteResult,
    RouteTier,
)
from .preprocessor      import normalize
from .intent_catalog    import INTENT_LOOKUP, INTENT_SLOTS
from .intent_classifier import classify_intent
from .entity_extractor  import extract_entities
from .entity_validator  import EntityValidator
from .reranker          import rerank
from .fallback          import generate_fallback_message
from .zones             import corrected_query_chips, question_chips, zone
from .suggestions       import elicitation_chips
from .config            import (
    MAX_CLARIFY_OPTIONS,
    MAX_MISS_SUGGESTIONS,
    RESULT_CACHE_DEFAULT_TTL,
    USE_VECTOR_RETRIEVAL,
    VECTOR_TOP_K,
)

# Simple in-process TTL result cache
_result_cache: dict[str, tuple[list[dict], float]] = {}

# query_id → a representative intent (for display/logging on the vector path)
_QID_TO_INTENT: dict[str, str] = {}
for (_intent, _entities), _qid in INTENT_LOOKUP.items():
    _QID_TO_INTENT.setdefault(_qid, _intent)


def _cache_get(key: str) -> list[dict] | None:
    if key in _result_cache:
        val, exp = _result_cache[key]
        if time.time() < exp:
            return val
        del _result_cache[key]
    return None


def _cache_set(key: str, value: list[dict], ttl: int) -> None:
    _result_cache[key] = (value, time.time() + ttl)


def _inject_date_filter(sql: str, alias: str, column: str) -> str:
    """
    Appends a date BETWEEN condition to the SQL, inserting just before the first
    GROUP BY / ORDER BY / LIMIT after the last WHERE clause.
    """
    has_where = bool(re.search(r'\bWHERE\b', sql, re.IGNORECASE))
    keyword   = "AND" if has_where else "WHERE"
    condition = f"\n  {keyword} {alias}.{column}::DATE BETWEEN ? AND ?"

    last_where_end = 0
    for m in re.finditer(r'\bWHERE\b', sql, re.IGNORECASE):
        last_where_end = m.end()

    for kw in (r'\bGROUP\s+BY\b', r'\bORDER\s+BY\b', r'\bLIMIT\b'):
        for m in re.finditer(kw, sql, re.IGNORECASE):
            if m.start() >= last_where_end:
                return sql[:m.start()].rstrip() + condition + '\n' + sql[m.start():]

    return sql.rstrip() + condition


def _exec_template(cache_conn, query_id: str, sql_template: str, param_values: list, ttl: int) -> list[dict]:
    h = hashlib.sha256(
        json.dumps([str(p) for p in param_values]).encode()
    ).hexdigest()[:8]
    cache_key = f"tmpl:{query_id}:{h}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached
    result = cache_conn.execute(sql_template, param_values)
    cols = result.description
    rows = [dict(zip(cols, r)) for r in result.fetchmany(200)]
    _cache_set(cache_key, rows, ttl)
    return rows


def _fallback(msg: str, user_query: str, normalized: str, start: float) -> RouteResult:
    return RouteResult(
        tier=RouteTier.FALLBACK,
        fallback_message=msg,
        raw_query=user_query,
        normalized_query=normalized,
        total_latency_ms=(time.monotonic() - start) * 1000,
    )


def _template_slot_types(template: dict) -> dict[str, str]:
    """Unique slot names in first-seen order, each with its registry type."""
    slot_type: dict[str, str] = {}
    for s in template["param_slots"]:
        slot_type.setdefault(s["name"], s.get("entity_type", s["name"]))
    return slot_type


def bind_param_values(
    param_slots: list[dict], params_by_name: dict, *, context: str = ""
) -> list:
    """
    One value per SQL placeholder: walk param_slots in positional order,
    repeating a logical value wherever its slot name recurs (many templates
    filter several subqueries by the same district/block/hospital).
    """
    ordered = sorted(param_slots, key=lambda s: s["position"])
    missing = [
        n for n in dict.fromkeys(s["name"] for s in ordered)
        if n not in params_by_name
    ]
    if missing:
        raise ValueError(
            f"missing parameter(s){context}: {', '.join(missing)}"
        )
    return [params_by_name[s["name"]] for s in ordered]


def _fill_slots_or_clarify(
    query_id: str,
    slot_type: dict[str, str],
    raw_entities: dict,
    validator: EntityValidator,
    user_query: str,
    normalized: str,
    start: float,
) -> tuple[list[ExtractedEntity], RouteResult | None]:
    """Validate every slot value, or return a clarify carrying pending state so
    the user's next message can resume this exact question."""
    validated: list[ExtractedEntity] = []

    def _pending(missing_slot: str) -> PendingClarification:
        return PendingClarification(
            query_id=query_id,
            missing_slot=missing_slot,
            slot_type=slot_type[missing_slot],
            filled={e.slot_name: e.resolved_value for e in validated},
            original_query=user_query,
        )

    for slot in slot_type:
        raw_val = raw_entities.get(slot)
        if raw_val is None:
            # Required slot empty → pause and ask, never execute broken SQL
            clarify = _clarify(
                "missing_parameter",
                f"For which {slot.replace('_', ' ')}?",
                [],
                user_query, normalized, start,
            )
            clarify.pending = _pending(slot)
            return [], clarify
        try:
            entity = validator.validate(raw_val, slot_type[slot])
            entity.slot_name = slot
            validated.append(entity)
        except EntityNotFound as e:
            if e.suggestions:
                clarify = _clarify(
                    "unknown_entity",
                    f"I couldn't find a {slot.replace('_', ' ')} called "
                    f"'{e.raw_value}'. Did you mean one of these?",
                    corrected_query_chips(
                        user_query, e.raw_value, e.suggestions, MAX_CLARIFY_OPTIONS
                    ),
                    user_query, normalized, start,
                )
            else:
                clarify = _clarify(
                    "unknown_entity",
                    f"I couldn't find a {slot.replace('_', ' ')} called '{e.raw_value}'. "
                    f"Which {slot.replace('_', ' ')} did you mean?",
                    [],
                    user_query, normalized, start,
                )
            clarify.pending = _pending(slot)
            return [], clarify
        except ClarificationNeeded as e:
            clarify = _clarify("unknown_entity", str(e), [], user_query, normalized, start)
            clarify.pending = _pending(slot)
            return [], clarify

    return validated, None


def _extract_fill_values(
    user_query: str,
    picked_ids: list[str],
    template_map: dict[str, dict],
    validator: EntityValidator,
    openai_client,
) -> dict[str, str]:
    """Entities already present in the user's utterance, resolved, keyed by
    slot — used to pre-fill clarify-chip placeholders (best-effort)."""
    slot_type: dict[str, str] = {}
    for qid in picked_ids:
        template = template_map.get(qid)
        if template:
            for name, etype in _template_slot_types(template).items():
                slot_type.setdefault(name, etype)
    if not slot_type:
        return {}
    try:
        raw = extract_entities(user_query, list(slot_type), openai_client)
    except Exception:
        return {}
    fill: dict[str, str] = {}
    for slot, value in raw.items():
        if value is None:
            continue
        try:
            fill[slot] = validator.validate(value, slot_type[slot]).resolved_value
        except Exception:
            continue
    return fill


def _clarify(
    reason: str,
    prompt: str,
    options: list[Chip],
    user_query: str,
    normalized: str,
    start: float,
) -> RouteResult:
    return RouteResult(
        tier=RouteTier.CLARIFY,
        clarification=Clarification(reason=reason, prompt=prompt, options=options),
        raw_query=user_query,
        normalized_query=normalized,
        total_latency_ms=(time.monotonic() - start) * 1000,
    )


def _no_match(
    scored: list[tuple[str, str, float]],
    user_query: str,
    normalized: str,
    start: float,
    *,
    validator: EntityValidator,
    openai_client,
    template_map: dict[str, dict],
) -> RouteResult:
    # Broad-question elicitation (8e): entity resolved, measure missing —
    # "How is Agra doing?" gets measure chips, not a failure message.
    try:
        raw = extract_entities(user_query, ["district"], openai_client).get("district")
        if raw:
            district = validator.validate(raw, "district")
            chips = elicitation_chips("district", district.resolved_value)
            if chips:
                return _clarify(
                    "broad_question",
                    f"What would you like to know about {district.resolved_value}?",
                    chips,
                    user_query, normalized, start,
                )
    except Exception:
        pass  # elicitation is best-effort; fall through to the miss message

    # Nearest-question chips must keep entities the user already gave
    # ("...in Lucknow" must not degrade to "...in a district?").
    fill = _extract_fill_values(
        user_query, [qid for qid, _, _ in scored],
        template_map, validator, openai_client,
    )
    result = _fallback(
        "I can't answer that exactly, but I can answer questions like these:",
        user_query, normalized, start,
    )
    result.clarification = Clarification(
        reason="no_match",
        prompt="I can't answer that exactly, but I can answer these:",
        options=question_chips(scored, MAX_MISS_SUGGESTIONS, fill),
    )
    return result


def requery_template(
    query_id: str,
    *,
    template_map: dict[str, dict],
    cache_conn,
    validator: EntityValidator,
    bound_params: dict[str, str],
    swap_slot: str,
    swap_value: str,
    start_date: str | None,
    end_date: str | None,
) -> list[dict]:
    """
    Re-execute a catalog template with one bound parameter swapped (used by the
    operations layer for compare). The swapped value is validated against the
    entity registry; everything else is identical to the original execution.
    Raises ValueError / EntityNotFound on bad input.
    """
    template = template_map.get(query_id)
    if template is None:
        raise ValueError(f"'{query_id}' is not a re-queryable template")

    slots = template["param_slots"]
    slot_types = {s["name"]: s.get("entity_type", s["name"]) for s in slots}
    if swap_slot not in slot_types:
        raise ValueError(f"template {query_id} has no '{swap_slot}' parameter")

    resolved = validator.validate(swap_value, slot_types[swap_slot]).resolved_value
    params = dict(bound_params, **{swap_slot: resolved})

    param_values = bind_param_values(slots, params, context=f" for {query_id}")

    sql = template["sql_template"]
    date_filter = template.get("date_filter")
    if date_filter and start_date and end_date:
        sql = _inject_date_filter(sql, date_filter["alias"], date_filter["column"])
        param_values = param_values + [start_date, end_date]

    return _exec_template(
        cache_conn, query_id, sql, param_values,
        template.get("result_ttl_seconds", RESULT_CACHE_DEFAULT_TTL),
    )


def serve_frame_edit(
    frame,
    *,
    edit_slot: str | None,
    edit_value: str | None,
    template_map: dict[str, dict],
    cache_conn,
    validator: EntityValidator,
    dashboard_results: dict[str, list[dict]],
    dashboard_questions: dict[str, str],
    user_query: str,
    start_date: str | None,
    end_date: str | None,
) -> RouteResult:
    """
    Execute a follow-up as an edit to the current frame (spec Section 4, v1):
    swap one bound parameter and/or change the date range, within the same
    template. Raises ValueError / EntityNotFound on edits that can't apply.
    """
    template = template_map.get(frame.template_id)
    if template is None:
        raise ValueError("the current result can't be edited — ask the question directly")

    slot_types = {
        s["name"]: s.get("entity_type", s["name"]) for s in template["param_slots"]
    }
    if edit_slot is not None and edit_slot not in slot_types:
        raise ValueError(
            f"the current question has no '{edit_slot}' to change "
            f"(it has: {', '.join(slot_types) or 'none'})"
        )

    entities: list[ExtractedEntity] = []
    for name, etype in slot_types.items():
        if name == edit_slot and edit_value is not None:
            entity = validator.validate(edit_value, etype)
            entity.slot_name = name
        else:
            current = frame.bound_params.get(name)
            if current is None:
                raise ValueError(f"missing '{name}' in the current context")
            entity = ExtractedEntity(
                slot_name=name, raw_value=current, resolved_value=current,
                entity_type=etype, confidence="context",
            )
        entities.append(entity)

    return _serve_query_id(
        frame.template_id, entities, None,
        user_query=user_query, normalized=normalize(user_query),
        start=time.monotonic(),
        cache_conn=cache_conn, dashboard_results=dashboard_results,
        template_map=template_map, dashboard_questions=dashboard_questions,
        start_date=start_date, end_date=end_date,
    )


def serve_pending_answer(
    pending: PendingClarification,
    answer_value: str,
    *,
    template_map: dict[str, dict],
    cache_conn,
    validator: EntityValidator,
    dashboard_results: dict[str, list[dict]],
    dashboard_questions: dict[str, str],
    start_date: str | None,
    end_date: str | None,
) -> RouteResult:
    """
    Resume the question the router paused on: the user's short reply fills the
    missing slot and the pending template executes with all earlier context
    intact. If the template still has another unfilled slot, this returns a
    further clarify carrying updated pending state (chained elicitation).
    """
    template = template_map.get(pending.query_id)
    if template is None:
        raise ValueError(f"'{pending.query_id}' is not a resumable template")

    slot_type = _template_slot_types(template)
    raw_entities = {
        slot: (answer_value if slot == pending.missing_slot else pending.filled.get(slot))
        for slot in slot_type
    }

    start = time.monotonic()
    normalized = normalize(pending.original_query)
    validated, clarify_result = _fill_slots_or_clarify(
        pending.query_id, slot_type, raw_entities, validator,
        pending.original_query, normalized, start,
    )
    if clarify_result is not None:
        return clarify_result

    return _serve_query_id(
        pending.query_id, validated, _QID_TO_INTENT.get(pending.query_id),
        user_query=pending.original_query, normalized=normalized, start=start,
        cache_conn=cache_conn, dashboard_results=dashboard_results,
        template_map=template_map, dashboard_questions=dashboard_questions,
        start_date=start_date, end_date=end_date,
    )


# ── Shared back-end: serve a resolved query_id ────────────────────────────────

def _serve_query_id(
    query_id: str,
    validated_entities: list,
    intent: str | None,
    *,
    user_query: str,
    normalized: str,
    start: float,
    cache_conn,
    dashboard_results: dict[str, list[dict]],
    template_map: dict[str, dict],
    dashboard_questions: dict[str, str],
    start_date: str | None,
    end_date: str | None,
) -> RouteResult:
    # Dashboard (Tier-1) — serve pre-computed result
    if query_id.startswith("D"):
        return RouteResult(
            tier=RouteTier.TIER1_DASHBOARD,
            result=dashboard_results.get(query_id, []),
            raw_query=user_query,
            normalized_query=normalized,
            total_latency_ms=(time.monotonic() - start) * 1000,
            query_id=query_id,
            intent=intent,
            query_description=dashboard_questions.get(query_id),
            start_date=start_date,
            end_date=end_date,
        )

    # Template (Tier-2) — execute with validated params
    template    = template_map[query_id]
    param_slots = template["param_slots"]

    # Build query description with resolved entity values
    _display_raw = {"month", "year"}
    entity_values = {
        e.slot_name: (e.raw_value if e.entity_type in _display_raw else e.resolved_value)
        for e in validated_entities
    }
    try:
        query_description = template["abstract_question"].format(**entity_values)
    except KeyError:
        query_description = template["abstract_question"]

    params_by_name = {e.slot_name: e.resolved_value for e in validated_entities}
    try:
        param_values = bind_param_values(
            param_slots, params_by_name, context=f" for {query_id}"
        )
    except ValueError as ex:
        return _fallback(f"Query failed to execute: {ex}", user_query, normalized, start)

    # Inject date filter if this template supports it
    sql = template["sql_template"]
    date_filter         = template.get("date_filter")
    date_filter_applied = False
    if date_filter and start_date and end_date:
        sql                 = _inject_date_filter(sql, date_filter["alias"], date_filter["column"])
        param_values        = param_values + [start_date, end_date]
        date_filter_applied = True

    try:
        result_rows = _exec_template(
            cache_conn, query_id, sql, param_values,
            template.get("result_ttl_seconds", RESULT_CACHE_DEFAULT_TTL),
        )
    except Exception as ex:
        return _fallback(f"Query failed to execute: {ex}", user_query, normalized, start)

    return RouteResult(
        tier=RouteTier.TIER2_TEMPLATE,
        entities=validated_entities,
        result=result_rows,
        raw_query=user_query,
        normalized_query=normalized,
        total_latency_ms=(time.monotonic() - start) * 1000,
        query_id=query_id,
        intent=intent,
        query_description=query_description,
        start_date=start_date,
        end_date=end_date,
        date_filter_applied=date_filter_applied,
    )


# ── Front-end A: template-direct (vector retrieve → rerank) ───────────────────

def _route_vector(
    user_query, normalized, start, *,
    validator, openai_client, retriever, cache_conn,
    dashboard_results, template_map, dashboard_questions,
    start_date, end_date,
) -> RouteResult:
    scored = retriever.retrieve_scored(normalized, VECTOR_TOP_K)

    # Three-zone confidence handling on retrieval scores
    score_zone = zone([s for _, _, s in scored])
    if score_zone == "no_match":
        return _no_match(
            scored, user_query, normalized, start,
            validator=validator, openai_client=openai_client,
            template_map=template_map,
        )
    if score_zone == "ambiguous":
        fill = _extract_fill_values(
            user_query, [qid for qid, _, _ in scored],
            template_map, validator, openai_client,
        )
        return _clarify(
            "ambiguous_templates",
            "I can read that a few ways — which of these did you mean?",
            question_chips(scored, MAX_CLARIFY_OPTIONS, fill),
            user_query, normalized, start,
        )

    candidates = [(qid, q) for qid, q, _ in scored]
    query_id, near_misses = rerank(user_query, candidates, openai_client)

    if query_id == "no_match" or (
        not query_id.startswith("D") and query_id not in template_map
    ):
        # No exact match. The clarify chips are the reranker's semantically
        # chosen near-misses — not raw embedding order, whose surface-wording
        # bias can rank the wrong template family on top.
        by_id = {qid: (qid, question, score) for qid, question, score in scored}
        picked = [by_id[qid] for qid in near_misses if qid in by_id]
        if picked:
            # Pre-fill chip placeholders with entities the user already gave
            # ("...in Lucknow" must survive into the offered interpretations).
            fill = _extract_fill_values(
                user_query, [qid for qid, _, _ in picked],
                template_map, validator, openai_client,
            )
            return _clarify(
                "ambiguous_templates",
                "I couldn't match that exactly. Did you mean one of these?",
                question_chips(picked, MAX_CLARIFY_OPTIONS, fill),
                user_query, normalized, start,
            )
        # The LLM offered no near-misses (off-topic or broad) — go through the
        # miss path, which also tries broad-question elicitation (8e).
        return _no_match(
            scored, user_query, normalized, start,
            validator=validator, openai_client=openai_client,
            template_map=template_map,
        )

    intent = _QID_TO_INTENT.get(query_id)

    # Extract entities for exactly the slots this template needs
    validated_entities = []
    if not query_id.startswith("D"):
        slot_type = _template_slot_types(template_map[query_id])
        if slot_type:
            raw_entities = extract_entities(
                user_query, list(slot_type), openai_client, intent=intent
            )
            validated_entities, clarify_result = _fill_slots_or_clarify(
                query_id, slot_type, raw_entities, validator,
                user_query, normalized, start,
            )
            if clarify_result is not None:
                return clarify_result

    return _serve_query_id(
        query_id, validated_entities, intent,
        user_query=user_query, normalized=normalized, start=start,
        cache_conn=cache_conn, dashboard_results=dashboard_results,
        template_map=template_map, dashboard_questions=dashboard_questions,
        start_date=start_date, end_date=end_date,
    )


# ── Front-end B: legacy intent classification ─────────────────────────────────

def _route_intent(
    user_query, normalized, start, *,
    validator, openai_client, cache_conn,
    dashboard_results, template_map, dashboard_questions,
    start_date, end_date,
) -> RouteResult:
    domain, intent = classify_intent(normalized, openai_client)

    if intent == "no_match":
        return _fallback(
            "I couldn't find a question that matches what you're asking.\n\n"
            + generate_fallback_message(dashboard_questions),
            user_query, normalized, start,
        )

    slots = INTENT_SLOTS.get(intent, [])
    raw_entities: dict[str, str | None] = {}
    if slots:
        raw_entities = extract_entities(user_query, slots, openai_client, intent=intent)

    validated_entities = []
    found_entity_types: set[str] = set()
    for slot in slots:
        raw_val = raw_entities.get(slot)
        if raw_val is None:
            continue
        try:
            entity = validator.validate(raw_val, slot)
            entity.slot_name = slot
            validated_entities.append(entity)
            found_entity_types.add(slot)
        except EntityNotFound:
            pass
        except ClarificationNeeded as e:
            return _fallback(str(e), user_query, normalized, start)

    lookup_key = (intent, frozenset(found_entity_types))
    query_id   = INTENT_LOOKUP.get(lookup_key)

    if query_id is None:
        for drop in found_entity_types:
            reduced = frozenset(found_entity_types - {drop})
            query_id = INTENT_LOOKUP.get((intent, reduced))
            if query_id:
                validated_entities = [e for e in validated_entities if e.slot_name != drop]
                found_entity_types = reduced
                break

    if query_id is None:
        query_id = INTENT_LOOKUP.get((intent, frozenset()))

    if query_id is None:
        return _fallback(
            f"I understood you were asking about **{intent.replace('_', ' ')}** "
            "but couldn't find the right query for the specific filters you mentioned.\n\n"
            + generate_fallback_message(dashboard_questions),
            user_query, normalized, start,
        )

    return _serve_query_id(
        query_id, validated_entities, intent,
        user_query=user_query, normalized=normalized, start=start,
        cache_conn=cache_conn, dashboard_results=dashboard_results,
        template_map=template_map, dashboard_questions=dashboard_questions,
        start_date=start_date, end_date=end_date,
    )


# ── Public entry point ────────────────────────────────────────────────────────

def route(
    user_query: str,
    *,
    validator: EntityValidator,
    openai_client,
    cache_conn,
    dashboard_results: dict[str, list[dict]],
    template_map: dict[str, dict],
    dashboard_questions: dict[str, str],
    retriever=None,
    start_date: str | None = None,
    end_date:   str | None = None,
    session_id: str | None = None,
) -> RouteResult:
    start      = time.monotonic()
    normalized = normalize(user_query)

    if USE_VECTOR_RETRIEVAL and retriever is not None:
        return _route_vector(
            user_query, normalized, start,
            validator=validator, openai_client=openai_client, retriever=retriever,
            cache_conn=cache_conn, dashboard_results=dashboard_results,
            template_map=template_map, dashboard_questions=dashboard_questions,
            start_date=start_date, end_date=end_date,
        )

    return _route_intent(
        user_query, normalized, start,
        validator=validator, openai_client=openai_client,
        cache_conn=cache_conn, dashboard_results=dashboard_results,
        template_map=template_map, dashboard_questions=dashboard_questions,
        start_date=start_date, end_date=end_date,
    )
