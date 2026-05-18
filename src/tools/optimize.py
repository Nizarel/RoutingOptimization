"""``optimize_route`` MCP tool — orchestrates Cosmos load → solver → persist."""
from __future__ import annotations

import asyncio
import time
import uuid
from datetime import UTC, datetime

from src.config import get_settings
from src.data.location_repo import LocationRepo
from src.data.matrix_repo import MatrixCacheRepo
from src.data.order_repo import OrderRepo
from src.data.route_repo import RouteRepo
from src.data.trailer_repo import TrailerRepo
from src.logging_config import get_logger
from src.models.location import Location
from src.models.matrix import MatrixCacheEntry
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
from src.models.trailer import TrailerType
from src.server import mcp
from src.services.azure_maps import get_matrix, matrix_from_cache, to_sorted_cache_entry
from src.services.constraint_engine import ConstraintEngine
from src.services.curfew import primary_window
from src.services.solver import (
    SolverSolution,
    StopInput,
    VehicleInput,
    solve_cvrptw_with_degradation,
)

log = get_logger(__name__)


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
        # Spec semantics: ``curfew`` is a do-not-deliver window. ``primary_window``
        # returns the widest *allowed* delivery window (handles overnight curfews).
        win_start, win_end = primary_window(loc.curfew)
        stops.append(
            StopInput(
                code=loc.location_code,
                lat=loc.lat,
                lon=loc.lon,
                weight_lbs=weight,
                cubes=cubes,
                service_sec=30 * 60,  # 30-minute fixed service time
                window_start_sec=win_start,
                window_end_sec=win_end,
            )
        )
    return stops


def _bin_pack_lead_pup(weight_lbs: int, trailer: TrailerType) -> tuple[int, int]:
    """Split a vehicle's total weight into (lead, pup) honouring trailer maxes.

    Simple greedy: lead first up to ``lead_weight_max_lbs``, remainder to pup.
    For Single trailers the entire load goes on the lead.
    """
    if trailer.trailer_class == "Single" or trailer.pup_weight_max_lbs == 0:
        return weight_lbs, 0
    lead = min(weight_lbs, trailer.lead_weight_max_lbs)
    pup = weight_lbs - lead
    return lead, pup


def _states_traversed(
    codes: list[str], locations_by_code: dict[str, Location]
) -> list[str]:
    seen: list[str] = []
    for code in codes:
        loc = locations_by_code.get(code)
        if loc is None or not loc.address.state:
            continue
        st = loc.address.state
        if st not in seen:
            seen.append(st)
    return seen


