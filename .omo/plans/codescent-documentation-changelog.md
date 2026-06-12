# CodeScent Documentation And Changelog

## TL;DR

> Summary: Create the post-PRD-complete documentation set for CodeScent and add
> a root `CHANGELOG.md` that accurately records the first shipped `0.1.0`
> surface. The docs must describe current implemented behavior from the public
> surface registry, CLI modules, tests, README, and completed `.omo` plans, not
> future PRD ideas or stale open questions. Deliverables:
>
> - Concise `README.md` docs hub with links to the full docs set.
> - New/updated docs: `docs/getting-started.md`, `docs/cli-reference.md`,
>   `docs/mcp-tools.md`, `docs/workflows.md`, `docs/configuration.md`,
>   `docs/dashboard.md`, and `docs/language-packs.md`.
> - Root `CHANGELOG.md` with `Unreleased` and `[0.1.0] - 2026-06-12`.
> - Docs tests that pin link integrity, changelog shape, safety claims, command
>   surface coverage, MCP surface coverage, and dashboard/local-only wording.
> - Agent-executed evidence under `.omo/evidence/docs-changelog-*`. Effort:
>   Medium Risk: Medium - broad prose surface, public-surface drift, dashboard
>   launch overclaim risk, and unrelated dirty worktree paths.

## Scope

### Must have

- Treat `.omo/boulder.json:5-24`, `README.md`,
  `src/codescent/core/public_surface.py`, current tests, and completed
  `.omo/plans/codescent-python-mvp.md` / `.omo/plans/codescent-prd-remainder.md`
  as the truth for shipped behavior.
- Use `docs/prd.md` as historical/product-requirements context only. Do not
  document unresolved PRD questions as shipped behavior.
- Keep `README.md` concise: product summary, safety summary, install, fast
  start, docs map, and development gates. Move detailed guides to `docs/*.md`.
- Add `docs/getting-started.md` for the first practical local workflow:
  `uv sync`, `codescent --help`, temp-repo or fixture setup, `init`, `index`,
  `scan`, `report`, `doctor`, `serve`, and where to go next.
- Add `docs/cli-reference.md` for every shipped CLI command declared in
  `src/codescent/core/public_surface.py:124-198`: `init`, `serve`, `index`,
  `scan`, `status`, `doctor`, `report`, `reset`, `watch`, `findings`, `next`,
  `explain`, `export`, `config`, `rules`, `ci`, and `review-diff`.
- Expand `docs/mcp-tools.md` from name inventory into a grouped MCP reference
  grounded in `src/codescent/core/public_surface.py:52-198` and existing
  contract tests under `tests/contract/test_mcp_*.py`.
- Add `docs/workflows.md` for the source-read-only improvement loop: initialize,
  index, scan, choose next finding, retrieve bounded context, plan refactor,
  suggest tests, rescan, mark finding, report/export.
- Add `docs/configuration.md` for `.codescent/` state, config/rules commands,
  routing templates, safe reset behavior, source-read-only boundaries,
  no-runtime-network boundaries, and common errors/recovery.
- Add `docs/dashboard.md` for the loopback dashboard's current verified surface:
  local-only API/UI behavior, exports, rule config updates, smoke script, and
  Chrome/Node dependency notes. Do not invent a public `codescent dashboard`
  command.
- Update `docs/language-packs.md` from future-tense pack planning to current
  supported-language docs: Python and TypeScript/React/Next are shipped; future
  packs remain explicitly future.
- Add root `CHANGELOG.md` using feature-family release notes for `0.1.0`, not a
  commit-by-commit log.
- Extend `tests/docs/test_docs.py` with concrete tests for the new docs and
  changelog.
- Capture evidence under `.omo/evidence/docs-changelog-*`.

### Must NOT have (guardrails, anti-slop, scope boundaries)

- Do not edit product code except docs tests if needed. No CLI, MCP, service,
  dashboard, storage, parser, or rule behavior changes.
- Do not add a public dashboard command. If dashboard launch is inconvenient,
  document the current smoke/programmatic launch path and state the limitation.
- Do not claim Headroom/context-compression features from
  `docs/prd/headroom-influence-prd.md:917-928` are shipped. That untracked PRD
  is future scope unless explicitly labeled as future ideas elsewhere.
