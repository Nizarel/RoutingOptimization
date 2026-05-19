# Routing Optimization MCP Server

A FastMCP server that ingests Albertsons SLC DC routing data (locations,
trailer types, state restrictions, daily order boards) into Azure Cosmos DB
and serves CVRPTW route plans via Google OR-Tools.

This repository implements the spec described in
[`Routing_Optimization_MCP_Server_Spec_Architecture.md`](Routing_Optimization_MCP_Server_Spec_Architecture.md)
through Sprint 7 (Azure Maps Route Matrix v2 + vehicleSpec, cost guards).

> **Deployment status — 2026-05-19:** All Sprint 1–6 work is live in
> `rg-routing-mcp-dev`. 12 MCP tools, 8 resources, 5 prompts, and full OTel
> telemetry are running. Health probes verified green. 74 unit tests pass.

## Status

| Capability | State |
|---|---|
| Pydantic v2 domain models (Locations, Trailers, Restrictions, Orders, Routes, Matrix) | ✅ |
| Async Cosmos repositories (RBAC via `DefaultAzureCredential`) | ✅ |
| Excel ingest (`ingest_locations`, `ingest_order_board`) | ✅ |
| Read-only query tools (`get_store_orders`, `get_restrictions`) | ✅ |
| OR-Tools CVRPTW solver (distance + weight + cube + time dimensions) | ✅ |
| `optimize_route` end-to-end tool + `routing://last-solution` resource | ✅ |
| 12 MCP tools, 8 resources, 5 prompts | ✅ |
| Bicep IaC at subscription scope (Cosmos serverless + Key Vault, VNet, Private Endpoint) | ✅ |
| HTTP health probes (`/healthz`, `/readyz`) for Container Apps liveness/readiness | ✅ |
| Azure Monitor / OpenTelemetry distro (App Insights traces + logs) | ✅ |
| Container App external HTTPS ingress, UAMI auth, 1–3 replicas | ✅ |
| Locust load test script (`scripts/load_test.py`) | ✅ |
| Real Azure Maps Route Matrix integration | ✅ Sprint 7 (v2 GeoJSON + vehicleSpec, Haversine fallback retained) |
| Cube-degradation / lead-pup split / state restrictions enforcement | ⏳ Sprint 8 |

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
pytest -v   # 74 unit tests pass offline; 1 integration test skipped
```

The integration test in `tests/integration/test_cosmos.py` is skipped unless
`AZURE_COSMOS_ENDPOINT` points at a real account.

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
scope: resource group, serverless Cosmos DB (7 containers), Key Vault, VNet,
private endpoint, Container Registry, Container Apps environment, Application
Insights, and Azure Maps. The current user receives **Cosmos DB Built-in Data
Contributor** and **Key Vault Secrets Officer** roles — no master keys are issued.

```powershell
# Build + push image and deploy the Container App
azd deploy
```

Export provisioned outputs into a local `.env`:

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
| Transport | HTTPS, port 8000 (external ingress enabled) |
| Scale | 1–3 replicas |
| Auth | User-assigned Managed Identity (`AZURE_CLIENT_ID=31c337c0-9f4f-453a-8bea-b0be1e9ba6b3`) |
| Liveness probe | `GET /healthz` (HTTP 200 → alive) |
| Readiness probe | `GET /readyz` (HTTP 200 → Cosmos reachable; 503 → not ready) |
| Startup probe | `GET /healthz` (30 s grace, 10 retries) |
| Telemetry | Azure Monitor / OTel distro → App Insights (`appi-rt-vqcz36euruiko`) |

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

Optional Azure Maps tuning (defaults shown):

```
AZURE_MAPS_MATRIX_MAX_CELLS            700    # refuse matrices larger than this
AZURE_MAPS_MATRIX_DAILY_BUDGET_CELLS   <unset># per-replica daily soft cap; raises RuntimeError when exceeded
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
| `matrix_travel_times` | Compute travel-time/distance matrix via Azure Maps Route Matrix v2 (cached, optional `vehicle_spec`) |
| `geocode_address` | Geocode a street address via Azure Maps |
| `directions` | Turn-by-turn directions between two points |
| `isochrone` | Compute reachability polygon from a point |
| `map_render` | Render a static map tile |
| `select_trailer` | Recommend trailer type for a given order profile |
| `validate_route` | Validate a proposed route against state restrictions |

