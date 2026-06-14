# Plan 004: Use the persisted index for context lookups

> **Executor instructions**: Follow this plan step by step. Run every verification command and confirm the expected result before moving to the next step. If anything in the STOP conditions section occurs, stop and report. Do not improvise.
>
> **Drift check (run first)**: `git diff --stat b93cbcf..HEAD -- src/codescent/services/symbols.py src/codescent/services/context.py src/codescent/services/context_support.py src/codescent/services/repo_index.py src/codescent/storage/schema.py tests/integration/test_context.py tests/integration/test_repo_index.py tests/contract/test_mcp_context_tools.py plans/README.md`
> If any in-scope file changed since this plan was written, compare the Current state excerpts against live code before proceeding; on a mismatch, treat it as a STOP condition.

## Status

- **Priority**: P1
- **Effort**: L
- **Risk**: MED
- **Depends on**: `plans/001-context-related-files.md`, `plans/003-batched-content-search.md`
- **Category**: perf | tech-debt
- **Planned at**: commit `b93cbcf`, 2026-06-14

## Why This Matters

CodeScent's product thesis is to build and maintain a local index, then expose fast bounded code intelligence through MCP. Several context paths still rebuild inventory and reparse source files on every request even though `RepoIndexService.index_repo()` persists files, symbols, references, and call edges into SQLite. Moving hot context lookups onto the persisted index reduces repo-size latency and aligns implementation with the documented architecture.

## Current State

- `src/codescent/services/repo_index.py` indexes files and persists `files`, `symbols`, `symbol_references`, and `call_edges`.
- `src/codescent/services/symbols.py` reparses all supported files every time `extract()` is called.
- `src/codescent/services/context.py` calls `SymbolService.extract()` from `find_symbol`, `get_file_context`, `get_symbol_context`, and `get_related_files`.
- `src/codescent/storage/schema.py` has an `imports` table, but `RepoIndexService` currently does not populate it.
- Graph functions already query persisted tables via `ensure_graph_indexed()`.

Current full-repo reparse:

```python
# src/codescent/services/symbols.py:26-35
    repo_root = resolve_repo_root(self.repo_root)
    config = ConfigService(repo_root).load()
    registry = build_pack_registry(config)
    parsed_files = tuple(
        parser(repo_root / item.path, item.path)
        for item in build_file_inventory(repo_root, config=config)
        for parser in (registry.parser_for_language(item.language),)
        if parser is not None
    )
    return SymbolExtraction(files=parsed_files)
```

Context hot paths use it:

```python
# src/codescent/services/context.py:61-76
files = SymbolService(self.repo_root).extract().files
matches = [
    symbol_payload(parsed, symbol)
    for parsed in files
    for symbol in parsed.symbols
    if matches_symbol(query, symbol)
]
...
files = SymbolService(repo_root).extract().files
parsed = file_by_path(files, relative_path)
```

The persisted schema already has relevant tables:

```sql
-- src/codescent/storage/schema.py:9-35, 141-164
create table if not exists files (... path text not null unique, language text not null, ...)
create table if not exists symbols (... file_id integer not null references files(id), name text not null, qualified_name text not null, kind text not null, start_line integer not null, end_line integer not null, confidence real not null)
create table if not exists symbol_references (...)
create table if not exists call_edges (...)
```

Repo conventions to preserve:

- CLI/MCP/dashboard adapters stay thin; services own behavior.
- Local runtime state belongs under `.codescent/`.
- Outputs stay bounded and source-read-only.

## Commands You Will Need

| Purpose | Command | Expected on success |
|---------|---------|---------------------|
| Context integration tests | `uv run pytest tests/integration/test_context.py` | exit 0 |
| Index persistence tests | `uv run pytest tests/integration/test_repo_index.py` | exit 0 |
| MCP context contract tests | `uv run pytest tests/contract/test_mcp_context_tools.py` | exit 0 |
| Deterministic eval | `uv run python evals/run_deterministic.py --repo tests/fixtures/python-basic --expected evals/fixtures/python-basic.expected.json --out .omo/evidence/plan-004-deterministic-eval.json` | exit 0 |
| Lint changed files | `uv run ruff check src/codescent/services/symbols.py src/codescent/services/context.py src/codescent/services/context_support.py src/codescent/services/repo_index.py src/codescent/storage/schema.py tests/integration/test_context.py tests/integration/test_repo_index.py tests/contract/test_mcp_context_tools.py` | exit 0 |
| Typecheck | `uv run basedpyright` | exit 0 |

## Scope

**In scope**:

- `src/codescent/services/symbols.py`
- `src/codescent/services/context.py`
- `src/codescent/services/context_support.py`
- `src/codescent/services/repo_index.py`
- `src/codescent/storage/schema.py` only if indexes or migrations are required
- `tests/integration/test_context.py`
- `tests/integration/test_repo_index.py`
- `tests/contract/test_mcp_context_tools.py`
- `plans/README.md` status row

**Out of scope**:

- Do not change public MCP tool names or payload field names.
- Do not implement a new full-text search engine.
- Do not add network access or external parser services.
- Do not change fixture source.
- Do not combine this with source-read caps from Plan 005.

