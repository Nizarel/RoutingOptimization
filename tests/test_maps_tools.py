"""Unit tests for geocode_address, directions, isochrone, map_render tools (offline stubs)."""
from __future__ import annotations

import base64

import pytest

from src.config import get_settings
from src.models.requests import (
    DirectionsRequest,
    GeocodeRequest,
    GeoPointLL,
    IsochroneRequest,
    MapRenderRequest,
)
from src.services import azure_maps
from src.tools.directions import directions
from src.tools.geocode import geocode_address
from src.tools.isochrone import isochrone
from src.tools.map_render import map_render


@pytest.fixture(autouse=True)
def _force_stub(monkeypatch):
    """Ensure azure_maps_client_id is unset so the offline stub paths run."""
    monkeypatch.setattr(
        get_settings(), "azure_maps_client_id", None, raising=False
    )
    # Clear the geocode LRU between tests.
    azure_maps._GEOCODE_CACHE.clear()


# ── geocode_address ──────────────────────────────────────────────────────────

async def test_geocode_address_stub_returns_empty():
    resp = await geocode_address(GeocodeRequest(query="123 Main St, Salt Lake City"))
    assert resp.candidates == []
    assert resp.from_stub is True
    assert resp.query == "123 Main St, Salt Lake City"


async def test_geocode_address_top_clamped_in_model():
    # Pydantic should reject top > 10.
    with pytest.raises(Exception):
        GeocodeRequest(query="x", top=99)


# ── directions ───────────────────────────────────────────────────────────────

async def test_directions_stub_haversine_no_waypoints():
    req = DirectionsRequest(
        origin=GeoPointLL(lat=40.85, lon=-111.93),
        destination=GeoPointLL(lat=40.76, lon=-111.89),
    )
    resp = await directions(req)
    assert resp.from_stub is True
    assert resp.distance_m > 0
    assert resp.duration_sec > 0
    assert len(resp.legs) == 1
    assert resp.legs[0].start.lat == pytest.approx(40.85)
    assert resp.legs[0].end.lat == pytest.approx(40.76)


async def test_directions_stub_with_waypoints():
    req = DirectionsRequest(
        origin=GeoPointLL(lat=40.85, lon=-111.93),
        destination=GeoPointLL(lat=40.76, lon=-111.89),
        waypoints=[GeoPointLL(lat=40.80, lon=-111.91)],
    )
    resp = await directions(req)
    assert resp.from_stub is True
    assert len(resp.legs) == 2
    assert resp.distance_m == pytest.approx(
        resp.legs[0].distance_m + resp.legs[1].distance_m
    )


# ── isochrone ────────────────────────────────────────────────────────────────

async def test_isochrone_stub_returns_closed_polygon():
    req = IsochroneRequest(
        origin=GeoPointLL(lat=40.85, lon=-111.93),
        max_minutes=30,
    )
    resp = await isochrone(req)
    assert resp.from_stub is True
    assert len(resp.polygon) == 33  # 32 vertices + closing point
    assert resp.polygon[0] == resp.polygon[-1]
    assert resp.reachable_area_km2 is not None and resp.reachable_area_km2 > 0
    assert resp.max_minutes == 30


async def test_isochrone_radius_scales_with_minutes():
    origin = GeoPointLL(lat=40.0, lon=-111.0)
    short = await isochrone(IsochroneRequest(origin=origin, max_minutes=15))
    long = await isochrone(IsochroneRequest(origin=origin, max_minutes=60))
    assert long.reachable_area_km2 > short.reachable_area_km2 * 10  # area ~ r^2


# ── map_render ───────────────────────────────────────────────────────────────

async def test_map_render_stub_returns_transparent_png():
    req = MapRenderRequest(
        center=GeoPointLL(lat=40.85, lon=-111.93),
        zoom=8,
    )
    resp = await map_render(req)
    assert resp.from_stub is True
    assert resp.content_type == "image/png"
    assert resp.width == 1 and resp.height == 1
    # Stub returns a tiny but valid PNG (starts with 8-byte PNG signature).
    raw = base64.b64decode(resp.image_base64)
    assert raw[:8] == b"\x89PNG\r\n\x1a\n"
