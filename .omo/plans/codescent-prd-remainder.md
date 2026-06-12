# CodeScent PRD Remainder Plan

## TL;DR

> Summary: Implement the remaining `docs/prd.md` features after the proven
> Python MVP as staged post-MVP releases: search expansion, graph intelligence,
> reports, backlog/progress, verification/risk, configuration, pack seams,
> TypeScript/React/Next support, CI/PR mode, optional LLM review, and a local
> dashboard.
> Deliverables:
> - Expanded MCP and CLI surface with matching docs and contract tests.
> - Persistent graph/search/report/backlog/verification data with migrations.
> - Internal language/framework/rule pack registry, then TypeScript/React/Next
>   pack.
> - Local-only CI/PR reporting, opt-in subjective review, and dashboard.
> Effort: XL
> Risk: High - broad product surface, public API expansion, storage migrations,
> multi-language parsing, optional networked LLM review, and browser UI.

## Scope

### Must Have

- Treat the current Python MCP MVP as complete and do not reopen the MVP plan.
- Preserve local-first, source-read-only runtime for analyzed source.
- Preserve no runtime network by default. Install-time dependency fetching and
  explicitly opted-in subjective LLM review are the only allowed exceptions.
- Keep FastMCP tool functions thin; product logic stays in services/engine.
- Update public MCP/CLI docs and contract tests before exposing any new public
  tool or command.
- Add schema migrations and migration tests for every storage-affecting task.
- Add one-writer/many-reader safety tests before long-running surfaces such as
  watch mode, dashboard, MCP server, and CI scans share `.codescent/`.
- Use JSON/asserted evidence for every smoke/eval/manual QA artifact.
- Keep `verify_change` recommend-only first: it records recommended
  verification plans and statuses, but it must not execute target project
  commands in this plan.
- Implement pack seams before the first non-Python pack. Migrate current Python
  parser/rules into the pack registry before adding TypeScript/React/Next.
- First non-Python pack scope: `.js`, `.jsx`, `.ts`, `.tsx` files; imports and
  exports; functions/classes; React components/hooks; basic Next.js pages/app
  route detection; deterministic React/Next rule pack.
- Dashboard scope: Python-served local web UI bound to `127.0.0.1` by default,
  no auth in this plan because it is loopback-only, no external requests, no
  source writes, and browser-smoke verified.
- Plan all remaining PRD roadmap phases through dashboard, plus non-roadmap
  PRD leftovers that are part of the same product surface: CLI `report`,
  `reset`, `watch`, `findings`, `next`, `explain`, `export`, `config`, `rules`,
  prompt resources, report exports, success metrics, and routing-file templates
  where they support the product.

### Must NOT Have

- Do not add automatic source edits or autofix.
- Do not execute target repository tests/builds/lints from `verify_change`.
- Do not expose HTTP/SSE MCP transport, hosted service, auth, or cloud indexing.
- Do not let optional LLM review run by default or store subjective findings as
  deterministic facts.
- Do not add dashboard remote access, telemetry, CDN assets, or external
  browser resources.
- Do not add a public external plugin API before the internal pack registry is
  stable; document the internal registry first, then package-entry-point support
  later in this plan.
- Do not index `.codescent/`, `.env`, `.git/`, virtualenvs, caches, binary
  artifacts, generated/vendor/build outputs, `data/`, or `archive/` by default.
- Do not rely on untracked `__pycache__`, fixture `.codescent/`, or stale smoke
  state as proof.

## Decisions

| Topic | Decision |
| --- | --- |
| Scope | One staged plan for all unimplemented PRD features through dashboard. |
| Pack boundary | Start with internal Python registry interfaces; then add package entry point discovery and repo-local pack config. |
| Python pack | Migrate current Python parser/rules into the pack registry before TS/React. |
| First non-Python pack | TypeScript/JavaScript/React/Next.js, after pack seams. |
| `verify_change` | Recommend-only first; persist recommendation records and status, no subprocess execution. |
| Reports | Add `ReportService` before CI/dashboard exports. |
| Dashboard | Python-served loopback web UI, no auth, no network assets, browser-smoke verified. |
| CLI `reset` | Add only as safe reset of `.codescent/` state; never deletes source. Requires `--yes` for non-dry-run. |

## Verification Strategy

> Zero human intervention - all verification is agent-executed.

- Test decision: TDD with `pytest`, contract tests for public MCP/CLI surface,
  integration tests for services/storage, eval tests for workflow quality, and
  smoke scripts for real-surface MCP/CLI/browser use.
- QA policy: every todo has agent-executed scenarios and writes evidence under
  `.omo/evidence/prd-remainder-task-<N>-<slug>.*`.
- Manual QA channels:
  - MCP: `uv run python scripts/smoke_mcp.py ...`
  - CLI/tmux: `tmux new-session -d -s ulw-qa-prd-<N> '<command>'` plus
    `tmux capture-pane -pS -2000 -t ulw-qa-prd-<N>`
  - Browser: local dashboard browser smoke with screenshot artifact.
- Every storage migration todo includes a test that opens an MVP-era
  `.codescent/index.sqlite`, migrates it, and proves old MVP commands still
  work.
- Every runtime-analysis todo includes source-read-only proof:
  `uv run python scripts/prove_source_read_only.py --repo tests/fixtures/python-basic --out <evidence>`.
- Every public-surface todo updates:
  `docs/mcp-tools.md` or README/CLI docs, contract tests, and smoke evidence.

## Execution Strategy

### Parallel Execution Waves

Wave 1 (public-surface unlock and storage foundation): 1, 2, 3, 4

Wave 2 (search expansion): 5, 6, 7, 8

Wave 3 (graph/code intelligence): 9, 10, 11, 12

Wave 4 (reports, scoring, backlog): 13, 14, 15, 16

Wave 5 (verification/risk and prompt workflow): 17, 18, 19

Wave 6 (configuration and pack seams): 20, 21, 22

Wave 7 (TypeScript/React/Next pack): 23, 24, 25, 26

Wave 8 (CI/PR and subjective review): 27, 28, 29

Wave 9 (dashboard): 30, 31, 32

Final wave: F1, F2, F3, F4, F5

Critical path: 1 -> 2 -> 3 -> 5 -> 9 -> 13 -> 17 -> 20 -> 22 -> 23 -> 27 -> 30 -> final verification.

### Dependency Matrix

