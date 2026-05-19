"""Azure Maps Route Matrix client.

Uses the Azure Maps Route Matrix v1 API with Managed Identity auth
(``azure_maps_client_id`` setting + ``DefaultAzureCredential``).

Falls back to a Haversine stub when:
  - ``azure_maps_client_id`` is not configured (unit tests, local dev without
    Azure credentials), or
  - the Azure Maps call fails (network error, transient fault).

The public interface — ``get_matrix(points, profile)`` — is unchanged so that
callers (tools, tests) do not need to know which backend is active.

Matrices are stored and retrieved from ``matrix_cache`` in *sorted-code order*
so the cache key remains stable regardless of input ordering.  Helpers
:func:`to_sorted_cache_entry` and :func:`matrix_from_cache` handle the sort /
re-order conversion.
"""
from __future__ import annotations

import asyncio
import math
from dataclasses import asdict, dataclass, field
from datetime import UTC, date, datetime

import httpx
from azure.identity.aio import DefaultAzureCredential

from src.config import get_settings
from src.logging_config import get_logger

log = get_logger(__name__)

# ── Haversine fallback ────────────────────────────────────────────────────────
_AVG_TRUCK_SPEED_MPS = 45 * 1609.344 / 3600  # ~20.1 m/s

# ── Azure Maps Route Matrix v2 ───────────────────────────────────────────────
_ROUTE_MATRIX_API_VERSION = "2025-01-01"
# v2 sync supports up to 2500 cells; runtime guard comes from settings.
_MATRIX_V2_HARD_LIMIT = 2500

# ── Daily budget tracker (per-replica, in-memory) ─────────────────────────────
_BUDGET_LOCK = asyncio.Lock()
_BUDGET_STATE: dict[str, int | date | bool] = {
    "date": date.today(),
    "cells": 0,
    "warned": False,
}

# ── OTel meter (lazy) ─────────────────────────────────────────────────────────
_CELLS_COUNTER = None


def _cells_counter():
    global _CELLS_COUNTER
    if _CELLS_COUNTER is None:
        try:
            from opentelemetry import metrics

            meter = metrics.get_meter("src.services.azure_maps")
            _CELLS_COUNTER = meter.create_counter(
                "azure_maps_cells_total",
                unit="cell",
                description="Cumulative Azure Maps Route Matrix cells requested",
            )
        except Exception:  # noqa: BLE001
            _CELLS_COUNTER = False  # disable on failure
    return _CELLS_COUNTER or None


# ── Public dataclass ──────────────────────────────────────────────────────────

@dataclass(slots=True)
class Matrix:
    """Symmetric distance/time matrix for a list of points (meters / seconds)."""

    location_codes: list[str]
    distance_m: list[list[float]]
    time_sec: list[list[float]]


@dataclass(slots=True)
class VehicleSpec:
    """Truck dimensions/weight passed to Azure Maps Route Matrix v2.

    Units: SI (kg, meters, km/h). All fields optional; only non-None values are
    serialized into the ``vehicleSpec`` block of the request.
    """

    weight_kg: float | None = None
    axle_weight_kg: float | None = None
    length_m: float | None = None
    width_m: float | None = None
    height_m: float | None = None
    max_speed_kmh: float | None = None
    is_commercial: bool = True
    load_type: list[str] = field(default_factory=list)
    adr_tunnel_restriction_code: str | None = None

    def to_payload(self) -> dict:
        """Render as the ``vehicleSpec`` block. Camel-case keys per REST spec."""
        d: dict = {}
        if self.weight_kg is not None:
            d["weight"] = round(self.weight_kg)
        if self.axle_weight_kg is not None:
            d["axleWeight"] = round(self.axle_weight_kg)
        if self.length_m is not None:
            d["length"] = round(self.length_m, 2)
        if self.width_m is not None:
            d["width"] = round(self.width_m, 2)
        if self.height_m is not None:
            d["height"] = round(self.height_m, 2)
        if self.max_speed_kmh is not None:
            d["maxSpeed"] = round(self.max_speed_kmh)
        d["isVehicleCommercial"] = self.is_commercial
        if self.load_type:
            d["loadType"] = list(self.load_type)
        if self.adr_tunnel_restriction_code:
            d["adrTunnelRestrictionCode"] = self.adr_tunnel_restriction_code
        return d

    def cache_fingerprint(self) -> dict:
        """Stable dict used to derive a cache-key suffix."""
        return {k: v for k, v in asdict(self).items() if v not in (None, [], False)}


