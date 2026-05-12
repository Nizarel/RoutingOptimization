# Routing Optimization MCP Server - Specification & Architecture v2.0

> **FastMCP + Google OR-Tools + Azure Maps + Azure Cosmos DB**

| Field | Value |
|---|---|
| **Project** | Routing Optimization Agent - MCP Server |
| **Customer** | Albertsons Companies Inc. (ACI) - SLC Distribution Center |
| **Author** | Nizar El Ouarti - Prin Sol Engineer |
| **Version** | 2.0 |
| **Date** | May 11, 2026 |
| **Status** | Draft - For Development |

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Project Overview and Goals](#2-project-overview-and-goals)
3. [Source Data Analysis](#3-source-data-analysis)
4. [Data-to-Cosmos DB Container Mapping](#4-data-to-cosmos-db-container-mapping)
5. [Cosmos DB Container Schemas (Detailed)](#5-cosmos-db-container-schemas-detailed)
6. [Updated System Architecture](#6-updated-system-architecture)
7. [MCP Tool Specifications](#7-mcp-tool-specifications)
8. [Data Flow and Sequence Diagrams](#8-data-flow-and-sequence-diagrams)
9. [OR-Tools Solver Design](#9-or-tools-solver-design)
10. [Functional Requirements](#10-functional-requirements)
11. [Non-Functional Requirements](#11-non-functional-requirements)
12. [Security and Authentication](#12-security-and-authentication)
13. [Deployment Architecture](#13-deployment-architecture)
14. [Development Roadmap](#14-development-roadmap)
15. [Appendix A - Environment Configuration](#15-appendix-a---environment-configuration)
16. [Appendix B - Project Structure](#16-appendix-b---project-structure)

---

## 1. Executive Summary

This document defines the **v2.0 specification and architecture** for the Routing Optimization MCP Server - a Model Context Protocol (MCP) server that enables AI agents to optimize grocery delivery routes for **Albertsons Companies Inc. (ACI)**.

The server combines:
- **Google OR-Tools** - for constraint-based vehicle routing (CVRPTW) with Albertsons-specific constraints (cube degradation, lead/pup weight splits, state trailer restrictions)
- **Azure Maps** - for real-world travel times, geocoding, directions, isochrones, and map rendering
- **Azure Cosmos DB** - for persistent storage of locations, trailer configurations, state restrictions, order boards, route history, and distance matrix caching

### What Changed in v2.0

| Area | v1.0 (Previous) | v2.0 (This Document) |
|---|---|---|
| **Data Model** | Generic VRP | Albertsons-specific: 416 order lines, 583 locations, 22 trailer configs, 57 state rules |
| **Database** | In-memory only | 7 Cosmos DB containers mapped from customer Excel files |
| **Constraints** | Weight + time windows | + Cube degradation by # stops, lead/pup split, state trailer restrictions, interstate proximity |
| **Solver** | Basic CVRPTW | Multi-constraint CVRPTW with trailer type selection and regulatory compliance |
| **Tools** | 7 generic tools | 10 tools + 2 data-ingestion tools tailored to Albertsons data format |

---

## 2. Project Overview and Goals

### 2.1 Problem Statement

The SLC Distribution Center (DC code: `52-DC`, North Salt Lake, UT) serves **57+ retail stores** across **8 states** (MT, ID, CO, OR, UT, NV, WY, ND) under 5 banners (Albertsons, Safeway, Lucky, Market Street, Dash Mart). Planners must:

- Route **416+ order lines** across **14 commodity types** (produce, meat, perishables, floral, etc.)
- Select from **22 trailer configurations** (13 combos + 9 singles) with varying weight/cube limits
- Comply with **57 state-level trailer restriction rules** (different weight limits and trailer types per state)
- Respect **store curfews** (20 locations with delivery time windows)
- Handle **cube degradation** - trailer capacity decreases as the number of stops increases
- Manage **lead/pup weight splits** for combo trailers (separate max weight for each trailer unit)

### 2.2 Goals

1. Provide **12 MCP tools** covering the full Albertsons routing workflow
2. Solve CVRPTW with up to **200 stops and 50 vehicles** within 60 seconds
3. Persist all reference data and route history in **7 Cosmos DB containers**
4. Enforce state-by-state trailer restrictions including Montana's 2-mile interstate rule
5. Model **stop-dependent cube degradation** as a custom OR-Tools constraint
6. Support both **STDIO** (local) and **HTTP/SSE** (remote) MCP transports

### 2.3 Out of Scope (v2.0)

- Real-time GPS tracking and dynamic re-routing
- Pickup-and-delivery (PDP) problem variant
- Backhaul optimization (using Pickup Locations from the locations file)
- Multi-DC routing (only SLC DC in v2)
- Custom map tile rendering / frontend UI


---

## 3. Source Data Analysis

### 3.1 File 1: Routable Order Board (416 order lines)

**What it is**: The daily routing input - every commodity order that needs to go from the DC to a store.

| Dimension | Value |
|---|---|
| Total order lines | 416 |
| Source DC | `52-DC` (North Salt Lake, UT - 40.8528, -111.925) |
| Unique destinations (stores) | 57 |
| Unique commodities | 14 |
| Order group | `FRE0224` (Fresh commodities, Feb 24 - routable together) |
| States served | MT, ID, CO, OR, UT, NV, WY, ND |
| Banners | Albertsons (278), Safeway (109), Lucky (15), Market Street (10), Dash Mart (4) |

**Commodity breakdown (top 5 by weight):**

| Commodity | Lines | Weight (lbs) | Pallets | Description |
|---|---|---|---|---|
| PRO (Produce) | 55 | ~458K | 335 | Fresh produce - heaviest |
| PER (Perishable) | 55 | ~216K | 97 | General perishables |
| MEA (Meat) | 55 | ~187K | 102 | Fresh meat |
| GM/HBC | 18 | ~47K | 49 | General merchandise |
| FLO (Floral) | 50 | ~25K | 32 | Fresh flowers |

**District groupings (routing regions):**

| District | Lines | Stores | States |
|---|---|---|---|
| SLMontana | 188 | 25 | MT |
| SLBoise | 125 | 17 | ID, OR |
| SLColorado | 51 | 5 | CO |
| SLLocal | 21 | 4 | UT |
| SLEastID | 15 | 2 | NV, WY |
| SLWyoming | 11 | 2 | WY |
| SLHighline | 1 | 1 | ND |

### 3.2 File 2: SLC Restrictions and Locations

**Sheet 1 - Trailer Types (22 configurations):**

| Type | Count | Weight Range | Cube Range (1 stop) |
|---|---|---|---|
| Combo (doubles) | 13 | 66,000 - 70,000 lbs | 2,600 - 3,240 |
| Single | 9 | 41,000 - 46,500 lbs | 1,020 - 2,010 |

**Sheet 2 - Locations (583 total):**

| Location Type | Count | Role in Routing |
|---|---|---|
| Pickup Location | 307 | Supplier/vendor points (backhaul - future) |
| Mileage Store | 131 | Delivery destinations (stores) |
| Distribution Center | 77 | DCs, relay points, swap yards |
| Road Exit | 42 | Fuel stops, detour anchors, highway swap points |
| Freight Delivery | 15 | One-off freight drops |
| Unknown | 11 | Unclassified |

**Sheet 3 - State Trailer Restrictions (57 rules across 7 states):**

| State | Most Permissive Combo | Max Combo Weight | Special Rules |
|---|---|---|---|
| UT | 45+45 | 70,000 lbs | All combos allowed |
| ID | 45+45 | 70,000 lbs | All combos allowed |
| OR | 45+45 | 70,000 lbs | All combos allowed |
| MT | 48+28 | 66,000 lbs | **40+40 only within 2mi of interstate** |
| NV | 40+40 | 66,000 lbs | Fewer combo options |
| WY | 48+28 | 59,000 lbs | Restrictive combo weight |
| CO | 48+28 | 54,000 lbs | **Most restrictive** |


---

## 4. Data-to-Cosmos DB Container Mapping

### 4.1 Mapping Overview

```
SOURCE FILES (Excel)                    COSMOS DB (routing_optimization)
========================                ================================

Routable Order Board                    order_boards container
  Orders (416 rows)  ----aggregate---->   PK: /order_group
  Group by Destination                    57 store-level documents
                                          TTL: 30 days

SLC Restrictions & Locations            locations container
  Locations (583 rows)  ----1:1-------->  PK: /location_type
                                          583 documents

  Max Weight & Cube (22 rows) --1:1--->  trailer_types container
                                          PK: /trailer_class
                                          22 documents

  By State Combo & Weight (57) -1:1--->  state_restrictions container
                                          PK: /state
                                          57 documents

Derived from both files  ------------->  districts container
                                          PK: /dc_code
                                          7 documents

Solver output  ------------------------> route_history container
                                          PK: /dc_code
                                          TTL: 90 days

Azure Maps API  -----------------------> matrix_cache container
                                          PK: /profile
                                          TTL: 24 hours
```

### 4.2 Container-by-Container Mapping

| # | Container | Partition Key | Source | Rows to Docs | TTL | Purpose |
|---|---|---|---|---|---|---|
| 1 | `locations` | `/location_type` | File 2: Locations sheet | 583 to 583 | None | Master location database with lat/lon, curfews |
| 2 | `trailer_types` | `/trailer_class` | File 2: Max Weight & Cube | 22 to 22 | None | Trailer configs with cube degradation curves |
| 3 | `state_restrictions` | `/state` | File 2: By State Combo & Weight | 57 to 57 | None | Legal trailer/weight limits per state |
| 4 | `order_boards` | `/order_group` | File 1: Orders sheet | 416 to 57 | 30 days | Orders aggregated per destination store |
| 5 | `route_history` | `/dc_code` | Solver output | 0 (grows) | 90 days | Persisted optimization results |
| 6 | `matrix_cache` | `/profile` | Azure Maps API | 0 (grows) | 24 hours | Cached distance/time matrices |
| 7 | `districts` | `/dc_code` | Derived from Orders + Locations | 7 | None | District metadata & store groupings |

### 4.3 Transformation Logic

**Orders to `order_boards` (aggregation):**

The 416 raw order lines are aggregated by destination store into 57 store-level documents. Each document contains all commodity orders for that store as a nested array.

**Locations to `locations` (1:1 with enrichment):**

Each of the 583 location rows maps 1:1 to a Cosmos DB document, with coordinates stored as GeoJSON Point for spatial indexing.

**Max Weight & Cube to `trailer_types` (1:1 with restructuring):**

Each trailer row becomes a document with the cube degradation curve stored as an embedded array (`cube_by_stops: [3240, 3200, 3160, ...]`).

**By State Combo & Weight to `state_restrictions` (1:1):**

Each rule becomes a document with `interstate_only: true/false` and `max_distance_from_interstate_mi` fields.


---

## 5. Cosmos DB Container Schemas (Detailed)

### 5.1 Container: `locations`

**Partition Key**: `/location_type` | **Documents**: 583

```json
{
  "id": "1010",
  "location_code": "1010",
  "location_type": "Mileage Store",
  "description": "Albertsons",
  "address": {
    "street": "3800 Russell Street",
    "city": "Missoula",
    "state": "MT",
    "postal": "59801",
    "phone": "4065491547"
  },
  "coordinates": {
    "type": "Point",
    "coordinates": [-114.015, 46.8365]
  },
  "lat": 46.8365,
  "lon": -114.015,
  "district_handle": "SLMontana",
  "district_description": "SLMontana",
  "curfew": { "start": null, "end": null },
  "bh_loc_code": "1010",
  "obc_loc_code": "1010",
  "is_enabled": true
}
```

**Location with curfew example (Store 161):**

```json
{
  "id": "161",
  "location_type": "Mileage Store",
  "description": "Albertsons",
  "address": { "street": "10700 Ustick Rd", "city": "Boise", "state": "ID", "postal": "83713" },
  "lat": 43.6348, "lon": -116.317,
  "district_handle": "SLBoise",
  "curfew": { "start": "22:00", "end": "07:00" },
  "is_enabled": true
}
```

### 5.2 Container: `trailer_types`

**Partition Key**: `/trailer_class` | **Documents**: 22 (13 Combo + 9 Single)

```json
{
  "id": "45+45",
  "trailer_class": "Combo",
  "trailer_type_description": "45+45",
  "dollies": 2,
  "lead_weight_max_lbs": 40000,
  "pup_weight_max_lbs": 30000,
  "total_weight_max_lbs": 70000,
  "cube_by_stops": [3240, 3200, 3160, 3120, 3080, 3040, 3000, 2960, 2920],
  "max_stops_supported": 9
}
```

```json
{
  "id": "53ft",
  "trailer_class": "Single",
  "trailer_type_description": "53'",
  "dollies": 0,
  "lead_weight_max_lbs": 41000,
  "pup_weight_max_lbs": 0,
  "total_weight_max_lbs": 41000,
  "cube_by_stops": [2010, 1970, 1930, 1890, 1850, 1810, 1770],
  "max_stops_supported": 7
}
```

### 5.3 Container: `state_restrictions`

**Partition Key**: `/state` | **Documents**: 57

```json
{
  "id": "MT_40+40",
  "state": "MT",
  "trailer_type": "40+40",
  "trailer_class": "Combo",
  "max_weight_lbs": 66000,
  "within_2mi_interstate_only": true,
  "max_distance_from_interstate_mi": 2,
  "notes": "Can take 40+40 into MT but cannot travel >2 miles off the interstate"
}
```

```json
{
  "id": "CO_48+28",
  "state": "CO",
  "trailer_type": "48+28",
  "trailer_class": "Combo",
  "max_weight_lbs": 54000,
  "within_2mi_interstate_only": false,
  "max_distance_from_interstate_mi": null,
  "notes": "Most restrictive state for combos - only 48+28 allowed at 54K max"
}
```

### 5.4 Container: `order_boards`

**Partition Key**: `/order_group` | **TTL**: 30 days | **Documents**: 57 per planning cycle

```json
{
  "id": "FRE0224_183",
  "order_group": "FRE0224",
  "dc_code": "52-DC",
  "site": "Salt Lake City, Utah",
  "destination": "183",
  "destination_desc": "Albertsons",
  "district": "SLEastID",
  "state": "WY",
  "orders": [
    { "commodity": "PRO", "order_code": "0033571371", "weight_lbs": 19414, "cubes": 1014, "pallets": 14.5, "cases": 1097 },
    { "commodity": "MEA", "order_code": "0033571297", "weight_lbs": 7548, "cubes": 298, "pallets": 4.3, "cases": 430 },
    { "commodity": "PER", "order_code": "0033571278", "weight_lbs": 7363, "cubes": 231, "pallets": 3.3, "cases": 449 },
    { "commodity": "GM/HBC", "weight_lbs": 6079, "cubes": 336, "pallets": 5.0, "cases": 1650 },
    { "commodity": "FLO", "weight_lbs": 475, "cubes": 34, "pallets": 0.5, "cases": 29 },
    { "commodity": "FR Fish", "weight_lbs": 114, "cubes": 12, "pallets": 0.2, "cases": 14 },
    { "commodity": "PAPA", "weight_lbs": 104, "cubes": 14, "pallets": 0.2, "cases": 7 }
  ],
  "totals": {
    "weight_lbs": 41097, "cubes": 1939, "pallets": 28.0,
    "cases": 3676, "order_line_count": 7, "commodity_count": 7
  },
  "ingested_at": "2026-05-11T20:54:00Z",
  "_ttl": 2592000
}
```

### 5.5 Container: `route_history`

**Partition Key**: `/dc_code` | **TTL**: 90 days

```json
{
  "id": "a3f1b2c4-uuid",
  "dc_code": "52-DC",
  "order_group": "FRE0224",
  "created_at": "2026-05-11T21:00:00Z",
  "request": {
    "depot": {"lat": 40.8528, "lon": -111.925},
    "district": "SLMontana",
    "stops": ["1010", "20", "24"],
    "trailer_type": "45+45",
    "profile": "truck",
    "objective": "min_total_distance"
  },
  "result": {
    "status": "optimal",
    "routes": [{
      "vehicle": "V1",
      "trailer_type": "45+45",
      "stops": ["52-DC", "259", "1158", "1010", "20", "52-DC"],
      "stop_count": 4,
      "distance_m": 1452000,
      "duration_min": 987,
      "weight_lbs": 62450,
      "cubes": 2890,
      "cube_limit_used": 3120,
      "weight_utilization_pct": 89.2,
      "cube_utilization_pct": 92.6,
      "states_traversed": ["UT", "ID", "MT"]
    }],
    "summary": {
      "total_distance_m": 4250000,
      "vehicles_used": 3,
      "avg_utilization_pct": 87.4
    }
  },
  "solver_time_sec": 28.4,
  "_ttl": 7776000
}
```

### 5.6 Container: `matrix_cache`

**Partition Key**: `/profile` | **TTL**: 24 hours

```json
{
  "id": "sha256_of_sorted_location_codes",
  "profile": "truck",
  "location_codes": ["52-DC", "1010", "20", "24", "259"],
  "location_count": 5,
  "time_matrix_sec": [[0,25200,26100],[25200,0,1800],[26100,1800,0]],
  "distance_matrix_m": [[0,745000,751000],[745000,0,8200],[751000,8200,0]],
  "fetched_at": "2026-05-11T19:30:00Z",
  "_ttl": 86400
}
```

### 5.7 Container: `districts`

**Partition Key**: `/dc_code` | **Documents**: 7

```json
{
  "id": "SLMontana",
  "dc_code": "52-DC",
  "district_handle": "SLMontana",
  "description": "Salt Lake Montana District",
  "states": ["MT"],
  "store_count": 25,
  "store_codes": ["1010", "20", "24", "33", "35", "37"],
  "banners": ["Albertsons", "Safeway"],
  "allowed_trailer_types": ["48+28", "53ft", "48ft", "45ft", "40ft"],
  "max_combo_weight_lbs": 66000,
  "has_interstate_restrictions": true,
  "relay_points": ["259 Relay Point", "1227 Relay Point"]
}
```


---

## 6. Updated System Architecture

### 6.1 High-Level Architecture

```
+------------------------------------------------------------------------------+
|                           MCP Clients                                        |
|  Claude Desktop | VS Code/Cursor | Copilot Studio | Custom Routing App      |
+----------+---------------------------------------------------------------+--+
           |  MCP Protocol (STDIO / HTTP+SSE)
           v
+------------------------------------------------------------------------------+
|                     FastMCP Server (Python 3.12)                             |
|                                                                              |
|  +------------------------------------------------------------------------+  |
|  |  TOOL LAYER (12 MCP Tools)                                            |  |
|  |                                                                        |  |
|  |  Routing:       optimize_route | select_trailer | validate_route       |  |
|  |  Geospatial:    matrix_travel_times | geocode_address | directions     |  |
|  |  Visualization: isochrone | map_render                                 |  |
|  |  Data Ingest:   ingest_order_board | ingest_locations                  |  |
|  |  Query:         get_store_orders | get_restrictions                    |  |
|  +------------------------------------------------------------------------+  |
|                                                                              |
|  +------------------------------------------------------------------------+  |
|  |  SERVICE LAYER                                                         |  |
|  |  +----------------+ +------------------+ +-------------------------+   |  |
|  |  | VRP Solver     | | Azure Maps Client| | Constraint Engine       |   |  |
|  |  | (OR-Tools)     | | (httpx async)    | | - Cube degradation      |   |  |
|  |  | - CVRPTW       | | - Route Matrix   | | - Lead/pup weight split |   |  |
|  |  | - Multi-dim    | | - Search/Geocode | | - State trailer laws    |   |  |
|  |  | - GLS meta-    | | - Directions     | | - Interstate proximity  |   |  |
|  |  |   heuristic    | | - Route Range    | | - Curfew time windows   |   |  |
|  |  +----------------+ +------------------+ +-------------------------+   |  |
|  |  +------------------------------------------------------------------+  |  |
|  |  | Cache Manager (matrix + geocode lookups)                          |  |  |
|  |  +------------------------------------------------------------------+  |  |
|  +------------------------------------------------------------------------+  |
|                                                                              |
|  +------------------------------------------------------------------------+  |
|  |  DATA LAYER - Repository Pattern (async, azure-cosmos aio)            |  |
|  |  +-----------+ +-----------+ +-----------+ +-----------+ +----------+ |  |
|  |  | Location  | | Trailer   | | State     | | Order     | | Route    | |  |
|  |  | Repo      | | Type Repo | | Restrict  | | Board     | | History  | |  |
|  |  |           | |           | | Repo      | | Repo      | | Repo     | |  |
|  |  +-----------+ +-----------+ +-----------+ +-----------+ +----------+ |  |
|  |  +-----------+ +-----------+                                          |  |
|  |  | Matrix    | | District  |                                          |  |
|  |  | Cache Repo| | Repo      |                                          |  |
|  |  +-----------+ +-----------+                                          |  |
|  +------------------------------------------------------------------------+  |
+-----------------------------------+------------------------------------------+
                                    |
              +---------------------+---------------------+
              v                     v                     v
+------------------+ +------------------+ +----------------------------------+
| Azure Maps API   | | Azure Key Vault  | | Azure Cosmos DB (Serverless)     |
| - Route Matrix   | | - API keys       | |                                  |
| - Search/Geocode | | - Conn strings   | | routing_optimization database    |
| - Directions     | |                  | | +-- locations       (583 docs)   |
| - Route Range    | |                  | | +-- trailer_types   (22 docs)    |
| - Render         | |                  | | +-- state_restrict  (57 docs)    |
|                  | |                  | | +-- order_boards    (57/cycle)   |
|                  | |                  | | +-- route_history   (grows)      |
|                  | |                  | | +-- matrix_cache    (TTL:24h)    |
|                  | |                  | | +-- districts       (7 docs)     |
+------------------+ +------------------+ +----------------------------------+
```

### 6.2 What Changed from v1.0

| Component | v1.0 | v2.0 |
|---|---|---|
| **Tool Layer** | 7 generic tools | 12 tools (+ingest, +select_trailer, +validate, +queries) |
| **Service Layer** | OR-Tools + Azure Maps | + **Constraint Engine** for cube degradation, lead/pup splits, state laws |
| **Data Layer** | In-memory (`_last_solution`) | 7 async Cosmos DB repositories |
| **Database** | None | Cosmos DB Serverless with 7 containers |
| **Resources** | 4 | 8 (+trailer_types, +state_restrictions, +order_summary, +districts) |
| **Prompts** | 3 generic | 5 (+select_best_trailer, +check_compliance) |

### 6.3 New Component: Constraint Engine

```python
class ConstraintEngine:
    def get_cube_limit(self, trailer_type: str, num_stops: int) -> int:
        # e.g., 45+45 with 4 stops -> cube_by_stops[3] = 3120

    def get_allowed_trailers(self, states: list[str]) -> list[dict]:
        # Intersect state_restrictions for each state

    def check_weight_split(self, trailer: str, lead_wt: int, pup_wt: int) -> bool:
        # Verify lead <= lead_max AND pup <= pup_max

    def check_interstate_proximity(self, trailer: str, state: str,
                                     stop_lat: float, stop_lon: float) -> bool:
        # For MT 40+40: verify stop is within 2mi of I-90/I-15

    def get_curfew_window(self, location_code: str) -> tuple | None:
        # Return delivery time window from location curfew data
```


---

## 7. MCP Tool Specifications

### 7.1 Tool Inventory (12 tools)

| # | Tool | Category | Description | Priority |
|---|---|---|---|---|
| 1 | `optimize_route` | Routing | Solve CVRPTW with all ACI constraints | Must |
| 2 | `select_trailer` | Routing | Recommend best trailer type for a route | Must |
| 3 | `validate_route` | Routing | Check a proposed route against all constraints | Must |
| 4 | `matrix_travel_times` | Geospatial | Get NxN distance/time matrix (cached) | Must |
| 5 | `geocode_address` | Geospatial | Address to lat/lon (cached) | Must |
| 6 | `directions` | Geospatial | Turn-by-turn directions | Must |
| 7 | `isochrone` | Visualization | Reachable area polygon | Should |
| 8 | `map_render` | Visualization | Static map with route overlay | Should |
| 9 | `ingest_order_board` | Data Ingest | Parse Order Board Excel into order_boards | Must |
| 10 | `ingest_locations` | Data Ingest | Parse Locations Excel into 3 containers | Must |
| 11 | `get_store_orders` | Query | Get all orders for a store or district | Must |
| 12 | `get_restrictions` | Query | Get trailer restrictions for a state/route | Must |

### 7.2 `optimize_route` - Full Specification

**Input Schema:**
```json
{
  "dc_code": "52-DC",
  "order_group": "FRE0224",
  "district": "SLMontana",
  "stops": ["1010", "20", "24", "33", "35"],
  "trailer_type": "45+45",
  "num_vehicles": 3,
  "profile": "truck",
  "max_solver_seconds": 30,
  "objective": "min_total_distance",
  "enforce_state_restrictions": true,
  "enforce_curfews": true
}
```

**Processing Steps:**
1. Load depot coordinates from `locations` container (52-DC)
2. Load stop coordinates and curfews from `locations` container
3. Load trailer config from `trailer_types` container
4. Load state restrictions from `state_restrictions` container
5. Check `matrix_cache`; if miss -> call Azure Maps Route Matrix API -> cache result
6. Build OR-Tools model with 4 dimensions: distance, time, weight, cube
7. Apply curfew time windows from location data
8. Apply state restriction feasibility filter
9. Solve with Guided Local Search metaheuristic
10. Persist request + result to `route_history` container
11. Return optimized routes with utilization metrics

**Output Schema:**
```json
{
  "status": "optimal",
  "trailer_type": "45+45",
  "routes": [{
    "vehicle": "V1",
    "stops": ["52-DC", "259", "1158", "1010", "52-DC"],
    "stop_count": 3,
    "distance_m": 1452000,
    "duration_min": 987,
    "weight_lbs": 58200,
    "lead_weight_lbs": 35000,
    "pup_weight_lbs": 23200,
    "cubes": 2950,
    "cube_limit": 3160,
    "weight_utilization_pct": 83.1,
    "cube_utilization_pct": 93.4,
    "states_traversed": ["UT", "ID", "MT"]
  }],
  "summary": {
    "total_distance_m": 4250000,
    "vehicles_used": 3,
    "avg_weight_utilization_pct": 85.0,
    "avg_cube_utilization_pct": 88.7
  },
  "compliance": {
    "state_restrictions_passed": true,
    "curfew_violations": 0,
    "weight_violations": 0
  },
  "history_id": "a3f1b2c4-..."
}
```

### 7.3 `select_trailer`

**Input:** `{ "stops": ["1010","20","24"], "states": ["UT","MT"], "total_weight_lbs": 52000, "total_cubes": 2800 }`

**Output:** `{ "recommended": "48+28", "reason": "Legal in both UT and MT. Cube limit at 3 stops = 2840. Weight limit 66000.", "alternatives": [...] }`

### 7.4 `ingest_order_board`

**Input:** `{ "file_path": "/uploads/Routable_Order_Board.xlsx", "sheet_name": "Orders" }`

**Processing:** Read Excel -> Group by Destination -> Aggregate -> Upsert 57 docs into order_boards

### 7.5 `ingest_locations`

**Input:** `{ "file_path": "/uploads/SLC_Restrictions_Locations.xlsx" }`

**Processing:**
1. Parse "Locations" sheet -> 583 docs into `locations`
2. Parse "Max weight and Cube" sheet -> 22 docs into `trailer_types`
3. Parse "By State Combo and Weight" -> 57 docs into `state_restrictions`
4. Derive 7 district docs -> `districts`


---

## 8. Data Flow and Sequence Diagrams

### 8.1 Data Ingestion Flow

```
Planner uploads Excel files
        |
        v
+-- ingest_locations --------------------------------------------------+
|  Parse "Locations" sheet -----------> locations container (583)       |
|  Parse "Max Weight & Cube" ---------> trailer_types container (22)   |
|  Parse "By State Combo" -----------> state_restrictions (57)         |
|  Derive district groupings ---------> districts container (7)        |
+----------------------------------------------------------------------+
        |
        v
+-- ingest_order_board ------------------------------------------------+
|  Parse "Orders" sheet                                                 |
|  Group by Destination                                                 |
|  Aggregate weight/cubes/pallets ----> order_boards container (57)     |
+----------------------------------------------------------------------+
```

### 8.2 Route Optimization Flow

```
Agent              MCP Server           Cosmos DB          Azure Maps       OR-Tools
  |                     |                    |                  |               |
  |-- optimize_route -> |                    |                  |               |
  |                     |-- load depot ----->|                  |               |
  |                     |<-- 52-DC coords --|                  |               |
  |                     |-- load stops ---->|                  |               |
  |                     |<-- 25 locations --|                  |               |
  |                     |-- load trailer -->|                  |               |
  |                     |<-- 45+45 config --|                  |               |
  |                     |-- load state --->|                  |               |
  |                     |   restrictions    |                  |               |
  |                     |<-- MT rules -----|                  |               |
  |                     |-- check matrix ->|                  |               |
  |                     |<-- CACHE MISS ---|                  |               |
  |                     |-- Route Matrix ---------------------->|               |
  |                     |<-- 26x26 matrix ----------------------|               |
  |                     |-- save matrix -->|                  |               |
  |                     |-- build VRP model ---------------------------------------->
  |                     |   (distance, time, weight, cube dims)                |
  |                     |<-- solution ---------------------------------------------|
  |                     |-- save history ->|                  |               |
  |<-- routes + summary |                    |                  |               |
```


---

## 9. OR-Tools Solver Design

### 9.1 Dimensions

| Dimension | Type | Callback | Constraint |
|---|---|---|---|
| **Distance** | Transit | `distance_matrix[i][j]` | Minimize total or minimize longest route |
| **Time** | Transit | `time_matrix[i][j] + service_time[i]` | Curfew windows (CumulVar ranges) |
| **Weight** | Unary demand | `stop_weight[i]` | <= `trailer.total_weight_max` per vehicle |
| **Cube** | Unary demand | `stop_cubes[i]` | <= `trailer.cube_by_stops[num_stops - 1]` |

### 9.2 Cube Degradation - Implementation Strategy

The cube constraint is **non-standard** because the limit depends on the number of stops:

```python
def solve_with_cube_degradation(stops, trailer, ...):
    # Strategy: Iterative solve with cube limit adjustment
    # 1. First pass: solve with cube_limit = cube_by_stops[0] (max)
    # 2. For each route in solution, count stops
    # 3. Check: actual_cubes <= cube_by_stops[actual_stops - 1]
    # 4. If violation: re-solve with tighter constraint or fewer stops
    # 5. Repeat until feasible
```

### 9.3 State Restriction - Pre-Filtering

```python
def pre_filter_stops(stops, trailer_type, state_restrictions):
    # For each stop:
    # 1. Get the stop's state
    # 2. Check if trailer_type is allowed in that state
    # 3. If not, flag as infeasible
    # For MT with 40+40:
    # 4. Check if stop is within 2mi of I-90/I-15
    # 5. If not, reject the combo for that stop
```

### 9.4 Lead/Pup Weight Split

```python
def assign_orders_to_trailers(route_orders, trailer):
    # Bin-packing within a combo:
    # - Lead trailer: up to trailer.lead_weight_max
    # - Pup trailer:  up to trailer.pup_weight_max
    # - Total: <= trailer.total_weight_max
```


---

## 10. Functional Requirements

### 10.1 MCP Tools

| ID | Tool | Description | Priority |
|---|---|---|---|
| FR-001 | `optimize_route` | Solve CVRPTW with weight, cube (degrading), time, state restrictions | Must |
| FR-002 | `select_trailer` | Recommend legal trailer type for given stops and states | Must |
| FR-003 | `validate_route` | Check proposed route against all constraints | Must |
| FR-004 | `matrix_travel_times` | NxN matrix (Cosmos DB cache + Azure Maps fallback) | Must |
| FR-005 | `geocode_address` | Address to lat/lon with Cosmos DB cache | Must |
| FR-006 | `directions` | Turn-by-turn directions with avoidance options | Must |
| FR-007 | `isochrone` | Reachable area polygon from origin | Should |
| FR-008 | `map_render` | Static map with pins and route overlay | Should |
| FR-009 | `ingest_order_board` | Parse Order Board Excel into order_boards | Must |
| FR-010 | `ingest_locations` | Parse Locations/Restrictions Excel into 3 containers | Must |
| FR-011 | `get_store_orders` | Query orders by store, district, or commodity | Must |
| FR-012 | `get_restrictions` | Query state restrictions and allowed trailer types | Must |

### 10.2 MCP Resources

| ID | URI | Description |
|---|---|---|
| FR-020 | `routing://profiles` | Available routing profiles and objectives |
| FR-021 | `routing://last-solution` | Most recent optimization result |
| FR-022 | `routing://trailer-types` | All 22 trailer configurations with cube curves |
| FR-023 | `routing://state-restrictions/{state}` | Restrictions for a specific state |
| FR-024 | `routing://districts` | All 7 district groupings with store lists |
| FR-025 | `routing://order-summary/{order_group}` | Summary stats for an order board |
| FR-026 | `routing://locations/{location_code}` | Single location details |
| FR-027 | `routing://vehicles` | Vehicle definitions from last run |

### 10.3 MCP Prompts

| ID | Prompt | Description |
|---|---|---|
| FR-030 | `plan_district_route` | Guide agent: load orders -> select trailer -> optimize -> present |
| FR-031 | `compare_scenarios` | Compare different trailer types or fleet sizes |
| FR-032 | `explain_solution` | Explain routing decisions and constraint impacts |
| FR-033 | `select_best_trailer` | Walk through trailer selection considering all state constraints |
| FR-034 | `check_compliance` | Verify a route against all regulatory and capacity constraints |

### 10.4 Database Requirements

| ID | Requirement | Priority |
|---|---|---|
| FR-040 | Persist all 583 locations with coordinates, curfews, districts | Must |
| FR-041 | Persist all 22 trailer types with cube degradation curves | Must |
| FR-042 | Persist all 57 state restriction rules | Must |
| FR-043 | Aggregate and persist order boards per planning cycle (TTL: 30d) | Must |
| FR-044 | Cache distance/time matrices keyed by location hash + profile (TTL: 24h) | Must |
| FR-045 | Persist every optimization result with full request/response (TTL: 90d) | Must |
| FR-046 | Derive and persist district metadata with store lists and allowed trailers | Must |
| FR-047 | Support Excel file ingestion to populate/refresh containers | Must |

---

## 11. Non-Functional Requirements

| ID | Category | Requirement |
|---|---|---|
| NFR-001 | Performance | `optimize_route`: <=60s for 200 stops, 50 vehicles |
| NFR-002 | Performance | `matrix_travel_times`: <=15s for 100x100 matrix |
| NFR-003 | Performance | Cached lookups (locations, trailers, restrictions): <=200ms |
| NFR-004 | Performance | `ingest_order_board`: <=10s for 500 order lines |
| NFR-005 | Scalability | Handle 50 concurrent MCP tool calls via async I/O |
| NFR-006 | Availability | 99.9% uptime on Azure Container Apps |
| NFR-007 | Security | Azure Maps keys never exposed in MCP responses or logs |
| NFR-008 | Security | Cosmos DB auth via Managed Identity (no connection strings) |
| NFR-009 | Observability | Structured JSON logging; OpenTelemetry traces |
| NFR-010 | Portability | Python 3.10+, Linux, Docker containerized |
| NFR-011 | Accuracy | All state restriction checks must be 100% correct (legal compliance) |
| NFR-012 | Accuracy | Cube degradation must match exact values from trailer config |

---

## 12. Security and Authentication

### 12.1 Azure Maps
- **Primary**: Subscription Key in Azure Key Vault, injected via env var
- **Production**: AAD Managed Identity token-based auth
- Key rotation: 90-day automatic via Key Vault

### 12.2 Cosmos DB
- **Primary**: Azure AD Managed Identity (RBAC: Cosmos DB Built-in Data Contributor)
- **Dev/Test fallback**: Connection string from Key Vault
- All data encrypted at rest (Microsoft-managed keys)

### 12.3 MCP Transport
- **STDIO**: Process-level security (local only)
- **HTTP**: TLS 1.2+, API key or OAuth2 bearer token
- Rate limiting: 100 req/min per client

### 12.4 Data Protection
- Location data (PII): 90-day retention on route_history
- API keys redacted from all logs
- All data encrypted in transit (TLS 1.2+)

---

## 13. Deployment Architecture

### 13.1 Target Environment

| Component | Azure Service | Configuration |
|---|---|---|
| MCP Server | Azure Container Apps | Python 3.12, 0.5-2 vCPU, 1-4 GiB RAM |
| Database | Azure Cosmos DB | NoSQL API, Serverless, East US 2 |
| Maps | Azure Maps | S1 Gen2 pricing tier |
| Secrets | Azure Key Vault | API keys, connection strings |
| Monitoring | Azure Monitor + App Insights | Logs, metrics, traces |
| Registry | Azure Container Registry | Docker images |

### 13.2 Cosmos DB Provisioning

```bash
# Create Cosmos DB account (serverless)
az cosmosdb create \
  --name routing-optimization-db \
  --resource-group rg-routing \
  --capabilities EnableServerless \
  --default-consistency-level Session \
  --locations regionName="East US 2"

# Create database
az cosmosdb sql database create \
  --account-name routing-optimization-db \
  --name routing_optimization

# Create containers
az cosmosdb sql container create --name locations          --partition-key-path /location_type
az cosmosdb sql container create --name trailer_types      --partition-key-path /trailer_class
az cosmosdb sql container create --name state_restrictions  --partition-key-path /state
az cosmosdb sql container create --name order_boards       --partition-key-path /order_group    --default-ttl 2592000
az cosmosdb sql container create --name route_history      --partition-key-path /dc_code        --default-ttl 7776000
az cosmosdb sql container create --name matrix_cache       --partition-key-path /profile        --default-ttl 86400
az cosmosdb sql container create --name districts          --partition-key-path /dc_code
```

### 13.3 Dockerfile

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml .
RUN pip install --no-cache-dir .[all]
COPY src/ ./src/
EXPOSE 8000
CMD ["fastmcp", "run", "src/server.py:mcp", "--transport", "http", "--host", "0.0.0.0", "--port", "8000"]
```

### 13.4 Local Development

```bash
# 1. Clone and install
git clone https://dev.azure.com/org/routing-mcp
cd routing-mcp && pip install -e .[dev]

# 2. Set environment variables
cp .env.example .env  # edit with your keys

# 3. Seed Cosmos DB with customer data
python scripts/seed_data.py \
  --locations "data/SLC_Restrictions_Locations.xlsx" \
  --orders "data/Routable_Order_Board.xlsx"

# 4. Run locally (STDIO)
python src/server.py

# 5. Run locally (HTTP)
fastmcp run src/server.py:mcp --transport http --port 8000

# 6. Run tests
pytest tests/ -v --cov=src
```

---

## 14. Development Roadmap

| Sprint | Theme | Deliverables |
|---|---|---|
| **Sprint 1** (Wk 1-2) | Foundation | Project scaffold, Pydantic models, basic optimize_route, OR-Tools unit tests |
| **Sprint 2** (Wk 3-4) | Cosmos DB + Ingestion | 7 containers provisioned, repository pattern, ingest tools, seed scripts |
| **Sprint 3** (Wk 5-6) | Azure Maps + Cache | Azure Maps client, matrix_cache with TTL, integration tests |
| **Sprint 4** (Wk 7-8) | Constraint Engine | Cube degradation, lead/pup split, state restrictions, select_trailer, validate_route |
| **Sprint 5** (Wk 9-10) | Advanced Tools | Isochrone, map_render, all 8 MCP resources, 5 MCP prompts, E2E agent testing |
| **Sprint 6** (Wk 11-12) | Production | Docker, Container Apps, Key Vault, Managed Identity, monitoring, load testing |

### Future (v3.0)
- Backhaul optimization (using 307 Pickup Locations)
- Multi-DC routing (Portland DC, Denver DC)
- Real-time traffic integration
- Dynamic re-routing on vehicle delays
- Power BI analytics dashboard

---

## 15. Appendix A - Environment Configuration

| Variable | Description | Required | Default |
|---|---|---|---|
| `AZURE_MAPS_SUBSCRIPTION_KEY` | Azure Maps API key | Yes | - |
| `AZURE_COSMOS_ENDPOINT` | Cosmos DB account URL | Yes | - |
| `AZURE_COSMOS_DATABASE` | Cosmos DB database name | Yes | `routing_optimization` |
| `AZURE_MAPS_BASE_URL` | Azure Maps base URL | No | `https://atlas.microsoft.com` |
| `DEFAULT_ROUTING_PROFILE` | Default travel mode | No | `truck` |
| `MATRIX_CACHE_TTL_SEC` | Matrix cache expiry | No | `86400` |
| `MCP_LOG_LEVEL` | Logging level | No | `INFO` |
| `MCP_TRANSPORT` | MCP transport mode | No | `stdio` |
| `MCP_HTTP_PORT` | HTTP port | No | `8000` |

### Python Dependencies

| Package | Version | Purpose |
|---|---|---|
| `fastmcp` | >=2.0 | MCP protocol server |
| `ortools` | >=9.10 | OR-Tools constraint solver |
| `httpx` | >=0.27 | Async HTTP client |
| `pydantic` | >=2.0 | Data validation |
| `azure-cosmos` | >=4.7 | Cosmos DB async SDK |
| `azure-identity` | >=1.17 | Managed Identity auth |
| `pandas` | >=2.0 | Excel file parsing |
| `openpyxl` | >=3.1 | Excel engine for pandas |
| `python-dotenv` | >=1.0 | .env file loading |

---

## 16. Appendix B - Project Structure

```
routing-optimization-mcp/
|-- src/
|   |-- server.py                  # FastMCP server entry point
|   |-- config.py                  # Environment & settings
|   |-- tools/
|   |   |-- optimize.py            # optimize_route tool
|   |   |-- select_trailer.py      # select_trailer tool
|   |   |-- validate_route.py      # validate_route tool
|   |   |-- matrix.py              # matrix_travel_times tool
|   |   |-- geocode.py             # geocode_address tool
|   |   |-- directions.py          # directions tool
|   |   |-- isochrone.py           # isochrone tool
|   |   |-- map_render.py          # map_render tool
|   |   |-- ingest_orders.py       # ingest_order_board tool
|   |   |-- ingest_locations.py    # ingest_locations tool
|   |   |-- query_orders.py        # get_store_orders tool
|   |   +-- query_restrictions.py  # get_restrictions tool
|   |-- services/
|   |   |-- solver.py              # OR-Tools VRP solver
|   |   |-- constraint_engine.py   # ACI-specific constraints
|   |   |-- azure_maps.py          # Azure Maps async client
|   |   +-- cache_manager.py       # Matrix & geocode cache
|   |-- data/
|   |   |-- cosmos_client.py       # Cosmos DB connection & init
|   |   |-- location_repo.py       # locations container
|   |   |-- trailer_repo.py        # trailer_types container
|   |   |-- restriction_repo.py    # state_restrictions container
|   |   |-- order_repo.py          # order_boards container
|   |   |-- route_repo.py          # route_history container
|   |   |-- matrix_repo.py         # matrix_cache container
|   |   +-- district_repo.py       # districts container
|   |-- models/
|   |   |-- location.py            # Location Pydantic models
|   |   |-- trailer.py             # TrailerType models
|   |   |-- restriction.py         # StateRestriction models
|   |   |-- order.py               # OrderBoard models
|   |   |-- route.py               # RouteHistory models
|   |   +-- requests.py            # Tool request/response models
|   |-- resources/                 # MCP resource handlers
|   +-- prompts/                   # MCP prompt templates
|-- scripts/
|   |-- seed_data.py               # Initial data load from Excel
|   +-- provision_cosmos.sh        # Azure CLI container provisioning
|-- data/                          # Sample Excel files
|-- tests/
|   |-- test_solver.py
|   |-- test_constraint_engine.py
|   |-- test_tools.py
|   |-- test_ingest.py
|   +-- test_repos.py
|-- Dockerfile
|-- docker-compose.yml
|-- pyproject.toml
|-- .env.example
+-- README.md
```

---

*Document Version 2.0 - May 11, 2026 - Nizar El Ouarti*
