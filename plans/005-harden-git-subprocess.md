# Plan 005: Harden every `git` invocation run against an untrusted analyzed repo

> **Executor instructions**: Follow this plan step by step. Confirm each
> verification before moving on. Honor "STOP conditions". When done, update the
> status row in `plans/README.md`.
>
> **Drift check (run first)**:
> `git diff --stat 5dca8d5..HEAD -- src/codescent/services/git.py tests/unit/test_git_co_change.py`
> If `git.py` changed, re-read it and compare against "Current state" before
> proceeding; on a mismatch, STOP.

## Status

- **Priority**: P1
- **Effort**: S–M
- **Risk**: LOW
- **Depends on**: none
- **Category**: security
- **Planned at**: commit `5dca8d5`, 2026-07-02

## Why this matters

CodeScent's headline safety promise is "a local tool that only *reads* the repo
you point it at and writes `.codescent/`." Every `git` subprocess in
`services/git.py` runs `git -C <analyzed_repo> …` with **no config hardening**
and **no `env`**, which quietly breaks that promise in three ways:

1. **Code execution (highest severity).** Git honors repo-local, execution-
   capable config keys. The most direct is `core.fsmonitor`: when set in a
   repo's `.git/config`, git spawns it as a program during index-refreshing
   commands like `git status`. Because `git status` runs on the search-ranking
   hot path and behind `get_repo_status`, merely pointing CodeScent at a hostile
   repo and searching can execute an attacker's program in the CodeScent
   process. `safe.directory` gives no protection — a user who cloned the repo
   owns it.
2. **Option injection.** Caller-supplied refs (`base_ref`, `ref`) are placed as
   positional args with no `--end-of-options` guard. A ref beginning with `-`
   is parsed by git as an *option*; on `git diff` some options can write files
   to arbitrary paths, escaping the `.codescent` write-containment invariant.
   Reaching this requires an agent to be induced (e.g. via prompt-injection from
   a hostile repo) to pass a crafted ref — a chained, not direct, vector.
3. **Silent wrong data on non-ASCII filenames.** Git quotes non-ASCII/special
   paths by default (`core.quotePath=true`), so `café.py` arrives as
   `"caf\303\251.py"` and never matches the real path — changed-file detection,
   co-change coupling, and churn/blast-radius signals silently omit those files.

Separately, one helper — `git_related_paths` — is missing the `TimeoutExpired`
guard every one of its six siblings has, so on a slow repo it raises an internal
error instead of degrading to "no git-history neighbors."

All four fixes live in one file and mostly flow through a single new argv
helper, so the blast radius of the change is small and testable.

## Current state

Every invocation follows the same unhardened shape. Representative sites:

- `git_working_state` (`services/git.py:82-98`): `[git_path, "-C", str(repo_root), "status", "--porcelain", ...]`
- `detect_git_state` (`:131-146`): `... "status", "--porcelain", ...`
- `git_untracked_paths` (`:177…`): `... "ls-files" ...`
- `git_changed_paths_since` (`:217-233`): `... "diff", "--name-only", diff_target, "--", ".", ":(exclude).codescent"`
- `_git_merge_base` (`:266-277`): `... "merge-base", base_ref, "HEAD"`
- `git_file_at_ref` (`:254-262`): `... "show", f"{ref}:{path}"`
- `git_related_paths` (`:280-319`): a `log` then a per-commit `show` — **both `subprocess.run` calls have no `try/except`** (contrast the siblings above, which all catch `(CalledProcessError, TimeoutExpired)`).

Excerpt — the missing guard (`services/git.py:288-296`):

```python
    commit_result = subprocess.run(
        [git_path, "-C", str(repo_root), "log", "--format=%H", "--", path],
        capture_output=True, check=False, text=True,
        timeout=GIT_HISTORY_TIMEOUT_SECONDS,
    )
    if commit_result.returncode != 0:
        return ()
    related: set[str] = set()
    for commit in commit_result.stdout.splitlines():
        show_result = subprocess.run([...], timeout=GIT_HISTORY_TIMEOUT_SECONDS)  # also unguarded
```

