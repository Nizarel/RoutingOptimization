"""Basic OR-Tools CVRPTW solver (skeleton).

This skeleton enforces:
  * **Distance** dimension (objective: minimize total)
  * **Weight** dimension (vehicle capacity)
  * **Time** dimension with optional per-stop time windows (curfews)

Deferred to the constraint engine plan:
  * Stop-dependent cube degradation
  * Lead/pup weight split for combo trailers
  * State-by-state trailer restriction filtering
  * Interstate proximity (MT 40+40 rule)

The solver is synchronous; callers should run it via :func:`asyncio.to_thread`.
"""
from __future__ import annotations

from dataclasses import dataclass

from ortools.constraint_solver import pywrapcp, routing_enums_pb2

from src.services.azure_maps import Matrix


@dataclass(slots=True)
class StopInput:
    """One stop (depot or store) given to the solver."""

    code: str
    lat: float
    lon: float
    weight_lbs: int = 0
    cubes: int = 0
    service_sec: int = 0
    # Time window in seconds from start-of-day (None = no window).
    window_start_sec: int | None = None
    window_end_sec: int | None = None


@dataclass(slots=True)
class VehicleInput:
    """One vehicle for the solver."""

    name: str
    weight_capacity_lbs: int
    cube_capacity: int
    max_route_seconds: int = 24 * 3600


@dataclass(slots=True)
class SolverRoute:
    vehicle: str
    stop_indices: list[int]   # indices into the original stop list (0 = depot)
    distance_m: float
    duration_sec: float
    weight_lbs: int
    cubes: int


@dataclass(slots=True)
class SolverSolution:
    status: str  # "optimal" | "feasible" | "infeasible" | "timeout"
    routes: list[SolverRoute]
    total_distance_m: float


_STATUS_MAP = {
    routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC: "PATH_CHEAPEST_ARC",
}


def solve_cvrptw(
    stops: list[StopInput],
    vehicles: list[VehicleInput],
    matrix: Matrix,
    *,
    depot_index: int = 0,
    max_solver_seconds: int = 30,
) -> SolverSolution:
    """Solve a CVRPTW with weight + time + distance dimensions.

    ``stops[depot_index]`` is the depot. All vehicles start and end there.
    """
    if len(stops) != len(matrix.location_codes):
        raise ValueError("stops and matrix size mismatch")
    if not vehicles:
        raise ValueError("at least one vehicle is required")

    n = len(stops)
    manager = pywrapcp.RoutingIndexManager(n, len(vehicles), depot_index)
    routing = pywrapcp.RoutingModel(manager)

    # --- Distance arc cost (objective) -------------------------------------
    def distance_cb(from_idx: int, to_idx: int) -> int:
        i, j = manager.IndexToNode(from_idx), manager.IndexToNode(to_idx)
        return int(matrix.distance_m[i][j])

    transit_cb_index = routing.RegisterTransitCallback(distance_cb)
    routing.SetArcCostEvaluatorOfAllVehicles(transit_cb_index)

    # --- Distance dimension (for slack/cumul tracking) ---------------------
    routing.AddDimension(
        transit_cb_index,
        0,
        10 ** 9,
        True,
        "Distance",
    )

    # --- Weight dimension --------------------------------------------------
    def weight_cb(from_idx: int) -> int:
        return stops[manager.IndexToNode(from_idx)].weight_lbs

    weight_cb_index = routing.RegisterUnaryTransitCallback(weight_cb)
    routing.AddDimensionWithVehicleCapacity(
        weight_cb_index,
        0,
        [v.weight_capacity_lbs for v in vehicles],
        True,
        "Weight",
    )

    # --- Cube dimension (using max cube_by_stops[0] from caller) -----------
    def cube_cb(from_idx: int) -> int:
        return stops[manager.IndexToNode(from_idx)].cubes

    cube_cb_index = routing.RegisterUnaryTransitCallback(cube_cb)
    routing.AddDimensionWithVehicleCapacity(
        cube_cb_index,
        0,
        [v.cube_capacity for v in vehicles],
        True,
        "Cube",
    )

    # --- Time dimension + optional curfew windows --------------------------
    def time_cb(from_idx: int, to_idx: int) -> int:
        i, j = manager.IndexToNode(from_idx), manager.IndexToNode(to_idx)
        return int(matrix.time_sec[i][j]) + stops[i].service_sec

    time_cb_index = routing.RegisterTransitCallback(time_cb)
    routing.AddDimension(
        time_cb_index,
        24 * 3600,                              # waiting slack
        max(v.max_route_seconds for v in vehicles),
        False,
        "Time",
    )
    time_dim = routing.GetDimensionOrDie("Time")

    for node, stop in enumerate(stops):
        if stop.window_start_sec is None or stop.window_end_sec is None:
            continue
        if node == depot_index:
            continue
        idx = manager.NodeToIndex(node)
        time_dim.CumulVar(idx).SetRange(stop.window_start_sec, stop.window_end_sec)

    # --- Search params -----------------------------------------------------
    params = pywrapcp.DefaultRoutingSearchParameters()
    params.first_solution_strategy = routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
    params.local_search_metaheuristic = routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
    params.time_limit.seconds = max(1, int(max_solver_seconds))

    assignment = routing.SolveWithParameters(params)
    if assignment is None:
        return SolverSolution(status="infeasible", routes=[], total_distance_m=0.0)

    routes: list[SolverRoute] = []
    total_distance = 0.0
    for v_id, vehicle in enumerate(vehicles):
        idx = routing.Start(v_id)
        path: list[int] = []
        weight_total = 0
        cubes_total = 0
        distance_total = 0.0
        while not routing.IsEnd(idx):
            node = manager.IndexToNode(idx)
            path.append(node)
            weight_total += stops[node].weight_lbs
            cubes_total += stops[node].cubes
            next_idx = assignment.Value(routing.NextVar(idx))
            distance_total += matrix.distance_m[node][manager.IndexToNode(next_idx)]
            idx = next_idx
        path.append(manager.IndexToNode(idx))  # depot end
        if len(path) <= 2:
            continue  # vehicle unused
        duration = float(assignment.Value(time_dim.CumulVar(routing.End(v_id))))
        routes.append(
            SolverRoute(
                vehicle=vehicle.name,
                stop_indices=path,
                distance_m=distance_total,
                duration_sec=duration,
                weight_lbs=weight_total,
                cubes=cubes_total,
            )
        )
        total_distance += distance_total

    # OR-Tools status enum: 1 == ROUTING_SUCCESS across recent versions.
    status = "optimal" if int(routing.status()) == 1 else "feasible"
    return SolverSolution(status=status, routes=routes, total_distance_m=total_distance)
