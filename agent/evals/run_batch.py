"""Batch eval runner for the routing-planner agent.

Usage:
    python -m agent.evals.run_batch [--config agent/evals/eval_config.yaml]

Requires (locally):
    pip install httpx pyyaml azure-ai-evaluation azure-identity
"""

from __future__ import annotations

import argparse
import asyncio
import importlib
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import yaml


def _load_dataset(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        rows.append(json.loads(line))
    return rows


async def _ask_agent(client: httpx.AsyncClient, url: str, query: str, timeout: float) -> dict[str, Any]:
    body = {"messages": [{"role": "user", "content": query}]}
    r = await client.post(url, json=body, timeout=timeout)
    r.raise_for_status()
    return r.json()


def _load_custom_evaluator(spec: dict[str, Any]):
    module = importlib.import_module(spec["module"])
    return getattr(module, spec["function"])


def _build_groundedness_evaluator(judge: dict[str, Any]):
    """Build azure.ai.evaluation.GroundednessEvaluator.

    When ``api_key`` is omitted from the model_config, the SDK falls back to
    DefaultAzureCredential automatically for Azure OpenAI calls.
    """
    from azure.ai.evaluation import GroundednessEvaluator  # type: ignore

    endpoint = judge.get("azure_endpoint") or os.environ.get("AZURE_OPENAI_ENDPOINT")
    deployment = judge.get("azure_deployment") or os.environ.get("AZURE_OPENAI_DEPLOYMENT")
    api_version = judge.get("api_version") or os.environ.get("AZURE_OPENAI_API_VERSION", "2024-10-21")
    if not endpoint or not deployment:
        raise RuntimeError("judge.azure_endpoint and azure_deployment required")

    model_config: dict[str, Any] = {
        "azure_endpoint": endpoint,
        "azure_deployment": deployment,
        "api_version": api_version,
    }
    api_key = os.environ.get("AZURE_OPENAI_API_KEY")
    if api_key:
        model_config["api_key"] = api_key
    return GroundednessEvaluator(model_config=model_config)


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="agent/evals/eval_config.yaml")
    parser.add_argument("--agent-url", default=os.environ.get("AGENT_URL"))
    parser.add_argument("--skip-groundedness", action="store_true")
    args = parser.parse_args()

    cfg_path = Path(args.config)
    cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))

    agent_url = args.agent_url or cfg["agent"]["chat_url"]
    timeout = float(cfg["agent"].get("request_timeout_sec", 240))
    dataset_path = Path(cfg["dataset"]["path"])
    rows = _load_dataset(dataset_path)
    print(f"[eval] loaded {len(rows)} dataset rows from {dataset_path}")
    print(f"[eval] agent: {agent_url}")

    # Build evaluators
    tool_corr = None
    groundedness = None
    for ev in cfg["evaluators"]:
        if ev["kind"] == "custom" and ev["name"] == "tool_correctness":
            tool_corr = _load_custom_evaluator(ev)
        elif ev["kind"] == "builtin" and ev["name"] == "groundedness" and not args.skip_groundedness:
            print("[eval] loading GroundednessEvaluator...")
            groundedness = _build_groundedness_evaluator(cfg["judge"])

    judge_delay = float(cfg.get("judge", {}).get("inter_row_delay_sec", 0))
    results: list[dict[str, Any]] = []
    async with httpx.AsyncClient() as client:
        for i, row in enumerate(rows, 1):
            if i > 1 and judge_delay > 0:
                await asyncio.sleep(judge_delay)
            qid = row["id"]
            query = row["query"]
            expected_calls = row.get("expected_tool_calls", [])
            reference = row.get("reference_answer", "")
            print(f"[eval] ({i}/{len(rows)}) {qid} -- asking agent")
            try:
                resp = await _ask_agent(client, agent_url, query, timeout)
                answer = resp.get("answer", "")
                actual_calls = resp.get("tool_calls", [])
                error = None
            except Exception as exc:  # noqa: BLE001
                answer = ""
                actual_calls = []
                error = str(exc)

            tc = tool_corr(expected_calls, actual_calls, answer) if tool_corr else None

            gd: dict[str, Any] | None = None
            if groundedness is not None and answer and reference:
                try:
                    gd_raw = groundedness(
                        query=query,
                        response=answer,
                        context=reference,
                    )
                    gd = dict(gd_raw) if not isinstance(gd_raw, dict) else gd_raw
                except Exception as exc:  # noqa: BLE001
                    gd = {"error": str(exc)}

            results.append(
                {
                    "id": qid,
                    "query": query,
                    "answer": answer,
                    "actual_tool_calls": actual_calls,
                    "expected_tool_calls": expected_calls,
                    "error": error,
                    "tool_correctness": tc,
                    "groundedness": gd,
                    "tags": row.get("tags", []),
                }
            )

    # Aggregate
    thresholds = cfg["thresholds"]
    tc_scores = [r["tool_correctness"]["score"] for r in results if r["tool_correctness"]]
    tc_pass = [s for s in tc_scores if s >= thresholds["tool_correctness_min_pass"]]
    tc_pass_rate = len(tc_pass) / len(tc_scores) if tc_scores else 0.0

    gd_scores: list[float] = []
    for r in results:
        if r["groundedness"] and isinstance(r["groundedness"], dict):
            v = r["groundedness"].get("groundedness") or r["groundedness"].get("gpt_groundedness")
            if isinstance(v, (int, float)):
                gd_scores.append(float(v))
    gd_avg = sum(gd_scores) / len(gd_scores) if gd_scores else 0.0

    summary = {
        "timestamp": datetime.now(UTC).isoformat(),
        "agent_url": agent_url,
        "rows": len(results),
        "tool_correctness": {
            "scores": tc_scores,
            "pass_count": len(tc_pass),
            "pass_rate": round(tc_pass_rate, 3),
            "min_pass_threshold": thresholds["tool_correctness_min_pass"],
            "overall_pass_rate_threshold": thresholds["tool_correctness_overall_min_pass_rate"],
            "overall_passed": tc_pass_rate >= thresholds["tool_correctness_overall_min_pass_rate"],
        },
        "groundedness": {
            "scores": gd_scores,
            "avg": round(gd_avg, 3),
            "min_avg_threshold": thresholds["groundedness_min_avg"],
            "overall_passed": gd_avg >= thresholds["groundedness_min_avg"] if gd_scores else None,
        },
    }

    # Persist
    out_dir = Path(cfg["output"]["results_dir"])
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    detail_path = out_dir / f"batch_eval_{ts}.jsonl"
    summary_path = out_dir / f"batch_eval_{ts}_summary.json"
    with detail_path.open("w", encoding="utf-8") as f:
        for r in results:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print("\n[eval] === SUMMARY ===")
    print(json.dumps(summary, indent=2))
    print(f"\n[eval] details: {detail_path}")
    print(f"[eval] summary: {summary_path}")

    overall_pass = summary["tool_correctness"]["overall_passed"] and (
        summary["groundedness"]["overall_passed"] in (True, None)
    )
    return 0 if overall_pass else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
