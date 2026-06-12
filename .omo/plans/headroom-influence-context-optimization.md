# Headroom Influence Context Optimization

## TL;DR

> Summary: Implement the PRD-recommended context-optimization MVP for CodeScent:
> summarized result envelopes, local result storage, `retrieve_result`, basic
> `context_stats`, and type-aware shaping for selected high-volume MCP tools
> while preserving exact local retrieval. Deliverables:
>
> - Shared response-envelope/result-store models with preservation metadata.
> - SQLite-backed `stored_results` and `session_events` persistence with TTL
>   cleanup.
> - MCP tools `retrieve_result` and `context_stats` registered, documented, and
>   contract-tested.
> - Envelope/shaping applied only to `find_symbol`, `find_references`,
>   `search_content`, and `search_tests`.
> - Safety, contract, migration, MCP smoke, deterministic eval, and
>   source-read-only verification evidence. Effort: Large Risk: High - changes
>   public MCP payload contracts, storage schema, and source-read-only safety
>   surface.

## Scope

### Must have

- Implement the MVP from `docs/prd/headroom-influence-prd.md`: Feature 1,
  Feature 2, Feature 3, Feature 4 for selected existing surfaces, Feature 5,
  Feature 6, and the minimal Feature 7 event logging needed for stats.
- Add a standard summarized result envelope with fields equivalent to `kind`,
  `mode`, `summary`, `items`, `omitted_count`, `original_result_id`,
  `retrieval_available`, `retrieval_hints`, `confidence`, and `warnings`.
- Preserve backward compatibility where practical by keeping current top-level
  fields (`ok`, `query`, `limit`, `results`, `next_cursor`) on existing tools
  and adding envelope metadata alongside them. Do not replace every existing
  payload with a nested-only shape in this plan.
- Use these exact first-wave tool targets:
  - `find_symbol`
  - `find_references`
  - `search_content`
  - `search_tests`
- Add `retrieve_result` with modes `exact`, `summary`, `filtered`, and `sample`.
- Add `context_stats` for local context savings stats.
- Store full raw results only under `.codescent/index.sqlite` using CodeScent
  storage.
- Use opaque result IDs shaped as `ctx_<short_hash>`.
- Use a local approximate token estimator only:
  `ceil(len(serialized_json) / 4)`. No tokenizer dependency and no network.
- Define "large result" thresholds in code constants:
  - result count greater than returned `limit`
  - OR estimated raw token count greater than
    `CONTEXT_RESULT_TOKEN_THRESHOLD = 4000`
  - OR generated exact source snippets larger than
    `CONTEXT_SOURCE_TOKEN_THRESHOLD = 1500`
- Define session ID semantics without Pi-specific assumptions:
  - Optional `session_id` argument on `retrieve_result` and `context_stats`.
  - Existing shaped tools accept optional `session_id: str | None = None`.
  - If absent, service uses deterministic local fallback `sess_default`.
  - Stats can be queried for one session or all sessions.
- Define default result retention:
  - `DEFAULT_RESULT_TTL_SECONDS = 86400`.
  - Expiration stored per row.
  - Cleanup runs opportunistically before storing a new result and through a
    repository/service method used in tests.
- Define unknown/expired retrieval response shape:
  - Return a structured payload with `ok: false`,
    `error_code: "result_not_found"` or `"result_expired"`, `result_id`, and
    `warnings`.
  - Do not raise raw SQLite or KeyError exceptions through FastMCP.
- Track events needed by `context_stats`: `tool_called`,
  `large_result_summarized`, `result_retrieved`, `agent_repeated_query`,
  `agent_requested_exact_large_result`, and `server_warning_returned`.
- Record current unrelated dirty paths before execution and do not require or
  perform reverts:
  - `AGENTS.md` modified
  - `docs/prd.md` deleted
  - `uv.lock` modified
  - `docs/prd/prd.md` untracked
  - `.omo/drafts/headroom-influence-planning-notepad.md` untracked

### Must NOT have

- Do not implement failure learning, `project_learnings`, `project_guidance`,
  learned guidance review/editing, or export to `AGENTS.md`, `.cursorrules`,
  `CLAUDE.md`, or Pi-specific files.
- Do not implement optional Headroom integration, `compress_generic_output`,
  `retrieve_original_output`, library/proxy/subprocess integration, or generic
  model-output compression.
- Do not add dashboard UI/API work.
- Do not add runtime network access.
- Do not lossy-compress source code when the agent is about to edit it.
- Do not apply envelopes to every MCP tool in one sweep.
- Do not change fixture source under `tests/fixtures/` except runtime
  `.codescent/` state created by tests/smokes.
- Do not move business logic into FastMCP wrappers.
- Do not auto-write templates or guidance into analyzed repos.
- Do not revert unrelated user changes in the dirty worktree.

## Verification strategy

> Zero human intervention - all verification is agent-executed.

- Test decision: TDD with pytest contract/integration/security tests first for
  every behavior-changing todo.