def _solver_to_result(
    solution: SolverSolution,
    stops: list[StopInput],
    trailer: TrailerType,
    locations_by_code: dict[str, Location],
    engine: ConstraintEngine | None,
    depot_code: str,
    enforce: bool,
) -> RouteResult:
    routes: list[VehicleRoute] = []
    weight_capacity = trailer.total_weight_max_lbs
    for r in solution.routes:
        codes = [stops[i].code for i in r.stop_indices]
        stop_count = max(0, len(codes) - 2)
        cube_limit = trailer.cube_limit_for(num_stops=max(1, stop_count))
        weight_util = (r.weight_lbs / weight_capacity * 100.0) if weight_capacity else 0.0
        cube_util = (r.cubes / cube_limit * 100.0) if cube_limit else 0.0
        lead, pup = _bin_pack_lead_pup(int(r.weight_lbs), trailer)
        routes.append(
            VehicleRoute(
                vehicle=r.vehicle,
                trailer_type=trailer.id,
                stops=codes,
                stop_count=stop_count,
                distance_m=r.distance_m,
                duration_min=round(r.duration_sec / 60.0, 1),
                weight_lbs=r.weight_lbs,
                lead_weight_lbs=lead,
                pup_weight_lbs=pup,
                cubes=r.cubes,
                cube_limit=cube_limit,
                cube_limit_used=cube_limit,
                weight_utilization_pct=round(weight_util, 2),
                cube_utilization_pct=round(cube_util, 2),
                states_traversed=_states_traversed(codes, locations_by_code),
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

    if engine is not None and enforce and routes:
        reports = [engine.evaluate_route(rt, ignore_depot_codes={depot_code}) for rt in routes]
        compliance = ConstraintEngine.merge_compliance(reports)
    else:
        compliance = ComplianceReport(status="not_evaluated")

    return RouteResult(
        status=solution.status,  # type: ignore[arg-type]
        trailer_type=trailer.id,
        routes=routes,
        summary=summary,
        compliance=compliance,
    )


@mcp.tool()
async def optimize_route(req: OptimizeRouteRequest) -> OptimizeRouteResponse:
    """Solve a CVRPTW for the given stops and trailer.

    Sprint 4 scope: distance + weight + time + iterative cube degradation
    (spec §9.2), curfew windows from do-not-deliver data, state-restriction
    pre-filter (spec §9.3), post-solve compliance report (states, interstate
    proximity, cube), and lead/pup weight split (spec §9.4).
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

    # ── Constraint engine (loaded with depot + stops) ──────────────────────
    engine = await ConstraintEngine.load(location_codes=[req.dc_code, *req.stops])
    locations_by_code: dict[str, Location] = {depot.location_code: depot}
    for loc in store_locations:
        locations_by_code[loc.location_code] = loc

    # State-restriction pre-filter (spec §9.3)
    if req.enforce_state_restrictions:
        states_in_route = sorted({
            loc.address.state for loc in store_locations if loc.address.state
        })
        if states_in_route:
            allowed = set(engine.get_allowed_trailers(states_in_route))
            if req.trailer_type not in allowed:
                log.info(
                    "optimize_route.state_prefilter_fail",
                    trailer=req.trailer_type,
                    states=states_in_route,
                    allowed=sorted(allowed),
                )
                infeasible = RouteResult(
                    status="infeasible",
                    trailer_type=req.trailer_type,
                    routes=[],
                    summary=RouteSummary(total_distance_m=0.0, vehicles_used=0),
                    compliance=ComplianceReport(
                        status="evaluated",
                        state_restrictions_passed=False,
                        state_violations=[
                            f"trailer={req.trailer_type} not allowed in states={states_in_route}"
                        ],
                        evaluated_at=datetime.now(UTC),
                    ),
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
                    result=infeasible,
                    solver_time_sec=0.0,
                )
                await RouteRepo().upsert(history)
                return OptimizeRouteResponse(history_id=history.id, result=infeasible)

    # Order totals per destination (for the requested order_group, if any).
    totals_by_dest: dict[str, tuple[int, int]] = {}
    if req.order_group:
        boards = await order_repo.list_by_group(req.order_group)
        totals_by_dest = {
            b.destination: (int(b.totals.weight_lbs), int(b.totals.cubes)) for b in boards
        }

    stops = await _build_stop_inputs(depot, store_locations, totals_by_dest)

    # ── Travel-time matrix (cache-first) ────────────────────────────────────
    stop_codes = [s.code for s in stops]
    sorted_codes = sorted(stop_codes)
    cache_repo = MatrixCacheRepo()
    matrix = None

    cache_entry = await cache_repo.get_cached(sorted_codes, req.profile)
    if cache_entry is not None:
        log.info("optimize_route.matrix_cache_hit", n=len(stops), profile=req.profile)
        matrix = matrix_from_cache(cache_entry, [(s.code, s.lat, s.lon) for s in stops])
    else:
        matrix = await get_matrix(
            [(s.code, s.lat, s.lon) for s in stops],
            profile=req.profile,
        )
        # Persist sorted copy to cache (24-hour TTL)
        sorted_data = to_sorted_cache_entry(matrix, req.profile)
        new_entry = MatrixCacheEntry(
            id=MatrixCacheRepo.make_key(sorted_codes),
            profile=req.profile,
            location_codes=sorted_data["sorted_codes"],
            location_count=len(sorted_codes),
            distance_matrix_m=sorted_data["distance_m"],
            time_matrix_sec=sorted_data["time_sec"],
            fetched_at=datetime.now(UTC),
        )
        await cache_repo.put_cached(new_entry)
        log.info("optimize_route.matrix_cached", n=len(stops), profile=req.profile)

    vehicles = [
        VehicleInput(
            name=f"V{i + 1}",
            weight_capacity_lbs=trailer.total_weight_max_lbs,
            cube_capacity=trailer.cube_by_stops[0],
        )
        for i in range(req.num_vehicles)
    ]

    started = time.perf_counter()
    solution: SolverSolution = await asyncio.to_thread(
        solve_cvrptw_with_degradation,
        stops,
        vehicles,
        matrix,
        cube_by_stops=trailer.cube_by_stops,
        depot_index=0,
        max_solver_seconds=req.max_solver_seconds,
    )
    elapsed = time.perf_counter() - started

    result = _solver_to_result(
        solution,
        stops,
        trailer=trailer,
        locations_by_code=locations_by_code,
        engine=engine,
        depot_code=depot.location_code,
        enforce=req.enforce_state_restrictions,
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
