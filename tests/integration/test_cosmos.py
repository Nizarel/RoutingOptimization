"""Cosmos round-trip integration test.

Skipped unless ``AZURE_COSMOS_ENDPOINT`` is set to a real account and the
running principal has the Cosmos DB Built-in Data Contributor role.

Run with: ``pytest -m integration``.
"""
from __future__ import annotations

import os
import uuid

import pytest

from src.data.cosmos_client import CosmosContext
from src.data.location_repo import LocationRepo
from src.models.location import Address, Curfew, GeoPoint, Location

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def _require_real_endpoint():
    endpoint = os.environ.get("AZURE_COSMOS_ENDPOINT", "")
    if "example.documents.azure.com" in endpoint or not endpoint:
        pytest.skip("AZURE_COSMOS_ENDPOINT not set to a real account")


async def test_location_upsert_and_read():
    code = f"itest-{uuid.uuid4().hex[:8]}"
    loc = Location(
        id=code,
        location_code=code,
        location_type="Mileage Store",
        description="Integration test",
        address=Address(state="UT"),
        coordinates=GeoPoint(coordinates=[-111.92, 40.85]),
        lat=40.85,
        lon=-111.92,
        curfew=Curfew(),
    )
    repo = LocationRepo()
    try:
        await repo.upsert(loc)
        fetched = await repo.get(code, partition_key="Mileage Store")
        assert fetched is not None
        assert fetched.location_code == code
    finally:
        async with CosmosContext() as ctx:
            await ctx.container("locations").delete_item(item=code, partition_key="Mileage Store")
