"""``compare_scenarios`` MCP prompt."""
from __future__ import annotations

from src.server import mcp


@mcp.prompt(
    name="compare_scenarios",
    description="Compare two routing scenarios side-by-side (different trailers, objectives, or constraints).",
)
async def compare_scenarios(
    dc_code: str,
    order_group: str,
    scenario_a_label: str = "Baseline",
    scenario_b_label: str = "Alternative",
) -> str:
    """Return a prompt that runs two optimize_route calls and compares them."""
    return (
        f"Compare two routing scenarios for DC {dc_code}, order group "
        f"'{order_group}'.\n\n"
        f"Scenario A — {scenario_a_label}: run optimize_route with its specific "
        "trailer_type and objective.\n"
        f"Scenario B — {scenario_b_label}: run optimize_route with the alternate "
        "trailer_type and/or objective.\n\n"
        "For each scenario, capture:\n"
        "  - total distance (m)\n"
        "  - vehicles used\n"
        "  - average weight & cube utilization\n"
        "  - compliance status (state restrictions, curfews)\n\n"
        "Output a markdown comparison table and recommend the winner with "
        "reasoning grounded in the numbers."
    )
