"""``routing://last-solution`` MCP resource."""
from __future__ import annotations

import json

from src.data.route_repo import RouteRepo
from src.server import mcp


@mcp.resource("routing://last-solution")
async def last_solution() -> str:
    """Return the most recent route_history document as JSON, or an empty object."""
    items = await RouteRepo().latest(limit=1)
    if not items:
        return json.dumps({})
    return items[0].model_dump_json(by_alias=True, exclude_none=True)
