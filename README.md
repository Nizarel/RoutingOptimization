# Routing Optimization MCP Server

A FastMCP server that ingests Albertsons SLC DC routing data (locations,
trailer types, state restrictions, daily order boards) into Azure Cosmos DB
and serves CVRPTW route plans via Google OR-Tools.

This repository implements the **walking skeleton** described in
[`Routing_Optimization_MCP_Server_Spec_Architecture.md`](Routing_Optimization_MCP_Server_Spec_Architecture.md)
(spec §14, Sprints 1–2).

## Status

| Capability | State |
|---|---|
| Pydantic v2 domain models (Locations, Trailers, Restrictions, Orders, Routes, Matrix) | ✅ |
| Async Cosmos repositories (RBAC via `DefaultAzureCredential`) | ✅ |
| Excel ingest (`ingest_locations`, `ingest_order_board`) | ✅ |
| Read-only query tools (`get_store_orders`, `get_restrictions`) | ✅ |
| OR-Tools CVRPTW solver (distance + weight + cube + time dimensions) | ✅ |
| `optimize_route` end-to-end tool + `routing://last-solution` resource | ✅ |
| Bicep IaC at subscription scope (Cosmos serverless + Key Vault, RBAC) | ✅ |
| Real Azure Maps Route Matrix integration | ⏳ stubbed (Haversine) |
| Cube-degradation / lead-pup split / state restrictions enforcement | ⏳ deferred to Sprint 3+ |
| Container Apps deployment target | ⏳ deferred (azd `services:` not wired) |

## Prerequisites

- Python 3.12
- Azure CLI + `azd` (Azure Developer CLI)
- Access to subscription `0192a5d6-e628-4362-9838-9a38759772a6`
  (tenant `f41907ba-5052-4208-b43b-fd1518a87d3e`)

## Local development

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
pytest -v
```

Currently 10 unit tests pass offline; the integration test in
`tests/integration/test_cosmos.py` is skipped unless `AZURE_COSMOS_ENDPOINT`
points at a real account.

## Provision Azure infrastructure

```powershell
az login --tenant f41907ba-5052-4208-b43b-fd1518a87d3e
az account set --subscription 0192a5d6-e628-4362-9838-9a38759772a6

azd auth login --tenant-id f41907ba-5052-4208-b43b-fd1518a87d3e
azd env new routing-dev      # or: azd env select routing-dev
azd env set AZURE_LOCATION eastus2
azd provision
```

`azd provision` deploys [`infra/main.bicep`](infra/main.bicep) at subscription
scope: a resource group, a serverless Cosmos DB account with the 7 containers
defined in spec §13.2, and a Key Vault. The current user (`AZURE_PRINCIPAL_ID`)
receives **Cosmos DB Built-in Data Contributor** and
**Key Vault Secrets Officer** roles — no master keys are issued.

Export the provisioned outputs into a local `.env`:

```powershell
azd env get-values | Out-File -Encoding utf8 .env
```

## Seed data

Drop the customer Excel files into `data/`:

- `data/SLC_Restrictions_Locations.xlsx` — Locations / Trailers / State Restrictions sheets
- `data/Routable_Order_Board.xlsx` — daily order board

Then:

```powershell
python scripts/seed_data.py `
  --locations data/SLC_Restrictions_Locations.xlsx `
  --orders    data/Routable_Order_Board.xlsx
```

This calls the same `ingest_locations` and `ingest_order_board` tools the MCP
server exposes.

## Run the MCP server

```powershell
# HTTP/SSE (default) on http://127.0.0.1:8000
python -m src.server

# STDIO (for MCP Inspector / Claude Desktop subprocess mode)
$env:MCP_TRANSPORT = "stdio"
python -m src.server
```

### Connect with MCP Inspector

```powershell
npx @modelcontextprotocol/inspector
```

Point it at `http://127.0.0.1:8000/sse` for HTTP transport, or run the
inspector with `python -m src.server` as the STDIO command.

## Tools

| Tool | Purpose |
|---|---|
| `ingest_locations` | Parse SLC Excel: Locations + Trailer Types + State Restrictions |
| `ingest_order_board` | Parse daily order board, aggregate by destination |
| `get_store_orders` | Filter the latest `OrderBoard` by destination / order group |
| `get_restrictions` | Read `StateRestriction` records (optional state filter) |
| `optimize_route` | Build a CVRPTW model from depot + stops + vehicles, solve, persist `RouteHistory` |

## Resource

- `routing://last-solution` — the most recent persisted `RouteHistory`, JSON.

## Project layout

```
src/
  server.py            FastMCP entrypoint, transport selection
  config.py            Pydantic Settings (env vars, spec §15)
  logging_config.py    structlog JSON logging
  models/              Pydantic v2 domain models
  data/                Async Cosmos client + repository pattern
  services/
    azure_maps.py      Route matrix (currently Haversine stub)
    solver.py          OR-Tools CVRPTW
  tools/               @mcp.tool() implementations
  resources/           @mcp.resource() implementations
infra/                 Bicep (subscription scope) + parameters
tests/                 Unit tests + skipped integration test
scripts/seed_data.py   CLI wrapper around ingest tools
```

## Next steps (post-skeleton)

1. Replace the Haversine stub in `src/services/azure_maps.py` with the real
   Azure Maps Route Matrix v2 client; persist results to `matrix_cache`.
2. Enforce state restrictions and cube degradation in the solver
   (spec §6, §10).
3. Implement lead/pup split logic for two-stop routes (spec §10.3).
4. Wire the `services:` block in `azure.yaml` to deploy the container to
   Azure Container Apps.
5. Add an eval harness comparing solver output to historical `RouteHistory`.
