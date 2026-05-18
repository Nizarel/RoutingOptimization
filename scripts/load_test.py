"""Locust load test for the deployed MCP server.

Hits the Streamable-HTTP MCP endpoint with read-heavy traffic
(``get_restrictions``, ``get_store_orders``) plus occasional ``matrix``
calls. ``optimize_route`` is intentionally low-weight because it is the
heaviest CPU path.

Usage::

    # against deployed Container App
    locust -f scripts/load_test.py \\
        --host https://<fqdn> \\
        -u 20 -r 2 -t 2m --headless --csv loadtest

    # interactive web UI
    locust -f scripts/load_test.py --host https://<fqdn>

The ``--host`` value should be the Container App FQDN root (no path); the
tasks append ``/mcp`` themselves.

Required env vars: none. Pre-seeded Cosmos data is assumed (district FRE0224
order_group, CA state restrictions). Override via env::

    LOAD_ORDER_GROUP=FRE0224
    LOAD_STATE=CA
"""
from __future__ import annotations

import json
import os
import uuid
from typing import Any

from locust import HttpUser, between, task


_ORDER_GROUP = os.environ.get("LOAD_ORDER_GROUP", "FRE0224")
_STATE = os.environ.get("LOAD_STATE", "CA")


def _rpc(method: str, params: dict[str, Any], req_id: str | None = None) -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": req_id or str(uuid.uuid4()),
        "method": method,
        "params": params,
    }


def _call_tool(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    return _rpc("tools/call", {"name": name, "arguments": arguments})


class McpUser(HttpUser):
    """Streamable-HTTP MCP client. We do not maintain an SSE session — each
    request is an independent JSON-RPC POST, which is the worst case for the
    server (no warm connection). That makes the throughput number a
    conservative lower bound.
    """

    wait_time = between(0.5, 2.0)

    @task(5)
    def get_restrictions(self) -> None:
        body = _call_tool("get_restrictions", {"req": {"state": _STATE}})
        self._post("get_restrictions", body)

    @task(5)
    def get_store_orders(self) -> None:
        body = _call_tool("get_store_orders", {"req": {"order_group": _ORDER_GROUP}})
        self._post("get_store_orders", body)

    @task(2)
    def healthz(self) -> None:
        with self.client.get("/healthz", name="GET /healthz", catch_response=True) as r:
            if r.status_code == 200:
                r.success()
            else:
                r.failure(f"status={r.status_code}")

    @task(1)
    def matrix_small(self) -> None:
        body = _call_tool(
            "matrix",
            {
                "req": {
                    "points": [
                        {"lat": 40.76, "lon": -111.89},
                        {"lat": 40.77, "lon": -111.88},
                        {"lat": 40.78, "lon": -111.87},
                    ],
                    "profile": "truck",
                }
            },
        )
        self._post("matrix", body)

    def _post(self, label: str, body: dict[str, Any]) -> None:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        with self.client.post(
            "/mcp/",
            data=json.dumps(body),
            headers=headers,
            name=f"POST /mcp {label}",
            catch_response=True,
        ) as r:
            if r.status_code != 200:
                r.failure(f"http {r.status_code}: {r.text[:200]}")
                return
            # FastMCP returns either JSON or SSE; treat 200 as success.
            r.success()
