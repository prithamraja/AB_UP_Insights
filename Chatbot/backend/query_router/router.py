"""
Three-step router:
  Step 1 — classify_intent(query)         → intent string
  Step 2 — extract_entities(query, slots) → {slot: raw_value}
  Step 3 — INTENT_LOOKUP[(intent, frozenset(found_entities))] → query_id
"""
import re
import time
import json
import hashlib

from .models            import RouteResult, RouteTier, ClarificationNeeded, EntityNotFound
from .preprocessor      import normalize
from .intent_catalog    import INTENT_LOOKUP, INTENT_SLOTS
from .intent_classifier import classify_intent
from .entity_extractor  import extract_entities
from .entity_validator  import EntityValidator
from .fallback          import generate_fallback_message
from .config            import RESULT_CACHE_DEFAULT_TTL

# Simple in-process TTL result cache
_result_cache: dict[str, tuple[list[dict], float]] = {}


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


def route(
    user_query: str,
    *,
    validator: EntityValidator,
    openai_client,
    cache_conn,
    dashboard_results: dict[str, list[dict]],
    template_map: dict[str, dict],
    dashboard_questions: dict[str, str],
    start_date: str | None = None,
    end_date:   str | None = None,
    session_id: str | None = None,
) -> RouteResult:
    start = time.monotonic()

    # ── Step 0: Normalise ─────────────────────────────────────────────────────
    normalized = normalize(user_query)

    # ── Step 1: Classify intent ───────────────────────────────────────────────
    domain, intent = classify_intent(normalized, openai_client)

    if intent == "no_match":
        return _fallback(
            "I couldn't find a question that matches what you're asking.\n\n"
            + generate_fallback_message(dashboard_questions),
            user_query, normalized, start,
        )

    # ── Step 2: Extract entities (only the slots this intent needs) ───────────
    slots = INTENT_SLOTS.get(intent, [])
    raw_entities: dict[str, str | None] = {}

    if slots:
        raw_entities = extract_entities(user_query, slots, openai_client, intent=intent)

    # ── Step 3: Validate entities & build lookup key ──────────────────────────
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

    # ── Handle lookup miss ────────────────────────────────────────────────────
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

    # ── Serve result ──────────────────────────────────────────────────────────
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

    # Template query — execute with validated params
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

    slot_order   = {s["name"]: s["position"] for s in param_slots}
    param_values = [
        e.resolved_value
        for e in sorted(validated_entities, key=lambda e: slot_order.get(e.slot_name, 99))
    ]

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
