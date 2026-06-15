# Plan 002: Reduce changed-source test false positives

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the next
> step. If anything in the STOP conditions section occurs, stop and report. Do
> not improvise.
>
> **Drift check (run first)**:
> `git diff --stat b93cbcf..HEAD -- src/codescent/services/code_health.py src/codescent/services/search_queries.py tests/integration/test_scan_code_health.py tests/integration/test_findings.py tests/integration/test_search.py evals/fixtures/python-basic.expected.json plans/README.md`
> If any in-scope file changed since this plan was written, compare the Current
> state excerpts against live code before proceeding; on a mismatch, treat it as
> a STOP condition.

## Status

- **Priority**: P1
- **Effort**: S/M
- **Risk**: LOW
- **Depends on**: `plans/001-context-related-files.md`
- **Category**: tests
- **Planned at**: commit `b93cbcf`, 2026-06-14

## Why This Matters

The `python.changed_source_without_related_test` finding is intended to warn
when changed source lacks obvious test coverage. Today it only checks for
`tests/test_<stem>.py`, which does not match this repo's own behavior-based test
layout under `tests/integration/`, `tests/contract/`, `tests/security/`, and
other folders. The result is noisy findings that make changed-file health and
CI/diff review less trustworthy.

## Current State

- `src/codescent/services/code_health.py` adds changed-source findings after
  indexing.
- `src/codescent/services/search_queries.py` already contains broader test
  discovery logic used by search and verification tools.
- `tests/integration/test_scan_code_health.py` currently expects the
  changed-source rule for a repo with no tests.
- `tests/integration/test_search.py` shows test discovery can rank
  `tests/test_workflow.py` by path and symbol.

Current narrow heuristic:

```python
# src/codescent/services/code_health.py:152-184
    changed_files: tuple[str, ...],
    indexed_paths: set[str],
) -> tuple[CodeHealthFinding, ...]:
    return tuple(
        build_finding(...)
        for path in changed_files
        if _is_python_source(path) and _expected_test_path(path) not in indexed_paths
    )

def _expected_test_path(path: str) -> str:
    stem = path.rsplit("/", maxsplit=1)[-1].removesuffix(".py")
    return f"tests/test_{stem}.py"
```

Existing broader test search:

```python
# src/codescent/services/search_queries.py:66-91
    ...
    for item in build_file_inventory(repo_root, config=project_config):
        if not is_test_path(item.path):
            continue
        lines = (repo_root / item.path).read_text().splitlines()
        score, reasons, matched_snippet = rank_test_file(item.path, lines, terms)
```

Repo conventions to preserve:

- Findings need deterministic evidence and stable IDs.
- Fixture repos under `tests/fixtures/` are intentionally flawed inputs; do not
  edit them.
- Public behavior changes should be covered by integration/contract/eval tests.

## Commands You Will Need

| Purpose                | Command                                                                                                                                                                                                           | Expected on success |
| ---------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------- |
| Focused scan tests     | `uv run pytest tests/integration/test_scan_code_health.py tests/integration/test_findings.py`                                                                                                                     | exit 0              |
| Search heuristic tests | `uv run pytest tests/integration/test_search.py`                                                                                                                                                                  | exit 0              |
| Deterministic eval     | `uv run python evals/run_deterministic.py --repo tests/fixtures/python-basic --expected evals/fixtures/python-basic.expected.json --out .omo/evidence/plan-002-deterministic-eval.json`                           | exit 0              |
| Lint changed files     | `uv run ruff check src/codescent/services/code_health.py src/codescent/services/search_queries.py tests/integration/test_scan_code_health.py tests/integration/test_findings.py tests/integration/test_search.py` | exit 0              |
| Typecheck              | `uv run basedpyright`                                                                                                                                                                                             | exit 0              |

## Scope

**In scope**:

