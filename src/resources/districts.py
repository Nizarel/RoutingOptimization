"""``routing://districts`` MCP resource — all district groupings."""
from __future__ import annotations

import json

from src.data.district_repo import DistrictRepo
from src.server import mcp


@mcp.resource("routing://districts")
async def districts() -> str:
    """Return every district document across all DCs as a JSON array."""
    items = await DistrictRepo().query("SELECT * FROM c")
    return json.dumps(
        [item.model_dump(by_alias=True, exclude_none=True, mode="json") for item in items]
    )
