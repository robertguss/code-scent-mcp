# Plan 002: Green `uv run basedpyright` — clear the 95 test-side type errors

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving on. If a
> "STOP condition" occurs, stop and report — do not improvise. When done,
> update the status row for this plan in `plans/README.md`.
>
> **Drift check (run first)**:
> `git diff --stat 5dca8d5..HEAD -- pyproject.toml tests/`
> If `pyproject.toml`'s `[tool.basedpyright]` block or the listed test files
> changed since this plan was written, re-run `uv run basedpyright` and compare
> the live error list against "Current state" before proceeding.

## Status

- **Priority**: P1
- **Effort**: M
- **Risk**: LOW
- **Depends on**: none (independent of plan 001; can run in parallel)
- **Category**: dx
- **Planned at**: commit `5dca8d5`, 2026-07-02

## Why this matters

`uv run basedpyright` reports **95 errors**, and the repo configures the
strictest mode (`typeCheckingMode = "all"`, `include = ["src", "tests"]`). Every
one of the 95 is in `tests/` — `src/` is clean — but with no CI (see plan 003)
the type gate was never enforced on test code, so the errors accumulated. A
red typecheck, like a red test suite, blinds an automated executor: it cannot
tell a new type regression from the standing 95. This plan makes
`basedpyright` exit 0 so it can become a CI gate.

The errors split into two principled groups, and the fix differs per group:

1. **External-boundary "unknown/any" noise** (~55 errors): test code indexes
   into results whose static type is `Any` — `subprocess.run(...).stdout`,
   `json.loads(...)`, FastMCP `Client.call_tool(...)` structured content, and
   un-annotated lambdas. These are `reportAny`, `reportExplicitAny`,
   `reportUnknownMemberType`, `reportUnknownVariableType`,
   `reportUnknownArgumentType`, `reportUnknownLambdaType`,
   `reportImplicitStringConcatenation`. Chasing precise types through those
   boundaries in *test* code is low-value churn and risks wrong casts. The
   right move is a scoped rule relaxation for `tests/**` only, leaving `src/`
   at full strictness.
2. **Real defects** (~20 errors): `reportUnusedParameter`,
   `reportUnusedFunction`, `reportUnusedVariable`, `reportUnusedCallResult`,
   `reportOperatorIssue`, `reportIndexIssue`, `reportArgumentType`,
   `reportGeneralTypeIssues`, `reportInvalidCast`. These flag dead code or
   genuinely wrong operations — fix them inline, do not suppress.

## Current state

Full error breakdown (from `uv run basedpyright --outputjson`), by file:

```
 28 tests/contract/test_install_hook.py
 23 tests/contract/test_hook_augment_cli.py
 13 tests/contract/test_mcp_error_contract.py
 12 tests/contract/test_hook_reindex_cli.py
  6 tests/integration/test_hook_payload.py
  2 tests/integration/test_hook_retrieval.py
  2 tests/integration/test_session_stats.py
  2 tests/unit/test_errors.py
  1 each: test_agent_ux_loop_connectivity.py, test_cli.py,
          test_explain_finding_tool.py, test_mcp_repo_tools.py,
          test_mcp_search_tools.py, test_answer_pack.py, test_cli_import_cost.py
```

By rule (approximate counts): `reportUnknownMemberType` 17, `reportAny` 17,
`reportUnknownVariableType` 7, `reportOperatorIssue` 5, `reportUnknownLambdaType`
4, `reportIndexIssue` 4, `reportImplicitStringConcatenation` 3,
`reportUnusedParameter` 3, `reportUnusedFunction` 2, `reportUnusedCallResult` 2,
`reportExplicitAny` 2, `reportInvalidCast` 1, `reportArgumentType` 2,
`reportGeneralTypeIssues` 1, `reportUnknownArgumentType` ~3.

Relevant config (`pyproject.toml:43-64`):