# ── Haversine helpers ─────────────────────────────────────────────────────────

def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6_371_000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _haversine_matrix(points: list[tuple[str, float, float]]) -> Matrix:
    n = len(points)
    dist = [[0.0] * n for _ in range(n)]
    time = [[0.0] * n for _ in range(n)]
    for i in range(n):
        _, lat_i, lon_i = points[i]
        for j in range(i + 1, n):
            _, lat_j, lon_j = points[j]
            d = _haversine_m(lat_i, lon_i, lat_j, lon_j)
            t = d / _AVG_TRUCK_SPEED_MPS
            dist[i][j] = dist[j][i] = d
            time[i][j] = time[j][i] = t
    return Matrix(
        location_codes=[code for code, _, _ in points],
        distance_m=dist,
        time_sec=time,
    )


# ── Cache conversion helpers ──────────────────────────────────────────────────

def to_sorted_cache_entry(matrix: Matrix, profile: str) -> "MatrixCacheEntryDict":
    """Return a dict suitable for creating a ``MatrixCacheEntry`` from a Matrix.

    The matrix rows/columns are re-ordered to *sorted* code order so the cache
    key (SHA-256 of sorted codes) and the stored data stay consistent.
    """
    sorted_codes = sorted(matrix.location_codes)
    idx = {code: i for i, code in enumerate(matrix.location_codes)}
    order = [idx[c] for c in sorted_codes]
    n = len(order)
    dist = [[matrix.distance_m[order[i]][order[j]] for j in range(n)] for i in range(n)]
    time = [[matrix.time_sec[order[i]][order[j]] for j in range(n)] for i in range(n)]
    return {
        "sorted_codes": sorted_codes,
        "distance_m": dist,
        "time_sec": time,
    }


def matrix_from_cache(entry: "MatrixCacheEntryLike", points: list[tuple[str, float, float]]) -> Matrix:
    """Re-index a cached (sorted-order) matrix to match ``points`` order."""
    idx = {code: i for i, code in enumerate(entry.location_codes)}
    order = [idx[code] for code, _, _ in points]
    n = len(order)
    dist = [[entry.distance_matrix_m[order[i]][order[j]] for j in range(n)] for i in range(n)]
    time = [[entry.time_matrix_sec[order[i]][order[j]] for j in range(n)] for i in range(n)]
    return Matrix(
        location_codes=[code for code, _, _ in points],
        distance_m=dist,
        time_sec=time,
    )


# ── Azure Maps HTTP helpers (Route Matrix v2) ────────────────────────────────

def _build_v2_body(
    points: list[tuple[str, float, float]],
    profile: str,
    vehicle_spec: "VehicleSpec | None",
) -> dict:
    """Build the GeoJSON FeatureCollection body for Route Matrix v2.

    Two Features, both MultiPoint of all ``points`` (square NxN matrix), with
    ``properties.pointType`` set to ``origins`` and ``destinations``.
    """
    coords = [[lon, lat] for _, lat, lon in points]
    multipoint = {"type": "MultiPoint", "coordinates": coords}
    body: dict = {
        "type": "FeatureCollection",
        "features": [
            {"type": "Feature", "geometry": multipoint, "properties": {"pointType": "origins"}},
            {"type": "Feature", "geometry": multipoint, "properties": {"pointType": "destinations"}},
        ],
        "travelMode": profile,
        "routeOutputOptions": ["routeSummary"],
        "optimizeRoute": "fastestWithoutTraffic",
        "traffic": "historical",
    }
    if vehicle_spec is not None:
        payload = vehicle_spec.to_payload()
        if payload:
            body["vehicleSpec"] = payload
    return body


