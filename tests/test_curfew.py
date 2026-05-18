"""Unit tests for curfew → allowed-delivery-window conversion."""
from __future__ import annotations

from src.models.location import Curfew
from src.services.curfew import (
    SECONDS_PER_DAY,
    parse_hhmm,
    primary_window,
    to_delivery_windows,
)


def test_parse_hhmm_valid():
    assert parse_hhmm("00:00") == 0
    assert parse_hhmm("07:30") == 7 * 3600 + 30 * 60
    assert parse_hhmm("23:59") == 23 * 3600 + 59 * 60
    assert parse_hhmm("24:00") == SECONDS_PER_DAY


def test_parse_hhmm_invalid():
    assert parse_hhmm(None) is None
    assert parse_hhmm("") is None
    assert parse_hhmm("garbage") is None
    assert parse_hhmm("25:00") is None
    assert parse_hhmm("12:99") is None


def test_no_curfew_full_day():
    assert to_delivery_windows(None) == [(0, SECONDS_PER_DAY)]
    assert to_delivery_windows(Curfew()) == [(0, SECONDS_PER_DAY)]


def test_same_day_curfew_splits_into_two():
    # 08:00–17:00 do-not-deliver → [00:00, 08:00) ∪ (17:00, 24:00)
    windows = to_delivery_windows(Curfew(start="08:00", end="17:00"))
    assert windows == [(0, 8 * 3600), (17 * 3600, SECONDS_PER_DAY)]


def test_overnight_curfew_single_daytime_window():
    # 22:00–07:00 do-not-deliver → [07:00, 22:00) single window
    windows = to_delivery_windows(Curfew(start="22:00", end="07:00"))
    assert windows == [(7 * 3600, 22 * 3600)]


def test_degenerate_zero_zero_means_no_curfew():
    assert to_delivery_windows(Curfew(start="00:00", end="00:00")) == [(0, SECONDS_PER_DAY)]


def test_full_day_block_yields_no_windows():
    # 00:00–24:00 entirely blocked.
    assert to_delivery_windows(Curfew(start="00:00", end="24:00")) == []


def test_curfew_starting_at_midnight_only_yields_post_window():
    # 00:00–06:00 → only the after-curfew window
    windows = to_delivery_windows(Curfew(start="00:00", end="06:00"))
    assert windows == [(6 * 3600, SECONDS_PER_DAY)]


def test_curfew_ending_at_midnight_only_yields_pre_window():
    # 22:00–24:00 → only the before-curfew window
    windows = to_delivery_windows(Curfew(start="22:00", end="24:00"))
    assert windows == [(0, 22 * 3600)]


def test_primary_window_picks_widest():
    # Same-day curfew 08:00–10:00 → allowed = [(0, 8h), (10h, 24h)]; widest is the second.
    win = primary_window(Curfew(start="08:00", end="10:00"))
    assert win == (10 * 3600, SECONDS_PER_DAY)


def test_primary_window_none_for_no_curfew():
    assert primary_window(None) == (None, None)
    assert primary_window(Curfew()) == (None, None)


def test_primary_window_overnight():
    win = primary_window(Curfew(start="22:00", end="07:00"))
    assert win == (7 * 3600, 22 * 3600)


def test_primary_window_full_block_yields_infeasible_range():
    # Should return a zero-length window so the solver flags infeasibility.
    start, end = primary_window(Curfew(start="00:00", end="24:00"))
    assert start is not None and end is not None
    assert end - start <= 1
