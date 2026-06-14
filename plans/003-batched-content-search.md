# Plan 003: Batch multi-query content search

> **Executor instructions**: Follow this plan step by step. Run every verification command and confirm the expected result before moving to the next step. If anything in the STOP conditions section occurs, stop and report. Do not improvise.
>
> **Drift check (run first)**: `git diff --stat b93cbcf..HEAD -- src/codescent/services/search.py src/codescent/services/search_support.py src/codescent/mcp/search_tools.py tests/integration/test_search.py tests/contract/test_mcp_search_tools.py plans/README.md`
> If any in-scope file changed since this plan was written, compare the Current state excerpts against live code before proceeding; on a mismatch, treat it as a STOP condition.

## Status

- **Priority**: P1
- **Effort**: M
- **Risk**: MED
- **Depends on**: none
- **Category**: perf
- **Planned at**: commit `b93cbcf`, 2026-06-14

## Why This Matters

`multi_search_content` is an agent-facing batching tool, but today it loops over queries and calls `search_content()` for each one. Each call rebuilds inventory and scans every line of every indexed file. Batching should reduce total work by scanning files once and evaluating all queries during that pass while preserving bounded output and ranking reasons.

## Current State

- `src/codescent/services/search.py` owns file/content search behavior.
- `src/codescent/services/search_support.py` owns ranking helpers, limits, pagination, and frecency.
- `src/codescent/mcp/search_tools.py` exposes `multi_search_content` to MCP clients.
- `tests/integration/test_search.py` and `tests/contract/test_mcp_search_tools.py` already cover bounded multi-search behavior.

Current per-query scan:

```python
# src/codescent/services/search.py:156-188
    page = PageOptions(limit=limit)
    merged: dict[str, SearchResultPayload] = {}
    for query in queries:
        for result in self.search_content(query, limit=MAX_LIMIT, line_budget=line_budget):
            existing = merged.get(result["path"])
            reasons = merge_reasons(result["reasons"], (f"query:{query}",))
            ...
    return tuple(sort_results(list(merged.values()))[: page.limit])
```

`search_content()` scans all inventory items and all file lines:

```python
# src/codescent/services/search.py:111-136
for item in build_file_inventory(repo_root, config=config):
    lines = (repo_root / item.path).read_text().splitlines()
    for line_number, line in enumerate(lines):
        if match_text(line, query) is None:
            continue
        ...
selected = tuple(sort_results(results)[page.offset : page.offset + page.limit])
record_frecency(repo_root, query, tuple(result["path"] for result in selected))
```

Repo conventions to preserve:

- Search outputs are bounded by default.
- Reasons are part of the public contract and should remain deterministic.
- Frecency writes are runtime state under `.codescent/`, not source changes.

## Commands You Will Need

| Purpose | Command | Expected on success |
|---------|---------|---------------------|
| Search integration tests | `uv run pytest tests/integration/test_search.py` | exit 0 |
| MCP search contract tests | `uv run pytest tests/contract/test_mcp_search_tools.py` | exit 0 |
| Lint changed files | `uv run ruff check src/codescent/services/search.py src/codescent/services/search_support.py src/codescent/mcp/search_tools.py tests/integration/test_search.py tests/contract/test_mcp_search_tools.py` | exit 0 |
| Typecheck | `uv run basedpyright` | exit 0 |

## Scope

**In scope**:

- `src/codescent/services/search.py`
- `src/codescent/services/search_support.py` if helper extraction is needed
- `src/codescent/mcp/search_tools.py` only if payload typing needs adjustment
- `tests/integration/test_search.py`
- `tests/contract/test_mcp_search_tools.py`
- `plans/README.md` status row

**Out of scope**:

- Do not change MCP tool names or the output field names.
- Do not change single-query `search_content()` semantics except via shared helpers.
- Do not implement persisted full-text search here; Plan 004 handles persisted-index context work.
- Do not remove frecency recording.

## Git Workflow

- Suggested branch: `advisor/003-batched-content-search`.
- Commit style, if requested: `perf(search): batch multi-query content scans`.
- Do not push or open a PR unless instructed.

## Steps

### Step 1: Add a regression test that proves one inventory pass

In `tests/integration/test_search.py`, add a test for `SearchService(repo).multi_search_content(("TODO", "billing"), limit=...)` that verifies behavior and guards against calling `search_content()` once per query. Use `monkeypatch` on `SearchService.search_content` or a helper seam if available. The cleanest test is to monkeypatch `codescent.services.search.build_file_inventory` and count calls during `multi_search_content`; expected count is 1 after the refactor.

Keep or extend existing assertions that merged results include `query:<query>` reasons.

**Verify**: `uv run pytest tests/integration/test_search.py` -> new call-count test fails before implementation, existing tests run.

### Step 2: Implement one-pass multi-query scanning

In `src/codescent/services/search.py`, rewrite `multi_search_content()` so it:

1. Resolves repo root and config once.
2. Loads changed files and frecency once.
3. Iterates each inventory item once.
4. Reads each file once.
5. Checks every line against every query.
6. Merges by path with deterministic score, reasons, and snippet selection.
7. Records frecency for selected paths for each query, or records a combined query signal only if existing frecency tests are updated to cover the new behavior.

Preserve current public behavior:

- Results remain path-deduped.
- Reasons include `query:<query>`.
- Result count respects `PageOptions(limit=limit)`.
- Snippets remain bounded by `line_budget`.

**Verify**: `uv run pytest tests/integration/test_search.py` -> exit 0.

### Step 3: Protect MCP behavior

Run and, if needed, extend `tests/contract/test_mcp_search_tools.py` so the MCP `multi_search_content` payload still merges and dedupes bounded results.

**Verify**: `uv run pytest tests/contract/test_mcp_search_tools.py` -> exit 0.

### Step 4: Run static checks

Run the lint and typecheck commands from the command table.

**Verify**: both exit 0.

## Test Plan

- Add a one-pass regression test in `tests/integration/test_search.py`.
- Preserve existing result-shape assertions for merged reasons and bounded output.
- Run MCP search contract tests for transport-level payload compatibility.

## Done Criteria

- [ ] `multi_search_content()` scans inventory once per call, not once per query.
- [ ] `query:<query>` reasons remain in merged results.
- [ ] Focused pytest commands exit 0.
- [ ] Ruff and BasedPyright commands exit 0.
- [ ] No files outside the in-scope list are modified.
- [ ] `plans/README.md` status row for 003 is updated.

## STOP Conditions

Stop and report if:

- Preserving frecency behavior requires a larger design decision than local helper changes.
- MCP contract output changes in a way that requires docs/public-surface updates.
- The one-pass implementation requires touching storage schema or adding new runtime state.
- Focused tests fail twice after reasonable fixes.

## Maintenance Notes

- Plan 005 will later add input read caps. Keep this plan focused on pass count and merge semantics, not read-size policy.
- Reviewers should compare old and new ranking behavior on multi-query tests, especially when the same file matches multiple queries.