- QA policy: every todo has one real-surface scenario through FastMCP client,
  CLI/tmux, or source-read-only proof where applicable.
- Evidence: `.omo/evidence/task-<N>-headroom-<slug>.<ext>`
- Required full gates after implementation:
  - `uv run pytest`
  - `uv run ruff check .`
  - `uv run ruff format --check .`
  - `uv run basedpyright`
  - `uv run python scripts/prove_source_read_only.py --repo tests/fixtures/python-basic --out .omo/evidence/task-F3-headroom-source-read-only.json`
  - FastMCP real-surface smoke exercising `find_symbol` or `search_content` ->
    `retrieve_result` -> `context_stats`.

## Execution strategy

### Parallel execution waves

> Target 5-8 todos per wave. < 3 per wave (except the final) = under-splitting.

Wave 1 (no deps): Todos 1-5

- Preflight and dirty-worktree recording.
- Public contract RED tests for new MCP tools.
- Storage migration RED tests.
- Envelope/model RED tests.
- Stats/event RED tests.

Wave 2 (after 1): Todos 6-10

- Storage schema/repository implementation.
- Envelope/result-store services.
- Retrieval service and MCP tool.
- Event/stats service and MCP tool.
- Public surface/docs registration.

Wave 3 (after 2): Todos 11-15

- Apply envelope to exact target tools.
- Add symbol/search/test-search shapers.
- Preservation rules.
- Security/source-read-only/no-network gates.
- Docs/eval/smoke updates.

Wave 4 (after 3): Todos 16-18

- FastMCP real-surface smoke.
- Full verification.
- Plan compliance and cleanup.

Critical path: 1 -> 2 -> 6 -> 7 -> 8 -> 9 -> 10 -> 11 -> 16 -> 17 -> 18

### Dependency matrix

| Todo | Depends on               | Blocks        | Can parallelize with |
| ---- | ------------------------ | ------------- | -------------------- |
| 1    | none                     | all todos     | none                 |
| 2    | 1                        | 10, 16        | 3, 4, 5              |
| 3    | 1                        | 6             | 2, 4, 5              |
| 4    | 1                        | 7, 11, 12, 13 | 2, 3, 5              |
| 5    | 1                        | 9             | 2, 3, 4              |
| 6    | 3                        | 7, 8, 9       | 10                   |
| 7    | 4, 6                     | 8, 11, 12, 13 | 9, 10                |
| 8    | 6, 7                     | 16            | 9, 10                |
| 9    | 5, 6                     | 16            | 8, 10                |
| 10   | 2                        | 16, 17        | 6, 7, 8, 9           |
| 11   | 7                        | 16            | 12, 13, 14, 15       |
| 12   | 7                        | 16            | 11, 13, 14, 15       |
| 13   | 7                        | 16            | 11, 12, 14, 15       |
| 14   | 7                        | 16, 17        | 11, 12, 13, 15       |
| 15   | 10, 11, 12, 13           | 17            | 14                   |
| 16   | 8, 9, 10, 11, 12, 13, 14 | 17            | none                 |
| 17   | 15, 16                   | 18            | none                 |
| 18   | 17                       | done          | none                 |

## Todos

> Implementation + Test = ONE todo. Never separate.

- [] 1. Record preflight state and isolate unrelated dirty paths What to do /
  Must NOT do
  - Add implementation evidence file
    `.omo/evidence/task-1-headroom-preflight.txt`.
  - Run `git status --short`, `mcp__codescent.get_repo_status`, and
    `mcp__codescent.search_changed_files`.
  - Record unrelated dirty paths exactly as observed before execution.
  - Must NOT revert or edit `AGENTS.md`, `docs/prd.md`, or `docs/prd/prd.md`
    unless a later user request explicitly changes scope. Parallelization: Can
    parallel N | Wave 1 | Blocks all todos References: `AGENTS.md`,
    `.omo/drafts/headroom-influence-planning-notepad.md`,
    `docs/prd/headroom-influence-prd.md`,
    `src/codescent/core/public_surface.py`, `docs/mcp-tools.md` Acceptance
    criteria (agent-executable):
    `git status --short > .omo/evidence/task-1-headroom-preflight.txt` plus
    append CodeScent MCP status and changed-file results; evidence names all
    unrelated dirty paths and says they are out of scope. QA scenarios (name the
    exact tool + invocation): CodeScent MCP channel: call
    `mcp__codescent.get_repo_status({"repo":"/Users/robertguss/Projects/startups/code-scent-mcp"})`;
    PASS if `database_ok=true` and dirty state is recorded without source edits.
    Evidence `.omo/evidence/task-1-headroom-preflight.txt` Commit: N |
    planning/preflight only | Files
    `.omo/evidence/task-1-headroom-preflight.txt`