- Do not restore, delete, or rewrite unrelated dirty/shared-worktree files:
  `codescent-mcp-test-results.md`, root `AGENTS.md`, `docs/prd/`, or unrelated
  untracked files.
- Do not document unsupported options such as `codescent serve --repo`.
- Do not over-expand README into a long manual.
- Do not make `CHANGELOG.md` mirror every commit or reconstructed micro-release.
- Do not weaken existing docs, CLI, MCP, eval, or safety tests.

## Verification strategy

> Zero human intervention - all verification is agent-executed.

- Test decision: TDD for validation edits in `tests/docs/test_docs.py`. Write
  failing tests first for each docs/changelog invariant, capture RED, then
  update docs and capture GREEN.
- QA policy: every todo has at least one real command or script invocation with
  a binary PASS predicate and evidence path.
- Evidence: `.omo/evidence/docs-changelog-task-<N>-<slug>.*`.
- Minimum focused gate:
  `uv run pytest tests/docs/test_docs.py tests/contract/test_cli.py tests/contract/test_mcp_tool_surface.py tests/contract/test_public_surface_registry.py tests/test_package_metadata.py tests/evals/test_agent_eval_spec.py`
- Quality gate when Python tests are edited: `uv run ruff check .`,
  `uv run ruff format --check .`, and `uv run basedpyright`.
- Manual QA isolation: use `mktemp -d` and copy `tests/fixtures/python-basic`
  before running documented commands that create `.codescent/`; evidence must
  show cleanup and must not modify the source fixture.
- Dashboard smoke: `scripts/smoke_dashboard.py` may require Google Chrome and
  Node (`scripts/smoke_dashboard.py:119-127`). If missing, record the missing
  dependency as blocked evidence and rely on integration tests for the
  non-browser dashboard gate; do not silently pass.

## Execution strategy

### Parallel execution waves

> Target 5-8 todos per wave. < 3 per wave except the final = under-splitting.

Wave 1 (no deps): 1, 2, 3, 4 Wave 2 (after 1-4): 5, 6, 7, 8 Wave 3 (after 5-8):
9, 10 Final wave (after all todos): F1, F2, F3, F4

Critical path: 1 -> 2 -> 5 -> 8 -> 9 -> 10 -> final verification.

### Dependency matrix

| Todo | Depends on | Blocks      | Can parallelize with |
| ---- | ---------- | ----------- | -------------------- |
| 1    | none       | 2-10        | 2, 3, 4              |
| 2    | none       | 5, 8, 9, 10 | 1, 3, 4              |
| 3    | none       | 5, 8, 9, 10 | 1, 2, 4              |
| 4    | none       | 8, 9, 10    | 1, 2, 3              |
| 5    | 1-4        | 8, 9, 10    | 6, 7                 |
| 6    | 1-4        | 8, 9, 10    | 5, 7                 |
| 7    | 1-4        | 8, 9, 10    | 5, 6                 |
| 8    | 5-7        | 9, 10       | none                 |
| 9    | 8          | 10          | none                 |
| 10   | 9          | final       | none                 |

## Todos

> Implementation + Test = ONE todo. Never separate.

- [x] 1. Add docs-link and changelog validation tests What to do / Must NOT do:
     Add focused tests to `tests/docs/test_docs.py` before writing docs. Tests
     must pin local markdown link integrity, docs hub links, changelog shape,
     unsupported `serve --repo` absence, public CLI/MCP coverage, safety claims,
     and dashboard local-only wording. Do not weaken existing tests at
     `tests/docs/test_docs.py:40-128`. Parallelization: Can parallel Y | Wave 1
     | Blocks all docs writes References: `tests/docs/test_docs.py:1-128`,
     `src/codescent/core/public_surface.py:52-198`, `README.md:13-18`,
     `README.md:98-102`, `docs/mcp-tools.md:1-106` Acceptance criteria:
  - RED first:
    `uv run pytest tests/docs/test_docs.py -k "documentation_map or changelog or public_surface or dashboard_local_only"`
    exits nonzero because the new docs/changelog files or assertions are
    missing.
  - New test ids must include: `test_documentation_map_links_exist`,
    `test_changelog_has_unreleased_and_initial_release`,
    `test_cli_reference_covers_registered_commands`,
    `test_mcp_reference_covers_registered_tools`,
    `test_dashboard_docs_do_not_invent_public_command`. QA scenarios: tmux
    channel:
    `tmux new-session -d -s docs-changelog-qa-1 'cd /Users/robertguss/Projects/startups/code-scent-mcp && uv run pytest tests/docs/test_docs.py -k "documentation_map or changelog or public_surface or dashboard_local_only"'`
    PASS if transcript records the intentional RED failures for missing docs or
    missing assertions before implementation. Evidence:
    `.omo/evidence/docs-changelog-task-1-red.txt` Commit: Y |
    `test(docs): pin documentation and changelog contracts` | Files
    `tests/docs/test_docs.py`

