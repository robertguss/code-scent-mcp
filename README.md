# CodeScent

CodeScent is a local, MCP-first codebase improvement server for AI coding
agents. It indexes repositories locally, exposes bounded code intelligence to
MCP clients, finds deterministic code-health issues, guides safe improvement
loops, and keeps all runtime state under `.codescent/`.

The first shipped slice was the Python-first MVP. The current local surface
keeps those safety guarantees while adding TypeScript/React/Next support,
expanded search and graph tools, reports, CI/diff review, opt-in subjective
review, evals, and a loopback dashboard.

CodeScent is local stdio for MCP and loopback-only for the dashboard. It writes
only `.codescent` state in the analyzed repository. It does not edit analyzed
source files. Safety summary: writes only .codescent state and does not edit
analyzed source files. The runtime no-network model applies to indexing,
scanning, searching, context building, dashboard use, CI mode, and eval
execution. Subjective LLM review remains opt-in and disabled by default.

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
uv run codescent report --repo tests/fixtures/python-basic --format json
uv run codescent ci --repo tests/fixtures/python-basic --format json
uv run codescent doctor --repo tests/fixtures/python-basic --json
```

`doctor` runs CodeScent internal diagnostics only. Suggested verification
commands are recommendations; CodeScent does not execute target project
test/lint/build commands in V1.

See [docs/getting-started.md](docs/getting-started.md) for an isolated first run
that uses a temporary fixture copy.

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

See [docs/mcp-tools.md](docs/mcp-tools.md) for the registered MCP tool surface.

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

## Documentation

- [Getting started](docs/getting-started.md): install and run the first local
  workflow.
- [CLI reference](docs/cli-reference.md): commands, options, outputs, and safety
  notes.
- [MCP tools](docs/mcp-tools.md): registered tools, groups, and output
  boundaries.
- [Workflows](docs/workflows.md): finding lifecycle and safe improvement loop.
- [Configuration](docs/configuration.md): `.codescent/`, rules, routing
  templates, reset, and recovery.
- [Dashboard](docs/dashboard.md): loopback UI/API, exports, and smoke checks.
- [Language packs](docs/language-packs.md): shipped language support and future
  pack boundaries.
- [Evals](docs/evals.md): deterministic eval, agent transcript, real smoke, and
  source-read-only proof.
- [Agent routing](docs/agent-routing.md): optional downstream agent templates.
- [Changelog](CHANGELOG.md): release history.

## Implemented Local Surface

- Python and TypeScript/React/Next language and rule packs.
- Search expansion, references/callers/callees, related files, and impact.
- Reports, backlog/progress/regression views, config/rules, and safe reset.
- Recommend-only `verify_change`; it records plans and does not execute target
  project commands.
- Local CI/PR review commands with deterministic threshold behavior.
- Opt-in subjective review with no runtime network unless explicitly enabled.
- Loopback dashboard for health, findings, progress, rule config updates, and
  exports.

## Still Out Of Scope

- automatic source edits or autofix
- HTTP/SSE MCP transport, hosted service, remote dashboard access, or auth
- runtime network by default

## Development

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run basedpyright
```
