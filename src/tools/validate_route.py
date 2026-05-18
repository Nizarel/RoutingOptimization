"""``validate_route`` MCP tool (FR-003).

Evaluates a route (loaded from ``route_history`` or supplied inline) against
the constraint engine and returns a compliance report plus a flat list of
violations.
"""
from __future__ import annotations

from src.data.route_repo import RouteRepo
from src.logging_config import get_logger
from src.models.requests import (
    RouteViolation,
    ValidateRouteRequest,
    ValidateRouteResponse,
)
from src.models.route import VehicleRoute
from src.server import mcp
from src.services.constraint_engine import ConstraintEngine

log = get_logger(__name__)


def _flatten_violations(route: VehicleRoute, report) -> list[RouteViolation]:  # type: ignore[no-untyped-def]
    out: list[RouteViolation] = []
    for detail in report.state_violations:
        if route.vehicle in detail:
            out.append(RouteViolation(vehicle=route.vehicle, category="state", detail=detail))
    for detail in report.interstate_violations:
        if route.vehicle in detail:
            out.append(RouteViolation(vehicle=route.vehicle, category="interstate", detail=detail))
    for detail in report.cube_violations:
        if route.vehicle in detail:
            out.append(RouteViolation(vehicle=route.vehicle, category="cube", detail=detail))
    return out


@mcp.tool()
async def validate_route(req: ValidateRouteRequest) -> ValidateRouteResponse:
    """Validate a route against state restrictions, interstate proximity, and cube limits.

    Supply either ``history_id`` + ``dc_code`` (loads from Cosmos) or an
    inline ``route`` payload.  Returns the aggregated ComplianceReport plus a
    per-vehicle list of violations.
    """
    log.info("validate_route.start", history_id=req.history_id, has_inline=req.route is not None)

    routes: list[VehicleRoute]
    if req.history_id is not None:
        if not req.dc_code:
            raise ValueError("dc_code is required when looking up by history_id")
        history = await RouteRepo().get_by_id(req.history_id, dc_code=req.dc_code)
        if history is None:
            raise ValueError(f"RouteHistory {req.history_id} not found in dc_code={req.dc_code}")
        routes = list(history.result.routes)
        depot_code = req.dc_code
        all_stop_codes = {c for r in routes for c in r.stops}
    elif req.route is not None:
        routes = [req.route]
        depot_code = req.route.stops[0] if req.route.stops else ""
        all_stop_codes = set(req.route.stops)
    else:
        raise ValueError("Either history_id or route must be provided")

    engine = await ConstraintEngine.load(location_codes=sorted(all_stop_codes))

    reports = [engine.evaluate_route(r, ignore_depot_codes={depot_code}) for r in routes]
    aggregated = ConstraintEngine.merge_compliance(reports)

    violations: list[RouteViolation] = []
    for r, rep in zip(routes, reports, strict=True):
        violations.extend(_flatten_violations(r, rep))

    log.info(
        "validate_route.done",
        passed=aggregated.state_restrictions_passed,
        violations=len(violations),
    )
    return ValidateRouteResponse(compliance=aggregated, violations=violations)
