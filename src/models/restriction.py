"""State trailer restriction schema (spec §5.3)."""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from src.models.trailer import TrailerClass


class StateRestriction(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    state: str
    trailer_type: str
    trailer_class: TrailerClass
    max_weight_lbs: int
    within_2mi_interstate_only: bool = False
    max_distance_from_interstate_mi: float | None = None
    notes: str | None = None