def _parse_v2_response(data: dict, points: list[tuple[str, float, float]]) -> Matrix:
    n = len(points)
    dist = [[0.0] * n for _ in range(n)]
    time = [[0.0] * n for _ in range(n)]
    haversine = _haversine_matrix(points)
    cells = (
        data.get("properties", {}).get("matrix")
        or data.get("matrix")  # tolerant of either shape
        or []
    )
    for cell in cells:
        i = int(cell.get("originIndex", -1))
        j = int(cell.get("destinationIndex", -1))
        if not (0 <= i < n and 0 <= j < n):
            continue
        status = int(cell.get("statusCode", 200))
        if status != 200:
            dist[i][j] = haversine.distance_m[i][j]
            time[i][j] = haversine.time_sec[i][j]
            continue
        dist[i][j] = float(cell.get("distanceInMeters", 0) or 0)
        time[i][j] = float(
            cell.get("durationTrafficInSeconds")
            or cell.get("durationInSeconds")
            or 0
        )
    return Matrix(
        location_codes=[code for code, _, _ in points],
        distance_m=dist,
        time_sec=time,
    )


async def _get_token(settings) -> str:  # type: ignore[no-untyped-def]
    async with DefaultAzureCredential() as credential:
        token_obj = await credential.get_token("https://atlas.microsoft.com/.default")
        return token_obj.token


async def _check_and_charge_budget(cells: int, daily_budget: int | None) -> None:
    """Roll the daily counter and enforce the budget. Raises ``RuntimeError`` over budget."""
    if daily_budget is None:
        return
    today = date.today()
    async with _BUDGET_LOCK:
        if _BUDGET_STATE["date"] != today:
            _BUDGET_STATE["date"] = today
            _BUDGET_STATE["cells"] = 0
            _BUDGET_STATE["warned"] = False
        current = int(_BUDGET_STATE["cells"])  # type: ignore[arg-type]
        if current + cells > daily_budget:
            log.error(
                "azure_maps.matrix_budget_exceeded",
                requested=cells, used=current, budget=daily_budget,
            )
            raise RuntimeError(
                f"Azure Maps daily cell budget exceeded ({current}+{cells} > {daily_budget})"
            )
        _BUDGET_STATE["cells"] = current + cells
        if (
            not _BUDGET_STATE["warned"]
            and (current + cells) >= int(0.8 * daily_budget)
        ):
            _BUDGET_STATE["warned"] = True
            log.warning(
                "azure_maps.matrix_budget_warn_80pct",
                used=current + cells, budget=daily_budget,
            )


async def _fetch_v2_sync(
    client: httpx.AsyncClient,
    token: str,
    client_id: str,
    base_url: str,
    points: list[tuple[str, float, float]],
    profile: str,
    vehicle_spec: "VehicleSpec | None",
) -> Matrix:
    resp = await client.post(
        f"{base_url}/route/matrix",
        params={"api-version": _ROUTE_MATRIX_API_VERSION},
        headers={
            "Authorization": f"Bearer {token}",
            "x-ms-client-id": client_id,
            "Content-Type": "application/json",
        },
        json=_build_v2_body(points, profile, vehicle_spec),
        timeout=90.0,
    )
    resp.raise_for_status()
    return _parse_v2_response(resp.json(), points)


# ── Public API ────────────────────────────────────────────────────────────────

async def get_matrix(
    points: list[tuple[str, float, float]],
    profile: str = "truck",
    *,
    vehicle_spec: "VehicleSpec | None" = None,
) -> Matrix:
    """Return an NxN travel-time/distance matrix for ``points = [(code, lat, lon), ...]``.

    Calls the Azure Maps Route Matrix v2 API (api-version=2025-01-01) when
    ``azure_maps_client_id`` is set; falls back to Haversine otherwise.
    """
    settings = get_settings()
    client_id = settings.azure_maps_client_id
    n = len(points)
    cells = n * n

    if not client_id:
        log.info("azure_maps.haversine_fallback", reason="client_id_not_set", n=n)
        return _haversine_matrix(points)

    max_cells = min(settings.azure_maps_matrix_max_cells, _MATRIX_V2_HARD_LIMIT)
    if cells > max_cells:
        raise ValueError(
            f"Matrix request too large: {cells} cells (limit={max_cells}). "
            f"Chunk the location list and merge results."
        )

    await _check_and_charge_budget(cells, settings.azure_maps_matrix_daily_budget_cells)

    started = datetime.now(UTC)
    counter = _cells_counter()
    if counter is not None:
        try:
            counter.add(cells, {"profile": profile, "weighted": vehicle_spec is not None})
        except Exception:  # noqa: BLE001
            pass

    try:
        token = await _get_token(settings)
        async with httpx.AsyncClient() as client:
            log.info(
                "azure_maps.matrix_sync_v2",
                n=n, cells=cells, profile=profile,
                weighted=vehicle_spec is not None,
            )
            result = await _fetch_v2_sync(
                client, token, client_id, settings.azure_maps_base_url,
                points, profile, vehicle_spec,
            )
            latency_ms = int((datetime.now(UTC) - started).total_seconds() * 1000)
            log.info(
                "azure_maps.matrix_call",
                n=n, cells=cells, latency_ms=latency_ms,
                status="ok", weighted=vehicle_spec is not None,
            )
            return result
    except Exception as exc:  # noqa: BLE001
        latency_ms = int((datetime.now(UTC) - started).total_seconds() * 1000)
        log.warning(
            "azure_maps.matrix_failed_fallback",
            error=str(exc), n=n, cells=cells, latency_ms=latency_ms,
        )
        return _haversine_matrix(points)


