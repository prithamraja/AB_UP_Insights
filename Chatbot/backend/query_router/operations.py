"""
Deterministic operations layer over the current context frame's result table.

The LLM (or a UI button) only *selects* an operation + arguments from this
closed set; every number below is computed in code. The policy table decides,
per (operation, column type), whether the computation may run client-side on
the displayed rows or must be recomputed through a catalog template — an
unweighted mean of ratios is wrong, so ratio aggregations never run here.
"""
from __future__ import annotations

import statistics
from collections import Counter
from typing import Callable

from .models import (
    ColumnMetadata,
    ColumnType,
    ContextFrame,
    OperationMode,
    OperationRequest,
    OperationResult,
)

OPERATIONS = {
    "sum", "average", "min", "max", "count", "share_of_total",
    "sort", "filter_rows", "percent_change", "top_n", "bottom_n", "compare",
    "median", "mode", "stdev", "percentile", "range", "count_distinct",
}

# Operations that aggregate a measure column — these are the dangerous ones.
_AGGREGATIONS = {"sum", "average", "share_of_total"}

# Measure-typed columns an aggregation may target, and how.
#   client  — safe on the displayed table
#   requery — must be recomputed from base data through a catalog template
_AGGREGATION_POLICY: dict[ColumnType, str] = {
    ColumnType.ADDITIVE_COUNT: "client",
    ColumnType.ADDITIVE_VALUE: "client",
    ColumnType.RATIO:          "requery",
    ColumnType.SNAPSHOT_STOCK: "client",   # except across time — see aggregation_mode()
    ColumnType.UNCLASSIFIED:   "requery",  # additivity unverified; don't guess
}

# Non-aggregating numeric ops are order/pick or distribution-of-the-displayed-rows
# statistics — safe on any measure, ratios included (a median district rate is a
# legitimate per-row statistic; it's the unweighted *mean* of rates that lies).
_NUMERIC_OPS = {
    "min", "max", "percent_change", "sort", "top_n", "bottom_n",
    "median", "stdev", "percentile", "range",
}

_MEASURE_TYPES = set(_AGGREGATION_POLICY)


def aggregation_mode(column: ColumnMetadata, table_columns: list[ColumnMetadata]) -> str:
    """Client-vs-requery decision for aggregating one column of the table."""
    if column.column_type not in _MEASURE_TYPES:
        return "invalid"
    mode = _AGGREGATION_POLICY[column.column_type]
    if column.column_type == ColumnType.SNAPSHOT_STOCK and any(
        c.column_type == ColumnType.TEMPORAL for c in table_columns
    ):
        return "requery"  # summing a stock across time periods double-counts
    return mode


# ── Value helpers ─────────────────────────────────────────────────────────────

def _to_number(value) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(str(value).replace(",", "").replace("₹", "").strip())
    except (ValueError, TypeError):
        return None


def _fmt(value: float, decimals: int = 2) -> str:
    if value == int(value):
        return f"{int(value):,}"
    return f"{value:,.{decimals}f}"


def _numeric_values(rows: list[dict], column: str) -> list[float]:
    values = (_to_number(row.get(column)) for row in rows)
    return [v for v in values if v is not None]


def _column_map(columns: list[ColumnMetadata]) -> dict[str, ColumnMetadata]:
    return {c.name: c for c in columns}


def _label_column(columns: list[ColumnMetadata], rows: list[dict]) -> str | None:
    """First dimension (else temporal) column — used to name rows in narration."""
    for wanted in (ColumnType.DIMENSION, ColumnType.TEMPORAL):
        for c in columns:
            if c.column_type == wanted:
                return c.name
    if rows:
        for name in rows[0]:
            if _to_number(rows[0][name]) is None:
                return name
    return None


def _match_column_name(requested: str, columns: list[ColumnMetadata]) -> str | None:
    """Loose name match against any column, exact first then substring."""
    wanted = requested.strip().lower().replace(" ", "_")
    for c in columns:
        if c.name.lower() == wanted:
            return c.name
    for c in columns:
        if wanted in c.name.lower() or c.name.lower() in wanted:
            return c.name
    return None


def _resolve_column(
    requested: str | None,
    columns: list[ColumnMetadata],
    rows: list[dict],
) -> str | None:
    """Match a (possibly loose) column reference; default to the first measure."""
    if requested:
        return _match_column_name(requested, columns)
    for preferred in (
        ColumnType.ADDITIVE_VALUE,
        ColumnType.ADDITIVE_COUNT,
        ColumnType.SNAPSHOT_STOCK,
        ColumnType.RATIO,
    ):
        for c in columns:
            if c.column_type == preferred and _numeric_values(rows, c.name):
                return c.name
    for c in columns:
        if _numeric_values(rows, c.name):
            return c.name
    return None


