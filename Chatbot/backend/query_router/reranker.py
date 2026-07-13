"""
LLM re-ranker for template-direct retrieval.

Given the user query and the top-K catalog candidates from the vector retriever,
pick the single query_id whose question best matches — including the right
parameter variant (e.g. prefer the {district} template only if the query names a
district). When no candidate truly answers the query, it returns "no_match"
plus the 2-3 most plausible near-misses, so the clarify zone can offer
semantically chosen interpretations instead of raw embedding neighbours.

Each candidate is shown with a curated description (reused from the intent
classifier's catalog) and the filters it accepts, so the model can tell apart
templates whose wording looks alike but which measure different things.
"""
import json
from openai import OpenAI

from .config import RERANK_MODEL, LLM_TEMPERATURE, LLM_TIMEOUT_SECONDS, REASONING_MODELS
from .intent_catalog import INTENT_LOOKUP
from .intent_classifier import _INTENT_CATALOG
from .template_catalog import TEMPLATE_CATALOG

_TEMPLATES = dict(TEMPLATE_CATALOG)

_RERANK_SYS = """\
You match a user's question to the single best canonical question from a numbered list, for the AB PM-JAY (Ayushman Bharat) health-insurance database for Uttar Pradesh, India.

Some candidates carry two extra lines:
- "↳" — what the question measures, with example queries.
- "accepts filters:" — every filter that candidate can actually apply. This is authoritative for that candidate.

Judge a candidate with a "↳" line by that description rather than by surface word overlap with its wording. But a "↳" description describes a question FAMILY, not one candidate: sibling candidates that are parameter variants of the same family repeat the same description and the same examples word-for-word. So an example may name a district or specialty that THIS candidate cannot accept — sometimes matching the user's query almost word-for-word. Use "↳" to choose the family, then "accepts filters:" and the {placeholder} rule to choose the variant within it. Never pick a candidate merely because one of its examples resembles the query: if the query names a filter the candidate does not accept and a sibling does accept it, the sibling wins.

Rules:
- Queries may be in English, Hindi, or Hinglish (romanized Hindi-English mix). Understand the meaning regardless of language.
- Return the id of the candidate whose question best matches the user's intent.
- {placeholders} in a candidate mark filters it expects. Prefer the variant that matches the filters ACTUALLY present in the query:
    - Query names a district  -> prefer the {district} variant over the state-wide one.
    - Query names no filter    -> prefer the state-wide (no-placeholder) variant.
    - Query names a specialty  -> prefer the {specialty} variant, and so on for block, division, hospital, year, month, diagnosis category, claim status.
- Pick the MOST SPECIFIC candidate that matches the query.
- "rejection" near "claims" or "hospitals" means CLAIMS rejection; "rejection" near "enrolment" means ENROLMENT rejection. Pick the candidate in the matching sense.
- "public vs private utilization share" -> the hospital-type utilization candidate. "public vs private approval rate / TAT" -> the public-private access-equity comparison candidate.
- If the query asks about a specific named hospital, prefer the hospital-performance or hospital-specialties candidate.
- If NONE of the candidates can answer the query exactly, return "no_match" for query_id — and in "candidates", list up to 3 ids of the questions that come CLOSEST to what the user wants (the ones a helpful analyst would offer instead), best first. Judge closeness by meaning, not wording — e.g. a question about women/female beneficiaries is closest to a gender-breakdown question even if the words differ.
- If the query is entirely off-topic for this database, return "no_match" and an empty "candidates" list.

Return ONLY a JSON object: {"query_id": "<id or no_match>", "candidates": ["<id>", ...]}."""


def _accepted_filters(qid: str) -> str:
    """The filters a query_id can actually apply — ground truth from its param_slots.

    Dashboards (D*) are precomputed and take no parameters, so they are state-wide.
    """
    template = _TEMPLATES.get(qid)
    if template is None:
        return "none (state-wide totals only)"
    slots = [slot["name"] for slot in template.get("param_slots") or []]
    return ", ".join(slots) if slots else "none (state-wide totals only)"


