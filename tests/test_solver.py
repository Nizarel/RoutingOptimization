"""Solver smoke test: 5-stop synthetic instance must produce a feasible solution."""
from __future__ import annotations

import asyncio

from src.services.azure_maps import get_matrix
from src.services.solver import StopInput, VehicleInput, solve_cvrptw


def _stops() -> list[StopInput]:
    # Depot + 4 SLC-area synthetic stops (~50 mi radius).
    return [
        StopInput(code="52-DC", lat=40.8528, lon=-111.925),
        StopInput(code="A", lat=40.76, lon=-111.89, weight_lbs=8_000, cubes=400, service_sec=900),
        StopInput(code="B", lat=40.69, lon=-111.99, weight_lbs=10_000, cubes=500, service_sec=900),
        StopInput(code="C", lat=41.22, lon=-111.97, weight_lbs=12_000, cubes=600, service_sec=900),
        StopInput(code="D", lat=40.30, lon=-111.69, weight_lbs=9_000, cubes=450, service_sec=900),
    ]


def test_solver_basic_feasible():
    stops = _stops()
    matrix = asyncio.run(get_matrix([(s.code, s.lat, s.lon) for s in stops]))
    vehicles = [VehicleInput(name="V1", weight_capacity_lbs=70_000, cube_capacity=3_000)]
    sol = solve_cvrptw(stops, vehicles, matrix, max_solver_seconds=5)
    assert sol.status in {"optimal", "feasible"}
    assert len(sol.routes) == 1
    visited = sol.routes[0].stop_indices
    assert visited[0] == 0 and visited[-1] == 0
    assert set(visited) == {0, 1, 2, 3, 4}
    assert sol.total_distance_m > 0


def test_solver_two_vehicles_split_load():
    stops = _stops()
    matrix = asyncio.run(get_matrix([(s.code, s.lat, s.lon) for s in stops]))
    # Capacity below total load forces use of both vehicles.
    vehicles = [
        VehicleInput(name="V1", weight_capacity_lbs=20_000, cube_capacity=1_000),
        VehicleInput(name="V2", weight_capacity_lbs=20_000, cube_capacity=1_000),
    ]
    sol = solve_cvrptw(stops, vehicles, matrix, max_solver_seconds=5)
    assert sol.status in {"optimal", "feasible"}
    assert len(sol.routes) == 2
    all_visited = {n for r in sol.routes for n in r.stop_indices if n != 0}
    assert all_visited == {1, 2, 3, 4}