| Todo | Depends on | Blocks | Can parallelize with |
| --- | --- | --- | --- |
| 1 | none | 2-32 | 2, 3, 4 |
| 2 | none | 5-32 | 1, 3, 4 |
| 3 | none | 5-32 | 1, 2, 4 |
| 4 | none | 5-32 | 1, 2, 3 |
| 5 | 1,2,3 | 6-8, 17 | 6, 7, 8 |
| 6 | 1,2,3 | 8, 17 | 5, 7 |
| 7 | 1,2,3 | 8, 15 | 5, 6 |
| 8 | 5,6,7 | 17, 27 | none |
| 9 | 1,2,3 | 10-12, 17 | 10 |
| 10 | 9 | 11,12 | 9 |
| 11 | 9,10 | 12,17,23 | none |
| 12 | 9,10,11 | 17,18 | none |
| 13 | 1,2,3 | 14,27,30 | 14 |
| 14 | 13 | 15,16,27 | 13 |
| 15 | 13,14 | 16,30 | none |
| 16 | 13,14,15 | 30 | none |
| 17 | 8,12,13 | 18,19,27 | 18 |
| 18 | 12,17 | 19,27 | 17 |
| 19 | 17,18 | 27 | none |
| 20 | 1,2,3 | 21,22,23 | 21 |
| 21 | 20 | 22,23 | 20 |
| 22 | 20,21 | 23-26 | none |
| 23 | 22 | 24-26 | 24 |
| 24 | 22,23 | 25,26 | 23 |
| 25 | 23,24 | 26 | none |
| 26 | 23,24,25 | 27,30 | none |
| 27 | 13,17,19,26 | 28,29 | none |
| 28 | 13,17,20 | 29 | none |
| 29 | 27,28 | 30 | none |
| 30 | 13,15,16,29 | 31,32 | none |
| 31 | 30 | 32 | none |
| 32 | 30,31 | final | none |

## Todos

> Implementation + Test = ONE todo. Never separate.

- [x] 1. Add post-MVP public surface registry and docs unlock
  What to do / Must NOT do: Replace the MVP-only public-surface lock with a versioned surface registry that lists MVP tools, post-MVP tools, CLI commands, and release stage. Update `docs/mcp-tools.md` to stop saying "exactly these MVP tools" for future releases while preserving a documented MVP surface. Do not expose new runtime tools yet.
  Parallelization: Can parallel Y | Wave 1 | Blocks all public tools
  References: `docs/mcp-tools.md:3`, `docs/mcp-tools.md:21`, `docs/prd.md:493`, `docs/prd.md:650`, `tests/contract/test_mcp_tool_surface.py`, `tests/contract/test_cli.py`
  Acceptance criteria: Red first: `tests/contract/test_public_surface_registry.py::test_post_mvp_surface_is_declared_but_not_registered` fails because no registry exists. Green: `uv run pytest tests/contract/test_public_surface_registry.py tests/contract/test_mcp_tool_surface.py tests/contract/test_cli.py`.
  QA scenarios: tmux: `tmux new-session -d -s ulw-qa-prd-1 'cd /Users/robertguss/Projects/startups/code-scent-mcp && uv run python scripts/audit_plan_compliance.py --plan .omo/plans/codescent-prd-remainder.md --evidence .omo/evidence'`; PASS if JSON reports the declared public surface and no missing evidence. Evidence `.omo/evidence/prd-remainder-task-1-public-surface.json`.
  Commit: Y | `docs(surface): declare post-mvp public surface` | Files `docs/mcp-tools.md`, `src/codescent/core/public_surface.py`, `tests/contract/test_public_surface_registry.py`, `scripts/audit_plan_compliance.py`

- [x] 2. Add schema migration framework for post-MVP storage
  What to do / Must NOT do: Extend storage migrations beyond schema version 2 and add MVP database fixture migration tests. Do not drop existing tables or break current MVP `.codescent/index.sqlite` files.
  Parallelization: Can parallel Y | Wave 1 | Blocks storage-affecting tasks
  References: `src/codescent/storage/schema.py:4`, `docs/architecture.md:612`, `docs/prd.md:684`
  Acceptance criteria: Red first: `tests/integration/test_storage_migrations.py::test_migrates_mvp_schema_to_latest_without_data_loss` fails against a version-2 fixture. Green: `uv run pytest tests/integration/test_storage_migrations.py tests/integration/test_storage.py`.
  QA scenarios: tmux: `tmux new-session -d -s ulw-qa-prd-2 'cd /Users/robertguss/Projects/startups/code-scent-mcp && uv run codescent status --repo tests/fixtures/python-basic --json'`; PASS if status exits 0 after migration and `database_ok` is true. Evidence `.omo/evidence/prd-remainder-task-2-migration.txt`.
  Commit: Y | `feat(storage): add post-mvp schema migrations` | Files `src/codescent/storage/schema.py`, `src/codescent/storage/repository.py`, `tests/fixtures/storage/**`, `tests/integration/test_storage_migrations.py`

- [x] 3. Add shared result pagination and bounds contracts
  What to do / Must NOT do: Add typed pagination/bounds models reused by search, reports, backlog, and dashboard APIs. Do not return whole files or unbounded result sets.
  Parallelization: Can parallel Y | Wave 1 | Blocks search/report/backlog/dashboard
  References: `docs/prd.md:246`, `docs/prd.md:1064`, `docs/architecture.md:752`
  Acceptance criteria: Red first: `tests/unit/test_models.py::test_pagination_bounds_are_enforced` fails because pagination options are missing. Green: `uv run pytest tests/unit/test_models.py tests/contract/test_mcp_search_tools.py`.
  QA scenarios: tmux: `tmux new-session -d -s ulw-qa-prd-3 'cd /Users/robertguss/Projects/startups/code-scent-mcp && uv run python - <<\"PY\"\nfrom codescent.core.models import PageOptions\nprint(PageOptions(limit=999).model_dump())\nPY'`; PASS if output caps the limit. Evidence `.omo/evidence/prd-remainder-task-3-pagination.txt`.
  Commit: Y | `feat(core): add shared pagination bounds` | Files `src/codescent/core/models.py`, `tests/unit/test_models.py`

- [x] 4. Add one-writer/many-reader storage concurrency guard
  What to do / Must NOT do: Extend `.codescent` locking so CLI, MCP, watch, dashboard, and CI scans cannot corrupt state. Allow concurrent readers and one writer. Do not use destructive lock cleanup.
  Parallelization: Can parallel Y | Wave 1 | Blocks watch/dashboard/CI
  References: `src/codescent/storage/repository.py`, `docs/architecture.md:600`, `docs/prd.md:762`
  Acceptance criteria: Red first: `tests/integration/test_storage_concurrency.py::test_concurrent_reader_waits_for_writer_without_corruption` fails. Green: `uv run pytest tests/integration/test_storage_concurrency.py tests/integration/test_storage.py`.
  QA scenarios: tmux: `tmux new-session -d -s ulw-qa-prd-4 'cd /Users/robertguss/Projects/startups/code-scent-mcp && uv run python scripts/prove_source_read_only.py --repo tests/fixtures/python-basic --out .omo/evidence/prd-remainder-task-4-read-only.json'`; PASS if JSON has `ok: true`, `changed_paths: []`, and `network_attempts: 0`. Evidence `.omo/evidence/prd-remainder-task-4-read-only.json`.
  Commit: Y | `feat(storage): guard concurrent codescent state access` | Files `src/codescent/storage/repository.py`, `tests/integration/test_storage_concurrency.py`

