"""``routing://order-summary/{order_group}`` MCP resource."""
from __future__ import annotations

import json

from src.data.order_repo import OrderRepo
from src.server import mcp


@mcp.resource("routing://order-summary/{order_group}")
async def order_summary(order_group: str) -> str:
    """Return aggregate statistics for an order board (counts + totals)."""
    boards = await OrderRepo().list_by_group(order_group)
    n_boards = len(boards)
    total_weight = sum(b.totals.weight_lbs for b in boards) if n_boards else 0.0
    total_cubes = sum(b.totals.cubes for b in boards) if n_boards else 0.0
    total_pallets = sum(b.totals.pallets for b in boards) if n_boards else 0.0
    total_cases = sum(b.totals.cases for b in boards) if n_boards else 0
    destinations = sorted({b.destination for b in boards})
    districts = sorted({b.district for b in boards if b.district})
    return json.dumps(
        {
            "order_group": order_group,
            "board_count": n_boards,
            "destination_count": len(destinations),
            "district_count": len(districts),
            "destinations": destinations,
            "districts": districts,
            "totals": {
                "weight_lbs": total_weight,
                "cubes": total_cubes,
                "pallets": total_pallets,
                "cases": total_cases,
            },
        }
    )
