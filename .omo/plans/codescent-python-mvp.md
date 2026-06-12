# CodeScent Python-First MCP MVP

## TL;DR

> Summary: Build CodeScent from a docs-only workspace into a Python-first,
> local, source-read-only FastMCP server that proves the full MVP loop: index ->
> search -> scan -> finding context -> refactor plan -> suggested tests ->
> rescan. The MVP includes deterministic evals and one agent-in-the-loop eval so
> usefulness is measured, not inferred. Deliverables:
>
> - `uv`/`pyproject.toml` Python package named `codescent`, CLI command
>   `codescent`, MIT license, README, and test harness.
> - Thin FastMCP stdio adapter over service/core/storage layers, not product
>   logic inside tool functions.
> - SQLite-backed `.codescent/` local state, Python repo indexing, bounded
>   search, Python symbol/context extraction, deterministic code-health
>   findings, finding lifecycle, refactor planning, suggested verification
>   commands, and rescan.
> - Deterministic offline evals plus an agent-in-the-loop milestone gate.
>   Effort: Large Risk: Medium - empty scaffold, Python-first override from
>   docs, SQLite/finding stability, bounded-context contracts, and eval design.

## Scope

### Must have

- Build from current repo state: only `.prettierrc`, `docs/prd.md`,
  `docs/architecture.md`, and `.omo/drafts/codescent-mcp-plan-interview.md`
  exist.
- Product identity: CodeScent, Python package `codescent`, CLI `codescent`, MIT
  license.
- Python-first MVP. Approved override: docs recommend
  TypeScript/JavaScript/React for MVP (`docs/prd.md:889`, `docs/prd.md:893`),
  but user chose Python-first in
  `.omo/drafts/codescent-mcp-plan-interview.md:92`. Replace TS/React
  parser/rule/fixture milestones with Python equivalents.
- Local-first and source-read-only runtime: CodeScent may write only its own
  `.codescent/` state (`config.toml`, `index.sqlite`, cache/logs, scan runs,
  finding state) and must never edit analyzed source files.
- Runtime no-network: core indexing, scanning, search, symbol extraction, and
  context building must not make network requests. Install-time dependency
  fetching is separate.
- FastMCP server is local stdio only in V1; no auth, HTTP, or SSE.
- CLI commands in MVP: `codescent init`, `serve`, `index`, `scan`, `status`,
  `doctor`.
- MCP tools in MVP: `get_repo_map`, `get_repo_status`, `search_files`,
  `search_content`, `find_symbol`, `get_file_context`, `get_symbol_context`,
  `scan_code_health`, `get_smell_report`, `get_finding_context`,
  `get_next_improvement`, `plan_refactor`, `suggest_tests`, `mark_finding`,
  `rescan`.
- Python fixture repo: `tests/fixtures/python-basic`.
- Real smoke repo: `/Users/robertguss/Projects/wts-lx/lx_data_lake`.
- Real smoke exclusions: `.env`, `.git/`, `.venv/`, `__pycache__/`,
  `.ruff_cache/`, `.pytest_cache/`, `data/`, `archive/`, `.codescent/`,
  generated/binary/cache artifacts.
- Target scale: small-to-medium Python repos up to roughly 25k included text
  files; first index target about 60s on a modern laptop as reported telemetry,
  not a hard failure.
- Evals: deterministic offline evals plus an agent-in-the-loop eval; measure
  retrieval quality, context efficiency, finding quality, workflow success,
  safety, and performance.
- Verification recommends project commands but does not execute target project
  test/lint/build commands in V1. `doctor` may execute internal diagnostics
  only.
- Error handling for invalid root, path outside root, stale index, missing
  index, unsupported file, parse failure, corrupt DB, missing git, non-git repo,
  and concurrent write.

### Must NOT have (guardrails, anti-slop, scope boundaries)

- Do not implement TypeScript/JavaScript/React/Next.js support in MVP; keep
  parser/rule seams for later packs.
- Do not implement CI/PR review mode, dashboard UI, hosted service, cloud
  indexing, subjective LLM review, HTTP/SSE MCP transport, auth, or source
  autofix.
- Do not add `codescent report`, `reset`, `find_references`, `find_callers`,
  `find_callees`, `get_impact`, `verify_change`, `get_backlog`, `get_progress`,
  or prompt resources unless needed as internal helpers. If internal helpers
  exist, do not expose them as MVP public tools.
- Do not read outside configured repo root. Normalize paths, reject traversal,
  and do not follow symlinks outside root.
- Do not index `.codescent/`, secrets, virtualenvs, caches,
  binary/generated/large data, or vendor/build outputs by default.
- Do not place business logic in FastMCP tool bodies; tools call services.
- Do not treat grep-only evidence, stale logs, or passing commands as completion
  unless the exact scenario and assertion ran.

## Verification strategy

> Zero human intervention - all verification is agent-executed.

- Test decision: TDD with `pytest`, FastMCP in-memory client tests, Typer CLI
  tests, SQLite integration tests, fixture-backed eval tests, and real smoke
  scripts.
- QA policy: every todo has agent-executed scenarios. Each todo captures RED
  then GREEN test output, plus at least one real surface artifact through CLI,
  MCP client, or eval transcript.
- Evidence: `.omo/evidence/task-<N>-<slug>.<ext>`
- Baseline checks after scaffold exists:
  - `uv run pytest`
  - `uv run ruff check .`
  - `uv run ruff format --check .`
  - `uv run basedpyright`
  - `uv run codescent --help`
  - `uv run python -m codescent.mcp.server --help` if a module CLI is provided
- MCP QA uses `fastmcp.Client(server)` in tests and a script under
  `scripts/smoke_mcp.py` for manual QA artifacts.
- CLI QA uses temp fixture repos with `uv run codescent ...`.
- Real smoke QA uses `/Users/robertguss/Projects/wts-lx/lx_data_lake` read-only
  and verifies only `.codescent/` changed.
- Evals QA uses deterministic expected-output files under `evals/fixtures/` and
  transcript artifacts under `.omo/evidence/`.

## Execution strategy

### Parallel execution waves