- [] 2. Add RED public-surface contract tests for `retrieve_result` and
  `context_stats` What to do / Must NOT do
  - Update `tests/contract/test_mcp_tool_surface.py` to expect `retrieve_result`
    and `context_stats`.
  - Update `tests/contract/test_public_surface_registry.py` to require both
    tools as registered post-MVP MCP tools in the `context` group.
  - Tests must fail before implementation because the tools are not registered.
  - Must NOT add `project_learnings`, `project_guidance`, or optional
    compression tools. Parallelization: Can parallel Y | Wave 1 | Blocks 10, 16
    References: `src/codescent/core/public_surface.py`,
    `src/codescent/mcp/server.py`, `tests/contract/test_mcp_tool_surface.py`,
    `tests/contract/test_public_surface_registry.py`,
    `docs/prd/headroom-influence-prd.md:270` Acceptance criteria
    (agent-executable): RED:
    `uv run pytest tests/contract/test_mcp_tool_surface.py::test_exact_mvp_tool_names tests/contract/test_public_surface_registry.py::test_post_mvp_surface_tracks_registered_and_locked_tools -q`
    fails with missing `retrieve_result` and `context_stats`; GREEN after Todo
    10 passes. QA scenarios (name the exact tool + invocation): tmux channel:
    `tmux new-session -d -s ulw-qa-task2 'cd /Users/robertguss/Projects/startups/code-scent-mcp && uv run pytest tests/contract/test_mcp_tool_surface.py::test_exact_mvp_tool_names -q; echo EXIT:$?'`;
    PASS after implementation if transcript includes `1 passed` and `EXIT:0`.
    Evidence `.omo/evidence/task-2-headroom-public-surface.txt` Commit: Y |
    test(context): pin context optimization MCP surface | Files
    `tests/contract/test_mcp_tool_surface.py`,
    `tests/contract/test_public_surface_registry.py`

- [] 3. Add RED storage migration and repository tests for result/session tables
  What to do / Must NOT do
  - Add tests that require `stored_results` and `session_events` tables after
    migration from schema version 4.
  - Assert existing file/symbol/finding data survives migration.
  - Add tests for cleanup of expired rows.
  - Add tests for concurrent store/retrieve behavior using existing storage
    guard expectations. Parallelization: Can parallel Y | Wave 1 | Blocks 6
    References: `src/codescent/storage/schema.py:4`,
    `src/codescent/storage/repository.py`,
    `tests/integration/test_storage_migrations.py`,
    `tests/integration/test_storage_concurrency.py`,
    `docs/prd/headroom-influence-prd.md:198` Acceptance criteria
    (agent-executable): RED:
    `uv run pytest tests/integration/test_storage_migrations.py tests/integration/test_storage_concurrency.py -q`
    fails on missing tables/repository methods; GREEN after Todo 6 passes. QA
    scenarios (name the exact tool + invocation): tmux channel:
    `tmux new-session -d -s ulw-qa-task3 'cd /Users/robertguss/Projects/startups/code-scent-mcp && uv run pytest tests/integration/test_storage_migrations.py::test_migrates_mvp_schema_to_latest_without_data_loss -q; echo EXIT:$?'`;
    PASS if schema version bump test passes and transcript includes `EXIT:0`.
    Evidence `.omo/evidence/task-3-headroom-storage-migration.txt` Commit: Y |
    test(storage): pin context result persistence migration | Files
    `tests/integration/test_storage_migrations.py`,
    `tests/integration/test_storage_concurrency.py`

- [] 4. Add RED unit tests for envelope, result IDs, thresholds, and
  preservation rules What to do / Must NOT do
  - Add unit tests for typed envelope model, token estimate, threshold decision,
    result ID format, retrieval hint generation, and preservation ordering.
  - Preserve critical items before reducing: errors, tracebacks, failing
    assertions, changed files, generated warnings, source ranges,
    highest-severity findings, verification failures, commands that failed,
    unreadable files, permission/environment errors.
  - Use exact thresholds `4000` raw result tokens and `1500` source tokens.
    Parallelization: Can parallel Y | Wave 1 | Blocks 7, 11, 12, 13 References:
    `docs/prd/headroom-influence-prd.md:140`,
    `docs/prd/headroom-influence-prd.md:451`,
    `src/codescent/services/search_support.py`,
    `src/codescent/services/context_support.py` Acceptance criteria
    (agent-executable): RED:
    `uv run pytest tests/unit/test_context_optimization.py -q` fails because
    modules do not exist; GREEN after Todo 7 passes. QA scenarios (name the
    exact tool + invocation): tmux channel:
    `tmux new-session -d -s ulw-qa-task4 'cd /Users/robertguss/Projects/startups/code-scent-mcp && uv run pytest tests/unit/test_context_optimization.py -q; echo EXIT:$?'`;
    PASS if transcript includes expected preservation test names and `EXIT:0`.
    Evidence `.omo/evidence/task-4-headroom-envelope-unit.txt` Commit: Y |
    test(context): pin summarized envelope rules | Files
    `tests/unit/test_context_optimization.py`