- [x] 5. Add multi-search content tool
  What to do / Must NOT do: Implement `multi_search_content` with bounded merged/deduped results, query-level reasons, pagination, and no full-file dumps.
  Parallelization: Can parallel Y | Wave 2 | Blocks broader search QA
  References: `docs/prd.md:535`, `docs/prd.md:1079`, `src/codescent/services/search.py`
  Acceptance criteria: Red first: `tests/contract/test_mcp_search_tools.py::test_multi_search_content_merges_and_dedupes_bounded_results` fails. Green: `uv run pytest tests/contract/test_mcp_search_tools.py tests/integration/test_search.py`.
  QA scenarios: MCP smoke: `uv run python scripts/smoke_mcp.py --repo tests/fixtures/python-basic search_expansion --out .omo/evidence/prd-remainder-task-5-mcp-search.json`; PASS if artifact includes `multi_search_content`, merged unique paths, and bounded snippets. Evidence `.omo/evidence/prd-remainder-task-5-mcp-search.json`.
  Commit: Y | `feat(search): add bounded multi content search` | Files `src/codescent/services/search.py`, `src/codescent/mcp/search_tools.py`, `tests/contract/test_mcp_search_tools.py`, `scripts/smoke_mcp.py`

- [x] 6. Add changed-file search
  What to do / Must NOT do: Implement `search_changed_files` over git modified/staged/untracked plus index-detected changes for non-git repos. Do not shell out unsafely or include ignored/generated files.
  Parallelization: Can parallel Y | Wave 2 | Blocks risk/diff features
  References: `docs/prd.md:539`, `docs/prd.md:1071`, `docs/architecture.md:587`
  Acceptance criteria: Red first: `tests/integration/test_search.py::test_search_changed_files_filters_to_git_and_index_changes` fails. Green: `uv run pytest tests/integration/test_search.py tests/contract/test_mcp_search_tools.py`.
  QA scenarios: tmux: `tmux new-session -d -s ulw-qa-prd-6 'cd /Users/robertguss/Projects/startups/code-scent-mcp && uv run python scripts/smoke_mcp.py --repo tests/fixtures/python-basic search_changed --out .omo/evidence/prd-remainder-task-6-changed-search.json'`; PASS if JSON includes only changed fixture paths and excludes `.codescent`. Evidence `.omo/evidence/prd-remainder-task-6-changed-search.json`.
  Commit: Y | `feat(search): add changed file search` | Files `src/codescent/services/git.py`, `src/codescent/services/search.py`, `src/codescent/mcp/search_tools.py`, `tests/integration/test_search.py`

- [x] 7. Add TODO and test search tools
  What to do / Must NOT do: Implement `search_todos` and `search_tests` with bounded results, TODO/FIXME/HACK grouping, and likely-test ranking for query/file/symbol/finding inputs.
  Parallelization: Can parallel Y | Wave 2 | Blocks verification ranking
  References: `docs/prd.md:543`, `docs/prd.md:547`, `docs/architecture.md:335`
  Acceptance criteria: Red first: `tests/contract/test_mcp_search_tools.py::test_search_todos_and_tests_are_bounded_and_ranked` fails. Green: `uv run pytest tests/contract/test_mcp_search_tools.py tests/integration/test_search.py`.
  QA scenarios: MCP smoke: `uv run python scripts/smoke_mcp.py --repo tests/fixtures/python-basic search_todos_tests --out .omo/evidence/prd-remainder-task-7-todos-tests.json`; PASS if artifact has TODO results and likely tests for `workflow`. Evidence `.omo/evidence/prd-remainder-task-7-todos-tests.json`.
  Commit: Y | `feat(search): add todo and test search tools` | Files `src/codescent/services/search.py`, `src/codescent/mcp/search_tools.py`, `tests/contract/test_mcp_search_tools.py`

- [x] 8. Add frecency, smart-case, and pagination to search
  What to do / Must NOT do: Persist search history/frecency signals, add smart-case matching, and return page cursors for search tools. Do not leak private query contents outside local SQLite.
  Parallelization: Can parallel N | Wave 2 | Blocks CI/risk ranking
  References: `docs/prd.md:1064`, `docs/prd.md:1069`, `docs/prd.md:710`, `docs/architecture.md:630`
  Acceptance criteria: Red first: `tests/integration/test_search.py::test_frecency_and_pagination_affect_rank_without_unbounded_results` fails. Green: `uv run pytest tests/integration/test_search.py tests/integration/test_storage_migrations.py`.
  QA scenarios: MCP smoke: `uv run python scripts/smoke_mcp.py --repo tests/fixtures/python-basic search_frecency --out .omo/evidence/prd-remainder-task-8-frecency.json`; PASS if repeated search changes local frecency ranking and remains bounded. Evidence `.omo/evidence/prd-remainder-task-8-frecency.json`.
  Commit: Y | `feat(search): add frecency and pagination` | Files `src/codescent/services/search.py`, `src/codescent/storage/schema.py`, `tests/integration/test_search.py`

- [x] 9. Persist references and call edges
  What to do / Must NOT do: Add reference and call-edge storage with confidence labels. Start with Python support through existing AST adapter. Do not claim low-confidence edges as certain.
  Parallelization: Can parallel Y | Wave 3 | Blocks graph tools
  References: `docs/prd.md:566`, `docs/architecture.md:682`, `docs/architecture.md:692`, `src/codescent/engine/parsers/python.py`
  Acceptance criteria: Red first: `tests/integration/test_repo_index.py::test_index_persists_references_and_call_edges_with_confidence` fails. Green: `uv run pytest tests/integration/test_repo_index.py tests/unit/test_python_parser.py`.
  QA scenarios: tmux: `tmux new-session -d -s ulw-qa-prd-9 'cd /Users/robertguss/Projects/startups/code-scent-mcp && uv run codescent index --repo tests/fixtures/python-basic --json'`; PASS if JSON/index inspection shows reference and call-edge counts. Evidence `.omo/evidence/prd-remainder-task-9-graph-index.txt`.
  Commit: Y | `feat(symbols): persist references and call edges` | Files `src/codescent/engine/parsers/python.py`, `src/codescent/storage/schema.py`, `src/codescent/services/repo_index.py`, `tests/integration/test_repo_index.py`

