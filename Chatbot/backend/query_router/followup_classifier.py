"""
Three-way follow-up classification against the current context frame
(spec Section 4): every utterance with an active frame is exactly one of

  frame_edit   — an edit to the frame (entity swap, time-range change)
                 within the current template; executed as a re-query
  operation    — a computation on the current result table (Section 2)
  new_question — reset to standard catalog matching

The LLM only classifies and names slots/values from what the user said;
execution and arithmetic are deterministic code.
"""
import json
import re
from datetime import date
from typing import Iterable

from openai import OpenAI
from pydantic import BaseModel

from .config import RERANK_MODEL, LLM_TEMPERATURE, LLM_TIMEOUT_SECONDS, REASONING_MODELS
from .models import ContextFrame, OperationRequest
from .operations import OPERATIONS


class FrameEdit(BaseModel):
    slot:       str | None = None   # bound parameter to swap (e.g. "district")
    value:      str | None = None   # new raw value (e.g. "Lucknow")
    start_date: str | None = None   # YYYY-MM-DD; set for time-range edits
    end_date:   str | None = None


class FollowupDecision(BaseModel):
    kind:      str                          # frame_edit | operation | new_question
    operation: OperationRequest | None = None
    edit:      FrameEdit | None        = None


# ── Catalog-question guard ────────────────────────────────────────────────────
# A message that is word-for-word a catalog question (a tapped chip, or a user
# typing exactly what a chip would send) must never be eaten by the follow-up
# classifier — it routes straight to matching, no LLM judgment involved.

def _norm_question(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().strip("?.! ").lower())


def catalog_question_patterns(questions: Iterable[str]) -> list[re.Pattern]:
    """Compile each catalog question ('How many claims in {district}?') into a
    shape pattern with slots as wildcards. Built once at startup."""
    patterns = []
    for question in questions:
        escaped = re.escape(_norm_question(question))
        patterns.append(re.compile(re.sub(r"\\\{\w+\\\}", ".+?", escaped) + r"\Z"))
    return patterns


def matches_catalog_question(message: str, patterns: list[re.Pattern]) -> bool:
    normalized = _norm_question(message)
    return any(p.match(normalized) for p in patterns)


_SYS = """\
You classify a user's follow-up message against the question they are currently looking at, for the AB PM-JAY (Ayushman Bharat) health-insurance assistant for Uttar Pradesh, India. Messages may be in English, Hindi, or Hinglish.

Classify into exactly one kind:

1. "frame_edit" — the message changes ONE aspect of the current question and keeps the rest:
   - entity swap: "what about Lucknow?", "aur Kanpur?" → set "slot" to the parameter being changed and "value" to the new value
   - time change: "pichhle saal ka?", "for 2024", "last 6 months" → set "start_date" and "end_date" (YYYY-MM-DD), computed from today's date given below
   Only parameters the current question actually has can be swapped. A message naming a parameter the question doesn't have is a "new_question".
   A frame_edit is a FRAGMENT that is meaningless without the current question. A complete question that names its own measure or subject ("How many hospitals are empanelled in Lucknow?") is a "new_question" even if it mentions the same district, entity, or time period as the current question.

2. "operation" — a computation on the current result table:
   sum ("total?", "kul kitna?"), average, min, max ("which is highest?"), count, share_of_total (set "label" if a row is named), sort (set "direction"), top_n / bottom_n (set "n"), percent_change, filter_rows (set filter_column, filter_operator: = != > >= < <= contains, filter_value), compare ("compare with Lucknow" — set "comparator" to the named value(s) and "comparator_slot" to the parameter being compared), median, mode ("most common X" — works on category columns like specialty too; set "column"), stdev ("how much do they vary?", "spread"), percentile (set "n" to the percentile, e.g. "90th percentile" → n=90), range ("spread from lowest to highest"), count_distinct ("how many different hospitals?" — set "column").
   Set "column" when the user names a table column; omit it for the default.
   An operation computes over the rows currently displayed. "count" counts those rows — a "how many X?" question where X is not what the table's rows represent (e.g. "how many hospitals are empanelled?" over a claims table) is a "new_question", not a count.

3. "new_question" — a different question, a change of subject, or anything you are not sure about. When in doubt, choose "new_question": the standard matcher will handle it.

Return ONLY a JSON object:
{"kind": "frame_edit|operation|new_question",
 "slot": null, "value": null, "start_date": null, "end_date": null,
 "operation": null, "column": null, "label": null, "n": null, "direction": null,
 "filter_column": null, "filter_operator": null, "filter_value": null,
 "comparator": null, "comparator_slot": null}"""