```toml
[tool.basedpyright]
typeCheckingMode = "all"
pythonVersion = "3.12"
pythonPlatform = "All"
include = ["src", "tests"]
exclude = [ ... fixture dirs ... ]
reportUnusedCallResult = "warning"
reportUnnecessaryTypeIgnoreComment = "error"
reportUnusedVariable = "error"
reportMissingParameterType = "error"
reportPrivateUsage = "error"
```

Note `reportUnnecessaryTypeIgnoreComment = "error"`: a `# pyright: ignore`
that turns out to be unnecessary is itself an error, so do **not** sprinkle
per-line ignores — use the scoped `executionEnvironments` override below.

basedpyright supports per-path rule overrides via `executionEnvironments` in
`pyproject.toml` — a list where each entry sets a `root` and rule levels that
apply only under that path. This keeps `src/` strict while relaxing the
boundary rules for `tests/`.

## Commands you will need

| Purpose | Command | Expected on success |
|---|---|---|
| Install | `uv sync` | exit 0 |
| Typecheck (all) | `uv run basedpyright` | `0 errors` |
| Typecheck one file | `uv run basedpyright tests/contract/test_install_hook.py` | `0 errors` |
| JSON error list | `uv run basedpyright --outputjson` | machine-readable diagnostics |
| Tests still pass | `uv run pytest -q` | no new failures vs baseline |
| Lint | `uv run ruff check .` | `All checks passed!` |

## Scope

**In scope**:

- `pyproject.toml` — add one `[[tool.basedpyright.executionEnvironments]]` entry
  scoped to `tests` (Step 1).
- The specific test files whose errors are "real defects" (Step 2), edited
  inline. Enumerate them from `uv run basedpyright --outputjson` after Step 1.

**Out of scope**:

- Any file under `src/` — it is already clean; if a `src/` error appears, that
  is a STOP condition (do not silence it).
- Relaxing rules globally or for `src/` — the override must be `tests`-scoped.
- Changing test *behavior/assertions* — only types, annotations, unused-symbol
  removal, and the config override.
- The 18 pytest failures (plan 001).

## Git workflow

- Branch off `main`: `git switch -c advisor/002-green-basedpyright`.
- Suggested commits: `chore(types): scope basedpyright boundary rules to tests`
  then `fix(tests): remove dead code and wrong ops flagged by basedpyright`.
- Do NOT push or open a PR.

## Steps

### Step 1: Add a `tests`-scoped rule relaxation for the boundary-noise rules

Add to `pyproject.toml` (after the `[tool.basedpyright]` block):

```toml
[[tool.basedpyright.executionEnvironments]]
root = "tests"
# Test code indexes into Any-typed external boundaries (subprocess stdout,
# json.loads, FastMCP Client.call_tool structured content, ad-hoc lambdas).
# src/ stays at typeCheckingMode="all"; only tests relax the "unknown type
# crossing a boundary" family. Real defects (unused/operator/index) stay errors.
reportAny = false
reportExplicitAny = false
reportUnknownMemberType = false
reportUnknownVariableType = false
reportUnknownArgumentType = false
reportUnknownLambdaType = false
reportImplicitStringConcatenation = false
```

**Verify**: `uv run basedpyright 2>&1 | tail -1` → error count drops from 95 to
roughly ~20 (only the "real defect" rules remain). If it drops to 0, skip to
Step 3. If any *remaining* error is in a `src/` file, STOP (the override is
mis-scoped or a real `src` error exists).

### Step 2: Fix the remaining "real defect" errors inline

Regenerate the list: `uv run basedpyright --outputjson` and read each remaining
diagnostic. Fix by rule category — do **not** suppress:

- **`reportUnusedFunction` / `reportUnusedParameter`** (e.g.
  `test_mcp_error_contract.py:79,100`, `test_hook_reindex_cli.py:86`): a nested
  helper or fixture param is never used. Either remove it, or if it is a
  required signature (e.g. a monkeypatch replacement must accept an arg),
  prefix the name with `_` (`_unused`) — pyright treats leading-underscore
  params as intentionally unused.
