# Routing Planner Agent — Evaluation

Two-tier evaluation for the ACA-hosted routing-planner agent.

## What this evaluates

- **`tool_correctness`** (custom): set-based tool-selection accuracy. For each
  dataset row, what fraction of the expected MCP tool names did the agent
  invoke? Implementation: `agent/evals/evaluators/tool_correctness.py`.
- **`groundedness`** (`azure.ai.evaluation.GroundednessEvaluator`, built-in):
  LLM-as-judge score 1–5 for whether the agent's answer is grounded in the
  reference answer / context. Uses the Foundry `gpt-4.1` deployment as judge.

Out-of-scope rows (empty `expected_tool_calls`) pass only when the agent
makes **no** tool calls *and* its answer explicitly states the gap
("out of scope", "no historical data", etc.).

## Dataset

`agent/evals/dataset.jsonl` — 9 rows derived from `data/FRE0224_Agent_Test_Questions.md`.
Each row: `{id, query, expected_tool_calls, reference_answer, tags}`.

## Local batch run

Prereqs: install the eval deps into your venv

```powershell
.\.venv\Scripts\python.exe -m pip install -r agent/evals/requirements.txt
```

Run against the deployed agent:

```powershell
.\.venv\Scripts\python.exe -m agent.evals.run_batch
```

Override the agent URL:

```powershell
$env:AGENT_URL = "https://<agent-fqdn>/chat"
.\.venv\Scripts\python.exe -m agent.evals.run_batch
```

Skip groundedness (no LLM judge calls):

```powershell
.\.venv\Scripts\python.exe -m agent.evals.run_batch --skip-groundedness
```

Outputs land in `.foundry/results/`:
- `batch_eval_<ts>.jsonl` — one row per query with answer, tool calls, scores.
- `batch_eval_<ts>_summary.json` — aggregate scores + pass/fail vs thresholds.

### Required RBAC for groundedness

The principal running `run_batch` (whether your AAD user locally or the UAMI
in the ACA Job) needs **Cognitive Services OpenAI User** on the Foundry
account. Grant for a user:

```powershell
$me     = az ad signed-in-user show --query id -o tsv
$acctId = az cognitiveservices account show -g rg-routing-mcp-dev -n aif-rt-<token> --query id -o tsv
az role assignment create --assignee-object-id $me --assignee-principal-type User `
  --role "Cognitive Services OpenAI User" --scope $acctId
```

(The agent UAMI already has this — granted in `infra/modules/foundry.bicep`.)

## Thresholds

Defined in `agent/evals/eval_config.yaml`:

| Metric | Threshold | Notes |
|---|---|---|
| `tool_correctness` per-row pass | score ≥ 0.5 | majority of expected tools were called |
| `tool_correctness` overall pass-rate | ≥ 0.78 (7/9) | gate for promoting agent revisions |
| `groundedness` avg | ≥ 4.0 / 5.0 | gate for answer quality |

The script exits non-zero when either threshold fails — wire into CI / azd hooks.

## Continuous evaluation (ACA Job)

`infra/modules/eval_job.bicep` provisions an ACA Job (`caj-eval-rt-<token>`)
on the existing managed environment. The job:
- Triggers on cron `0 10 * * *` (daily 10:00 UTC). Override `cronExpression`.
- Reuses the agent container image and runs `python -m agent.evals.run_batch`.
- Sends stdout (incl. summary JSON) to Log Analytics under the same workspace.

After every `azd deploy agent`, sync the job's image to the agent's current image:

```powershell
$rg     = "rg-routing-mcp-dev"
$agent  = az containerapp show -g $rg -n ca-agent-rt-<token> --query 'properties.template.containers[0].image' -o tsv
az containerapp job update -g $rg -n caj-eval-rt-<token> --image $agent
```

Trigger a one-off run manually:

```powershell
az containerapp job start -g rg-routing-mcp-dev -n caj-eval-rt-<token>
```

Tail the job's logs:

```powershell
az containerapp job execution list -g rg-routing-mcp-dev -n caj-eval-rt-<token> --query "[0].name" -o tsv
# then in Log Analytics:
#   ContainerAppConsoleLogs_CL | where ContainerJobName_s == "caj-eval-rt-<token>"
```

## Known agent quality gaps (first eval run)

From the initial batch (set-based scoring will reflect after re-run):
- The agent reliably calls `get_store_orders` + `get_restrictions` but **does not
  call `optimize_route` or `validate_route`** even when the question implies
  optimization. This is a **system prompt / instruction-following gap** in
  `agent/system_prompt.md` — the explicit "plan → optimize → validate" policy
  is being treated as optional.
- Q2/Q4/Q5/Q8 receive **zero tool calls**: the model answers conceptually
  from the system prompt context without grounding via tools.
- Q3 (out-of-scope) is correctly silent on tools but doesn't surface the data
  gap explicitly — partial pass.

Next iteration: tighten `agent/system_prompt.md` with hard rules ("MUST call
`optimize_route` before answering any question about routes, utilization,
delays, or splits") and re-evaluate.