> Target 5-8 todos per wave. < 3 per wave (except the final) = under-splitting.
> Wave 1 (no deps): 1, 2, 3, 4, 5 Wave 2 (after 1-5): 6, 7, 8, 9, 10 Wave 3
> (after 6-10): 11, 12, 13, 14, 15 Wave 4 (after 11-15): 16, 17, 18, 19, 20
> Final wave (after all todos): F1, F2, F3, F4 Critical path: 1 -> 2 -> 3 -> 6
> -> 8 -> 11 -> 13 -> 15 -> 17 -> 18 -> 19 -> 20 -> final verification.

### Dependency matrix

| Todo | Depends on | Blocks  | Can parallelize with |
| ---- | ---------- | ------- | -------------------- |
| 1    | none       | 2-20    | 2, 3, 4, 5           |
| 2    | none       | 3, 6-20 | 1, 4, 5              |
| 3    | 1, 2       | 6-20    | 4, 5                 |
| 4    | none       | 6-20    | 1, 2, 5              |
| 5    | none       | 6-20    | 1, 2, 4              |
| 6    | 1-5        | 7-20    | 7, 8, 9, 10          |
| 7    | 1-6        | 8-20    | 8, 9, 10             |
| 8    | 1-7        | 9-20    | 9, 10                |
| 9    | 1-8        | 10-20   | 10                   |
| 10   | 1-8        | 11-20   | 9                    |
| 11   | 1-10       | 12-20   | 12, 13, 14, 15       |
| 12   | 1-10       | 13-20   | 11, 14, 15           |
| 13   | 1-12       | 14-20   | 14, 15               |
| 14   | 1-13       | 15-20   | 15                   |
| 15   | 1-14       | 16-20   | none                 |
| 16   | 1-15       | 17-20   | 17, 18               |
| 17   | 1-16       | 18-20   | 16                   |
| 18   | 1-17       | 19-20   | none                 |
| 19   | 1-18       | 20      | none                 |
| 20   | 1-19       | final   | none                 |

## Todos

> Implementation + Test = ONE todo. Never separate.

- [x] 1. Scaffold package, metadata, commands, and baseline docs What to do /
     Must NOT do Create `pyproject.toml`, `uv.lock`, `README.md`, `LICENSE`,
     `src/codescent/__init__.py`, `src/codescent/__main__.py`,
     `src/codescent/cli/main.py`, `src/codescent/mcp/server.py`, `tests/`,
     `scripts/`, and `evals/`. Configure package name `codescent`, CLI script
     `codescent`, MIT license, Python `>=3.12`, `fastmcp`, `typer`, `pydantic`,
     `pydantic-settings`, `rapidfuzz`, `pytest`, `ruff`, `basedpyright`. Use
     stdlib `sqlite3`. Do not scaffold TS/React packages. Parallelization: Can
     parallel Y | Wave 1 | Blocks all implementation References (executor has NO
     interview context - be exhaustive): `docs/architecture.md:191`,
     `docs/architecture.md:215`, `docs/architecture.md:222`,
     `docs/architecture.md:228`, `docs/architecture.md:974`,
     `.omo/drafts/codescent-mcp-plan-interview.md:75`,
     `.omo/drafts/codescent-mcp-plan-interview.md:84`,
     `.omo/drafts/codescent-mcp-plan-interview.md:92` Acceptance criteria
     (agent-executable): First write failing tests
     `tests/test_package_metadata.py::test_codescent_cli_registered` and
     `tests/test_package_metadata.py::test_python_version_and_license_metadata`;
     RED shows missing package metadata. GREEN: `uv sync`,
     `uv run pytest tests/test_package_metadata.py`, `uv run codescent --help`,
     `uv run ruff check .`, `uv run ruff format --check .`, and
     `uv run basedpyright` exit 0. QA scenarios (name the exact tool +
     invocation): tmux channel:
     `tmux new-session -d -s ulw-qa-1 'cd /Users/robertguss/Projects/startups/code-scent-mcp && uv run codescent --help'`;
     PASS if transcript contains `Usage:` and `codescent`. Evidence
     `.omo/evidence/task-1-scaffold.txt` Commit: Y |
     `chore(scaffold): initialize codescent python package` | Files
     `pyproject.toml`, `uv.lock`, `README.md`, `LICENSE`, `src/codescent/**`,
     `tests/test_package_metadata.py`

- [x] 2. Define core models, typed errors, config precedence, and output bounds
     What to do / Must NOT do Add Pydantic/domain models for repo config,
     indexed file, symbol, finding, scan run, repo status, search result,
     context pack, refactor plan, suggested verification, eval result, and typed
     `CodeScentError` variants. Define config precedence: built-in defaults <
     `.codescent/config.toml` < CLI flags < MCP tool args. Define default result
     limit 20, max result limit 100, default context source line cap 80, max
     source line cap 200, default token budget 3000. Do not return whole files
     by default. Parallelization: Can parallel Y | Wave 1 | Blocks
     storage/services/tools References: `docs/prd.md:255`, `docs/prd.md:271`,
     `docs/prd.md:719`, `docs/architecture.md:557`, `docs/architecture.md:747`,
     `docs/architecture.md:1005`,
     `.omo/drafts/codescent-mcp-plan-interview.md:132` Acceptance criteria:
     Write failing tests
     `tests/unit/test_models.py::test_context_defaults_are_bounded` and
     `tests/unit/test_errors.py::test_error_payload_is_structured`. GREEN:
     `uv run pytest tests/unit/test_models.py tests/unit/test_errors.py`. QA
     scenarios: tmux channel:
     `tmux new-session -d -s ulw-qa-2 'cd /Users/robertguss/Projects/startups/code-scent-mcp && uv run python - <<\"PY\"\nfrom codescent.core.models import ContextOptions\nprint(ContextOptions().model_dump())\nPY'`;
     PASS if output shows default token/source bounds. Evidence
     `.omo/evidence/task-2-models.txt` Commit: Y |
     `feat(core): add bounded domain models and errors` | Files
     `src/codescent/core/**`, `tests/unit/test_models.py`,
     `tests/unit/test_errors.py`