- [x] 2. Update README as concise docs hub What to do / Must NOT do: Rewrite
     `README.md` only as a concise landing page and docs map. Keep product
     summary and safety guarantees; link to all deeper docs. Do not duplicate
     the full CLI/MCP reference in README. Do not mention unsupported
     `serve --repo`. Parallelization: Can parallel Y | Wave 1 | Blocks final
     docs map References: `README.md:1-111`, `tests/docs/test_docs.py:40-69`,
     `docs/mcp-tools.md:100-106` Acceptance criteria: GREEN:
     `uv run pytest tests/docs/test_docs.py::test_readme_names_python_first_mvp_and_safety tests/docs/test_docs.py::test_no_docs_or_runbooks_use_unsupported_serve_repo_option tests/docs/test_docs.py::test_documentation_map_links_exist`
     exits 0, and README links exist for `docs/getting-started.md`,
     `docs/cli-reference.md`, `docs/mcp-tools.md`, `docs/workflows.md`,
     `docs/configuration.md`, `docs/dashboard.md`, `docs/language-packs.md`,
     `docs/evals.md`, `docs/agent-routing.md`, and `CHANGELOG.md`. QA scenarios:
     tmux channel:
     `tmux new-session -d -s docs-changelog-qa-2 'cd /Users/robertguss/Projects/startups/code-scent-mcp && sed -n "1,160p" README.md && uv run codescent --help'`
     PASS if README displays the docs map and `codescent --help` runs without
     README documenting unsupported options. Evidence:
     `.omo/evidence/docs-changelog-task-2-readme.txt` Commit: Y |
     `docs(readme): add documentation map` | Files `README.md`,
     `tests/docs/test_docs.py`

- [x] 3. Add getting started guide with isolated first-run workflow What to do /
     Must NOT do: Create `docs/getting-started.md` for a first 10-minute
     workflow. Use a temp copy of `tests/fixtures/python-basic` in examples that
     write `.codescent/`. Include install, `--help`, `init`, `index`, `scan`,
     `status`, `report`, `doctor`, `serve`, next docs links, and common first
     errors. Do not run commands directly against the tracked fixture in
     examples unless they are read-only. Parallelization: Can parallel Y | Wave
     1 | Blocks workflows/docs hub References: `README.md:20-61`,
     `src/codescent/cli/main.py:40-157`, `src/codescent/cli/admin.py:30-60`,
     `src/codescent/cli/reporting.py:57-87` Acceptance criteria: GREEN:
     `uv run pytest tests/docs/test_docs.py::test_documentation_map_links_exist tests/docs/test_docs.py::test_no_docs_or_runbooks_use_unsupported_serve_repo_option`
     exits 0 and the guide contains `mktemp -d`,
     `cp -R tests/fixtures/python-basic`, `uv run codescent init`, `index`,
     `scan`, `status`, `report`, `doctor`, and `serve`. QA scenarios: tmux
     channel:
     `tmux new-session -d -s docs-changelog-qa-3 'cd /Users/robertguss/Projects/startups/code-scent-mcp && tmp=$(mktemp -d) && cp -R tests/fixtures/python-basic "$tmp/repo" && uv run codescent init --repo "$tmp/repo" --json && uv run codescent index --repo "$tmp/repo" --json && uv run codescent scan --repo "$tmp/repo" --json && uv run codescent status --repo "$tmp/repo" --json && rm -rf "$tmp"'`
     PASS if all commands exit 0 and cleanup removes the temp repo. Evidence:
     `.omo/evidence/docs-changelog-task-3-getting-started.txt` Commit: Y |
     `docs: add getting started workflow` | Files `docs/getting-started.md`,
     `tests/docs/test_docs.py`