- `src/codescent/services/code_health.py`
- `src/codescent/services/search_queries.py` only if a reusable helper is needed
- `tests/integration/test_scan_code_health.py`
- `tests/integration/test_findings.py` if expected counts/statuses change
- `tests/integration/test_search.py` if helper behavior needs coverage
- `evals/fixtures/python-basic.expected.json` only if the deterministic fixture
  expectation legitimately changes
- `plans/README.md` status row

**Out of scope**:

- Do not remove the `python.changed_source_without_related_test` rule.
- Do not weaken tests by simply deleting assertions for the rule.
- Do not change rule IDs or stable-key format unless the deterministic eval
  makes that unavoidable.
- Do not edit checked-in fixture source.

## Git Workflow

- Suggested branch: `advisor/002-change-test-heuristic`.
- Commit style, if requested:
  `fix(health): reduce changed-source test false positives`.
- Do not push or open a PR unless instructed.

## Steps

### Step 1: Add a failing false-positive test

In `tests/integration/test_scan_code_health.py`, add a temporary repo with a
source file such as `src/pkg/workflow.py` and a related test under a non-root
behavior folder such as `tests/integration/test_workflow.py` or
`tests/contract/test_workflow.py`. Run `CodeHealthService(repo).scan()` or the
CLI scan path and assert that no `python.changed_source_without_related_test`
finding is emitted for `src/pkg/workflow.py`.

Also keep the existing no-test case covered so the rule still fires when there
is no plausible related test.

**Verify**: `uv run pytest tests/integration/test_scan_code_health.py` -> new
test fails before implementation, existing tests still run.

### Step 2: Replace exact expected-path matching with existing test search semantics

In `src/codescent/services/code_health.py`, replace the
`_expected_test_path(path) not in indexed_paths` check with a helper that asks
whether a changed source path has any likely test. Prefer reusing or extracting
from `search_tests_for_repo` so this rule and
`VerificationService.suggest_tests()` do not diverge further.

The helper should consider:

- The changed source path.
- The source stem/module terms.
- Only indexed files within the current repo inventory.

Keep the finding evidence useful. If the rule still fires, evidence can include
the old expected path plus a note that no likely tests were found.

**Verify**:
`uv run pytest tests/integration/test_scan_code_health.py tests/integration/test_search.py`
-> exit 0.

### Step 3: Refresh affected lifecycle/eval expectations only if needed

Run the focused finding lifecycle tests. If counts changed because a fixture now
has a correctly detected related test, update only the expectations that
describe the new behavior. If the deterministic eval expected manifest changes,
update `evals/fixtures/python-basic.expected.json` only after confirming the
changed finding is truly a false positive.

**Verify**: focused tests and deterministic eval command from the command table
exit 0.

### Step 4: Run static checks

Run the lint and typecheck commands from the command table.

**Verify**: both exit 0.

## Test Plan

- Add one regression test where related tests exist outside
  `tests/test_<stem>.py` and the rule does not fire.
- Preserve a test where no related tests exist and the rule does fire.
- Run deterministic eval to ensure fixture scoring remains intentional.

## Done Criteria

- [ ] False-positive regression test exists and passes.
- [ ] No-test regression case still emits
      `python.changed_source_without_related_test`.
- [ ] Focused pytest commands exit 0.
- [ ] Deterministic eval exits 0.
- [ ] Ruff and BasedPyright commands exit 0.
- [ ] No files outside the in-scope list are modified.
- [ ] `plans/README.md` status row for 002 is updated.

## STOP Conditions

Stop and report if:

- Reusing `search_tests_for_repo` creates an import cycle.
- The fix requires changing public finding IDs for unrelated rules.
- Deterministic eval failures are not clearly tied to the changed-source
  heuristic.
- You need to edit fixture source to make tests pass.

## Maintenance Notes

- This rule feeds changed-file health and CI/diff review. Reviewers should look
  for reduced noise without losing the useful warning when tests are genuinely
  absent.
- Plan 004 may later move test lookup onto persisted index data. Keep helpers
  small and documented by tests.