# ── Geocode / Directions / Isochrone / Map Render ───────────────────────────

import base64

# Single-pixel transparent PNG used as the offline-stub for map_render.
_STUB_PNG_BASE64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="
)

# Process-wide LRU cache for geocode results.
_GEOCODE_CACHE: dict[tuple[str, str | None, int], list[dict]] = {}
_GEOCODE_CACHE_LOCK = asyncio.Lock()
_GEOCODE_CACHE_MAX = 512


@dataclass(slots=True)
class GeocodeHit:
    formatted_address: str
    lat: float
    lon: float
    confidence: float | None = None
    match_type: str | None = None


async def geocode(query: str, *, country: str | None = None, top: int = 1) -> list[GeocodeHit]:
    """Geocode a free-form address via Azure Maps Search Address v1.

    Returns ``[]`` when ``azure_maps_client_id`` is not configured (offline stub)
    or when the upstream call fails.
    """
    settings = get_settings()
    client_id = settings.azure_maps_client_id
    if not client_id:
        log.info("azure_maps.geocode_stub", reason="client_id_not_set", query=query)
        return []

    key = (query.strip().lower(), country, top)
    async with _GEOCODE_CACHE_LOCK:
        cached = _GEOCODE_CACHE.get(key)
        if cached is not None:
            return [GeocodeHit(**h) for h in cached]

    try:
        token = await _get_token(settings)
        params: dict[str, str | int] = {
            "api-version": "1.0",
            "query": query,
            "limit": top,
        }
        if country:
            params["countrySet"] = country
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{settings.azure_maps_base_url}/search/address/json",
                params=params,
                headers={"Authorization": f"Bearer {token}", "x-ms-client-id": client_id},
                timeout=30.0,
            )
            resp.raise_for_status()
            data = resp.json()
    except Exception as exc:  # noqa: BLE001
        log.warning("azure_maps.geocode_failed", error=str(exc), query=query)
        return []

    hits: list[GeocodeHit] = []
    for r in data.get("results", [])[:top]:
        pos = r.get("position", {})
        addr = r.get("address", {})
        hits.append(
            GeocodeHit(
                formatted_address=addr.get("freeformAddress", query),
                lat=float(pos.get("lat", 0.0)),
                lon=float(pos.get("lon", 0.0)),
                confidence=float(r["score"]) if "score" in r else None,
                match_type=r.get("matchConfidence", {}).get("score") if isinstance(r.get("matchConfidence"), dict) else r.get("type"),
            )
        )

    async with _GEOCODE_CACHE_LOCK:
        if len(_GEOCODE_CACHE) >= _GEOCODE_CACHE_MAX:
            _GEOCODE_CACHE.pop(next(iter(_GEOCODE_CACHE)))
        _GEOCODE_CACHE[key] = [h.__dict__ for h in hits]
    return hits


@dataclass(slots=True)
class DirectionsLegResult:
    start_lat: float
    start_lon: float
    end_lat: float
    end_lon: float
    distance_m: float
    duration_sec: float


@dataclass(slots=True)
class DirectionsResult:
    distance_m: float
    duration_sec: float
    legs: list[DirectionsLegResult]
    from_stub: bool = False


