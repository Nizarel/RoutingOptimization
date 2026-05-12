"""Repository for the ``districts`` container."""
from __future__ import annotations

from src.data.base_repo import BaseRepository
from src.models.matrix import District


class DistrictRepo(BaseRepository[District]):
    container_name = "districts"
    model = District
    partition_key_field = "dc_code"

    async def list_for_dc(self, dc_code: str) -> list[District]:
        return await self.query(
            "SELECT * FROM c WHERE c.dc_code = @dc",
            parameters=[{"name": "@dc", "value": dc_code}],
            partition_key=dc_code,
        )

    async def get_by_handle(self, dc_code: str, district_handle: str) -> District | None:
        results = await self.query(
            "SELECT * FROM c WHERE c.dc_code = @dc AND c.district_handle = @h",
            parameters=[
                {"name": "@dc", "value": dc_code},
                {"name": "@h", "value": district_handle},
            ],
            partition_key=dc_code,
            max_items=1,
        )
        return results[0] if results else None