- [x] 3. Build Python fixture repo and expected eval manifest What to do / Must
     NOT do Create `tests/fixtures/python-basic` with a small Python package,
     Typer-like CLI file, tests, one intentionally large function, one large
     file, TODO cluster, duplicate literals, missing-test candidate, and
     source/test relationships. Add `evals/fixtures/python-basic.expected.json`
     with expected files, symbols, findings, search queries, context limits, and
     workflow task. Do not rely on generated fixture code without checked-in
     expectations. Parallelization: Can parallel Y | Wave 1 | Blocks
     indexing/search/symbol/health/evals References: `docs/prd.md:880`,
     `docs/prd.md:936`, `docs/prd.md:964`,
     `.omo/drafts/codescent-mcp-plan-interview.md:110`,
     `.omo/drafts/codescent-mcp-plan-interview.md:132` Acceptance criteria:
     Write failing tests
     `tests/fixtures/test_python_basic_fixture.py::test_fixture_contains_expected_smells`.
     GREEN confirms fixture manifest paths exist, fixture has at least 5 `.py`
     source files and at least 3 tests, and expected finding IDs are listed. QA
     scenarios: tmux channel:
     `tmux new-session -d -s ulw-qa-3 'cd /Users/robertguss/Projects/startups/code-scent-mcp && find tests/fixtures/python-basic -type f | sort && cat evals/fixtures/python-basic.expected.json'`;
     PASS if transcript lists fixture package, tests, and expected eval
     manifest. Evidence `.omo/evidence/task-3-fixture.txt` Commit: Y |
     `test(fixtures): add python mvp fixture repo` | Files
     `tests/fixtures/python-basic/**`,
     `evals/fixtures/python-basic.expected.json`,
     `tests/fixtures/test_python_basic_fixture.py`

- [x] 4. Implement repository boundary, exclusions, and file inventory What to
     do / Must NOT do Add root resolution, path normalization, traversal
     rejection, symlink-outside-root rejection, default excludes, binary
     detection, generated/cache/vendor/data excludes, `.codescent` exclusion,
     language detection, line counts, size, hashes, and non-git degradation. Do
     not read `.env`, `data/`, virtualenvs, caches, `.git/`, `.codescent/`, or
     outside-root paths. Parallelization: Can parallel Y | Wave 1 | Blocks
     index/search/smoke References: `docs/prd.md:741`, `docs/prd.md:768`,
     `docs/prd.md:773`, `docs/architecture.md:498`, `docs/architecture.md:780`,
     `.omo/drafts/codescent-mcp-plan-interview.md:118`,
     `.omo/drafts/codescent-mcp-plan-interview.md:153` Acceptance criteria:
     Write failing tests
     `tests/unit/test_inventory.py::test_default_excludes_skip_sensitive_and_generated_paths`,
     `tests/unit/test_inventory.py::test_rejects_path_traversal`, and
     `tests/unit/test_inventory.py::test_symlink_outside_root_is_not_followed`.
     GREEN: `uv run pytest tests/unit/test_inventory.py`. QA scenarios: tmux
     channel:
     `tmux new-session -d -s ulw-qa-4 'cd /Users/robertguss/Projects/startups/code-scent-mcp && uv run python scripts/inspect_inventory.py tests/fixtures/python-basic --json'`;
     PASS if JSON includes Python files and excludes `.codescent`. Evidence
     `.omo/evidence/task-4-inventory.json` Commit: Y |
     `feat(index): add safe repository inventory` | Files
     `src/codescent/engine/inventory.py`, `src/codescent/core/paths.py`,
     `scripts/inspect_inventory.py`, `tests/unit/test_inventory.py`

- [x] 5. Implement SQLite storage, migrations, locking, and recovery What to do
     / Must NOT do Add `.codescent/` layout creation, `index.sqlite`,
     `config.toml`, schema version table, migrations, tables for files, symbols,
     imports, chunks, findings, scan_runs, finding_events,
     suggested_verifications, eval_runs, and telemetry. Use transactions,
     `busy_timeout`, one-writer policy, and corruption detection with rebuild
     guidance. Do not write anywhere except `.codescent/`. Parallelization: Can
     parallel Y | Wave 1 | Blocks services/rescan References: `docs/prd.md:682`,
     `docs/prd.md:976`, `docs/architecture.md:595`, `docs/architecture.md:607`,
     `docs/architecture.md:637`,
     `.omo/drafts/codescent-mcp-plan-interview.md:101` Acceptance criteria:
     Write failing tests
     `tests/integration/test_storage.py::test_init_creates_codescent_state_only`,
     `tests/integration/test_storage.py::test_schema_migration_idempotent`, and
     `tests/integration/test_storage.py::test_concurrent_writer_returns_structured_error`.
     GREEN: `uv run pytest tests/integration/test_storage.py`. QA scenarios:
     tmux channel:
     `tmux new-session -d -s ulw-qa-5 'cd /Users/robertguss/Projects/startups/code-scent-mcp && tmp=$(mktemp -d) && uv run codescent init --repo \"$tmp\" && find \"$tmp\" -maxdepth 3 -type f | sort'`;
     PASS if only `.codescent/config.toml` and `.codescent/index.sqlite` are
     created. Evidence `.omo/evidence/task-5-storage.txt` Commit: Y |
     `feat(storage): add sqlite project state` | Files
     `src/codescent/storage/**`, `tests/integration/test_storage.py`

