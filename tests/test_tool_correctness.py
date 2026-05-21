"""Unit tests for the tool_correctness evaluator (offline)."""

from agent.evals.evaluators.tool_correctness import score_row


def test_perfect_match():
    expected = [
        {"name": "get_store_orders", "args": {"district": "SLMontana"}},
        {"name": "get_restrictions", "args": {"state": "MT"}},
    ]
    actual = [
        {"name": "get_store_orders", "arguments": {"req": {"order_group": "slmontana"}}},
        {"name": "get_restrictions", "arguments": {"req": {"state": "MT"}}},
    ]
    r = score_row(expected, actual, "ok")
    assert r["score"] == 1.0
    assert r["matched"] == 2


def test_partial_match():
    expected = [
        {"name": "get_store_orders", "args": {}},
        {"name": "optimize_route", "args": {}},
        {"name": "validate_route", "args": {}},
    ]
    actual = [{"name": "get_store_orders", "arguments": {}}]
    r = score_row(expected, actual, "ok")
    assert r["score"] == round(1 / 3, 3)
    assert r["matched"] == 1


def test_no_match():
    expected = [{"name": "select_trailer", "args": {}}]
    actual = [{"name": "get_store_orders", "arguments": {}}]
    r = score_row(expected, actual, "ok")
    assert r["score"] == 0.0


def test_extra_tools_ignored():
    expected = [{"name": "get_store_orders", "args": {}}]
    actual = [
        {"name": "get_store_orders", "arguments": {}},
        {"name": "get_restrictions", "arguments": {}},
    ]
    r = score_row(expected, actual, "ok")
    assert r["score"] == 1.0


def test_out_of_scope_correct():
    r = score_row([], [], "This is out of scope; I have no historical data.")
    assert r["score"] == 1.0


def test_out_of_scope_with_calls():
    r = score_row([], [{"name": "x", "arguments": {}}], "answer")
    assert r["score"] == 0.0


def test_out_of_scope_no_gap_statement():
    r = score_row([], [], "Here is an answer.")
    assert r["score"] == 0.5
