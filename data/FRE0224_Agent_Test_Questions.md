# FRE0224 — Agent Test Questions
**Order Board:** `Routable Order Board2026-03-02.xlsx` · **Order Group:** `FRE0224` · **Date:** March 2, 2026  
**Source DC:** `52-DC` (SLC Distribution Center) · **Agent under test:** Routing Optimization MCP

---

## Board Summary (ground truth for verification)

| Metric | Value |
|---|---|
| Total order lines | 416 |
| Unique stores (Destinations) | 57 |
| All routed | **No** — 0 of 416 routed |
| Total weight | 985,857 lbs |
| Total cubes | 45,577 |
| Total pallets | 666.7 |
| Total cases | 65,132 |
| Districts | 7 (SLMontana, SLBoise, SLColorado, SLLocal, SLEastID, SLWyoming, SLHighline) |
| States served | MT (188 lines), ID (121), CO (51), UT (21), WY (18), OR (8), NV (8), ND (1) |

### Commodity breakdown

| Commodity | Weight (lbs) | Cubes | Pallets | Temp zone |
|---|---|---|---|---|
| PRO | 457,824 | 23,398 | 335 | ambient |
| PER | 216,367 | 6,690 | 97 | ambient |
| MEA | 186,613 | 7,110 | 102 | refrigerated |
| GM/HBC | 46,876 | 2,721 | 49 | ambient |
| FLO | 25,451 | 2,151 | 32 | floral/chilled |
| EGGS | 17,696 | 1,106 | 16 | refrigerated |
| GRO | 14,666 | 661 | 8 | ambient |
| KEHE DRY | 13,641 | 1,000 | 14 | ambient |
| PAPA | 2,428 | 382 | 6 | ambient |
| FR Fish | 2,210 | 190 | 4 | frozen |
| KEHE CHILL | 1,203 | 48 | 1 | chilled |
| MAIL | 650 | 104 | 3 | ambient |
| KEHE | 211 | 14 | 0 | ambient |
| SEA CHILL | 21 | 2 | 0 | chilled |

### District breakdown

| District | Stores | Weight | Cubes | Pallets | States |
|---|---|---|---|---|---|
| SLMontana | 25 | 393,081 | 18,472 | 270.4 | MT |
| SLBoise | 17 | 332,574 | 15,028 | 216.5 | ID, OR (store 131) |
| SLColorado | 5 | 106,603 | 5,048 | 74.2 | CO |
| SLLocal | 4 | 65,082 | 2,802 | 43.5 | UT |
| SLEastID | 2 | 62,121 | 2,950 | 43.5 | WY (183), NV (155) |
| SLWyoming | 2 | 22,738 | 1,086 | 15.6 | WY |
| SLHighline | 1 | 2,259 | 130 | 2.0 | ND |

### Notable stores

| Store | Banner | District | State | Weight | Cubes | Pal | Commodities | Note |
|---|---|---|---|---|---|---|---|---|
| 183 | Albertsons | SLEastID | WY | 41,097 | 1,939 | 28.0 | 7 | **Heaviest store** |
| 2106 | Safeway | SLMontana | MT | 30,356 | 1,512 | 21.8 | 10 | Multi-temp risk |
| 897 | Albertsons | SLColorado | CO | 27,903 | 1,425 | 20.8 | **11** | Most commodity lines |
| 130 | Albertsons | SLBoise | ID | 33,116 | 1,534 | 22.2 | 10 | Boise anchor |
| 131 | Albertsons | SLBoise | OR | 17,785 | 820 | 11.9 | 8 | Cross-state (OR) |
| 155 | Albertsons | SLEastID | NV | 21,024 | 1,011 | 15.5 | 8 | Cross-state (NV) |
| 28 | Albertsons | SLHighline | ND | 2,259 | 130 | 2.0 | 1 | Single-line solo run |
| 42 | Albertsons | SLMontana | MT | 56 | 8 | 0.2 | 2 | **Suspiciously small** |
| 1158 | Safeway | SLMontana | MT | 8,702 | 413 | 5.9 | 9 | KEHE CHILL + multi-temp |

