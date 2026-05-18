"""``map_render`` MCP tool — Azure Maps static map PNG."""
from __future__ import annotations

from src.models.requests import MapRenderRequest, MapRenderResponse
from src.server import mcp
from src.services import azure_maps


@mcp.tool()
async def map_render(req: MapRenderRequest) -> MapRenderResponse:
    """Render a static PNG map with optional pins and a path overlay."""
    center = (req.center.lat, req.center.lon) if req.center is not None else None
    result = await azure_maps.render_map(
        center=center,
        zoom=req.zoom,
        width=req.width,
        height=req.height,
        pins=[(p.lat, p.lon, p.label) for p in req.pins],
        path_points=[(p.lat, p.lon) for p in req.path_points],
    )
    return MapRenderResponse(
        image_base64=result.image_base64,
        content_type="image/png",
        width=result.width,
        height=result.height,
        from_stub=result.from_stub,
    )
