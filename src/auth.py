"""HTTP API key authentication middleware for the FastMCP transport.

Enforces an ``x-api-key`` header on all routes except the unauthenticated
liveness/readiness probes. No-op when no key is configured (local dev / tests).
"""
from __future__ import annotations

import hmac

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp

from src.logging_config import get_logger

log = get_logger(__name__)

# Paths that must remain anonymous for Container Apps probes and basic
# infra introspection.
_PUBLIC_PATHS: frozenset[str] = frozenset({"/healthz", "/readyz"})

_HEADER = "x-api-key"


class APIKeyMiddleware(BaseHTTPMiddleware):
    """Reject requests missing or mismatching the ``x-api-key`` header."""

    def __init__(self, app: ASGIApp, api_key: str | None) -> None:
        super().__init__(app)
        self._api_key = api_key

    async def dispatch(self, request: Request, call_next):  # type: ignore[override]
        if self._api_key is None or request.url.path in _PUBLIC_PATHS:
            return await call_next(request)

        provided = request.headers.get(_HEADER)
        if provided is None or not hmac.compare_digest(provided, self._api_key):
            log.warning(
                "auth.rejected",
                path=request.url.path,
                reason="missing_key" if provided is None else "bad_key",
            )
            return JSONResponse(
                {"error": "unauthorized"},
                status_code=401,
            )
        return await call_next(request)
