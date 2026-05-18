"""Curfew window helpers.

In the customer data a curfew is a **do-not-deliver** window
(e.g. 22:00–07:00 means "deliveries are not allowed between 22:00 and 07:00").
The solver wants **allowed-delivery** windows.  This module converts between
the two formats and correctly handles windows that span midnight.

Times are expressed as seconds since 00:00 UTC of a synthetic 24-hour day
(``0 <= t < 86400``).
"""
from __future__ import annotations

from src.models.location import Curfew

SECONDS_PER_DAY = 24 * 60 * 60  # 86_400


def parse_hhmm(hhmm: str | None) -> int | None:
    """Parse ``"HH:MM"`` (24h) into seconds since 00:00.  Returns ``None`` on bad input."""
    if not hhmm:
        return None
    try:
        h_str, m_str = hhmm.split(":", 1)
        h = int(h_str)
        m = int(m_str)
    except (ValueError, AttributeError):
        return None
    if not (0 <= h <= 24 and 0 <= m <= 59):
        return None
    secs = h * 3600 + m * 60
    # Accept "24:00" as end-of-day.
    if secs > SECONDS_PER_DAY:
        return None
    return secs


def to_delivery_windows(curfew: Curfew | None) -> list[tuple[int, int]]:
    """Convert a do-not-deliver curfew into a list of allowed delivery windows.

    Returns at most two ``(start_sec, end_sec)`` tuples with
    ``0 <= start < end <= 86400``.

    Semantics:
      * No curfew (or unparseable) → ``[(0, 86400)]`` (full day allowed)
      * Same-day curfew ``08:00–17:00`` →
        ``[(0, 28800), (61200, 86400)]`` (before and after the curfew)
      * Overnight curfew ``22:00–07:00`` (start > end) →
        ``[(25200, 79200)]`` (single allowed window 07:00–22:00)
      * Degenerate ``00:00–00:00`` → full day allowed
      * Degenerate ``00:00–24:00`` (or ``24:00–24:00``) → no deliveries possible → ``[]``
    """
    if curfew is None:
        return [(0, SECONDS_PER_DAY)]

    start = parse_hhmm(curfew.start)
    end = parse_hhmm(curfew.end)

    # Missing fields = no curfew enforced.
    if start is None or end is None:
        return [(0, SECONDS_PER_DAY)]

    # 00:00–00:00 means "no curfew applies" by convention.
    if start == end == 0:
        return [(0, SECONDS_PER_DAY)]

    # Full-day curfew → nothing allowed.
    if start == 0 and end >= SECONDS_PER_DAY:
        return []
    if start == end:
        # Empty curfew = full day allowed.
        return [(0, SECONDS_PER_DAY)]

    if end > start:
        # Same-day do-not-deliver window: allowed = [00:00, start) ∪ (end, 24:00).
        windows: list[tuple[int, int]] = []
        if start > 0:
            windows.append((0, start))
        if end < SECONDS_PER_DAY:
            windows.append((end, SECONDS_PER_DAY))
        return windows

    # Overnight do-not-deliver (start > end), e.g. 22:00–07:00.
    # Allowed window is the gap in the middle: [end, start).
    return [(end, start)]


def primary_window(curfew: Curfew | None) -> tuple[int | None, int | None]:
    """Return the first allowed-delivery window suitable for the OR-Tools Time dimension.

    The solver dimension only supports one contiguous window per stop; when a
    curfew produces two same-day windows we pass the **larger** one (more
    flexibility for the solver) and rely on post-solve compliance for the rest.

    Returns ``(None, None)`` when the location has no curfew (full day).
    """
    windows = to_delivery_windows(curfew)
    if not windows:
        # Fully blocked — return a 1-second zero-length window centred at noon
        # so the solver flags it as infeasible deterministically.
        return (12 * 3600, 12 * 3600 + 1)
    if len(windows) == 1 and windows[0] == (0, SECONDS_PER_DAY):
        return (None, None)
    # Pick the widest window.
    widest = max(windows, key=lambda w: w[1] - w[0])
    return widest
