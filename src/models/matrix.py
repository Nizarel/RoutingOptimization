"""Matrix cache and district schemas (spec §5.6 - 5.7)."""
from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field


class MatrixCacheEntry(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    id: str
    profile: str
    location_codes: list[str]
    location_count: int
    time_matrix_sec: list[list[float]]
    distance_matrix_m: list[list[float]]
    fetched_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    ttl_seconds: int | None = Field(default=86_400, alias="_ttl")


class District(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    dc_code: str
    district_handle: str
    description: str | None = None
    states: list[str] = Field(default_factory=list)
    store_count: int = 0
    store_codes: list[str] = Field(default_factory=list)
    banners: list[str] = Field(default_factory=list)
    allowed_trailer_types: list[str] = Field(default_factory=list)
    max_combo_weight_lbs: int | None = None
    has_interstate_restrictions: bool = False
    relay_points: list[str] = Field(default_factory=list)
