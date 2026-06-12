# CodeScent Documentation And Changelog Planning Notepad

## Request

Use `omo:ulw-plan` after completing all of `docs/prd.md` to create documentation
for the project and create a root changelog for tracking changes over time.

## Planner Scope

This is an `omo:ulw-plan` turn. The planner may read, search, run read-only
analysis, and write `.omo/drafts/` or `.omo/plans/` artifacts only. It must not
edit `README.md`, `docs/*.md`, `CHANGELOG.md`, tests, or product code until the
user approves the proposed approach and a worker executes the plan.

## Skills Survey

- `omo:ulw-plan`: selected because the user explicitly invoked it and the task
  requires a decision-complete implementation plan spanning docs, changelog,
  tests, QA, and current release state.
- `omo:programming`: relevant to the eventual worker only if docs tests are
  added or updated in Python files.
- `omo:review-work`: relevant as a final verification lane after the worker
  implements the documentation/changelog changes.
- `omo:visual-qa`: relevant only if the worker updates dashboard docs and wants
  to re-run browser/dashboard proof.
- GitHub/Linear/Vercel/iOS/macOS/browser skills: not selected for planning; this
  is local repo documentation planning, not a PR, issue, deployment, or
  platform-app task.

## Grounded Facts

- Current branch: `main...origin/main`.
- Dirty worktree: `codescent-mcp-test-results.md` is deleted. The plan must
  treat that deletion as unrelated user/shared-worktree state and must not
  restore or rewrite the file.
- `pyproject.toml` declares package version `0.1.0`, package name `codescent`,
  Python `>=3.12`, MIT license, and CLI entrypoint
  `codescent = "codescent.cli.main:app"`.
- `.omo/boulder.json` marks both prior workstreams completed:
  `codescent-python-mvp` and `codescent-prd-remainder`.
- Existing docs:
  - `README.md`: concise entry point with install, CLI workflow, MCP stdio,
    eval/smoke commands, implemented surface, and out-of-scope notes.
  - `docs/prd.md`: product vision and requirements, not a user guide.
  - `docs/architecture.md`: high-level architecture and design rationale.
  - `docs/mcp-tools.md`: current MCP and CLI public-surface inventory.
  - `docs/evals.md`: deterministic eval, agent-in-the-loop eval, real smoke, and
    source-read-only proof.
  - `docs/language-packs.md`: language-pack/parser direction; currently terse.
  - `docs/agent-routing.md`: routing-template overview.
  - `scripts/run_agent_eval.md`: operational eval transcript runbook.
  - `templates/AGENTS.md`, `templates/CLAUDE.md`, `templates/CODEX.md`: optional
    routing templates.
- Existing docs tests in `tests/docs/test_docs.py` pin README safety language,
  no unsupported `serve --repo` docs, PRD/architecture supersession language,
  MCP docs headings, eval docs, and routing-template behavior.
- There is no root `CHANGELOG.md` and no changelog-specific test yet.

## Research Lanes

Three read-only subagents were spawned and closed:

1. Documentation inventory lane:
   - Verified current docs and command surfaces.
   - Found gaps around getting started, command reference, finding lifecycle,
     dashboard guide, config/state reference, supported language guide, and
     template adoption guide.
2. Changelog planning lane:
   - Recommended one seeded `0.1.0` release plus an `Unreleased` section.
   - Recommended feature-family bullets instead of commit-by-commit history.
   - Confirmed not to include the unrelated deleted
     `codescent-mcp-test-results.md`.
3. Risk/QA lane:
   - Confirmed docs correctness currently runs through `tests/docs/test_docs.py`
     and adjacent CLI/MCP/public-surface contract tests.
   - Recommended adding changelog validation because no changelog-specific test
     exists.

## Recommended Documentation Set

Use a pragmatic post-PRD-complete doc set:

1. Keep `README.md` as the concise landing page and docs map.
2. Add `docs/getting-started.md` for the first local workflow: install, `init`,
   `index`, `scan`, `report`, `serve`, and dashboard entry.
3. Add `docs/cli-reference.md` for all shipped CLI commands, examples, output
   formats, safety notes, and destructive-command guardrails.
4. Expand or restructure `docs/mcp-tools.md` into a real MCP reference with
   groups, tool purpose, inputs, outputs, and bounded/source-read-only behavior.
5. Add `docs/workflows.md` for the finding lifecycle and safe improvement loop:
   scan, next, context, plan, suggested tests, rescan, mark, report.
6. Add `docs/configuration.md` for `.codescent/` state, config precedence,
   rules, reset behavior, routing templates, and no-network/source-read-only
   boundaries.
7. Add `docs/dashboard.md` for loopback dashboard usage, exports, local-only
   behavior, and smoke verification.
8. Update `docs/language-packs.md` into supported-language documentation for
   Python and TypeScript/React/Next plus pack boundaries.
9. Add root `CHANGELOG.md` with `Unreleased` and `[0.1.0] - 2026-06-12`.
10. Add/extend docs tests to validate the new docs map, changelog shape, command
    references, safety promises, and public-surface drift.

## Recommended Changelog Shape

Seed `CHANGELOG.md` as a first release:

- `## [Unreleased]` with empty `Added`, `Changed`, `Fixed`, `Docs`, and `Tests`
  sections.
- `## [0.1.0] - 2026-06-12` with family-level bullets for:
  - package/CLI/MCP scaffold;
  - Python-first local source-read-only MVP;
  - storage/migrations/locking;
  - search expansion;
  - graph/context/impact;
  - reports/findings/health/risk/planning/verification;
  - config/rules/reset and prompt resources;
  - TypeScript/React/Next pack support;
  - CI/PR review and opt-in subjective review;
  - loopback dashboard;
  - docs, tests, evals, smoke, and safety proof.

Do not mirror every commit and do not include the unrelated deleted
`codescent-mcp-test-results.md`.

## Proposed Verification Strategy

Implementation should be TDD for validation changes:

- Add failing docs tests first for new docs/changelog expectations, then write
  docs to pass.
- Minimum focused gate:
  `uv run pytest tests/docs/test_docs.py tests/contract/test_cli.py tests/contract/test_mcp_tool_surface.py tests/contract/test_public_surface_registry.py tests/test_package_metadata.py tests/evals/test_agent_eval_spec.py`
- Quality gate: `uv run ruff check .`, `uv run ruff format --check .`, and
  `uv run basedpyright` if Python tests are edited.
- Manual QA: use tmux to run representative documented commands against
  `tests/fixtures/python-basic`, capture `.omo/evidence/docs-changelog-*`
  artifacts, and verify the docs mention only commands that succeed.

## Ambiguities For Approval

1. Documentation scope:
   - Option A: full practical project docs now, including getting started, CLI
     reference, MCP reference, workflows, configuration, dashboard, language
     packs, README updates, and changelog.
   - Option B: only README plus root changelog.
   - Recommendation: Option A, because the PRD is fully implemented and the
     missing value is user/operator discoverability across the shipped surface.
2. Changelog scope:
   - Option A: one `0.1.0` release plus `Unreleased`.
   - Option B: multiple historical sections reconstructed from commits.
   - Recommendation: Option A, because package version is `0.1.0` and no tags
     indicate real intermediate releases.
3. Validation scope:
   - Option A: add/extend docs tests for changelog and docs links/surface
     claims.
   - Option B: prose-only docs update with manual review.
   - Recommendation: Option A, because this repo already pins docs through tests
     and the changelog currently has no validation.

## Approval Gate

Waiting for explicit user approval before writing
`.omo/plans/codescent-documentation-changelog.md`.