def _rejected(operation: str, answer: str, column: str | None = None) -> OperationResult:
    return OperationResult(
        operation=operation, mode=OperationMode.REJECTED, answer=answer, column=column,
    )


# ── Entry point ───────────────────────────────────────────────────────────────

# Re-query hook: (comparator_slot, comparator_value) -> rows of the same
# template with that one bound parameter swapped. Raises on failure.
RequeryFn = Callable[[str, str], list[dict]]


def run_operation(
    request: OperationRequest,
    frame: ContextFrame,
    rows: list[dict],
    requery: RequeryFn | None = None,
) -> OperationResult:
    op = request.operation.strip().lower()
    if op not in OPERATIONS:
        return _rejected(op, f"'{request.operation}' is not a supported operation.")
    if not rows and op != "compare":
        return _rejected(op, "The current result table is empty — nothing to compute.")

    columns = frame.result_set.columns

    if op == "count":
        return OperationResult(
            operation=op, mode=OperationMode.CLIENT, value=float(len(rows)),
            answer=f"The table has {len(rows):,} row{'s' if len(rows) != 1 else ''}.",
        )

    if op == "filter_rows":
        return _filter_rows(request, columns, rows)

    if op == "compare":
        return _compare(request, frame, rows, requery)

    # These two target any column (dimensions included), so they resolve their
    # own column instead of going through the numeric default below.
    if op in ("mode", "count_distinct"):
        return _value_frequency_op(op, request, columns, rows)

    column = _resolve_column(request.column, columns, rows)
    if column is None:
        return _rejected(
            op,
            f"I couldn't find a numeric column matching '{request.column}' in this table."
            if request.column else
            "This table has no numeric column to compute on.",
        )
    meta = _column_map(columns).get(column, ColumnMetadata(name=column, column_type=ColumnType.UNCLASSIFIED))

    if op in _AGGREGATIONS:
        mode = aggregation_mode(meta, columns)
        if mode == "invalid":
            return _rejected(op, f"'{column}' is not a measure column, so it can't be aggregated.", column)
        if mode == "requery":
            reason = (
                f"'{column}' is a rate/ratio — a {op.replace('_', ' ')} over displayed rows would be an "
                "unweighted mean, which is statistically wrong. Ask the underlying question "
                "(e.g. the state-wide or period-total version) so it's computed from base data."
                if meta.column_type == ColumnType.RATIO else
                f"'{column}' is a point-in-time stock and this table spans time periods — "
                f"a {op.replace('_', ' ')} would double-count. Ask for the figure as of a single date."
                if meta.column_type == ColumnType.SNAPSHOT_STOCK else
                f"'{column}' isn't verified as safely additive, so I won't {op.replace('_', ' ')} it here. "
                "Ask the question directly so it's computed from base data."
            )
            return _rejected(op, reason, column)

    if op in ("sum", "average", "min", "max"):
        return _scalar_op(op, column, meta, columns, rows)
    if op in ("median", "stdev", "percentile", "range"):
        return _distribution_op(op, request, column, columns, rows)
    if op == "share_of_total":
        return _share_of_total(request, column, columns, rows)
    if op == "percent_change":
        return _percent_change(column, columns, rows)
    if op == "sort":
        return _sort(request, column, columns, rows)
    if op in ("top_n", "bottom_n"):
        return _top_bottom(op, request, column, columns, rows)

    return _rejected(op, f"'{op}' is not implemented.")


# ── Implementations ───────────────────────────────────────────────────────────

def _scalar_op(
    op: str,
    column: str,
    meta: ColumnMetadata,
    columns: list[ColumnMetadata],
    rows: list[dict],
) -> OperationResult:
    values = _numeric_values(rows, column)
    if not values:
        return _rejected(op, f"'{column}' has no numeric values to compute on.", column)

    label_col = _label_column(columns, rows)
    if op == "sum":
        value = sum(values)
        answer = f"Total {column} across {len(values):,} rows: {_fmt(value)}."
    elif op == "average":
        value = sum(values) / len(values)
        answer = f"Average {column} across {len(values):,} rows: {_fmt(value)}."
    else:
        pick = min if op == "min" else max
        value = pick(values)
        row = next((r for r in rows if _to_number(r.get(column)) == value), None)
        where = f" ({row[label_col]})" if row and label_col and row.get(label_col) is not None else ""
        answer = f"{'Lowest' if op == 'min' else 'Highest'} {column}: {_fmt(value)}{where}."

    return OperationResult(
        operation=op, mode=OperationMode.CLIENT, answer=answer, column=column, value=value,
    )


