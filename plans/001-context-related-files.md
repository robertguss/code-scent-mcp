# Plan 001: Fix file-context related files

> **Executor instructions**: Follow this plan step by step. Run every verification command and confirm the expected result before moving to the next step. If anything in the STOP conditions section occurs, stop and report. Do not improvise.
>
> **Drift check (run first)**: `git diff --stat b93cbcf..HEAD -- src/codescent/services/context.py src/codescent/services/context_support.py src/codescent/mcp/context_tools.py tests/integration/test_context.py tests/contract/test_mcp_context_tools.py plans/README.md`
> If any in-scope file changed since this plan was written, compare the Current state excerpts against live code before proceeding; on a mismatch, treat it as a STOP condition.

## Status

- **Priority**: P1
- **Effort**: S
- **Risk**: LOW/MED
- **Depends on**: none
- **Category**: bug
- **Planned at**: commit `b93cbcf`, 2026-06-14

## Why This Matters

`get_file_context` exposes both `likely_tests` and `related_files`, but today `related_files` is just a duplicate of likely tests. Agents that ask for bounded context before reading a file miss import, directory, search-similarity, and git-history relationships even though CodeScent already has a `get_related_files` implementation. Fixing this first creates behavior coverage for later context refactors.

## Current State

- `src/codescent/services/context.py` owns the service payloads used by CLI/MCP/dashboard paths.
- `src/codescent/services/context_support.py` owns related-file scoring helpers.
- `src/codescent/mcp/context_tools.py` passes the service payload through to MCP clients.
- `tests/integration/test_context.py` already tests `get_related_files` separately.
- `tests/contract/test_mcp_context_tools.py` checks that MCP context tools do not dump whole files.

Current `get_file_context` computes tests and assigns them to both fields:

```python
# src/codescent/services/context.py:76-88
parsed = file_by_path(files, relative_path)
tests = likely_tests(files, parsed)
return {
    "path": parsed.path,
    "summary": file_summary(parsed),
    "symbols": tuple(symbol.name for symbol in parsed.symbols),
    "imports": tuple(
        import_text(imported.module, imported.name)
        for imported in parsed.imports
    ),
    "likely_tests": tests,
    "related_files": tests,
```

The real related-file computation exists later in the same service:

```python
# src/codescent/services/context.py:220-232
for related_path in likely_tests(files, target):
    add_related_reason(reasons, related_path, "test_match")
for candidate in files:
    if candidate.path == target.path:
        continue
    if imports_between(target, candidate):
        add_related_reason(reasons, candidate.path, "import_graph")
    if same_directory(target.path, candidate.path):
        add_related_reason(reasons, candidate.path, "directory_proximity")
    if similar_source_terms(target, candidate):
        add_related_reason(reasons, candidate.path, "search_similarity")
for related_path in git_related_paths(repo_root, target.path):
    add_related_reason(reasons, related_path, "git_history")
```

Repo conventions to preserve:

- Keep MCP adapters thin; service code should compute payloads.
- Keep output bounded; do not add source dumps.
- Use `uv run ...` commands for verification.

## Commands You Will Need

| Purpose | Command | Expected on success |
|---------|---------|---------------------|
| Focused integration tests | `uv run pytest tests/integration/test_context.py` | exit 0 |
| Focused MCP contract tests | `uv run pytest tests/contract/test_mcp_context_tools.py` | exit 0 |
| Lint changed files | `uv run ruff check src/codescent/services/context.py src/codescent/services/context_support.py src/codescent/mcp/context_tools.py tests/integration/test_context.py tests/contract/test_mcp_context_tools.py` | exit 0 |
| Typecheck | `uv run basedpyright` | exit 0 |

## Scope

**In scope**:

- `src/codescent/services/context.py`
- `src/codescent/services/context_support.py` if a helper extraction is needed
- `src/codescent/mcp/context_tools.py` only if the MCP payload type needs adjustment
- `tests/integration/test_context.py`
- `tests/contract/test_mcp_context_tools.py`
- `plans/README.md` status row

**Out of scope**:

- Do not change the shape of `get_related_files` results.
- Do not add full source content to `get_file_context`.
- Do not refactor `SymbolService.extract()` or persisted-index behavior here; that is Plan 004.
- Do not touch fixture source under `tests/fixtures/`.

## Git Workflow

- Suggested branch: `advisor/001-context-related-files`.
- Recent commits use concise conventional-style messages such as `fix(config): honor project excludes in inventory`; match that style if committing is requested.
- Do not push or open a PR unless instructed.

## Steps

### Step 1: Add characterization tests

In `tests/integration/test_context.py`, extend or add a test using the existing temporary git repo from `test_related_files_include_import_test_directory_and_git_reasons`. Assert that `ContextService(repo).get_file_context("src/app.py")` returns:

- `likely_tests` containing `tests/test_app.py`.
- `related_files` containing `tests/test_app.py`, `src/helper.py`, and `src/view.py`.
- `related_files` is not merely equal to `likely_tests` when non-test related files exist.

In `tests/contract/test_mcp_context_tools.py`, update `ContextToolPayload` to include `related_files: tuple[str, ...] = ()` and add an MCP assertion that `get_file_context` exposes the field without full source dumps.

**Verify**: `uv run pytest tests/integration/test_context.py tests/contract/test_mcp_context_tools.py` -> tests fail before implementation because `related_files` only mirrors `likely_tests`, then pass after Step 2.

### Step 2: Compute related file paths from the existing related logic

In `src/codescent/services/context.py`, extract the related-reason building logic used by `get_related_files` into a private helper that accepts `repo_root`, `files`, and `target` and returns `dict[str, set[str]]`. Use that helper from both `get_file_context` and `get_related_files`.

For `get_file_context`, convert the helper output into sorted related file paths using the same ordering as `_related_rows`, then return only paths in the `related_files` tuple. Keep `likely_tests` unchanged.

**Verify**: `uv run pytest tests/integration/test_context.py tests/contract/test_mcp_context_tools.py` -> exit 0.

### Step 3: Run static checks

Run the focused lint and typecheck commands from the command table.

**Verify**: both commands exit 0.

## Test Plan

- Add/extend `tests/integration/test_context.py` to prove file context now includes non-test related files.
- Add/extend `tests/contract/test_mcp_context_tools.py` to protect the MCP payload and bounded-output behavior.
- Reuse the existing git-backed temporary repo pattern in `test_related_files_include_import_test_directory_and_git_reasons`.

## Done Criteria

- [ ] `uv run pytest tests/integration/test_context.py tests/contract/test_mcp_context_tools.py` exits 0.
- [ ] `uv run ruff check ...` for in-scope files exits 0.
- [ ] `uv run basedpyright` exits 0.
- [ ] `get_file_context("src/app.py")` can return non-test related files when they exist.
- [ ] No files outside the in-scope list are modified.
- [ ] `plans/README.md` status row for 001 is updated.

## STOP Conditions

Stop and report if:

- The current code no longer assigns `"related_files": tests` in `get_file_context`.
- Fixing the bug requires changing public MCP tool names or removing payload fields.
- A related-file test requires modifying checked-in fixture repos.
- Focused tests fail twice after reasonable fixes.

## Maintenance Notes

- Plan 004 will revisit related-file internals while moving context lookups toward the persisted index. Keep this fix small and behavior-focused so it can serve as a regression guard.
- Reviewers should check that related files remain bounded and that no source snippets were added to the file-context response.