## Resources

| Resource URI | Content |
|---|---|
| `routing://last-solution` | Most recent persisted `RouteHistory`, JSON |
| `routing://districts` | All DC districts |
| `routing://locations` | All store locations |
| `routing://order-summary/{order_group}` | Aggregated order summary |
| `routing://profiles` | Available routing profiles |
| `routing://state-restrictions/{state}` | State restrictions |
| `routing://trailer-types` | Trailer type catalog |
| `routing://vehicles` | Available vehicles |

## Health endpoints

```powershell
$fqdn = "ca-rt-vqcz36euruiko.proudglacier-ba160324.eastus2.azurecontainerapps.io"
curl "https://$fqdn/healthz"   # {"status":"ok","ts":"..."}
curl "https://$fqdn/readyz"    # {"status":"ready"} or {"status":"not_ready","reason":"cosmos_unreachable"}
```

## Smoke test

```powershell
.\.venv\Scripts\python.exe scripts/smoke_mcp.py `
  "https://ca-rt-vqcz36euruiko.proudglacier-ba160324.eastus2.azurecontainerapps.io/mcp"
```

## Load test

Requires the `dev` extras (`pip install -e ".[dev]"`):

```powershell
# headless 2-minute run, 20 users, ramp at 2/s
locust -f scripts/load_test.py `
  --host https://ca-rt-vqcz36euruiko.proudglacier-ba160324.eastus2.azurecontainerapps.io `
  -u 20 -r 2 -t 2m --headless --csv loadtest

# interactive web UI at http://localhost:8089
locust -f scripts/load_test.py `
  --host https://ca-rt-vqcz36euruiko.proudglacier-ba160324.eastus2.azurecontainerapps.io
```

Tasks: `get_restrictions` (5×), `get_store_orders` (5×), `GET /healthz` (2×), `matrix_travel_times` (1×).
Override fixtures via env: `LOAD_ORDER_GROUP`, `LOAD_STATE`.

## Project layout

```
src/
  server.py            FastMCP entrypoint, transport selection
  config.py            Pydantic Settings (env vars, spec §15)
  logging_config.py    structlog JSON logging (noisy Azure SDK loggers silenced)
  telemetry.py         Azure Monitor / OTel init (no-op when conn string absent)
  health.py            /healthz and /readyz HTTP routes
  models/              Pydantic v2 domain models
  data/                Async Cosmos client + repository pattern
  services/
    azure_maps.py      Route Matrix v2 client + VehicleSpec (Haversine fallback)
    solver.py          OR-Tools CVRPTW
  tools/               @mcp.tool() implementations (12 tools)
  resources/           @mcp.resource() implementations (8 resources)
  prompts/             @mcp.prompt() implementations (5 prompts)
infra/                 Bicep (subscription scope) + parameters
tests/                 74 unit tests + 1 skipped integration test
scripts/
  seed_data.py         CLI wrapper around ingest tools
  smoke_mcp.py         Quick functional smoke test
  load_test.py         Locust load test (read-heavy)
```

## Next steps (Sprint 8+)

### Sprint 8 — Solver constraint engine
1. Cube degradation (spec §6.2) inside the solver — trailer cube limit shrinks
   with each additional stop on a route.
2. Lead/pup split for two-stop routes (spec §10.3).
3. State restriction enforcement *inside* the solver (currently pre-filtered
   by `ConstraintEngine` before solving).
4. Trailer dimensions catalog (length/width/height per `trailer_type`) to
   replace the weight-only `VehicleSpec` placeholder in `optimize_route`.
5. Interstate-proximity check using Azure Maps `isochrone` / road network.

### Sprint 5 backlog — Remaining tools and prompts
6. 7 remaining MCP resources (FR-020 through FR-027).
7. 5 MCP prompts in `src/prompts/` (FR-030 through FR-034).
8. Eval harness comparing solver output to historical `RouteHistory`.