Excerpt — a ref placed positionally with no option barrier
(`services/git.py:269`):

```python
    [git_path, "-C", str(repo_root), "merge-base", base_ref, "HEAD"]
```

Excerpt — the status-output path parser strips quotes but leaves octal escapes
(`services/git.py:551`, `_parse_git_status_paths`): `path.strip('"')`.

Path parsing of git output happens in several helpers via `line.strip()` /
`_parse_git_status_paths`; none disable `core.quotePath`.

The existing test file `tests/unit/test_git_co_change.py` shows the real-repo
test pattern (build commits in a `tmp_path` repo) with helpers `_git`,
`_write`, `_commit` — reuse it. Its top already imports several helpers from
`codescent.services.git`.

Repo conventions: `ruff` has `S603` (subprocess) suppressed for
`src/codescent/services/git.py` in `pyproject.toml`, so `subprocess.run` with a
list argv is accepted there. `which("git")` is used to resolve the binary;
`GIT_STATUS_TIMEOUT_SECONDS` / `GIT_HISTORY_TIMEOUT_SECONDS` are module
constants.

## Commands you will need

| Purpose | Command | Expected |
|---|---|---|
| Install | `uv sync` | exit 0 |
| Git tests | `uv run pytest tests/unit/test_git_co_change.py tests/unit/test_git_hardening.py -q` | pass (second file after Step 4) |
| Full suite | `uv run pytest` | no new failures |
| Lint | `uv run ruff check .` | `All checks passed!` |
| Typecheck | `uv run basedpyright` | no new errors |

## Scope

**In scope**:

- `src/codescent/services/git.py`
- `tests/unit/test_git_hardening.py` (create)
- Possibly `tests/unit/test_git_co_change.py` (only if you extend it; prefer the
  new file)

**Out of scope**:

- Any caller of these helpers (`services/context.py`, `services/ci.py`,
  `services/answer_pack_support.py`) — the fixes are internal to `git.py`; the
  public function signatures do not change.
- Switching to `-z`/NUL parsing — `-c core.quotePath=false` is the chosen,
  simpler fix (NUL parsing conflicts with the `%x00` author delimiter in
  `git_author_churn`); do not rewrite the parsers.
- The `.codescent` exclusion pathspec (`:(exclude).codescent`) — keep it exactly.

## Git workflow

- Branch off `main`: `git switch -c advisor/005-harden-git-subprocess`.
- Commit: `fix(git): harden subprocess invocations against untrusted analyzed repos`.
- Do NOT push or open a PR.

## Steps

### Step 1: Add a hardened argv helper and route every invocation through it

Near the top of `git.py` (after imports/constants), add:

```python
# Repo-local git config can execute programs (core.fsmonitor, hooks) when we run
# commands inside an untrusted analyzed repo, and core.quotePath mangles
# non-ASCII paths. Neutralize all three on every invocation.
_GIT_HARDENING: tuple[str, ...] = (
    "-c", "core.fsmonitor=",
    "-c", "core.hooksPath=/dev/null",
    "-c", "core.quotePath=false",
)


def _git_argv(git_path: str, repo_root: Path, *args: str) -> list[str]:
    return [git_path, *_GIT_HARDENING, "-C", str(repo_root), *args]
```

Then replace **every** `[git_path, "-C", str(repo_root), <subcommand>, ...]`
literal in the file with `_git_argv(git_path, repo_root, <subcommand>, ...)`.
Grep to find them all: `grep -n 'str(repo_root)' src/codescent/services/git.py`.
There are on the order of 10–12 sites (`status` ×2, `ls-files`, `diff`,
`merge-base`, `show` ×2, `log` ×2, and any others). Keep every existing flag,
pathspec, `timeout=`, `check=`, `capture_output=`, and `text=` argument exactly
as-is — you are only prefixing the hardening + quotePath flags.

