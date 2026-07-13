from pydantic import BaseModel
from enum import Enum
from typing import Optional


class RouteTier(str, Enum):
    TIER1_DASHBOARD = "tier1"
    TIER2_TEMPLATE  = "tier2"
    FALLBACK        = "fallback"
    CLARIFY         = "clarify"   # paused before execution; user picks an interpretation


class Chip(BaseModel):
    """A tappable suggestion. send_text is what the tap submits as a message —
    it must always route to something the engine can execute."""
    label:     str
    send_text: str


class Clarification(BaseModel):
    reason:  str          # ambiguous_templates | missing_parameter | unknown_entity | broad_question
    prompt:  str
    options: list[Chip] = []


class PendingClarification(BaseModel):
    """The question the system paused on (spec Sec 6: pause BEFORE execution).
    Stored per session so the user's next message can resume it — 'For which
    district?' → 'lucknow' executes the pending template with context intact."""
    query_id:       str
    missing_slot:   str
    slot_type:      str
    filled:         dict[str, str]   # slot -> already-resolved value
    original_query: str


class ExtractedEntity(BaseModel):
    slot_name:      str
    raw_value:      str
    resolved_value: str
    entity_type:    str
    confidence:     str   # exact | alias | fuzzy

class ColumnType(str, Enum):
    DIMENSION       = "dimension"
    TEMPORAL        = "temporal"
    IDENTIFIER      = "identifier"
    ADDITIVE_COUNT  = "additive_count"
    ADDITIVE_VALUE  = "additive_value"
    RATIO           = "ratio"
    SNAPSHOT_STOCK  = "snapshot_stock"
    UNCLASSIFIED    = "unclassified"


class ColumnMetadata(BaseModel):
    name:        str
    column_type: ColumnType


class ActiveFilter(BaseModel):
    dimension: str
    operator:  str = "="
    value:     str


class TimeRange(BaseModel):
    start: str | None
    end:   str | None
    grain: str


class ResultSetReference(BaseModel):
    id:        str
    row_count: int
    columns:   list[ColumnMetadata]


class ContextFrameSnapshot(BaseModel):
    template_id:        str
    template_question:  Optional[str] = None   # canonical question, for breadcrumb rendering
    bound_params:       dict[str, str]
    active_filters:     list[ActiveFilter]
    time_range:         TimeRange
    grouping_dimension: str | None
    result_set:         ResultSetReference


class ContextFrame(ContextFrameSnapshot):
    history_stack: list[ContextFrameSnapshot] = []


class OperationMode(str, Enum):
    CLIENT   = "client"     # computed deterministically on the displayed table
    REQUERY  = "requery"    # recomputed through a catalog template
    REJECTED = "rejected"   # not executed; answer explains why / what to ask instead


class OperationRequest(BaseModel):
    operation:       str
    column:          Optional[str] = None        # target measure column
    label:           Optional[str] = None        # target row (dimension value), e.g. share of "Agra"
    n:               Optional[int] = None        # top_n / bottom_n
    direction:       Optional[str] = None        # asc | desc
    filter_column:   Optional[str] = None
    filter_operator: Optional[str] = None        # = != > >= < <= contains
    filter_value:    Optional[str] = None
    comparator:      Optional[list[str]] = None  # compare: entity values to re-query with
    comparator_slot: Optional[str] = None        # compare: which bound param to swap


class OperationResult(BaseModel):
    operation: str
    mode:      OperationMode
    answer:    str
    column:    Optional[str]        = None
    value:     Optional[float]      = None
    result:    Optional[list[dict]] = None
    result_columns: Optional[list[ColumnMetadata]] = None


class RouteResult(BaseModel):
    tier:              RouteTier
    entities:          Optional[list[ExtractedEntity]] = None
    query_description: Optional[str]                   = None
    fallback_message:  Optional[str]                   = None
    result:            Optional[list[dict]]             = None

    raw_query:        str
    normalized_query: str
    total_latency_ms: float

    start_date:          Optional[str] = None   # YYYY-MM-DD
    end_date:            Optional[str] = None   # YYYY-MM-DD
    date_filter_applied: bool          = False

    query_id: Optional[str] = None
    intent:   Optional[str] = None
    context_frame: Optional[ContextFrame] = None
    clarification: Optional[Clarification] = None
    suggestions:   Optional[list[Chip]]    = None
    pending:       Optional[PendingClarification] = None  # set alongside a clarify

    model_config = {"arbitrary_types_allowed": True}


class ClarificationNeeded(Exception):
    pass


class EntityNotFound(Exception):
    def __init__(self, entity_type: str, raw_value: str, suggestions: list[str]):
        self.entity_type = entity_type
        self.raw_value   = raw_value
        self.suggestions = suggestions
        super().__init__(
            f"Could not find a valid '{entity_type}' matching '{raw_value}'. "
            f"Did you mean: {', '.join(suggestions[:3])}?"
            if suggestions else
            f"Could not find a valid '{entity_type}' matching '{raw_value}'."
        )