---

## Questions to Ask the Agent

> **Convention:**  
> 🟢 Can answer from order board data + Cosmos alone (no optimization needed)  
> 🟡 Requires `optimize_route` to have been run first  
> 🔴 Requires 3+ months of historical `route_history` data

---

### Q1 — Equipment and driver constraints for a specific route 🟡

**Ask after running optimize_route for SLMontana:**

> What equipment and driver constraints apply to the SLMontana route that serves stores 2106, 1486, and 9?

**Expected answer elements:**
- Trailer type: likely `45+45` or `48+28` combo (Montana allows LCV on interstates)
- Weight check: 2106 (30,356) + 1486 (26,459) + 9 (21,309) = **78,124 lbs combined** → exceeds 70k single-trailer limit; must be split across vehicles or combo-assigned correctly
- Cube check at 3 stops: 1,512 + 1,193 + 927 = **3,632 cubes** → verify against cube degradation curve for 3-stop combo
- Temperature flag: store 2106 carries KEHE CHILL + FLO + MEA → check compartment compatibility
- MT state restriction: max combo weight 70,000 lbs; must stay on interstate corridors

---

### Q2 — Exceptions and alerts to watch for 🟡

**Ask after running optimize_route for SLMontana:**

> What exceptions or alerts should the router watch for in the SLMontana district?

**Expected answer elements:**
- **Volume anomaly:** Store `42` has only 56 lbs / 8 cubes / 2 order lines — verify this is not a data entry error before routing
- **Temperature conflict:** Store `2106` carries FLO + KEHE CHILL + MEA + FR Fish — frozen/chilled/ambient mix on one stop
- **Temperature conflict:** Store `1158` carries KEHE CHILL + KEHE DRY + 7 other commodities — multi-temp risk
- **Small-store pairing:** Stores `42`, `614` (9,925 lbs / 435 cubes), `4041` (9,890 lbs / 516 cubes) and `3269` (9,388 lbs / 455 cubes) are low-volume — route optimizer should pair them to avoid single-stop runs
- **No delivery windows** in this board — confirm with planner before releasing routes

---

### Q3 — Compare vs last week's session 🔴

**Ask after at least one prior route_history entry exists:**

> Summarize key differences between this week's FRE0224 routing session (March 2, 2026) and last week's same-commodity session.

**Expected answer elements (ground truth for validation):**
- This week: 57 stores, 985,857 lbs, 45,577 cubes, 666.7 pallets, 14 commodities
- Delta metrics should show week-over-week route count change, avg cube utilization, total miles
- Agent must query `route_history` with `order_group = "FRE0224"` and compare two most-recent sessions

---

### Q4 — Suboptimal routes (low cube, high miles) 🟡

**Ask after running optimize_route for all districts:**

> Are there any routes in FRE0224 that are suboptimal — low cube utilization or high inter-stop mileage?

**Expected answer elements:**
- **Store 42 candidate:** 56 lbs / 8 cubes — if placed on its own route, cube utilization near 0%; must be paired or questioned
- **Store 28 (ND, SLHighline):** 130 cubes, single order line — will almost certainly be a low-util solo run unless piggy-backed on a Montana combo
- **Pairing candidates:** Stores `4041` (516 cubes), `3269` (455 cubes), `614` (435 cubes) in SLMontana are all below 550 cubes — optimizer should attempt pairing; flag any 1-stop routes against these stores
- Agent should call `validate_route` on any route below 60% cube utilization

---

### Q5 — Re-optimize with +5% capacity caps 🟡

**Ask after running optimize_route for SLMontana:**

> Could SLMontana routes be improved if cube and weight constraints were relaxed by 5%? Show the impact on route count and total miles.