def classify_followup(
    utterance: str,
    frame: ContextFrame,
    client: OpenAI,
) -> FollowupDecision:
    columns = ", ".join(
        f"{c.name} ({c.column_type.value})" for c in frame.result_set.columns
    )
    params = ", ".join(f"{k}={v}" for k, v in frame.bound_params.items()) or "none"
    time_range = (
        f"{frame.time_range.start} to {frame.time_range.end}"
        if frame.time_range.start else frame.time_range.grain
    )
    user_msg = (
        f"Today's date: {date.today().isoformat()}\n"
        f"Current question: {frame.template_question or frame.template_id}\n"
        f"Its parameters: {params}\n"
        f"Its time range: {time_range}\n"
        f"Table columns: {columns} ({frame.result_set.row_count} rows shown)\n\n"
        f'User message: "{utterance}"\nJSON:'
    )

    try:
        kwargs = dict(
            model=RERANK_MODEL,
            timeout=LLM_TIMEOUT_SECONDS,
            messages=[
                {"role": "system", "content": _SYS},
                {"role": "user", "content": user_msg},
            ],
            response_format={"type": "json_object"},
        )
        if RERANK_MODEL in REASONING_MODELS:
            kwargs["max_completion_tokens"] = 500
            kwargs["extra_body"] = {"reasoning_effort": "low"}
        else:
            kwargs["temperature"] = LLM_TEMPERATURE
            kwargs["max_tokens"] = 250

        resp = client.chat.completions.create(**kwargs)
        data = json.loads(resp.choices[0].message.content.strip())
    except Exception:
        return FollowupDecision(kind="new_question")

    return parse_decision(data, frame)


def parse_decision(data: dict, frame: ContextFrame) -> FollowupDecision:
    """Pure, testable projection of the LLM's JSON onto a safe decision."""
    kind = str(data.get("kind", "")).strip().lower()

    if kind == "frame_edit":
        slot = data.get("slot")
        value = data.get("value")
        start_date = data.get("start_date")
        end_date = data.get("end_date")
        has_swap = bool(slot and value and slot in frame.bound_params)
        if has_swap and (
            str(frame.bound_params[slot]).strip().lower() == str(value).strip().lower()
        ):
            # No-op swap: the "new" value is what's already bound. Executing it
            # could only re-serve the same answer, so the LLM misread — a full
            # question mentioning the current entity is a new question.
            has_swap = False
        has_time = bool(start_date and end_date)
        if not has_swap and not has_time:
            return FollowupDecision(kind="new_question")
        return FollowupDecision(
            kind="frame_edit",
            edit=FrameEdit(
                slot=str(slot) if has_swap else None,
                value=str(value) if has_swap else None,
                start_date=str(start_date) if has_time else None,
                end_date=str(end_date) if has_time else None,
            ),
        )

    if kind == "operation":
        operation = str(data.get("operation") or "").strip().lower()
        if operation not in OPERATIONS:
            return FollowupDecision(kind="new_question")

        comparator = data.get("comparator")
        if isinstance(comparator, str):
            comparator = [comparator]
        if comparator is not None and not (
            isinstance(comparator, list) and all(isinstance(v, str) for v in comparator)
        ):
            comparator = None

        def _opt_str(key: str) -> str | None:
            value = data.get(key)
            return str(value) if value is not None else None

        n = data.get("n")
        return FollowupDecision(
            kind="operation",
            operation=OperationRequest(
                operation=operation,
                column=_opt_str("column"),
                label=_opt_str("label"),
                n=int(n) if isinstance(n, (int, float, str)) and str(n).isdigit() else None,
                direction=_opt_str("direction"),
                filter_column=_opt_str("filter_column"),
                filter_operator=_opt_str("filter_operator"),
                filter_value=_opt_str("filter_value"),
                comparator=comparator,
                comparator_slot=_opt_str("comparator_slot"),
            ),
        )

    return FollowupDecision(kind="new_question")
