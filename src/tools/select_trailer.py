"""``select_trailer`` MCP tool (FR-002, spec §7.3)."""
from __future__ import annotations

from src.logging_config import get_logger
from src.models.requests import (
    SelectTrailerRequest,
    SelectTrailerResponse,
    TrailerRecommendation,
)
from src.server import mcp
from src.services.constraint_engine import ConstraintEngine

log = get_logger(__name__)


@mcp.tool()
async def select_trailer(req: SelectTrailerRequest) -> SelectTrailerResponse:
    """Recommend the best trailer type for a candidate route.

    Considers (a) state legality intersected across all states in the route,
    (b) cube degradation at the actual stop count, and (c) total weight.
    Returns the recommended trailer plus alternatives sorted by the
    ``prefer`` strategy.
    """
    log.info("select_trailer.start", **req.model_dump())

    # Engine loads locations only when the caller did not supply states; we
    # also need locations to derive the stop count for cube degradation.
    needs_states = not req.states
    engine = await ConstraintEngine.load(
        location_codes=req.stops if needs_states else None
    )

    if needs_states:
        derived: list[str] = []
        for code in req.stops:
            loc = engine.locations_by_code.get(code)
            if loc is None or not loc.address.state:
                continue
            if loc.address.state not in derived:
                derived.append(loc.address.state)
        states = sorted(derived)
    else:
        states = sorted(set(req.states or []))

    num_stops = max(1, len(req.stops))
    allowed_ids = engine.get_allowed_trailers(states) if states else sorted(engine.trailers.keys())

    if not allowed_ids:
        log.info("select_trailer.no_legal", states=states)
        return SelectTrailerResponse(
            recommended=None,
            alternatives=[],
            states_considered=states,
            infeasible_reason=f"No trailer type is legal in all states: {states}",
        )

    candidates: list[TrailerRecommendation] = []
    for tid in allowed_ids:
        trailer = engine.trailers.get(tid)
        if trailer is None:
            continue
        cube_limit = trailer.cube_limit_for(num_stops)
        if req.total_cubes > cube_limit:
            continue
        if req.total_weight_lbs > trailer.total_weight_max_lbs:
            continue
        cube_util = (req.total_cubes / cube_limit * 100.0) if cube_limit else 0.0
        weight_util = (
            req.total_weight_lbs / trailer.total_weight_max_lbs * 100.0
            if trailer.total_weight_max_lbs else 0.0
        )
        reason = (
            f"Legal in {','.join(states) or 'all states'}. "
            f"Cube limit at {num_stops} stops = {cube_limit}. "
            f"Weight max = {trailer.total_weight_max_lbs}."
        )
        candidates.append(
            TrailerRecommendation(
                trailer_type=tid,
                trailer_class=trailer.trailer_class,
                cube_limit=cube_limit,
                weight_max_lbs=trailer.total_weight_max_lbs,
                cube_utilization_pct=round(cube_util, 2),
                weight_utilization_pct=round(weight_util, 2),
                reason=reason,
            )
        )

    if not candidates:
        log.info("select_trailer.no_feasible", states=states, allowed=allowed_ids)
        return SelectTrailerResponse(
            recommended=None,
            alternatives=[],
            states_considered=states,
            infeasible_reason=(
                f"No legal trailer can carry weight={req.total_weight_lbs} lbs "
                f"and cubes={req.total_cubes} at {num_stops} stops."
            ),
        )

    # Sort
    if req.prefer == "max_capacity":
        # Tighter utilisation = better fit (less wasted capacity).
        candidates.sort(
            key=lambda c: -max(c.cube_utilization_pct, c.weight_utilization_pct)
        )
    else:  # min_class — prefer Single trailers, then smaller capacity
        class_rank = {"Single": 0, "Combo": 1}
        candidates.sort(
            key=lambda c: (class_rank.get(c.trailer_class, 9), c.weight_max_lbs)
        )

    recommended = candidates[0]
    log.info(
        "select_trailer.done",
        recommended=recommended.trailer_type,
        alternatives=[c.trailer_type for c in candidates[1:]],
    )
    return SelectTrailerResponse(
        recommended=recommended,
        alternatives=candidates[1:],
        states_considered=states,
    )