**Expected answer elements:**
- SLMontana total: 393,081 lbs / 18,472 cubes / 270.4 pallets across 25 stores
- At nominal 45+45 cap (~3,200 cubes, 70,000 lbs): estimated 6–8 routes
- At +5% cap (~3,360 cubes, 73,500 lbs): feasible only where MT state legal limit (70,000 lbs) is not exceeded — weight relaxation likely blocked by state law; cube relaxation may reduce route count by 1
- Agent must note MT restriction: state max takes precedence over +5% scenario for weight

---

### Q6 — Improve with relaxed delivery windows 🟢

**Ask before or after optimization:**

> This order board has no delivery windows set. What delivery curfew data is available for SLMontana stores in the locations database, and which stores have the tightest curfew windows?

**Expected answer elements:**
- Agent calls `get_store_orders` and cross-references `routing://locations/{code}` for curfew data
- Stores in MT with known early curfews (from locations data): `1158`, `20`, `24` — agent should surface these
- No `Earliest Delivery` / `Latest Delivery` values exist in this order board — agent should flag this gap and retrieve curfews from the `locations` container directly

---

### Q7 — Delay impact (warehouse or driver breakdown) 🟡

**Ask after running optimize_route for SLMontana:**

> A SLMontana trip carrying stores 2106 and 1486 departs 2 hours late due to a warehouse loading delay. What is the on-time impact and can we proactively communicate?

**Expected answer elements:**
- Combined weight 2106+1486 = 56,815 lbs; likely a combo (45+45 or 48+28) assigned to MT
- 2-hour departure shift: agent should propagate ETAs through each stop's curfew window
- Pre-generate notifications for each impacted store with updated ETA vs. planned ETA
- Agent should call `validate_route` on the shifted schedule and flag any curfew violations

---

### Q8 — Store-order splits 🟡

**Ask after running optimize_route for all districts:**

> How many store-order splits occurred in FRE0224, and why?

**Expected answer elements (pre-computed from order board):**

**High split-risk stores by commodity count + weight:**

| Store | District | Weight (lbs) | Cubes | Commodities | Split risk |
|---|---|---|---|---|---|
| 897 | SLColorado | 27,903 | 1,425 | 11 | High — mixed KEHE CHILL + FLO + ambient |
| 2106 | SLMontana | 30,356 | 1,512 | 10 | High — KEHE CHILL + FLO + MEA + FR Fish |
| 130 | SLBoise | 33,116 | 1,534 | 10 | Medium — verify temp zones |
| 183 | SLEastID | 41,097 | 1,939 | 7 | Low for split — but heaviest single store; WY weight limit 70k |
| 1131 | SLColorado | 19,394 | 875 | 11 | High — KEHE CHILL + DRY + multi-temp |

- Primary split reason expected: temperature-zone incompatibility (FLO/frozen + ambient)
- Secondary: cube degradation limit exceeded at assigned stop count
- Agent should surface `cube_utilization` per route and `temp_zone_conflict` flag

---

### Q9 — Routes in danger of missing delivery windows 🟡

**Ask after running optimize_route (requires curfew data from locations container):**

> Which FRE0224 routes are at risk of missing delivery windows based on estimated travel times from 52-DC?

**Expected answer elements:**
- This board has no explicit windows — agent must retrieve curfew data from `locations` container
- SLMontana has the longest haul legs: expected 3–6h travel time to Billings/Great Falls area
- Stores `1158`, `20`, and `24` in SLMontana are historically tight-window (surfaced from locations data)
- Agent should call `matrix_travel_times` for the SLMontana lane and compare ETAs against location curfews

---

### Q10 — Weather event: remove store and re-optimize 🟡

**Ask after running optimize_route for SLMontana:**

> A winter storm closes the Store 259 (Safeway, Billings MT) area tomorrow. Remove Store 259 from its current SLMontana trip and re-optimize the remaining stops on that route. What is the cost impact?