- [x] 4. Add feature-family changelog What to do / Must NOT do: Create root
     `CHANGELOG.md`. Use `pyproject.toml` version `0.1.0`, the public surface
     registry, README taxonomy, completed `.omo` plans, and current tests as
     sources. Add `Unreleased` and `[0.1.0] - 2026-06-12`. Use feature-family
     bullets, not commit-by-commit history. Exclude
     `docs/prd/headroom-influence-prd.md` future tools and unrelated dirty
     state. Parallelization: Can parallel Y | Wave 1 | Blocks release docs
     References: `README.md:86-102`, `pyproject.toml`,
     `src/codescent/core/public_surface.py:52-198`, `.omo/boulder.json:5-24`,
     `docs/prd/headroom-influence-prd.md:917-928` Acceptance criteria: GREEN:
     `uv run pytest tests/docs/test_docs.py::test_changelog_has_unreleased_and_initial_release`
     exits 0 and asserts `CHANGELOG.md` contains `## [Unreleased]`,
     `## [0.1.0] - 2026-06-12`, `Python-first`, `TypeScript/React/Next`,
     `loopback dashboard`, `source-read-only`, and does not contain
     `retrieve_result`, `context_stats`, `project_guidance`, or
     `project_learnings`. QA scenarios: tmux channel:
     `tmux new-session -d -s docs-changelog-qa-4 'cd /Users/robertguss/Projects/startups/code-scent-mcp && sed -n "1,220p" CHANGELOG.md && git status --short -- CHANGELOG.md codescent-mcp-test-results.md docs/prd'`
     PASS if changelog has the release sections and git status shows no changes
     to unrelated dirty paths beyond their pre-existing state. Evidence:
     `.omo/evidence/docs-changelog-task-4-changelog.txt` Commit: Y |
     `docs(changelog): seed initial release notes` | Files `CHANGELOG.md`,
     `tests/docs/test_docs.py`

- [x] 5. Add CLI reference grounded in Typer command modules What to do / Must
     NOT do: Create `docs/cli-reference.md` covering every command in the
     public-surface registry and real Typer modules. Include purpose, common
     options, JSON vs markdown output where applicable, destructive guardrails,
     failure/recovery notes, and examples. Do not document `serve --repo` or a
     dashboard command. Parallelization: Can parallel Y | Wave 2 | Blocks
     README/docs completion References:
     `src/codescent/core/public_surface.py:124-198`,
     `src/codescent/cli/main.py:40-157`, `src/codescent/cli/admin.py:30-147`,
     `src/codescent/cli/reporting.py:57-231`, `tests/contract/test_cli.py`
     Acceptance criteria: GREEN:
     `uv run pytest tests/docs/test_docs.py::test_cli_reference_covers_registered_commands tests/contract/test_cli.py`
     exits 0. The docs test must derive expected command names from
     `PUBLIC_SURFACE.cli_commands` or the exported constants, not duplicate an
     unverified hand list. QA scenarios: tmux channel:
     `tmux new-session -d -s docs-changelog-qa-5 'cd /Users/robertguss/Projects/startups/code-scent-mcp && for cmd in init serve index scan status doctor report reset watch findings next explain export config rules ci review-diff; do uv run codescent "$cmd" --help >/dev/null || exit 1; done'`
     PASS if every documented command help exits 0. Evidence:
     `.omo/evidence/docs-changelog-task-5-cli-reference.txt` Commit: Y |
     `docs(cli): add command reference` | Files `docs/cli-reference.md`,
     `tests/docs/test_docs.py`

