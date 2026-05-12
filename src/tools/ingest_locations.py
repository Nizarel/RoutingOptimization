"""``ingest_locations`` MCP tool.

Parses the SLC Restrictions & Locations workbook and upserts:
- ``locations``         (~583 rows, 1:1)
- ``trailer_types``     (22 rows, 1:1 with cube_by_stops embedded)
- ``state_restrictions`` (57 rows, 1:1)
- ``districts``          (derived from Locations)

Header matching is fuzzy (see :mod:`src.tools._excel`).
"""
from __future__ import annotations

from typing import Any

import pandas as pd

from src.data.district_repo import DistrictRepo
from src.data.location_repo import LocationRepo
from src.data.restriction_repo import RestrictionRepo
from src.data.trailer_repo import TrailerRepo
from src.logging_config import get_logger
from src.models.location import Address, Curfew, GeoPoint, Location
from src.models.matrix import District
from src.models.requests import IngestLocationsRequest, IngestLocationsResponse
from src.models.restriction import StateRestriction
from src.models.trailer import TrailerType
from src.server import mcp
from src.tools._excel import pick, read_sheet, to_bool, to_float, to_int, to_str

log = get_logger(__name__)


# --- Locations sheet ---------------------------------------------------------

def _row_to_location(row: dict[str, Any]) -> Location | None:
    code = to_str(pick(row, "location_code", "loc_code", "code"))
    if code is None:
        return None
    lat = to_float(pick(row, "lat", "latitude"), default=float("nan"))
    lon = to_float(pick(row, "lon", "lng", "long", "longitude"), default=float("nan"))
    if pd.isna(lat) or pd.isna(lon):
        return None

    location_type = to_str(pick(row, "location_type", "type"), default="Unknown") or "Unknown"

    return Location(
        id=code,
        location_code=code,
        location_type=location_type,  # type: ignore[arg-type]
        description=to_str(pick(row, "description", "name", "banner")),
        address=Address(
            street=to_str(pick(row, "street", "address", "address_line_1")),
            city=to_str(pick(row, "city")),
            state=to_str(pick(row, "state", "st")),
            postal=to_str(pick(row, "postal", "postal_code", "zip", "zip_code")),
            phone=to_str(pick(row, "phone", "phone_number")),
        ),
        coordinates=GeoPoint(coordinates=[lon, lat]),
        lat=lat,
        lon=lon,
        district_handle=to_str(pick(row, "district_handle", "district")),
        district_description=to_str(pick(row, "district_description", "district_desc")),
        curfew=Curfew(
            start=to_str(pick(row, "curfew_start", "curfew_open")),
            end=to_str(pick(row, "curfew_end", "curfew_close")),
        ),
        bh_loc_code=to_str(pick(row, "bh_loc_code", "backhaul_code")),
        obc_loc_code=to_str(pick(row, "obc_loc_code", "obc_code")),
        is_enabled=to_bool(pick(row, "is_enabled", "enabled"), default=True),
    )


# --- Trailer sheet -----------------------------------------------------------

_CUBE_HEADER_RE_PARTS = ("cube", "stop")


def _row_to_trailer(row: dict[str, Any]) -> TrailerType | None:
    desc = to_str(pick(row, "trailer_type_description", "trailer_type", "description"))
    if desc is None:
        return None
    trailer_class = to_str(pick(row, "trailer_class", "class"), default="Single") or "Single"
    if trailer_class not in ("Combo", "Single"):
        trailer_class = "Combo" if "+" in desc else "Single"

    # Cube columns are like "cube_1_stop", "cube_2_stops", ... — collect & sort by stop count.
    cube_pairs: list[tuple[int, int]] = []
    for k, v in row.items():
        if not all(part in k for part in _CUBE_HEADER_RE_PARTS):
            continue
        digits = "".join(ch for ch in k if ch.isdigit())
        if not digits:
            continue
        cube_pairs.append((int(digits), to_int(v)))
    cube_pairs.sort(key=lambda t: t[0])
    cube_by_stops = [c for _, c in cube_pairs if c > 0]
    if not cube_by_stops:
        # Fallback: a single max_cubes column
        max_cubes = to_int(pick(row, "max_cubes", "cubes_max", "cube_max"))
        if max_cubes:
            cube_by_stops = [max_cubes]
        else:
            return None

    safe_id = desc.replace("'", "ft").replace(" ", "")

    return TrailerType(
        id=safe_id,
        trailer_class=trailer_class,  # type: ignore[arg-type]
        trailer_type_description=desc,
        dollies=to_int(pick(row, "dollies"), default=2 if trailer_class == "Combo" else 0),
        lead_weight_max_lbs=to_int(pick(row, "lead_weight_max_lbs", "lead_weight_max", "lead_max_lbs")),
        pup_weight_max_lbs=to_int(pick(row, "pup_weight_max_lbs", "pup_weight_max", "pup_max_lbs")),
        total_weight_max_lbs=to_int(pick(row, "total_weight_max_lbs", "total_weight_max", "max_weight_lbs")),
        cube_by_stops=cube_by_stops,
        max_stops_supported=len(cube_by_stops),
    )


