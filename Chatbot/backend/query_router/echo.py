"""Echo-back rendering: the resolved question, standing alone. Spec invariant 4
called for appending inherited context (filters + explicit time range) too,
but that's dropped here by explicit product decision — the breadcrumb already
shows filters and period as chips, so repeating them in prose read as
redundant. Same decision applies to the "Back to: ..." pop message in
main.py."""
from .models import RouteResult


def echo_answer(result: RouteResult) -> str:
    return result.query_description or result.query_id or "Query matched."
