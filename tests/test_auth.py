"""Unit tests for ``APIKeyMiddleware``."""
from __future__ import annotations

from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from src.auth import APIKeyMiddleware


async def _ok(request):  # noqa: ANN001
    return JSONResponse({"ok": True})


def _client(api_key: str | None) -> TestClient:
    app = Starlette(
        routes=[
            Route("/mcp", _ok, methods=["GET"]),
            Route("/healthz", _ok, methods=["GET"]),
            Route("/readyz", _ok, methods=["GET"]),
        ],
        middleware=[Middleware(APIKeyMiddleware, api_key=api_key)],
    )
    return TestClient(app)


def test_no_key_configured_is_noop() -> None:
    client = _client(None)
    assert client.get("/mcp").status_code == 200


def test_missing_header_rejected() -> None:
    client = _client("secret")
    res = client.get("/mcp")
    assert res.status_code == 401
    assert res.json() == {"error": "unauthorized"}


def test_wrong_key_rejected() -> None:
    client = _client("secret")
    res = client.get("/mcp", headers={"x-api-key": "nope"})
    assert res.status_code == 401


def test_correct_key_allowed() -> None:
    client = _client("secret")
    res = client.get("/mcp", headers={"x-api-key": "secret"})
    assert res.status_code == 200


def test_probes_always_anonymous() -> None:
    client = _client("secret")
    assert client.get("/healthz").status_code == 200
    assert client.get("/readyz").status_code == 200
