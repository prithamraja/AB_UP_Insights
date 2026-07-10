"""
LLM re-ranker for template-direct retrieval.

Given the user query and the top-K catalog candidates from the vector retriever,
pick the single query_id whose question best matches — including the right
parameter variant (e.g. prefer the {district} template only if the query names a
district). Returns "no_match" if none of the candidates answer the query.
"""
import json
from openai import OpenAI

from .config import RERANK_MODEL, LLM_TEMPERATURE, LLM_TIMEOUT_SECONDS, REASONING_MODELS

_RERANK_SYS = """\
You match a user's question to the single best canonical question from a numbered list, for the AB PM-JAY (Ayushman Bharat) health-insurance database for Uttar Pradesh, India.

Rules:
- Queries may be in English, Hindi, or Hinglish (romanized Hindi-English mix). Understand the meaning regardless of language.
- Return the id of the candidate whose question best matches the user's intent.
- {placeholders} in a candidate mark filters it expects. Prefer the variant that matches the filters ACTUALLY present in the query:
    - Query names a district  -> prefer the {district} variant over the state-wide one.
    - Query names no filter    -> prefer the state-wide (no-placeholder) variant.
    - Query names a specialty  -> prefer the {specialty} variant, and so on for block, division, hospital, year, month, diagnosis category, claim status.
- If NONE of the candidates can answer the query (off-topic or not covered), return "no_match".

Return ONLY a JSON object: {"query_id": "<id or no_match>"}."""


def rerank(query: str, candidates: list[tuple[str, str]], client: OpenAI) -> str:
    """candidates: list of (query_id, question). Returns a query_id or 'no_match'."""
    if not candidates:
        return "no_match"

    valid_ids = {qid for qid, _ in candidates}
    listing = "\n".join(f"{qid}: {question}" for qid, question in candidates)
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
            kwargs["max_tokens"] = 20

        resp = client.chat.completions.create(**kwargs)
        chosen = json.loads(resp.choices[0].message.content.strip()).get("query_id", "no_match")
        chosen = str(chosen).strip()

        if chosen in valid_ids:
            return chosen
        if chosen == "no_match":
            return "no_match"
        # Tolerate case / whitespace drift (e.g. "t25" -> "T25")
        for qid in valid_ids:
            if qid.lower() == chosen.lower():
                return qid
        return "no_match"

    except Exception:
        return "no_match"