- [x] 6. Implement RepoIndexService and status lifecycle What to do / Must NOT
     do Add `RepoIndexService` for full and incremental index, hash freshness,
     stale detection, file inventory persistence, scan status placeholders, git
     status if available, degraded non-git status if not. Add
     `RepoStatusService`. Do not parse symbols or run health rules here.
     Parallelization: Can parallel Y | Wave 2 | Blocks MCP/CLI search/status
     References: `docs/prd.md:496`, `docs/prd.md:513`, `docs/prd.md:1017`,
     `docs/architecture.md:41`, `docs/architecture.md:90`,
     `docs/architecture.md:1011` Acceptance criteria: Write failing tests
     `tests/integration/test_repo_index.py::test_index_persists_files_and_freshness`,
     `tests/integration/test_repo_index.py::test_reindex_marks_changed_files`,
     and
     `tests/integration/test_repo_index.py::test_non_git_repo_degrades_cleanly`.
     GREEN: `uv run pytest tests/integration/test_repo_index.py`. QA scenarios:
     tmux channel:
     `tmux new-session -d -s ulw-qa-6 'cd /Users/robertguss/Projects/startups/code-scent-mcp && uv run codescent init --repo tests/fixtures/python-basic && uv run codescent index --repo tests/fixtures/python-basic && uv run codescent status --repo tests/fixtures/python-basic --json'`;
     PASS if status reports fresh index and file counts. Evidence
     `.omo/evidence/task-6-index-status.json` Commit: Y |
     `feat(index): persist repo index status` | Files
     `src/codescent/services/repo_index.py`, `src/codescent/services/status.py`,
     `tests/integration/test_repo_index.py`

- [x] 7. Implement CLI commands over services What to do / Must NOT do Implement
     `codescent init`, `serve`, `index`, `scan`, `status`, `doctor`. `serve`
     starts FastMCP stdio. `doctor` checks internal
     availability/config/DB/exclusions and never runs target repo tests. Leave
     `report` and `reset` out of MVP. Parallelization: Can parallel Y | Wave 2 |
     Blocks manual QA and smoke References: `docs/prd.md:923`,
     `docs/architecture.md:153`, `docs/architecture.md:222`,
     `.omo/drafts/codescent-mcp-plan-interview.md:101` Acceptance criteria:
     Write failing tests
     `tests/contract/test_cli.py::test_cli_help_lists_mvp_commands`,
     `tests/contract/test_cli.py::test_init_index_status_doctor_round_trip`, and
     `tests/contract/test_cli.py::test_report_and_reset_not_exposed`. GREEN:
     `uv run pytest tests/contract/test_cli.py`. QA scenarios: tmux channel:
     `tmux new-session -d -s ulw-qa-7 'cd /Users/robertguss/Projects/startups/code-scent-mcp && uv run codescent --help && uv run codescent doctor --repo tests/fixtures/python-basic --json'`;
     PASS if MVP commands appear and doctor returns OK/structured warnings.
     Evidence `.omo/evidence/task-7-cli.txt` Commit: Y |
     `feat(cli): expose mvp service commands` | Files `src/codescent/cli/**`,
     `tests/contract/test_cli.py`

- [x] 8. Implement thin FastMCP adapter and repo/status tools What to do / Must
     NOT do Build FastMCP server with `get_repo_map` and `get_repo_status` as
     thin wrappers. Use current FastMCP pattern: `FastMCP(name=...)`,
     `@mcp.tool`, `mcp.run()` stdio, and in-memory `Client(server)` tests. Tool
     descriptions must instruct agents to use CodeScent before broad grep/large
     reads and state read-only behavior. Parallelization: Can parallel Y | Wave
     2 | Blocks all MCP tools References: `docs/prd.md:491`, `docs/prd.md:787`,
     `docs/architecture.md:77`, `docs/architecture.md:131`,
     `.omo/drafts/codescent-mcp-plan-interview.md:29` Acceptance criteria: Write
     failing tests
     `tests/contract/test_mcp_repo_tools.py::test_mcp_lists_repo_tools` and
     `tests/contract/test_mcp_repo_tools.py::test_get_repo_map_and_status_are_bounded`.
     GREEN: `uv run pytest tests/contract/test_mcp_repo_tools.py`. QA scenarios:
     tmux channel:
     `tmux new-session -d -s ulw-qa-8 'cd /Users/robertguss/Projects/startups/code-scent-mcp && uv run python scripts/smoke_mcp.py --repo tests/fixtures/python-basic get_repo_map get_repo_status'`;
     PASS if transcript includes both tool calls and bounded JSON. Evidence
     `.omo/evidence/task-8-mcp-repo.json` Commit: Y |
     `feat(mcp): add repo map and status tools` | Files `src/codescent/mcp/**`,
     `tests/contract/test_mcp_repo_tools.py`, `scripts/smoke_mcp.py`

- [x] 9. Implement bounded file/content search with ranking reasons What to do /
     Must NOT do Add `SearchService`, `search_files`, `search_content`, fuzzy
     fallback, smart-case behavior, result limits, snippets capped by source
     line budget, ranking reason fields, changed-file filter internally for
     ranking, and frecency table placeholder. Do not expose
     `multi_search_content`, `search_changed_files`, `search_todos`, or
     `search_tests` as public MVP tools unless folded into approved tools.
     Parallelization: Can parallel Y | Wave 2 | Blocks symbol/context/evals
     References: `docs/prd.md:525`, `docs/prd.md:953`,
     `docs/architecture.md:625`, `docs/architecture.md:747`,
     `.omo/drafts/codescent-mcp-plan-interview.md:132` Acceptance criteria:
     Write failing tests
     `tests/integration/test_search.py::test_search_files_exact_and_fuzzy`,
     `tests/integration/test_search.py::test_search_content_returns_bounded_snippets`,
     and
     `tests/contract/test_mcp_search_tools.py::test_search_tools_include_ranking_reasons`.
     GREEN:
     `uv run pytest tests/integration/test_search.py tests/contract/test_mcp_search_tools.py`.
     QA scenarios: tmux channel:
     `tmux new-session -d -s ulw-qa-9 'cd /Users/robertguss/Projects/startups/code-scent-mcp && uv run python scripts/smoke_mcp.py --repo tests/fixtures/python-basic search_files:payrol search_content:TODO'`;
     PASS if results are <= 20, include ranking reasons, and snippets are
     bounded. Evidence `.omo/evidence/task-9-search.json` Commit: Y |
     `feat(search): add bounded ranked search` | Files
     `src/codescent/services/search.py`, `src/codescent/engine/search/**`,
     `tests/integration/test_search.py`,
     `tests/contract/test_mcp_search_tools.py`