- [] 5. Add RED stats/event service tests What to do / Must NOT do
  - Add integration tests for session events and `context_stats` aggregation.
  - Assert stats exclude source content and include `tool_calls`,
    `summarized_results`, `retrievals`, `estimated_raw_tokens`,
    `estimated_returned_tokens`, `estimated_tokens_avoided`,
    `largest_summarized_results`, `most_used_tools`, and `warnings`.
  - Assert repeated broad queries can be identified. Parallelization: Can
    parallel Y | Wave 1 | Blocks 9 References:
    `docs/prd/headroom-influence-prd.md:502`,
    `docs/prd/headroom-influence-prd.md:567`,
    `src/codescent/storage/schema.py:129`, `tests/integration/test_storage.py`
    Acceptance criteria (agent-executable): RED:
    `uv run pytest tests/integration/test_context_stats.py -q` fails because
    service/tool does not exist; GREEN after Todo 9 passes. QA scenarios (name
    the exact tool + invocation): tmux channel:
    `tmux new-session -d -s ulw-qa-task5 'cd /Users/robertguss/Projects/startups/code-scent-mcp && uv run pytest tests/integration/test_context_stats.py -q; echo EXIT:$?'`;
    PASS if transcript includes `context_stats` aggregation assertions and
    `EXIT:0`. Evidence `.omo/evidence/task-5-headroom-context-stats.txt` Commit:
    Y | test(context): pin context stats aggregation | Files
    `tests/integration/test_context_stats.py`

- [] 6. Implement schema version 5 and result/session repositories What to do /
  Must NOT do
  - Bump `SCHEMA_VERSION` from 4 to 5.
  - Add migration statements for `stored_results` and `session_events`.
  - Add repository methods in a focused module such as
    `src/codescent/storage/repositories/context_results.py`.
  - Store JSON as text with deterministic serialization.
  - Increment retrieval count atomically.
  - Cleanup expired results before store and through explicit method.
  - Avoid making common reads depend on writes unless storing a large result or
    recording an event. Parallelization: Can parallel Y | Wave 2 | Blocks 7, 8,
    9 References: `src/codescent/storage/schema.py`,
    `src/codescent/storage/repository.py`,
    `src/codescent/storage/repositories/`,
    `tests/integration/test_storage_migrations.py`,
    `tests/integration/test_storage_concurrency.py` Acceptance criteria
    (agent-executable):
    `uv run pytest tests/integration/test_storage.py tests/integration/test_storage_migrations.py tests/integration/test_storage_concurrency.py -q`
    exits 0. QA scenarios (name the exact tool + invocation): tmux channel:
    `tmux new-session -d -s ulw-qa-task6 'cd /Users/robertguss/Projects/startups/code-scent-mcp && uv run pytest tests/integration/test_storage_migrations.py tests/integration/test_storage_concurrency.py -q; echo EXIT:$?'`;
    PASS if transcript includes all selected tests passing and `EXIT:0`.
    Evidence `.omo/evidence/task-6-headroom-storage-green.txt` Commit: Y |
    feat(storage): persist context result and session events | Files
    `src/codescent/storage/schema.py`,
    `src/codescent/storage/repositories/context_results.py`, storage tests

- [] 7. Implement envelope/result-store service models What to do / Must NOT do
  - Add typed domain models in `src/codescent/services/context_optimization.py`
    or a similarly focused services module.
  - Add `ResultEnvelope`, `StoredResult`, `RetrievalRequest`,
    `RetrievalPayload`, and preservation helpers.
  - Generate `ctx_<short_hash>` IDs from canonicalized tool name, input JSON,
    raw result JSON, and collision suffix when needed.
  - Build retrieval hints using actual tool name
    `retrieve_result(result_id=...)`.
  - Keep model/service logic out of MCP adapters. Parallelization: Can parallel
    Y | Wave 2 | Blocks 8, 11, 12, 13 References:
    `docs/prd/headroom-influence-prd.md:158`,
    `src/codescent/services/search_support.py`,
    `src/codescent/services/context_support.py`,
    `tests/unit/test_context_optimization.py` Acceptance criteria
    (agent-executable):
    `uv run pytest tests/unit/test_context_optimization.py -q` exits 0. QA
    scenarios (name the exact tool + invocation): tmux channel:
    `tmux new-session -d -s ulw-qa-task7 'cd /Users/robertguss/Projects/startups/code-scent-mcp && uv run pytest tests/unit/test_context_optimization.py -q; echo EXIT:$?'`;
    PASS if transcript includes result ID, threshold, and preservation tests
    passing with `EXIT:0`. Evidence
    `.omo/evidence/task-7-headroom-envelope-green.txt` Commit: Y |
    feat(context): add summarized result envelope service | Files
    `src/codescent/services/context_optimization.py`, unit tests

