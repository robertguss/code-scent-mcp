# CodeScent Evals

CodeScent measures the Python-first MVP with deterministic offline evals,
agent-in-the-loop evals, real repo smoke, and source-read-only safety proofs.
These gates are local and do not require network access at runtime.

## Deterministic Offline Eval

Run:

```bash
uv run python evals/run_deterministic.py --repo tests/fixtures/python-basic --expected evals/fixtures/python-basic.expected.json --out .omo/evidence/task-16-deterministic-eval.json
```

The deterministic offline eval measures:

- retrieval top-k for file and content search;
- bounded context ranges;
- finding precision against expected fixture findings;
- stable finding IDs;
- workflow success for finding context, refactor plan, and suggested tests;
- source-read-only behavior;
- timing telemetry.

The command exits nonzero when the eval score does not pass.

## Agent-In-The-Loop Eval

Run the transcript gate described in `evals/agent_task.md` and
`scripts/run_agent_eval.md`.

The agent-in-the-loop eval requires a local agent or human-driven transcript to
use CodeScent tools to select one fixture finding, retrieve finding context,
produce a safe plan, call `suggest_tests`, rescan, and mark the finding with an
artifact-backed transcript. Broad shell grep cannot be the primary discovery
mechanism.

## Real Repo Smoke

Run:

```bash
uv run python scripts/smoke_lx_data_lake.py --repo /Users/robertguss/Projects/wts-lx/lx_data_lake --out .omo/evidence/task-18-lx-smoke.json
```

The real smoke validates exclusions, tool calls, findings, telemetry,
source-read-only proof, and filtered git status stability on
`/Users/robertguss/Projects/wts-lx/lx_data_lake`.

## Source-Read-Only Safety

Run:

```bash
uv run python scripts/prove_source_read_only.py --repo tests/fixtures/python-basic --out .omo/evidence/task-19-read-only.json
```

The source-read-only proof snapshots indexed source hashes before and after the
MCP/CLI loop, blocks network socket creation, confirms `network_attempts` is
zero, and records that only `.codescent` state is allowed to change.
