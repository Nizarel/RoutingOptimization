"""Smoke-test the deployed MCP server over Streamable HTTP.

Usage::

    # against locally running server
    python scripts/smoke_mcp.py http://localhost:8000/mcp

    # against the deployed Container App (must have public ingress enabled)
    python scripts/smoke_mcp.py https://<fqdn>/mcp

Calls a couple of read-only tools and prints the responses. Exits non-zero
on any failure.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys

from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport


async def _run(url: str) -> int:
    print(f"[smoke] connecting to {url}")
    api_key = os.environ.get("MCP_API_KEY")
    headers = {"x-api-key": api_key} if api_key else None
    if headers:
        print("[smoke] x-api-key header attached from MCP_API_KEY")
    transport = StreamableHttpTransport(url, headers=headers)
    async with Client(transport) as client:
        tools = await client.list_tools()
        names = sorted(t.name for t in tools)
        print(f"[smoke] tools registered: {names}")
        assert {"optimize_route", "ingest_locations", "ingest_order_board",
                "get_store_orders", "get_restrictions"}.issubset(set(names)), \
            f"missing tools: {names}"

        print("[smoke] calling get_restrictions(state=CA)")
        r1 = await client.call_tool("get_restrictions", {"req": {"state": "CA"}})
        payload = r1.data if hasattr(r1, "data") else r1
        print(json.dumps(payload, default=str, indent=2)[:500])

        print("[smoke] calling get_store_orders(order_group=FRE0224)")
        r2 = await client.call_tool("get_store_orders", {"req": {"order_group": "FRE0224"}})
        payload2 = r2.data if hasattr(r2, "data") else r2
        boards = payload2.get("boards", []) if isinstance(payload2, dict) else []
        print(f"[smoke] got {len(boards)} order boards")
        if boards:
            print(f"[smoke] first destination: {boards[0].get('destination')}")

    print("[smoke] OK")
    return 0


def main() -> None:
    if len(sys.argv) != 2:
        print("usage: python scripts/smoke_mcp.py <mcp-url>", file=sys.stderr)
        sys.exit(2)
    sys.exit(asyncio.run(_run(sys.argv[1])))


if __name__ == "__main__":
    main()
