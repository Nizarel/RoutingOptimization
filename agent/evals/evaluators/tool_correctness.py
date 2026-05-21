"""Custom evaluator: tool_correctness.

Measures *tool selection accuracy*: did the agent invoke the set of tools
required to answer this question? Argument fidelity is intentionally NOT
scored here -- many MCP tools accept multiple valid argument shapes
(``district`` vs ``order_group``, etc.), and arg-level correctness is better
evaluated by GroundednessEvaluator / TaskAdherenceEvaluator on the final answer.

Scoring per row:
- ``score = |expected_names ∩ actual_names| / |expected_names|``
- If ``expected_tool_calls`` is empty (out-of-scope rows), pass with 1.0 only
  when the agent made no tool calls AND surfaced an explicit gap statement
  ("out of scope", "not available", "no historical data", etc.).
"""

from __future__ import annotations

import re
from typing import Any

_GAP_PATTERNS = re.compile(
    r"\b(out[- ]of[- ]scope|not available|no (historical|history|access)|"
    r"don'?t have|cannot answer|outside (my|the) scope|no data)\b",
    re.IGNORECASE,
)


def score_row(
    expected_calls: list[dict[str, Any]],
    actual_calls: list[dict[str, Any]],
    answer: str,
) -> dict[str, Any]:
    """Return {score, reason, matched, expected_count, actual_count}."""
    if not expected_calls:
        if actual_calls:
            return {
                "score": 0.0,
                "reason": "Expected no tool calls (out-of-scope) but agent called tools.",
                "matched": 0,
                "expected_count": 0,
                "actual_count": len(actual_calls),
            }
        if _GAP_PATTERNS.search(answer or ""):
            return {
                "score": 1.0,
                "reason": "Agent correctly declined out-of-scope question.",
                "matched": 0,
                "expected_count": 0,
                "actual_count": 0,
            }
        return {
            "score": 0.5,
            "reason": "No tool calls (correct) but answer did not explicitly state the gap.",
            "matched": 0,
            "expected_count": 0,
            "actual_count": 0,
        }

    expected_names = {c.get("name", "") for c in expected_calls if c.get("name")}
    actual_names = {c.get("name", "") for c in actual_calls if c.get("name")}
    matched = expected_names & actual_names
    missing = expected_names - actual_names

    score = len(matched) / len(expected_names) if expected_names else 0.0
    reason_parts = [f"{n}:hit" for n in sorted(matched)] + [
        f"{n}:missing" for n in sorted(missing)
    ]
    return {
        "score": round(score, 3),
        "reason": ", ".join(reason_parts) or "no expected tools",
        "matched": len(matched),
        "expected_count": len(expected_names),
        "actual_count": len(actual_calls),
    }
