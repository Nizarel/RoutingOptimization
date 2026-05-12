"""Trailer type container schema (spec §5.2)."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

TrailerClass = Literal["Combo", "Single"]


class TrailerType(BaseModel):
    """Trailer configuration with stop-dependent cube degradation curve."""

    model_config = ConfigDict(extra="ignore")

    id: str
    trailer_class: TrailerClass
    trailer_type_description: str
    dollies: int = 0
    lead_weight_max_lbs: int
    pup_weight_max_lbs: int = 0
    total_weight_max_lbs: int
    cube_by_stops: list[int] = Field(
        ...,
        min_length=1,
        description="Cube limit indexed by (num_stops - 1).",
    )
    max_stops_supported: int

    def cube_limit_for(self, num_stops: int) -> int:
        """Return cube limit for ``num_stops``. Falls back to last entry if exceeded."""
        if num_stops <= 0:
            return self.cube_by_stops[0]
        idx = min(num_stops - 1, len(self.cube_by_stops) - 1)
        return self.cube_by_stops[idx]
