# Routing Optimization MCP Server

A FastMCP server that ingests Albertsons SLC DC routing data (locations,
trailer types, state restrictions, daily order boards) into Azure Cosmos DB
and serves CVRPTW route plans via Google OR-Tools.

This repository implements the **walking skeleton** described in
[`Routing_Optimization_MCP_Server_Spec_Architecture.md`](Routing_Optimization_MCP_Server_Spec_Architecture.md)
(spec §14, Sprints 1–2).

> **Deployment status — 2026-05-18:** Full Sprint 1–2 infrastructure is live in
> `rg-routing-mcp-dev` (subscription `0192a5d6-e628-4362-9838-9a38759772a6`,
> tenant `f41907ba-5052-4208-b43b-fd1518a87d3e`). All 7 Cosmos containers are
> provisioned, seed data is loaded (57 order-board documents confirmed), and the
> Container App is running. Sprint 3+ work (real Azure Maps, constraint engine,
> remaining tools) is pending.

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
| Real Azure Maps Route Matrix integration | ⏳ Sprint 3 (Haversine stub active) |
| Cube-degradation / lead-pup split / state restrictions enforcement | ⏳ Sprint 4 |
| Container Apps deployment (image live, replicas running) | ✅ |

## Prerequisites

- Python 3.13
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

## Azure Infrastructure (deployed — 2026-05-18)

Resource group: **`rg-routing-mcp-dev`** · Region: East US 2 · Resource token: `vqcz36euruiko`

### Cosmos DB — `cosmos-rt-vqcz36euruiko`

Database: `routing_optimization`

| Container | Partition key | TTL |
|---|---|---|
| `locations` | `/location_type` | none |
| `trailer_types` | `/trailer_class` | none |
| `state_restrictions` | `/state` | none |
| `order_boards` | `/order_group` | 30 days |
| `route_history` | `/dc_code` | 90 days |
| `matrix_cache` | `/profile` | 24 hours |
| `districts` | `/dc_code` | none |

Seed data confirmed: 57 order-board documents in `order_boards` (last verified 2026-05-13).

### Container App — `ca-rt-vqcz36euruiko`

| Property | Value |
|---|---|
| FQDN | `ca-rt-vqcz36euruiko.proudglacier-ba160324.eastus2.azurecontainerapps.io` |
| Transport | HTTP, port 8000 |
| Scale | 1–3 replicas |
| Image | `acrrtvqcz36euruiko.azurecr.io/routing-optimization-mcp/mcp-routing-mcp-dev:azd-deploy-1778658604` |
| Auth | Managed identity (`AZURE_CLIENT_ID=31c337c0-9f4f-453a-8bea-b0be1e9ba6b3`) |

Key environment variables set on the Container App:

```
AZURE_COSMOS_ENDPOINT   https://cosmos-rt-vqcz36euruiko.documents.azure.com:443/
AZURE_COSMOS_DATABASE   routing_optimization
AZURE_KEY_VAULT_URI     https://kv-rt-vqcz36euruiko.vault.azure.net/
AZURE_MAPS_CLIENT_ID    31c337c0-9f4f-453a-8bea-b0be1e9ba6b3  (managed identity)
MCP_TRANSPORT           http
MCP_HTTP_HOST           0.0.0.0
MCP_HTTP_PORT           8000
APPLICATIONINSIGHTS_CONNECTION_STRING  <set; InstrumentationKey=c12febc9-...>
```

### Other resources

| Resource | Name | Notes |
|---|---|---|
| Azure Container Registry | `acrrtvqcz36euruiko` | Hosts the MCP server image |
| Azure Maps | `maps-rt-vqcz36euruiko` | Gen2 · Standard G2 · Managed Identity auth |
| Key Vault | `kv-rt-vqcz36euruiko` | Public access disabled; VNet/private endpoint only |
| App Insights | (connection string above) | Telemetry for Container App |

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

## Next steps (Sprint 3+)

### Sprint 3 — Azure Maps + matrix cache
1. Replace the Haversine stub in `src/services/azure_maps.py` with the real
   Azure Maps Route Matrix v2 async client (Managed Identity token via
   `azure-identity`); keep the `get_matrix(points, profile)` interface stable.
2. Implement `matrix_travel_times` MCP tool: check `matrix_cache` first
   (SHA-256 key of sorted location codes + profile), call Azure Maps on miss,
   persist result with 24-hour TTL.
3. Wire the cached matrix into `optimize_route` instead of always calling
   Haversine.

### Sprint 4 — Constraint engine
4. Create `src/services/constraint_engine.py`: cube degradation (spec §6.2),
   lead/pup split for two-stop routes (spec §10.3), state restriction check
   (spec §6.4), interstate proximity check.
5. Add `select_trailer` tool (spec §7.3, FR-002).
6. Add `validate_route` tool (spec FR-003).
7. Fix overnight curfew window handling in `optimize_route` (currently windows
   spanning midnight are silently dropped).

### Sprint 5 — Remaining tools and prompts
8. `geocode_address`, `directions`, `isochrone`, `map_render` tools
   (FR-005 through FR-008).
9. 7 remaining MCP resources (FR-020 through FR-027).
10. 5 MCP prompts in `src/prompts/` (FR-030 through FR-034).
11. Add an eval harness comparing solver output to historical `RouteHistory`.
