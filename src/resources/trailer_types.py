"""``routing://trailer-types`` MCP resource — all trailer configurations."""
from __future__ import annotations

import json

from src.data.trailer_repo import TrailerRepo
from src.server import mcp


@mcp.resource("routing://trailer-types")
async def trailer_types() -> str:
    """Return every TrailerType document as a JSON array."""
    items = await TrailerRepo().list_all()
    return json.dumps(
        [item.model_dump(by_alias=True, exclude_none=True, mode="json") for item in items]
    )