**Verify**:
- `grep -n 'str(repo_root)]' src/codescent/services/git.py` and
  `grep -cn '_git_argv' src/codescent/services/git.py` — every former literal is
  now a `_git_argv(...)` call (no raw `[git_path, "-C", ...]` list literals
  remain for subprocess).
- `uv run pytest tests/unit/test_git_co_change.py -q` → still passes (behavior
  for valid repos unchanged; the quotePath/fsmonitor flags are inert on a benign
  repo).

### Step 2: Add `--end-of-options` before caller-supplied refs

For the invocations that place a caller-controlled ref positionally, insert
`--end-of-options` immediately before the ref so a leading-dash value is always
treated as a revision, never an option:

- `_git_merge_base`: `_git_argv(git_path, repo_root, "merge-base", "--end-of-options", base_ref, "HEAD")`
- `git_changed_paths_since`: in the `diff` argv, `"--name-only", "--end-of-options", diff_target, "--", ".", ":(exclude).codescent"`
- `git_file_at_ref` (`show f"{ref}:{path}"`): `_git_argv(git_path, repo_root, "show", "--end-of-options", f"{ref}:{path}")`
- `git_related_paths` (`log ... -- path`): the `path` is already after `--`, so it is safe; leave its argument order but still route through `_git_argv`.

Also add a cheap defensive guard: at the top of `git_changed_paths_since` and
`git_file_at_ref`, if the incoming `base_ref`/`ref` starts with `-`, treat it as
absent (return `None`) — belt-and-suspenders in case an older git lacks
`--end-of-options`.

**Verify**: `uv run pytest tests/unit/test_git_co_change.py -q` → passes
(legitimate refs like `HEAD`, a branch name, a SHA still resolve). Add the
leading-dash assertion in Step 4.

### Step 3: Add the missing timeout/error guard to `git_related_paths`

Wrap the two `subprocess.run` calls in `git_related_paths` in
`try/except (subprocess.CalledProcessError, subprocess.TimeoutExpired)`,
returning `()` for the outer `log` call and `continue` for the inner per-commit
`show`, mirroring `git_co_change_counts` and the other siblings. The function's
contract already documents "returns empty on unavailable", so this makes the
timeout path match every other helper.

**Verify**: `grep -n "except (subprocess" src/codescent/services/git.py` shows
the new guard inside `git_related_paths`. `uv run pytest tests/unit/test_git_co_change.py -q` → passes.

### Step 4: Add `tests/unit/test_git_hardening.py`

Model on `tests/unit/test_git_co_change.py` (reuse its `_git`/`_write`/`_commit`
helper style — copy small local helpers into the new file or import them).
Cover:

- **SEC-01 regression — repo-local `core.fsmonitor` is not executed.** Build a
  `tmp_path` git repo with one commit. Configure a repo-local fsmonitor that,
  if run, writes a sentinel file: e.g. write a tiny executable script into the
  repo and `git config core.fsmonitor <path-to-script>` so the script would
  `touch <sentinel>` when invoked. Call `git_working_state(repo)` and
  `detect_git_state(repo)`. Assert the sentinel file does **not** exist
  afterward (the hardening flag neutralized it). This is defensive verification
  of the fix, not an exploit — the "program" is a benign sentinel-writer.
  (If constructing an executable is awkward on the CI runner, an equivalent is
  to set `core.fsmonitor` to a command that would fail loudly and assert the
  git helper still returns a normal result rather than erroring — because the
  hardening blanks the setting, the helper never invokes it.)
- **B-04 — non-ASCII filename round-trips.** Create and commit a file named with
  a non-ASCII character (e.g. `café.py`). Modify it so it shows as changed.
  Assert `git_changed_paths` / `git_changed_paths_since` returns the path in its
  real UTF-8 form (`"café.py"`), not an octal-escaped `"caf\303\251.py"`.
