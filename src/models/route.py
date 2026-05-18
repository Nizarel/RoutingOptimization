"""Route history schema (spec §5.5)."""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Depot(BaseModel):
    lat: float
    lon: float


class RouteRequestSnapshot(BaseModel):
    """Snapshot of the optimize_route request (persisted with the result)."""

    model_config = ConfigDict(extra="ignore")

    depot: Depot
    district: str | None = None
    stops: list[str]
    trailer_type: str
    profile: str = "truck"
    objective: str = "min_total_distance"


class VehicleRoute(BaseModel):
    model_config = ConfigDict(extra="ignore")

    vehicle: str
    trailer_type: str
    stops: list[str]
    stop_count: int
    distance_m: float
    duration_min: float
    weight_lbs: float
    lead_weight_lbs: float | None = None
    pup_weight_lbs: float | None = None
    cubes: float
    cube_limit: int | None = None
    cube_limit_used: int | None = None
    weight_utilization_pct: float
    cube_utilization_pct: float
    states_traversed: list[str] = Field(default_factory=list)


class RouteSummary(BaseModel):
    total_distance_m: float
    vehicles_used: int
    avg_weight_utilization_pct: float | None = None
    avg_cube_utilization_pct: float | None = None
    avg_utilization_pct: float | None = None


class ComplianceReport(BaseModel):
    state_restrictions_passed: bool | None = None
    curfew_violations: int | None = None
    weight_violations: int | None = None
    state_violations: list[str] = Field(default_factory=list)
    interstate_violations: list[str] = Field(default_factory=list)
    cube_violations: list[str] = Field(default_factory=list)
    evaluated_at: datetime | None = None
    status: Literal["evaluated", "not_evaluated"] = "not_evaluated"


class RouteResult(BaseModel):
    status: Literal["optimal", "feasible", "infeasible", "timeout", "error"]
    trailer_type: str
    routes: list[VehicleRoute]
    summary: RouteSummary
    compliance: ComplianceReport = Field(default_factory=ComplianceReport)


class RouteHistory(BaseModel):
    """Persisted optimization result. Partition key = ``/dc_code``. TTL 90 days."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    id: str
    dc_code: str
    order_group: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    request: RouteRequestSnapshot
    result: RouteResult
    solver_time_sec: float
    ttl_seconds: int | None = Field(default=7_776_000, alias="_ttl")
