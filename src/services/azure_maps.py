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
from dataclasses import dataclass
from datetime import UTC, datetime

import httpx
from azure.identity.aio import DefaultAzureCredential

from src.config import get_settings
from src.logging_config import get_logger

log = get_logger(__name__)

# ── Haversine fallback ────────────────────────────────────────────────────────
_AVG_TRUCK_SPEED_MPS = 45 * 1609.344 / 3600  # ~20.1 m/s

# ── Azure Maps limits ─────────────────────────────────────────────────────────
# Sync endpoint supports ≤700 origin×destination cells (origins==destinations
# for our square matrix, so ≤26×26 = 676).
_SYNC_CELL_LIMIT = 700
# Polling config for the async endpoint.
_ASYNC_POLL_INTERVAL_SEC = 3
_ASYNC_POLL_TIMEOUT_SEC = 300


# ── Public dataclass ──────────────────────────────────────────────────────────

@dataclass(slots=True)
class Matrix:
    """Symmetric distance/time matrix for a list of points (meters / seconds)."""

    location_codes: list[str]
    distance_m: list[list[float]]
    time_sec: list[list[float]]


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


# ── Azure Maps HTTP helpers ───────────────────────────────────────────────────

def _build_request_body(points: list[tuple[str, float, float]]) -> dict:
    coords = [[lon, lat] for _, lat, lon in points]
    return {
        "origins": {"type": "MultiPoint", "coordinates": coords},
        "destinations": {"type": "MultiPoint", "coordinates": coords},
    }


def _parse_response(data: dict, points: list[tuple[str, float, float]]) -> Matrix:
    n = len(points)
    dist = [[0.0] * n for _ in range(n)]
    time = [[0.0] * n for _ in range(n)]
    for i, row in enumerate(data["matrix"]):
        for j, cell in enumerate(row):
            summary = cell.get("response", {}).get("routeSummary", {})
            dist[i][j] = float(summary.get("lengthInMeters", 0))
            time[i][j] = float(summary.get("travelTimeInSeconds", 0))
    return Matrix(
        location_codes=[code for code, _, _ in points],
        distance_m=dist,
        time_sec=time,
    )


async def _get_token(settings) -> str:  # type: ignore[no-untyped-def]
    async with DefaultAzureCredential() as credential:
        token_obj = await credential.get_token("https://atlas.microsoft.com/.default")
        return token_obj.token


async def _fetch_sync(
    client: httpx.AsyncClient,
    token: str,
    client_id: str,
    base_url: str,
    points: list[tuple[str, float, float]],
    profile: str,
) -> Matrix:
    resp = await client.post(
        f"{base_url}/route/matrix/sync/json",
        params={"api-version": "1.0", "travelMode": profile, "routeType": "fastest"},
        headers={
            "Authorization": f"Bearer {token}",
            "x-ms-client-id": client_id,
            "Content-Type": "application/json",
        },
        json=_build_request_body(points),
        timeout=60.0,
    )
    resp.raise_for_status()
    return _parse_response(resp.json(), points)


async def _fetch_async(
    client: httpx.AsyncClient,
    token: str,
    client_id: str,
    base_url: str,
    points: list[tuple[str, float, float]],
    profile: str,
) -> Matrix:
    resp = await client.post(
        f"{base_url}/route/matrix/json",
        params={"api-version": "1.0", "travelMode": profile, "routeType": "fastest"},
        headers={
            "Authorization": f"Bearer {token}",
            "x-ms-client-id": client_id,
            "Content-Type": "application/json",
        },
        json=_build_request_body(points),
        timeout=30.0,
    )
    if resp.status_code == 200:
        return _parse_response(resp.json(), points)
    if resp.status_code != 202:
        resp.raise_for_status()

    poll_url = resp.headers.get("Location")
    if not poll_url:
        raise RuntimeError("Azure Maps async matrix: missing Location header in 202 response")

    log.info("azure_maps.matrix_async_submitted", poll_url=poll_url)
    elapsed = 0
    while elapsed < _ASYNC_POLL_TIMEOUT_SEC:
        await asyncio.sleep(_ASYNC_POLL_INTERVAL_SEC)
        elapsed += _ASYNC_POLL_INTERVAL_SEC
        poll_resp = await client.get(
            poll_url,
            headers={"Authorization": f"Bearer {token}", "x-ms-client-id": client_id},
            timeout=30.0,
        )
        if poll_resp.status_code == 200:
            return _parse_response(poll_resp.json(), points)
        if poll_resp.status_code != 202:
            poll_resp.raise_for_status()

    raise TimeoutError(f"Azure Maps async matrix did not complete within {_ASYNC_POLL_TIMEOUT_SEC}s")


# ── Public API ────────────────────────────────────────────────────────────────

async def get_matrix(
    points: list[tuple[str, float, float]],
    profile: str = "truck",
) -> Matrix:
    """Return an NxN travel-time/distance matrix for ``points = [(code, lat, lon), ...]``.

    Calls the Azure Maps Route Matrix v1 API when ``azure_maps_client_id`` is
    set; falls back to Haversine otherwise.
    """
    settings = get_settings()
    client_id = settings.azure_maps_client_id

    if not client_id:
        log.info("azure_maps.haversine_fallback", reason="client_id_not_set", n=len(points))
        return _haversine_matrix(points)

    n = len(points)
    cells = n * n

    try:
        token = await _get_token(settings)
        async with httpx.AsyncClient() as client:
            if cells <= _SYNC_CELL_LIMIT:
                log.info("azure_maps.matrix_sync", n=n, cells=cells, profile=profile)
                return await _fetch_sync(client, token, client_id, settings.azure_maps_base_url, points, profile)
            else:
                log.info("azure_maps.matrix_async", n=n, cells=cells, profile=profile)
                return await _fetch_async(client, token, client_id, settings.azure_maps_base_url, points, profile)
    except Exception as exc:  # noqa: BLE001
        log.warning("azure_maps.matrix_failed_fallback", error=str(exc), n=n)
        return _haversine_matrix(points)


# ── Type stubs for cache helpers (avoid circular import) ─────────────────────
# These match the fields accessed on MatrixCacheEntry; no runtime import needed.
class MatrixCacheEntryDict:  # pragma: no cover
    pass


class MatrixCacheEntryLike:  # pragma: no cover
    location_codes: list[str]
    distance_matrix_m: list[list[float]]
    time_matrix_sec: list[list[float]]
