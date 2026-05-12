# Copilot Instructions — Routing Optimization MCP Server

This repo is a **FastMCP server** that exposes Albertsons SLC DC routing
optimization (CVRPTW) as MCP tools. The authoritative spec is
[`Routing_Optimization_MCP_Server_Spec_Architecture.md`](../Routing_Optimization_MCP_Server_Spec_Architecture.md).
The current code is the walking skeleton from spec §14, Sprints 1–2.

## Stack & key versions

- Python **3.12**
- `fastmcp` 3.x — primary framework. Tools registered with `@mcp.tool()`,
  resources with `@mcp.resource(uri)`. The `mcp` instance lives in
  [`src/server.py`](../src/server.py); `_register()` imports tool modules
  to trigger decorator side effects.
- `pydantic` v2 + `pydantic-settings` v2 — all I/O models in
  [`src/models/`](../src/models/), env config in
  [`src/config.py`](../src/config.py).
- `azure-cosmos` (async via `azure.cosmos.aio`) + `azure-identity`
  `DefaultAzureCredential` — **no master keys**, RBAC only.
- `ortools` — solver in [`src/services/solver.py`](../src/services/solver.py).
- `pandas` + `openpyxl` — Excel ingest in [`src/tools/_excel.py`](../src/tools/_excel.py).
- `structlog` — JSON logging via
  [`src/logging_config.py`](../src/logging_config.py).
- `pytest` + `pytest-asyncio` (`asyncio_mode = "auto"`,
  `integration` marker for tests requiring real Cosmos).

## Project conventions (must follow)

1. **Async everywhere.** All Cosmos and tool entrypoints are `async def`.
   When invoking the sync OR-Tools solver from a tool, wrap with
   `await asyncio.to_thread(solve_cvrptw, ...)` (see
   [`src/tools/optimize.py`](../src/tools/optimize.py)).
2. **Repository pattern.** Never instantiate Cosmos `ContainerProxy`
   directly from a tool. Add a method to the relevant repo under
   [`src/data/`](../src/data/), all of which extend
   [`BaseRepository`](../src/data/base_repo.py). Use `bulk_upsert` (which
   gates concurrency with a Semaphore) for batches.
3. **Pydantic v2 models are the wire format.** Every tool input/output is a
   `BaseModel` declared in [`src/models/requests.py`](../src/models/requests.py).
   Use `ConfigDict(populate_by_name=True)` and `Field(alias=...)` when the
   Cosmos document field name differs from the Python attribute (e.g. `_ttl`).
4. **Time is UTC and timezone-aware.** Use `datetime.now(UTC)` (import
   `from datetime import UTC, datetime`). Never `datetime.utcnow()`.
5. **Settings come from env only.** Never hard-code Azure endpoints or
   container names. Read via `get_settings()` from
   [`src/config.py`](../src/config.py); the Bicep outputs in
   [`infra/main.bicep`](../infra/main.bicep) are the source of truth for
   what env vars exist.
6. **No emojis in code or logs.** Logs are structured JSON via structlog —
   pass fields as kwargs (`log.info("event.name", count=n)`), never f-string
   them into the message.
7. **Cosmos containers and PKs** are defined once in
   [`src/data/cosmos_client.py`](../src/data/cosmos_client.py)'s `CONTAINERS`
   dict and mirrored in [`infra/modules/cosmos.bicep`](../infra/modules/cosmos.bicep).
   Keep the two in sync; PK paths must match exactly.

## Tool authoring checklist

When adding a new MCP tool:

1. Define request/response models in `src/models/requests.py`.
2. Create `src/tools/<name>.py` with an async function decorated
   `@mcp.tool()` taking the request model and returning the response model.
3. Import the new module from `_register()` in `src/server.py` so the
   decorator runs.
4. Add a unit test under `tests/`. Tests must run offline — use the dummy
   `AZURE_COSMOS_ENDPOINT` set in [`tests/conftest.py`](../tests/conftest.py)
   and only hit Cosmos in tests marked `@pytest.mark.integration`.
5. If the tool reads/writes Cosmos, do it through a repository — add a new
   query method there rather than constructing SQL in the tool.

## Infra conventions

- Bicep is at **subscription scope** (`targetScope = 'subscription'` in
  [`infra/main.bicep`](../infra/main.bicep)). The deployment creates the
  resource group itself.
- Resource names use the azd resource token pattern:
  `cosmos-rt-${uniqueString(...)}`, `kv-rt-${uniqueString(...)}`.
- Region default is **East US 2**.
- All RBAC role assignments use **role-definition GUIDs** (not names):
  Cosmos DB Built-in Data Contributor `00000000-0000-0000-0000-000000000002`,
  Key Vault Secrets Officer `b86a8fe4-44ce-4948-aee5-eccb2c155cd7`.
- Container Apps deployment is intentionally **not** wired into
  [`azure.yaml`](../azure.yaml) yet — only `provider: bicep` is configured.
  Adding a `services:` block is a deliberate Sprint 3+ task.

## Out-of-scope for the skeleton (do not add unless asked)

- Cube-degradation curves on trailers (spec §6.2)
- Lead-pup split logic for two-stop routes (spec §10.3)
- State-restriction enforcement inside the solver (spec §6.4) — the model
  carries the data, the solver does not yet consume it
- Real Azure Maps Route Matrix calls — `src/services/azure_maps.py` is a
  Haversine stub. Keep it isolated behind `get_matrix(points, profile)` so
  the swap is a single-file change.
- Any front-end, dashboard, or non-MCP API surface

## Testing & verification

- `pytest -v` from the activated venv must stay green (10 unit tests).
- After adding a tool, smoke-test registration:
  ```powershell
  $env:AZURE_COSMOS_ENDPOINT="https://example.documents.azure.com:443/"
  python -c "import asyncio, src.server as s; print(sorted(t.key for t in asyncio.run(s.mcp._list_tools())))"
  ```
- For real Cosmos validation, set a real endpoint and run
  `pytest -m integration`.
