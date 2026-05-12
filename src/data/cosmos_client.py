"""Cosmos DB client factory using DefaultAzureCredential.

A single ``CosmosClient`` is reused across the process; container handles are
lazily resolved on first access. Auth is RBAC-only (no master keys).
"""
from __future__ import annotations

import asyncio
from functools import lru_cache

from azure.cosmos.aio import ContainerProxy, CosmosClient, DatabaseProxy
from azure.identity.aio import DefaultAzureCredential

from src.config import get_settings


# Container catalog — keep in sync with infra/modules/cosmos.bicep.
CONTAINERS: dict[str, str] = {
    "locations": "/location_type",
    "trailer_types": "/trailer_class",
    "state_restrictions": "/state",
    "order_boards": "/order_group",
    "route_history": "/dc_code",
    "matrix_cache": "/profile",
    "districts": "/dc_code",
}


class CosmosContext:
    """Process-wide async Cosmos DB context.

    Use as ``async with CosmosContext() as ctx: ctx.container('locations')``.
    For long-lived processes (FastMCP server), call :func:`get_context` to
    obtain a singleton initialized once at startup.
    """

    def __init__(self) -> None:
        settings = get_settings()
        self._endpoint = settings.azure_cosmos_endpoint
        self._database_name = settings.azure_cosmos_database
        self._credential: DefaultAzureCredential | None = None
        self._client: CosmosClient | None = None
        self._database: DatabaseProxy | None = None
        self._containers: dict[str, ContainerProxy] = {}

    async def __aenter__(self) -> "CosmosContext":
        await self.connect()
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self.close()

    async def connect(self) -> None:
        if self._client is not None:
            return
        self._credential = DefaultAzureCredential()
        self._client = CosmosClient(self._endpoint, credential=self._credential)
        self._database = self._client.get_database_client(self._database_name)

    def container(self, name: str) -> ContainerProxy:
        if self._database is None:
            raise RuntimeError("CosmosContext not connected; call connect() or use async with.")
        if name not in CONTAINERS:
            raise KeyError(f"Unknown container '{name}'. Known: {sorted(CONTAINERS)}")
        if name not in self._containers:
            self._containers[name] = self._database.get_container_client(name)
        return self._containers[name]

    async def close(self) -> None:
        if self._client is not None:
            await self._client.close()
            self._client = None
        if self._credential is not None:
            await self._credential.close()
            self._credential = None
        self._database = None
        self._containers.clear()


_context_lock = asyncio.Lock()
_context_singleton: CosmosContext | None = None


@lru_cache(maxsize=1)
def _get_lock() -> asyncio.Lock:
    return asyncio.Lock()


async def get_context() -> CosmosContext:
    """Return a process-wide singleton CosmosContext, connecting on first use."""
    global _context_singleton
    async with _get_lock():
        if _context_singleton is None:
            ctx = CosmosContext()
            await ctx.connect()
            _context_singleton = ctx
    return _context_singleton
