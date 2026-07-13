"""Catalog result-schema extraction and editable column-type tagging."""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

from .models import ColumnMetadata, ColumnType

_RULES_PATH = Path(__file__).with_name("column_types.json")


@lru_cache(maxsize=1)
def _load_rules() -> dict:
    return json.loads(_RULES_PATH.read_text(encoding="utf-8"))


def classify_column(name: str) -> ColumnType:
    """Classify a result column using the standalone, reviewable rule file."""
    normalized = name.strip().strip('"').lower()
    rules = _load_rules()
    exact = rules.get("exact", {})
    if normalized in exact:
        return ColumnType(exact[normalized])
    for rule in rules.get("patterns", []):
        if re.search(rule["pattern"], normalized, re.IGNORECASE):
            return ColumnType(rule["column_type"])
    return ColumnType(rules.get("fallback", "unclassified"))


def _keyword_at(text: str, index: int, keyword: str) -> bool:
    end = index + len(keyword)
    if text[index:end].upper() != keyword:
        return False
    before = text[index - 1] if index else " "
    after = text[end] if end < len(text) else " "
    return not (before.isalnum() or before == "_") and not (after.isalnum() or after == "_")


def _find_keyword_at_depth_zero(text: str, keyword: str, start: int = 0) -> int:
    depth = 0
    quote: str | None = None
    index = start
    while index < len(text):
        char = text[index]
        if quote:
            if char == quote:
                if index + 1 < len(text) and text[index + 1] == quote:
                    index += 2
                    continue
                quote = None
            index += 1
            continue
        if char in ("'", '"'):
            quote = char
        elif char == "(":
            depth += 1
        elif char == ")":
            depth = max(0, depth - 1)
        elif depth == 0 and _keyword_at(text, index, keyword):
            return index
        index += 1
    return -1


def _split_top_level_csv(text: str) -> list[str]:
    parts: list[str] = []
    start = 0
    depth = 0
    quote: str | None = None
    index = 0
    while index < len(text):
        char = text[index]
        if quote:
            if char == quote:
                if index + 1 < len(text) and text[index + 1] == quote:
                    index += 2
                    continue
                quote = None
        elif char in ("'", '"'):
            quote = char
        elif char == "(":
            depth += 1
        elif char == ")":
            depth = max(0, depth - 1)
        elif char == "," and depth == 0:
            parts.append(text[start:index].strip())
            start = index + 1
        index += 1
    tail = text[start:].strip()
    if tail:
        parts.append(tail)
    return parts


def _column_name(expression: str) -> str | None:
    expression = re.sub(r"^DISTINCT\s+", "", expression.strip(), flags=re.IGNORECASE)
    alias = re.search(r"\bAS\s+(?:\"([^\"]+)\"|([A-Za-z_][\w$]*))\s*$", expression, re.IGNORECASE)
    if alias:
        return alias.group(1) or alias.group(2)
    direct = re.fullmatch(r"(?:[A-Za-z_][\w$]*\.)?(?:\"([^\"]+)\"|([A-Za-z_][\w$]*))", expression)
    if direct:
        return direct.group(1) or direct.group(2)
    return None


def extract_result_columns(sql: str) -> list[str]:
    """Extract the outer SELECT list without executing catalog SQL."""
    sql = re.sub(r"--[^\n]*", "", sql)
    select_at = _find_keyword_at_depth_zero(sql, "SELECT")
    if select_at < 0:
        return []
    body_start = select_at + len("SELECT")
    from_at = _find_keyword_at_depth_zero(sql, "FROM", body_start)
    if from_at < 0:
        return []
    columns = []
    for expression in _split_top_level_csv(sql[body_start:from_at]):
        name = _column_name(expression)
        if name:
            columns.append(name)
    return columns


def metadata_for_columns(columns: list[str]) -> list[ColumnMetadata]:
    return [ColumnMetadata(name=name, column_type=classify_column(name)) for name in columns]


def build_catalog_column_metadata(
    dashboard_catalog: dict[str, dict],
    template_catalog: dict[str, dict],
) -> dict[str, list[ColumnMetadata]]:
    result: dict[str, list[ColumnMetadata]] = {}
    for query_id, entry in dashboard_catalog.items():
        result[query_id] = metadata_for_columns(extract_result_columns(entry["sql"]))
    for query_id, entry in template_catalog.items():
        result[query_id] = metadata_for_columns(extract_result_columns(entry["sql_template"]))
    return result


def metadata_for_result(
    rows: list[dict] | None,
    declared: list[ColumnMetadata] | None = None,
) -> list[ColumnMetadata]:
    """Prefer actual returned columns, falling back to the catalog declaration."""
    if not rows:
        return list(declared or [])
    declared_by_name = {column.name: column for column in (declared or [])}
    return [
        declared_by_name.get(name, ColumnMetadata(name=name, column_type=classify_column(name)))
        for name in rows[0].keys()
    ]
