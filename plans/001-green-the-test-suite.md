# Plan 001: Green the `uv run pytest` suite — repair the docs-removal fallout

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md`.
>
> **Drift check (run first)**:
> `git diff --stat 5dca8d5..HEAD -- tests/docs/test_docs.py tests/integration/test_north_star_lint.py scripts/check_north_star.py tests/fixtures/test_ts_react_next_fixture.py README.md`
> If any of those files changed since this plan was written, compare the
> "Current state" excerpts against the live code before proceeding; on a
> mismatch, treat it as a STOP condition.

## Status

- **Priority**: P1
- **Effort**: M
- **Risk**: MED
- **Depends on**: none
- **Category**: tests
- **Planned at**: commit `5dca8d5`, 2026-07-02

## Why this matters

`uv run pytest` fails on a clean checkout: **18 failed, 858 passed**. Two
commits — `0ab5610 remove old docs and convert agents to claude files` and
`674a01f remove changelog` — deliberately deleted the entire `docs/*.md` prose
tree, `CHANGELOG.md`, and the root `AGENTS.md`, but left ~13 tests plus a lint
script still reading those now-missing files. A permanently-red suite is the
worst possible state for an automated executor: it cannot tell its own
breakage from the known-broken baseline, so every future plan that says "run
the tests" is undermined. This plan makes the suite green by updating the
stale tests/scripts to match the intentional post-removal reality. It is the
prerequisite for the CI gate (plan 003) and de-risks every other plan.

**Key intent (do not second-guess):** the docs were removed *on purpose*. The
north-star content moved from `AGENTS.md` to `CLAUDE.md` (verified: `CLAUDE.md`
contains both `## NAVIGATOR NORTH STAR` and `### Anti-drift checklist`). Your
job is to update the references, **not** to restore the deleted docs. Two
registry-derivable references (`docs/mcp-tools.md`, `docs/cli-reference.md`)
will be regenerated durably by a later plan (008); here you remove their stale
coverage tests.

## Current state

Files and their roles:

- `tests/docs/test_docs.py` — doc-contract tests; ~10 read deleted files.
- `tests/integration/test_north_star_lint.py` — companion to the north-star
  lint; reads deleted root `AGENTS.md`.
- `scripts/check_north_star.py` — lint asserting the north star exists; targets
  deleted root `AGENTS.md`.
- `tests/fixtures/test_ts_react_next_fixture.py` — collected test (only
  `tests/fixtures/python-basic` is excluded from collection); reads deleted
  `docs/language-packs.md`.
- `README.md` — Documentation section links 11 deleted files.
- Four source/script comments point at deleted docs.

What exists on disk in `docs/` now: only `docs/decisions/0001-cbm-optional-by-default.md`
and `docs/diagrams/*.md`. Everything else under `docs/` is gone.

The exact pytest failures (from `uv run pytest`):

```
tests/docs/test_docs.py::test_documentation_map_links_exist
tests/docs/test_docs.py::test_changelog_has_unreleased_and_initial_release
tests/docs/test_docs.py::test_cli_reference_covers_registered_commands
tests/docs/test_docs.py::test_mcp_reference_covers_registered_tools
tests/docs/test_docs.py::test_mcp_reference_documents_result_retrieval_and_envelopes
tests/docs/test_docs.py::test_mcp_docs_do_not_name_post_mvp_excluded_tools
tests/docs/test_docs.py::test_dashboard_docs_do_not_invent_public_command
tests/fixtures/test_ts_react_next_fixture.py::test_fixture_contains_expected_ts_react_next_patterns
tests/integration/test_north_star_lint.py::test_repo_agents_md_has_north_star
tests/integration/test_north_star_lint.py::test_repo_agents_md_contains_section_and_checklist
```

Two more failing test functions in `test_docs.py` also read deleted docs but
did not appear by name above because they raise on `read_text()` at import of
the test body: `test_original_docs_name_python_first_supersession` (reads
`docs/prd.md`, `docs/architecture.md`) and `test_eval_docs_include_deterministic_agent_and_real_smoke`
(reads `docs/evals.md`). Confirm by reading the file.

Excerpt — the north-star lint targets the removed root `AGENTS.md`
(`scripts/check_north_star.py:27-32`):

```python
def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    root = Path(args[0]) if args else Path(__file__).resolve().parents[1]
    agents_md = root / "AGENTS.md"
    if check_north_star(agents_md):
```

Excerpt — the companion test hardcodes `AGENTS.md`
(`tests/integration/test_north_star_lint.py:14`):

```python
REPO_AGENTS_MD = Path("AGENTS.md")
```

The north star now lives in `CLAUDE.md`. The four guardrail strings the
companion test asserts (`Facts stay deterministic`, `LLM layer is opt-in`,
`Stay bounded`, `Engines stay optional`) are all present in `CLAUDE.md`'s
`### Anti-drift checklist` — verify with
`grep -c 'Facts stay deterministic' CLAUDE.md` (expect `1`).

Excerpt — the ts fixture test reads the deleted decision doc
(`tests/fixtures/test_ts_react_next_fixture.py:5,38`):

```python
DECISION_DOC = ROOT / "docs" / "language-packs.md"
...
    decision = DECISION_DOC.read_text()
```

Excerpt — the currently-passing tests you must KEEP unchanged in
`test_docs.py`: `test_readme_names_python_first_mvp_and_safety` (reads
`README.md`, which exists) and `test_no_docs_or_runbooks_use_unsupported_serve_repo_option`
(already guarded with `if path.exists()`).

Repo conventions: tests use plain `assert`; `pytest` config sets
`filterwarnings = ["error"]` (a warning fails the suite) and `--strict-markers`.
Ruff runs `select = ["ALL"]` — unused imports (`F401`) will fail lint, so when
you delete a test that was the only user of an import, delete the import too.

## Commands you will need

| Purpose | Command | Expected on success |
|---|---|---|
| Install | `uv sync` | exit 0 |
| Full suite | `uv run pytest` | exit 0, 0 failed |
| Docs tests only | `uv run pytest tests/docs tests/integration/test_north_star_lint.py tests/fixtures/test_ts_react_next_fixture.py -q` | all pass |
| Lint | `uv run ruff check .` | `All checks passed!` |
| Format check | `uv run ruff format --check .` | exit 0 |

## Scope

**In scope** (the only files you should modify):

- `tests/docs/test_docs.py`
- `tests/integration/test_north_star_lint.py`
- `scripts/check_north_star.py`
- `tests/fixtures/test_ts_react_next_fixture.py`
- `README.md`
- `src/codescent/mcp/finding_payloads.py` (one comment only, line ~29)
- `src/codescent/evals/agent_ux/deterministic.py` (one comment only, line ~12)
- `scripts/dogfood_scan.py` (one comment only, line ~7)
- `scripts/audit_plan_compliance.py` (the `docs/evals.md` / `docs/mcp-tools.md` path entries, lines ~51-52)
- `scripts/dogfood_allowlist.json` (the `_comment` field only)

**Out of scope** (do NOT touch, even though they look related):

- Any file under `docs/` — do not recreate deleted docs; plan 008 handles the
  registry-derivable ones.
- `src/codescent/core/public_surface.py` and any tool/CLI registration — this
  plan changes only tests/docs, never the surface.
- The 95 `basedpyright` errors — those are plan 002. Do not fix type errors here.
- `src/codescent/cli/admin.py:227` — its `"AGENTS.md"` string is the *scaffold
  template name* (`templates/AGENTS.md`, which exists), not a dead reference.
  Leave it.

## Git workflow

- Branch off `main`: `git switch -c advisor/001-green-the-test-suite` (never
  commit to `main`).
- Conventional commits, matching repo style (e.g. `git log` shows
  `test(...)`, `fix(...)`, `chore(...)`). Suggested: one commit
  `test(docs): update doc-contract tests to the post-removal reality`.
- Do NOT push or open a PR.

## Steps

### Step 1: Repoint the north-star lint and its companion test to `CLAUDE.md`

In `scripts/check_north_star.py`: change `agents_md = root / "AGENTS.md"` to
`agents_md = root / "CLAUDE.md"`. Update the module docstring's `AGENTS.md`
mentions (lines 1, and the `MISSING` message) to say `CLAUDE.md`.

In `tests/integration/test_north_star_lint.py`: change `REPO_AGENTS_MD =
Path("AGENTS.md")` to `Path("CLAUDE.md")`. Leave the `tmp_path`-based tests
(`test_lint_fails_when_section_absent`, `test_lint_fails_when_file_missing`)
as-is — they create their own `AGENTS.md` fixtures inside `tmp_path` and
correctly still test the "missing/stripped" behavior against
`check_north_star`. But note: `check_north_star` now reads `root / "CLAUDE.md"`,
so `main([str(tmp_path)])` in those two tests will look for
`tmp_path/"CLAUDE.md"`. Rename the fixture files those tests write from
`AGENTS.md` to `CLAUDE.md` so the negative tests still exercise `main`.

**Verify**: `uv run pytest tests/integration/test_north_star_lint.py -q` →
all pass.

### Step 2: Fix the ts-react-next fixture test

In `tests/fixtures/test_ts_react_next_fixture.py`: remove the `DECISION_DOC`
constant (line ~5) and the block in `test_fixture_contains_expected_ts_react_next_patterns`
that reads `DECISION_DOC.read_text()` and asserts on `decision` (around line
38). Keep every assertion about the fixture files themselves (the
`_fixture_contains` / `FIXTURE_ROOT` checks) — those verify the intentionally-
flawed TS fixture and must stay. Remove the now-unused `ROOT` constant only if
nothing else uses it (grep within the file first).

**Verify**: `uv run pytest tests/fixtures/test_ts_react_next_fixture.py -q` →
passes.

### Step 3: Remove the stale doc-contract tests in `tests/docs/test_docs.py`

Delete these test functions **entirely** (each reads a deleted file that will
not return):

- `test_original_docs_name_python_first_supersession` (docs/prd.md, docs/architecture.md)
- `test_eval_docs_include_deterministic_agent_and_real_smoke` (docs/evals.md)
- `test_changelog_has_unreleased_and_initial_release` (CHANGELOG.md)
- `test_dashboard_docs_do_not_invent_public_command` (docs/dashboard.md)
- `test_cli_reference_covers_registered_commands` (docs/cli-reference.md — plan 008 regenerates this doc and restores a coverage test)
- `test_mcp_reference_covers_registered_tools` (docs/mcp-tools.md — plan 008 restores)
- `test_mcp_reference_documents_result_retrieval_and_envelopes` (docs/mcp-tools.md — plan 008 restores)
- `test_mcp_docs_do_not_name_post_mvp_excluded_tools` (docs/mcp-tools.md — plan 008 restores)
- `test_tool_docs_keep_mvp_tools_and_stage_post_mvp_surface` (docs/mcp-tools.md — plan 008 restores)

Then remove the now-dead module-level constants they were the only users of:
`CHANGELOG`, `EVALS`, `MCP_TOOLS`, `CLI_REFERENCE`, `DASHBOARD`,
`GETTING_STARTED`, `WORKFLOWS`, `CONFIGURATION`, `AGENT_ROUTING`,
`LANGUAGE_PACKS`, `DOC_MAP_TARGETS`, `MVP_TOOLS`, `POST_MVP_PHRASES` (if only
used by removed tests), `POST_MVP_ABSENT_TOOLS`, and the
`PUBLIC_SURFACE`/`REGISTERED_MCP_TOOL_NAMES` import **only if** no surviving
test uses them. Grep before removing each: `grep -n "MVP_TOOLS" tests/docs/test_docs.py`.

**Do not** delete `test_readme_names_python_first_mvp_and_safety`,
`test_no_docs_or_runbooks_use_unsupported_serve_repo_option`, or
`test_agent_routing_templates_are_documented_and_not_auto_written` — see Steps
4–5 for the last one.

**Verify**: `uv run pytest tests/docs/test_docs.py -q` — will still fail on the
two remaining doc-referencing tests until Steps 4–5; that's expected.

### Step 4: Rewrite `test_agent_routing_templates_are_documented_and_not_auto_written`

This test reads `AGENT_ROUTING` (`docs/agent-routing.md`, deleted) plus three
`templates/*.md` files (which exist). Remove the `AGENT_ROUTING.read_text()`
term from the `combined` string; keep the template reads and every assertion
that still resolves against the templates and the `doctor --json` output. If an
assertion asserted a phrase that lived only in `docs/agent-routing.md` and is
not in any template, remove just that assertion. Verify the phrases you keep
actually appear: `grep -rn "use codescent before broad grep" templates/`.

**Verify**: `uv run pytest tests/docs/test_docs.py::test_agent_routing_templates_are_documented_and_not_auto_written -q` → passes.

### Step 5: Rewrite `test_documentation_map_links_exist` into a live-link check, and fix README links

The test's value is "every local markdown link in README (and contract docs)
resolves." Rewrite it to drop the hardcoded `DOC_MAP_TARGETS` existence loop
and keep only the link-resolution loop:

```python
def test_documentation_map_links_exist() -> None:
    for source in (README, *(p for p in DOC_CONTRACT_PATHS if p.exists())):
        for target in _linked_markdown_targets(source.read_text()):
            assert _resolve_local_markdown_target(source, target).exists(), (
                f"{source}: dead link -> {target}"
            )
```

Then fix `README.md`: in the Documentation section and inline references,
remove or repoint every link to a deleted file. Delete the bullets for
getting-started, cli-reference, mcp-tools, workflows, configuration, dashboard,
language-packs, evals, agent-routing, and the CHANGELOG link. Keep the
`docs/decisions/0001-cbm-optional-by-default.md` link (it resolves). If you
remove the "Evals And Smoke" doc link at README line ~90/107, keep the inline
`evals/run_deterministic.py` command block already present — do not remove
commands, only the dead `.md` links. **Do not** delete the assertions in
`test_readme_names_python_first_mvp_and_safety`; confirm the strings it checks
(`python-first mvp`, `uv run codescent serve`, `writes only .codescent`, etc.)
still appear in README after your edits (`uv run pytest tests/docs/test_docs.py::test_readme_names_python_first_mvp_and_safety -q`).

**Verify**: `uv run pytest tests/docs -q` → all pass.

### Step 6: Repoint the four dangling doc comments (no behavior change)

These are comment/docstring text only — do not change any code logic:

- `src/codescent/mcp/finding_payloads.py:29` — replace `docs/ideas/boundedness-bug-fix.md` with a short inline note (the doc is gone); e.g. `# Boundedness controls (bounded list/aggregate output).`
- `src/codescent/evals/agent_ux/deterministic.py:12` — change the `AGENTS.md` reference to `CLAUDE.md`.
- `scripts/dogfood_scan.py:7` and `scripts/dogfood_allowlist.json` `_comment` — replace `docs/workflows.md` with `CLAUDE.md` (or drop the clause).
- `scripts/audit_plan_compliance.py:51-52` — remove the `Path("docs/evals.md")` and `Path("docs/mcp-tools.md")` entries from the processed-paths list (they no longer exist).

**Verify**: `grep -rn "docs/ideas\|docs/evals.md\|docs/mcp-tools.md\|docs/workflows.md" src scripts | grep -v '.venv'` → no matches in the files you edited. (`docs/mcp-tools.md` may reappear in plan 008; that's fine — it's not in this plan's scope.)

### Step 7: Full green + lint

**Verify**:
- `uv run pytest` → exit 0, 0 failed.
- `uv run ruff check .` → `All checks passed!` (fix any `F401` unused-import from deletions).
- `uv run ruff format --check .` → exit 0 (run `uv run ruff format .` if it complains, then re-check).

## Test plan

No new test files. You are pruning/repointing existing tests to match the
intentional docs removal. The surviving, strengthened
`test_documentation_map_links_exist` (Step 5) becomes a durable dead-link guard
for README. After the change:

- `uv run pytest` → 0 failed (was 18 failed).
- The count of passing tests will drop by ~9 (the deleted stale tests); that is
  expected and correct. Note the new pass count in your `plans/README.md`
  status update.

## Done criteria

ALL must hold:

- [ ] `uv run pytest` exits 0 with 0 failures.
- [ ] `uv run ruff check .` prints `All checks passed!`.
- [ ] `uv run ruff format --check .` exits 0.
- [ ] `grep -rn 'Path("AGENTS.md")' tests/ scripts/` returns no matches outside `tmp_path` fixtures.
- [ ] No files outside the in-scope list are modified (`git status`).
- [ ] `plans/README.md` status row for 001 updated to DONE with the new pass count.

## STOP conditions

Stop and report back (do not improvise) if:

- Any file the plan says is "deleted" actually **exists** on disk (e.g.
  `docs/mcp-tools.md` is present) — the tree has drifted; the removal may have
  been reverted, and deleting tests would then be wrong.
- `CLAUDE.md` does **not** contain `## NAVIGATOR NORTH STAR` and
  `### Anti-drift checklist` (Step 1's target is wrong — the north star moved
  elsewhere).
- After Steps 1–6, `uv run pytest` still has failures **outside** the files in
  scope (a failure this plan didn't cause — likely a separate regression).
- Removing a constant/import breaks a test you were told to keep.

## Maintenance notes

- The rewritten `test_documentation_map_links_exist` now guards against future
  dead README links generically — keep it.
- Plan 008 (registry-generated reference docs) will re-add `docs/mcp-tools.md`
  and `docs/cli-reference.md` plus regenerated coverage tests; the tests you
  delete in Step 3 for those two files are intentionally superseded there, not
  lost.
- A reviewer should confirm no *source* behavior changed — every edit is to a
  test, a script, a comment, or README prose.
- Deferred out of scope: the `evals/precision_corpus/labels.json` "see
  AGENTS.md" note (fixture data, cosmetic) and the 95 basedpyright errors (plan
  002).
