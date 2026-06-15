# Plan 012: Add `select_tests` — minimal verification set for a change

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving on. If a
> STOP condition occurs, stop and report — do not improvise. When done, update
> the status row for this plan in `plans/README.md`.
>
> **Drift check (run first)**:
> `git diff --stat 40cbf50..HEAD -- src/codescent/services/verification.py src/codescent/mcp/planning_tools.py src/codescent/core/public_surface.py tests/contract tests/integration docs/mcp-tools.md plans/README.md`
> If any in-scope file changed, compare excerpts against live code; on a
> mismatch, treat it as a STOP condition.

## Status

- **Priority**: P1
- **Effort**: M
- **Risk**: MED
- **Depends on**: none
- **Category**: direction (new MCP tool) / tests
- **Planned at**: commit `40cbf50`, 2026-06-15

## Why this matters

`suggest_tests` answers "tests near this one file." It cannot answer the
question agents and CI actually need: "given everything I changed, what is the
smallest set of tests that exercises it?" By walking the import/related-file
graph from the changed files to their related test files, CodeScent can emit a
single focused `pytest` command — slashing CI time and giving agents a fast
inner loop instead of running the whole suite or skipping tests.

## Current state

- `suggest_tests` is per-file and basic:

```python
# src/codescent/services/verification.py:34-42
    def suggest_tests(self, file_path: str) -> SuggestedTests:
        context = ContextService(self.repo_root).get_file_context(file_path)
        likely_tests = context["likely_tests"]
        commands = tuple(f"pytest {path}" for path in likely_tests)
        return SuggestedTests(commands=commands or ("pytest",), likely_tests=likely_tests, executes_in_v1=False)
```

- The graph signals already exist:
  - `ContextService.get_related_files(path, limit=...)` returns related files
    with reasons including `import_graph`, `test_match`, and (after plan 006)
    `co_change` (`services/context.py:204-243`).
  - `git_changed_paths(repo_root)` returns the worktree's changed files
    (`services/git.py:54-83`).

- The MCP tool registration pattern (thin function + `TypedDict` payload + a
  `register_*_tools(mcp)` that calls `mcp.tool(description=...)(fn)`) is in
  `src/codescent/mcp/planning_tools.py:75-149`.

- Public surface is a frozen registry; new MCP tools MUST be added in
  `src/codescent/core/public_surface.py` (both the `POST_MVP_MCP_TOOL_NAMES`/
  `REGISTERED_POST_MVP_MCP_TOOL_NAMES` frozensets and the `PUBLIC_SURFACE`
  tuple) or contract tests fail. See `public_surface.py:72-118` and `148-184`.

Repo conventions: MCP tools are thin adapters over services; bounded output;
read-only for source; tool descriptions are contract text.

## Commands you will need

| Purpose | Command | Expected |
|---|---|---|
| Contract tests | `uv run pytest tests/contract` | exit 0 |
| Focused tests | `uv run pytest tests -k "select_tests or test_impact"` | exit 0 |
| Full tests | `uv run pytest` | exit 0 |
| Lint | `uv run ruff check .` | exit 0 |
| Format | `uv run ruff format --check .` | exit 0 |
| Typecheck | `uv run basedpyright` | exit 0 |

## Scope

**In scope**:
- `src/codescent/services/verification.py` — add `select_tests(...)` to
  `VerificationService`.
- `src/codescent/mcp/planning_tools.py` — register a `select_tests` MCP tool.
- `src/codescent/core/public_surface.py` — register the new tool name.
- `docs/mcp-tools.md` — add the tool reference entry (match existing format).
- `tests/contract/` and `tests/integration/` — contract + behavior tests.
- `plans/README.md` status row.

**Out of scope**:
- Do NOT execute pytest or any project command (recommend-only, like
  `verify_change`). `executes_in_v1` stays `False`.
- Do NOT change `suggest_tests` behavior or shape.
- Do NOT add a CLI command in this plan (MCP + service only).
- `tests/fixtures/` source.

## Steps

### Step 1: Implement `select_tests` in the service

Add to `VerificationService`:

```python
@dataclass(frozen=True, slots=True)
class SelectedTests:
    changed_files: tuple[str, ...]
    test_files: tuple[str, ...]
    command: str
    executes_in_v1: bool

def select_tests(self, *, paths: tuple[str, ...] | None = None) -> SelectedTests:
    """Map changed (or given) files to the minimal set of related test files.

    If ``paths`` is None, use ``git_changed_paths``. For each path, gather
    related files whose reason includes a test signal (test_match) or whose
    path is itself a test, via ContextService.get_related_files. Deduplicate
    and build a single ``pytest <files...>`` command.
    """
```
Implementation:
- Resolve `repo_root`. `changed = paths or tuple(sorted(git_changed_paths(repo_root)))`.
- For each changed python source file, call
  `ContextService(repo_root).get_related_files(path, limit=20)` and collect
  result paths that are tests (path startswith `tests/` or matches the repo's
  test convention) — also include `get_file_context(path)["likely_tests"]`.
- Also include any changed path that is itself a test file directly.
- Dedupe (`dict.fromkeys`), sort. `command = "pytest " + " ".join(test_files)`
  or `"pytest"` if none found. `executes_in_v1=False`.
- Import `git_changed_paths`, `ContextService`, `resolve_repo_root` at module top
  (no inline imports).

### Step 2: Register the MCP tool

In `planning_tools.py`, add a `SelectTestsToolPayload(TypedDict)` and a thin
`select_tests(repo: str = ".", paths: tuple[str, ...] | None = None)` function,
and register it inside `register_planning_tools` with a description like:

> "Use CodeScent to compute the minimal set of tests for the current changes (or
> given paths) and a single focused command. Recommend-only; does not execute
> tests."

Follow the exact pattern of `suggest_tests`/`verify_change` in the same file
(payload dict builder + `mcp.tool(description=...)(select_tests)`).

### Step 3: Register on the public surface

In `core/public_surface.py`: add `"select_tests"` to `POST_MVP_MCP_TOOL_NAMES`
and `REGISTERED_POST_MVP_MCP_TOOL_NAMES`, and add
`_registered_post_mvp_entry("select_tests", "planning")` to the
`PUBLIC_SURFACE.mcp_tools` tuple.

**Verify**: `uv run pytest tests/contract` → exit 0 (contract tests confirm the
registered surface matches).

### Step 4: Docs

Add a `### select_tests` entry to `docs/mcp-tools.md` matching the existing
reference block format (Group: planning; recommend-only; bounded).

### Step 5: Tests

- Integration: temp repo with `src/app/x.py`, `tests/test_x.py`, and an unrelated
  `tests/test_y.py`. With `x.py` "changed", assert `select_tests(paths=("src/app/x.py",))`
  returns `test_files == ("tests/test_x.py",)` and `command == "pytest tests/test_x.py"`.
- Edge: no related tests → `command == "pytest"`.
- Contract: the registered tool surface includes `select_tests`.

**Verify**: `uv run pytest`, `ruff check .`, `ruff format --check .`,
`basedpyright` → all exit 0.

## Test plan

- Changed file → its test only (not unrelated tests).
- No related tests → fallback `pytest`.
- Contract test sees `select_tests`.
- Verification: `uv run pytest` → all pass.

## Done criteria

- [ ] `select_tests` MCP tool registered and listed in `public_surface.py` and
      `docs/mcp-tools.md`.
- [ ] Returns a single focused command from changed/related test mapping;
      `executes_in_v1` is `False`.
- [ ] `uv run pytest`, `ruff check`, `ruff format --check`, `basedpyright` exit 0.
- [ ] No project command executed; no source edited; `tests/fixtures/` untouched.
- [ ] `plans/README.md` status row for 012 updated.

## STOP conditions

Stop and report if:
- Contract tests reference an additional registry (e.g. a separate JSON/docs
  list) that must also be updated and is not in scope — report what else needs
  the name.
- `get_related_files` does not expose enough signal to find the test reliably
  for this repo's test layout — report; you may need plan 006 landed first.
- Verification fails twice after a reasonable fix.

## Maintenance notes

- Once landed, `CiService` (`services/ci.py`) and `review_diff_risk` should
  prefer `select_tests` output over `("pytest",)` — a worthwhile follow-up.
- Precision improves when plan 006 (co-change) is in; note that dependency.
- Reviewers should confirm the tool never executes anything and output is
  bounded.