# --- State restriction sheet -------------------------------------------------

def _row_to_restriction(row: dict[str, Any]) -> StateRestriction | None:
    state = to_str(pick(row, "state", "st"))
    trailer_type = to_str(pick(row, "trailer_type", "combo", "trailer"))
    if not state or not trailer_type:
        return None
    trailer_class = to_str(pick(row, "trailer_class", "class"))
    if trailer_class not in ("Combo", "Single"):
        trailer_class = "Combo" if "+" in trailer_type else "Single"
    return StateRestriction(
        id=f"{state}_{trailer_type}",
        state=state,
        trailer_type=trailer_type,
        trailer_class=trailer_class,  # type: ignore[arg-type]
        max_weight_lbs=to_int(pick(row, "max_weight_lbs", "max_weight", "weight_lbs")),
        within_2mi_interstate_only=to_bool(
            pick(row, "within_2mi_interstate_only", "interstate_only"), default=False
        ),
        max_distance_from_interstate_mi=to_float(
            pick(row, "max_distance_from_interstate_mi", "max_distance_mi"), default=0.0
        ) or None,
        notes=to_str(pick(row, "notes", "comment")),
    )


# --- District derivation -----------------------------------------------------

def _derive_districts(locations: list[Location], dc_code: str) -> list[District]:
    by_handle: dict[str, list[Location]] = {}
    for loc in locations:
        if loc.location_type != "Mileage Store" or not loc.district_handle:
            continue
        by_handle.setdefault(loc.district_handle, []).append(loc)

    districts: list[District] = []
    for handle, stores in by_handle.items():
        states = sorted({loc.address.state for loc in stores if loc.address.state})
        banners = sorted({loc.description for loc in stores if loc.description})
        districts.append(
            District(
                id=handle,
                dc_code=dc_code,
                district_handle=handle,
                description=stores[0].district_description or handle,
                states=states,
                store_count=len(stores),
                store_codes=sorted(loc.location_code for loc in stores),
                banners=banners,
            )
        )
    return districts


# --- Tool entry point --------------------------------------------------------

@mcp.tool()
async def ingest_locations(req: IngestLocationsRequest) -> IngestLocationsResponse:
    """Parse the SLC Restrictions & Locations workbook and upsert master data into Cosmos DB.

    Populates four containers: ``locations``, ``trailer_types``, ``state_restrictions``,
    and ``districts``. Header matching is fuzzy (whitespace/case/punctuation insensitive).
    """
    log.info("ingest_locations.start", file=req.file_path)

    loc_df = read_sheet(req.file_path, req.locations_sheet)
    locations = [m for r in loc_df.to_dict(orient="records") if (m := _row_to_location(r))]

    trailer_df = read_sheet(req.file_path, req.trailer_sheet)
    trailers = [m for r in trailer_df.to_dict(orient="records") if (m := _row_to_trailer(r))]

    rest_df = read_sheet(req.file_path, req.restriction_sheet)
    restrictions = [m for r in rest_df.to_dict(orient="records") if (m := _row_to_restriction(r))]

    from src.config import get_settings
    dc_code = get_settings().default_dc_code
    districts = _derive_districts(locations, dc_code)

    n_loc = await LocationRepo().bulk_upsert(locations)
    n_trail = await TrailerRepo().bulk_upsert(trailers)
    n_rest = await RestrictionRepo().bulk_upsert(restrictions)
    n_dist = await DistrictRepo().bulk_upsert(districts)

    log.info(
        "ingest_locations.done",
        locations=n_loc,
        trailers=n_trail,
        restrictions=n_rest,
        districts=n_dist,
    )
    return IngestLocationsResponse(
        locations_loaded=n_loc,
        trailer_types_loaded=n_trail,
        state_restrictions_loaded=n_rest,
        districts_derived=n_dist,
    )