- [x] 10. Add reference, caller, and callee MCP tools
  What to do / Must NOT do: Implement `find_references`, `find_callers`, and `find_callees` using persisted graph data with bounded, confidence-labeled results.
  Parallelization: Can parallel Y | Wave 3 | Blocks related files and impact
  References: `docs/prd.md:566`, `docs/prd.md:570`, `docs/prd.md:574`, `docs/prd.md:1115`
  Acceptance criteria: Red first: `tests/contract/test_mcp_context_tools.py::test_reference_graph_tools_return_bounded_confidence_labeled_results` fails. Green: `uv run pytest tests/contract/test_mcp_context_tools.py tests/integration/test_context.py`.
  QA scenarios: MCP smoke: `uv run python scripts/smoke_mcp.py --repo tests/fixtures/python-basic graph_context --out .omo/evidence/prd-remainder-task-10-graph-tools.json`; PASS if artifact contains all three graph tools and no whole-file dumps. Evidence `.omo/evidence/prd-remainder-task-10-graph-tools.json`.
  Commit: Y | `feat(context): expose reference graph tools` | Files `src/codescent/services/context.py`, `src/codescent/mcp/context_tools.py`, `tests/contract/test_mcp_context_tools.py`

- [x] 11. Add related-file detection
  What to do / Must NOT do: Implement `get_related_files` from imports, tests, directory proximity, search similarity, and git history. Return reasons and confidence.
  Parallelization: Can parallel N | Wave 3 | Blocks impact and dashboard detail
  References: `docs/prd.md:578`, `docs/architecture.md:370`, `docs/prd.md:1185`
  Acceptance criteria: Red first: `tests/integration/test_context.py::test_related_files_include_import_test_directory_and_git_reasons` fails. Green: `uv run pytest tests/integration/test_context.py tests/contract/test_mcp_context_tools.py`.
  QA scenarios: MCP smoke: `uv run python scripts/smoke_mcp.py --repo tests/fixtures/python-basic related_files --out .omo/evidence/prd-remainder-task-11-related-files.json`; PASS if reasons include at least `test_match` and `import_graph`. Evidence `.omo/evidence/prd-remainder-task-11-related-files.json`.
  Commit: Y | `feat(context): add related file detection` | Files `src/codescent/services/context.py`, `src/codescent/mcp/context_tools.py`, `tests/integration/test_context.py`

- [x] 12. Add impact analysis
  What to do / Must NOT do: Implement `get_impact` for file/symbol/finding inputs using references, callers, related files, changed-file status, and likely tests. Keep it bounded and confidence-labeled.
  Parallelization: Can parallel N | Wave 3 | Blocks verification/risk
  References: `docs/prd.md:583`, `docs/prd.md:1198`, `docs/prd.md:1254`
  Acceptance criteria: Red first: `tests/contract/test_mcp_planning_tools.py::test_get_impact_reports_blast_radius_without_false_certainty` fails. Green: `uv run pytest tests/contract/test_mcp_planning_tools.py tests/integration/test_refactor_planning.py`.
  QA scenarios: MCP smoke: `uv run python scripts/smoke_mcp.py --repo tests/fixtures/python-basic impact --out .omo/evidence/prd-remainder-task-12-impact.json`; PASS if artifact includes affected files, likely tests, risk notes, and confidence. Evidence `.omo/evidence/prd-remainder-task-12-impact.json`.
  Commit: Y | `feat(planning): add impact analysis` | Files `src/codescent/services/refactor_planning.py`, `src/codescent/mcp/planning_tools.py`, `tests/contract/test_mcp_planning_tools.py`

- [x] 13. Add ReportService and structured finding detail
  What to do / Must NOT do: Add `ReportService` and `get_finding` with stable JSON payloads, evidence, status history, and score inputs. Do not mix subjective and deterministic finding types.
  Parallelization: Can parallel Y | Wave 4 | Blocks report/export/CI/dashboard
  References: `docs/prd.md:597`, `docs/prd.md:800`, `docs/architecture.md:480`
  Acceptance criteria: Red first: `tests/integration/test_reports.py::test_report_service_returns_finding_detail_with_evidence_and_history` fails. Green: `uv run pytest tests/integration/test_reports.py tests/contract/test_mcp_finding_tools.py`.
  QA scenarios: MCP smoke: `uv run python scripts/smoke_mcp.py --repo tests/fixtures/python-basic finding_detail --out .omo/evidence/prd-remainder-task-13-finding-detail.json`; PASS if artifact includes `get_finding`, evidence JSON keys, and status history. Evidence `.omo/evidence/prd-remainder-task-13-finding-detail.json`.
  Commit: Y | `feat(reports): add report service and finding detail` | Files `src/codescent/services/reports.py`, `src/codescent/mcp/finding_tools.py`, `tests/integration/test_reports.py`

- [x] 14. Add score explanation
  What to do / Must NOT do: Implement `explain_score` for findings and reports with deterministic ranking inputs, severity/confidence rationale, and next-step guidance.
  Parallelization: Can parallel Y | Wave 4 | Blocks CI/dashboard explanations
  References: `docs/prd.md:609`, `docs/architecture.md:388`
  Acceptance criteria: Red first: `tests/contract/test_mcp_finding_tools.py::test_explain_score_returns_deterministic_ranking_reasons` fails. Green: `uv run pytest tests/contract/test_mcp_finding_tools.py tests/integration/test_reports.py`.
  QA scenarios: MCP smoke: `uv run python scripts/smoke_mcp.py --repo tests/fixtures/python-basic explain_score --out .omo/evidence/prd-remainder-task-14-explain-score.json`; PASS if artifact includes score inputs and no subjective claims. Evidence `.omo/evidence/prd-remainder-task-14-explain-score.json`.
  Commit: Y | `feat(health): explain deterministic scores` | Files `src/codescent/services/reports.py`, `src/codescent/mcp/finding_tools.py`, `tests/contract/test_mcp_finding_tools.py`

- [x] 15. Add backlog, progress, and regression tools
  What to do / Must NOT do: Implement `get_backlog`, `get_progress`, and `get_regressions` plus richer lifecycle states. Preserve existing IDs across rescans.
  Parallelization: Can parallel N | Wave 4 | Blocks dashboard progress
  References: `docs/prd.md:1215`, `docs/prd.md:1231`, `docs/architecture.md:408`
  Acceptance criteria: Red first: `tests/integration/test_findings.py::test_backlog_progress_and_regressions_survive_rescan` fails. Green: `uv run pytest tests/integration/test_findings.py tests/contract/test_mcp_finding_tools.py`.
  QA scenarios: MCP smoke: `uv run python scripts/smoke_mcp.py --repo tests/fixtures/python-basic backlog_progress --out .omo/evidence/prd-remainder-task-15-backlog.json`; PASS if artifact shows open/resolved/regressed counts across two scans. Evidence `.omo/evidence/prd-remainder-task-15-backlog.json`.
  Commit: Y | `feat(findings): add backlog progress and regressions` | Files `src/codescent/services/findings.py`, `src/codescent/mcp/finding_tools.py`, `tests/integration/test_findings.py`

