"""``explain_solution`` MCP prompt."""
from __future__ import annotations

from src.server import mcp


@mcp.prompt(
    name="explain_solution",
    description="Explain a routing optimization result in plain English for a dispatcher.",
)
async def explain_solution(history_id: str | None = None) -> str:
    """Return a prompt that walks through and explains a route_history document."""
    target = (
        f"the route_history document with id '{history_id}'"
        if history_id
        else "the most recent solution (resource routing://last-solution)"
    )
    return (
        f"Read {target} and produce a dispatcher-friendly explanation.\n\n"
        "Cover:\n"
        "  1. How many vehicles were used and why (cube vs. weight limited).\n"
        "  2. The stop sequence for each vehicle and approximate drive time.\n"
        "  3. Which states are traversed and any restrictions that influenced the plan.\n"
        "  4. Curfew or time-window constraints that mattered.\n"
        "  5. Risk callouts: tight utilization, multi-state combos, long single routes.\n\n"
        "Keep the tone practical. Cite numbers from the result; do not invent data."
    )
