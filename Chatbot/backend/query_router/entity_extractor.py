"""
Step 2: Extract entity values from the user query.
Given an intent, we know exactly which slots to look for — so the prompt is
small and targeted, making extraction very reliable.
"""
import json
from datetime import date
from openai import OpenAI
from .config import EXTRACTION_MODEL, LLM_TEMPERATURE, LLM_MAX_TOKENS_EXTRACT, LLM_TIMEOUT_SECONDS, REASONING_MODELS

_VALID_YEARS = ", ".join(str(y) for y in range(2022, date.today().year + 1))

_EXTRACTION_PROMPT = """\
Extract entity values from this health insurance query.
{intent_context}
Query: "{query}"

Extract ONLY these specific values (return null if not present):
{slot_lines}

Rules:
- For district/block: return the place name in ENGLISH (e.g. आगरा → "Agra", लखनऊ → "Lucknow", वाराणसी → "Varanasi"). Always transliterate to the standard English spelling.
- For specialty: return the code if given (OBG, CARD, ORTH, OPTH, GS, MED, URO, PEDS, NEURO, ONCO) or the full name
- For diagnosis_category: return one of COMMUNICABLE, MATERNAL_NEONATAL, NCD, SURGICAL, INJURY
- For claim_status: return APPROVED, SETTLED, QUERY_RAISED, REJECTED, or PENDING
- For year: return 4-digit year ({valid_years})
- For month: return the month name or number
- For hospital: return the full hospital name as written
- For district_2: return the SECOND district mentioned in the query. Example: "Compare Lucknow and Agra" → district="Lucknow", district_2="Agra". Example: "claims between Kanpur and Varanasi" → district="Kanpur", district_2="Varanasi"
- For division_2: return the SECOND division mentioned in the query (same logic as district_2)

Return ONLY a JSON object with these exact keys.
JSON:"""


def extract_entities(
    user_query: str,
    slots: list[str],
    client: OpenAI,
    *,
    intent: str | None = None,
) -> dict[str, str | None]:
    """
    slots: flat list of entity type names e.g. ["district", "specialty"]
    intent: the classified intent name (provides context for better extraction)
    Returns dict mapping slot_name → raw string value (or None if not found).
    """
    if not slots:
        return {}

    slot_lines = "\n".join(f'- "{s}"' for s in slots)
    intent_context = f"The query was classified as intent: {intent}" if intent else ""

    try:
        kwargs = dict(
            model=EXTRACTION_MODEL,
            timeout=LLM_TIMEOUT_SECONDS,
            messages=[{
                "role": "user",
                "content": _EXTRACTION_PROMPT.format(
                    query=user_query,
                    slot_lines=slot_lines,
                    intent_context=intent_context,
                    valid_years=_VALID_YEARS,
                )
            }],
            response_format={"type": "json_object"},
        )
        if EXTRACTION_MODEL in REASONING_MODELS:
            kwargs["max_completion_tokens"] = 2000
            kwargs["extra_body"] = {"reasoning_effort": "low"}
        else:
            kwargs["temperature"] = LLM_TEMPERATURE
            kwargs["max_tokens"] = LLM_MAX_TOKENS_EXTRACT
        resp = client.chat.completions.create(**kwargs)
        parsed = json.loads(resp.choices[0].message.content.strip())
        return {s: parsed.get(s) for s in slots}
    except Exception:
        return {s: None for s in slots}