def _build_qid_to_context() -> dict[str, tuple[str, str]]:
    """query_id -> (family description, accepted filters) for the reranker listing.

    Descriptions come from the intent classifier's catalog, so only the 324 of 410
    query_ids that map to an intent get one; the rest (mostly newer D-dashboards)
    are shown to the reranker as bare id: question.
    TODO: write descriptions for the uncovered query_ids in the catalog content pass.

    Those descriptions are per-INTENT, and most intents own several query_ids — the
    parameter variants of one question family (specialty_utilization is both T21
    state-wide and T25 {specialty}+{district}). Sibling variants therefore repeat one
    desc and its examples verbatim, and an example can name a filter a sibling cannot
    accept: specialty_utilization's example "CARD utilization in Varanasi" lands on
    district-less T21 as well as on T25, and being near-verbatim for a real user query
    it drags the pick onto the wrong variant. The examples still earn their place —
    they carry the vocabulary that identifies the family at all, e.g. that CARD means
    cardiology and not a beneficiary card — so rather than drop them we pair each
    candidate with its own accepted-filter list, per-query_id ground truth that the
    shared prose cannot contradict.
    """
    qid_to_intent: dict[str, str] = {}
    for (intent, _entities), qid in INTENT_LOOKUP.items():
        qid_to_intent.setdefault(qid, intent)

    contexts: dict[str, tuple[str, str]] = {}
    for qid, intent in qid_to_intent.items():
        entry = _INTENT_CATALOG.get(intent)
        if not entry:
            continue
        desc = entry["desc"]
        examples = entry.get("examples") or []
        if examples:
            desc += "  e.g. " + " | ".join(f'"{e}"' for e in examples[:2])
        contexts[qid] = (desc, _accepted_filters(qid))
    return contexts


_QID_TO_CONTEXT: dict[str, tuple[str, str]] = _build_qid_to_context()


def parse_rerank_response(data: dict, valid_ids: set[str]) -> tuple[str, list[str]]:
    """Pure projection of the LLM's JSON onto (query_id | 'no_match', near_miss_ids)."""
    by_lower = {qid.lower(): qid for qid in valid_ids}

    def _canonical(value) -> str | None:
        text = str(value).strip()
        if text in valid_ids:
            return text
        return by_lower.get(text.lower())

    chosen = _canonical(data.get("query_id", "no_match")) or "no_match"

    raw_candidates = data.get("candidates")
    candidates: list[str] = []
    if isinstance(raw_candidates, list):
        for item in raw_candidates:
            qid = _canonical(item)
            if qid and qid != chosen and qid not in candidates:
                candidates.append(qid)
            if len(candidates) == 3:
                break
    return chosen, candidates


def rerank(query: str, candidates: list[tuple[str, str]], client: OpenAI) -> tuple[str, list[str]]:
    """candidates: list of (query_id, question).
    Returns (query_id | 'no_match', llm_picked_near_miss_ids)."""
    if not candidates:
        return "no_match", []

    valid_ids = {qid for qid, _ in candidates}
    lines = []
    for qid, question in candidates:
        ctx = _QID_TO_CONTEXT.get(qid)
        if ctx:
            desc, filters = ctx
            lines.append(f"{qid}: {question}\n    ↳ {desc}\n    accepts filters: {filters}")
        else:
            lines.append(f"{qid}: {question}")
    listing = "\n".join(lines)
    user_msg = f'Candidates:\n{listing}\n\nUser question: "{query}"\nJSON:'

    try:
        kwargs = dict(
            model=RERANK_MODEL,
            timeout=LLM_TIMEOUT_SECONDS,
            messages=[
                {"role": "system", "content": _RERANK_SYS},
                {"role": "user", "content": user_msg},
            ],
            response_format={"type": "json_object"},
        )
        if RERANK_MODEL in REASONING_MODELS:
            kwargs["max_completion_tokens"] = 500
            kwargs["extra_body"] = {"reasoning_effort": "low"}
        else:
            kwargs["temperature"] = LLM_TEMPERATURE
            kwargs["max_tokens"] = 80

        resp = client.chat.completions.create(**kwargs)
        data = json.loads(resp.choices[0].message.content.strip())
        return parse_rerank_response(data, valid_ids)

    except Exception:
        return "no_match", []
