"""``geocode_address`` MCP tool — Azure Maps Search Address v1."""
from __future__ import annotations

from src.config import get_settings
from src.models.requests import (
    GeocodeCandidate,
    GeocodeRequest,
    GeocodeResponse,
)
from src.server import mcp
from src.services import azure_maps


@mcp.tool()
async def geocode_address(req: GeocodeRequest) -> GeocodeResponse:
    """Resolve a free-form address to lat/lon candidates."""
    hits = await azure_maps.geocode(
        req.query, country=req.country_code, top=req.top
    )
    from_stub = not bool(get_settings().azure_maps_client_id)
    return GeocodeResponse(
        query=req.query,
        candidates=[
            GeocodeCandidate(
                formatted_address=h.formatted_address,
                lat=h.lat,
                lon=h.lon,
                confidence=h.confidence,
                match_type=str(h.match_type) if h.match_type is not None else None,
            )
            for h in hits
        ],
        from_stub=from_stub,
    )
