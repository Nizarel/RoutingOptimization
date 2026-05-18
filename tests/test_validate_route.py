"""Unit tests for the ``validate_route`` MCP tool (offline)."""
from __future__ import annotations

import pytest

from src.models.location import Address, Curfew, GeoPoint, Location
from src.models.requests import ValidateRouteRequest
from src.models.restriction import StateRestriction
from src.models.route import VehicleRoute
from src.models.trailer import TrailerType
from src.services import constraint_engine as ce_mod
from src.services.constraint_engine import ConstraintEngine
from src.tools.validate_route import validate_route


def _trailer(tid: str, total: int, curve: list[int]) -> TrailerType:
    return TrailerType(
        id=tid, trailer_class="Combo", trailer_type_description=tid,
        dollies=1, lead_weight_max_lbs=total // 2, pup_weight_max_lbs=total // 2,
        total_weight_max_lbs=total,
        cube_by_stops=curve, max_stops_supported=len(curve),
    )


def _loc(code: str, state: str, lat: float = 40.0, lon: float = -111.0) -> Location:
    return Location(
        id=code, location_code=code, location_type="Mileage Store",
        address=Address(state=state),
        coordinates=GeoPoint(coordinates=[lon, lat]),
        lat=lat, lon=lon, curfew=Curfew(),
    )


def _make_engine(codes: list[str] | None) -> ConstraintEngine:
    trailers = {t.id: t for t in [_trailer("45+45", 80000, [3000, 2900])]}
    restrictions = [
        StateRestriction(id="UT_45+45", state="UT", trailer_type="45+45", trailer_class="Combo", max_weight_lbs=80000),
    ]
    by_state: dict[str, list[StateRestriction]] = {}
    for r in restrictions:
        by_state.setdefault(r.state, []).append(r)
    all_locs = {
        "52-DC": _loc("52-DC", "UT", 40.85, -111.92),
        "UT-1": _loc("UT-1", "UT", 40.76, -111.89),
        "MT-1": _loc("MT-1", "MT", 45.78, -108.50),
    }
    locs = {c: all_locs[c] for c in (codes or all_locs.keys()) if c in all_locs}
    return ConstraintEngine(
        trailers=trailers,
        restrictions_by_state=by_state,
        locations_by_code=locs,
        mt_interstate_segments=ce_mod._load_mt_interstate_segments(),
    )


@pytest.fixture
def patch_engine(monkeypatch):
    async def fake_load(cls, *, location_codes=None):
        return _make_engine(location_codes)
    monkeypatch.setattr(ConstraintEngine, "load", classmethod(fake_load))


def _route(stops: list[str], weight: float = 10000, cubes: float = 500) -> VehicleRoute:
    return VehicleRoute(
        vehicle="V1", trailer_type="45+45",
        stops=stops, stop_count=max(0, len(stops) - 2),
        distance_m=10000, duration_min=30,
        weight_lbs=weight, cubes=cubes,
        weight_utilization_pct=10.0, cube_utilization_pct=20.0,
    )


async def test_validate_route_inline_passes(patch_engine):
    req = ValidateRouteRequest(route=_route(["52-DC", "UT-1", "52-DC"]))
    resp = await validate_route(req)
    assert resp.compliance.status == "evaluated"
    assert resp.compliance.state_restrictions_passed is True
    assert resp.violations == []


async def test_validate_route_inline_state_violation(patch_engine):
    req = ValidateRouteRequest(route=_route(["52-DC", "MT-1", "52-DC"]))
    resp = await validate_route(req)
    assert resp.compliance.state_restrictions_passed is False
    assert len(resp.violations) == 1
    assert resp.violations[0].category == "state"
    assert resp.violations[0].vehicle == "V1"


async def test_validate_route_inline_cube_violation(patch_engine):
    req = ValidateRouteRequest(route=_route(["52-DC", "UT-1", "52-DC"], cubes=5000))
    resp = await validate_route(req)
    cube = [v for v in resp.violations if v.category == "cube"]
    assert len(cube) == 1


async def test_validate_route_requires_history_or_route():
    with pytest.raises(ValueError):
        await validate_route(ValidateRouteRequest())


async def test_validate_route_history_id_requires_dc_code():
    with pytest.raises(ValueError):
        await validate_route(ValidateRouteRequest(history_id="abc"))