- [] 8. Implement `retrieve_result` service and MCP tool What to do / Must NOT
  do
  - Add service method to retrieve stored result by ID.
  - Support modes `exact`, `summary`, `filtered`, and `sample`.
  - Support filters `query`, `file`, `symbol`, `limit`, and `mode`.
  - Exact source/code snippets may return only when explicitly requested through
    `mode="exact"` or a specific filter.
  - Unknown and expired IDs return structured `ok:false` payloads.
  - Register MCP wrapper in a new focused module, for example
    `src/codescent/mcp/context_optimization_tools.py`. Parallelization: Can
    parallel Y | Wave 2 | Blocks 16 References:
    `docs/prd/headroom-influence-prd.md:270`, `src/codescent/mcp/server.py`,
    `src/codescent/core/public_surface.py`,
    `tests/contract/test_mcp_context_tools.py` Acceptance criteria
    (agent-executable):
    `uv run pytest tests/contract/test_mcp_context_tools.py tests/integration/test_context_results.py -q`
    exits 0. QA scenarios (name the exact tool + invocation): FastMCP client
    channel: run a Python snippet with `Client(mcp)` that calls a shaped tool to
    produce `original_result_id`, then calls `retrieve_result` with
    `mode="filtered"` and `file=<fixture file>`; PASS if payload has `ok:true`,
    matching `result_id`, filtered `items`, and no unfiltered source dump.
    Evidence `.omo/evidence/task-8-headroom-retrieve-fastmcp.json` Commit: Y |
    feat(mcp): add retrievable context results | Files
    `src/codescent/services/context_optimization.py`,
    `src/codescent/mcp/context_optimization_tools.py`,
    `src/codescent/mcp/server.py`, tests

- [] 9. Implement context stats service and MCP tool What to do / Must NOT do
  - Aggregate `session_events` into `context_stats`.
  - Track tool calls, summarized results, retrievals, estimated
    raw/returned/avoided tokens, largest summarized results, most used tools,
    repeated queries, and warnings.
  - Do not include raw source content in stats payloads.
  - Support `session_id: str | None = None` and all-session aggregate.
    Parallelization: Can parallel Y | Wave 2 | Blocks 16 References:
    `docs/prd/headroom-influence-prd.md:502`,
    `docs/prd/headroom-influence-prd.md:567`,
    `tests/integration/test_context_stats.py` Acceptance criteria
    (agent-executable):
    `uv run pytest tests/integration/test_context_stats.py tests/contract/test_mcp_tool_surface.py -q`
    exits 0. QA scenarios (name the exact tool + invocation): FastMCP client
    channel: call
    `search_content(query="TODO", repo="tests/fixtures/python-basic", session_id="sess_plan_qa")`,
    then
    `context_stats(repo="tests/fixtures/python-basic", session_id="sess_plan_qa")`;
    PASS if stats show at least one tool call and no source content. Evidence
    `.omo/evidence/task-9-headroom-stats-fastmcp.json` Commit: Y |
    feat(context): expose local context savings stats | Files
    `src/codescent/services/context_stats.py`,
    `src/codescent/mcp/context_optimization_tools.py`, tests

- [] 10. Register public surface and update docs/contracts What to do / Must NOT
  do
  - Add `retrieve_result` and `context_stats` to
    `REGISTERED_POST_MVP_MCP_TOOL_NAMES`, `POST_MVP_MCP_TOOL_NAMES`, and
    `PUBLIC_SURFACE`.
  - Add docs to `docs/mcp-tools.md` with bounds, payload shape, and
    source-read-only wording.
  - Update `tests/docs/test_docs.py` deliberately so docs cover these registered
    tools.
  - Update `README.md` only if package/public surface docs require it.
  - Do not mention or register excluded future tools. Parallelization: Can
    parallel Y | Wave 2 | Blocks 16, 17 References:
    `src/codescent/core/public_surface.py`, `docs/mcp-tools.md`,
    `tests/docs/test_docs.py`, `tests/contract/test_mcp_tool_surface.py`
    Acceptance criteria (agent-executable):
    `uv run pytest tests/contract/test_public_surface_registry.py tests/contract/test_mcp_tool_surface.py tests/docs/test_docs.py -q`
    exits 0. QA scenarios (name the exact tool + invocation): FastMCP client
    channel: `Client(mcp).list_tools()`; PASS if names include `retrieve_result`
    and `context_stats` and do not include `project_learnings`,
    `project_guidance`, `compress_generic_output`, or
    `retrieve_original_output`. Evidence
    `.omo/evidence/task-10-headroom-public-surface.json` Commit: Y | docs(mcp):
    document context optimization tools | Files
    `src/codescent/core/public_surface.py`, `docs/mcp-tools.md`, docs/contract
    tests

- [] 11. Apply envelope to `find_symbol` and `find_references` What to do / Must
  NOT do
  - Add optional `session_id` argument to `find_symbol` and `find_references`.
  - Return current fields plus envelope metadata.
  - Store raw full result when threshold is exceeded or when omitted rows exist
    due to limit.
  - Preserve symbol names, qualified names, definition/reference distinction
    where available, file/module grouping, confidence, and line ranges.
  - Do not return full source files. Parallelization: Can parallel Y | Wave 3 |
    Blocks 16 References: `src/codescent/mcp/context_tools.py:126`,
    `src/codescent/services/context.py:55`,
    `src/codescent/services/context.py:117`,
    `tests/contract/test_mcp_context_tools.py`,
    `tests/integration/test_context.py` Acceptance criteria (agent-executable):
    `uv run pytest tests/contract/test_mcp_context_tools.py tests/integration/test_context.py -q`
    exits 0. QA scenarios (name the exact tool + invocation): FastMCP client
    channel: call
    `find_symbol(query="load", repo="tests/fixtures/python-basic", limit=1, session_id="sess_symbol_qa")`;
    PASS if payload has `ok:true`, `mode`, `summary`, `retrieval_available`, and
    no `source_content`. Evidence
    `.omo/evidence/task-11-headroom-symbol-fastmcp.json` Commit: Y |
    feat(context): summarize symbol and reference results | Files
    `src/codescent/services/context.py`, `src/codescent/mcp/context_tools.py`,
    context tests

