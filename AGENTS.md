# PROJECT KNOWLEDGE BASE

**Generated:** 2026-06-12
**Commit:** bd76c34
**Branch:** main

## OVERVIEW

CodeScent is a local, MCP-first codebase improvement server for coding agents.
The package is Python 3.12+, distributed as `codescent`, and exposes a Typer
CLI, a FastMCP stdio server, and a local dashboard backed by `.codescent` state.

## STRUCTURE

```text
code-scent-mcp/
+-- src/codescent/        # package source: CLI, MCP, services, engine, storage
+-- tests/                # unit, integration, contract, smoke, eval, security
+-- tests/fixtures/       # checked-in smell fixture repos; do not "fix" them
+-- evals/                # deterministic eval CLI and expected manifests
+-- scripts/              # smoke, safety, audit, screenshot, inspection helpers
+-- docs/                 # PRD, architecture, MCP tools, eval, routing docs
+-- templates/            # optional downstream agent-routing templates
```

## WHERE TO LOOK

| Task | Location | Notes |
| --- | --- | --- |
| Product scope | `docs/prd.md` | Durable source for what CodeScent is and is not. |
| Architecture | `docs/architecture.md` | Transport, service, storage, and MCP boundaries. |
| MCP tool contract | `docs/mcp-tools.md` | Current public tool surface and safety wording. |
| CLI entry | `src/codescent/cli/main.py` | Typer app; admin/reporting commands register here. |
| MCP entry | `src/codescent/mcp/server.py` | FastMCP app and tool registration order. |
| Public surface registry | `src/codescent/core/public_surface.py` | Canonical CLI/MCP names used by contract tests. |
| Business logic | `src/codescent/services/` | Keep transport adapters thin; put behavior here. |
| Code analysis | `src/codescent/engine/` | Inventory, parsers, rules, packs, search ranking. |
| Persistence | `src/codescent/storage/` | `.codescent/index.sqlite` schema and repositories. |
| Dashboard | `src/codescent/dashboard/` | Loopback HTTP UI and static assets. |
| Tests by behavior | `tests/` | Contract and security tests are part of the public API. |
| Evals and smokes | `docs/evals.md`, `scripts/` | Deterministic eval, real repo smoke, read-only proof. |

## CODE MAP

| Symbol / File | Type | Location | Role |
| --- | --- | --- | --- |
| `app` | Typer app | `src/codescent/cli/main.py` | CLI root for `codescent`. |
| `mcp` | FastMCP app | `src/codescent/mcp/server.py` | Local MCP server instance. |
| `PUBLIC_SURFACE` | registry | `src/codescent/core/public_surface.py` | Contract source for exposed commands/tools. |
| `SearchService` | service | `src/codescent/services/search.py` | Ranked, bounded search operations. |
| `ContextService` | service | `src/codescent/services/context.py` | Bounded context and graph operations. |
| `FindingService` | service | `src/codescent/services/findings.py` | Deterministic finding lifecycle. |
| `StorageRepository` | storage | `src/codescent/storage/repository.py` | SQLite state under `.codescent`. |
| `run_deterministic_eval` | eval | `src/codescent/evals/deterministic.py` | Manifest-backed offline eval. |

LSP document-symbol support was unavailable in this environment; this map is
based on repo inspection and existing contract anchors.

## CONVENTIONS

- Use `uv run ...` for local commands; there is no `Makefile`, `Justfile`, or
  GitHub workflow as the canonical gate.
- Keep CodeScent source-read-only for analyzed source. Runtime writes belong in
  `.codescent/` unless a command explicitly targets an output file.
- Keep MCP, CLI, and dashboard adapters thin. Shared behavior belongs in
  `src/codescent/services/`, `src/codescent/engine/`, or `src/codescent/storage/`.
- Public CLI/MCP changes must update `src/codescent/core/public_surface.py`,
  `docs/mcp-tools.md` or README docs as appropriate, and contract tests.
- Outputs should be bounded by default. Prefer summarized context and persisted
  local state over returning huge source payloads.
- Preserve the checked-in fixture repos as intentionally flawed inputs.

## ANTI-PATTERNS (THIS PROJECT)

- Do not edit analyzed source as part of CodeScent runtime behavior.
- Do not introduce runtime network access into indexing, scanning, search,
  context, dashboard smoke, or deterministic eval paths.
- Do not move business logic into FastMCP tool functions or Typer commands.
- Do not treat `tests/fixtures/python-basic` as part of the main pytest suite;
  it is excluded by config and used as an analyzed repo.
- Do not expose new public tools or commands without contract coverage and docs.
- Do not auto-write templates from `templates/` into analyzed repos.

## COMMANDS

```bash
uv sync
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run basedpyright
uv run codescent --help
uv run codescent init --repo tests/fixtures/python-basic
uv run codescent scan --repo tests/fixtures/python-basic --json
uv run python evals/run_deterministic.py --repo tests/fixtures/python-basic --expected evals/fixtures/python-basic.expected.json --out .omo/evidence/task-16-deterministic-eval.json
uv run python scripts/prove_source_read_only.py --repo tests/fixtures/python-basic --out .omo/evidence/task-19-read-only.json
```

## NOTES

- `.venv/`, `.omo/`, caches, `.codescent/`, generated/vendor/build outputs, and
  fixture runtime state can dominate search results; exclude them deliberately.
- `codescent reset` is intentionally gated behind `--dry-run` or `--yes`.
- `docs/prd.md`, `docs/architecture.md`, and `docs/mcp-tools.md` outrank older
  chat context for product behavior.
- The TypeScript/React/Next tree under `tests/fixtures/ts-react-next-basic` is a
  fixture inside a Python repo, not a top-level frontend app.
