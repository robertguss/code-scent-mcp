# Plan 005: Bound source-file input reads

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the next
> step. If anything in the STOP conditions section occurs, stop and report. Do
> not improvise.
>
> **Drift check (run first)**:
> `git diff --stat b93cbcf..HEAD -- src/codescent/engine/inventory.py src/codescent/engine/context/ranges.py src/codescent/engine/rules/python.py src/codescent/engine/rules/ts_react_next.py src/codescent/services/search.py src/codescent/services/search_queries.py tests/integration/test_search.py tests/integration/test_context.py tests/integration/test_scan_code_health.py tests/security/test_runtime_safety.py plans/README.md`
> If any in-scope file changed since this plan was written, compare the Current
> state excerpts against live code before proceeding; on a mismatch, treat it as
> a STOP condition.

## Status

- **Priority**: P1
- **Effort**: M/L
- **Risk**: MED
- **Depends on**: `plans/004-index-backed-context.md`
- **Category**: security | perf
- **Planned at**: commit `b93cbcf`, 2026-06-14

## Why This Matters

CodeScent's public outputs are bounded, but several input paths still read
entire supported source files into memory. A repo with one very large `.py`,
`.ts`, `.tsx`, `.js`, or `.jsx` file can stall indexing, search, context, or
scan operations even when the returned payload is small. Adding a shared
source-read budget protects the local daemon and makes the bounded-output
promise more honest.

## Current State

Current full-file read sites include:

```python
# src/codescent/engine/inventory.py:61-73
for path in sorted(repo_root.rglob("*")):
    if not path.is_file() or _is_excluded(repo_root, path, project_config):
        continue
    ...
    content = path.read_bytes()
    if _is_binary(content):
        continue
```

```python
# src/codescent/services/search.py:111-113
for item in build_file_inventory(repo_root, config=config):
    lines = (repo_root / item.path).read_text().splitlines()
    for line_number, line in enumerate(lines):
```

```python
# src/codescent/services/search_queries.py:44-46, 76-80
for item in build_file_inventory(repo_root, config=project_config):
    lines = (repo_root / item.path).read_text().splitlines()
...
lines = (repo_root / item.path).read_text().splitlines()
```

```python
# src/codescent/engine/context/ranges.py:29-31
capped_end = min(end_line, start_line + max(line_cap, 1) - 1)
lines = (repo_root / relative_path).read_text().splitlines()
selected = lines[start_line - 1 : capped_end]
```

```python
# src/codescent/engine/rules/python.py:39-45
for item in build_file_inventory(repo_root, config=project_config):
    if item.language != "python":
        continue
    parsed = parse_python_file(repo_root / item.path, item.path)
    source_path = repo_root / parsed.path
    lines = source_path.read_text().splitlines()
```

```python
# src/codescent/engine/rules/ts_react_next.py:34-38
for item in inventory:
    if item.language not in {"javascript", "typescript"}:
        continue
    parsed = parse_typescript_file(repo_root / item.path, item.path)
    lines = (repo_root / item.path).read_text().splitlines()
```

Repo conventions to preserve:

- Runtime must remain source-read-only.
- Runtime no-network must remain true.
- Outputs should be bounded by default.
- Fixture repos are intentionally flawed inputs; do not edit them.

## Commands You Will Need

| Purpose            | Command                                                                                                                                                                                                                                                                                                                                                                                                     | Expected on success                                                                |
| ------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------- |
| Search tests       | `uv run pytest tests/integration/test_search.py`                                                                                                                                                                                                                                                                                                                                                            | exit 0                                                                             |
| Context tests      | `uv run pytest tests/integration/test_context.py tests/contract/test_mcp_context_tools.py`                                                                                                                                                                                                                                                                                                                  | exit 0                                                                             |
| Scan tests         | `uv run pytest tests/integration/test_scan_code_health.py tests/integration/test_ts_react_next_rules.py`                                                                                                                                                                                                                                                                                                    | exit 0                                                                             |
| Safety tests       | `uv run pytest tests/security/test_runtime_safety.py`                                                                                                                                                                                                                                                                                                                                                       | exit 0 or dashboard smoke skipped only for missing Chrome as pre-existing behavior |
| Deterministic eval | `uv run python evals/run_deterministic.py --repo tests/fixtures/python-basic --expected evals/fixtures/python-basic.expected.json --out .omo/evidence/plan-005-deterministic-eval.json`                                                                                                                                                                                                                     | exit 0                                                                             |
| Lint changed files | `uv run ruff check src/codescent/engine/inventory.py src/codescent/engine/context/ranges.py src/codescent/engine/rules/python.py src/codescent/engine/rules/ts_react_next.py src/codescent/services/search.py src/codescent/services/search_queries.py tests/integration/test_search.py tests/integration/test_context.py tests/integration/test_scan_code_health.py tests/security/test_runtime_safety.py` | exit 0                                                                             |
| Typecheck          | `uv run basedpyright`                                                                                                                                                                                                                                                                                                                                                                                       | exit 0                                                                             |

