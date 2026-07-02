# Plan 003: Add a CI gate that runs the full verification suite on every push/PR

> **Executor instructions**: Follow this plan step by step. Confirm each
> verification before moving on. Honor "STOP conditions". When done, update the
> status row in `plans/README.md`.
>
> **Drift check (run first)**:
> `git diff --stat 5dca8d5..HEAD -- pyproject.toml README.md` and
> `ls .github/workflows 2>/dev/null`. If a workflow already exists, STOP and
> report — do not create a second one.

## Status

- **Priority**: P1
- **Effort**: S
- **Risk**: LOW
- **Depends on**: plans/001-green-the-test-suite.md, plans/002-green-basedpyright.md
- **Category**: dx
- **Planned at**: commit `5dca8d5`, 2026-07-02

## Why this matters

There is no CI: `.github/` does not exist, there is no `.pre-commit-config.yaml`,
and nothing automatically runs the toolchain the repo already configures
(`ruff`, `basedpyright`, `pytest`, `pytest-cov`). This absence is *why* the
suite went red (plans 001/002) and why dead doc links shipped unnoticed —
`scripts/dogfood_allowlist.json` even claims the dogfood scan "fails CI" when
no CI exists to run it. This plan adds one GitHub Actions workflow that runs
the same commands a developer runs locally, so regressions are caught on push
and PR instead of by luck. It must land only after 001 and 002 make the suite
green, or the very first CI run fails.

## Current state

- No `.github/` directory (confirm: `ls .github` → "No such file or directory").
- The canonical verification commands (from `README.md` "Development" and
  `CLAUDE.md` "COMMANDS"):
  - `uv sync`
  - `uv run ruff check .`
  - `uv run ruff format --check .`
  - `uv run basedpyright`
  - `uv run pytest`
- Dogfood scan (self-analysis gate): `scripts/dogfood_scan.py` with a reviewed
  baseline in `scripts/dogfood_allowlist.json`; its own comment says it "fails
  CI when a NEW warning-or-higher finding appears that is not listed here."
  Confirm its invocation: `uv run python scripts/dogfood_scan.py --help` (read
  the flags; do not assume `--check` exists — use whatever the script exposes,
  and if it only supports `--update-baseline`, run it without flags and rely on
  its exit code).
- Deterministic eval: `uv run python evals/run_deterministic.py --repo tests/fixtures/python-basic --expected evals/fixtures/python-basic.expected.json --out <path>`.
- Package manager: `uv` (there is a committed `uv.lock`). Python floor: 3.12
  (`pyproject.toml: requires-python = ">=3.12"`).

The repo is a Python package managed by `uv`; the standard CI setup is
`actions/checkout` + `astral-sh/setup-uv` (which installs uv and can pin the
Python version and cache the environment from `uv.lock`).

## Commands you will need

| Purpose | Command | Expected |
|---|---|---|
| Install | `uv sync` | exit 0 |
| Full local gate (dry-run before writing CI) | see Step 1 | all exit 0 |
| Lint the workflow YAML | `uv run python -c "import yaml,sys; yaml.safe_load(open('.github/workflows/ci.yml'))"` | exit 0 (valid YAML) |

(`pyyaml` may not be installed; if the import fails, validate YAML by eye and
rely on the drift/STOP checks. Do not add a dependency for this.)

## Scope

**In scope**:

- `.github/workflows/ci.yml` (create)
- `README.md` — add a one-line CI badge/status note (optional, only if trivial)

**Out of scope**:

- Any source or test change — if the gate is red locally, that is plans 001/002,
  not this plan. Do not "fix" code here.
- Release/publish workflows, matrix over multiple OSes, or deploy steps — keep
  it a single-job lint+type+test gate.
- Changing the tool commands themselves.

## Git workflow

- Branch off `main`: `git switch -c advisor/003-add-ci-gate`.
- Commit: `ci: add push/PR workflow running ruff, basedpyright, pytest`.
- Do NOT push or open a PR (the operator controls when CI first runs remotely).

## Steps

### Step 1: Prove the full gate is green locally first