- [x] 6. Expand MCP reference from registry and contract behavior What to do /
     Must NOT do: Update `docs/mcp-tools.md` into a grouped reference. For each
     registered MCP tool, document group, purpose, source-read-only behavior,
     bounded output expectations, and at least one example shape. Use the public
     registry and contract tests. Do not rely on the stale test name
     `test_no_post_mvp_tools_exposed`; cite the actual assertions instead.
     Parallelization: Can parallel Y | Wave 2 | Blocks workflows/docs completion
     References: `docs/mcp-tools.md:1-106`,
     `src/codescent/core/public_surface.py:52-198`,
     `tests/contract/test_mcp_tool_surface.py:64-97`,
     `tests/contract/test_mcp_repo_tools.py`,
     `tests/contract/test_mcp_context_tools.py`,
     `tests/contract/test_mcp_finding_tools.py`,
     `tests/contract/test_mcp_planning_tools.py` Acceptance criteria: GREEN:
     `uv run pytest tests/docs/test_docs.py::test_mcp_reference_covers_registered_tools tests/contract/test_mcp_tool_surface.py tests/contract/test_public_surface_registry.py`
     exits 0. Docs test must compare docs contents to
     `REGISTERED_MCP_TOOL_NAMES`. QA scenarios: tmux channel:
     `tmux new-session -d -s docs-changelog-qa-6 'cd /Users/robertguss/Projects/startups/code-scent-mcp && uv run pytest tests/contract/test_mcp_tool_surface.py tests/contract/test_public_surface_registry.py'`
     PASS if MCP runtime surface and registry tests pass. Evidence:
     `.omo/evidence/docs-changelog-task-6-mcp-reference.txt` Commit: Y |
     `docs(mcp): expand tool reference` | Files `docs/mcp-tools.md`,
     `tests/docs/test_docs.py`

- [x] 7. Add workflow and configuration/state docs What to do / Must NOT do: Add
     `docs/workflows.md` and `docs/configuration.md`. Workflow docs must show
     the safe improvement loop and verification recommendation boundary.
     Configuration docs must cover `.codescent/` state, config/rules, routing
     templates, `doctor`, `reset --dry-run` / `reset --yes`, invalid repo and
     invalid output format recovery, source-read-only, and no runtime network by
     default. Parallelization: Can parallel Y | Wave 2 | Blocks README/docs
     completion References: `README.md:39-58`, `README.md:86-102`,
     `src/codescent/cli/admin.py:30-147`,
     `src/codescent/cli/reporting.py:19-231`, `docs/agent-routing.md`,
     `templates/AGENTS.md`, `templates/CLAUDE.md`, `templates/CODEX.md`
     Acceptance criteria: GREEN:
     `uv run pytest tests/docs/test_docs.py::test_documentation_map_links_exist tests/docs/test_docs.py::test_agent_routing_templates_are_documented_and_not_auto_written tests/docs/test_docs.py::test_no_docs_or_runbooks_use_unsupported_serve_repo_option`
     exits 0 and docs include `reset requires --dry-run or --yes`, `.codescent`,
     `routing_templates`, `source-read-only`, and `runtime no-network`. QA
     scenarios: tmux channel:
     `tmux new-session -d -s docs-changelog-qa-7 'cd /Users/robertguss/Projects/startups/code-scent-mcp && tmp=$(mktemp -d) && cp -R tests/fixtures/python-basic "$tmp/repo" && uv run codescent init --repo "$tmp/repo" --json && uv run codescent reset --repo "$tmp/repo" --dry-run --json && ! uv run codescent reset --repo "$tmp/repo" --json && rm -rf "$tmp"'`
     PASS if dry-run returns JSON, reset without `--dry-run`/`--yes` fails, and
     cleanup runs. Evidence:
     `.omo/evidence/docs-changelog-task-7-workflows-config.txt` Commit: Y |
     `docs: add workflows and configuration guides` | Files `docs/workflows.md`,
     `docs/configuration.md`, `tests/docs/test_docs.py`

