from pydantic import BaseModel
from enum import Enum
from typing import Optional


class RouteTier(str, Enum):
    TIER1_DASHBOARD = "tier1"
    TIER2_TEMPLATE  = "tier2"
    FALLBACK        = "fallback"


class ExtractedEntity(BaseModel):
    slot_name:      str
    raw_value:      str
    resolved_value: str
    entity_type:    str
    confidence:     str   # exact | alias | fuzzy


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