## Git Workflow

- Suggested branch: `advisor/004-index-backed-context`.
- Commit style, if requested: `perf(context): use persisted index for lookups`.
- Do not push or open a PR unless instructed.

## Steps

### Step 1: Add tests that prove context uses the index after indexing

Add or extend tests in `tests/integration/test_context.py` with a temporary repo that is indexed once via `RepoIndexService(repo).index_repo()`. Monkeypatch parser entry points such as `codescent.engine.parsers.python.parse_python_file` or `codescent.engine.packs.build_pack_registry` in a way that would fail if a context lookup reparses source after indexing. Then call:

- `ContextService(repo).find_symbol(...)`
- `ContextService(repo).get_symbol_context(...)`
- `ContextService(repo).get_file_context(...)`

At least `find_symbol` and `get_symbol_context` must use persisted symbols and pass without reparsing. If `get_file_context` still needs a small bounded source read for source ranges, that is acceptable, but it must not reparse the full repo.

**Verify**: `uv run pytest tests/integration/test_context.py` -> new test fails before implementation.

### Step 2: Introduce persisted symbol/file readers

In `src/codescent/services/symbols.py` or a small new repository helper under `src/codescent/services/`, add typed functions that read from SQLite after ensuring the graph is indexed. The readers should return the same payload fields currently exposed by `symbol_payload`:

- `name`
- `qualified_name`
- `kind`
- `path`
- `start_line`
- `end_line`
- `confidence`

Use existing `RepositoryStorage` and `initialize_storage` patterns. Keep SQL bounded with `limit ?` and deterministic ordering.

**Verify**: `uv run pytest tests/integration/test_repo_index.py tests/integration/test_context.py` -> exit 0 for reader tests added in this step.

### Step 3: Move `find_symbol` and `get_symbol_context` to persisted data

Update `ContextService.find_symbol()` to query persisted symbols instead of `SymbolService.extract()`. Update `ContextService.get_symbol_context()` to retrieve the symbol row from persisted symbols and use `source_range()` for the bounded source excerpt.

Preserve behavior:

- `find_symbol(..., limit=...)` still clamps to 1..20.
- Matching remains case-insensitive substring matching on `name` and `qualified_name`.
- Payload field names do not change.

**Verify**: `uv run pytest tests/integration/test_context.py tests/contract/test_mcp_context_tools.py` -> exit 0.

### Step 4: Persist imports or otherwise avoid full-repo parse for file context

`get_file_context()` needs symbols, imports, likely tests, and source ranges. Symbols can come from SQLite. Imports should not require a full repo parse. Either:

1. Populate the existing `imports` table in `RepoIndexService._persist_python_graph()` and add a small reader for file imports, or
2. Add a narrowly scoped parser/read for only the requested file while avoiding `SymbolService.extract()` across the whole repo.

Prefer option 1 because `imports` already exists in `src/codescent/storage/schema.py`.

**Verify**: `uv run pytest tests/integration/test_repo_index.py tests/integration/test_context.py` -> exit 0 and includes an assertion that imports are persisted/read correctly.

### Step 5: Reduce related-file full parsing where practical

Keep the behavior protected by Plan 001. If related-file scoring still needs parsed imports/symbol terms, query persisted files, symbols, imports, and call/reference tables instead of reparsing all files. If this is too large to complete safely in this plan, STOP and report the remaining full-parse path rather than adding a half-compatible fallback.

**Verify**: `uv run pytest tests/integration/test_context.py tests/contract/test_mcp_context_tools.py` -> exit 0.

### Step 6: Run eval and static checks

Run deterministic eval, lint, and typecheck from the command table.

**Verify**: all exit 0.

## Test Plan

- Add regression tests that fail if context lookups reparse the whole repo after indexing.
- Add index persistence tests for imports if Step 4 chooses the existing imports table route.
- Preserve MCP context contract tests.
- Run deterministic eval to protect fixture workflow behavior.

## Done Criteria

- [ ] `find_symbol` and `get_symbol_context` read persisted symbol data after indexing.
- [ ] `get_file_context` no longer calls `SymbolService.extract()` across the full repo.
- [ ] Related-file behavior from Plan 001 remains intact.
- [ ] Focused pytest commands exit 0.
- [ ] Deterministic eval exits 0.
- [ ] Ruff and BasedPyright commands exit 0.
- [ ] No files outside the in-scope list are modified.
- [ ] `plans/README.md` status row for 004 is updated.

## STOP Conditions

Stop and report if:

- The persisted schema lacks data needed to preserve current public context payloads and adding that persistence would require a broad schema redesign.
- MCP contract tests require payload field renames.
- A proposed fallback silently reparses the whole repo on the hot path.
- The fix requires network access, external services, or modifying analyzed source.
- Focused tests fail twice after reasonable fixes.

## Maintenance Notes

- This plan is intentionally larger than the others. Keep commits small if committing is requested: reader tests, symbol readers, context migration, import persistence, then related-file migration.
- Reviewers should scrutinize freshness semantics: if the source changed after indexing, context should either re-index via existing `ensure_graph_indexed()` patterns or clearly report stale state according to existing conventions.
