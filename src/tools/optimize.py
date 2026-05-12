"""``optimize_route`` MCP tool — orchestrates Cosmos load → solver → persist."""
from __future__ import annotations

import asyncio
import time
import uuid
from datetime import UTC, datetime

from src.config import get_settings
from src.data.location_repo import LocationRepo
from src.data.order_repo import OrderRepo
from src.data.route_repo import RouteRepo
from src.data.trailer_repo import TrailerRepo
from src.logging_config import get_logger
from src.models.location import Location
from src.models.requests import OptimizeRouteRequest, OptimizeRouteResponse
from src.models.route import (
    ComplianceReport,
    Depot,
    RouteHistory,
    RouteRequestSnapshot,
    RouteResult,
    RouteSummary,
    VehicleRoute,
)
from src.server import mcp
from src.services.azure_maps import get_matrix
from src.services.solver import (
    SolverSolution,
    StopInput,
    VehicleInput,
    solve_cvrptw,
)

log = get_logger(__name__)


def _curfew_to_seconds(hhmm: str | None) -> int | None:
    if not hhmm:
        return None
    try:
        h, m = hhmm.split(":")
        return int(h) * 3600 + int(m) * 60
    except ValueError:
        return None


async def _build_stop_inputs(
    depot: Location,
    store_locations: list[Location],
    order_totals_by_dest: dict[str, tuple[int, int]],
) -> list[StopInput]:
    stops: list[StopInput] = [
        StopInput(code=depot.location_code, lat=depot.lat, lon=depot.lon, service_sec=0)
    ]
    for loc in store_locations:
        weight, cubes = order_totals_by_dest.get(loc.location_code, (0, 0))
        start = _curfew_to_seconds(loc.curfew.start)
        end = _curfew_to_seconds(loc.curfew.end)
        # The spec stores curfews as "do-not-deliver" windows (e.g. 22:00-07:00).
        # In this skeleton we treat any present window as the *allowed* delivery window.
        # Refining this is a constraint-engine TODO.
        stops.append(
            StopInput(
                code=loc.location_code,
                lat=loc.lat,
                lon=loc.lon,
                weight_lbs=weight,
                cubes=cubes,
                service_sec=30 * 60,  # 30-minute fixed service time
                window_start_sec=start,
                window_end_sec=end if start is not None and end is not None and end > start else None,
            )
        )
    return stops


def _solver_to_result(
    solution: SolverSolution,
    stops: list[StopInput],
    trailer_id: str,
    cube_limit: int,
    weight_capacity: int,
) -> RouteResult:
    routes: list[VehicleRoute] = []
    for r in solution.routes:
        codes = [stops[i].code for i in r.stop_indices]
        weight_util = (r.weight_lbs / weight_capacity * 100.0) if weight_capacity else 0.0
        cube_util = (r.cubes / cube_limit * 100.0) if cube_limit else 0.0
        routes.append(
            VehicleRoute(
                vehicle=r.vehicle,
                trailer_type=trailer_id,
                stops=codes,
                stop_count=len(codes) - 2,  # exclude start/end depot
                distance_m=r.distance_m,
                duration_min=round(r.duration_sec / 60.0, 1),
                weight_lbs=r.weight_lbs,
                cubes=r.cubes,
                cube_limit=cube_limit,
                cube_limit_used=cube_limit,
                weight_utilization_pct=round(weight_util, 2),
                cube_utilization_pct=round(cube_util, 2),
            )
        )
    summary = RouteSummary(
        total_distance_m=solution.total_distance_m,
        vehicles_used=len(routes),
        avg_weight_utilization_pct=(
            round(sum(r.weight_utilization_pct for r in routes) / len(routes), 2)
            if routes else None
        ),
        avg_cube_utilization_pct=(
            round(sum(r.cube_utilization_pct for r in routes) / len(routes), 2)
            if routes else None
        ),
    )
    return RouteResult(
        status=solution.status,  # type: ignore[arg-type]
        trailer_type=trailer_id,
        routes=routes,
        summary=summary,
        compliance=ComplianceReport(status="not_evaluated"),
    )


@mcp.tool()
async def optimize_route(req: OptimizeRouteRequest) -> OptimizeRouteResponse:
    """Solve a CVRPTW for the given stops and trailer.

    Skeleton scope: distance + weight + time-window only. Cube uses the trailer's
    max (1-stop) capacity; stop-dependent degradation, lead/pup splits, and
    state restrictions are deferred (compliance status will be ``not_evaluated``).
    """
    settings = get_settings()
    log.info("optimize_route.start", **req.model_dump())

    loc_repo = LocationRepo()
    trailer_repo = TrailerRepo()
    order_repo = OrderRepo()

    depot_task = loc_repo.get_by_code(req.dc_code)
    stops_task = loc_repo.get_many_by_codes(req.stops)
    trailer_task = trailer_repo.find_by_id(req.trailer_type)

    depot, store_locations, trailer = await asyncio.gather(depot_task, stops_task, trailer_task)
    if depot is None:
        raise ValueError(f"Depot '{req.dc_code}' not found in locations container.")
    if trailer is None:
        raise ValueError(f"Trailer type '{req.trailer_type}' not found.")
    found_codes = {loc.location_code for loc in store_locations}
    missing = [s for s in req.stops if s not in found_codes]
    if missing:
        raise ValueError(f"Unknown stop codes: {missing}")

    # Order totals per destination (for the requested order_group, if any).
    totals_by_dest: dict[str, tuple[int, int]] = {}
    if req.order_group:
        boards = await order_repo.list_by_group(req.order_group)
        totals_by_dest = {
            b.destination: (int(b.totals.weight_lbs), int(b.totals.cubes)) for b in boards
        }

    stops = await _build_stop_inputs(depot, store_locations, totals_by_dest)

    matrix = await get_matrix(
        [(s.code, s.lat, s.lon) for s in stops],
        profile=req.profile,
    )

    cube_limit = trailer.cube_limit_for(num_stops=max(1, len(stops) - 1))
    vehicles = [
        VehicleInput(
            name=f"V{i + 1}",
            weight_capacity_lbs=trailer.total_weight_max_lbs,
            cube_capacity=cube_limit,
        )
        for i in range(req.num_vehicles)
    ]

    started = time.perf_counter()
    solution: SolverSolution = await asyncio.to_thread(
        solve_cvrptw,
        stops,
        vehicles,
        matrix,
        depot_index=0,
        max_solver_seconds=req.max_solver_seconds,
    )
    elapsed = time.perf_counter() - started

    result = _solver_to_result(
        solution,
        stops,
        trailer_id=trailer.id,
        cube_limit=cube_limit,
        weight_capacity=trailer.total_weight_max_lbs,
    )

    history = RouteHistory(
        id=str(uuid.uuid4()),
        dc_code=req.dc_code or settings.default_dc_code,
        order_group=req.order_group,
        created_at=datetime.now(UTC),
        request=RouteRequestSnapshot(
            depot=Depot(lat=depot.lat, lon=depot.lon),
            district=req.district,
            stops=req.stops,
            trailer_type=req.trailer_type,
            profile=req.profile,
            objective=req.objective,
        ),
        result=result,
        solver_time_sec=round(elapsed, 3),
    )
    await RouteRepo().upsert(history)

    log.info(
        "optimize_route.done",
        history_id=history.id,
        status=result.status,
        vehicles_used=result.summary.vehicles_used,
        elapsed=elapsed,
    )
    return OptimizeRouteResponse(history_id=history.id, result=result)
