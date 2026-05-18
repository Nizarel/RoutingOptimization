"""``matrix_travel_times`` MCP tool — cached Azure Maps Route Matrix lookups."""
from __future__ import annotations

from datetime import UTC, datetime

from src.data.location_repo import LocationRepo
from src.data.matrix_repo import MatrixCacheRepo
from src.logging_config import get_logger
from src.models.matrix import MatrixCacheEntry
from src.models.requests import MatrixTravelTimesRequest, MatrixTravelTimesResponse
from src.server import mcp
from src.services.azure_maps import get_matrix, matrix_from_cache, to_sorted_cache_entry

log = get_logger(__name__)


@mcp.tool()
async def matrix_travel_times(req: MatrixTravelTimesRequest) -> MatrixTravelTimesResponse:
    """Return an NxN travel-time and distance matrix for the requested location codes.

    Results are cached in the ``matrix_cache`` Cosmos container (24-hour TTL).
    On a cache hit the stored matrix is returned immediately without calling
    Azure Maps.  On a miss the matrix is fetched from Azure Maps (or Haversine
    if ``azure_maps_client_id`` is not configured), persisted, and returned.

    The response ``location_codes`` list is always in *sorted* order so that
    ``response.distance_m[i][j]`` is the distance from
    ``location_codes[i]`` to ``location_codes[j]``.
    """
    sorted_codes = sorted(req.location_codes)
    cache_repo = MatrixCacheRepo()

    # ── Cache lookup ────────────────────────────────────────────────────────
    if req.use_cache:
        hit = await cache_repo.get_cached(sorted_codes, req.profile)
        if hit is not None:
            log.info("matrix_travel_times.cache_hit", n=len(sorted_codes), profile=req.profile)
            return MatrixTravelTimesResponse(
                location_codes=hit.location_codes,
                distance_m=hit.distance_matrix_m,
                time_sec=hit.time_matrix_sec,
                from_cache=True,
                profile=req.profile,
            )

    # ── Resolve coordinates ─────────────────────────────────────────────────
    loc_repo = LocationRepo()
    locations = await loc_repo.get_many_by_codes(sorted_codes)
    found = {loc.location_code: loc for loc in locations}
    missing = [c for c in sorted_codes if c not in found]
    if missing:
        raise ValueError(f"Unknown location codes: {missing}")

    points = [(c, found[c].lat, found[c].lon) for c in sorted_codes]

    # ── Fetch from Azure Maps (or Haversine fallback) ───────────────────────
    log.info("matrix_travel_times.fetch", n=len(sorted_codes), profile=req.profile)
    matrix = await get_matrix(points, profile=req.profile)

    # ── Persist to cache ────────────────────────────────────────────────────
    sorted_data = to_sorted_cache_entry(matrix, req.profile)
    entry = MatrixCacheEntry(
        id=MatrixCacheRepo.make_key(sorted_codes),
        profile=req.profile,
        location_codes=sorted_data["sorted_codes"],
        location_count=len(sorted_codes),
        distance_matrix_m=sorted_data["distance_m"],
        time_matrix_sec=sorted_data["time_sec"],
        fetched_at=datetime.now(UTC),
    )
    await cache_repo.put_cached(entry)

    log.info("matrix_travel_times.cached", n=len(sorted_codes), profile=req.profile)
    return MatrixTravelTimesResponse(
        location_codes=entry.location_codes,
        distance_m=entry.distance_matrix_m,
        time_sec=entry.time_matrix_sec,
        from_cache=False,
        profile=req.profile,
    )
