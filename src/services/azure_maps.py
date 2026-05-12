"""Distance/time matrix provider.

In the walking skeleton this is a Haversine-based stub so that the OR-Tools
solver can run end-to-end without requiring an Azure Maps subscription key.
The real Azure Maps Route Matrix client lands in a follow-up plan; this module's
public surface (:func:`get_matrix`) will not change.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

# Average truck speed used to derive a duration from straight-line distance.
# Conservative figure for mixed highway/urban routing (mph -> m/s).
_AVG_TRUCK_SPEED_MPS = 45 * 1609.344 / 3600  # ~20.1 m/s


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance between two WGS84 points, in meters."""
    r = 6_371_000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


@dataclass(slots=True)
class Matrix:
    """Symmetric distance/time matrix for a list of points (meters / seconds)."""

    location_codes: list[str]
    distance_m: list[list[float]]
    time_sec: list[list[float]]


async def get_matrix(
    points: list[tuple[str, float, float]],
    profile: str = "truck",  # noqa: ARG001 — reserved for the real Azure Maps client
) -> Matrix:
    """Return an NxN Haversine-derived matrix for ``points = [(code, lat, lon), ...]``.

    Times are derived from a constant truck speed; this is *only* good enough
    to exercise the solver and is replaced by Azure Maps Route Matrix in a
    follow-up phase.
    """
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