- **TEST-04 — cover the untested helpers.** Add straightforward tests for
  `git_working_state` (returns `available=False` for a non-git dir; returns the
  changed set for a dirty repo), `git_untracked_paths` (a new unstaged file
  appears; empty for a clean repo), `git_changed_paths_since` (a known base ref
  returns the expected changed set; an unknown base ref returns `None`), and
  `git_file_at_ref` (returns file content at a ref; `None` for an unknown ref).
  Include a **rename** commit and assert the parser handles it, an **empty/
  first-commit** repo, and a **detached HEAD** case if cheap.
- **SEC-04 — leading-dash ref is refused.** Assert
  `git_changed_paths_since(repo, "--output=/tmp/x")` returns `None` (or the
  whole-repo fallback) and does **not** create `/tmp/x`.

**Verify**: `uv run pytest tests/unit/test_git_hardening.py -q` → all pass.

### Step 5: Full green

**Verify**:
- `uv run pytest` → no new failures.
- `uv run ruff check .` and `uv run ruff format --check .` → pass.
- `uv run basedpyright` → no new errors.

## Test plan

- New file `tests/unit/test_git_hardening.py` with: the fsmonitor non-execution
  regression (SEC-01), the non-ASCII round-trip (B-04), the four previously
  untested helpers incl. rename/empty-repo/unknown-ref cases (TEST-04), and the
  leading-dash ref refusal (SEC-04).
- These are real regression tests: the fsmonitor and non-ASCII tests fail on the
  unpatched code and pass after.
- Verification: `uv run pytest tests/unit/test_git_hardening.py tests/unit/test_git_co_change.py -q` → all pass.

## Done criteria

ALL must hold:

- [ ] Every `git` subprocess in `git.py` goes through `_git_argv` (no raw
      `[git_path, "-C", str(repo_root), ...]` list literals remain):
      `grep -n 'str(repo_root)]' src/codescent/services/git.py` returns nothing
      that is a subprocess argv.
- [ ] `_GIT_HARDENING` includes `core.fsmonitor=`, `core.hooksPath=/dev/null`,
      and `core.quotePath=false`.
- [ ] `--end-of-options` precedes caller refs in `merge-base`, `diff`, and
      `show`; leading-dash refs are refused.
- [ ] `git_related_paths` catches `(CalledProcessError, TimeoutExpired)` on both
      subprocess calls.
- [ ] `tests/unit/test_git_hardening.py` exists and passes, including the
      fsmonitor non-execution assertion.
- [ ] `uv run pytest` no new failures; `ruff` + `basedpyright` clean.
- [ ] No files outside the in-scope list modified.
- [ ] `plans/README.md` status row for 005 updated.

## STOP conditions

Stop and report if:

- The installed git rejects `--end-of-options` (very old git) — the tests will
  fail with a usage error; report the git version rather than removing the
  guard.
- Routing a call through `_git_argv` changes a passing test's expected output
  (e.g. a test asserted an octal-escaped path — that test encoded the bug; note
  it, and update it to expect the real path, but flag the change).
- You cannot construct the fsmonitor regression test on the runner after a
  reasonable attempt — implement the "hardening blanks the setting" variant and
  say so; do not skip SEC-01 verification silently.

## Maintenance notes

- All future `git` calls in this file **must** go through `_git_argv` — a raw
  argv reintroduces the fsmonitor/quotePath exposure. A reviewer should reject
  any new `subprocess.run([git_path, ...])` that bypasses the helper.
- `core.hooksPath=/dev/null` disables hook execution for these read-only
  commands; that is intended (CodeScent must never run a repo's hooks).
- Deferred (out of scope): centralizing the several `line.strip()` path parsers
  behind one helper, and the `git_author_churn` `%x00` delimiter's interaction
  with any future `-z` migration.
- The SEC-01 mechanism (fsmonitor-on-status) is standard git behavior; if a
  future git version adds another exec-capable key reachable from these
  read-only commands, add it to `_GIT_HARDENING`.
