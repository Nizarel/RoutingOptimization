"""Liveness and readiness HTTP endpoints for Container Apps probes.

Both routes are mounted on the FastMCP HTTP transport via ``@mcp.custom_route``
and are intentionally lightweight:

* ``/healthz`` — process is up. Returns 200 immediately.
* ``/readyz``  — process can serve traffic. Pings Cosmos with a cheap
  ``SELECT VALUE COUNT(1) FROM c OFFSET 0 LIMIT 1`` against ``trailer_types``.
  Returns 503 if the dependency check fails.
"""
from __future__ import annotations

from datetime import UTC, datetime

from starlette.requests import Request
from starlette.responses import JSONResponse

from src.data.cosmos_client import get_context
from src.logging_config import get_logger
from src.server import mcp

log = get_logger(__name__)


@mcp.custom_route("/healthz", methods=["GET"], include_in_schema=False)
async def healthz(request: Request) -> JSONResponse:  # noqa: ARG001
    """Liveness probe — returns 200 as long as the process is running."""
    return JSONResponse(
        {"status": "ok", "ts": datetime.now(UTC).isoformat()}
    )


@mcp.custom_route("/readyz", methods=["GET"], include_in_schema=False)
async def readyz(request: Request) -> JSONResponse:  # noqa: ARG001
    """Readiness probe — verifies Cosmos is reachable."""
    try:
        ctx = await get_context()
        container = ctx.container("trailer_types")
        # Cheap query: COUNT against an empty result set still validates auth + routing.
        iterator = container.query_items(
            query="SELECT VALUE COUNT(1) FROM c OFFSET 0 LIMIT 1",
        )
        async for _ in iterator:
            break
        return JSONResponse({"status": "ready"})
    except Exception as exc:  # noqa: BLE001
        log.warning("readyz.cosmos_failed", error=str(exc))
        return JSONResponse(
            {"status": "not_ready", "reason": "cosmos_unreachable"},
            status_code=503,
        )
