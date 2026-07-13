"""Session-scoped analytical context frames."""
from __future__ import annotations

import calendar
import hashlib
import json
import threading
import time
from dataclasses import dataclass, field
from typing import Callable

from .column_metadata import metadata_for_result
from .models import (
    ActiveFilter,
    ColumnMetadata,
    ColumnType,
    ContextFrame,
    ContextFrameSnapshot,
    PendingClarification,
    ResultSetReference,
    RouteResult,
    TimeRange,
)


def _resolved_time_range(result: RouteResult, bound_params: dict[str, str]) -> TimeRange:
    year = bound_params.get("year")
    month = bound_params.get("month")
    if year and month:
        month_number = int(month)
        last_day = calendar.monthrange(int(year), month_number)[1]
        return TimeRange(
            start=f"{year}-{month_number:02d}-01",
            end=f"{year}-{month_number:02d}-{last_day:02d}",
            grain="month",
        )
    if year:
        return TimeRange(start=f"{year}-01-01", end=f"{year}-12-31", grain="year")
    if result.date_filter_applied and result.start_date and result.end_date:
        return TimeRange(start=result.start_date, end=result.end_date, grain="day")
    return TimeRange(start=None, end=None, grain="all_time")


def _result_reference_id(
    query_id: str,
    bound_params: dict[str, str],
    time_range: TimeRange,
) -> str:
    payload = json.dumps(
        {
            "query_id": query_id,
            "bound_params": bound_params,
            "time_range": time_range.model_dump(),
        },
        sort_keys=True,
    )
    return "rs_" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def build_context_frame(
    result: RouteResult,
    declared_columns: list[ColumnMetadata] | None = None,
    template_question: str | None = None,
) -> ContextFrame | None:
    """Create a fully renderable frame from a successful catalog result."""
    if not result.query_id or result.result is None:
        return None

    bound_params = {
        entity.slot_name: str(entity.resolved_value)
        for entity in (result.entities or [])
    }
    active_filters = [
        ActiveFilter(dimension=name, value=value)
        for name, value in bound_params.items()
        if name not in {"year", "month"}
    ]
    columns = metadata_for_result(result.result, declared_columns)
    grouping_dimension = next(
        (column.name for column in columns if column.column_type == ColumnType.DIMENSION),
        None,
    )
    time_range = _resolved_time_range(result, bound_params)

    return ContextFrame(
        template_id=result.query_id,
        template_question=result.query_description or template_question,
        bound_params=bound_params,
        active_filters=active_filters,
        time_range=time_range,
        grouping_dimension=grouping_dimension,
        result_set=ResultSetReference(
            id=_result_reference_id(result.query_id, bound_params, time_range),
            row_count=len(result.result),
            columns=columns,
        ),
    )


@dataclass
class _StoredFrame:
    frame: ContextFrame
    rows: list[dict]
    last_active: float
    # Result rows for each history_stack entry, kept parallel so pop-back can
    # restore the exact table the user was looking at.
    history_rows: list[list[dict]] = field(default_factory=list)


class ContextStore:
    """Thread-safe in-process session store with inactivity expiry."""

    def __init__(
        self,
        inactivity_timeout_seconds: int = 30 * 60,
        history_depth: int = 10,
        clock: Callable[[], float] = time.monotonic,
    ):
        self.inactivity_timeout_seconds = inactivity_timeout_seconds
        self.history_depth = history_depth
        self._clock = clock
        self._sessions: dict[str, _StoredFrame] = {}
        self._pending: dict[str, tuple[PendingClarification, float]] = {}
        self._lock = threading.RLock()

    def _get_stored_unlocked(self, session_id: str, touch: bool) -> _StoredFrame | None:
        stored = self._sessions.get(session_id)
        if stored is None:
            return None
        now = self._clock()
        if now - stored.last_active >= self.inactivity_timeout_seconds:
            del self._sessions[session_id]
            return None
        if touch:
            stored.last_active = now
        return stored

    def _get_unlocked(self, session_id: str, touch: bool) -> ContextFrame | None:
        stored = self._get_stored_unlocked(session_id, touch)
        if stored is None:
            return None
        return stored.frame.model_copy(deep=True)

    def get(self, session_id: str) -> ContextFrame | None:
        with self._lock:
            return self._get_unlocked(session_id, touch=True)

    def get_with_rows(self, session_id: str) -> tuple[ContextFrame, list[dict]] | None:
        """Current frame plus the exact rows of its displayed result table."""
        with self._lock:
            stored = self._get_stored_unlocked(session_id, touch=True)
            if stored is None:
                return None
            return stored.frame.model_copy(deep=True), [dict(r) for r in stored.rows]

    def set_frame(
        self,
        session_id: str,
        frame: ContextFrame,
        rows: list[dict] | None = None,
    ) -> ContextFrame:
        with self._lock:
            previous = self._get_stored_unlocked(session_id, touch=False)
            history: list[ContextFrameSnapshot] = []
            history_rows: list[list[dict]] = []
            if previous is not None:
                history = list(previous.frame.history_stack)
                history_rows = list(previous.history_rows)
                history.append(
                    ContextFrameSnapshot.model_validate(
                        previous.frame.model_dump(exclude={"history_stack"})
                    )
                )
                history_rows.append(previous.rows)
            frame = frame.model_copy(deep=True)
            frame.history_stack = history[-self.history_depth:]
            self._sessions[session_id] = _StoredFrame(
                frame=frame,
                rows=[dict(r) for r in (rows or [])],
                last_active=self._clock(),
                history_rows=history_rows[-self.history_depth:],
            )
            return frame.model_copy(deep=True)

    def pop(self, session_id: str) -> tuple[ContextFrame, list[dict]] | None:
        """Restore the previous frame (breadcrumb back). None if no history."""
        with self._lock:
            stored = self._get_stored_unlocked(session_id, touch=True)
            if stored is None or not stored.frame.history_stack:
                return None
            snapshot = stored.frame.history_stack[-1]
            rows = stored.history_rows[-1] if stored.history_rows else []
            frame = ContextFrame.model_validate(
                {**snapshot.model_dump(),
                 "history_stack": [s.model_dump() for s in stored.frame.history_stack[:-1]]}
            )
            self._sessions[session_id] = _StoredFrame(
                frame=frame,
                rows=rows,
                last_active=self._clock(),
                history_rows=stored.history_rows[:-1],
            )
            return frame.model_copy(deep=True), [dict(r) for r in rows]

    def set_pending(self, session_id: str, pending: PendingClarification) -> None:
        """Remember the question the router paused on, awaiting an answer."""
        with self._lock:
            self._pending[session_id] = (pending.model_copy(deep=True), self._clock())

    def take_pending(self, session_id: str) -> PendingClarification | None:
        """One-shot: return and clear the pending question (None if expired)."""
        with self._lock:
            entry = self._pending.pop(session_id, None)
            if entry is None:
                return None
            pending, stored_at = entry
            if self._clock() - stored_at >= self.inactivity_timeout_seconds:
                return None
            return pending

    def reset(self, session_id: str) -> None:
        with self._lock:
            self._sessions.pop(session_id, None)
            self._pending.pop(session_id, None)

