"""Location container schema (spec §5.1)."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


LocationType = Literal[
    "Mileage Store",
    "Pickup Location",
    "Distribution Center",
    "Road Exit",
    "Freight Delivery",
    "Unknown",
]


class Address(BaseModel):
    model_config = ConfigDict(extra="ignore")
    street: str | None = None
    city: str | None = None
    state: str | None = None
    postal: str | None = None
    phone: str | None = None


class Curfew(BaseModel):
    """Delivery time window for a store (HH:MM, 24h). ``None`` means no curfew."""
    start: str | None = None
    end: str | None = None


class GeoPoint(BaseModel):
    """GeoJSON Point for Cosmos spatial indexing."""
    type: Literal["Point"] = "Point"
    coordinates: list[float] = Field(..., min_length=2, max_length=2)
    """[longitude, latitude]"""


class Location(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    id: str
    location_code: str
    location_type: LocationType
    description: str | None = None
    address: Address = Field(default_factory=Address)
    coordinates: GeoPoint
    lat: float
    lon: float
    district_handle: str | None = None
    district_description: str | None = None
    curfew: Curfew = Field(default_factory=Curfew)
    bh_loc_code: str | None = None
    obc_loc_code: str | None = None
    is_enabled: bool = True