- [x] 8. Add dashboard and language-pack docs without overclaims What to do /
     Must NOT do: Add `docs/dashboard.md` and update `docs/language-packs.md`.
     Dashboard docs must state loopback-only, no auth, no remote dashboard, no
     public `codescent dashboard` command, current API/export/rules behavior,
     and smoke dependencies. Language-pack docs must say Python and
     TypeScript/React/Next are current shipped packs and future packs are
     future. Parallelization: Can parallel N | Wave 2 | Blocks final docs checks
     References: `README.md:13-18`, `README.md:86-102`,
     `docs/language-packs.md:1-16`, `src/codescent/dashboard/server.py`,
     `tests/integration/test_dashboard.py:14-194`,
     `scripts/smoke_dashboard.py:39-80`, `scripts/smoke_dashboard.py:119-127`
     Acceptance criteria: GREEN:
     `uv run pytest tests/docs/test_docs.py::test_dashboard_docs_do_not_invent_public_command tests/integration/test_dashboard.py`
     exits 0. Docs must contain `127.0.0.1`, `loopback`, `no auth`,
     `no remote dashboard`, and must not contain `codescent dashboard`. QA
     scenarios: tmux channel:
     `tmux new-session -d -s docs-changelog-qa-8 'cd /Users/robertguss/Projects/startups/code-scent-mcp && uv run pytest tests/integration/test_dashboard.py && uv run python scripts/smoke_dashboard.py --repo tests/fixtures/python-basic --out .omo/evidence/docs-changelog-task-8-dashboard-smoke.json'`
     PASS if integration tests pass and smoke JSON has `"ok": true`; if Chrome
     or Node is missing, evidence must record the missing dependency and the
     worker must not mark the browser-smoke part as passed. Evidence:
     `.omo/evidence/docs-changelog-task-8-dashboard.txt`,
     `.omo/evidence/docs-changelog-task-8-dashboard-smoke.json` Commit: Y |
     `docs: document dashboard and language packs` | Files `docs/dashboard.md`,
     `docs/language-packs.md`, `tests/docs/test_docs.py`

- [x] 9. Run focused docs/changelog gate and fix drift What to do / Must NOT do:
     Run the minimum focused gate, inspect failures, and fix only docs/test
     drift needed for this documentation/changelog scope. Do not touch product
     behavior. Parallelization: Can parallel N | Wave 3 | Blocks final
     verification References: `tests/docs/test_docs.py`,
     `tests/contract/test_cli.py`, `tests/contract/test_mcp_tool_surface.py`,
     `tests/contract/test_public_surface_registry.py`,
     `tests/test_package_metadata.py`, `tests/evals/test_agent_eval_spec.py`
     Acceptance criteria: GREEN:
     `uv run pytest tests/docs/test_docs.py tests/contract/test_cli.py tests/contract/test_mcp_tool_surface.py tests/contract/test_public_surface_registry.py tests/test_package_metadata.py tests/evals/test_agent_eval_spec.py`
     exits 0. QA scenarios: tmux channel:
     `tmux new-session -d -s docs-changelog-qa-9 'cd /Users/robertguss/Projects/startups/code-scent-mcp && uv run pytest tests/docs/test_docs.py tests/contract/test_cli.py tests/contract/test_mcp_tool_surface.py tests/contract/test_public_surface_registry.py tests/test_package_metadata.py tests/evals/test_agent_eval_spec.py'`
     PASS if transcript ends with all selected tests passing. Evidence:
     `.omo/evidence/docs-changelog-task-9-focused-gate.txt` Commit: Y |
     `test(docs): verify documentation surface` | Files docs/test/doc-only fixes
     as needed

- [x] 10. Run quality, link, and dirty-worktree final receipts What to do / Must
      NOT do: Run quality gates for edited Python tests, capture final
      dirty-worktree state, and confirm unrelated files were not
      restored/deleted/rewritten. If only markdown changed and docs tests
      already passed, still run ruff/basedpyright because
      `tests/docs/test_docs.py` changed. Parallelization: Can parallel N | Wave
      3 | Blocks final verification References: `pyproject.toml`,
      `tests/docs/test_docs.py`,
      `.omo/drafts/codescent-documentation-changelog-planning-notepad.md`
      Acceptance criteria: GREEN: `uv run ruff check .`,
      `uv run ruff format --check .`, and `uv run basedpyright` exit 0.
      `git status --short` shows only intended docs, docs tests, `CHANGELOG.md`,
      `.omo/evidence/docs-changelog-*`, and pre-existing unrelated dirty paths.
      QA scenarios: tmux channel:
      `tmux new-session -d -s docs-changelog-qa-10 'cd /Users/robertguss/Projects/startups/code-scent-mcp && uv run ruff check . && uv run ruff format --check . && uv run basedpyright && git status --short'`
      PASS if quality commands exit 0 and status does not show unexpected
      product code changes. Evidence:
      `.omo/evidence/docs-changelog-task-10-quality.txt`,
      `.omo/evidence/docs-changelog-task-10-status.txt` Commit: Y |
      `docs: finalize documentation and changelog` | Files intended
      docs/tests/evidence only

