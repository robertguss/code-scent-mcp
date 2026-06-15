# Plan 011: Ingest coverage data into precise test-gap findings

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving on. If a
> STOP condition occurs, stop and report — do not improvise. When done, update
> the status row for this plan in `plans/README.md`.
>
> **Drift check (run first)**:
> `git diff --stat 40cbf50..HEAD -- src/codescent/services src/codescent/engine/rules src/codescent/core/models.py tests plans/README.md`
> If any in-scope file changed, compare excerpts against live code; on a
> mismatch, treat it as a STOP condition.

## Status

- **Priority**: P1
- **Effort**: M
- **Risk**: LOW/MED
- **Depends on**: none
- **Category**: tests / direction (reliability of test-gap findings)
- **Planned at**: commit `40cbf50`, 2026-06-15

## Why this matters

Today's test-gap signal is heuristic: `python.changed_source_without_related_test`
guesses based on filename convention. If the project already produces a coverage
report locally (`coverage.xml`, Cobertura format), CodeScent can convert a guess
into a fact: "this function spans uncovered lines." Reading an artifact file is
local, no network, no execution — squarely within the read-only ethos — and it
sharply raises the reliability of test-gap findings. It also composes with the
hotspot ranking (uncovered + churny = the best finding to surface).

## Current state

- The heuristic test-gap finding lives in
  `src/codescent/services/code_health.py:152-184`:

```python
# src/codescent/services/code_health.py:152-174
def _changed_source_without_related_tests(changed_files, indexed_paths):
    return tuple(
        build_finding(FindingSpec(
            rule_id="python.changed_source_without_related_test",
            ...
            confidence=0.6,
            evidence={"expected_test": _expected_test_path(path)},
            ...))
        for path in changed_files
        if _is_python_source(path) and _expected_test_path(path) not in indexed_paths
    )
```

- The scan composes findings in `CodeHealthService.scan`
  (`code_health.py:40-50`) and persists them. New findings flow through the same
  insert loop automatically as long as they are `CodeHealthFinding`s.

- `ParsedSymbol` (functions/classes) carries `start_line`/`end_line`, so mapping
  uncovered line numbers to symbols is a range check.

- `FindingSpec.evidence` values are scalar (`int|float|str|bool`).

Repo conventions: strict typing; no network; never edit analyzed source; read
runtime inputs only — coverage files are read-only inputs, not written.

## Commands you will need

| Purpose | Command | Expected |
|---|---|---|
| Focused tests | `uv run pytest tests -k "coverage or uncovered"` | exit 0 |
| Full tests | `uv run pytest` | exit 0 |
| Lint | `uv run ruff check .` | exit 0 |
| Format | `uv run ruff format --check .` | exit 0 |
| Typecheck | `uv run basedpyright` | exit 0 |

## Scope

**In scope**:
- `src/codescent/services/coverage.py` (create) — parse Cobertura `coverage.xml`.
- `src/codescent/engine/rules/coverage_gaps.py` (create) OR a function composed
  into the scan — produce `python.uncovered_symbol` findings.
- `src/codescent/services/code_health.py` — compose coverage findings into the
  scan (only when a coverage file is found).
- `src/codescent/core/models.py` — optional config field for a coverage path.
- `tests/unit/` and `tests/integration/` — coverage parsing + findings.
- `docs/configuration.md` — document the coverage path setting.
- `plans/README.md` status row.

**Out of scope**:
- Do NOT run the project's test suite or `coverage` tool to *generate* the file
  — only read an existing one.
- Do NOT support every coverage format. Support Cobertura `coverage.xml` only
  (the `coverage.py --xml` and `pytest-cov --cov-report=xml` default). LCOV is a
  future plan.
- Do NOT emit any coverage finding when no coverage file exists (zero cost,
  zero noise by default).
- `tests/fixtures/` source.

## Steps

### Step 1: Parse Cobertura XML

Create `src/codescent/services/coverage.py` using the stdlib
`xml.etree.ElementTree` (no new dependency). Implement:

```python
@dataclass(frozen=True, slots=True)
class FileCoverage:
    path: str                       # repo-relative posix path
    uncovered_lines: frozenset[int]

def load_coverage(repo_root: Path, *, coverage_path: str = "coverage.xml") -> tuple[FileCoverage, ...]:
    """Parse a Cobertura coverage.xml at repo_root. Returns () if missing/invalid."""
```
- Cobertura shape: `<coverage><packages><package><classes><class filename="...">
  <lines><line number="N" hits="H"/>...`. Collect lines with `hits == 0`.
