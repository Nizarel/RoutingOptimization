"""Repository for the ``trailer_types`` container."""
from __future__ import annotations

from src.data.base_repo import BaseRepository
from src.models.trailer import TrailerType


class TrailerRepo(BaseRepository[TrailerType]):
    container_name = "trailer_types"
    model = TrailerType
    partition_key_field = "trailer_class"

    async def get_by_id(self, trailer_id: str, trailer_class: str) -> TrailerType | None:
        return await self.get(trailer_id, partition_key=trailer_class)

    async def find_by_id(self, trailer_id: str) -> TrailerType | None:
        results = await self.query(
            "SELECT * FROM c WHERE c.id = @id",
            parameters=[{"name": "@id", "value": trailer_id}],
            max_items=1,
        )
        return results[0] if results else None

    async def list_all(self) -> list[TrailerType]:
        return await self.query("SELECT * FROM c")