- [x] 10. Add Python parser adapter and symbol/import/test extraction What to do
      / Must NOT do Implement Python parser adapter using stdlib `ast` plus
      `tokenize`/source line helpers. Extract modules, classes, functions, async
      functions, methods, imports, rough references where confident, test files,
      and line ranges. Return confidence; do not pretend caller/callee certainty
      where AST-only extraction is weak. Parallelization: Can parallel Y | Wave
      2 | Blocks symbol context, findings, evals References: `docs/prd.md:551`,
      `docs/prd.md:964`, `docs/architecture.md:514`, `docs/architecture.md:531`,
      `.omo/drafts/codescent-mcp-plan-interview.md:92`,
      `.omo/drafts/codescent-mcp-plan-interview.md:162` Acceptance criteria:
      Write failing tests
      `tests/unit/test_python_parser.py::test_extracts_python_symbols_imports_and_tests`
      and
      `tests/unit/test_python_parser.py::test_uncertain_relationships_have_low_confidence`.
      GREEN: `uv run pytest tests/unit/test_python_parser.py`. QA scenarios:
      tmux channel:
      `tmux new-session -d -s ulw-qa-10 'cd /Users/robertguss/Projects/startups/code-scent-mcp && uv run python scripts/inspect_symbols.py tests/fixtures/python-basic --json'`;
      PASS if JSON includes expected classes/functions/imports with line ranges
      and confidence. Evidence `.omo/evidence/task-10-python-symbols.json`
      Commit: Y | `feat(symbols): add python ast parser adapter` | Files
      `src/codescent/engine/parsers/python.py`,
      `src/codescent/services/symbols.py`, `tests/unit/test_python_parser.py`

- [x] 11. Implement file and symbol context packs What to do / Must NOT do Add
      `get_file_context`, `find_symbol`, `get_symbol_context`, context pack
      builder, related files, likely tests, imports summary, bounded source
      ranges, risk notes, and next recommended tool calls. Default to summaries
      over raw source. Keep `find_references`, `find_callers`, `find_callees`,
      and `get_related_files` internal only for MVP. Parallelization: Can
      parallel Y | Wave 3 | Blocks finding context/refactor planning/evals
      References: `docs/prd.md:557`, `docs/prd.md:562`, `docs/prd.md:964`,
      `docs/architecture.md:557`, `docs/architecture.md:1104` Acceptance
      criteria: Write failing tests
      `tests/integration/test_context.py::test_file_context_is_bounded_summary`,
      `tests/integration/test_context.py::test_symbol_context_includes_likely_tests`,
      and
      `tests/contract/test_mcp_context_tools.py::test_context_tools_do_not_dump_whole_files`.
      GREEN:
      `uv run pytest tests/integration/test_context.py tests/contract/test_mcp_context_tools.py`.
      QA scenarios: tmux channel:
      `tmux new-session -d -s ulw-qa-11 'cd /Users/robertguss/Projects/startups/code-scent-mcp && uv run python scripts/smoke_mcp.py --repo tests/fixtures/python-basic find_symbol:calculate get_file_context:src/python_basic/service.py get_symbol_context:python_basic.service.calculate'`;
      PASS if output includes summaries, relevant tests, and source ranges under
      cap. Evidence `.omo/evidence/task-11-context.json` Commit: Y |
      `feat(context): add bounded python context packs` | Files
      `src/codescent/engine/context/**`, `src/codescent/services/symbols.py`,
      `tests/integration/test_context.py`

- [x] 12. Implement Python deterministic code-health rules What to do / Must NOT
      do Add modular rule engine and Python MVP rules: large file, large
      function, large class, too many imports, deep nesting, TODO/FIXME/HACK
      cluster, duplicate literal strings, missing nearby test candidate, changed
      source file with no related test, mixed responsibilities heuristic,
      suspicious generated/slop candidate. Each finding includes rule ID,
      severity, confidence, evidence, suggested action, and stable key. Do not
      add TS/React-specific rules. Parallelization: Can parallel Y | Wave 3 |
      Blocks findings/backlog/refactor/evals References: `docs/prd.md:587`,
      `docs/prd.md:936`, `docs/architecture.md:536`, `docs/architecture.md:706`,
      `.omo/drafts/codescent-mcp-plan-interview.md:92` Acceptance criteria:
      Write failing tests
      `tests/unit/test_rules_python.py::test_fixture_rules_find_expected_findings`,
      `tests/unit/test_rules_python.py::test_finding_stable_key_survives_line_shift`,
      and
      `tests/integration/test_scan_code_health.py::test_scan_persists_run_and_findings`.
      GREEN:
      `uv run pytest tests/unit/test_rules_python.py tests/integration/test_scan_code_health.py`.
      QA scenarios: tmux channel:
      `tmux new-session -d -s ulw-qa-12 'cd /Users/robertguss/Projects/startups/code-scent-mcp && uv run codescent scan --repo tests/fixtures/python-basic --json'`;
      PASS if output includes expected Python finding IDs and evidence. Evidence
      `.omo/evidence/task-12-health-scan.json` Commit: Y |
      `feat(health): add python smell scanner` | Files
      `src/codescent/engine/rules/**`, `src/codescent/services/code_health.py`,
      `tests/unit/test_rules_python.py`

- [x] 13. Implement finding service, reports subset, and lifecycle tools What to
      do / Must NOT do Add finding persistence, statuses (`open`, `in_progress`,
      `resolved`, `deferred`, `wontfix`, `ignored`, `regressed`,
      `needs_review`), event history, rescan comparison, `get_smell_report`,
      `get_next_improvement`, `mark_finding`, and `rescan`. Reports are
      structured MCP/CLI JSON only in MVP; no markdown/HTML report command.
      Parallelization: Can parallel Y | Wave 3 | Blocks finding
      context/refactor/evals References: `docs/prd.md:475`, `docs/prd.md:593`,
      `docs/prd.md:605`, `docs/prd.md:630`, `docs/prd.md:976`,
      `docs/architecture.md:706` Acceptance criteria: Write failing tests
      `tests/integration/test_findings.py::test_mark_finding_persists_status`,
      `tests/integration/test_findings.py::test_rescan_preserves_resolved_or_marks_regressed`,
      and
      `tests/contract/test_mcp_finding_tools.py::test_finding_tools_are_source_read_only`.
      GREEN:
      `uv run pytest tests/integration/test_findings.py tests/contract/test_mcp_finding_tools.py`.
      QA scenarios: tmux channel:
      `tmux new-session -d -s ulw-qa-13 'cd /Users/robertguss/Projects/startups/code-scent-mcp && uv run python scripts/smoke_mcp.py --repo tests/fixtures/python-basic scan_code_health get_smell_report get_next_improvement mark_finding rescan'`;
      PASS if finding status changes in `.codescent` and source tree hash is
      unchanged. Evidence `.omo/evidence/task-13-findings.json` Commit: Y |
      `feat(findings): add lifecycle and rescan` | Files
      `src/codescent/services/findings.py`,
      `src/codescent/storage/repositories/findings.py`,
      `tests/integration/test_findings.py`

