"""Ad-hoc live test of the deployed MCP server.

Usage:
    python scripts/_live_test.py [mcp-url]
"""
from __future__ import annotations

import asyncio
import json
import sys
import time

from fastmcp import Client

FQDN = "https://ca-rt-vqcz36euruiko.proudglacier-ba160324.eastus2.azurecontainerapps.io"
URL  = sys.argv[1] if len(sys.argv) > 1 else f"{FQDN}/mcp"

EXPECTED_TOOLS = {
    "directions", "geocode_address", "get_restrictions", "get_store_orders",
    "ingest_locations", "ingest_order_board", "isochrone", "map_render",
    "matrix_travel_times", "optimize_route", "select_trailer", "validate_route",
}


def p(tag: str, obj: object) -> None:
    s = json.dumps(obj, default=str, indent=2)
    print(f"\n[{tag}]\n{s[:800]}")


async def main() -> int:
    failures: list[str] = []

    async with Client(URL) as c:

        # ── 1. Tool inventory ──────────────────────────────────────────────
        tools = sorted(t.name for t in await c.list_tools())
        print(f"\n[tools] registered ({len(tools)}): {tools}")
        missing = EXPECTED_TOOLS - set(tools)
        if missing:
            failures.append(f"missing tools: {sorted(missing)}")
            print(f"[tools] FAIL - missing: {sorted(missing)}")
        else:
            print(f"[tools] OK - all {len(EXPECTED_TOOLS)} tools present")

        # ── 2. geocode_address ─────────────────────────────────────────────
        try:
            r = await c.call_tool("geocode_address",
                                  {"req": {"query": "1500 S 700 W, Salt Lake City, UT"}})
            d = r.data if hasattr(r, "data") else r
            p("geocode_address", d)
            print("[geocode] OK")
        except Exception as exc:
            failures.append(f"geocode_address: {exc}")
            print(f"[geocode] FAIL: {exc}")

        # ── 3. get_restrictions (UT) ───────────────────────────────────────
        try:
            r = await c.call_tool("get_restrictions", {"req": {"state": "UT"}})
            d = r.data if hasattr(r, "data") else r
            p("get_restrictions(UT)", d)
            print("[restrictions] OK")
        except Exception as exc:
            failures.append(f"get_restrictions: {exc}")
            print(f"[restrictions] FAIL: {exc}")

        # ── 4. matrix_travel_times – cache MISS then cache HIT ─────────────
        # Real SLC-group codes from the Locations Excel (52-DC = SLC DC, 101/1010 = stores).
        # Requires locations to have been seeded via ingest_locations.
        matrix_req = {
            "req": {
                "location_codes": ["52-DC", "101", "1010"],
                "profile": "truck",
            }
        }
        for attempt in (1, 2):
            label = "MISS (cold)" if attempt == 1 else "HIT  (warm)"
            try:
                t0 = time.perf_counter()
                r = await c.call_tool("matrix_travel_times", matrix_req)
                elapsed = (time.perf_counter() - t0) * 1000
                d = r.data if hasattr(r, "data") else r
                from_cache = d.get("from_cache") if isinstance(d, dict) else "?"
                rows       = len(d.get("matrix", [])) if isinstance(d, dict) else "?"
                print(f"\n[matrix call-{attempt}] {label}  "
                      f"from_cache={from_cache}  rows={rows}  {elapsed:.0f}ms")
                p(f"matrix call-{attempt}", d)
                if attempt == 2 and from_cache is True:
                    print("[matrix] cache HIT confirmed")
                elif attempt == 2:
                    print("[matrix] NOTE: from_cache not True on second call "
                          "(replica cold-start or location codes not seeded)")
            except Exception as exc:
                failures.append(f"matrix_travel_times call {attempt}: {exc}")
                print(f"[matrix call-{attempt}] FAIL: {exc}")

    print()
    if failures:
        print("=== LIVE SMOKE: FAILED ===")
        for f in failures:
            print(f"  - {f}")
        return 1

    print("=== LIVE SMOKE: ALL CHECKS PASSED ===")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