def _haversine_directions(
    origin: tuple[float, float],
    destination: tuple[float, float],
    waypoints: list[tuple[float, float]],
) -> DirectionsResult:
    pts = [origin, *waypoints, destination]
    legs: list[DirectionsLegResult] = []
    total_d = 0.0
    total_t = 0.0
    for i in range(len(pts) - 1):
        d = _haversine_m(pts[i][0], pts[i][1], pts[i + 1][0], pts[i + 1][1])
        t = d / _AVG_TRUCK_SPEED_MPS
        legs.append(DirectionsLegResult(pts[i][0], pts[i][1], pts[i + 1][0], pts[i + 1][1], d, t))
        total_d += d
        total_t += t
    return DirectionsResult(distance_m=total_d, duration_sec=total_t, legs=legs, from_stub=True)


async def directions(
    origin: tuple[float, float],
    destination: tuple[float, float],
    *,
    waypoints: list[tuple[float, float]] | None = None,
    profile: str = "truck",
    avoid: list[str] | None = None,
) -> DirectionsResult:
    """Compute a route via Azure Maps Directions v1.

    ``origin``/``destination``/``waypoints`` are ``(lat, lon)`` tuples.
    Falls back to a single-leg Haversine stub when ``azure_maps_client_id`` is
    not configured or the upstream call fails.
    """
    settings = get_settings()
    client_id = settings.azure_maps_client_id
    waypoints = waypoints or []
    if not client_id:
        log.info("azure_maps.directions_stub", reason="client_id_not_set")
        return _haversine_directions(origin, destination, waypoints)

    coord_list = [origin, *waypoints, destination]
    query = ":".join(f"{lat},{lon}" for lat, lon in coord_list)
    params: dict[str, str] = {
        "api-version": "1.0",
        "query": query,
        "travelMode": profile,
        "routeType": "fastest",
    }
    if avoid:
        params["avoid"] = ",".join(avoid)
    try:
        token = await _get_token(settings)
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{settings.azure_maps_base_url}/route/directions/json",
                params=params,
                headers={"Authorization": f"Bearer {token}", "x-ms-client-id": client_id},
                timeout=60.0,
            )
            resp.raise_for_status()
            data = resp.json()
    except Exception as exc:  # noqa: BLE001
        log.warning("azure_maps.directions_failed", error=str(exc))
        return _haversine_directions(origin, destination, waypoints)

    routes = data.get("routes", [])
    if not routes:
        return _haversine_directions(origin, destination, waypoints)
    route = routes[0]
    summary = route.get("summary", {})
    legs_out: list[DirectionsLegResult] = []
    for i, leg in enumerate(route.get("legs", [])):
        ls = leg.get("summary", {})
        start = coord_list[i]
        end = coord_list[min(i + 1, len(coord_list) - 1)]
        legs_out.append(
            DirectionsLegResult(
                start_lat=start[0],
                start_lon=start[1],
                end_lat=end[0],
                end_lon=end[1],
                distance_m=float(ls.get("lengthInMeters", 0)),
                duration_sec=float(ls.get("travelTimeInSeconds", 0)),
            )
        )
    return DirectionsResult(
        distance_m=float(summary.get("lengthInMeters", 0)),
        duration_sec=float(summary.get("travelTimeInSeconds", 0)),
        legs=legs_out,
        from_stub=False,
    )


@dataclass(slots=True)
class IsochroneResult:
    polygon: list[list[float]]  # list of [lon, lat]
    reachable_area_km2: float | None
    from_stub: bool = False


def _stub_isochrone(origin: tuple[float, float], max_minutes: int) -> IsochroneResult:
    """32-vertex circle whose radius matches ``max_minutes`` at ~45 mph."""
    lat0, lon0 = origin
    radius_m = _AVG_TRUCK_SPEED_MPS * 60 * max_minutes
    # Approx degrees per meter (lat is ~constant, lon depends on cos(lat))
    deg_per_m_lat = 1.0 / 111_320.0
    deg_per_m_lon = 1.0 / (111_320.0 * max(math.cos(math.radians(lat0)), 1e-6))
    vertices: list[list[float]] = []
    for k in range(32):
        theta = 2 * math.pi * k / 32
        dlat = radius_m * math.sin(theta) * deg_per_m_lat
        dlon = radius_m * math.cos(theta) * deg_per_m_lon
        vertices.append([lon0 + dlon, lat0 + dlat])
    vertices.append(vertices[0])  # close ring
    area_km2 = math.pi * (radius_m / 1000.0) ** 2
    return IsochroneResult(polygon=vertices, reachable_area_km2=area_km2, from_stub=True)