- [x] 14. Implement finding context and safe refactor planning What to do / Must
      NOT do Add `get_finding_context`, `plan_refactor`, and `suggest_tests`.
      Plan output must include goal, non-goals, affected files, relevant
      symbols, risk, steps, fallback, expected behavior preservation, and
      verification recommendations. `suggest_tests` recommends commands and
      likely tests only; it does not execute them. Parallelization: Can parallel
      Y | Wave 3 | Blocks workflow/evals References: `docs/prd.md:601`,
      `docs/prd.md:615`, `docs/prd.md:619`, `docs/prd.md:1170`,
      `docs/architecture.md:920`,
      `.omo/drafts/codescent-mcp-plan-interview.md:101` Acceptance criteria:
      Write failing tests
      `tests/integration/test_refactor_planning.py::test_finding_context_is_minimal_and_actionable`,
      `tests/integration/test_refactor_planning.py::test_plan_refactor_has_required_fields`,
      and
      `tests/integration/test_refactor_planning.py::test_suggest_tests_recommends_without_execution`.
      GREEN: `uv run pytest tests/integration/test_refactor_planning.py`. QA
      scenarios: tmux channel:
      `tmux new-session -d -s ulw-qa-14 'cd /Users/robertguss/Projects/startups/code-scent-mcp && uv run python scripts/smoke_mcp.py --repo tests/fixtures/python-basic get_finding_context plan_refactor suggest_tests'`;
      PASS if output contains one safe plan with non-goals and no command
      execution record. Evidence `.omo/evidence/task-14-refactor-plan.json`
      Commit: Y | `feat(planning): add finding context and refactor plans` |
      Files `src/codescent/services/refactor_planning.py`,
      `src/codescent/services/verification.py`,
      `tests/integration/test_refactor_planning.py`

- [x] 15. Complete MCP tool surface and schemas What to do / Must NOT do
      Register all 15 MVP tools with schemas, descriptions, bounds, and service
      delegation. Add schema snapshot/contract tests to prevent accidental
      output bloat or source-editing capabilities. Tool descriptions should say
      when to use the tool before broad shell search or large file reads.
      Parallelization: Can parallel Y | Wave 3 | Blocks final MCP smoke/evals
      References: `docs/prd.md:903`, `docs/prd.md:787`,
      `docs/architecture.md:131`, `docs/architecture.md:747` Acceptance
      criteria: Write failing tests
      `tests/contract/test_mcp_tool_surface.py::test_exact_mvp_tool_names`,
      `tests/contract/test_mcp_tool_surface.py::test_no_post_mvp_tools_exposed`,
      and
      `tests/contract/test_mcp_tool_surface.py::test_tool_outputs_match_bounded_schema_snapshots`.
      GREEN: `uv run pytest tests/contract/test_mcp_tool_surface.py`. QA
      scenarios: tmux channel:
      `tmux new-session -d -s ulw-qa-15 'cd /Users/robertguss/Projects/startups/code-scent-mcp && uv run python scripts/smoke_mcp.py --repo tests/fixtures/python-basic list_tools'`;
      PASS if exactly the 15 MVP tools are listed. Evidence
      `.omo/evidence/task-15-mcp-surface.json` Commit: Y |
      `feat(mcp): expose complete mvp tool surface` | Files
      `src/codescent/mcp/tools/**`, `tests/contract/test_mcp_tool_surface.py`

- [x] 16. Add deterministic offline eval harness What to do / Must NOT do Add
      `evals/run_deterministic.py`, eval schemas, expected outputs, and scoring
      for retrieval top-k, context line/token bounds, finding precision on
      fixture, stable finding IDs, workflow success, source-read-only safety,
      and timing telemetry. Deterministic evals run against
      `tests/fixtures/python-basic` and synthetic scale fixture/generator. Do
      not require network or LLM. Parallelization: Can parallel Y | Wave 4 |
      Blocks final eval gate References:
      `.omo/drafts/codescent-mcp-plan-interview.md:125`,
      `.omo/drafts/codescent-mcp-plan-interview.md:132`, `docs/prd.md:880`,
      `docs/prd.md:953` Acceptance criteria: Write failing tests
      `tests/evals/test_deterministic_eval.py::test_eval_scores_fixture_workflow`
      and
      `tests/evals/test_deterministic_eval.py::test_eval_fails_on_missing_expected_finding`.
      GREEN: `uv run pytest tests/evals/test_deterministic_eval.py` and
      `uv run python evals/run_deterministic.py --repo tests/fixtures/python-basic --expected evals/fixtures/python-basic.expected.json --out .omo/evidence/task-16-deterministic-eval.json`
      exits 0. QA scenarios: tmux channel:
      `tmux new-session -d -s ulw-qa-16 'cd /Users/robertguss/Projects/startups/code-scent-mcp && uv run python evals/run_deterministic.py --repo tests/fixtures/python-basic --expected evals/fixtures/python-basic.expected.json --out .omo/evidence/task-16-deterministic-eval.json'`;
      PASS if score summary meets thresholds. Evidence
      `.omo/evidence/task-16-deterministic-eval.json` Commit: Y |
      `test(evals): add deterministic mvp evaluation` | Files `evals/**`,
      `tests/evals/test_deterministic_eval.py`

