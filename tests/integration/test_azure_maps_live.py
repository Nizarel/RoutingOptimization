"""Live Azure Maps integration tests (require ``AZURE_MAPS_CLIENT_ID``)."""
from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.integration


SLC_POINTS = [
    ("SLC-DC", 40.8528, -111.925),
    ("SUGARHOUSE", 40.7251, -111.8551),
    ("OGDEN", 41.2230, -111.9738),
]


def _has_maps_creds() -> bool:
    return bool(os.getenv("AZURE_MAPS_CLIENT_ID"))


@pytest.mark.skipif(not _has_maps_creds(), reason="AZURE_MAPS_CLIENT_ID not set")
async def test_route_matrix_v2_live_returns_realistic_durations():
    """Live call to Route Matrix v2; assert distances exceed Haversine baselines."""
    from src.services.azure_maps import _haversine_matrix, get_matrix

    matrix = await get_matrix(SLC_POINTS, profile="truck")
    haversine = _haversine_matrix(SLC_POINTS)

    # Off-diagonal cells should be populated and road-network distance > great-circle
    for i in range(len(SLC_POINTS)):
        for j in range(len(SLC_POINTS)):
            if i == j:
                continue
            assert matrix.distance_m[i][j] > 0, f"empty cell ({i},{j})"
            assert matrix.time_sec[i][j] > 60, f"unrealistic duration ({i},{j})"
            assert matrix.distance_m[i][j] >= haversine.distance_m[i][j] * 0.95, (
                f"road distance {matrix.distance_m[i][j]:.0f} < 95% of Haversine "
                f"{haversine.distance_m[i][j]:.0f} at ({i},{j})"
            )


@pytest.mark.skipif(not _has_maps_creds(), reason="AZURE_MAPS_CLIENT_ID not set")
async def test_route_matrix_v2_live_with_vehicle_spec():
    """Vehicle spec should not break the call; result remains a valid matrix."""
    from src.services.azure_maps import VehicleSpec, get_matrix

    spec = VehicleSpec(weight_kg=20000, height_m=4.1, is_commercial=True)
    matrix = await get_matrix(SLC_POINTS, profile="truck", vehicle_spec=spec)

    assert len(matrix.distance_m) == len(SLC_POINTS)
    assert matrix.distance_m[0][1] > 0