**Expected answer elements:**
- Store 259: 18,361 lbs / 877 cubes / 12.7 pallets / 9 commodities — significant volume
- Removing 259 frees ~877 cubes on its assigned trip
- Re-optimization: check if remaining stops can be merged with an adjacent trip (e.g., stores 1227, 4022, or 3367 are nearby and low-volume)
- Deferred order: 259's 416 lbs of KEHE DRY + 49 lbs KEHE CHILL moved to next planning cycle
- Agent should call `optimize_route` with `excluded_locations: ["259"]` and report delta miles

---

### Q11 — Hot load: force first stop 🟡

**Ask after running optimize_route for SLLocal:**

> Store 1509 (Lucky, Salt Lake City UT) has a high-priority perishable order (MEA: 9,219 lbs + PER: 7,217 lbs) that must be the first retail stop. Re-optimize the SLLocal sequence with Store 1509 as the forced first stop.

**Expected answer elements:**
- SLLocal stores: 1509 (23,123 lbs), 1708 (14,830 lbs), 3197 (14,033 lbs), 339 (13,096 lbs) — total 65,082 lbs / 2,802 cubes
- SLLocal is UT-only — state restriction: singles max 42k lbs, combos max 70k lbs
- Forcing 1509 first: verify departure from 52-DC still satisfies store curfew
- Feasibility check: remaining 3 stops (41,959 lbs) within single-trailer or combo capacity
- Agent must call `validate_route` with `priority_stops: ["1509"]`

---

### Q12 — Insufficient doubles: prioritize single conversions 🟡

**Ask after running optimize_route for SLMontana:**

> We have one fewer 45+45 combo set available for SLMontana tonight. Which SLMontana route is the best candidate to convert to a 53ft single, and what is the cost increase?

**Expected answer elements:**
- SLMontana total: 270.4 pallets — requires multiple runs; combos save total route count
- Stores most suitable for single-trailer conversion (lower weight, fewer stops):
  - Group: 42 (8 cubes) + 614 (435) + 4041 (516) = 959 cubes / 19,871 lbs — fits a 53ft single
  - Group: 3269 (455) + 3367 (708) = 1,163 cubes / 24,999 lbs — fits a 53ft single
- Downgrade penalty: +extra route or +miles; agent must call `select_trailer` with `max_trailer_class: "Single"` for candidate trips
- MT restriction: single max weight varies by trailer type; agent must validate against `get_restrictions("MT")`

---

### Q13 — Suggest delivery windows from history 🔴

**Ask after 3+ months of route_history data exists:**

> Using the last 3 months of FRE0224 routing history, which SLMontana stores repeatedly force high-cost early arrivals, and what delivery windows would minimize total route miles?

**Expected answer elements:**
- Historically tight stores expected: `1158`, `20`, `24` (based on location data)
- Agent must query `route_history` with `dc_code = "52-DC"` and `order_group = "FRE0224"`, group by store, analyze avg ETA vs curfew_open
- Savings modeled by widening windows 2h → express as % mile reduction

---

### Q14 — Low-pallet stores: reduce delivery frequency 🔴

**Ask after 3+ months of history:**

> Using 3 months of FRE0224 history, find SLMontana stores averaging fewer than 5 pallets per delivery per temperature zone, and suggest reduced delivery frequency (minimum 2x/week per zone).

**Expected answer elements (current board snapshot):**

| Store | Pallets this run | Commodities | Likely low-pallet candidate? |
|---|---|---|---|
| 42 | 0.2 | 2 (MAIL+PAPA) | **Yes** — 0.2 pallets is critically low |
| 614 | 6.5 | 10 | Borderline |
| 4041 | 7.5 | 6 | Borderline |
| 3269 | 6.6 | 7 | Borderline |
| 1158 | 5.9 | 9 | Borderline — check chilled zone separately |

- Store 42 is the most obvious candidate — 2 lines (MAIL 25 lbs + PAPA 31 lbs) — should be aggregated or moved to a weekly mail run
- Agent queries route_history for pallet-per-delivery averages, grouped by temp zone

