"""
Next-question suggestion chips (spec 8b) and broad-question elicitation (8e).

v1 generation is hand-authored "moves" per template family (drill to related
measure, switch measure, extend to trend). A chip is only emitted when every
slot of the target template can be filled from the current frame, so every
chip is a fully pre-filled, executable catalog question — the LLM never
freestyles a suggestion.
"""
from .config import MAX_SUGGESTION_CHIPS
from .models import Chip, ContextFrame
from .template_catalog import TEMPLATE_CATALOG

# Hand-authored moves, keyed by the slot that anchors the family. Order is
# priority order; the current template is skipped at build time.
FAMILY_MOVES: dict[str, list[str]] = {
    "district": [
        "T02",  # claims summary
        "T03",  # top hospitals
        "T05",  # monthly trend
        "T06",  # hospitals empanelled
        "T08",  # rejection rate
        "T40",  # specialty coverage
        "T01",  # enrolment
        "T27",  # claim status breakdown
    ],
    "block": ["T12", "T14", "T13", "T11"],
    "hospital": ["T15", "T19", "T17", "T16", "T20", "T18"],
    "specialty": ["T21", "T22", "T24"],
    "diagnosis_category": ["T23", "T35"],
    "year": ["T33"],
}

# 8e: template families offered when only an entity is resolved
# ("How is Agra doing?") — enrolment, claims, empanelment, coverage.
ELICITATION_MOVES: dict[str, list[str]] = {
    "district": ["T01", "T02", "T06", "T40"],
    "hospital": ["T15", "T16", "T19", "T17"],
}


def _template_slots(query_id: str) -> set[str] | None:
    template = TEMPLATE_CATALOG.get(query_id)
    if template is None:
        return None
    return {s["name"] for s in template["param_slots"]}


def _chip_for(query_id: str, params: dict[str, str]) -> Chip | None:
    """Pre-filled chip for a target template, or None if it can't be filled."""
    slots = _template_slots(query_id)
    if slots is None or not slots <= set(params):
        return None
    question = TEMPLATE_CATALOG[query_id]["abstract_question"].format(
        **{k: v for k, v in params.items() if k in slots}
    )
    return Chip(label=question, send_text=question)


def suggest_followups(frame: ContextFrame) -> list[Chip]:
    chips: list[Chip] = []
    seen: set[str] = set()
    for slot in frame.bound_params:
        for target in FAMILY_MOVES.get(slot, []):
            if target == frame.template_id or target in seen:
                continue
            chip = _chip_for(target, frame.bound_params)
            if chip is None:
                continue
            seen.add(target)
            chips.append(chip)
            if len(chips) == MAX_SUGGESTION_CHIPS:
                return chips
    return chips


def elicitation_chips(entity_type: str, value: str) -> list[Chip]:
    chips: list[Chip] = []
    for target in ELICITATION_MOVES.get(entity_type, []):
        chip = _chip_for(target, {entity_type: value})
        if chip is not None:
            chips.append(chip)
    return chips
