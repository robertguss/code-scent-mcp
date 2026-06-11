# CodeScent

CodeScent is a local, MCP-first codebase improvement server for AI coding
agents. This repository implements the Python-first MVP: Python indexing,
search, context, deterministic code-health findings, refactor planning,
suggested verification commands, finding lifecycle, and evals.

CodeScent is local stdio only in this MVP. It writes only .codescent state in
the analyzed repository and does not edit analyzed source files. The runtime no-network
model applies to indexing, scanning, searching, context building, and eval
execution.

## Install

```bash
uv sync
uv run codescent --help
```

## CLI Workflow

```bash
uv run codescent init --repo tests/fixtures/python-basic
uv run codescent index --repo tests/fixtures/python-basic --json
uv run codescent status --repo tests/fixtures/python-basic --json
uv run codescent scan --repo tests/fixtures/python-basic --json
uv run codescent doctor --repo tests/fixtures/python-basic --json
```

`doctor` runs CodeScent internal diagnostics only. Suggested verification
commands are recommendations; CodeScent does not execute target project
test/lint/build commands in V1.

## MCP Stdio

Connect an MCP client to the local stdio server:

```bash
uv run codescent serve
```

The first-run loop is:

1. `init`
2. `index`
3. `scan`
4. use MCP tools for repo map, bounded search, finding context, refactor plan,
   suggested tests, and rescan
5. mark findings only after the user or agent has separate verification evidence

See [docs/mcp-tools.md](docs/mcp-tools.md) for the exact MVP tool list.

## Evals And Smoke

Run the deterministic offline eval:

```bash
uv run python evals/run_deterministic.py --repo tests/fixtures/python-basic --expected evals/fixtures/python-basic.expected.json --out .omo/evidence/task-16-deterministic-eval.json
```

Run the real repo smoke target:

```bash
uv run python scripts/smoke_lx_data_lake.py --repo /Users/robertguss/Projects/wts-lx/lx_data_lake --out .omo/evidence/task-18-lx-smoke.json
```

Run the source-read-only proof:

```bash
uv run python scripts/prove_source_read_only.py --repo tests/fixtures/python-basic --out .omo/evidence/task-19-read-only.json
```

See [docs/evals.md](docs/evals.md) for deterministic, agent-in-the-loop, real
smoke, and safety eval details.

## Out Of Scope

- additional language support
- dashboard UI or hosted service
- HTTP/SSE MCP transport or auth
- CI/PR review mode
- subjective LLM review
- automatic source edits
- broad impact/reference/caller graph tools beyond the approved MVP surface

## Development

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run basedpyright
```
