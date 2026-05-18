"""``routing://vehicles`` MCP resource — vehicle definitions from the last optimization run."""
from __future__ import annotations

import json

from src.data.route_repo import RouteRepo
from src.server import mcp


@mcp.resource("routing://vehicles")
async def vehicles() -> str:
    """Return the vehicle list from the most recent route_history document."""
    items = await RouteRepo().latest(limit=1)
    if not items:
        return json.dumps({"vehicles": [], "history_id": None})
    history = items[0]
    return json.dumps(
        {
            "history_id": history.id,
            "dc_code": history.dc_code,
            "trailer_type": history.result.trailer_type,
            "vehicles": [
                v.model_dump(by_alias=True, exclude_none=True, mode="json")
                for v in history.result.routes
            ],
        }
    )