---

### Q15 — Overhang pallet patterns 🔴

**Ask after 3+ months of history:**

> Using 3 months of FRE0224 history, identify overhang pallet patterns — specifically for PRO and PER commodities in SLMontana and SLBoise — and suggest model improvements.

**Expected answer elements (current board context):**
- SLMontana PRO: 188,159 lbs / SLBoise PRO: 146,250 lbs — PRO is the dominant commodity in both districts
- SLMontana PER: 98,769 lbs — second largest; high cube density relative to weight
- Agent must surface any routes where PRO + PER combined exceed cube-degradation limit at planned stop count
- Suggested check: call `validate_route` for any trip where PRO + PER share a trailer with perishable-sensitive commodities (KEHE CHILL, FLO)

---

### Q16 — LCV combo more than 2 miles off interstate 🟡

**Ask after running optimize_route for SLMontana or SLBoise:**

> Do any SLMontana or SLBoise routes assigned a combo trailer (45+45, 48+28, or 40+40) travel more than 2 miles off the interstate to reach their delivery stores?

**Expected answer elements:**
- SLMontana stores most likely off-interstate: `614`, `4041`, `3269`, `4008` — smaller-volume stores in rural MT
- SLBoise: Store `131` is in Oregon — verify OR combo restrictions (OR restricts doubles on certain highways)
- SLEastID: Store `155` (NV) — verify NV combo rules; Store `183` (WY) — WY allows doubles on interstates
- Agent calls `get_restrictions` for MT, OR, NV and `validate_route` with `check_interstate_proximity: true`
- Any violation: agent must re-route to legal alternative or downgrade trailer type

---

### Q17 — Driver layover required 🟡

**Ask after running optimize_route for SLMontana:**

> Do any SLMontana routes require a driver layover based on projected duty time including drive time, service time, and HOS breaks?

**Expected answer elements:**
- SLMontana longest haul candidates: stores in Billings MT area (2106, 1486, 9, 35, 4040) — ~450 miles from SLC
- Drive time SLC → Billings: ~6.5h one-way + service time per stop (~30 min avg) → 3-stop Montana trip easily exceeds 10h
- Stores 2106+1486+9: total 71,724 lbs — heavy combo load, service time per stop likely 45–60 min
- Agent should flag any trip where `total_time = drive_time + (service_time × stops) + breaks > 11h`

---

### Q18 — Routes that benefit from relay vs single-driver 🟡

**Ask after running optimize_route for SLMontana:**

> Would any SLMontana routes benefit from a relay arrangement versus a single-driver leg from 52-DC?

**Expected answer elements:**
- Relay benefit is highest on longest Montana runs (Billings, Great Falls area)
- Relay candidates: any route where total projected duty time exceeds 10h — likely stores 2106+1486 (Billings cluster, ~6.5h drive one-way)
- Benefit: first retail ETA improves by 30–60 min if relay driver meets trailer partway
- Cost tradeoff: relay handling at relay point vs. driver overtime cost
- Agent should call `directions` for longest SLMontana legs and project duty time

---

### Q19 — Routes that benefit from straight-leg vs relay 🟡

**Ask after running optimize_route for SLLocal and SLEastID:**

> Would any SLLocal or SLEastID routes benefit from staying straight-leg rather than relay?

**Expected answer elements:**
- SLLocal: 4 stores, all UT, total 65,082 lbs / 2,802 cubes — short haul; relay unnecessary; straight-leg always optimal
- SLEastID: Store 183 (WY, 41,097 lbs) + Store 155 (NV, 21,024 lbs) — combined 62,121 lbs; these are in different states; likely 2 separate trips or one heavy relay
- Agent should note that straight-leg is preferred for SLLocal to avoid handoff overhead on a local UT run

---

### Q20 — Additional LCV set availability impact 🟡

**Ask after running optimize_route for SLMontana:**

