"""
Three-zone confidence handling (spec Section 6).

Retrieval scores are partitioned by two tunable thresholds:
  proceed   — best candidate is clearly the interpretation; execute (happy path)
  ambiguous — several templates score alike; pause and let the user pick
  no_match  — nothing plausible; say so and offer the nearest catalog questions

Every chip built here carries send_text that routes back through the normal
matcher, so a tap can only ever lead to an executable catalog question.
"""
import re

from .config import (
    CLARIFY_SCORE_MARGIN,
    CLARIFY_UPPER_THRESHOLD,
    NO_MATCH_LOWER_THRESHOLD,
)
from .models import Chip

ScoredCandidate = tuple[str, str, float]  # (query_id, display_question, cosine)


def zone(scores: list[float]) -> str:
    """'proceed' | 'ambiguous' | 'no_match' for a descending score list."""
    if not scores or scores[0] < NO_MATCH_LOWER_THRESHOLD:
        return "no_match"
    if (
        len(scores) > 1
        and scores[0] < CLARIFY_UPPER_THRESHOLD
        and scores[0] - scores[1] < CLARIFY_SCORE_MARGIN
    ):
        return "ambiguous"
    return "proceed"


def _readable(question: str, fill: dict[str, str] | None = None) -> str:
    """'enrolment in {district}?' -> 'enrolment in Lucknow?' when the value is
    known from the user's own utterance, else 'enrolment in a district?'
    (either way the text stays routable)."""
    def _sub(match: re.Match) -> str:
        name = match.group(1)
        if fill and name in fill:
            return str(fill[name])
        return "a " + name.replace("_", " ")

    return re.sub(r"\{(\w+?)\}", _sub, question)


def question_chips(
    candidates: list[ScoredCandidate],
    limit: int,
    fill: dict[str, str] | None = None,
) -> list[Chip]:
    """Nearest catalog questions as tappable chips (deduplicated), with slots
    pre-filled from entities already present in the user's query."""
    chips: list[Chip] = []
    seen: set[str] = set()
    for _, question, _ in candidates:
        text = _readable(question, fill)
        if text in seen:
            continue
        seen.add(text)
        chips.append(Chip(label=text, send_text=text))
        if len(chips) == limit:
            break
    return chips


def corrected_query_chips(
    raw_query: str,
    raw_value: str,
    suggestions: list[str],
    limit: int,
) -> list[Chip]:
    """'Did you mean…' chips: the user's own query with the entity corrected."""
    chips: list[Chip] = []
    pattern = re.compile(re.escape(raw_value), re.IGNORECASE)
    for suggestion in suggestions[:limit]:
        if pattern.search(raw_query):
            send = pattern.sub(suggestion, raw_query, count=1)
        else:
            send = f"{raw_query} ({suggestion})"
        chips.append(Chip(label=suggestion, send_text=send))
    return chips
