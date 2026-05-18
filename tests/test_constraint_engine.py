"""Unit tests for the ConstraintEngine (offline, no Cosmos)."""
from __future__ import annotations

from src.models.location import Address, Curfew, GeoPoint, Location
from src.models.restriction import StateRestriction
from src.models.route import VehicleRoute
from src.models.trailer import TrailerType
from src.services.constraint_engine import (
    ConstraintEngine,
    _load_mt_interstate_segments,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _trailer(
    tid: str,
    cls: str,
    lead: int,
    pup: int,
    total: int,
    cube_curve: list[int],
) -> TrailerType:
    return TrailerType(
        id=tid,
        trailer_class=cls,  # type: ignore[arg-type]
        trailer_type_description=tid,
        dollies=1 if cls == "Combo" else 0,
        lead_weight_max_lbs=lead,
        pup_weight_max_lbs=pup,
        total_weight_max_lbs=total,
        cube_by_stops=cube_curve,
        max_stops_supported=len(cube_curve),
    )


def _location(code: str, lat: float, lon: float, state: str) -> Location:
    return Location(
        id=code,
        location_code=code,
        location_type="Mileage Store",
        address=Address(state=state),
        coordinates=GeoPoint(coordinates=[lon, lat]),
        lat=lat,
        lon=lon,
        curfew=Curfew(),
    )


def _restriction(state: str, trailer: str, weight: int, *, interstate_only: bool = False) -> StateRestriction:
    return StateRestriction(
        id=f"{state}_{trailer}",
        state=state,
        trailer_type=trailer,
        trailer_class="Combo" if "+" in trailer else "Single",
        max_weight_lbs=weight,
        within_2mi_interstate_only=interstate_only,
        max_distance_from_interstate_mi=2.0 if interstate_only else None,
    )


def _engine(
    trailers: list[TrailerType],
    restrictions: list[StateRestriction],
    locations: list[Location],
) -> ConstraintEngine:
    by_state: dict[str, list[StateRestriction]] = {}
    for r in restrictions:
        by_state.setdefault(r.state, []).append(r)
    return ConstraintEngine(
        trailers={t.id: t for t in trailers},
        restrictions_by_state=by_state,
        locations_by_code={loc.location_code: loc for loc in locations},
        mt_interstate_segments=_load_mt_interstate_segments(),
    )


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_get_cube_limit_uses_degradation_curve():
    t = _trailer("45+45", "Combo", 45000, 35000, 80000, [3240, 3200, 3160, 3120, 3080])
    eng = _engine([t], [], [])
    assert eng.get_cube_limit("45+45", 1) == 3240
    assert eng.get_cube_limit("45+45", 3) == 3160
    # Past end of curve → clamp to last value
    assert eng.get_cube_limit("45+45", 99) == 3080


def test_get_allowed_trailers_intersection():
    trailers = [
        _trailer("45+45", "Combo", 45000, 35000, 80000, [3000]),
        _trailer("48+28", "Combo", 48000, 18000, 66000, [2800]),
        _trailer("40+40", "Combo", 40000, 30000, 70000, [2600]),
    ]
    restrictions = [
        _restriction("UT", "45+45", 80000),
        _restriction("UT", "48+28", 66000),
        _restriction("UT", "40+40", 70000),
        _restriction("MT", "48+28", 66000),
        _restriction("MT", "40+40", 70000, interstate_only=True),
    ]
    eng = _engine(trailers, restrictions, [])

    assert eng.get_allowed_trailers(["UT"]) == ["40+40", "45+45", "48+28"]
    # 45+45 not legal in MT → drops out of the intersection
    assert eng.get_allowed_trailers(["UT", "MT"]) == ["40+40", "48+28"]
    # No states → all trailers known to the engine
    assert eng.get_allowed_trailers([]) == ["40+40", "45+45", "48+28"]
    # Unknown state → empty result (no restrictions known)
    assert eng.get_allowed_trailers(["XX"]) == []


def test_check_weight_split_combo():
    t = _trailer("45+45", "Combo", 45000, 35000, 80000, [3000])
    eng = _engine([t], [], [])
    assert eng.check_weight_split("45+45", 45000, 35000) is True
    assert eng.check_weight_split("45+45", 46000, 30000) is False  # lead exceeds
    assert eng.check_weight_split("45+45", 40000, 36000) is False  # pup exceeds
    assert eng.check_weight_split("45+45", 50000, 31000) is False  # total exceeds


def test_check_weight_split_single():
    t = _trailer("53", "Single", 48000, 0, 48000, [4000])
    eng = _engine([t], [], [])
    assert eng.check_weight_split("53", 48000, 0) is True
    assert eng.check_weight_split("53", 40000, 1000) is False  # singles cannot have pup load
    assert eng.check_weight_split("53", 49000, 0) is False


def test_interstate_proximity_missoula_on_corridor_passes():
    # Missoula, MT is essentially on I-90 (≈46.87°N, 113.99°W)
    t = _trailer("40+40", "Combo", 40000, 30000, 70000, [2600])
    r = _restriction("MT", "40+40", 70000, interstate_only=True)
    loc = _location("MISSOULA", 46.8721, -113.994, "MT")
    eng = _engine([t], [r], [loc])
    assert eng.check_interstate_proximity("40+40", "MT", loc.lat, loc.lon) is True


def test_interstate_proximity_remote_mt_fails():
    # Glasgow, MT (NE corner, ~250 mi from any interstate corridor)
    t = _trailer("40+40", "Combo", 40000, 30000, 70000, [2600])
    r = _restriction("MT", "40+40", 70000, interstate_only=True)
    loc = _location("GLASGOW", 48.197, -106.638, "MT")
    eng = _engine([t], [r], [loc])
    assert eng.check_interstate_proximity("40+40", "MT", loc.lat, loc.lon) is False


def test_interstate_proximity_skipped_when_rule_off():
    t = _trailer("48+28", "Combo", 48000, 18000, 66000, [2800])
    r = _restriction("MT", "48+28", 66000, interstate_only=False)
    loc = _location("GLASGOW", 48.197, -106.638, "MT")
    eng = _engine([t], [r], [loc])
    assert eng.check_interstate_proximity("48+28", "MT", loc.lat, loc.lon) is True


def test_evaluate_route_pass_case():
    t = _trailer("45+45", "Combo", 45000, 35000, 80000, [3000, 2900, 2800])
    r = _restriction("UT", "45+45", 80000)
    locs = [
        _location("52-DC", 40.85, -111.92, "UT"),
        _location("S1", 40.76, -111.89, "UT"),
        _location("S2", 40.69, -111.99, "UT"),
    ]
    eng = _engine([t], [r], locs)
    route = VehicleRoute(
        vehicle="V1", trailer_type="45+45",
        stops=["52-DC", "S1", "S2", "52-DC"], stop_count=2,
        distance_m=10000, duration_min=30, weight_lbs=20000, cubes=1500,
        weight_utilization_pct=25.0, cube_utilization_pct=50.0,
    )
    report = eng.evaluate_route(route, ignore_depot_codes={"52-DC"})
    assert report.status == "evaluated"
    assert report.state_restrictions_passed is True
    assert report.state_violations == []
    assert report.cube_violations == []


def test_evaluate_route_state_violation():
    t = _trailer("45+45", "Combo", 45000, 35000, 80000, [3000])
    r = _restriction("UT", "45+45", 80000)  # legal in UT only
    locs = [
        _location("52-DC", 40.85, -111.92, "UT"),
        _location("MT1", 45.78, -108.50, "MT"),  # MT not allowed for 45+45
    ]
    eng = _engine([t], [r], locs)
    route = VehicleRoute(
        vehicle="V1", trailer_type="45+45",
        stops=["52-DC", "MT1", "52-DC"], stop_count=1,
        distance_m=10000, duration_min=30, weight_lbs=10000, cubes=500,
        weight_utilization_pct=12.5, cube_utilization_pct=16.6,
    )
    report = eng.evaluate_route(route, ignore_depot_codes={"52-DC"})
    assert report.state_restrictions_passed is False
    assert len(report.state_violations) == 1
    assert "MT" in report.state_violations[0]


def test_evaluate_route_cube_violation():
    t = _trailer("45+45", "Combo", 45000, 35000, 80000, [3000, 2900])
    r = _restriction("UT", "45+45", 80000)
    locs = [
        _location("52-DC", 40.85, -111.92, "UT"),
        _location("S1", 40.76, -111.89, "UT"),
        _location("S2", 40.69, -111.99, "UT"),
    ]
    eng = _engine([t], [r], locs)
    route = VehicleRoute(
        vehicle="V1", trailer_type="45+45",
        stops=["52-DC", "S1", "S2", "52-DC"], stop_count=2,
        distance_m=10000, duration_min=30, weight_lbs=20000, cubes=3500,  # > 2900
        weight_utilization_pct=25.0, cube_utilization_pct=100.0,
    )
    report = eng.evaluate_route(route, ignore_depot_codes={"52-DC"})
    assert len(report.cube_violations) == 1
    assert "3500" in report.cube_violations[0]