> Would one additional 45+45 combo set in the SLMontana wave reduce total route expense? Estimate impact on route count and total miles.

**Expected answer elements:**
- SLMontana: 25 stores, 393,081 lbs, 18,472 cubes, 270.4 pallets
- One additional 45+45 set (~3,200 cubes, 70,000 lbs) could absorb 1 extra route worth of volume
- Expected impact: route count −1, total miles −3% to −6% (estimate based on Montana geography)
- Highest benefit: Mon/Fri when produce (PRO: 188,159 lbs) and perishables (PER: 98,769 lbs) are heaviest
- Agent calls `optimize_route` with `available_vehicles` bumped by 1 and compares objective value delta

---

### Q21 — Snow event: lock to 53ft single, show cost impact 🟡

**Ask after running optimize_route for SLMontana:**

> A winter storm in central Montana forces all SLMontana routes to use only 53ft single trailers until tomorrow. Re-optimize using only singles and show the cost and route-count impact.

**Expected answer elements:**
- SLMontana 270.4 pallets / 393,081 lbs on singles only (~26 pal / ~42,000 lbs per 53ft UT single)
- Estimated route increase: from ~7–8 combo routes to ~12–15 single routes (+4 to +7 routes)
- MT state restriction: single-trailer weight limit varies — agent must call `get_restrictions("MT")` first
- No state-restriction violations if weight per truck stays under MT single limit
- Agent calls `optimize_route` with `trailer_type_filter: ["53'"]` and reports:  
  - New route count  
  - Total miles delta  
  - Any stores that still can't be served (weight too high for single)

---

## Pre-Flight Verification Questions

These should be asked **before** starting any optimization to validate data quality:

### PF-1 — Verify all 57 stores have geocoordinates 🟢

> Are all 57 stores in FRE0224 (order group `FRE0224`) present in the locations database with valid latitude/longitude coordinates?

Expected: agent calls `get_store_orders` and cross-checks each `Destination` against the `locations` container.  
Flag if any store is missing.

---

### PF-2 — Flag Store 42 volume anomaly 🟢

> Store 42 in SLMontana has only 2 order lines totaling 56 lbs and 8 cubes (MAIL + PAPA JOHNS). Is this a valid delivery order or a data entry error?

Expected: agent retrieves store 42 from `locations` and confirms it is an active Albertsons in MT, then flags for planner confirmation before routing.

---

### PF-3 — Confirm no delivery windows 🟢

> The FRE0224 order board has no `Earliest Delivery` or `Latest Delivery` values set. Does the locations database have delivery curfew data for all 57 stores? List any stores with missing curfew data.

Expected: agent queries `locations` container for `curfew_open` and `curfew_close` for all 57 destination codes.

---

### PF-4 — Cross-state trailer legality check 🟢

> Before routing, confirm what trailer types are legal for each state in FRE0224: MT, ID, CO, UT, WY, OR, NV, ND.

Expected: agent calls `get_restrictions` for each state and returns a table of allowed combos and weight limits.  
Key known restrictions:
- UT: combo max 70,000 lbs (from seeded data)
- OR: verify doubles restriction for Store 131
- NV: verify for Store 155
- ND: Store 28 only — 1 line, 2,259 lbs; likely single-trailer mandatory

---

### PF-5 — SLHighline viability 🟢

> Store 28 (Albertsons, ND) in SLHighline has 1 order line: 2,259 lbs / 130 cubes / GM/HBC only. Is a solo run to North Dakota cost-effective? What is the estimated drive time and distance from 52-DC?

Expected: agent calls `matrix_travel_times` with `["52-DC", "28"]` and `directions` for turn-by-turn, then flags the empty-backhaul cost to the planner for a go/no-go decision.

---

*Generated from `Routable Order Board2026-03-02.xlsx` on 2026-05-19.*  
*Use with the Routing Optimization MCP at `https://ca-rt-vqcz36euruiko.proudglacier-ba160324.eastus2.azurecontainerapps.io/`*