## Final verification wave (after ALL todos)

> Runs in parallel. ALL must APPROVE. Surface results and wait for the user's
> explicit okay before declaring implementation complete.

- [x] F1. Plan compliance audit Command:
      `uv run pytest tests/docs/test_docs.py tests/contract/test_cli.py tests/contract/test_mcp_tool_surface.py tests/contract/test_public_surface_registry.py tests/test_package_metadata.py tests/evals/test_agent_eval_spec.py`
      PASS if all selected tests pass and every todo evidence file exists.
      Evidence: `.omo/evidence/docs-changelog-final-plan-compliance.txt`

- [x] F2. Code quality review Command:
      `uv run ruff check . && uv run ruff format --check . && uv run basedpyright`
      PASS if all commands exit 0. Evidence:
      `.omo/evidence/docs-changelog-final-code-quality.txt`

- [x] F3. Real manual QA Command:
      `tmp=$(mktemp -d) && cp -R tests/fixtures/python-basic "$tmp/repo" && uv run codescent init --repo "$tmp/repo" --json && uv run codescent index --repo "$tmp/repo" --json && uv run codescent scan --repo "$tmp/repo" --json && uv run codescent report --repo "$tmp/repo" --format json && uv run codescent doctor --repo "$tmp/repo" --json && rm -rf "$tmp"`
      PASS if all commands exit 0, output is valid JSON where expected, and
      cleanup removes the temp repo. Evidence:
      `.omo/evidence/docs-changelog-final-manual-qa.txt`

- [x] F4. Scope fidelity and dirty-worktree audit Command:
      `git diff -- README.md docs CHANGELOG.md tests/docs/test_docs.py .omo/plans/codescent-documentation-changelog.md && git status --short`
      PASS if diff contains only docs/changelog/docs-test/plan/evidence changes
      and does not restore/delete/rewrite unrelated dirty files such as
      `codescent-mcp-test-results.md`, root `AGENTS.md`, or `docs/prd/`.
      Evidence: `.omo/evidence/docs-changelog-final-scope.txt`

## Commit strategy

- Do not auto-commit unless the user explicitly asks.
- If committing later, use atomic Conventional Commits:
  - `test(docs): pin documentation and changelog contracts`
  - `docs(readme): add documentation map`
  - `docs: add project usage guides`
  - `docs(changelog): seed initial release notes`
  - `docs: document dashboard and language packs`
- Keep unrelated dirty files unstaged.

## Success criteria

- `README.md` is a concise docs hub, not a long manual.
- New docs exist and are linked: `docs/getting-started.md`,
  `docs/cli-reference.md`, `docs/workflows.md`, `docs/configuration.md`,
  `docs/dashboard.md`, plus updated `docs/mcp-tools.md` and
  `docs/language-packs.md`.
- `CHANGELOG.md` exists with `Unreleased` and `[0.1.0] - 2026-06-12`.
- CLI docs cover every command in `PUBLIC_SURFACE.cli_commands`.
- MCP docs cover every registered MCP tool in `REGISTERED_MCP_TOOL_NAMES`.
- Docs do not mention unsupported `codescent serve --repo` or
  `codescent dashboard`.
- Dashboard docs clearly state loopback-only, no auth, no remote dashboard, and
  current smoke dependencies.
- Changelog does not claim future Headroom tools from `docs/prd/`.
- Docs tests, CLI/MCP surface tests, package metadata test, eval-spec test,
  ruff, format check, and basedpyright pass.
- Manual QA evidence exists under `.omo/evidence/docs-changelog-*`.
- Unrelated dirty worktree paths are preserved.
