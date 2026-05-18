"""FastMCP server entry point.

Registers all MCP tools and resources, then runs over the configured transport
(``http`` by default; ``stdio`` for local IDE integrations).
"""
from __future__ import annotations

from fastmcp import FastMCP

from src.config import get_settings
from src.logging_config import configure_logging, get_logger
from src.telemetry import configure_telemetry

settings = get_settings()
configure_logging(settings.mcp_log_level)
# Initialize Azure Monitor / OpenTelemetry if APPLICATIONINSIGHTS_CONNECTION_STRING
# is set. Safe no-op otherwise (unit tests, local stdio).
configure_telemetry()
log = get_logger(__name__)

mcp: FastMCP = FastMCP(
    name="routing-optimization-mcp",
    instructions=(
        "Routing Optimization MCP Server for Albertsons SLC DC. "
        "Provides tools to ingest order boards and locations, query store orders "
        "and state restrictions, and optimize delivery routes (CVRPTW)."
    ),
)


def _register() -> None:
    """Register all tools and resources. Imports are deferred so that
    ``src.server`` can be imported without triggering Cosmos client init."""
    from src.tools import (  # noqa: F401  (registration via import side-effects)
        directions,
        geocode,
        ingest_locations,
        ingest_orders,
        isochrone,
        map_render,
        matrix,
        optimize,
        query_orders,
        query_restrictions,
        select_trailer,
        validate_route,
    )
    from src.resources import (  # noqa: F401
        districts,
        last_solution,
        locations,
        order_summary,
        profiles,
        state_restrictions,
        trailer_types,
        vehicles,
    )
    from src.prompts import (  # noqa: F401
        check_compliance,
        compare_scenarios,
        explain_solution,
        plan_district_route,
        select_best_trailer,
    )

    # Health/readiness HTTP routes (mounted on the FastMCP HTTP transport).
    from src import health  # noqa: F401

    log.info("mcp.tools_registered", count=12, resources=8, prompts=5)


_register()


def main() -> None:
    """Console-script entry point."""
    if settings.mcp_transport == "stdio":
        log.info("mcp.starting", transport="stdio")
        mcp.run()
    else:
        log.info(
            "mcp.starting",
            transport="http",
            host=settings.mcp_http_host,
            port=settings.mcp_http_port,
        )
        mcp.run(
            transport="http",
            host=settings.mcp_http_host,
            port=settings.mcp_http_port,
        )


if __name__ == "__main__":
    main()