def _ordinal(n: int) -> str:
    if 11 <= n % 100 <= 13:
        return f"{n}th"
    return f"{n}{ {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th') }"


def _distribution_op(
    op: str,
    request: OperationRequest,
    column: str,
    columns: list[ColumnMetadata],
    rows: list[dict],
) -> OperationResult:
    """Distribution statistics over the displayed rows. These describe the rows
    as shown (each row weighted equally), so unlike sum/average they are safe on
    any measure type — the narration says so explicitly."""
    values = _numeric_values(rows, column)
    if not values:
        return _rejected(op, f"'{column}' has no numeric values to compute on.", column)
    n_rows = len(values)

    if op == "median":
        value = float(statistics.median(values))
        answer = f"Median {column} across the {n_rows:,} rows shown: {_fmt(value)}."

    elif op == "stdev":
        if n_rows < 2:
            return _rejected(op, "Standard deviation needs at least two numeric values.", column)
        value = statistics.stdev(values)
        answer = (
            f"Standard deviation of {column} across the {n_rows:,} rows shown: "
            f"{_fmt(value)} (sample)."
        )

    elif op == "percentile":
        if request.n is None:
            return _rejected(op, "Tell me which percentile you want (e.g. 90).", column)
        if not 0 <= request.n <= 100:
            return _rejected(op, f"{request.n} is not a valid percentile (0–100).", column)
        ordered = sorted(values)
        rank = request.n / 100 * (n_rows - 1)
        lo, frac = int(rank), rank - int(rank)
        value = ordered[lo] if frac == 0 else ordered[lo] + frac * (ordered[lo + 1] - ordered[lo])
        answer = (
            f"{_ordinal(request.n)} percentile of {column} across the "
            f"{n_rows:,} rows shown: {_fmt(value)}."
        )

    else:  # range
        low, high = min(values), max(values)
        value = high - low
        label_col = _label_column(columns, rows)

        def _where(target: float) -> str:
            row = next((r for r in rows if _to_number(r.get(column)) == target), None)
            if row and label_col and row.get(label_col) is not None:
                return f" ({row[label_col]})"
            return ""

        answer = (
            f"{column} ranges from {_fmt(low)}{_where(low)} to {_fmt(high)}{_where(high)} "
            f"across the {n_rows:,} rows shown — a spread of {_fmt(value)}."
        )

    return OperationResult(
        operation=op, mode=OperationMode.CLIENT, answer=answer, column=column, value=value,
    )


def _value_frequency_op(
    op: str,
    request: OperationRequest,
    columns: list[ColumnMetadata],
    rows: list[dict],
) -> OperationResult:
    """mode / count_distinct — work on any column; default to the first dimension."""
    if request.column:
        column = _match_column_name(request.column, columns)
        if column is None:
            return _rejected(op, f"No column matching '{request.column}' in this table.")
    else:
        column = next(
            (c.name for c in columns if c.column_type == ColumnType.DIMENSION), None
        ) or (next(iter(rows[0]), None) if rows else None)
    if column is None:
        return _rejected(op, "This table has no column to compute on.")

    values = [str(row[column]).strip() for row in rows if row.get(column) is not None]
    if not values:
        return _rejected(op, f"'{column}' has no values to compute on.", column)
    counts = Counter(values)

    if op == "count_distinct":
        distinct = len(counts)
        return OperationResult(
            operation=op, mode=OperationMode.CLIENT, column=column, value=float(distinct),
            answer=(
                f"{column} has {distinct:,} distinct value{'s' if distinct != 1 else ''} "
                f"across the {len(values):,} rows shown."
            ),
        )

    top_count = max(counts.values())
    if top_count == 1:
        return OperationResult(
            operation=op, mode=OperationMode.CLIENT, column=column,
            answer=(
                f"Every value of {column} appears exactly once in the "
                f"{len(values):,} rows shown — there is no most common value."
            ),
        )
    modes = sorted(v for v, c in counts.items() if c == top_count)
    if len(modes) == 1:
        answer = (
            f"Most common {column}: {modes[0]} "
            f"({top_count:,} of {len(values):,} rows)."
        )
    else:
        listed = ", ".join(modes[:3]) + (f" and {len(modes) - 3} more" if len(modes) > 3 else "")
        answer = (
            f"{len(modes)} values of {column} tie as most common "
            f"({top_count:,} rows each): {listed}."
        )
    value = _to_number(modes[0]) if len(modes) == 1 else None
    return OperationResult(
        operation=op, mode=OperationMode.CLIENT, column=column, value=value, answer=answer,
    )


