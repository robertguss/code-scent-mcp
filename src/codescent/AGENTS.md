# SOURCE PACKAGE GUIDANCE

## OVERVIEW

`src/codescent` contains the installable package: CLI, MCP transport, dashboard,
engine, services, storage, evals, and smoke helpers.

## STRUCTURE

```text
src/codescent/
+-- cli/          # Typer command surface
+-- mcp/          # FastMCP transport adapters
+-- dashboard/    # local loopback UI and JSON API
+-- services/     # shared business logic
+-- engine/       # inventory, parsers, rules, search ranking
+-- storage/      # SQLite state and migrations
+-- evals/        # deterministic eval implementation
+-- smoke/        # reusable smoke-test contract helpers
```

## WHERE TO LOOK

| Task | Location | Notes |
| --- | --- | --- |
| CLI command wiring | `cli/main.py`, `cli/admin.py`, `cli/reporting.py` | Keep command bodies small. |
| MCP server wiring | `mcp/server.py` | Registers tool groups only. |
| Shared models | `core/models.py`, `core/errors.py` | Prefer typed Pydantic/domain models. |
| Public surface names | `core/public_surface.py` | Contract tests compare against this. |
| Repo paths and excludes | `core/paths.py`, `engine/inventory.py` | Keep `.codescent` and generated paths excluded. |
| Persistence | `storage/repository.py`, `storage/schema.py` | Owns `.codescent/index.sqlite`. |

## CONVENTIONS

- Python is typed strictly. `pyproject.toml` sets BasedPyright to `all`; avoid
  untyped parameters and private test reach-through outside test-only scopes.
- Ruff selects `ALL` with explicit ignores. Match the existing Google-style
  docstring and 88-column formatting.
- Treat CLI, MCP, and dashboard code as adapters over service objects.
- Write runtime state only below `.codescent/` unless the command is explicitly
  an export/report command with a user-provided output path.
- Keep returned source snippets bounded; prefer line ranges, summaries, and
  ranking reasons over whole-file payloads.

## ANTI-PATTERNS

- No autofix behavior in runtime tools.
- No runtime subprocess execution for verification suggestions; planning tools
  describe checks, they do not run them.
- No runtime network dependency for local analysis paths.
- Do not make fixture-only behavior leak into main package defaults.
