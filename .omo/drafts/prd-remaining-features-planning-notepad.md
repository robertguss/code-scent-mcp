# CodeScent PRD Remainder Planning Notepad

## Request

Use `omo:ulw-plan` to create a plan to implement the remaining features from
`docs/prd.md`, now that the MVP is working.

## Skills Survey

- `omo:ulw-plan`: selected. The user explicitly invoked it, and the work is
  architecture-scale planning with 5+ steps, ambiguous scope, and many modules.
- `omo:programming`: relevant for the eventual worker because this is a
  Python-first repo, but not used for implementation in this planner turn.
- `omo:ultraresearch` / `librarian`: relevant pattern for broad research, but
  `ulw-plan` already mandates collect/verify/design/adversarial lanes.
- `omo:review-work`: relevant after implementation, not for this plan-only
  turn.
- `github:*`, `linear:*`, `vercel:*`, iOS/macOS/frontend/browser skills:
  not selected; the requested scope is local repo product planning, not PR,
  issue tracker, deployment, platform app, or UI implementation.

## Goal

Produce one decision-complete implementation plan under `.omo/plans/` after
explicit user approval. Planner scope only: read, search, analyze, and write
only `.omo/drafts/` or `.omo/plans/`.

## Success Criteria

1. Current MVP baseline is grounded in repo files and evidence.
2. Remaining PRD scope is separated from already-shipped MVP scope.
3. Genuine ambiguities are surfaced with recommended options before plan
   generation.
4. No product code is edited during planning.
5. Final plan, after approval, includes executable tests, real-surface QA, and
   evidence paths for each todo.

## Dirty Worktree

Initial `git status --short` showed untracked runtime/test artifacts:

- `codescent-mcp-test-results.md`
- `scripts/__pycache__/`
- `src/codescent/**/__pycache__/`
- `tests/**/__pycache__/`
- `tests/fixtures/python-basic/.codescent/`

Planning must not overwrite or depend on these artifacts except to treat the
test-results markdown as user-provided evidence.

## Evidence Log

- Read `omo:ulw-plan` full workflow.
- Searched memory for CodeScent context.
- Captured dirty worktree before planning.
- Directly read `docs/prd.md`, `docs/architecture.md`, `docs/mcp-tools.md`,
  `.omo/plans/codescent-python-mvp.md`, `pyproject.toml`, and current MCP
  modules under `src/codescent/mcp/`.
- Spawned five read-only research lanes:
  - implementation surface vs MVP
  - PRD remainder extraction
  - tests/package/QA surface
  - execution ordering
  - risk/QA adversarial checks
- Closed all research lanes after integrating results.

## Grounded Facts

- The MVP is no longer pending. The user-provided
  `codescent-mcp-test-results.md` and existing final evidence show the full
  source-read-only MCP loop works on the fixture repo and `lx_data_lake`.
- Current public MCP surface is explicitly the 15 MVP tools in
  `docs/mcp-tools.md`; post-MVP tools are intentionally excluded there.
- Current CLI surface is `init`, `serve`, `index`, `scan`, `status`, and
  `doctor`.
- The repo already has pytest, ruff, basedpyright, contract tests, integration
  tests, deterministic evals, source-read-only proof scripts, real-repo smoke,
  and `.omo/evidence/task-*` conventions.
- Runtime safety constraints remain hard requirements: local-first,
  source-read-only for analyzed source, no runtime network by default, bounded
  context, thin MCP adapters, and no target-project test execution unless a
  later feature explicitly introduces an opt-in execution boundary.

## PRD Remainder Buckets

### Already Covered by MVP

- Local MCP-first Python vertical loop.
- Repo map/status, bounded file/content search, Python symbols/context, code
  health scan/report, finding context, next improvement, refactor plan,
  suggested tests, mark finding, and rescan.
- SQLite `.codescent/` state, finding lifecycle basics, deterministic evals,
  fixture smoke, real repo smoke, and source-read-only proof.

### Recommended Post-MVP Plan Scope

Plan the remaining PRD features as staged post-MVP releases:

1. Search expansion:
   `multi_search_content`, `search_changed_files`, `search_todos`,
   `search_tests`, smart-case, pagination, frecency/search history, richer
   ranking reasons.
2. Code intelligence expansion:
   `find_references`, `find_callers`, `find_callees`, `get_related_files`,
   `get_impact`, reference/call-edge persistence, improved related-file and
   test matching.
3. Reporting and scoring:
   `get_finding`, `explain_score`, report/export CLI, JSON/Markdown reports,
   clearer score/evidence breakdown.
4. Durable backlog/progress workflow:
   `get_backlog`, `get_progress`, `get_regressions`, richer lifecycle states,
   resolved/regressed trend history, CLI `findings`, `next`, `explain`.
5. Verification and risk:
   `verify_change` as recommend-only first, verification run records,
   relevant-test ranking, risk scoring, branch/diff-aware reports.
6. Configuration and extensibility:
   config/rules CLI, rule enable/disable, command hints, language/framework/rule
   pack interfaces. Use the current Python pack as the first migrated pack.
7. Language/framework expansion:
   after the pack interface exists, choose the first non-Python pack.
   Candidate from PRD: TypeScript/JavaScript/React/Next.js.
8. CI/PR mode:
   CI command, diff mode, Markdown/JSON outputs, quality thresholds.
9. Optional subjective LLM review:
   opt-in only, privacy notice, provider config, clearly separated subjective
   findings.
10. Local dashboard:
    local web UI for findings, trends, rules, index status, and exports.

## Recommended Approach

Recommend a single XL plan that covers all PRD remainder features but stages
implementation in strict dependency waves:

1. Expand search and tool-surface contracts first.
2. Add graph/code-intelligence primitives needed by impact and verification.
3. Deepen reporting/backlog/progress on top of stable findings and graph data.
4. Add recommend-only verification/risk and diff analysis.
5. Add config/rule/language-pack extension seams before any non-Python pack.
6. Add the first non-Python pack after the extension seam exists.
7. Add CI/PR mode only after diff/risk/reporting are proven locally.
8. Add optional LLM review after deterministic reports are mature.
9. Add dashboard last, backed by the same local services and reports.

## Required QA Pattern for the Plan

Every feature todo should include:

- Test-first acceptance: unit/integration/contract/eval test named explicitly.
- Manual QA through CLI, MCP smoke, or real repo smoke as appropriate.
- Evidence path under `.omo/evidence/prd-next-task-<N>-<slug>.*`.
- JSON/asserted pass criteria, not stdout-only claims.
- Source-read-only and no-network checks where the feature touches runtime
  analysis.
- Final gates: `uv run pytest`, `uv run ruff check .`,
  `uv run ruff format --check .`, `uv run basedpyright`, MCP smoke, real repo
  smoke, source-read-only proof, and plan compliance.

## Ambiguities for User Approval

1. Scope size:
   - Option A: plan every PRD phase through dashboard in one decision-complete
     roadmap plan.
   - Option B: plan only the next shippable post-MVP release.
   - Recommendation: Option A, because the user asked for "remaining features"
     from `docs/prd.md`; make it staged so execution can still stop after any
     release.
2. First non-Python language pack:
   - Option A: TypeScript/JavaScript/React/Next.js as the PRD originally
     recommends.
   - Option B: stay Python-only and harden pack interfaces before choosing.
   - Recommendation: Option A, but only after implementing pack interfaces and
     migrating Python into that architecture.
3. `verify_change` behavior:
   - Option A: recommend-only first, no target command execution.
   - Option B: opt-in local command execution with strict allowlists.
   - Recommendation: Option A for the next plan; add execution only as a later
     explicit phase.
4. Dashboard timing:
   - Option A: include dashboard in this full remainder plan as the final stage.
   - Option B: leave dashboard out of this plan.
   - Recommendation: Option A, because it is in the PRD remainder, but place it
     last and keep it local-only.

## Open Approval-Gate Items

Approved by user. Final plan written to `.omo/plans/codescent-prd-remainder.md`.