- [] 12. Apply envelope to `search_content` What to do / Must NOT do
  - Add optional `session_id` to `search_content`.
  - Preserve current `ok`, `query`, `limit`, `next_cursor`, and `results`
    fields.
  - Add envelope metadata when results are omitted or threshold exceeded.
  - Store raw full result before page slicing so `retrieve_result` can filter by
    file/query later.
  - Keep snippets capped by existing `line_budget=1` unless explicitly
    retrieved. Parallelization: Can parallel Y | Wave 3 | Blocks 16 References:
    `src/codescent/mcp/search_tools.py:131`,
    `src/codescent/services/search.py:97`,
    `src/codescent/services/search_support.py:60`,
    `tests/contract/test_mcp_search_tools.py`,
    `tests/integration/test_search.py` Acceptance criteria (agent-executable):
    `uv run pytest tests/contract/test_mcp_search_tools.py tests/integration/test_search.py -q`
    exits 0. QA scenarios (name the exact tool + invocation): FastMCP client
    channel: call
    `search_content(query="TODO", repo="tests/fixtures/python-basic", limit=1, session_id="sess_search_qa")`,
    then
    `retrieve_result(result_id=<id>, mode="filtered", query="TODO", limit=5)`;
    PASS if retrieved payload contains only filtered items and original search
    payload remains bounded. Evidence
    `.omo/evidence/task-12-headroom-search-fastmcp.json` Commit: Y |
    feat(search): make content search retrievable | Files
    `src/codescent/services/search.py`, `src/codescent/mcp/search_tools.py`,
    search tests

- [] 13. Apply envelope to `search_tests` and defer generic command-output
  shaping What to do / Must NOT do
  - Add optional `session_id` to `search_tests`.
  - Shape test-search results as the PRD's "test surface" for this MVP because
    no MCP tool currently ingests pytest/lint/type-check output.
  - Preserve test file path, ranking reasons, snippet,
    query/path/symbol/finding_id inputs, and limit.
  - Add explicit docs note that generic pytest/lint/type-check output shaping is
    deferred until a command-output ingestion surface exists. Parallelization:
    Can parallel Y | Wave 3 | Blocks 16 References:
    `src/codescent/mcp/search_tools.py:199`,
    `src/codescent/services/search.py:234`,
    `docs/prd/headroom-influence-prd.md:383`,
    `tests/contract/test_mcp_search_tools.py` Acceptance criteria
    (agent-executable):
    `uv run pytest tests/contract/test_mcp_search_tools.py::test_search_todos_and_tests_are_bounded_and_ranked tests/integration/test_search.py::test_search_todos_and_tests_service_rank_bounded_results -q`
    exits 0 and new assertions cover envelope metadata for `search_tests`. QA
    scenarios (name the exact tool + invocation): FastMCP client channel: call
    `search_tests(query="app", repo="tests/fixtures/python-basic", limit=1, session_id="sess_tests_qa")`;
    PASS if payload has bounded test results, envelope metadata, and retrieval
    hint when omitted rows exist. Evidence
    `.omo/evidence/task-13-headroom-search-tests-fastmcp.json` Commit: Y |
    feat(search): summarize test discovery results | Files
    `src/codescent/services/search.py`, `src/codescent/mcp/search_tools.py`,
    docs/tests

- [] 14. Extend safety and runtime guarantees for new context tools What to do /
  Must NOT do
  - Add `retrieve_result` and `context_stats` to source-read-only proof
    coverage.
  - Add no-network assertions for result store, retrieval, stats, shaping, and
    cleanup paths.
  - Assert retrieval exact mode does not mutate analyzed source.
  - Assert unknown/expired IDs do not expose absolute sensitive paths beyond
    existing repo-relative paths. Parallelization: Can parallel Y | Wave 3 |
    Blocks 16, 17 References: `tests/security/test_runtime_safety.py`,
    `scripts/prove_source_read_only.py`, `docs/mcp-tools.md:105`,
    `docs/prd/headroom-influence-prd.md:253` Acceptance criteria
    (agent-executable): `uv run pytest tests/security/test_runtime_safety.py -q`
    exits 0. QA scenarios (name the exact tool + invocation): tmux channel:
    `tmux new-session -d -s ulw-qa-task14 'cd /Users/robertguss/Projects/startups/code-scent-mcp && uv run python scripts/prove_source_read_only.py --repo tests/fixtures/python-basic --out .omo/evidence/task-14-headroom-source-read-only.json; echo EXIT:$?'`;
    PASS if JSON says source hashes unchanged and transcript includes `EXIT:0`.
    Evidence `.omo/evidence/task-14-headroom-source-read-only.json` Commit: Y |
    test(security): cover context result safety | Files
    `tests/security/test_runtime_safety.py`, `scripts/prove_source_read_only.py`

