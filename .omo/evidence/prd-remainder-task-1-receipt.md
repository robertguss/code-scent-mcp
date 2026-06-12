# PRD Remainder Task 1 Receipt

Timestamp: 2026-06-11T21:13:08Z

## Scope

Task: Add post-MVP public surface registry and docs unlock.

Changed:

- Added `src/codescent/core/public_surface.py`.
- Added `tests/contract/test_public_surface_registry.py`.
- Updated `docs/mcp-tools.md`.
- Updated `scripts/audit_plan_compliance.py`.

Did not expose new runtime MCP tools or CLI commands.

## Red

Command:

```bash
uv run pytest tests/contract/test_public_surface_registry.py::test_post_mvp_surface_is_declared_but_not_registered
```

Result: failed during collection with
`ModuleNotFoundError: No module named 'codescent.core.public_surface'`.

## Green

Command:

```bash
uv run pytest tests/contract/test_public_surface_registry.py tests/contract/test_mcp_tool_surface.py tests/contract/test_cli.py
```

Result: 12 passed.

Command:

```bash
uv run ruff check src/codescent/core/public_surface.py tests/contract/test_public_surface_registry.py scripts/audit_plan_compliance.py
```

Result: all checks passed.

Command:

```bash
uv run basedpyright src/codescent/core/public_surface.py tests/contract/test_public_surface_registry.py scripts/audit_plan_compliance.py
```

Result: 0 errors, 0 warnings, 0 notes.

Command:

```bash
uv run ruff format --check src/codescent/core/public_surface.py tests/contract/test_public_surface_registry.py scripts/audit_plan_compliance.py
```

Result: 3 files already formatted.

## QA

Command:

```bash
tmux new-session -d -s ulw-qa-prd-1 'cd <repo> && uv run python scripts/audit_plan_compliance.py --plan .omo/plans/codescent-prd-remainder.md --evidence .omo/evidence > .omo/evidence/prd-remainder-task-1-public-surface.json'
```

Result: `.omo/evidence/prd-remainder-task-1-public-surface.json` reports
`ok: true`, `tool_surface_ok: true`, no missing evidence, and no user decision
gaps.

Command:

```bash
uv run python -m json.tool .omo/evidence/prd-remainder-task-1-public-surface.json >/dev/null
```

Result: valid JSON.

Command:

```bash
uv run pytest tests/contract/test_public_surface_registry.py::test_post_mvp_surface_is_declared_but_not_registered -q
```

Result: 1 passed.

Command:

```bash
uv run pytest tests/contract/test_mcp_tool_surface.py::test_no_post_mvp_tools_exposed -q
```

Result: 1 passed.

Malformed plan check:

```bash
uv run python scripts/audit_plan_compliance.py --plan .omo/plans/does-not-exist.md --evidence .omo/evidence
```

Result: exited 1 with `FileNotFoundError`, proving missing plan input is
rejected.

Cleanup: tmux session `ulw-qa-prd-1` exited; `tmux has-session -t ulw-qa-prd-1`
returned 1.
