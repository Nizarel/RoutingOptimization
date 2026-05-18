"""Tool request/response models (spec §7)."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from src.models.order import OrderBoard
from src.models.restriction import StateRestriction
from src.models.route import ComplianceReport, RouteResult, VehicleRoute


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


# --- matrix_travel_times ---

class MatrixTravelTimesRequest(BaseModel):
    location_codes: list[str] = Field(..., min_length=2)
    profile: str = "truck"
    use_cache: bool = True


class MatrixTravelTimesResponse(BaseModel):
    location_codes: list[str]
    distance_m: list[list[float]]
    time_sec: list[list[float]]
    from_cache: bool
    profile: str


# --- select_trailer ---

class SelectTrailerRequest(BaseModel):
    stops: list[str] = Field(..., min_length=1)
    states: list[str] | None = None
    total_weight_lbs: int = Field(..., ge=0)
    total_cubes: int = Field(..., ge=0)
    prefer: Literal["max_capacity", "min_class"] = "max_capacity"


class TrailerRecommendation(BaseModel):
    trailer_type: str
    trailer_class: Literal["Combo", "Single"]
    cube_limit: int
    weight_max_lbs: int
    cube_utilization_pct: float
    weight_utilization_pct: float
    reason: str


class SelectTrailerResponse(BaseModel):
    recommended: TrailerRecommendation | None
    alternatives: list[TrailerRecommendation] = Field(default_factory=list)
    states_considered: list[str]
    infeasible_reason: str | None = None


# --- validate_route ---

class ValidateRouteRequest(BaseModel):
    history_id: str | None = None
    dc_code: str | None = None
    route: VehicleRoute | None = None


class RouteViolation(BaseModel):
    vehicle: str
    category: Literal["state", "interstate", "cube", "weight", "curfew"]
    detail: str


class ValidateRouteResponse(BaseModel):
    compliance: ComplianceReport
    violations: list[RouteViolation] = Field(default_factory=list)
