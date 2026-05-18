"""``check_compliance`` MCP prompt."""
from __future__ import annotations

from src.server import mcp


@mcp.prompt(
    name="check_compliance",
    description="Validate a routing solution against state restrictions and curfews.",
)
async def check_compliance(history_id: str | None = None) -> str:
    """Return a prompt that validates a routing solution end-to-end."""
    target = (
        f"history_id='{history_id}'"
        if history_id
        else "the most recent solution (resource routing://last-solution)"
    )
    return (
        f"Verify the routing solution at {target} is fully compliant.\n\n"
        "Steps:\n"
        "  1. Load the solution.\n"
        "  2. For every state in routes[*].states_traversed, call get_restrictions "
        "and confirm the trailer class is allowed.\n"
        "  3. Call validate_route to re-run the compliance engine.\n"
        "  4. Report each violation with: vehicle id, stop, state(s), rule violated, "
        "and severity.\n"
        "  5. If clean, state 'COMPLIANT' explicitly; otherwise list required fixes."
    )