- [x] 17. Add agent-in-the-loop eval script and transcript capture What to do /
      Must NOT do Add `evals/agent_task.md` and `scripts/run_agent_eval.md`
      describing the manual/agent gate: agent must use CodeScent tools to
      identify one fixture finding, retrieve finding context, produce a safe
      plan, call `suggest_tests`, and rescan/mark finding without broad shell
      grep as primary discovery. Pass/fail is transcript-based and
      artifact-backed. Do not require an external hosted LLM. Parallelization:
      Can parallel Y | Wave 4 | Blocks final eval gate References:
      `.omo/drafts/codescent-mcp-plan-interview.md:132`,
      `.omo/drafts/codescent-mcp-plan-interview.md:177`, `docs/prd.md:82`,
      `docs/prd.md:95` Acceptance criteria: Write failing tests
      `tests/evals/test_agent_eval_spec.py::test_agent_eval_spec_has_required_steps_and_pass_fail`.
      GREEN: `uv run pytest tests/evals/test_agent_eval_spec.py`. QA scenarios:
      tmux channel:
      `tmux new-session -d -s ulw-qa-17 'cd /Users/robertguss/Projects/startups/code-scent-mcp && sed -n \"1,220p\" evals/agent_task.md && sed -n \"1,220p\" scripts/run_agent_eval.md'`;
      PASS if transcript names exact required CodeScent tool calls and pass/fail
      criteria. Evidence `.omo/evidence/task-17-agent-eval-spec.txt` Commit: Y |
      `test(evals): add agent-in-the-loop eval gate` | Files
      `evals/agent_task.md`, `scripts/run_agent_eval.md`,
      `tests/evals/test_agent_eval_spec.py`

- [x] 18. Add real repo smoke for `lx_data_lake` What to do / Must NOT do Add
      `scripts/smoke_lx_data_lake.py` or documented script target that indexes
      `/Users/robertguss/Projects/wts-lx/lx_data_lake` read-only with strict
      exclusions. Validate repo map, status, search, symbol/context, scan, smell
      report, finding context, refactor plan, suggested tests, and rescan.
      Confirm `.env`, `data/`, `.venv/`, `.git/`, caches, `archive/`, and
      `.codescent/` are excluded. Confirm unrelated untracked files are
      untouched. Parallelization: Can parallel N | Wave 4 | Blocks final QA
      References: `.omo/drafts/codescent-mcp-plan-interview.md:183`,
      `/Users/robertguss/Projects/wts-lx/lx_data_lake/AGENTS.md`,
      `/Users/robertguss/Projects/wts-lx/lx_data_lake/LEARNINGS.md`,
      `/Users/robertguss/Projects/wts-lx/lx_data_lake/pyproject.toml` Acceptance
      criteria: Write failing test
      `tests/smoke/test_lx_data_lake_smoke_config.py::test_lx_smoke_uses_required_exclusions`
      and script dry-run support. GREEN:
      `uv run pytest tests/smoke/test_lx_data_lake_smoke_config.py`. Manual real
      smoke command exits 0 when repo path exists. QA scenarios: tmux channel:
      `tmux new-session -d -s ulw-qa-18 'cd /Users/robertguss/Projects/startups/code-scent-mcp && uv run python scripts/smoke_lx_data_lake.py --repo /Users/robertguss/Projects/wts-lx/lx_data_lake --out .omo/evidence/task-18-lx-smoke.json'`;
      PASS if JSON confirms excluded paths, tool calls, findings, telemetry, and
      source hashes unchanged except `.codescent/`. Evidence
      `.omo/evidence/task-18-lx-smoke.json` Commit: Y |
      `test(smoke): add lx data lake real repo smoke` | Files
      `scripts/smoke_lx_data_lake.py`,
      `tests/smoke/test_lx_data_lake_smoke_config.py`

- [x] 19. Add runtime safety, no-network, and source-read-only proof What to do
      / Must NOT do Add tests/scripts that snapshot target repo source hashes
      before/after MCP/CLI tools, assert only `.codescent/` changes, monkeypatch
      network calls to fail if core indexing/scanning/searching attempts
      network, and validate internal `doctor` diagnostics are allowed while
      target project test/lint/build execution is not. Parallelization: Can
      parallel N | Wave 4 | Blocks final security/safety audit References:
      `docs/prd.md:755`, `docs/prd.md:762`, `docs/prd.md:773`,
      `docs/architecture.md:780`,
      `.omo/drafts/codescent-mcp-plan-interview.md:101` Acceptance criteria:
      Write failing tests
      `tests/security/test_runtime_safety.py::test_mcp_tools_do_not_modify_source`,
      `tests/security/test_runtime_safety.py::test_core_scan_makes_no_network_requests`,
      and
      `tests/security/test_runtime_safety.py::test_verification_commands_are_recommended_not_executed`.
      GREEN: `uv run pytest tests/security/test_runtime_safety.py`. QA
      scenarios: tmux channel:
      `tmux new-session -d -s ulw-qa-19 'cd /Users/robertguss/Projects/startups/code-scent-mcp && uv run python scripts/prove_source_read_only.py --repo tests/fixtures/python-basic --out .omo/evidence/task-19-read-only.json'`;
      PASS if only `.codescent/` changed and no network attempts recorded.
      Evidence `.omo/evidence/task-19-read-only.json` Commit: Y |
      `test(safety): prove source-read-only runtime` | Files
      `tests/security/test_runtime_safety.py`,
      `scripts/prove_source_read_only.py`

