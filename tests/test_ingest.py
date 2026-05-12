"""Unit tests for ingest aggregation logic (no Cosmos required)."""
from __future__ import annotations

from src.tools.ingest_orders import _aggregate


def test_aggregate_groups_by_destination():
    rows = [
        {"order_group": "FRE0224", "destination": "183", "commodity": "PRO",
         "weight_lbs": 19414, "cubes": 1014, "pallets": 14.5, "cases": 1097, "state": "WY"},
        {"order_group": "FRE0224", "destination": "183", "commodity": "MEA",
         "weight_lbs": 7548, "cubes": 298, "pallets": 4.3, "cases": 430, "state": "WY"},
        {"order_group": "FRE0224", "destination": "183", "commodity": "PER",
         "weight_lbs": 7363, "cubes": 231, "pallets": 3.3, "cases": 449, "state": "WY"},
        {"order_group": "FRE0224", "destination": "1010", "commodity": "PRO",
         "weight_lbs": 5000, "cubes": 200, "pallets": 4, "cases": 100, "state": "MT"},
    ]
    og, boards = _aggregate(rows, dc_code="52-DC")
    assert og == "FRE0224"
    by_dest = {b.destination: b for b in boards}
    assert set(by_dest) == {"183", "1010"}

    b183 = by_dest["183"]
    assert b183.totals.order_line_count == 3
    assert b183.totals.commodity_count == 3
    assert round(b183.totals.weight_lbs, 0) == 19414 + 7548 + 7363
    assert b183.state == "WY"
    assert b183.id == "FRE0224_183"

    b1010 = by_dest["1010"]
    assert b1010.totals.order_line_count == 1
    assert b1010.state == "MT"


def test_aggregate_skips_invalid_rows():
    rows = [
        {"destination": None, "commodity": "PRO", "weight_lbs": 100},
        {"destination": "X", "commodity": None, "weight_lbs": 100},
        {"destination": "X", "commodity": "PRO", "weight_lbs": 100},
    ]
    _, boards = _aggregate(rows, dc_code="52-DC")
    assert len(boards) == 1
    assert boards[0].destination == "X"
    assert boards[0].totals.order_line_count == 1