- Normalize `filename` to a repo-relative posix path. Cobertura paths may be
  relative to a source root; if a `<sources><source>` element exists, try
  joining, but always reduce to a path that matches the indexed `files.path`
  form. If you cannot confidently match, skip that file (do not guess).
- Return `()` on missing file or any `ParseError`.

### Step 2: Map uncovered lines to symbols and emit findings

Create the rule (or a function in `coverage.py`):

```python
def coverage_findings(repo_root, *, config=None) -> tuple[CodeHealthFinding, ...]:
    coverage = load_coverage(repo_root, coverage_path=...)
    if not coverage:
        return ()
    # for each FileCoverage, parse the file's symbols (parse_python_file),
    # and for each function/method/class symbol whose [start_line, end_line]
    # range overlaps uncovered_lines, emit one finding.
```
Finding shape:
```python
build_finding(FindingSpec(
    rule_id="python.uncovered_symbol",
    title="Uncovered symbol",
    message=f"{symbol.qualified_name} has uncovered lines per coverage.xml.",
    file_path=fc.path,
    symbol=symbol.qualified_name,
    severity="info",
    confidence=0.95,             # coverage data is a fact, not a guess
    evidence={"uncovered_in_symbol": n_uncovered, "start_line": symbol.start_line},
    suggested_action="Add a test exercising the uncovered lines before changing behavior.",
))
```
- Bound output: emit per-symbol, but cap total coverage findings (e.g. 200) to
  avoid flooding; if capped, that is acceptable (most-uncovered first).

### Step 3: Compose into the scan (only when present)

In `CodeHealthService.scan` (`code_health.py:44-50`), add coverage findings to
the `findings` tuple, e.g.:

```python
        findings = (
            *registry.scan_rule_packs(state.repo_root),
            *_changed_source_without_related_tests(...),
            *coverage_findings(state.repo_root, config=ConfigService(state.repo_root).load()),
        )
```
`coverage_findings` returns `()` when no coverage file exists, so default
behavior is unchanged.

### Step 4: Optional config field

In `core/models.py`, add to `ProjectConfig` (or to `CommandHints`/a new model) a
`coverage_path: str = "coverage.xml"` so projects can point elsewhere. Keep it
optional with the sensible default.

**Verify**: `uv run pytest tests -k coverage` → exit 0 after Step 5.

### Step 5: Tests

- Unit: write a small Cobertura `coverage.xml` into a temp repo with one file
  having an uncovered line inside a function; assert `load_coverage` returns the
  uncovered line, and `coverage_findings` emits one `python.uncovered_symbol`
  with confidence 0.95.
- Negative: no `coverage.xml` → `coverage_findings` returns `()` and the normal
  scan still works.
- Malformed XML → `load_coverage` returns `()` (no crash).

**Verify**: `uv run pytest`, `ruff check .`, `ruff format --check .`,
`basedpyright` → all exit 0.

## Test plan

- Uncovered-line → symbol finding with high confidence.
- Missing/malformed coverage file → zero findings, no crash, normal scan
  unaffected.
- Verification: `uv run pytest` → all pass.

## Done criteria

- [ ] `python.uncovered_symbol` findings appear ONLY when a parseable
      `coverage.xml` exists.
- [ ] No coverage tool is executed (`grep -rn "subprocess" src/codescent/services/coverage.py`
      returns nothing).
- [ ] `uv run pytest`, `ruff check`, `ruff format --check`, `basedpyright` exit 0.
- [ ] `docs/configuration.md` documents the coverage path.
- [ ] No analyzed source edited; `tests/fixtures/` untouched.
- [ ] `plans/README.md` status row for 011 updated.

## STOP conditions

Stop and report if:
- Cobertura `filename` paths cannot be reliably mapped to indexed `files.path`
  for this repo's layout — report the mismatch (path-mapping is the main risk).
- Composing coverage findings changes the count/shape of existing scan tests
  unexpectedly — report rather than editing unrelated tests.
- Verification fails twice after a reasonable fix.

## Maintenance notes

- LCOV (`lcov.info`) and `.coverage` SQLite support are deliberate follow-ups.
- Plan 012 (test-impact selection) and plan 007 (hotspot) both compose well with
  this: "uncovered + churny + about to change" is the premium finding.
- Reviewers should confirm zero behavior change when coverage.xml is absent.
