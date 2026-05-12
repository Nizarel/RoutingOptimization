"""Repository for the ``state_restrictions`` container."""
from __future__ import annotations

from src.data.base_repo import BaseRepository
from src.models.restriction import StateRestriction


class RestrictionRepo(BaseRepository[StateRestriction]):
    container_name = "state_restrictions"
    model = StateRestriction
    partition_key_field = "state"

    async def list_by_state(self, state: str) -> list[StateRestriction]:
        return await self.query(
            "SELECT * FROM c WHERE c.state = @s",
            parameters=[{"name": "@s", "value": state}],
            partition_key=state,
        )

    async def list_filtered(
        self, state: str | None = None, trailer_class: str | None = None
    ) -> list[StateRestriction]:
        clauses: list[str] = []
        params: list[dict] = []
        if state:
            clauses.append("c.state = @s")
            params.append({"name": "@s", "value": state})
        if trailer_class:
            clauses.append("c.trailer_class = @tc")
            params.append({"name": "@tc", "value": trailer_class})
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        return await self.query(
            f"SELECT * FROM c{where}",
            parameters=params,
            partition_key=state,
        )
