"""Generic async repository for Cosmos DB containers."""
from __future__ import annotations

import asyncio
from typing import Any, Generic, TypeVar

from azure.cosmos import exceptions as cosmos_exc
from pydantic import BaseModel

from src.data.cosmos_client import get_context

TModel = TypeVar("TModel", bound=BaseModel)


class BaseRepository(Generic[TModel]):
    """Async CRUD wrapper around a single Cosmos container.

    Subclasses set ``container_name``, ``model``, and ``partition_key_field``
    (the document attribute used to derive the partition key value).
    """

    container_name: str
    model: type[TModel]
    partition_key_field: str

    async def _container(self):  # type: ignore[no-untyped-def]
        ctx = await get_context()
        return ctx.container(self.container_name)

    def _pk(self, doc: dict[str, Any] | TModel) -> str:
        data = doc.model_dump(by_alias=True) if isinstance(doc, BaseModel) else doc
        return str(data[self.partition_key_field])

    async def upsert(self, item: TModel) -> TModel:
        container = await self._container()
        body = item.model_dump(by_alias=True, mode="json", exclude_none=True)
        await container.upsert_item(body=body)
        return item

    async def bulk_upsert(self, items: list[TModel], concurrency: int = 16) -> int:
        if not items:
            return 0
        container = await self._container()
        sem = asyncio.Semaphore(concurrency)

        async def _one(it: TModel) -> None:
            body = it.model_dump(by_alias=True, mode="json", exclude_none=True)
            async with sem:
                await container.upsert_item(body=body)

        await asyncio.gather(*(_one(it) for it in items))
        return len(items)

    async def get(self, item_id: str, partition_key: str) -> TModel | None:
        container = await self._container()
        try:
            doc = await container.read_item(item=item_id, partition_key=partition_key)
        except cosmos_exc.CosmosResourceNotFoundError:
            return None
        return self.model.model_validate(doc)

    async def query(
        self,
        query: str,
        parameters: list[dict[str, Any]] | None = None,
        partition_key: str | None = None,
        max_items: int | None = None,
    ) -> list[TModel]:
        container = await self._container()
        kwargs: dict[str, Any] = {"query": query, "parameters": parameters or []}
        if partition_key is not None:
            kwargs["partition_key"] = partition_key
        else:
            kwargs["enable_cross_partition_query"] = True

        results: list[TModel] = []
        async for doc in container.query_items(**kwargs):
            results.append(self.model.model_validate(doc))
            if max_items is not None and len(results) >= max_items:
                break
        return results

    async def count(self, partition_key: str | None = None) -> int:
        container = await self._container()
        kwargs: dict[str, Any] = {"query": "SELECT VALUE COUNT(1) FROM c"}
        if partition_key is not None:
            kwargs["partition_key"] = partition_key
        else:
            kwargs["enable_cross_partition_query"] = True
        async for v in container.query_items(**kwargs):
            return int(v)
        return 0
