"""Repository for the ``locations`` container."""
from __future__ import annotations

from src.data.base_repo import BaseRepository
from src.models.location import Location


class LocationRepo(BaseRepository[Location]):
    container_name = "locations"
    model = Location
    partition_key_field = "location_type"

    async def get_by_code(self, location_code: str) -> Location | None:
        results = await self.query(
            "SELECT * FROM c WHERE c.location_code = @code",
            parameters=[{"name": "@code", "value": location_code}],
            max_items=1,
        )
        return results[0] if results else None

    async def get_many_by_codes(self, codes: list[str]) -> list[Location]:
        if not codes:
            return []
        # Cosmos has a small limit on IN list size; chunk if needed.
        return await self.query(
            "SELECT * FROM c WHERE ARRAY_CONTAINS(@codes, c.location_code)",
            parameters=[{"name": "@codes", "value": codes}],
        )

    async def list_by_type(self, location_type: str) -> list[Location]:
        return await self.query(
            "SELECT * FROM c WHERE c.location_type = @t",
            parameters=[{"name": "@t", "value": location_type}],
            partition_key=location_type,
        )
