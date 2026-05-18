"""``plan_district_route`` MCP prompt."""
from __future__ import annotations

from src.server import mcp


@mcp.prompt(
    name="plan_district_route",
    description="Plan and optimize routes for a single district within an order group.",
)
async def plan_district_route(
    dc_code: str,
    order_group: str,
    district: str,
    trailer_type: str = "P53R",
) -> str:
    """Return a planning prompt scoped to one district."""
    return (
        f"You are a logistics planner for DC {dc_code}.\n"
        f"Plan delivery routes for district '{district}' from order group "
        f"'{order_group}' using trailer type {trailer_type}.\n\n"
        "Workflow:\n"
        f"  1. Call get_store_orders(order_group='{order_group}', district='{district}') "
        "to retrieve all destination boards.\n"
        f"  2. Call select_trailer with the aggregated demand to confirm "
        f"trailer_type='{trailer_type}' is suitable, or pick a better one.\n"
        "  3. Call optimize_route with the destinations, chosen trailer, and "
        "enforce_state_restrictions=True, enforce_curfews=True.\n"
        "  4. Call validate_route on the result to confirm compliance.\n"
        "  5. Summarize: total distance, vehicles used, utilization, and any violations.\n"
    )
