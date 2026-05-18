"""``select_best_trailer`` MCP prompt."""
from __future__ import annotations

from src.server import mcp


@mcp.prompt(
    name="select_best_trailer",
    description="Pick the best trailer type for an order group's aggregated demand.",
)
async def select_best_trailer(
    order_group: str,
    candidate_trailers: str = "P53R,P57R,P53V",
) -> str:
    """Return a prompt that compares candidate trailers via select_trailer."""
    return (
        f"Pick the most efficient trailer for order group '{order_group}'.\n\n"
        "Workflow:\n"
        f"  1. Call get_store_orders(order_group='{order_group}') and aggregate "
        "totals (weight_lbs, cubes, pallets).\n"
        f"  2. For each candidate in [{candidate_trailers}], call select_trailer "
        "with the aggregated demand.\n"
        "  3. Compare on:\n"
        "     - feasibility (weight & cube fit)\n"
        "     - utilization (higher = better, but >95% is risky)\n"
        "     - vehicles needed (fewer = better)\n"
        "  4. Recommend ONE trailer and justify the trade-off."
    )
