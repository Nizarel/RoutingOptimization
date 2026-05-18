"""Constraint Engine (spec §6.3, §9).

Encapsulates Albertsons-specific routing rules:
  * Cube degradation by number of stops (trailer table)
  * Allowed trailer types per state (intersection of state_restrictions)
  * Lead/pup weight split for Combo trailers
  * MT interstate-proximity rule for 40+40 trailers
  * Curfew → allowed-delivery windows

Core methods are **synchronous** for fast unit testing.  The
:meth:`ConstraintEngine.load` async factory is responsible for the one-time
bulk load of trailers / restrictions / locations from Cosmos.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from src.data.location_repo import LocationRepo
from src.data.restriction_repo import RestrictionRepo
from src.data.trailer_repo import TrailerRepo
from src.logging_config import get_logger
from src.models.location import Location
from src.models.restriction import StateRestriction
from src.models.route import ComplianceReport, VehicleRoute
from src.models.trailer import TrailerType
from src.services.curfew import to_delivery_windows

log = get_logger(__name__)

_MT_INTERSTATE_PATH = Path(__file__).parent / "data" / "mt_interstate.json"
_EARTH_RADIUS_MI = 3958.7613


# ── Helpers ───────────────────────────────────────────────────────────────────

def _haversine_mi(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * _EARTH_RADIUS_MI * math.asin(math.sqrt(a))


def _point_to_segment_mi(
    lat: float, lon: float,
    lat_a: float, lon_a: float,
    lat_b: float, lon_b: float,
) -> float:
    """Approximate distance from (lat,lon) to segment AB in miles.

    Uses an equirectangular projection — adequate at MT latitudes for a
    ≤2-mile compliance test on segments of ~10–20 miles.
    """
    # Project to a local flat plane centred at A.
    lat0 = math.radians((lat_a + lat_b) / 2)
    mi_per_deg_lat = 69.0
    mi_per_deg_lon = 69.0 * math.cos(lat0)

    ax, ay = 0.0, 0.0
    bx = (lon_b - lon_a) * mi_per_deg_lon
    by = (lat_b - lat_a) * mi_per_deg_lat
    px = (lon - lon_a) * mi_per_deg_lon
    py = (lat - lat_a) * mi_per_deg_lat

    dx, dy = bx - ax, by - ay
    seg_len_sq = dx * dx + dy * dy
    if seg_len_sq < 1e-9:
        return math.hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, (px * dx + py * dy) / seg_len_sq))
    cx, cy = ax + t * dx, ay + t * dy
    return math.hypot(px - cx, py - cy)


def _load_mt_interstate_segments() -> list[tuple[float, float, float, float]]:
    """Return list of (lat_a, lon_a, lat_b, lon_b) segments for MT interstates."""
    data = json.loads(_MT_INTERSTATE_PATH.read_text(encoding="utf-8"))
    segments: list[tuple[float, float, float, float]] = []
    for line in data["lines"]:
        wps = line["waypoints"]
        for i in range(len(wps) - 1):
            la, lo = wps[i]
            lb, lon_b = wps[i + 1]
            segments.append((la, lo, lb, lon_b))
    return segments


# ── Engine ────────────────────────────────────────────────────────────────────

@dataclass(slots=True)
class ConstraintEngine:
    """Stateless rule lookups over pre-loaded reference data."""

    trailers: dict[str, TrailerType]
    restrictions_by_state: dict[str, list[StateRestriction]]
    locations_by_code: dict[str, Location]
    mt_interstate_segments: list[tuple[float, float, float, float]] = field(default_factory=list)

    # ── Factory ───────────────────────────────────────────────────────────────

    @classmethod
    async def load(cls, *, location_codes: list[str] | None = None) -> "ConstraintEngine":
        """Bulk-load reference data from Cosmos.

        ``location_codes``: restrict location lookup to this subset.  When
        ``None``, no locations are loaded (engine methods that need them will
        raise ``KeyError``).
        """
        trailer_repo = TrailerRepo()
        restr_repo = RestrictionRepo()
        loc_repo = LocationRepo()

        trailers_list = await trailer_repo.list_all()
        trailers = {t.id: t for t in trailers_list}

        # All known states across restrictions; load each partition.
        # Cheaper than a cross-partition query for the ~50-state universe.
        all_restr = await restr_repo.query("SELECT * FROM c")
        by_state: dict[str, list[StateRestriction]] = {}
        for r in all_restr:
            by_state.setdefault(r.state, []).append(r)

        locs: dict[str, Location] = {}
        if location_codes:
            loc_list = await loc_repo.get_many_by_codes(list(set(location_codes)))
            locs = {loc.location_code: loc for loc in loc_list}

        segments = _load_mt_interstate_segments()
        log.info(
            "constraint_engine.loaded",
            trailers=len(trailers),
            states=len(by_state),
            locations=len(locs),
            mt_segments=len(segments),
        )
        return cls(
            trailers=trailers,
            restrictions_by_state=by_state,
            locations_by_code=locs,
            mt_interstate_segments=segments,
        )

    # ── Core lookups (spec §6.3) ──────────────────────────────────────────────

    def get_cube_limit(self, trailer_id: str, num_stops: int) -> int:
        trailer = self.trailers.get(trailer_id)
        if trailer is None:
            raise KeyError(f"Unknown trailer type: {trailer_id}")
        return trailer.cube_limit_for(num_stops)

    def get_allowed_trailers(self, states: list[str]) -> list[str]:
        """Return trailer IDs legal in **every** state in ``states``.

        A trailer is "legal in a state" iff a `StateRestriction` exists for
        that ``(state, trailer_type)`` pair.  Empty ``states`` → all trailers.
        """
        if not states:
            return sorted(self.trailers.keys())
        sets: list[set[str]] = []
        for st in states:
            rs = self.restrictions_by_state.get(st, [])
            sets.append({r.trailer_type for r in rs})
        if not sets:
            return []
        legal = set.intersection(*sets)
        return sorted(legal)

    def get_restriction(self, state: str, trailer_id: str) -> StateRestriction | None:
        for r in self.restrictions_by_state.get(state, []):
            if r.trailer_type == trailer_id:
                return r
        return None

    def check_weight_split(self, trailer_id: str, lead_lbs: int, pup_lbs: int) -> bool:
        trailer = self.trailers.get(trailer_id)
        if trailer is None:
            return False
        total = lead_lbs + pup_lbs
        if total > trailer.total_weight_max_lbs:
            return False
        if trailer.trailer_class == "Single":
            return pup_lbs == 0 and lead_lbs <= trailer.total_weight_max_lbs
        # Combo
        return (
            lead_lbs <= trailer.lead_weight_max_lbs
            and pup_lbs <= trailer.pup_weight_max_lbs
        )

    def check_interstate_proximity(
        self, trailer_id: str, state: str, lat: float, lon: float
    ) -> bool:
        """True if the stop is OK under the interstate-proximity rule.

        Only enforces a check when a matching restriction has
        ``within_2mi_interstate_only == True`` (currently MT-specific data).
        For Sprint 4, only the MT corridor is loaded; other states without
        proximity rules always pass.
        """
        restriction = self.get_restriction(state, trailer_id)
        if restriction is None or not restriction.within_2mi_interstate_only:
            return True
        max_mi = restriction.max_distance_from_interstate_mi or 2.0
        if state != "MT" or not self.mt_interstate_segments:
            # No corridor data for this state — fail closed (conservative).
            return False
        for la, lo, lb, lon_b in self.mt_interstate_segments:
            if _point_to_segment_mi(lat, lon, la, lo, lb, lon_b) <= max_mi:
                return True
        return False

    def get_curfew_window(self, location_code: str) -> list[tuple[int, int]]:
        loc = self.locations_by_code.get(location_code)
        if loc is None:
            return [(0, 24 * 3600)]
        return to_delivery_windows(loc.curfew)

    # ── Aggregate evaluation ──────────────────────────────────────────────────

    def evaluate_route(
        self, route: VehicleRoute, *, ignore_depot_codes: set[str] | None = None
    ) -> ComplianceReport:
        """Build a ComplianceReport for a single solved VehicleRoute.

        Stops not present in ``locations_by_code`` (e.g. depot codes that were
        not requested) are skipped silently.
        """
        ignore = ignore_depot_codes or set()
        state_v: list[str] = []
        interstate_v: list[str] = []
        cube_v: list[str] = []
        weight_v = 0

        trailer = self.trailers.get(route.trailer_type)
        # Cube check
        if trailer is not None:
            cube_limit = trailer.cube_limit_for(route.stop_count or 1)
            if route.cubes > cube_limit:
                cube_v.append(
                    f"vehicle={route.vehicle} cubes={route.cubes:.0f} > limit={cube_limit}"
                )
            if route.weight_lbs > trailer.total_weight_max_lbs:
                weight_v += 1

        # State + interstate proximity per stop
        for code in route.stops:
            if code in ignore:
                continue
            loc = self.locations_by_code.get(code)
            if loc is None or not loc.address.state:
                continue
            state = loc.address.state
            if self.get_restriction(state, route.trailer_type) is None:
                state_v.append(f"vehicle={route.vehicle} stop={code} state={state} not allowed")
                continue
            if not self.check_interstate_proximity(route.trailer_type, state, loc.lat, loc.lon):
                interstate_v.append(
                    f"vehicle={route.vehicle} stop={code} state={state} not within proximity"
                )

        return ComplianceReport(
            state_restrictions_passed=(not state_v and not interstate_v),
            curfew_violations=0,
            weight_violations=weight_v,
            state_violations=state_v,
            interstate_violations=interstate_v,
            cube_violations=cube_v,
            evaluated_at=datetime.now(UTC),
            status="evaluated",
        )

    @staticmethod
    def merge_compliance(reports: list[ComplianceReport]) -> ComplianceReport:
        if not reports:
            return ComplianceReport(status="not_evaluated")
        state_v: list[str] = []
        interstate_v: list[str] = []
        cube_v: list[str] = []
        weight_v = 0
        for r in reports:
            state_v.extend(r.state_violations)
            interstate_v.extend(r.interstate_violations)
            cube_v.extend(r.cube_violations)
            weight_v += r.weight_violations or 0
        return ComplianceReport(
            state_restrictions_passed=(not state_v and not interstate_v),
            curfew_violations=0,
            weight_violations=weight_v,
            state_violations=state_v,
            interstate_violations=interstate_v,
            cube_violations=cube_v,
            evaluated_at=datetime.now(UTC),
            status="evaluated",
        )
