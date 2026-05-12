"""``ingest_order_board`` MCP tool.

Reads the Routable Order Board sheet, groups by Destination, and upserts one
aggregated document per store into the ``order_boards`` container.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime
from typing import Any

from src.config import get_settings
from src.data.order_repo import OrderRepo
from src.logging_config import get_logger
from src.models.order import OrderBoard, OrderLine, OrderTotals
from src.models.requests import IngestOrderBoardRequest, IngestOrderBoardResponse
from src.server import mcp
from src.tools._excel import pick, read_sheet, to_float, to_int, to_str

log = get_logger(__name__)

_ILLEGAL_ID_CHARS = str.maketrans({"/": "-", "\\": "-", "?": "-", "#": "-"})


def _safe_id(value: str) -> str:
    return value.translate(_ILLEGAL_ID_CHARS).strip()


def _row_to_line(row: dict[str, Any]) -> tuple[str, OrderLine] | None:
    dest = to_str(pick(row, "destination", "dest", "store_code", "destination_code"))
    commodity = to_str(pick(row, "commodity", "commodity_code", "comm"))
    if not dest or not commodity:
        return None
    line = OrderLine(
        commodity=commodity,
        order_code=to_str(pick(row, "order_code", "order", "order_number")),
        weight_lbs=to_float(pick(row, "weight_lbs", "weight", "lbs")),
        cubes=to_float(pick(row, "cubes", "cube")),
        pallets=to_float(pick(row, "pallets", "pallet_count")),
        cases=to_int(pick(row, "cases", "case_count")),
    )
    return dest, line


def _aggregate(rows: list[dict[str, Any]], dc_code: str) -> tuple[str | None, list[OrderBoard]]:
    by_dest: dict[str, list[OrderLine]] = defaultdict(list)
    meta: dict[str, dict[str, Any]] = defaultdict(dict)
    order_group: str | None = None

    for raw in rows:
        og = to_str(pick(raw, "order_group", "group"))
        if og and order_group is None:
            order_group = og

        parsed = _row_to_line(raw)
        if parsed is None:
            continue
        dest, line = parsed
        by_dest[dest].append(line)
        m = meta[dest]
        m.setdefault("destination_desc", to_str(pick(raw, "dest_desc", "destination_desc", "destination_description", "store_name", "banner")))
        m.setdefault("district", to_str(pick(raw, "district", "district_handle")))
        m.setdefault("state", to_str(pick(raw, "state", "st")))
        m.setdefault("site", to_str(pick(raw, "site")))

    boards: list[OrderBoard] = []
    og_value = order_group or "UNKNOWN"
    now = datetime.now(UTC)
    for dest, lines in by_dest.items():
        totals = OrderTotals(
            weight_lbs=sum(li.weight_lbs for li in lines),
            cubes=sum(li.cubes for li in lines),
            pallets=sum(li.pallets for li in lines),
            cases=sum(li.cases for li in lines),
            order_line_count=len(lines),
            commodity_count=len({li.commodity for li in lines}),
        )
        m = meta[dest]
        boards.append(
            OrderBoard(
                id=_safe_id(f"{og_value}_{dest}"),
                order_group=og_value,
                dc_code=dc_code,
                site=m.get("site"),
                destination=dest,
                destination_desc=m.get("destination_desc"),
                district=m.get("district"),
                state=m.get("state"),
                orders=lines,
                totals=totals,
                ingested_at=now,
            )
        )
    return order_group, boards


@mcp.tool()
async def ingest_order_board(req: IngestOrderBoardRequest) -> IngestOrderBoardResponse:
    """Parse the Routable Order Board, aggregate by destination, and upsert into ``order_boards``."""
    log.info("ingest_order_board.start", file=req.file_path)

    df = read_sheet(req.file_path, req.sheet_name)
    rows = df.to_dict(orient="records")

    dc_code = get_settings().default_dc_code
    order_group, boards = _aggregate(rows, dc_code)

    n = await OrderRepo().bulk_upsert(boards)

    log.info("ingest_order_board.done", order_group=order_group, lines=len(rows), boards=n)
    return IngestOrderBoardResponse(
        order_group=order_group,
        order_lines_read=len(rows),
        boards_upserted=n,
    )
