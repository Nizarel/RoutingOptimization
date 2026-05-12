"""Order board schema (spec §5.4)."""
from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field


class OrderLine(BaseModel):
    model_config = ConfigDict(extra="ignore")

    commodity: str
    order_code: str | None = None
    weight_lbs: float = 0.0
    cubes: float = 0.0
    pallets: float = 0.0
    cases: int = 0


class OrderTotals(BaseModel):
    weight_lbs: float = 0.0
    cubes: float = 0.0
    pallets: float = 0.0
    cases: int = 0
    order_line_count: int = 0
    commodity_count: int = 0


class OrderBoard(BaseModel):
    """Aggregated orders for a single destination store within an order group."""

    model_config = ConfigDict(extra="ignore")

    id: str
    order_group: str
    dc_code: str
    site: str | None = None
    destination: str
    destination_desc: str | None = None
    district: str | None = None
    state: str | None = None
    orders: list[OrderLine] = Field(default_factory=list)
    totals: OrderTotals
    ingested_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    # Cosmos TTL field (seconds). 30 days for order_boards per spec §5.4.
    ttl_seconds: int | None = Field(default=2_592_000, alias="_ttl")