- [x] 16. Add report/export CLI commands
  What to do / Must NOT do: Add `codescent report`, `codescent export --format json|markdown`, `codescent findings`, `codescent next`, and `codescent explain <finding-id>`. Do not add destructive `reset` yet.
  Parallelization: Can parallel N | Wave 4 | Blocks CI/dashboard exports
  References: `docs/prd.md:662`, `docs/prd.md:671`, `docs/prd.md:674`
  Acceptance criteria: Red first: `tests/contract/test_cli.py::test_report_findings_next_explain_and_export_commands` fails. Green: `uv run pytest tests/contract/test_cli.py tests/docs/test_docs.py`.
  QA scenarios: tmux: `tmux new-session -d -s ulw-qa-prd-16 'cd /Users/robertguss/Projects/startups/code-scent-mcp && uv run codescent report --repo tests/fixtures/python-basic --format json'`; PASS if captured output parses as JSON with findings and score explanations. Evidence `.omo/evidence/prd-remainder-task-16-cli-report.txt`.
  Commit: Y | `feat(cli): add report and backlog commands` | Files `src/codescent/cli/main.py`, `README.md`, `tests/contract/test_cli.py`

- [x] 17. Add recommend-only verify_change
  What to do / Must NOT do: Implement `verify_change` to recommend commands, likely tests, missing characterization tests, and record a non-executed verification recommendation. Do not run subprocesses.
  Parallelization: Can parallel Y | Wave 5 | Blocks risk reports
  References: `docs/prd.md:623`, `docs/prd.md:1256`, `docs/architecture.md:463`, `docs/architecture.md:799`
  Acceptance criteria: Red first: `tests/contract/test_mcp_planning_tools.py::test_verify_change_records_recommendations_without_execution` fails. Green: `uv run pytest tests/contract/test_mcp_planning_tools.py tests/security/test_runtime_safety.py`.
  QA scenarios: MCP smoke: `uv run python scripts/smoke_mcp.py --repo tests/fixtures/python-basic verify_change --out .omo/evidence/prd-remainder-task-17-verify-change.json`; PASS if artifact has `executes: false`, recommended commands, and persisted recommendation ID. Evidence `.omo/evidence/prd-remainder-task-17-verify-change.json`.
  Commit: Y | `feat(verification): add recommend-only verify change` | Files `src/codescent/services/verification.py`, `src/codescent/mcp/planning_tools.py`, `src/codescent/storage/schema.py`, `tests/contract/test_mcp_planning_tools.py`

- [x] 18. Add diff-aware risk reports
  What to do / Must NOT do: Implement `review_diff_risk` and `get_changed_file_health` using git changed files, impact, findings, and verification recommendations. Do not require GitHub or network.
  Parallelization: Can parallel Y | Wave 5 | Blocks CI/PR
  References: `docs/prd.md:1261`, `docs/prd.md:1268`, `docs/architecture.md:593`
  Acceptance criteria: Red first: `tests/contract/test_mcp_finding_tools.py::test_diff_risk_tools_report_changed_file_health_locally` fails. Green: `uv run pytest tests/contract/test_mcp_finding_tools.py tests/integration/test_repo_index.py`.
  QA scenarios: MCP smoke: `uv run python scripts/smoke_mcp.py --repo tests/fixtures/python-basic diff_risk --out .omo/evidence/prd-remainder-task-18-diff-risk.json`; PASS if artifact includes changed files, risk score, findings, and suggested tests. Evidence `.omo/evidence/prd-remainder-task-18-diff-risk.json`.
  Commit: Y | `feat(risk): add diff aware health reports` | Files `src/codescent/services/risk.py`, `src/codescent/mcp/finding_tools.py`, `tests/contract/test_mcp_finding_tools.py`

- [x] 19. Add workflow prompt resources
  What to do / Must NOT do: Expose MCP prompt resources for safe refactor, symbol investigation, characterization tests, changed-file slop review, risky refactor verification, and code-health improvement. Prompts must be inspectable and must not override local safety constraints.
  Parallelization: Can parallel N | Wave 5 | Blocks agent workflow polish
  References: `docs/prd.md:638`, `docs/prd.md:1229`
  Acceptance criteria: Red first: `tests/contract/test_mcp_prompt_resources.py::test_prompt_resources_are_registered_and_safety_bounded` fails. Green: `uv run pytest tests/contract/test_mcp_prompt_resources.py tests/contract/test_mcp_tool_surface.py`.
  QA scenarios: MCP smoke: `uv run python scripts/smoke_mcp.py --repo tests/fixtures/python-basic prompts --out .omo/evidence/prd-remainder-task-19-prompts.json`; PASS if artifact lists prompt names and safety text. Evidence `.omo/evidence/prd-remainder-task-19-prompts.json`.
  Commit: Y | `feat(mcp): add safe workflow prompt resources` | Files `src/codescent/mcp/prompts.py`, `src/codescent/mcp/server.py`, `tests/contract/test_mcp_prompt_resources.py`

- [x] 20. Add full project config model and CLI config command
  What to do / Must NOT do: Implement include/exclude paths, generated/vendor/build config, command hints, token budgets, privacy settings, and optional LLM settings in repository-local config. Preserve current precedence: defaults < config < CLI flags < MCP args.
  Parallelization: Can parallel Y | Wave 6 | Blocks rules/packs/LLM
  References: `docs/prd.md:721`, `docs/prd.md:723`, `docs/architecture.md:810`
  Acceptance criteria: Red first: `tests/unit/test_models.py::test_project_config_parses_full_prd_surface_with_precedence` fails. Green: `uv run pytest tests/unit/test_models.py tests/contract/test_cli.py`.
  QA scenarios: tmux: `tmux new-session -d -s ulw-qa-prd-20 'cd /Users/robertguss/Projects/startups/code-scent-mcp && uv run codescent config --repo tests/fixtures/python-basic --json'`; PASS if JSON includes command hints, token budgets, privacy, and pack settings. Evidence `.omo/evidence/prd-remainder-task-20-config.txt`.
  Commit: Y | `feat(config): add full project configuration surface` | Files `src/codescent/core/models.py`, `src/codescent/services/config.py`, `src/codescent/cli/main.py`, `tests/unit/test_models.py`

