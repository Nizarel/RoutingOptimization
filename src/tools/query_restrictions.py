"""``get_restrictions`` MCP tool — read-only Cosmos query."""
from __future__ import annotations

from src.data.restriction_repo import RestrictionRepo
from src.models.requests import GetRestrictionsRequest, GetRestrictionsResponse
from src.server import mcp


@mcp.tool()
async def get_restrictions(req: GetRestrictionsRequest) -> GetRestrictionsResponse:
    """Return state trailer restrictions, optionally filtered by state and trailer class."""
    repo = RestrictionRepo()
    if req.state:
        restrictions = await repo.list_filtered(state=req.state, trailer_class=req.trailer_class)
    else:
        restrictions = await repo.query("SELECT * FROM c")
        if req.trailer_class:
            restrictions = [r for r in restrictions if r.trailer_class == req.trailer_class]
    return GetRestrictionsResponse(restrictions=restrictions)
