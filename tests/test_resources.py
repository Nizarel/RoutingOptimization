"""Unit tests for MCP resources (offline, repos monkeypatched)."""
from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest

from src.models.location import Location
from src.models.matrix import District
from src.models.order import OrderBoard, OrderTotals
from src.models.restriction import StateRestriction
from src.models.route import (
    ComplianceReport,
    RouteHistory,
    RouteRequestSnapshot,
    RouteResult,
    RouteSummary,
    VehicleRoute,
)
from src.models.route import Depot
from src.models.trailer import TrailerType
from src.resources.districts import districts as districts_res
from src.resources.last_solution import last_solution
from src.resources.locations import location_detail
from src.resources.order_summary import order_summary
from src.resources.profiles import profiles
from src.resources.state_restrictions import state_restrictions
from src.resources.trailer_types import trailer_types
from src.resources.vehicles import vehicles


# ── profiles (static) ────────────────────────────────────────────────────────

async def test_profiles_static_payload():
    payload = json.loads(await profiles())
    ids = {p["id"] for p in payload["profiles"]}
    assert {"truck", "car"} <= ids
    objs = {o["id"] for o in payload["objectives"]}
    assert {"min_total_distance", "min_longest_route"} <= objs


# ── trailer_types ────────────────────────────────────────────────────────────

async def test_trailer_types_calls_repo(monkeypatch):
    sample = TrailerType(
        id="P53R",
        trailer_class="Single",
        trailer_type_description="53' reefer",
        lead_weight_max_lbs=44000,
        total_weight_max_lbs=44000,
        cube_by_stops=[3489, 3300, 3100],
        max_stops_supported=10,
    )

    async def fake_list_all(self):
        return [sample]

    monkeypatch.setattr(
        "src.data.trailer_repo.TrailerRepo.list_all", fake_list_all
    )
    payload = json.loads(await trailer_types())
    assert isinstance(payload, list) and len(payload) == 1
    assert payload[0]["id"] == "P53R"


# ── state_restrictions/{state} ───────────────────────────────────────────────

async def test_state_restrictions_uppercases_state(monkeypatch):
    captured: dict[str, str] = {}

    async def fake_list_by_state(self, state):
        captured["state"] = state
        return [
            StateRestriction(
                id="ut-P53R",
                state=state,
                trailer_type="P53R",
                trailer_class="Single",
                max_weight_lbs=80000,
            )
        ]

    monkeypatch.setattr(
        "src.data.restriction_repo.RestrictionRepo.list_by_state",
        fake_list_by_state,
    )
    payload = json.loads(await state_restrictions("ut"))
    assert captured["state"] == "UT"
    assert payload[0]["state"] == "UT"


# ── districts ────────────────────────────────────────────────────────────────

async def test_districts_lists_all(monkeypatch):
    items = [
        District(
            id="d1",
            dc_code="52-DC",
            district_handle="N1",
            store_codes=["A", "B"],
        ),
    ]

    async def fake_query(self, *args, **kwargs):
        return items

    monkeypatch.setattr("src.data.district_repo.DistrictRepo.query", fake_query)
    payload = json.loads(await districts_res())
    assert len(payload) == 1
    assert payload[0]["district_handle"] == "N1"


# ── order_summary/{order_group} ──────────────────────────────────────────────

async def test_order_summary_aggregates(monkeypatch):
    boards = [
        OrderBoard(
            id="b1",
            order_group="OG1",
            dc_code="52-DC",
            destination="STORE-100",
            district="N1",
            totals=OrderTotals(weight_lbs=1000, cubes=200, pallets=5, cases=80,
                               order_line_count=3, commodity_count=2),
        ),
        OrderBoard(
            id="b2",
            order_group="OG1",
            dc_code="52-DC",
            destination="STORE-200",
            district="N2",
            totals=OrderTotals(weight_lbs=500, cubes=100, pallets=2, cases=40,
                               order_line_count=1, commodity_count=1),
        ),
    ]

    async def fake_list_by_group(self, og):
        return boards

    monkeypatch.setattr(
        "src.data.order_repo.OrderRepo.list_by_group", fake_list_by_group
    )
    payload = json.loads(await order_summary("OG1"))
    assert payload["board_count"] == 2
    assert payload["destination_count"] == 2
    assert payload["district_count"] == 2
    assert payload["totals"]["weight_lbs"] == 1500
    assert payload["totals"]["cubes"] == 300


