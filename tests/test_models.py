"""Round-trip tests for Pydantic models against the spec §5 example documents."""
from __future__ import annotations

from src.models.location import Location
from src.models.matrix import District, MatrixCacheEntry
from src.models.order import OrderBoard
from src.models.restriction import StateRestriction
from src.models.route import RouteHistory
from src.models.trailer import TrailerType


def test_location_with_curfew_roundtrip():
    raw = {
        "id": "161",
        "location_code": "161",
        "location_type": "Mileage Store",
        "description": "Albertsons",
        "address": {"street": "10700 Ustick Rd", "city": "Boise", "state": "ID", "postal": "83713"},
        "coordinates": {"type": "Point", "coordinates": [-116.317, 43.6348]},
        "lat": 43.6348,
        "lon": -116.317,
        "district_handle": "SLBoise",
        "curfew": {"start": "22:00", "end": "07:00"},
        "is_enabled": True,
    }
    loc = Location.model_validate(raw)
    assert loc.curfew.start == "22:00"
    assert loc.coordinates.coordinates == [-116.317, 43.6348]


def test_trailer_cube_lookup():
    raw = {
        "id": "45+45",
        "trailer_class": "Combo",
        "trailer_type_description": "45+45",
        "dollies": 2,
        "lead_weight_max_lbs": 40000,
        "pup_weight_max_lbs": 30000,
        "total_weight_max_lbs": 70000,
        "cube_by_stops": [3240, 3200, 3160, 3120, 3080, 3040, 3000, 2960, 2920],
        "max_stops_supported": 9,
    }
    t = TrailerType.model_validate(raw)
    assert t.cube_limit_for(1) == 3240
    assert t.cube_limit_for(4) == 3120
    assert t.cube_limit_for(20) == 2920  # clamped


def test_restriction_roundtrip():
    raw = {
        "id": "MT_40+40",
        "state": "MT",
        "trailer_type": "40+40",
        "trailer_class": "Combo",
        "max_weight_lbs": 66000,
        "within_2mi_interstate_only": True,
        "max_distance_from_interstate_mi": 2,
        "notes": "MT 40+40 must stay near interstates",
    }
    r = StateRestriction.model_validate(raw)
    assert r.within_2mi_interstate_only is True


def test_order_board_roundtrip():
    raw = {
        "id": "FRE0224_183",
        "order_group": "FRE0224",
        "dc_code": "52-DC",
        "destination": "183",
        "orders": [{"commodity": "PRO", "weight_lbs": 19414, "cubes": 1014, "pallets": 14.5, "cases": 1097}],
        "totals": {"weight_lbs": 19414, "cubes": 1014, "pallets": 14.5, "cases": 1097, "order_line_count": 1, "commodity_count": 1},
    }
    b = OrderBoard.model_validate(raw)
    assert b.totals.weight_lbs == 19414
    assert b.orders[0].commodity == "PRO"


def test_district_and_matrix_roundtrip():
    District.model_validate({
        "id": "SLMontana",
        "dc_code": "52-DC",
        "district_handle": "SLMontana",
        "states": ["MT"],
        "store_count": 25,
    })
    MatrixCacheEntry.model_validate({
        "id": "deadbeef",
        "profile": "truck",
        "location_codes": ["52-DC", "1010"],
        "location_count": 2,
        "time_matrix_sec": [[0, 25200], [25200, 0]],
        "distance_matrix_m": [[0, 745000], [745000, 0]],
    })


def test_route_history_roundtrip():
    raw = {
        "id": "abc",
        "dc_code": "52-DC",
        "request": {
            "depot": {"lat": 40.85, "lon": -111.92},
            "stops": ["1010"],
            "trailer_type": "45+45",
        },
        "result": {
            "status": "optimal",
            "trailer_type": "45+45",
            "routes": [{
                "vehicle": "V1",
                "trailer_type": "45+45",
                "stops": ["52-DC", "1010", "52-DC"],
                "stop_count": 1,
                "distance_m": 1000.0,
                "duration_min": 60.0,
                "weight_lbs": 1000,
                "cubes": 100,
                "weight_utilization_pct": 50.0,
                "cube_utilization_pct": 30.0,
            }],
            "summary": {"total_distance_m": 1000.0, "vehicles_used": 1},
        },
        "solver_time_sec": 0.5,
    }
    h = RouteHistory.model_validate(raw)
    assert h.result.status == "optimal"
