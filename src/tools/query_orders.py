"""``get_store_orders`` MCP tool — read-only Cosmos query."""
from __future__ import annotations

from src.data.order_repo import OrderRepo
from src.models.requests import GetStoreOrdersRequest, GetStoreOrdersResponse
from src.server import mcp


@mcp.tool()
async def get_store_orders(req: GetStoreOrdersRequest) -> GetStoreOrdersResponse:
    """Return order boards for a given order_group, optionally filtered by destination or district."""
    repo = OrderRepo()
    if req.destination:
        boards = await repo.list_by_destination(req.order_group, req.destination)
    elif req.district:
        boards = await repo.list_by_district(req.order_group, req.district)
    else:
        boards = await repo.list_by_group(req.order_group)
    return GetStoreOrdersResponse(boards=boards)
