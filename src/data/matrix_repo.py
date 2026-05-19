"""Repository for the ``matrix_cache`` container."""
from __future__ import annotations

import hashlib
import json

from src.data.base_repo import BaseRepository
from src.models.matrix import MatrixCacheEntry


class MatrixCacheRepo(BaseRepository[MatrixCacheEntry]):
    container_name = "matrix_cache"
    model = MatrixCacheEntry
    partition_key_field = "profile"

    @staticmethod
    def make_key(
        location_codes: list[str],
        vehicle_fingerprint: dict | None = None,
    ) -> str:
        """Stable cache key derived from sorted codes + optional vehicle spec.

        ``vehicle_fingerprint`` is a small dict of non-default vehicleSpec fields.
        When ``None`` (or empty) the key collapses to the legacy codes-only hash so
        existing cache entries remain reachable for the unweighted path.
        """
        joined = ",".join(sorted(location_codes))
        if vehicle_fingerprint:
            joined += "|" + json.dumps(vehicle_fingerprint, sort_keys=True, default=str)
        return hashlib.sha256(joined.encode("utf-8")).hexdigest()

    async def get_cached(
        self,
        location_codes: list[str],
        profile: str,
        vehicle_fingerprint: dict | None = None,
    ) -> MatrixCacheEntry | None:
        return await self.get(
            self.make_key(location_codes, vehicle_fingerprint),
            partition_key=profile,
        )

    async def put_cached(self, entry: MatrixCacheEntry) -> MatrixCacheEntry:
        """Upsert a cache entry; returns the entry unchanged."""
        return await self.upsert(entry)