## Scope

**In scope**:

- `src/codescent/engine/inventory.py`
- `src/codescent/engine/context/ranges.py`
- `src/codescent/engine/rules/python.py`
- `src/codescent/engine/rules/ts_react_next.py`
- `src/codescent/services/search.py`
- `src/codescent/services/search_queries.py`
- A small shared helper module if needed under `src/codescent/engine/` or
  `src/codescent/core/`
- Tests under `tests/integration/`, `tests/contract/`, and `tests/security/`
  that cover the cap
- `plans/README.md` status row

**Out of scope**:

- Do not add network access, background workers, or external indexing services.
- Do not change public tool names or remove existing bounded output fields.
- Do not silently include huge file content in returned payloads.
- Do not edit checked-in fixture source.
- Do not use this plan to implement dashboard smoke portability or docs cleanup.

## Git Workflow

- Suggested branch: `advisor/005-bounded-source-reads`.
- Commit style, if requested: `fix(safety): bound source file reads`.
- Do not push or open a PR unless instructed.

## Steps

### Step 1: Add oversized-file regression tests

Add tests using `tmp_path` repos with one source file larger than the chosen
byte budget. Cover at least:

- Inventory/indexing does not read/process the huge file as normal source.
- `SearchService.search_content()` does not materialize the huge file and still
  returns results from normal-sized files.
- `source_range()` returns a bounded result or a structured bounded error for an
  oversized file.
- Python and TS rule scans do not hang or crash on oversized supported files.

Do not create huge committed fixtures; generate test files under `tmp_path`.

**Verify**: targeted tests fail before implementation, without modifying
checked-in source.

### Step 2: Introduce a shared source-read budget helper

Add a small helper with explicit constants, for example:

- `MAX_SOURCE_BYTES`
- `read_source_text(path: Path) -> str | None` or a typed result that marks
  oversized files
- `read_source_lines(path: Path) -> tuple[str, ...] | None`

Keep behavior deterministic. If a file exceeds the budget, skip it or return a
bounded warning according to the caller's current payload shape. Do not add
broad exception swallowing.

**Verify**: unit or integration tests for the helper pass.

### Step 3: Apply the helper to inventory and scans

Update `build_file_inventory()` so oversized supported files are excluded or
marked generated/skipped according to existing model constraints. Because
`IndexedFile` has no skip-reason field today, prefer excluding oversized files
unless adding a field is explicitly necessary and covered by tests.

Update Python and TS rule scanners to use the helper for line reads. If parsing
still reads the whole file internally, STOP and report; do not claim the cap
protects scans until parser reads are also bounded or oversized files are
excluded before parsing.

**Verify**:
`uv run pytest tests/integration/test_scan_code_health.py tests/integration/test_ts_react_next_rules.py`
-> exit 0.

### Step 4: Apply the helper to search and source ranges

Update `search_content`, TODO search, test search, and `source_range()` to use
bounded line reads. Preserve current behavior for normal files.

For oversized files, ensure search skips the file rather than returning partial
misleading matches unless the tests explicitly define partial behavior.

**Verify**:
`uv run pytest tests/integration/test_search.py tests/integration/test_context.py tests/contract/test_mcp_context_tools.py`
-> exit 0.

### Step 5: Run safety, eval, and static checks

Run the remaining commands from the command table.

**Verify**: all commands exit 0, with only the existing Chrome skip allowed in
the dashboard smoke safety test.

## Test Plan

- Generate oversized files under `tmp_path`; do not commit large fixtures.
- Add tests for inventory/index, search, context source ranges, and rule scans.
- Preserve existing deterministic eval behavior on normal fixtures.
- Run security tests to ensure source-read-only and no-network guarantees remain
  intact.

## Done Criteria

- [ ] Oversized supported source files cannot force normal
      index/search/context/scan paths to materialize the entire file.
- [ ] Normal-sized fixture behavior remains unchanged.
- [ ] Focused pytest commands exit 0.
- [ ] Deterministic eval exits 0.
- [ ] Ruff and BasedPyright commands exit 0.
- [ ] No files outside the in-scope list are modified.
- [ ] `plans/README.md` status row for 005 is updated.

## STOP Conditions

Stop and report if:

- Parser functions still read oversized files before the new cap can apply.
- A bounded-read change requires altering public payload schemas across multiple
  MCP tools.
- The only viable fix requires adding persisted schema fields beyond a local
  helper and tests.
- Safety tests reveal source modifications outside `.codescent/`.
- Focused tests fail twice after reasonable fixes.

## Maintenance Notes

- The chosen byte budget should become a named constant and, eventually, a
  documented config value if users need control. Do not add config surface in
  this plan unless required by tests.
- Reviewers should check that skipped oversized files do not create false
  confidence. If a warning surface is added, it must be bounded and documented
  by tests.
