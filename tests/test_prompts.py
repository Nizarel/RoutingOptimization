"""Unit tests for MCP prompts (string content)."""
from __future__ import annotations

from src.prompts.check_compliance import check_compliance
from src.prompts.compare_scenarios import compare_scenarios
from src.prompts.explain_solution import explain_solution
from src.prompts.plan_district_route import plan_district_route
from src.prompts.select_best_trailer import select_best_trailer


async def test_plan_district_route_includes_args():
    text = await plan_district_route(
        dc_code="52-DC", order_group="OG1", district="N1", trailer_type="P53R"
    )
    assert "52-DC" in text
    assert "OG1" in text
    assert "N1" in text
    assert "P53R" in text
    assert "optimize_route" in text


async def test_compare_scenarios_mentions_both_labels():
    text = await compare_scenarios(
        dc_code="52-DC",
        order_group="OG1",
        scenario_a_label="Baseline",
        scenario_b_label="LeadPup",
    )
    assert "Baseline" in text
    assert "LeadPup" in text


async def test_explain_solution_with_history_id():
    text = await explain_solution(history_id="hist-1")
    assert "hist-1" in text


async def test_explain_solution_without_history_id():
    text = await explain_solution()
    assert "routing://last-solution" in text


async def test_select_best_trailer_lists_candidates():
    text = await select_best_trailer(
        order_group="OG1", candidate_trailers="P53R,P57R"
    )
    assert "P53R,P57R" in text
    assert "select_trailer" in text


async def test_check_compliance_mentions_validate():
    text = await check_compliance(history_id="hist-9")
    assert "hist-9" in text
    assert "validate_route" in text