- [] 15. Update eval and smoke documentation for retrieval workflow What to do /
  Must NOT do
  - Update deterministic eval docs/run-agent eval docs only enough to describe
    the new summarize -> retrieve -> stats workflow.
  - Update smoke script(s) or add a focused smoke helper that drives FastMCP
    in-process against `tests/fixtures/python-basic`.
  - Do not require real Pi or external Headroom.
  - Avoid scattering future-tool names in changelog/docs outside the new
    registered tools. Parallelization: Can parallel Y | Wave 3 | Blocks 17
    References: `docs/evals.md`, `scripts/run_agent_eval.md`,
    `scripts/smoke_mcp.py`, `tests/evals/test_agent_eval_spec.py`,
    `tests/docs/test_docs.py` Acceptance criteria (agent-executable):
    `uv run pytest tests/evals/test_agent_eval_spec.py tests/docs/test_docs.py -q`
    exits 0. QA scenarios (name the exact tool + invocation): tmux channel:
    `tmux new-session -d -s ulw-qa-task15 'cd /Users/robertguss/Projects/startups/code-scent-mcp && uv run pytest tests/evals/test_agent_eval_spec.py tests/docs/test_docs.py -q; echo EXIT:$?'`;
    PASS if transcript includes docs/eval tests passing and no unsupported
    future tools. Evidence `.omo/evidence/task-15-headroom-docs-eval.txt`
    Commit: Y | docs(evals): add context retrieval eval path | Files
    `docs/evals.md`, `scripts/run_agent_eval.md`, smoke/doc tests

- [] 16. Run real FastMCP summarize -> retrieve -> stats smoke What to do / Must
  NOT do
  - Use `fastmcp.Client(mcp)` against the real in-process MCP app.
  - Initialize fixture state first if needed:
    `uv run codescent init --repo tests/fixtures/python-basic`.
  - Call `find_symbol` or `search_content` with a low limit and `session_id`.
  - Capture `original_result_id`.
  - Call `retrieve_result` with filtered mode.
  - Call `context_stats` for the same session.
  - Save raw JSON artifact. Parallelization: Can parallel N | Wave 4 | Blocks 17
    References: `src/codescent/mcp/server.py`, `scripts/smoke_mcp.py`,
    `tests/fixtures/python-basic`, `docs/prd/headroom-influence-prd.md:335`
    Acceptance criteria (agent-executable):
    `uv run python scripts/smoke_mcp.py --repo tests/fixtures/python-basic --out .omo/evidence/task-16-headroom-fastmcp-smoke.json`
    or a new equivalent smoke command exits 0 and artifact proves all three tool
    calls. QA scenarios (name the exact tool + invocation): tmux channel:
    `tmux new-session -d -s ulw-qa-task16 'cd /Users/robertguss/Projects/startups/code-scent-mcp && uv run python scripts/smoke_mcp.py --repo tests/fixtures/python-basic --out .omo/evidence/task-16-headroom-fastmcp-smoke.json; echo EXIT:$?'`;
    PASS if JSON includes `source_hashes_unchanged:true`, a `ctx_` ID, retrieve
    payload `ok:true`, and stats `retrievals>=1`. Evidence
    `.omo/evidence/task-16-headroom-fastmcp-smoke.json` Commit: Y | test(smoke):
    prove retrievable context MCP loop | Files `scripts/smoke_mcp.py` or focused
    smoke helper, smoke tests

- [] 17. Run full verification and classify unrelated dirty-tree failures What
  to do / Must NOT do
  - Run the full gates.
  - If failures are caused by pre-existing unrelated dirty paths (`docs/prd.md`
    deletion, moved `docs/prd/prd.md`, `AGENTS.md`, `uv.lock`), record exact
    failing test/command and cause in evidence without reverting.
  - Fix failures caused by this plan's implementation.
  - Clean only artifacts created by this implementation that should not remain.
    Parallelization: Can parallel N | Wave 4 | Blocks 18 References:
    `pyproject.toml`, `AGENTS.md`, `tests/`, `docs/mcp-tools.md`,
    `docs/evals.md` Acceptance criteria (agent-executable):
  - `uv run pytest`
  - `uv run ruff check .`
  - `uv run ruff format --check .`
  - `uv run basedpyright`
  - `uv run python scripts/prove_source_read_only.py --repo tests/fixtures/python-basic --out .omo/evidence/task-17-headroom-source-read-only.json`
    QA scenarios (name the exact tool + invocation): tmux channel:
    `tmux new-session -d -s ulw-qa-task17 'cd /Users/robertguss/Projects/startups/code-scent-mcp && { uv run pytest && uv run ruff check . && uv run ruff format --check . && uv run basedpyright; }; echo EXIT:$?'`;
    PASS if transcript includes all gates 0, or evidence classifies unrelated
    pre-existing failures with exact commands. Evidence
    `.omo/evidence/task-17-headroom-full-gates.txt` Commit: Y | chore(qa):
    verify context optimization MVP | Files evidence only unless fixes required

