"""``directions`` MCP tool — Azure Maps Directions v1."""
from __future__ import annotations

from src.models.requests import (
    DirectionsLeg,
    DirectionsRequest,
    DirectionsResponse,
    GeoPointLL,
)
from src.server import mcp
from src.services import azure_maps


@mcp.tool()
async def directions(req: DirectionsRequest) -> DirectionsResponse:
    """Compute a turn-by-turn route between origin and destination (with optional waypoints)."""
    result = await azure_maps.directions(
        (req.origin.lat, req.origin.lon),
        (req.destination.lat, req.destination.lon),
        waypoints=[(w.lat, w.lon) for w in req.waypoints],
        profile=req.profile,
        avoid=req.avoid,
    )
    return DirectionsResponse(
        distance_m=result.distance_m,
        duration_sec=result.duration_sec,
        legs=[
            DirectionsLeg(
                start=GeoPointLL(lat=leg.start_lat, lon=leg.start_lon),
                end=GeoPointLL(lat=leg.end_lat, lon=leg.end_lon),
                distance_m=leg.distance_m,
                duration_sec=leg.duration_sec,
            )
            for leg in result.legs
        ],
        from_stub=result.from_stub,
    )
