"""Unit tests for the matrix_travel_times tool and Azure Maps helpers (offline)."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.models.matrix import MatrixCacheEntry
from src.services.azure_maps import (
    Matrix,
    _haversine_matrix,
    matrix_from_cache,
    to_sorted_cache_entry,
)


# ── Helper factories ──────────────────────────────────────────────────────────

def _points() -> list[tuple[str, float, float]]:
    return [
        ("52-DC", 40.8528, -111.925),
        ("A", 40.76, -111.89),
        ("B", 40.69, -111.99),
    ]


def _make_cache_entry(codes: list[str], mat: Matrix, profile: str = "truck") -> MatrixCacheEntry:
    from src.data.matrix_repo import MatrixCacheRepo
    from datetime import UTC, datetime

    sorted_data = to_sorted_cache_entry(mat, profile)
    return MatrixCacheEntry(
        id=MatrixCacheRepo.make_key(codes),
        profile=profile,
        location_codes=sorted_data["sorted_codes"],
        location_count=len(codes),
        distance_matrix_m=sorted_data["distance_m"],
        time_matrix_sec=sorted_data["time_sec"],
        fetched_at=datetime.now(UTC),
    )


# ── azure_maps unit tests ─────────────────────────────────────────────────────

def test_haversine_matrix_symmetric():
    pts = _points()
    mat = _haversine_matrix(pts)
    n = len(pts)
    for i in range(n):
        assert mat.distance_m[i][i] == 0.0
        for j in range(n):
            assert abs(mat.distance_m[i][j] - mat.distance_m[j][i]) < 1e-6


def test_to_sorted_cache_entry_roundtrip():
    """Storing in sorted order and reading back should yield the same distances."""
    pts = _points()
    mat = _haversine_matrix(pts)

    sorted_data = to_sorted_cache_entry(mat, "truck")
    sorted_codes = sorted_data["sorted_codes"]

    # Build a MatrixCacheEntry-like object for matrix_from_cache
    class _FakeEntry:
        location_codes = sorted_codes
        distance_matrix_m = sorted_data["distance_m"]
        time_matrix_sec = sorted_data["time_sec"]

    # Re-order back to the original points order
    recovered = matrix_from_cache(_FakeEntry(), pts)

    for i in range(len(pts)):
        for j in range(len(pts)):
            assert abs(recovered.distance_m[i][j] - mat.distance_m[i][j]) < 1e-6, (
                f"Mismatch at ({i},{j}): {recovered.distance_m[i][j]} != {mat.distance_m[i][j]}"
            )


def test_matrix_from_cache_different_order():
    """matrix_from_cache must correctly re-index when request order differs from sorted order."""
    pts = [("C", 1.0, 2.0), ("A", 3.0, 4.0), ("B", 5.0, 6.0)]
    mat = _haversine_matrix(pts)

    class _FakeEntry:
        # Stored in sorted order: A, B, C
        location_codes = ["A", "B", "C"]
        sorted_pts = sorted(pts, key=lambda x: x[0])
        _sorted_mat = _haversine_matrix(sorted_pts)
        distance_matrix_m = _sorted_mat.distance_m
        time_matrix_sec = _sorted_mat.time_sec

    recovered = matrix_from_cache(_FakeEntry(), pts)
    # distance C→A == distance A→C (symmetric)
    assert abs(recovered.distance_m[0][1] - recovered.distance_m[1][0]) < 1e-6


# ── matrix_travel_times tool tests (Cosmos mocked) ───────────────────────────

@pytest.fixture()
def _fake_locations():
    """Three Location-like objects for the mock LocationRepo."""
    locs = []
    for code, lat, lon in _points():
        m = MagicMock()
        m.location_code = code
        m.lat = lat
        m.lon = lon
        locs.append(m)
    return locs


async def test_matrix_travel_times_cache_miss(_fake_locations):
    """On a cache miss the tool calls get_matrix and persists the entry."""
    from src.models.requests import MatrixTravelTimesRequest

    with (
        patch("src.tools.matrix.MatrixCacheRepo") as MockCacheRepo,
        patch("src.tools.matrix.LocationRepo") as MockLocRepo,
        patch("src.tools.matrix.get_matrix", new_callable=AsyncMock) as mock_get_matrix,
    ):
        # Cache miss
        MockCacheRepo.return_value.get_cached = AsyncMock(return_value=None)
        MockCacheRepo.return_value.put_cached = AsyncMock(return_value=None)
        MockCacheRepo.make_key = MagicMock(return_value="deadbeef")

        # Location resolution
        MockLocRepo.return_value.get_many_by_codes = AsyncMock(return_value=_fake_locations)

        # Azure Maps (Haversine since client_id not set)
        pts = _points()
        mock_get_matrix.return_value = _haversine_matrix(pts)

        from src.tools.matrix import matrix_travel_times

        req = MatrixTravelTimesRequest(
            location_codes=["52-DC", "A", "B"],
            profile="truck",
            use_cache=True,
        )
        resp = await matrix_travel_times(req)

    assert resp.from_cache is False
    assert resp.profile == "truck"
    assert len(resp.location_codes) == 3
    assert len(resp.distance_m) == 3
    MockCacheRepo.return_value.put_cached.assert_awaited_once()


async def test_matrix_travel_times_cache_hit(_fake_locations):
    """On a cache hit no Azure Maps call is made."""
    from src.models.requests import MatrixTravelTimesRequest

    pts = _points()
    mat = _haversine_matrix(pts)
    codes = ["52-DC", "A", "B"]
    fake_entry = _make_cache_entry(codes, mat)

    with (
        patch("src.tools.matrix.MatrixCacheRepo") as MockCacheRepo,
        patch("src.tools.matrix.get_matrix", new_callable=AsyncMock) as mock_get_matrix,
    ):
        MockCacheRepo.return_value.get_cached = AsyncMock(return_value=fake_entry)

        from src.tools.matrix import matrix_travel_times

        req = MatrixTravelTimesRequest(
            location_codes=codes,
            profile="truck",
            use_cache=True,
        )
        resp = await matrix_travel_times(req)

    assert resp.from_cache is True
    mock_get_matrix.assert_not_awaited()
    assert resp.location_codes == sorted(codes)
