"""``isochrone`` MCP tool — Azure Maps Route Range v1."""
from __future__ import annotations

from src.models.requests import IsochroneRequest, IsochroneResponse
from src.server import mcp
from src.services import azure_maps


@mcp.tool()
async def isochrone(req: IsochroneRequest) -> IsochroneResponse:
    """Return a reachable polygon from ``origin`` within ``max_minutes``."""
    result = await azure_maps.isochrone(
        (req.origin.lat, req.origin.lon),
        req.max_minutes,
        profile=req.profile,
    )
    return IsochroneResponse(
        origin=req.origin,
        max_minutes=req.max_minutes,
        polygon=result.polygon,
        reachable_area_km2=result.reachable_area_km2,
        from_stub=result.from_stub,
    )