def _share_of_total(
    request: OperationRequest,
    column: str,
    columns: list[ColumnMetadata],
    rows: list[dict],
) -> OperationResult:
    values = _numeric_values(rows, column)
    total = sum(values)
    if total == 0:
        return _rejected("share_of_total", f"Total of '{column}' is zero — shares are undefined.", column)

    label_col = _label_column(columns, rows)
    share_col = f"share_of_{column}_pct"
    result = []
    for row in rows:
        v = _to_number(row.get(column))
        result.append({**row, share_col: round(v / total * 100, 2) if v is not None else None})

    if request.label and label_col:
        wanted = request.label.strip().lower()
        match = next(
            (r for r in result if str(r.get(label_col, "")).strip().lower() == wanted),
            None,
        )
        if match is None:
            return _rejected(
                "share_of_total",
                f"No row with {label_col} = '{request.label}' in the current table.",
                column,
            )
        return OperationResult(
            operation="share_of_total", mode=OperationMode.CLIENT, column=column,
            value=match[share_col], result=result,
            answer=(
                f"{match[label_col]} accounts for {match[share_col]}% of total {column} "
                f"({_fmt(_to_number(match.get(column)) or 0)} of {_fmt(total)})."
            ),
        )

    top = max(
        (r for r in result if r[share_col] is not None),
        key=lambda r: r[share_col],
        default=None,
    )
    lead = (
        f" The largest share is {top[share_col]}%"
        + (f" ({top[label_col]})" if label_col and top.get(label_col) is not None else "")
        + "." if top else ""
    )
    return OperationResult(
        operation="share_of_total", mode=OperationMode.CLIENT, column=column, result=result,
        result_columns=columns + [ColumnMetadata(name=share_col, column_type=ColumnType.RATIO)],
        answer=f"Added each row's share of total {column} (total: {_fmt(total)}).{lead}",
    )


def _percent_change(
    column: str,
    columns: list[ColumnMetadata],
    rows: list[dict],
) -> OperationResult:
    temporal = next((c.name for c in columns if c.column_type == ColumnType.TEMPORAL), None)
    ordered = rows
    if temporal:
        ordered = sorted(rows, key=lambda r: str(r.get(temporal, "")))

    pairs = [
        (row, _to_number(row.get(column)))
        for row in ordered
        if _to_number(row.get(column)) is not None
    ]
    if len(pairs) < 2:
        return _rejected(
            "percent_change",
            f"Percent change needs at least two rows with numeric '{column}' values.",
            column,
        )
    (first_row, first), (last_row, last) = pairs[0], pairs[-1]
    if first == 0:
        return _rejected(
            "percent_change",
            f"The starting value of '{column}' is zero — percent change is undefined.",
            column,
        )

    change = (last - first) / abs(first) * 100
    label_col = temporal or _label_column(columns, rows)
    span = (
        f" from {first_row.get(label_col)} to {last_row.get(label_col)}"
        if label_col and first_row.get(label_col) is not None else ""
    )
    return OperationResult(
        operation="percent_change", mode=OperationMode.CLIENT, column=column,
        value=round(change, 2),
        answer=(
            f"{column}{span}: {_fmt(first)} → {_fmt(last)}, "
            f"a change of {change:+.1f}%."
        ),
    )


def _sort(
    request: OperationRequest,
    column: str,
    columns: list[ColumnMetadata],
    rows: list[dict],
) -> OperationResult:
    descending = (request.direction or "desc").lower() != "asc"
    ordered = sorted(
        rows,
        key=lambda r: (_to_number(r.get(column)) is None, _to_number(r.get(column)) or 0),
        reverse=descending,
    )
    return OperationResult(
        operation="sort", mode=OperationMode.CLIENT, column=column, result=ordered,
        result_columns=columns,
        answer=f"Sorted by {column}, {'highest first' if descending else 'lowest first'}.",
    )


def _top_bottom(
    op: str,
    request: OperationRequest,
    column: str,
    columns: list[ColumnMetadata],
    rows: list[dict],
) -> OperationResult:
    n = max(1, request.n or 5)
    descending = op == "top_n"
    ordered = [r for r in rows if _to_number(r.get(column)) is not None]
    ordered.sort(key=lambda r: _to_number(r.get(column)), reverse=descending)
    sliced = ordered[:n]
    if not sliced:
        return _rejected(op, f"'{column}' has no numeric values to rank.", column)

    label_col = _label_column(columns, rows)
    lead_row = sliced[0]
    lead = (
        f" {lead_row[label_col]} leads with {_fmt(_to_number(lead_row.get(column)))}."
        if label_col and lead_row.get(label_col) is not None else ""
    )
    which = "Top" if descending else "Bottom"
    return OperationResult(
        operation=op, mode=OperationMode.CLIENT, column=column, result=sliced,
        result_columns=columns,
        answer=f"{which} {len(sliced)} rows by {column}.{lead}",
    )


