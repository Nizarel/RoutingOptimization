"""Unit tests for liveness/readiness endpoints."""
from __future__ import annotations

import pytest
from starlette.testclient import TestClient

# Importing src.server registers all tools/resources/prompts/routes via _register().
from src import server  # noqa: F401  (import side effect: route registration)


@pytest.fixture
def client():
    app = server.mcp.http_app()
    return TestClient(app)


def test_healthz_returns_ok(client):
    resp = client.get("/healthz")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert "ts" in body


def test_readyz_returns_503_when_cosmos_unreachable(client, monkeypatch):
    """The conftest endpoint is dummy, so Cosmos calls must fail -> 503."""
    # Monkey-patch CosmosContext.container to raise (defensive — keeps the test
    # deterministic even if a future change makes the dummy endpoint succeed).
    from src.data import cosmos_client

    async def boom():
        raise RuntimeError("cosmos unreachable (test)")

    monkeypatch.setattr(cosmos_client, "get_context", boom)
    resp = client.get("/readyz")
    assert resp.status_code == 503
    assert resp.json()["status"] == "not_ready"
