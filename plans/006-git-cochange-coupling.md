# Plan 006: Add git logical co-change coupling to related files and impact

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the next
> step. If anything in the STOP conditions section occurs, stop and report — do
> not improvise. When done, update the status row for this plan in
> `plans/README.md`.
>
> **Drift check (run first)**:
> `git diff --stat 40cbf50..HEAD -- src/codescent/services/git.py src/codescent/services/context.py src/codescent/services/context_support.py tests/unit tests/integration/test_context.py plans/README.md`
> If any in-scope file changed since this plan was written, compare the Current
> state excerpts against live code before proceeding; on a mismatch, treat it as
> a STOP condition.

## Status

- **Priority**: P1
- **Effort**: M
- **Risk**: LOW/MED
- **Depends on**: none
- **Category**: direction (new code-intelligence signal)
- **Planned at**: commit `40cbf50`, 2026-06-15

## Why this matters

CodeScent's import graph only sees _structural_ dependencies. The single
highest-signal predictor of real blast radius — which files historically change
_together_ — is invisible today. Adding deterministic **temporal coupling**
(co-change) from local `git log` makes `get_related_files` and `get_impact`
dramatically better at answering "if I touch X, what else tends to move?" It is
100% local, no network, and reuses git the tool already shells out to. A prior
audit flagged that the existing `git_related_paths` shells out _once per
commit_; this plan deliberately uses a **single** `git log --name-only` pass so
the new signal is cheap.

## Current state

- `src/codescent/services/git.py` — git helpers. It already has
  `git_related_paths(repo_root, path)` which is correct but inefficient (one
  `git show` per commit). Co-change must NOT copy that shape.

```python
# src/codescent/services/git.py:86-127  (existing, do not delete — only add beside it)
def git_related_paths(repo_root: Path, path: str) -> tuple[str, ...]:
    ...
    for commit in commit_result.stdout.splitlines():
        show_result = subprocess.run([... "show" ...])  # one subprocess per commit
```

The module's conventions: use `which("git")`, `subprocess.run` with
`capture_output=True`, `text=True`, a `timeout=`, and return empty on any
failure. Reuse `GIT_HISTORY_TIMEOUT_SECONDS` (currently `5`).

- `src/codescent/services/context.py:204-243` — `get_related_files` builds a
  `reasons: dict[str, set[str]]` then sorts. Reason strings currently used:
  `"test_match"`, `"import_graph"`, `"directory_proximity"`,
  `"search_similarity"`, `"git_history"`. This is the integration point:

```python
# src/codescent/services/context.py:231-234
        for related_path in git_related_paths(repo_root, target.path):
            add_related_reason(reasons, related_path, "git_history")

        rows = _related_rows(reasons, target.path)
```

- `src/codescent/services/context_support.py` — owns `add_related_reason`,
  `related_file_payload`, and the scoring map that turns reason strings into a
  `confidence`. **You must read this file** and find the reason→weight mapping;
  a new reason string needs a weight there or it will score as zero/unknown.

Repo conventions to preserve:

- Strict typing (BasedPyright `all`), Google-style docstrings, 88-col format.
- Services return structured data; never edit analyzed source; no network.
- Keep output bounded; co-change candidates must be capped (use a constant).

## Commands you will need

| Purpose                   | Command                                                      | Expected on success |
| ------------------------- | ------------------------------------------------------------ | ------------------- |
| Focused unit tests        | `uv run pytest tests/unit -k "co_change or coupling or git"` | exit 0              |
| Context integration tests | `uv run pytest tests/integration/test_context.py`            | exit 0              |
| Full tests                | `uv run pytest`                                              | exit 0              |
| Lint                      | `uv run ruff check .`                                        | exit 0              |
| Format                    | `uv run ruff format --check .`                               | exit 0              |
| Typecheck                 | `uv run basedpyright`                                        | exit 0              |

## Scope

**In scope**:

- `src/codescent/services/git.py` — add `git_co_change_counts` (new helper).
- `src/codescent/services/context.py` — call it in `get_related_files`.
- `src/codescent/services/context_support.py` — add a weight for the new reason.
- `tests/unit/` — new unit test for the git helper (create a file, e.g.
  `tests/unit/test_git_co_change.py`).
- `tests/integration/test_context.py` — assert the new reason appears.
- `plans/README.md` status row.

**Out of scope** (do NOT touch):

- `git_related_paths` — leave it exactly as is; do not refactor it into the new
  helper in this plan.
- `get_impact` in `refactor_planning.py` — it already consumes
  `get_related_files`, so it inherits co-change automatically. Do not edit it.
- Any new MCP tool or public-surface entry — this plan adds NO new tool name.
- `tests/fixtures/` source.

## Git workflow

- Branch: `advisor/006-git-cochange-coupling`.
- Commit style matches `git log` (conventional, e.g.
  `feat(git): add co-change coupling helper`). Do not push or open a PR.

## Steps

### Step 1: Add `git_co_change_counts` to `services/git.py`

Add a helper that runs ONE git command and returns co-change counts:

