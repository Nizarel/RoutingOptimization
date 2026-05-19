"""Unit tests for the pre-flight infeasibility detector and ComplianceReport extensions."""
from __future__ import annotations

from src.models.route import ComplianceReport
from src.services.azure_maps import Matrix
from src.services.solver import StopInput, VehicleInput
from src.tools.optimize import _preflight_infeasibility


def _matrix(codes: list[str], time_sec: list[list[float]]) -> Matrix:
    n = len(codes)
    dist = [[time_sec[i][j] * 20.0 for j in range(n)] for i in range(n)]  # filler
    return Matrix(location_codes=codes, distance_m=dist, time_sec=time_sec)


def test_preflight_passes_for_short_trip():
    stops = [
        StopInput(code="DC", lat=0, lon=0),
        StopInput(code="A", lat=0, lon=0, weight_lbs=10_000, cubes=500, service_sec=1800),
    ]
    # 1h each way + 30min service = 2.5h round trip — well under 24h.
    matrix = _matrix(["DC", "A"], [[0, 3600], [3600, 0]])
    vehicles = [VehicleInput(name="V1", weight_capacity_lbs=70_000, cube_capacity=3_000)]
    assert _preflight_infeasibility(stops, vehicles, matrix) == []


def test_preflight_flags_stop_exceeding_max_route_seconds():
    stops = [
        StopInput(code="DC", lat=0, lon=0),
        StopInput(code="FAR", lat=0, lon=0, weight_lbs=10_000, cubes=500, service_sec=1800),
    ]
    # 13h each way → 26.5h round trip > 24h default cap.
    matrix = _matrix(["DC", "FAR"], [[0, 13 * 3600], [13 * 3600, 0]])
    vehicles = [VehicleInput(name="V1", weight_capacity_lbs=70_000, cube_capacity=3_000)]
    notes = _preflight_infeasibility(stops, vehicles, matrix)
    assert len(notes) == 1
    assert "FAR" in notes[0]
    assert "exceeds vehicle max" in notes[0]


def test_preflight_flags_aggregate_weight_overflow():
    stops = [
        StopInput(code="DC", lat=0, lon=0),
        StopInput(code="A", lat=0, lon=0, weight_lbs=50_000, cubes=500, service_sec=1800),
        StopInput(code="B", lat=0, lon=0, weight_lbs=50_000, cubes=500, service_sec=1800),
    ]
    matrix = _matrix(
        ["DC", "A", "B"],
        [[0, 3600, 3600], [3600, 0, 1800], [3600, 1800, 0]],
    )
    # Single vehicle 70k lbs cap, demand is 100k lbs.
    vehicles = [VehicleInput(name="V1", weight_capacity_lbs=70_000, cube_capacity=10_000)]
    notes = _preflight_infeasibility(stops, vehicles, matrix)
    assert any("total weight" in n for n in notes)


def test_preflight_flags_aggregate_cube_overflow():
    stops = [
        StopInput(code="DC", lat=0, lon=0),
        StopInput(code="A", lat=0, lon=0, weight_lbs=1_000, cubes=2_000, service_sec=1800),
        StopInput(code="B", lat=0, lon=0, weight_lbs=1_000, cubes=2_000, service_sec=1800),
    ]
    matrix = _matrix(
        ["DC", "A", "B"],
        [[0, 3600, 3600], [3600, 0, 1800], [3600, 1800, 0]],
    )
    # Single vehicle 1_500 cube cap, demand is 4_000.
    vehicles = [VehicleInput(name="V1", weight_capacity_lbs=70_000, cube_capacity=1_500)]
    notes = _preflight_infeasibility(stops, vehicles, matrix)
    assert any("total cubes" in n for n in notes)


def test_preflight_uses_most_generous_vehicle_for_time():
    stops = [
        StopInput(code="DC", lat=0, lon=0),
        StopInput(code="A", lat=0, lon=0, weight_lbs=10_000, cubes=500, service_sec=1800),
    ]
    matrix = _matrix(["DC", "A"], [[0, 13 * 3600], [13 * 3600, 0]])
    # One short-leg vehicle and one big-leg vehicle. Stop fits the bigger one.
    vehicles = [
        VehicleInput(name="V1", weight_capacity_lbs=70_000, cube_capacity=3_000,
                     max_route_seconds=12 * 3600),
        VehicleInput(name="V2", weight_capacity_lbs=70_000, cube_capacity=3_000,
                     max_route_seconds=48 * 3600),
    ]
    assert _preflight_infeasibility(stops, vehicles, matrix) == []


def test_compliance_report_has_new_fields():
    report = ComplianceReport(
        status="evaluated",
        notes=["stop=X round-trip 25h exceeds vehicle max 24h"],
        suggested_trailers=["48+28", "40+40"],
    )
    serialized = report.model_dump()
    assert serialized["notes"] == ["stop=X round-trip 25h exceeds vehicle max 24h"]
    assert serialized["suggested_trailers"] == ["48+28", "40+40"]


def test_compliance_report_defaults_empty():
    report = ComplianceReport()
    assert report.notes == []
    assert report.suggested_trailers == []
