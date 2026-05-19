"""Unit tests for Azure Maps Route Matrix v2 client (offline, respx-mocked)."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import httpx
import pytest
import respx

from src.services import azure_maps as az_maps
from src.services.azure_maps import (
    VehicleSpec,
    _build_v2_body,
    _parse_v2_response,
    get_matrix,
)


def _points() -> list[tuple[str, float, float]]:
    return [
        ("52-DC", 40.8528, -111.925),
        ("A", 40.76, -111.89),
        ("B", 40.69, -111.99),
    ]


def _canned_v2_response(n: int) -> dict:
    matrix = []
    for i in range(n):
        for j in range(n):
            matrix.append({
                "originIndex": i,
                "destinationIndex": j,
                "statusCode": 200,
                "distanceInMeters": 0 if i == j else 1000 * (i + j + 1),
                "durationInSeconds": 0 if i == j else 60 * (i + j + 1),
                "durationTrafficInSeconds": 0 if i == j else 75 * (i + j + 1),
            })
    return {"type": "RouteMatrix", "properties": {"matrix": matrix}}


# ── Body shape ────────────────────────────────────────────────────────────────

def test_build_v2_body_is_geojson_feature_collection():
    body = _build_v2_body(_points(), "truck", None)
    assert body["type"] == "FeatureCollection"
    assert body["travelMode"] == "truck"
    assert len(body["features"]) == 2
    types = {f["properties"]["pointType"] for f in body["features"]}
    assert types == {"origins", "destinations"}
    for f in body["features"]:
        assert f["geometry"]["type"] == "MultiPoint"
        assert len(f["geometry"]["coordinates"]) == 3
        # GeoJSON ordering: [lon, lat]
        lon, lat = f["geometry"]["coordinates"][0]
        assert lon == -111.925 and lat == 40.8528
    assert "vehicleSpec" not in body


def test_build_v2_body_includes_vehicle_spec_when_provided():
    spec = VehicleSpec(weight_kg=18000, height_m=4.1, is_commercial=True)
    body = _build_v2_body(_points(), "truck", spec)
    assert body["vehicleSpec"] == {
        "weight": 18000,
        "height": 4.1,
        "isVehicleCommercial": True,
    }


# ── Response parser ───────────────────────────────────────────────────────────

def test_parse_v2_response_uses_traffic_duration_when_present():
    data = _canned_v2_response(3)
    m = _parse_v2_response(data, _points())
    assert m.distance_m[0][1] == 2000
    # 75*(0+1+1) = 150 for [0][1] traffic-aware
    assert m.time_sec[0][1] == 150


def test_parse_v2_response_falls_back_to_haversine_for_failed_cells():
    data = _canned_v2_response(3)
    # Mark one cell as failed
    data["properties"]["matrix"][1]["statusCode"] = 400
    data["properties"]["matrix"][1]["distanceInMeters"] = 999_999
    m = _parse_v2_response(data, _points())
    # Cell [0][1] should now be Haversine, not 999_999
    assert m.distance_m[0][1] != 999_999
    assert m.distance_m[0][1] > 0


# ── get_matrix (mocked HTTP) ──────────────────────────────────────────────────

@pytest.fixture
def _maps_settings(monkeypatch):
    """Patch settings to set client_id, forcing the live path."""
    from src.config import get_settings

    s = get_settings()
    monkeypatch.setattr(s, "azure_maps_client_id", "test-uami-client-id")
    monkeypatch.setattr(s, "azure_maps_base_url", "https://atlas.test")
    monkeypatch.setattr(s, "azure_maps_matrix_max_cells", 700)
    monkeypatch.setattr(s, "azure_maps_matrix_daily_budget_cells", None)
    return s


async def test_get_matrix_calls_v2_endpoint_and_parses(_maps_settings):
    with patch.object(az_maps, "_get_token", new=AsyncMock(return_value="fake-token")):
        with respx.mock(assert_all_called=True) as router:
            route = router.post("https://atlas.test/route/matrix").mock(
                return_value=httpx.Response(200, json=_canned_v2_response(3))
            )
            m = await get_matrix(_points(), profile="truck")

    assert route.called
    sent = route.calls[0].request
    assert "api-version=2025-01-01" in str(sent.url)
    assert sent.headers["x-ms-client-id"] == "test-uami-client-id"
    assert sent.headers["Authorization"] == "Bearer fake-token"
    # Symmetric NxN with the canned values
    assert m.distance_m[1][2] == 4000  # 1000*(1+2+1)
    assert m.location_codes == ["52-DC", "A", "B"]


async def test_get_matrix_forwards_vehicle_spec(_maps_settings):
    import json

    spec = VehicleSpec(weight_kg=20000, height_m=4.1)
    with patch.object(az_maps, "_get_token", new=AsyncMock(return_value="fake-token")):
        with respx.mock(assert_all_called=True) as router:
            router.post("https://atlas.test/route/matrix").mock(
                return_value=httpx.Response(200, json=_canned_v2_response(3))
            )
            await get_matrix(_points(), vehicle_spec=spec)
            body = json.loads(router.calls[0].request.content)
    assert body["vehicleSpec"]["weight"] == 20000
    assert body["vehicleSpec"]["height"] == 4.1


async def test_get_matrix_cell_limit_raises(_maps_settings, monkeypatch):
    monkeypatch.setattr(_maps_settings, "azure_maps_matrix_max_cells", 4)
    big = [(f"C{i}", 40.0 + i * 0.01, -111.0) for i in range(5)]  # 25 cells > 4
    with pytest.raises(ValueError, match="too large"):
        await get_matrix(big)


async def test_get_matrix_http_failure_falls_back_to_haversine(_maps_settings):
    with patch.object(az_maps, "_get_token", new=AsyncMock(return_value="fake-token")):
        with respx.mock() as router:
            router.post("https://atlas.test/route/matrix").mock(
                return_value=httpx.Response(500, json={"error": "boom"})
            )
            m = await get_matrix(_points())
    # Haversine: diagonal is zero, off-diagonal > 0, symmetric
    assert m.distance_m[0][0] == 0.0
    assert m.distance_m[0][1] > 0
    assert m.distance_m[0][1] == m.distance_m[1][0]


async def test_get_matrix_no_client_id_uses_haversine(monkeypatch):
    from src.config import get_settings

    s = get_settings()
    monkeypatch.setattr(s, "azure_maps_client_id", None)
    m = await get_matrix(_points())
    assert m.distance_m[0][0] == 0.0
    assert m.distance_m[0][1] > 0


# ── Daily budget ──────────────────────────────────────────────────────────────

async def test_daily_budget_enforced(monkeypatch, _maps_settings):
    """Exceeding the daily cell budget raises ``RuntimeError`` (no silent fallback)."""
    monkeypatch.setattr(_maps_settings, "azure_maps_matrix_daily_budget_cells", 5)
    from datetime import date

    az_maps._BUDGET_STATE["date"] = date.today()
    az_maps._BUDGET_STATE["cells"] = 0
    az_maps._BUDGET_STATE["warned"] = False

    with patch.object(az_maps, "_get_token", new=AsyncMock(return_value="fake-token")):
        with pytest.raises(RuntimeError, match="budget exceeded"):
            await get_matrix(_points())  # 9 cells > 5 budget


# ── VehicleSpec fingerprint ───────────────────────────────────────────────────

def test_vehicle_spec_cache_fingerprint_omits_defaults():
    spec = VehicleSpec(weight_kg=18000)
    fp = spec.cache_fingerprint()
    assert fp == {"weight_kg": 18000, "is_commercial": True}
    # Empty spec collapses
    assert VehicleSpec(is_commercial=False).cache_fingerprint() == {}