async def test_order_summary_empty(monkeypatch):
    async def fake_list_by_group(self, og):
        return []

    monkeypatch.setattr(
        "src.data.order_repo.OrderRepo.list_by_group", fake_list_by_group
    )
    payload = json.loads(await order_summary("MISSING"))
    assert payload["board_count"] == 0
    assert payload["totals"]["weight_lbs"] == 0


# ── locations/{location_code} ────────────────────────────────────────────────

async def test_location_detail_found(monkeypatch):
    from src.models.location import GeoPoint

    loc = Location(
        id="STORE-100",
        location_code="STORE-100",
        location_type="Mileage Store",
        coordinates=GeoPoint(coordinates=[-111.9, 40.7]),
        lat=40.7,
        lon=-111.9,
    )

    async def fake_get_by_code(self, code):
        return loc if code == "STORE-100" else None

    monkeypatch.setattr(
        "src.data.location_repo.LocationRepo.get_by_code", fake_get_by_code
    )
    payload = json.loads(await location_detail("STORE-100"))
    assert payload["location_code"] == "STORE-100"


async def test_location_detail_missing_returns_empty(monkeypatch):
    async def fake_get_by_code(self, code):
        return None

    monkeypatch.setattr(
        "src.data.location_repo.LocationRepo.get_by_code", fake_get_by_code
    )
    payload = json.loads(await location_detail("NOPE"))
    assert payload == {}


# ── vehicles + last-solution share RouteRepo.latest ──────────────────────────

def _sample_history() -> RouteHistory:
    vr = VehicleRoute(
        vehicle="veh-0",
        trailer_type="P53R",
        stops=["52-DC", "STORE-100", "52-DC"],
        stop_count=1,
        distance_m=10000.0,
        duration_min=20.0,
        weight_lbs=1000.0,
        cubes=200.0,
        weight_utilization_pct=10.0,
        cube_utilization_pct=5.0,
    )
    return RouteHistory(
        id="hist-1",
        dc_code="52-DC",
        request=RouteRequestSnapshot(
            depot=Depot(lat=40.85, lon=-111.93),
            stops=["STORE-100"],
            trailer_type="P53R",
        ),
        result=RouteResult(
            status="optimal",
            trailer_type="P53R",
            routes=[vr],
            summary=RouteSummary(total_distance_m=10000.0, vehicles_used=1),
            compliance=ComplianceReport(status="evaluated"),
        ),
        solver_time_sec=0.5,
    )


async def test_vehicles_uses_latest_history(monkeypatch):
    hist = _sample_history()

    async def fake_latest(self, dc_code=None, limit=1):
        return [hist]

    monkeypatch.setattr("src.data.route_repo.RouteRepo.latest", fake_latest)
    payload = json.loads(await vehicles())
    assert payload["history_id"] == "hist-1"
    assert len(payload["vehicles"]) == 1
    assert payload["vehicles"][0]["vehicle"] == "veh-0"


async def test_vehicles_empty(monkeypatch):
    async def fake_latest(self, dc_code=None, limit=1):
        return []

    monkeypatch.setattr("src.data.route_repo.RouteRepo.latest", fake_latest)
    payload = json.loads(await vehicles())
    assert payload["vehicles"] == []
    assert payload["history_id"] is None


async def test_last_solution_empty(monkeypatch):
    async def fake_latest(self, dc_code=None, limit=1):
        return []

    monkeypatch.setattr("src.data.route_repo.RouteRepo.latest", fake_latest)
    payload = json.loads(await last_solution())
    assert payload == {}