Run, in order, and confirm each exits 0:

```
uv sync
uv run ruff format --check .
uv run ruff check .
uv run basedpyright
uv run pytest
```

If any fails, **STOP** — plans 001 and 002 have not fully landed, and CI is
premature.

Then check the dogfood scan's real interface and run it:

```
uv run python scripts/dogfood_scan.py --help
```

Run it in whatever "check against baseline" mode it exposes and note its exit
code on a clean tree (expected 0). If it has no check mode and only mutates the
baseline, do **not** include it as a blocking CI step (note that in Step 2's
comment instead).

### Step 2: Write `.github/workflows/ci.yml`

Order steps fast-to-slow so the job fails cheaply. Target shape:

```yaml
name: CI

on:
  push:
    branches: [main]
  pull_request:

jobs:
  gate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
        with:
          python-version: "3.12"
          enable-cache: true
      - run: uv sync --all-extras --dev
      - run: uv run ruff format --check .
      - run: uv run ruff check .
      - run: uv run basedpyright
      - run: uv run pytest
      # Dogfood self-scan — include ONLY if Step 1 confirmed a non-mutating
      # check mode with a meaningful exit code:
      # - run: uv run python scripts/dogfood_scan.py <check-flag>
```

Notes:
- Use `uv sync --all-extras --dev` so the `fast` extra (`pyahocorasick`) and
  dev tools install; if `--all-extras` errors, fall back to `uv sync --dev`.
- Pin action major versions as shown; do not use unpinned `@main`.
- Do not add `continue-on-error`; the gate must be blocking.

### Step 3: Add the deterministic eval as a separate non-blocking job (optional)

If Step 1's deterministic eval command succeeds locally, add a second job so
eval drift is visible without blocking merges on eval flakiness:

```yaml
  eval:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
        with:
          python-version: "3.12"
          enable-cache: true
      - run: uv sync --dev
      - run: uv run python evals/run_deterministic.py --repo tests/fixtures/python-basic --expected evals/fixtures/python-basic.expected.json --out eval-out.json
```

Only add this if the command exits 0 locally with those exact paths (verify
`ls evals/fixtures/python-basic.expected.json`). If the expected manifest path
differs, use the real one or omit this job.

### Step 4: Validate the YAML

**Verify**: `.github/workflows/ci.yml` is valid YAML (see Commands table) and
the file parses. Re-read it to confirm every `run:` command matches a command
you proved green in Step 1.

## Test plan

CI cannot be fully exercised locally, so the "test" is: (a) every command in the
workflow was proven to exit 0 locally in Step 1, and (b) the YAML is
syntactically valid. Do not fabricate a green CI run — the operator will push
to trigger the first real run.

## Done criteria

ALL must hold:

- [ ] `.github/workflows/ci.yml` exists and is valid YAML.
- [ ] Every `run:` step in the workflow was executed locally in Step 1 and
      exited 0 (record this in your report).
- [ ] The workflow triggers on both `push` to `main` and `pull_request`.
- [ ] No source/test files modified (`git status` shows only the workflow and
      possibly README).
- [ ] `plans/README.md` status row for 003 updated.

## STOP conditions

Stop and report if:

- A `.github/workflows/*.yml` already exists (don't duplicate CI).
- The local gate (Step 1) is not fully green — CI must not be added over a red
  baseline; report which of 001/002 is incomplete.
- The dogfood scan or deterministic eval has no stable non-mutating invocation —
  omit that step and note it, rather than guessing flags.

## Maintenance notes

- When plan 008 lands the doc generator, add a `--check` step so doc drift also
  fails CI (the generator plan describes it).
- Keep the gate single-job and blocking; if it gets slow (>~3–4 min), cache is
  the first lever (`enable-cache: true` is already set), then split pytest into
  its own job — do not drop steps.
- A reviewer should confirm no `continue-on-error` crept in and action versions
  are pinned.
- Consider a matching `.pre-commit-config.yaml` running `ruff format`/`ruff
  check` for the local loop as a follow-up (explicitly deferred here to keep
  this plan to one artifact).
