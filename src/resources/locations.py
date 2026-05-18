"""``routing://locations/{location_code}`` MCP resource — single location lookup."""
from __future__ import annotations

import json

from src.data.location_repo import LocationRepo
from src.server import mcp


@mcp.resource("routing://locations/{location_code}")
async def location_detail(location_code: str) -> str:
    """Return a single Location document by code (cross-partition lookup)."""
    loc = await LocationRepo().get_by_code(location_code)
    if loc is None:
        return json.dumps({})
    return loc.model_dump_json(by_alias=True, exclude_none=True)