- [x] 21. Add rule configuration and safe reset/watch CLI
  What to do / Must NOT do: Add `codescent rules`, safe `.codescent`-only `codescent reset --dry-run|--yes`, and `codescent watch` with lock-safe incremental indexing. Do not delete source or execute target tests.
  Parallelization: Can parallel Y | Wave 6 | Blocks pack/rule customization
  References: `docs/prd.md:664`, `docs/prd.md:670`, `docs/prd.md:676`
  Acceptance criteria: Red first: `tests/contract/test_cli.py::test_rules_watch_and_reset_are_safe_and_codescent_scoped` fails. Green: `uv run pytest tests/contract/test_cli.py tests/integration/test_storage_concurrency.py`.
  QA scenarios: tmux: `tmux new-session -d -s ulw-qa-prd-21 'cd /Users/robertguss/Projects/startups/code-scent-mcp && uv run codescent reset --repo tests/fixtures/python-basic --dry-run --json'`; PASS if JSON lists only `.codescent` deletions and `deleted: false`. Evidence `.omo/evidence/prd-remainder-task-21-reset.txt`.
  Commit: Y | `feat(cli): add rules watch and safe reset` | Files `src/codescent/cli/main.py`, `src/codescent/services/rules.py`, `tests/contract/test_cli.py`

- [x] 22. Add internal language/framework/rule pack registry
  What to do / Must NOT do: Create internal pack interfaces and registry, migrate current Python parser/rules into a Python pack, and support repo-local pack enable/disable config. Do not add TypeScript parsing yet.
  Parallelization: Can parallel N | Wave 6 | Blocks TS/React pack
  References: `docs/prd.md:1277`, `docs/prd.md:1285`, `docs/architecture.md:523`, `src/codescent/engine/parsers/python.py`
  Acceptance criteria: Red first: `tests/integration/test_packs.py::test_python_pack_registers_parser_rules_and_context_without_behavior_regression` fails. Green: `uv run pytest tests/integration/test_packs.py tests/unit/test_rules_python.py tests/unit/test_python_parser.py`.
  QA scenarios: MCP smoke: `uv run python scripts/smoke_mcp.py --repo tests/fixtures/python-basic full_loop --out .omo/evidence/prd-remainder-task-22-python-pack-loop.json`; PASS if full loop still finds Python findings through the pack registry. Evidence `.omo/evidence/prd-remainder-task-22-python-pack-loop.json`.
  Commit: Y | `feat(packs): add internal pack registry` | Files `src/codescent/engine/packs.py`, `src/codescent/engine/parsers/python.py`, `src/codescent/engine/rules/**`, `tests/integration/test_packs.py`

- [x] 23. Add TypeScript/JavaScript fixture and parser dependency decision
  What to do / Must NOT do: Add `tests/fixtures/ts-react-next-basic` with `.js`, `.jsx`, `.ts`, `.tsx`, React components/hooks, and basic Next routes. Choose and document the parser approach. Prefer a local deterministic parser library or stdlib-compatible adapter; no runtime network.
  Parallelization: Can parallel Y | Wave 7 | Blocks TS pack
  References: `docs/prd.md:1099`, `docs/prd.md:1293`, `docs/prd.md:1294`
  Acceptance criteria: Red first: `tests/fixtures/test_ts_react_next_fixture.py::test_fixture_contains_expected_ts_react_next_patterns` fails. Green: `uv run pytest tests/fixtures/test_ts_react_next_fixture.py`.
  QA scenarios: tmux: `tmux new-session -d -s ulw-qa-prd-23 'cd /Users/robertguss/Projects/startups/code-scent-mcp && find tests/fixtures/ts-react-next-basic -type f | sort'`; PASS if fixture includes JS/JSX/TS/TSX, app/pages routes, and tests. Evidence `.omo/evidence/prd-remainder-task-23-ts-fixture.txt`.
  Commit: Y | `test(fixtures): add ts react next fixture` | Files `tests/fixtures/ts-react-next-basic/**`, `tests/fixtures/test_ts_react_next_fixture.py`, `docs/architecture.md`

- [x] 24. Add TypeScript/JavaScript parser pack
  What to do / Must NOT do: Implement parser pack for `.js`, `.jsx`, `.ts`, `.tsx`: symbols, imports/exports, functions/classes, React components/hooks, Next routes with confidence labels. Do not support arbitrary transpilation or typechecking.
  Parallelization: Can parallel Y | Wave 7 | Blocks TS rules
  References: `docs/prd.md:1099`, `docs/prd.md:1101`, `docs/prd.md:1102`, `docs/prd.md:1103`
  Acceptance criteria: Red first: `tests/integration/test_ts_react_next_parser.py::test_ts_pack_indexes_symbols_imports_components_hooks_and_routes` fails. Green: `uv run pytest tests/integration/test_ts_react_next_parser.py tests/integration/test_packs.py`.
  QA scenarios: tmux: `tmux new-session -d -s ulw-qa-prd-24 'cd /Users/robertguss/Projects/startups/code-scent-mcp && uv run codescent index --repo tests/fixtures/ts-react-next-basic --json'`; PASS if JSON/index inspection includes TypeScript and React symbol counts. Evidence `.omo/evidence/prd-remainder-task-24-ts-index.txt`.
  Commit: Y | `feat(packs): add ts react next parser` | Files `src/codescent/engine/packs_ts.py`, `tests/integration/test_ts_react_next_parser.py`

- [x] 25. Add TypeScript/React/Next rule pack
  What to do / Must NOT do: Add deterministic rules for large component, too many hooks, too many props, too many exports, route handler doing too much, duplicate literals, TODO cluster, missing nearby test, and suspicious generated code.
  Parallelization: Can parallel N | Wave 7 | Blocks TS eval
  References: `docs/prd.md:1141`, `docs/prd.md:1145`, `docs/prd.md:1159`
  Acceptance criteria: Red first: `tests/integration/test_ts_react_next_rules.py::test_ts_react_next_rules_find_expected_fixture_smells_with_evidence` fails. Green: `uv run pytest tests/integration/test_ts_react_next_rules.py tests/unit/test_rules_python.py`.
  QA scenarios: tmux: `tmux new-session -d -s ulw-qa-prd-25 'cd /Users/robertguss/Projects/startups/code-scent-mcp && uv run codescent scan --repo tests/fixtures/ts-react-next-basic --json'`; PASS if JSON includes expected React/Next rule IDs with evidence. Evidence `.omo/evidence/prd-remainder-task-25-ts-rules.txt`.
  Commit: Y | `feat(packs): add ts react next rules` | Files `src/codescent/engine/rules/ts_react_next.py`, `tests/integration/test_ts_react_next_rules.py`

