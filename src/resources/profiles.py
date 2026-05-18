"""``routing://profiles`` MCP resource — available routing profiles & objectives."""
from __future__ import annotations

import json

from src.server import mcp

_PROFILES = {
    "profiles": [
        {
            "id": "truck",
            "label": "Truck",
            "description": "Commercial truck profile (default for tractor + trailer routing).",
        },
        {
            "id": "car",
            "label": "Car",
            "description": "Passenger-vehicle profile (no truck restrictions).",
        },
    ],
    "objectives": [
        {
            "id": "min_total_distance",
            "label": "Minimize total distance",
            "description": "Total fleet distance traveled across all vehicles.",
        },
        {
            "id": "min_longest_route",
            "label": "Minimize the longest route (makespan)",
            "description": "Minimizes the duration of the worst-case vehicle route.",
        },
    ],
}


@mcp.resource("routing://profiles")
async def profiles() -> str:
    """Return the supported routing profiles and optimization objectives."""
    return json.dumps(_PROFILES)
