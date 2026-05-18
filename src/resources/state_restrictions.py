"""``routing://state-restrictions/{state}`` MCP resource."""
from __future__ import annotations

import json

from src.data.restriction_repo import RestrictionRepo
from src.server import mcp


@mcp.resource("routing://state-restrictions/{state}")
async def state_restrictions(state: str) -> str:
    """Return all StateRestriction documents for ``state`` as a JSON array."""
    items = await RestrictionRepo().list_by_state(state.upper())
    return json.dumps(
        [item.model_dump(by_alias=True, exclude_none=True, mode="json") for item in items]
    )