- [x] 26. Add TypeScript/React/Next MCP and eval smoke
  What to do / Must NOT do: Extend deterministic evals and MCP smoke scripts to prove the TS/React/Next pack completes the improvement loop without source edits.
  Parallelization: Can parallel N | Wave 7 | Blocks CI/dashboard pack coverage
  References: `docs/prd.md:1120`, `docs/prd.md:1170`, `docs/evals.md`
  Acceptance criteria: Red first: `tests/evals/test_deterministic_eval.py::test_ts_react_next_pack_meets_expected_eval_thresholds` fails. Green: `uv run pytest tests/evals/test_deterministic_eval.py tests/contract/test_mcp_tool_surface.py`.
  QA scenarios: MCP smoke: `uv run python scripts/smoke_mcp.py --repo tests/fixtures/ts-react-next-basic full_loop --out .omo/evidence/prd-remainder-task-26-ts-full-loop.json`; PASS if full loop selects a TS/React finding and source hashes are unchanged. Evidence `.omo/evidence/prd-remainder-task-26-ts-full-loop.json`.
  Commit: Y | `test(evals): add ts react next mcp eval` | Files `evals/fixtures/ts-react-next.expected.json`, `tests/evals/test_deterministic_eval.py`, `scripts/smoke_mcp.py`

- [x] 27. Add CI and PR/diff review mode
  What to do / Must NOT do: Add `codescent ci` and `codescent review-diff` local commands with JSON and Markdown output, thresholds, changed-file health, risk report, and suggested tests. Do not call GitHub APIs or network.
  Parallelization: Can parallel N | Wave 8 | Blocks dashboard import/export
  References: `docs/prd.md:1342`, `docs/prd.md:1350`, `docs/prd.md:1357`
  Acceptance criteria: Red first: `tests/contract/test_cli.py::test_ci_and_review_diff_emit_json_markdown_and_threshold_exit_codes` fails. Green: `uv run pytest tests/contract/test_cli.py tests/integration/test_reports.py`.
  QA scenarios: tmux: `tmux new-session -d -s ulw-qa-prd-27 'cd /Users/robertguss/Projects/startups/code-scent-mcp && uv run codescent ci --repo tests/fixtures/python-basic --format json --threshold warn'`; PASS if JSON includes risk, changed-file health, suggested tests, and deterministic exit behavior. Evidence `.omo/evidence/prd-remainder-task-27-ci.txt`.
  Commit: Y | `feat(ci): add local ci and diff review mode` | Files `src/codescent/cli/main.py`, `src/codescent/services/ci.py`, `tests/contract/test_cli.py`

- [x] 28. Add optional subjective LLM review abstraction
  What to do / Must NOT do: Add disabled-by-default subjective review provider interface, fake provider tests, inspectable prompts, privacy notice, and separate subjective finding storage. Do not make network calls in tests or default runtime.
  Parallelization: Can parallel N | Wave 8 | Blocks subjective review reports
  References: `docs/prd.md:1309`, `docs/prd.md:1328`, `docs/architecture.md:805`
  Acceptance criteria: Red first: `tests/security/test_runtime_safety.py::test_subjective_review_is_disabled_by_default_and_uses_fake_provider_in_tests` fails. Green: `uv run pytest tests/security/test_runtime_safety.py tests/integration/test_subjective_review.py`.
  QA scenarios: tmux: `tmux new-session -d -s ulw-qa-prd-28 'cd /Users/robertguss/Projects/startups/code-scent-mcp && uv run codescent report --repo tests/fixtures/python-basic --include-subjective --provider fake --format json'`; PASS if JSON labels subjective findings separately and records fake provider. Evidence `.omo/evidence/prd-remainder-task-28-subjective.txt`.
  Commit: Y | `feat(review): add opt-in subjective review seam` | Files `src/codescent/services/subjective_review.py`, `src/codescent/storage/schema.py`, `tests/integration/test_subjective_review.py`

- [ ] 29. Add routing templates and adoption docs
  What to do / Must NOT do: Add optional AGENTS/CLAUDE/Codex routing-file templates that instruct agents to use CodeScent before broad grep and to respect source-read-only behavior. Do not auto-write templates into analyzed repos.
  Parallelization: Can parallel Y | Wave 8 | Blocks final docs
  References: `docs/prd.md:1479`, `docs/prd.md:1480`, `docs/prd.md:867`
  Acceptance criteria: Red first: `tests/docs/test_docs.py::test_agent_routing_templates_are_documented_and_not_auto_written` fails. Green: `uv run pytest tests/docs/test_docs.py tests/security/test_runtime_safety.py`.
  QA scenarios: tmux: `tmux new-session -d -s ulw-qa-prd-29 'cd /Users/robertguss/Projects/startups/code-scent-mcp && uv run codescent doctor --repo tests/fixtures/python-basic --json'`; PASS if doctor recommends templates but does not write them. Evidence `.omo/evidence/prd-remainder-task-29-routing.txt`.
  Commit: Y | `docs: add agent routing templates` | Files `docs/agent-routing.md`, `templates/AGENTS.md`, `templates/CLAUDE.md`, `tests/docs/test_docs.py`

- [ ] 30. Add local dashboard service and read API
  What to do / Must NOT do: Add a Python-served dashboard bound to `127.0.0.1` by default with local JSON endpoints for status, findings, progress, rules, reports, and exports. Do not expose remote bind by default or fetch external assets.
  Parallelization: Can parallel N | Wave 9 | Blocks dashboard UI
  References: `docs/prd.md:1365`, `docs/prd.md:1373`, `docs/prd.md:1385`
  Acceptance criteria: Red first: `tests/integration/test_dashboard.py::test_dashboard_binds_loopback_and_serves_local_read_api` fails. Green: `uv run pytest tests/integration/test_dashboard.py tests/security/test_runtime_safety.py`.
  QA scenarios: HTTP call: `curl -i http://127.0.0.1:<port>/api/status`; PASS if status is 200, content-type JSON, and body has `read_only: true`. Evidence `.omo/evidence/prd-remainder-task-30-dashboard-api.txt`.
  Commit: Y | `feat(dashboard): add local dashboard service` | Files `src/codescent/dashboard/**`, `src/codescent/cli/main.py`, `tests/integration/test_dashboard.py`