- [x] 20. Write operator docs, install snippets, and evidence runbook What to do
      / Must NOT do Update README with install, `uv sync`, CLI usage, MCP stdio
      connection snippet, first-run workflow, Python-first scope, runtime safety
      model, eval commands, real smoke target instructions, and what is out of
      scope. Add `docs/evals.md` and `docs/mcp-tools.md`. Do not claim support
      for TS/React or source autofix. Parallelization: Can parallel N | Wave 4 |
      Blocks final declaration References: `docs/prd.md:638`, `docs/prd.md:787`,
      `docs/architecture.md:477`,
      `.omo/drafts/codescent-mcp-plan-interview.md:75` Acceptance criteria:
      Write failing docs tests or assertions
      `tests/docs/test_docs.py::test_readme_names_python_first_mvp_and_safety`
      and `tests/docs/test_docs.py::test_tool_docs_list_exact_mvp_tools`. GREEN:
      `uv run pytest tests/docs/test_docs.py`. QA scenarios: tmux channel:
      `tmux new-session -d -s ulw-qa-20 'cd /Users/robertguss/Projects/startups/code-scent-mcp && sed -n \"1,260p\" README.md && sed -n \"1,260p\" docs/evals.md && sed -n \"1,260p\" docs/mcp-tools.md'`;
      PASS if docs include setup, safety, eval, and exact MVP tool list.
      Evidence `.omo/evidence/task-20-docs.txt` Commit: Y |
      `docs: document python mvp operation and evals` | Files `README.md`,
      `docs/evals.md`, `docs/mcp-tools.md`, `tests/docs/test_docs.py`

## Final verification wave (after ALL todos)

> Runs in parallel. ALL must APPROVE. Surface results and wait for the user's
> explicit okay before declaring complete.

- [x] F1. Plan compliance audit Verify every todo above is completed, every
      acceptance command has current evidence, no post-MVP tools are exposed,
      and all user decisions in `.omo/drafts/codescent-mcp-plan-interview.md`
      are reflected. Command:
      `uv run python scripts/audit_plan_compliance.py --plan .omo/plans/codescent-python-mvp.md --evidence .omo/evidence`.
      Evidence `.omo/evidence/final-plan-compliance.json`
- [x] F2. Code quality review Run `uv run ruff check .`,
      `uv run ruff format --check .`, `uv run basedpyright`, and
      `uv run pytest`. Review module sizes; no production module over 250 pure
      LOC without an explicit split or documented reason. Evidence
      `.omo/evidence/final-code-quality.txt`
- [x] F3. Real manual QA Run
      `uv run python scripts/smoke_mcp.py --repo tests/fixtures/python-basic full_loop --out .omo/evidence/final-fixture-full-loop.json`
      and
      `uv run python scripts/smoke_lx_data_lake.py --repo /Users/robertguss/Projects/wts-lx/lx_data_lake --out .omo/evidence/final-lx-full-loop.json`.
      Evidence must show MCP tool use, bounded output, findings, refactor plan,
      suggested tests, rescan, and source-read-only proof.
- [x] F4. Scope fidelity Run
      `uv run python evals/run_deterministic.py --repo tests/fixtures/python-basic --expected evals/fixtures/python-basic.expected.json --out .omo/evidence/final-deterministic-eval.json`,
      complete agent-in-the-loop transcript per `evals/agent_task.md`, and
      verify no network/default-source-edit behavior. Evidence
      `.omo/evidence/final-agent-eval-transcript.md`

## Commit strategy

- Do not auto-commit unless the user explicitly requests it.
- Stage only files for the completed todo; do not stage unrelated `.omo` scratch
  output unless requested.
- Use atomic Conventional Commits:
  - `chore(scaffold): initialize codescent python package`
  - `feat(core): add bounded domain models and errors`
  - `test(fixtures): add python mvp fixture repo`
  - `feat(index): add safe repository inventory`
  - `feat(storage): add sqlite project state`
  - `feat(index): persist repo index status`
  - `feat(cli): expose mvp service commands`
  - `feat(mcp): add repo map and status tools`
  - `feat(search): add bounded ranked search`
  - `feat(symbols): add python ast parser adapter`
  - `feat(context): add bounded python context packs`
  - `feat(health): add python smell scanner`
  - `feat(findings): add lifecycle and rescan`
  - `feat(planning): add finding context and refactor plans`
  - `feat(mcp): expose complete mvp tool surface`
  - `test(evals): add deterministic mvp evaluation`
  - `test(evals): add agent-in-the-loop eval gate`
  - `test(smoke): add lx data lake real repo smoke`
  - `test(safety): prove source-read-only runtime`
  - `docs: document python mvp operation and evals`
- Final commit footer for any plan-execution commit series:
  `Plan: .omo/plans/codescent-python-mvp.md`

## Success criteria

- `codescent` installs with `uv sync`, exposes CLI help, and has a working
  FastMCP stdio server.
- The 15 MVP MCP tools are exposed and only those 15 public tools are exposed.
- `codescent init/index/status/scan/doctor/serve` work against
  `tests/fixtures/python-basic`.
- CodeScent writes only `.codescent/` in analyzed repos and never edits analyzed
  source files.
- Default exclusions prevent indexing `.env`, `.git/`, `.venv/`, cache dirs,
  `.codescent/`, `data/`, `archive/`, binary/generated/vendor/build outputs.
- Python indexing stores file inventory, hashes, freshness, git/non-git status,
  symbols, imports, chunks, scan runs, findings, finding status, and eval
  telemetry in SQLite.
- Search returns bounded ranked results with reasons and fuzzy fallback.
- Python symbol/context tools return bounded summaries, related files, likely
  tests, confidence, and source ranges only under caps.
- Python health scanner finds expected fixture smells with evidence, severity,
  confidence, and stable IDs.
- Finding lifecycle, `get_next_improvement`, `mark_finding`, and `rescan` work
  across repeated scans and regressions.
- `plan_refactor` returns small, behavior-preserving plans with non-goals,
  affected files, risks, fallback, and suggested verification commands.
- Deterministic evals meet expected thresholds for retrieval, context
  efficiency, finding quality, workflow success, safety, and timing telemetry.
- Agent-in-the-loop eval transcript proves an agent used CodeScent tools to
  complete the scripted improvement loop.
- Real smoke on `/Users/robertguss/Projects/wts-lx/lx_data_lake` completes
  read-only with exclusions and captures evidence.
- Final quality gates pass: `uv run pytest`, `uv run ruff check .`,
  `uv run ruff format --check .`, `uv run basedpyright`, deterministic eval,
  fixture full-loop MCP smoke, real repo smoke, and source-read-only proof.
