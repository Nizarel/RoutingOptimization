"""Repository for the ``order_boards`` container."""
from __future__ import annotations

from src.data.base_repo import BaseRepository
from src.models.order import OrderBoard


class OrderRepo(BaseRepository[OrderBoard]):
    container_name = "order_boards"
    model = OrderBoard
    partition_key_field = "order_group"

    async def list_by_group(self, order_group: str) -> list[OrderBoard]:
        return await self.query(
            "SELECT * FROM c WHERE c.order_group = @og",
            parameters=[{"name": "@og", "value": order_group}],
            partition_key=order_group,
        )

    async def list_by_destination(
        self, order_group: str, destination: str
    ) -> list[OrderBoard]:
        return await self.query(
            "SELECT * FROM c WHERE c.order_group = @og AND c.destination = @d",
            parameters=[
                {"name": "@og", "value": order_group},
                {"name": "@d", "value": destination},
            ],
            partition_key=order_group,
        )

    async def list_by_district(
        self, order_group: str, district: str
    ) -> list[OrderBoard]:
        return await self.query(
            "SELECT * FROM c WHERE c.order_group = @og AND c.district = @dist",
            parameters=[
                {"name": "@og", "value": order_group},
                {"name": "@dist", "value": district},
            ],
            partition_key=order_group,
        )
