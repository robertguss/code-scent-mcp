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

## Per-Rule Eval Precision Harness + CI Gate

This harness measures **eval precision** — `TP / (TP + FP)` for every rule
against a labeled corpus of known-smelly and known-clean fixtures. It is
distinct from the runtime **acceptance precision** (accept-vs-dismiss verdicts):
eval precision answers "when a rule fires on this fixed corpus, is it firing on
something it is supposed to flag?". For one rule `R`:

- **TP** — `R` produced a finding on an item labeled *smelly* for `R`.
- **FP** — `R` produced a finding on an item labeled *clean* for `R`.
- **eval precision** — `TP / (TP + FP)` (`1.0` when `R` made no positive
  prediction on either set).

Run the verbose per-rule report over the seeded corpus:

```bash
uv run python evals/run_precision.py --verbose
```

Run the CI gate (exits nonzero when any rule regresses below its recorded
baseline, or a baselined rule's fixture disappeared):

```bash
uv run python evals/run_precision.py --check
```

Re-record the baselines after an intentional, reviewed precision change:

```bash
uv run python evals/run_precision.py --update-baseline
```

### Corpus and baselines

- **Corpus** — `evals/precision_corpus/`. Tiny Python + TypeScript fixtures, one
  smelly fixture per covered rule plus shared clean negatives (`pkg/tidy.py`,
  `tests/test_corpus_clean.py`, `ts/clean.ts`, `ts/tests/clean.test.ts`). The
  smelly fixtures are intentionally flawed and **must stay flawed** (AGENTS.md);
  the corpus is excluded from `ruff`/`basedpyright`.
- **Labels** — `evals/precision_corpus/labels.json`. Per `rule_id`, the `smelly`
  (true-positive) and `clean` (false-positive) fixture paths, relative to the
  corpus root.
- **Baselines** — `evals/precision_baselines.json`. A checked-in, inspectable
  per-rule eval-precision floor map. The gate fails whenever a measured rule
  precision drops below its baseline.

The harness reuses the production `CodeHealthService` scan with the same strict
thresholds the deterministic eval pins, so it exercises the real rules. It is
deterministic, bounded (tiny corpus), and performs no network or git access.

### Coverage and known gaps

Covered (20 rules, all at baseline `1.0`): the Python maintainability rules
(`python.large_file`, `large_function`, `large_class`, `too_many_imports`,
`deep_nesting`, `todo_cluster`, `duplicate_literal`, `mixed_responsibilities`,
`suspicious_slop_candidate`, `missing_nearby_test`, `import_cycle`) and the
TypeScript/React/Next rules (`typescript.large_component`, `too_many_exports`,
`todo_cluster`, `duplicate_literal`, `suspicious_slop_candidate`,
`missing_nearby_test`, `react.too_many_hooks`, `too_many_props`,
`next.route_handler_too_much`).

Intentional gaps (not yet labeled): `python.dead_code_candidate` and
`python.structural_near_duplicate` (actively evolving rule code, surfaced as
"gaps" in `--verbose` output); `python.relative_large_*` (disabled under strict
thresholds and require a ≥12-sample size distribution); `python.uncovered_symbol`
(needs a coverage report); `architecture.boundary_violation` (needs a project
layering config); `python.changed_source_without_related_test` (git/index
dependent — excluded, mirroring the deterministic eval).

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
