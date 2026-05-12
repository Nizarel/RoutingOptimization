"""Seed Cosmos DB containers from customer Excel files."""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

# Make `src` importable when running this script directly.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.logging_config import configure_logging, get_logger  # noqa: E402
from src.models.requests import IngestLocationsRequest, IngestOrderBoardRequest  # noqa: E402
from src.tools.ingest_locations import ingest_locations  # noqa: E402
from src.tools.ingest_orders import ingest_order_board  # noqa: E402


async def _run(locations_path: str | None, orders_path: str | None) -> None:
    log = get_logger("seed")

    if locations_path:
        log.info("seed.locations.start", path=locations_path)
        resp = await ingest_locations(IngestLocationsRequest(file_path=locations_path))
        log.info("seed.locations.done", **resp.model_dump())

    if orders_path:
        log.info("seed.orders.start", path=orders_path)
        resp_o = await ingest_order_board(IngestOrderBoardRequest(file_path=orders_path))
        log.info("seed.orders.done", **resp_o.model_dump())


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed Cosmos DB from customer Excel files.")
    parser.add_argument("--locations", help="Path to SLC Restrictions & Locations workbook.")
    parser.add_argument("--orders", help="Path to Routable Order Board workbook.")
    args = parser.parse_args()

    if not args.locations and not args.orders:
        parser.error("Provide at least --locations or --orders.")

    configure_logging("INFO")
    asyncio.run(_run(args.locations, args.orders))


if __name__ == "__main__":
    main()