- [] 18. Final plan compliance, scope fidelity, and handoff What to do / Must
  NOT do
  - Verify all todos have evidence files.
  - Verify no must-not-have feature was implemented.
  - Verify new public tools are documented and contract-tested.
  - Verify no unrelated dirty paths were reverted or absorbed.
  - Prepare final implementation summary and commit list. Parallelization: Can
    parallel N | Wave 4 | Blocks done References:
    `.omo/plans/headroom-influence-context-optimization.md`, `.omo/evidence/`,
    `src/codescent/core/public_surface.py`, `docs/mcp-tools.md` Acceptance
    criteria (agent-executable):
    `test -f .omo/evidence/task-16-headroom-fastmcp-smoke.json && test -f .omo/evidence/task-17-headroom-full-gates.txt && git status --short`
    shows only intended deliverables plus pre-existing unrelated paths. QA
    scenarios (name the exact tool + invocation): tmux channel:
    `tmux new-session -d -s ulw-qa-task18 'cd /Users/robertguss/Projects/startups/code-scent-mcp && rg -n \"project_learnings|project_guidance|compress_generic_output|retrieve_original_output|headroom_enabled\" src tests docs/mcp-tools.md; echo EXIT:$?'`;
    PASS if forbidden implementation names are absent from `src/` and only
    appear in PRD/post-MVP docs where explicitly out of scope. Evidence
    `.omo/evidence/task-18-headroom-scope-fidelity.txt` Commit: Y | chore(plan):
    close context optimization MVP evidence | Files evidence/summary only

## Final verification wave (after ALL todos)

> Runs in parallel. ALL must APPROVE. Surface results and wait for the user's
> explicit okay before declaring complete.

- [] F1. Plan compliance audit
  - Run
    `uv run python scripts/audit_plan_compliance.py --plan .omo/plans/headroom-influence-context-optimization.md --evidence-dir .omo/evidence`
    if the script supports custom plan paths; otherwise run a manual checklist
    with `rg` and evidence file existence.
  - PASS if every todo has evidence and no unchecked must-have remains.

- [] F2. Code quality review
  - Run `uv run ruff check .`, `uv run ruff format --check .`, and
    `uv run basedpyright`.
  - PASS if all exit 0 or unrelated dirty-tree failures are isolated with exact
    proof.

- [] F3. Real manual QA
  - Run FastMCP summarize -> retrieve -> stats smoke from Todo 16.
  - PASS if artifact contains a `ctx_` result ID, retrieval succeeds, stats
    count the retrieval, and source hashes are unchanged.

- [] F4. Scope fidelity
  - Search implementation paths for excluded future features.
  - PASS if `project_learnings`, `project_guidance`, optional Headroom
    integration, dashboard stats, and generic compression were not implemented.

## Commit strategy

- Do not auto-commit unless the user explicitly requests it.
- Stage only intended deliverables. Leave unrelated dirty paths out of scope:
  - `AGENTS.md`
  - `docs/prd.md`
  - `docs/prd/prd.md`
  - unrelated `uv.lock` changes if present
- Suggested commit sequence:
  1. `test(context): pin context optimization contracts`
  2. `feat(storage): persist context result events`
  3. `feat(context): add retrievable summarized results`
  4. `feat(mcp): expose context retrieval stats`
  5. `docs(mcp): document context optimization tools`
  6. `test(smoke): prove retrievable context workflow`
- Final commit footer if committing this plan's implementation:
  `Plan: .omo/plans/headroom-influence-context-optimization.md`

## Success criteria

- `retrieve_result` and `context_stats` are registered MCP tools, documented,
  and contract-tested.
- `find_symbol`, `find_references`, `search_content`, and `search_tests` return
  bounded current fields plus envelope metadata when large/partial results
  exist.
- Large/partial raw results are stored locally in `.codescent/index.sqlite`,
  retrievable by `ctx_` ID, expirable by TTL, and never silently discarded.
- Unknown/expired retrieval IDs return structured `ok:false` errors.
- `context_stats` reports local token savings/retrieval counts without source
  content.
- Preservation rules ensure critical errors, source ranges, changed-file info,
  and verification failures remain surfaced before reduction.
- FastMCP smoke proves summarize -> retrieve -> stats through the real MCP
  surface.
- Source-read-only and no-network safety gates pass for the new tools.
- Full gates pass or only pre-existing unrelated dirty-tree failures are
  explicitly classified.
- No failure-learning, project-guidance, optional Headroom, dashboard, or
  generic compression features are implemented in this MVP.