- [ ] 31. Add dashboard UI for health, findings, trends, rules, and exports
  What to do / Must NOT do: Build the actual local dashboard UI with finding list/detail, trend charts, rule config read/update, search/index status, progress, and export controls. Use restrained operational UI. Do not build a marketing landing page.
  Parallelization: Can parallel N | Wave 9 | Blocks browser QA
  References: `docs/prd.md:1371`, `docs/prd.md:1374`, `docs/prd.md:1380`
  Acceptance criteria: Red first: `tests/integration/test_dashboard.py::test_dashboard_ui_renders_findings_trends_rules_and_exports` fails. Green: `uv run pytest tests/integration/test_dashboard.py`.
  QA scenarios: Browser use: open `http://127.0.0.1:<port>/`, click finding detail, rules, export; PASS if screenshot shows findings list, selected finding detail, progress trend, rule config, and export control. Evidence `.omo/evidence/prd-remainder-task-31-dashboard-browser.png` plus action log `.omo/evidence/prd-remainder-task-31-dashboard-browser.txt`.
  Commit: Y | `feat(dashboard): add local health dashboard ui` | Files `src/codescent/dashboard/static/**`, `src/codescent/dashboard/templates/**`, `tests/integration/test_dashboard.py`

- [ ] 32. Add dashboard smoke, no-network, and cleanup proof
  What to do / Must NOT do: Add dashboard smoke script that starts the local server, drives browser checks, verifies no external requests, proves no source writes, exports JSON/Markdown, and cleans up server/process/temp state.
  Parallelization: Can parallel N | Wave 9 | Blocks final verification
  References: `docs/prd.md:757`, `docs/prd.md:762`, `docs/prd.md:777`, `docs/prd.md:1385`
  Acceptance criteria: Red first: `tests/security/test_runtime_safety.py::test_dashboard_smoke_is_local_only_and_source_read_only` fails. Green: `uv run pytest tests/security/test_runtime_safety.py tests/integration/test_dashboard.py`.
  QA scenarios: Browser use: `uv run python scripts/smoke_dashboard.py --repo tests/fixtures/python-basic --out .omo/evidence/prd-remainder-task-32-dashboard-smoke.json`; PASS if JSON has `ok: true`, `external_requests: 0`, `changed_source_paths: []`, screenshot path, and cleanup receipt. Evidence `.omo/evidence/prd-remainder-task-32-dashboard-smoke.json`.
  Commit: Y | `test(smoke): add dashboard local-only smoke` | Files `scripts/smoke_dashboard.py`, `tests/security/test_runtime_safety.py`

## Final Verification Wave

> Runs after all todos. ALL must pass before the plan is considered executed.

- [ ] F1. Plan compliance audit
  Command: `uv run python scripts/audit_plan_compliance.py --plan .omo/plans/codescent-prd-remainder.md --evidence .omo/evidence`
  Evidence: `.omo/evidence/prd-remainder-final-plan-compliance.json`
  Must prove every todo has evidence, every exposed MCP/CLI surface is documented, and all safety decisions are represented.

- [ ] F2. Code quality gates
  Command: `uv run ruff check . && uv run ruff format --check . && uv run basedpyright && uv run pytest`
  Evidence: `.omo/evidence/prd-remainder-final-code-quality.txt`
  Must include module-size audit; split any production module over 250 pure LOC unless documented as indivisible.

- [ ] F3. Full MCP and CLI smoke
  Commands:
  - `uv run python scripts/smoke_mcp.py --repo tests/fixtures/python-basic full_loop --out .omo/evidence/prd-remainder-final-python-mcp-loop.json`
  - `uv run python scripts/smoke_mcp.py --repo tests/fixtures/ts-react-next-basic full_loop --out .omo/evidence/prd-remainder-final-ts-mcp-loop.json`
  - `uv run codescent ci --repo tests/fixtures/python-basic --format json > .omo/evidence/prd-remainder-final-ci.json`
  Evidence: the three files above.

- [ ] F4. Runtime safety and stale-state proof
  Commands:
  - `uv run python scripts/prove_source_read_only.py --repo tests/fixtures/python-basic --out .omo/evidence/prd-remainder-final-source-read-only.json`
  - `uv run python scripts/smoke_lx_data_lake.py --repo /Users/robertguss/Projects/wts-lx/lx_data_lake --out .omo/evidence/prd-remainder-final-lx-smoke.json`
  Evidence: the two JSON files above, plus cleanup receipt `.omo/evidence/prd-remainder-final-cleanup.txt`.
  Must prove `changed_source_paths: []`, `network_attempts: 0`, and only `.codescent/` runtime state changed.

- [ ] F5. Dashboard browser QA
  Command: `uv run python scripts/smoke_dashboard.py --repo tests/fixtures/python-basic --out .omo/evidence/prd-remainder-final-dashboard.json`
  Evidence: `.omo/evidence/prd-remainder-final-dashboard.json`, screenshot path recorded inside JSON.
  Must prove local loopback UI renders findings/detail/trends/rules/export, makes no external requests, and cleans up the server.

## Commit Strategy

- User explicitly requested commit-and-continue execution: after each stage is
  complete and its tests/QA pass, commit the stage's intended code, docs, tests,
  scripts, fixtures, and evidence before starting the next stage.
- "Everything" means every deliverable produced for that completed stage,
  including `.omo/evidence/prd-remainder-task-*` artifacts required by the stage.
  It does not mean unrelated pre-existing dirty files, runtime `.codescent/`
  state, generated `__pycache__/`, or scratch files outside the stage scope.
- Before each stage commit, run `git status --short` and verify the staged set
  matches the stage deliverables. If unrelated dirty files exist, leave them
  unstaged and mention them in the stage handoff.
- Use atomic Conventional Commits as listed per todo.
- Prefer one commit per todo while executing inside a stage. If a stage contains
  tightly coupled todos that only pass together, use one stage commit and name
  every completed todo in the commit body.
- Final commit footer for any plan-execution commit series:
  `Plan: .omo/plans/codescent-prd-remainder.md`

## Success Criteria

- All remaining PRD search tools exist and return bounded, ranked, explained,
  paginated results with frecency and changed-file support.
- Graph tools expose references, callers, callees, related files, and impact
  with confidence labels and no false certainty.
- Reports and score explanations are deterministic, JSON/Markdown exportable,
  and useful to humans and agents.
- Backlog/progress/regression tracking works across rescans and sessions.
- `verify_change` recommends and records verification without executing target
  commands.
- Config/rule/pack settings are project-local and follow documented precedence.
- Python behavior is preserved after migrating to the pack registry.
- TypeScript/JavaScript/React/Next.js pack completes the same read-only
  improvement loop as Python.
- CI/PR mode runs locally, produces JSON/Markdown output, and obeys thresholds.
- Optional subjective review is disabled by default, opt-in, privacy-noticed,
  fake-provider tested, and stored separately from deterministic findings.
- Local dashboard runs on `127.0.0.1`, uses no external assets, writes no source,
  and exposes findings, details, trends, rules, status, progress, and exports.
- Final gates pass: full tests, ruff, format check, basedpyright, MCP smokes,
  real repo smoke, source-read-only proof, no-network proof, and dashboard
  browser smoke.