async def isochrone(
    origin: tuple[float, float],
    max_minutes: int,
    *,
    profile: str = "truck",
) -> IsochroneResult:
    """Compute an isochrone polygon via Azure Maps Route Range v1.

    Falls back to a 32-vertex Haversine circle stub when offline.
    """
    settings = get_settings()
    client_id = settings.azure_maps_client_id
    if not client_id:
        log.info("azure_maps.isochrone_stub", reason="client_id_not_set")
        return _stub_isochrone(origin, max_minutes)

    try:
        token = await _get_token(settings)
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{settings.azure_maps_base_url}/route/range/json",
                params={
                    "api-version": "1.0",
                    "query": f"{origin[0]},{origin[1]}",
                    "travelMode": profile,
                    "timeBudgetInSec": max_minutes * 60,
                },
                headers={"Authorization": f"Bearer {token}", "x-ms-client-id": client_id},
                timeout=60.0,
            )
            resp.raise_for_status()
            data = resp.json()
    except Exception as exc:  # noqa: BLE001
        log.warning("azure_maps.isochrone_failed", error=str(exc))
        return _stub_isochrone(origin, max_minutes)

    boundary = data.get("reachableRange", {}).get("boundary", [])
    polygon = [[float(p["longitude"]), float(p["latitude"])] for p in boundary]
    if polygon and polygon[0] != polygon[-1]:
        polygon.append(polygon[0])
    return IsochroneResult(polygon=polygon, reachable_area_km2=None, from_stub=False)


@dataclass(slots=True)
class MapRenderResult:
    image_base64: str
    width: int
    height: int
    from_stub: bool = False


async def render_map(
    *,
    center: tuple[float, float] | None,
    zoom: int = 8,
    width: int = 800,
    height: int = 600,
    pins: list[tuple[float, float, str | None]] | None = None,
    path_points: list[tuple[float, float]] | None = None,
) -> MapRenderResult:
    """Render a static PNG via Azure Maps Render v2.

    Returns a 1x1 transparent PNG stub when ``azure_maps_client_id`` is unset.
    """
    settings = get_settings()
    client_id = settings.azure_maps_client_id
    pins = pins or []
    path_points = path_points or []
    if not client_id:
        log.info("azure_maps.map_render_stub", reason="client_id_not_set")
        return MapRenderResult(image_base64=_STUB_PNG_BASE64, width=1, height=1, from_stub=True)

    params: dict[str, str | int] = {
        "api-version": "2024-04-01",
        "tilesetId": "microsoft.base.road",
        "width": width,
        "height": height,
        "zoom": zoom,
    }
    if center is not None:
        params["center"] = f"{center[1]},{center[0]}"  # lon,lat
    if pins:
        pin_parts = ["default|co0078D4"]
        for lat, lon, label in pins:
            pin_parts.append(f"||{lon} {lat}" + (f' "{label}"' if label else ""))
        params["pins"] = "".join(pin_parts)
    if path_points:
        path = "lcFF0000|lw3|" + "|".join(f"{lon} {lat}" for lat, lon in path_points)
        params["path"] = path
    try:
        token = await _get_token(settings)
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{settings.azure_maps_base_url}/map/static/png",
                params=params,
                headers={"Authorization": f"Bearer {token}", "x-ms-client-id": client_id},
                timeout=60.0,
            )
            resp.raise_for_status()
            png_bytes = resp.content
    except Exception as exc:  # noqa: BLE001
        log.warning("azure_maps.map_render_failed", error=str(exc))
        return MapRenderResult(image_base64=_STUB_PNG_BASE64, width=1, height=1, from_stub=True)

    return MapRenderResult(
        image_base64=base64.b64encode(png_bytes).decode("ascii"),
        width=width,
        height=height,
        from_stub=False,
    )


# ── Type stubs for cache helpers (avoid circular import) ─────────────────────
# These match the fields accessed on MatrixCacheEntry; no runtime import needed.
class MatrixCacheEntryDict:  # pragma: no cover
    pass


class MatrixCacheEntryLike:  # pragma: no cover
    location_codes: list[str]
    distance_matrix_m: list[list[float]]
    time_matrix_sec: list[list[float]]
