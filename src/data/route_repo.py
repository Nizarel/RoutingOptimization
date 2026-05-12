"""Repository for the ``route_history`` container."""
from __future__ import annotations

from src.data.base_repo import BaseRepository
from src.models.route import RouteHistory


class RouteRepo(BaseRepository[RouteHistory]):
    container_name = "route_history"
    model = RouteHistory
    partition_key_field = "dc_code"

    async def get_by_id(self, history_id: str, dc_code: str) -> RouteHistory | None:
        return await self.get(history_id, partition_key=dc_code)

    async def latest(self, dc_code: str | None = None, limit: int = 1) -> list[RouteHistory]:
        if dc_code is not None:
            return await self.query(
                "SELECT TOP @n * FROM c WHERE c.dc_code = @dc ORDER BY c.created_at DESC",
                parameters=[
                    {"name": "@n", "value": limit},
                    {"name": "@dc", "value": dc_code},
                ],
                partition_key=dc_code,
            )
        return await self.query(
            "SELECT TOP @n * FROM c ORDER BY c.created_at DESC",
            parameters=[{"name": "@n", "value": limit}],
        )
