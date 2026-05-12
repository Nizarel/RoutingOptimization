"""Tool request/response models (spec §7)."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from src.models.order import OrderBoard
from src.models.restriction import StateRestriction
from src.models.route import RouteResult


# --- optimize_route ---

class OptimizeRouteRequest(BaseModel):
    dc_code: str = "52-DC"
    order_group: str | None = None
    district: str | None = None
    stops: list[str] = Field(..., min_length=1)
    trailer_type: str
    num_vehicles: int = Field(default=1, ge=1, le=50)
    profile: str = "truck"
    max_solver_seconds: int = Field(default=30, ge=1, le=300)
    objective: Literal["min_total_distance", "min_longest_route"] = "min_total_distance"
    enforce_state_restrictions: bool = True
    enforce_curfews: bool = True


class OptimizeRouteResponse(BaseModel):
    history_id: str
    result: RouteResult


# --- ingest tools ---

class IngestLocationsRequest(BaseModel):
    file_path: str
    locations_sheet: str = "Locations"
    trailer_sheet: str = "Max weight and Cube"
    trailer_header_row: int = 6  # header lives on Excel row 7 in the customer workbook
    restriction_sheet: str = "By State Combo and Weight"


class IngestLocationsResponse(BaseModel):
    locations_loaded: int
    trailer_types_loaded: int
    state_restrictions_loaded: int
    districts_derived: int


class IngestOrderBoardRequest(BaseModel):
    file_path: str
    sheet_name: str = "Orders"


class IngestOrderBoardResponse(BaseModel):
    order_group: str | None
    order_lines_read: int
    boards_upserted: int


# --- query tools ---

class GetStoreOrdersRequest(BaseModel):
    order_group: str
    destination: str | None = None
    district: str | None = None


class GetStoreOrdersResponse(BaseModel):
    boards: list[OrderBoard]


class GetRestrictionsRequest(BaseModel):
    state: str | None = None
    trailer_class: Literal["Combo", "Single"] | None = None


class GetRestrictionsResponse(BaseModel):
    restrictions: list[StateRestriction]
