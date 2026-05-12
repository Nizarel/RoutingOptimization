"""Repository for the ``matrix_cache`` container."""
from __future__ import annotations

import hashlib

from src.data.base_repo import BaseRepository
from src.models.matrix import MatrixCacheEntry


class MatrixCacheRepo(BaseRepository[MatrixCacheEntry]):
    container_name = "matrix_cache"
    model = MatrixCacheEntry
    partition_key_field = "profile"

    @staticmethod
    def make_key(location_codes: list[str]) -> str:
        """Stable cache key derived from a sorted list of location codes."""
        joined = ",".join(sorted(location_codes))
        return hashlib.sha256(joined.encode("utf-8")).hexdigest()

    async def get_cached(
        self, location_codes: list[str], profile: str
    ) -> MatrixCacheEntry | None:
        return await self.get(self.make_key(location_codes), partition_key=profile)