_FILTER_OPS: dict[str, Callable[[float, float], bool]] = {
    ">":  lambda a, b: a > b,
    ">=": lambda a, b: a >= b,
    "<":  lambda a, b: a < b,
    "<=": lambda a, b: a <= b,
}


def _filter_rows(
    request: OperationRequest,
    columns: list[ColumnMetadata],
    rows: list[dict],
) -> OperationResult:
    if not request.filter_column or not request.filter_operator or request.filter_value is None:
        return _rejected("filter_rows", "Filtering needs a column, an operator, and a value.")

    column = _resolve_column(request.filter_column, columns, rows)
    if column is None:
        # Fall back to any (non-numeric) column by name for =/contains filters
        names = {c.name.lower(): c.name for c in columns}
        column = names.get(request.filter_column.strip().lower().replace(" ", "_"))
    if column is None:
        return _rejected("filter_rows", f"No column matching '{request.filter_column}' in this table.")

    op = request.filter_operator.strip()
    value = request.filter_value
    if op in _FILTER_OPS:
        threshold = _to_number(value)
        if threshold is None:
            return _rejected("filter_rows", f"'{value}' is not a number, so '{op}' can't be applied.")
        kept = [
            r for r in rows
            if (v := _to_number(r.get(column))) is not None and _FILTER_OPS[op](v, threshold)
        ]
    elif op in ("=", "=="):
        kept = [r for r in rows if str(r.get(column, "")).strip().lower() == str(value).strip().lower()]
    elif op == "!=":
        kept = [r for r in rows if str(r.get(column, "")).strip().lower() != str(value).strip().lower()]
    elif op == "contains":
        kept = [r for r in rows if str(value).strip().lower() in str(r.get(column, "")).lower()]
    else:
        return _rejected("filter_rows", f"'{op}' is not a supported filter operator.")

    return OperationResult(
        operation="filter_rows", mode=OperationMode.CLIENT, column=column, result=kept,
        result_columns=columns,
        answer=f"{len(kept):,} of {len(rows):,} rows where {column} {op} {value}.",
    )


def _compare(
    request: OperationRequest,
    frame: ContextFrame,
    rows: list[dict],
    requery: RequeryFn | None,
) -> OperationResult:
    if requery is None:
        return _rejected("compare", "Comparison re-query is not available right now.")
    if not request.comparator:
        return _rejected("compare", "Tell me what to compare with (e.g. another district).")

    slot = request.comparator_slot
    if slot and slot not in frame.bound_params:
        return _rejected(
            "compare",
            f"The current question has no '{slot}' parameter to swap "
            f"(it has: {', '.join(frame.bound_params) or 'none'}).",
        )
    if not slot:
        slot = next((s for s in frame.bound_params if s not in ("year", "month")), None)
    if not slot:
        return _rejected(
            "compare",
            "The current question has no swappable parameter — comparison needs an "
            "entity-scoped result (e.g. a specific district).",
        )

    base_value = frame.bound_params[slot]
    slot_col = f"compared_{slot}"
    merged: list[dict] = [{slot_col: base_value, **row} for row in rows]
    for value in request.comparator[:3]:
        try:
            peer_rows = requery(slot, value)
        except Exception as ex:
            return _rejected("compare", f"Couldn't re-run the query for '{value}': {ex}")
        merged.extend({slot_col: value, **row} for row in peer_rows)

    columns = [ColumnMetadata(name=slot_col, column_type=ColumnType.DIMENSION)] + list(
        frame.result_set.columns
    )
    entities = [base_value] + list(request.comparator[:3])
    answer = f"Comparison of {slot}: {' vs '.join(str(e) for e in entities)}."

    # Single-row-per-entity results get a numeric narration of the differences.
    if len(rows) == 1 and len(merged) == len(entities):
        deltas = []
        for col in frame.result_set.columns:
            if col.column_type not in _MEASURE_TYPES:
                continue
            vals = [_to_number(r.get(col.name)) for r in merged]
            if any(v is None for v in vals):
                continue
            deltas.append(f"{col.name}: " + " vs ".join(_fmt(v) for v in vals))
            if len(deltas) == 4:
                break
        if deltas:
            answer += " " + "; ".join(deltas) + "."

    return OperationResult(
        operation="compare", mode=OperationMode.REQUERY, result=merged,
        result_columns=columns, answer=answer,
    )
