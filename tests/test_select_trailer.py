"""Unit tests for the ``select_trailer`` MCP tool (offline)."""
from __future__ import annotations

import pytest

from src.models.location import Address, Curfew, GeoPoint, Location
from src.models.requests import SelectTrailerRequest
from src.models.restriction import StateRestriction
from src.models.trailer import TrailerType
from src.services import constraint_engine as ce_mod
from src.services.constraint_engine import ConstraintEngine
from src.tools.select_trailer import select_trailer


def _trailer(tid: str, cls: str, lead: int, pup: int, total: int, curve: list[int]) -> TrailerType:
    return TrailerType(
        id=tid, trailer_class=cls, trailer_type_description=tid,  # type: ignore[arg-type]
        dollies=1 if cls == "Combo" else 0,
        lead_weight_max_lbs=lead, pup_weight_max_lbs=pup,
        total_weight_max_lbs=total,
        cube_by_stops=curve, max_stops_supported=len(curve),
    )


def _loc(code: str, state: str) -> Location:
    return Location(
        id=code, location_code=code, location_type="Mileage Store",
        address=Address(state=state),
        coordinates=GeoPoint(coordinates=[-111.0, 40.0]),
        lat=40.0, lon=-111.0, curfew=Curfew(),
    )


TRAILERS = [
    _trailer("45+45", "Combo", 45000, 35000, 80000, [3000, 2900, 2800]),
    _trailer("48+28", "Combo", 48000, 18000, 66000, [2800, 2700]),
    _trailer("40+40", "Combo", 40000, 30000, 70000, [2600, 2500]),
    _trailer("53", "Single", 48000, 0, 48000, [4000, 3900]),
]

RESTRICTIONS = [
    StateRestriction(id="UT_45+45", state="UT", trailer_type="45+45", trailer_class="Combo", max_weight_lbs=80000),
    StateRestriction(id="UT_48+28", state="UT", trailer_type="48+28", trailer_class="Combo", max_weight_lbs=66000),
    StateRestriction(id="UT_40+40", state="UT", trailer_type="40+40", trailer_class="Combo", max_weight_lbs=70000),
    StateRestriction(id="UT_53", state="UT", trailer_type="53", trailer_class="Single", max_weight_lbs=48000),
    StateRestriction(id="MT_48+28", state="MT", trailer_type="48+28", trailer_class="Combo", max_weight_lbs=66000),
    StateRestriction(id="MT_40+40", state="MT", trailer_type="40+40", trailer_class="Combo", max_weight_lbs=70000, within_2mi_interstate_only=True),
    StateRestriction(id="MT_53", state="MT", trailer_type="53", trailer_class="Single", max_weight_lbs=48000),
]

LOCATIONS = {
    "UT-A": _loc("UT-A", "UT"),
    "UT-B": _loc("UT-B", "UT"),
    "MT-A": _loc("MT-A", "MT"),
}


def _make_engine(codes: list[str] | None) -> ConstraintEngine:
    locs = {c: LOCATIONS[c] for c in (codes or []) if c in LOCATIONS}
    by_state: dict[str, list[StateRestriction]] = {}
    for r in RESTRICTIONS:
        by_state.setdefault(r.state, []).append(r)
    return ConstraintEngine(
        trailers={t.id: t for t in TRAILERS},
        restrictions_by_state=by_state,
        locations_by_code=locs,
        mt_interstate_segments=ce_mod._load_mt_interstate_segments(),
    )


@pytest.fixture
def patch_engine(monkeypatch):
    async def fake_load(cls, *, location_codes=None):
        return _make_engine(location_codes)
    monkeypatch.setattr(ConstraintEngine, "load", classmethod(fake_load))


async def test_select_trailer_ut_only_all_feasible(patch_engine):
    req = SelectTrailerRequest(
        stops=["UT-A", "UT-B"],
        total_weight_lbs=20000, total_cubes=1000,
        prefer="max_capacity",
    )
    resp = await select_trailer(req)
    assert resp.recommended is not None
    assert resp.infeasible_reason is None
    assert resp.states_considered == ["UT"]
    ids = {resp.recommended.trailer_type, *(a.trailer_type for a in resp.alternatives)}
    assert ids == {"45+45", "48+28", "40+40", "53"}


async def test_select_trailer_ut_mt_excludes_45_45(patch_engine):
    req = SelectTrailerRequest(
        stops=["UT-A", "MT-A"],
        total_weight_lbs=20000, total_cubes=1000,
        prefer="max_capacity",
    )
    resp = await select_trailer(req)
    assert resp.recommended is not None
    ids = {resp.recommended.trailer_type, *(a.trailer_type for a in resp.alternatives)}
    assert "45+45" not in ids
    assert resp.states_considered == ["MT", "UT"]


async def test_select_trailer_infeasible_when_overweight(patch_engine):
    req = SelectTrailerRequest(
        stops=["UT-A"],
        total_weight_lbs=900_000, total_cubes=100,
    )
    resp = await select_trailer(req)
    assert resp.recommended is None
    assert resp.infeasible_reason is not None


async def test_select_trailer_min_class_prefers_single(patch_engine):
    req = SelectTrailerRequest(
        stops=["UT-A"],
        total_weight_lbs=10000, total_cubes=500,
        prefer="min_class",
    )
    resp = await select_trailer(req)
    assert resp.recommended is not None
    assert resp.recommended.trailer_class == "Single"


async def test_select_trailer_explicit_states_skips_location_load(monkeypatch):
    async def fake_load(cls, *, location_codes=None):
        assert location_codes is None
        return _make_engine(None)
    monkeypatch.setattr(ConstraintEngine, "load", classmethod(fake_load))

    req = SelectTrailerRequest(
        stops=["UT-A"], states=["UT"],
        total_weight_lbs=10000, total_cubes=500,
    )
    resp = await select_trailer(req)
    assert resp.recommended is not None
    assert resp.states_considered == ["UT"]