- **`reportUnusedVariable`**: delete the dead assignment (or use `_ =` if the
  call has a needed side effect — the repo already uses `_ =` widely, e.g.
  `repository.py`).
- **`reportUnusedCallResult`** (configured `warning`, but treat as fix-worthy):
  assign the ignored result to `_`, matching the repo convention.
- **`reportOperatorIssue`** (`test_session_stats.py:40,41`): an operator is
  applied to an operand pyright can't prove supports it — usually indexing a
  value typed `object`/`Any` then doing arithmetic. Add a local annotation or
  `cast(...)` from `typing` to the concrete type the test knows it is (e.g.
  `count = cast(int, payload["count"])`). Do not change the asserted value.
- **`reportIndexIssue`** (`test_errors.py:38,39`, `test_install_hook.py:71`):
  subscripting a value typed `object`. Annotate the source (e.g. the result of
  a helper) as `dict[str, object]` or `cast` it before indexing.
- **`reportArgumentType` / `reportGeneralTypeIssues` / `reportInvalidCast`**
  (`test_install_hook.py:65,78,98`): a value of the wrong type is passed or an
  impossible cast is made. Read the callee signature and pass the correct type,
  or fix the cast target.

Fix one file at a time and re-run `uv run basedpyright <file>` after each so
you always know your remaining count.

**Verify**: `uv run basedpyright` → `0 errors`.

### Step 3: Confirm tests still pass and lint is clean

Type fixes can accidentally change behavior (e.g. deleting a "dead" variable
that had a side effect, or a wrong cast). Re-run the affected tests.

**Verify**:
- `uv run pytest tests/contract tests/integration/test_hook_payload.py tests/integration/test_hook_retrieval.py tests/integration/test_session_stats.py tests/unit/test_errors.py -q` → pass (allowing for the plan-001 docs failures if plan 001 has not landed; those are unrelated and outside the files you touched).
- `uv run ruff check .` → `All checks passed!`
- `uv run ruff format --check .` → exit 0.

## Test plan

No new tests. This plan removes noise from the type gate and fixes real
test-code defects. Verification is the type checker itself plus a re-run of the
touched tests to prove no behavior changed. If plan 001 has landed, the full
`uv run pytest` should be green; if not, only the plan-001 docs failures remain
and are out of scope here.

## Done criteria

ALL must hold:

- [ ] `uv run basedpyright` reports `0 errors`.
- [ ] The `executionEnvironments` override is scoped to `root = "tests"` only;
      `grep -A2 'root = "tests"' pyproject.toml` shows the relaxed rules under it.
- [ ] `src/` has zero suppressions added (`git diff src/` is empty).
- [ ] `uv run pytest` shows no *new* failures introduced by this plan (compare
      to the pre-plan failure set).
- [ ] `uv run ruff check .` passes.
- [ ] No files outside the in-scope list modified (`git status`).
- [ ] `plans/README.md` status row for 002 updated.

## STOP conditions

Stop and report if:

- After Step 1, any remaining error is in a `src/` file (the codebase has a
  real source-side type error this plan did not anticipate — surface it, don't
  silence it).
- A "real defect" fix would require changing a test's assertion or its runtime
  behavior to satisfy the type checker (that's a test-correctness question for
  a human, not a mechanical type fix).
- basedpyright does not honor the `executionEnvironments` override (version
  mismatch) — the error count does not drop after Step 1.
- `uv run pytest` gains a new failure in a file you edited.

## Maintenance notes

- The `tests`-scoped relaxation is deliberate and documented in the config
  comment: `src/` stays maximally strict; only the "can't-type-an-external-
  boundary" rules are off for tests. A reviewer should confirm the override's
  `root` is `tests`, not the repo root.
- If future test code introduces a *real* type bug in one of the relaxed
  categories, it won't be caught — that is the accepted trade for not
  annotating every subprocess/JSON boundary. If a specific test file warrants
  strictness, add a narrower `executionEnvironments` entry for it.
- Plan 003 (CI) will run `uv run basedpyright` as a gate, so this must stay at
  0 errors going forward.