```python
GIT_LOG_MAX_COMMITS: Final = 400
CO_CHANGE_MAX_RESULTS: Final = 10

def git_co_change_counts(repo_root: Path, path: str) -> tuple[tuple[str, int], ...]:
    """Return paths that changed in the same commits as ``path``.

    Uses a single ``git log --name-only`` pass over commits that touched
    ``path``, then counts how often each other path co-occurred. Returns the
    top ``CO_CHANGE_MAX_RESULTS`` by count, descending, excluding ``path`` and
    anything under ``.codescent``. Returns ``()`` on any git failure.
    """
```

Implementation requirements:

- Guard: if `not (repo_root / ".git").exists()` or `which("git") is None`,
  return `()`.
- Run
  `git -C <root> log --no-renames --format=%H --name-only -n <GIT_LOG_MAX_COMMITS> -- <path>`
  with
  `capture_output=True, text=True, check=False, timeout=GIT_HISTORY_TIMEOUT_SECONDS`.
- Parse: blank-line-separated commit blocks; first non-empty line is the hash,
  subsequent lines are changed paths. Count co-occurring paths across all
  blocks.
- Exclude `path` itself and any path that starts with `.codescent`.
- Return
  `tuple(sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])))[:CO_CHANGE_MAX_RESULTS]`.
- Return `()` on `subprocess.TimeoutExpired` or non-zero return code.

**Verify**: `uv run pytest tests/unit -k co_change` → passes after Step 2.

### Step 2: Unit-test the helper against a temporary git repo

In `tests/unit/test_git_co_change.py`, create a temporary directory, `git init`,
configure a throwaway user, and make commits where two files change together and
a third changes alone. Assert `git_co_change_counts(root, "a.py")` returns
`b.py` with the expected count and excludes `c.py` (never co-changed) and `a.py`
itself. Model the temp-git pattern on the existing test
`test_related_files_include_import_test_directory_and_git_reasons` in
`tests/integration/test_context.py` (read it for the exact `subprocess`/`git`
setup idiom this repo uses).

**Verify**: `uv run pytest tests/unit/test_git_co_change.py` → exit 0.

### Step 3: Wire the signal into `get_related_files`

In `src/codescent/services/context.py`, import `git_co_change_counts` alongside
`git_related_paths` and add, right after the `git_history` loop (line ~232):

```python
        for related_path, _count in git_co_change_counts(repo_root, target.path):
            add_related_reason(reasons, related_path, "co_change")
```

### Step 4: Give the new reason a weight

In `src/codescent/services/context_support.py`, locate the mapping that assigns
a confidence/weight per reason string (used by `related_file_payload` /
`add_related_reason`). Add `"co_change"` with a weight between the
`import_graph` and `git_history` weights (co-change is a stronger signal than
raw git history but weaker than a direct import). Match the existing structure
exactly — do not invent a new mechanism.

**Verify**: `uv run pytest tests/integration/test_context.py` → exit 0.

### Step 5: Integration assertion + static checks

Extend `tests/integration/test_context.py` (reuse the temp-git fixture) to
assert that a file which historically co-changed with the target appears in
`get_related_files(...)["results"]` with `"co_change"` in its `reasons`.

**Verify**: `uv run pytest` , `uv run ruff check .`,
`uv run ruff format --check .`, `uv run basedpyright` → all exit 0.

## Test plan

- New: `tests/unit/test_git_co_change.py` — helper happy path, exclusion of self
  and non-co-changed files, empty result for non-git dir.
- Extend: `tests/integration/test_context.py` — `co_change` reason surfaces in
  related files. Pattern after the existing git-backed related-files test.
- Verification: `uv run pytest` → all pass including the new tests.

## Done criteria

- [ ] `git_co_change_counts` exists in `services/git.py` and uses exactly ONE
      git subprocess invocation
      (`grep -c "subprocess.run" src/codescent/services/git.py` increases by
      exactly 1 versus baseline).
- [ ] `get_related_files` can return a `"co_change"` reason.
- [ ] `uv run pytest` exits 0 with the new tests present.
- [ ] `uv run ruff check .`, `uv run ruff format --check .`,
      `uv run basedpyright` exit 0.
- [ ] No new MCP tool name added (`git diff` shows no change to
      `src/codescent/core/public_surface.py`).
- [ ] No files outside the in-scope list modified.
- [ ] `plans/README.md` status row for 006 updated.

## STOP conditions

Stop and report if:

- `context_support.py` has no per-reason weight mapping (the scoring model
  differs from what this plan assumes) — do not invent one.
- `get_related_files` no longer builds a `reasons: dict[str, set[str]]`.
- Adding the helper requires more than one git subprocess to stay correct.
- Any verification fails twice after a reasonable fix.

## Maintenance notes

- Plan 007 (hotspot prioritization) reuses the single-pass `git log` idea; if
  you generalize commit-history parsing, both should share it.
- A reviewer should confirm the git call has a timeout and degrades to `()` so a
  huge/slow history never blocks a tool call.
- `GIT_LOG_MAX_COMMITS` bounds cost on large repos; revisit if coupling looks
  truncated on a real repo.
