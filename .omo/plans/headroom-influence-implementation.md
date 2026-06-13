# Headroom-Inspired Context Optimization MVP

## TL;DR

> **Quick Summary**: Implement the PRD's MVP for deterministic, local context optimization: summarized result envelopes, a repo-local result store, `retrieve_result`, symbol-search/test-output shaping, preservation rules, and basic `context_stats`.
>
> **Deliverables**:
> - Standard summarized result envelope and deterministic formatter contracts.
> - SQLite-backed `stored_results` and `session_events` persistence under `.codescent/index.sqlite`.
> - MCP tools: `retrieve_result` and `context_stats`.
> - MVP shaping for symbol-search-like output and test output.
> - Public surface/docs/contract/security/storage tests updated in lockstep.
>
> **Estimated Effort**: Large
> **Parallel Execution**: YES - 4 implementation waves + final verification
> **Critical Path**: Wave 1 foundations join at Wave 2 services (6/7/8/9/10) → Wave 3 MCP integration joins (11/12/13 → 14) → 18 → F1-F4

---

## Context

### Original Request
Create a plan to implement `docs/prd/headroom-influence-prd.md`.

### Interview Summary
**Key Discussions**:
- Explicit plan-generation request; no implementation in this session.
- Use PRD section 14 Recommended MVP as implementation scope.
- Default decisions: fast local token approximation, session-scoped TTL result storage, deterministic rule-based shaping, tests-after automated tests plus mandatory agent QA.

**Research Findings**:
- MCP tool registration starts in `src/codescent/mcp/server.py`; public tool names are governed by `src/codescent/core/public_surface.py` and strict contract/docs tests.
- Current MCP payloads are direct JSON objects; changing top-level shapes can break contract tests unless public surface/docs/tests are updated together.
- Storage is repo-local SQLite in `.codescent/index.sqlite`; schema/migrations live in `src/codescent/storage/schema.py`, currently `SCHEMA_VERSION = 4`.
- Test infrastructure exists and is strong: pytest, fastmcp Client, Typer CliRunner, direct SQLite assertions, docs tests, security tests, ruff, and basedpyright.
- No live response token estimator exists; MVP must use local approximate counting and disclose estimate basis.

### Metis Review
**Identified Gaps** (addressed):
- Backward compatibility: plan explicitly requires a compatibility strategy and lockstep public contract updates.
- `retrieve_result` scope: limited to opaque result ID retrieval and documented filters; no broad history/query API.
- Shaping semantics: deterministic and local only; no LLM summarization.
- Storage edge cases: migration, restart persistence, missing IDs, TTL expiry, cleanup, reset behavior, concurrent writes, and oversized payloads must be tested.

### High Accuracy Review
- User selected **High Accuracy Review** after plan generation.
- Momus first review rejected a conflict between automated verification and user-approval wording.
- Plan was edited to clarify that any user acknowledgement is outside automated verification Definition of Done.
- Fresh Momus re-review returned **OKAY** for `.omo/plans/headroom-influence-implementation.md`.

---

## Work Objectives

### Core Objective
Implement the PRD MVP so large CodeScent MCP results return the smallest useful deterministic representation while preserving exact originals locally for bounded retrieval.

### Concrete Deliverables
- `ResponseEnvelope`/formatter models and preservation rules in service/engine layer.
- `stored_results` and `session_events` schema migration and repository/service accessors.
- MCP tools `retrieve_result` and `context_stats` registered, documented, and contract-tested.
- Symbol-search/result shaping integrated for the existing CodeScent symbol/search surface.
- Test-output formatter implemented and tested with deterministic fixture strings.
- Context/token stats based on local event log and approximate token counts.

### Definition of Done
- [ ] `uv run pytest` passes.
- [ ] `uv run ruff check .` passes.
- [ ] `uv run ruff format --check .` passes.
- [ ] `uv run basedpyright` passes.
- [ ] `uv run pytest tests/contract/test_mcp_tool_surface.py tests/docs/test_docs.py` passes.
- [ ] New evidence files exist under `.omo/evidence/` for every task QA scenario.

### Must Have
- Deterministic summarized envelope with explicit `mode`, `omitted_count`, `original_result_id`, `retrieval_available`, `retrieval_hints`, `confidence`, and `warnings` where applicable.
- Full raw summarized results stored locally and retrievable by opaque `ctx_<short_hash>` IDs.
- Exact source snippets/ranges preserved when edit context may be used.
- Errors, tracebacks, failing assertions, public API information, security findings, highest-severity findings, circular dependencies, and failed commands preserved before reduction.
- `retrieve_result` supports exact, summary, filtered, and sample modes with bounded limits.
- `context_stats` reports tool calls, summarized results, retrievals, estimated raw/returned/avoided tokens, largest summarized results, repeated broad queries, and warnings without sensitive full content.

### Must NOT Have (Guardrails)
- MUST NOT become a generic LLM proxy or compression proxy.
- MUST NOT add Headroom as a runtime dependency or call external network/provider APIs.
- MUST NOT route requests between model providers or depend on Pi/Claude/Codex-specific host behavior.
- MUST NOT lossy-compress source code intended for editing.
- MUST NOT silently drop errors, stack frames, symbol names, file paths, line numbers, diagnostics, permission failures, or failed commands.
- MUST NOT implement post-MVP failure learning, project guidance tools, optional Headroom integration, dashboard UI, or generic historical query UI.
- MUST NOT move business logic into FastMCP/Typer adapters; keep adapters thin.
- MUST NOT edit checked-in fixture repos except through isolated temp copies in tests.

---

## Verification Strategy (MANDATORY)

> **ZERO HUMAN INTERVENTION** - ALL verification is agent-executed. No acceptance criterion may require manual user confirmation.

### Test Decision
- **Infrastructure exists**: YES
- **Automated tests**: Tests-after
- **Framework**: pytest + fastmcp Client + Typer CliRunner + direct SQLite assertions
- **Quality Gates**: `uv run pytest`, `uv run ruff check .`, `uv run ruff format --check .`, `uv run basedpyright`

### QA Policy
Every task MUST include agent-executed QA scenarios. Evidence saved to `.omo/evidence/task-{N}-{scenario-slug}.{ext}`.

---

## Execution Strategy

### Execution Environment Constraint

- **Preferred execution subscription/provider**: Claude Code subscription.
- **Must NOT use**: GitHub Copilot for executing `/start-work` tasks.
- **Executor note**: If `/start-work` prompts for or routes through an agent/provider, select Claude Code-compatible execution. Do not choose GitHub Copilot-backed execution for this plan.

### Parallel Execution Waves

```text
Wave 1 (Foundations, start immediately):
├── 1. Envelope schema and compatibility contract [quick]
├── 2. Preservation rules and token estimator [quick]
├── 3. Storage schema migration [quick]
├── 4. Public surface/docs test planning updates [quick]
└── 5. Test fixtures for symbol/test output [quick]

Wave 2 (Core services, after Wave 1):
├── 6. Stored result repository [unspecified-high]
├── 7. Result store service [unspecified-high]
├── 8. Session event/stat service [unspecified-high]
├── 9. Symbol-search formatter [unspecified-high]
└── 10. Test-output formatter [quick]

Wave 3 (MCP integration, after Wave 2):
├── 11. retrieve_result MCP tool [unspecified-high]
├── 12. context_stats MCP tool [unspecified-high]
├── 13. Integrate symbol/search summarized envelope [deep]
└── 14. Contract/docs/public surface lockstep update [quick]

Wave 4 (Hardening, after Wave 3):
├── 15. Storage and migration edge-case tests [unspecified-high]
├── 16. Security and privacy tests [unspecified-high]
├── 17. End-to-end MCP workflow test [deep]
└── 18. Quality gate cleanup [quick]

Wave FINAL:
├── F1. Plan Compliance Audit (oracle)
├── F2. Code Quality Review (unspecified-high)
├── F3. Real Manual QA (unspecified-high)
└── F4. Scope Fidelity Check (deep)
```

### Dependency Matrix
- **1**: None → 6, 7, 9, 10, 11, 13, 14
- **2**: None → 9, 10, 13, 16
- **3**: None → 6, 8, 15
- **4**: None → 11, 12, 14
- **5**: None → 9, 10, 17
- **6**: 1, 3 → 7, 11, 15
- **7**: 1, 6 → 11, 13, 17
- **8**: 3 → 12, 13, 17
- **9**: 1, 2, 5 → 13, 17
- **10**: 1, 2, 5 → 11, 17
- **11**: 1, 4, 7, 10 → 14, 17
- **12**: 4, 8 → 14, 17
- **13**: 1, 2, 7, 8, 9 → 14, 17
- **14**: 11, 12, 13 → 18
- **15**: 3, 6 → 18
- **16**: 2, 11, 12, 13 → 18
- **17**: 7, 8, 9, 10, 11, 12, 13 → 18
- **18**: 14, 15, 16, 17 → F1-F4

### Agent Dispatch Summary
- **Wave 1**: 5 tasks - all `quick`
- **Wave 2**: 5 tasks - T6-T9 `unspecified-high`, T10 `quick`
- **Wave 3**: 4 tasks - T11-T12 `unspecified-high`, T13 `deep`, T14 `quick`
- **Wave 4**: 4 tasks - T15-T16 `unspecified-high`, T17 `deep`, T18 `quick`
- **FINAL**: 4 review agents in parallel

---

## TODOs

> Implementation + Test = ONE Task. Every task includes Recommended Agent Profile, Parallelization, References, Acceptance Criteria, QA Scenarios, and Commit guidance.

- [x] 1. Envelope schema and compatibility contract

  **What to do**:
  - Define the MVP summarized response envelope contract in service/engine layer, with exact fields: `kind`, `mode`, `summary`, `items`, `omitted_count`, `original_result_id`, `retrieval_available`, `retrieval_hints`, `confidence`, `warnings`, and optional `stats`.
  - Define compatibility policy: existing item schemas remain stable; scoped large responses may add documented envelope metadata only where contract tests/docs are updated in the same wave.
  - Add unit tests for exact/summarized/filtered/sampled/truncated mode serialization.

  **Must NOT do**:
  - Do not wrap every MCP tool globally.
  - Do not add Headroom, network, or LLM summarization hooks.

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: focused schema/model/test work in 1-3 files.
  - **Skills**: []
  - **Skills Evaluated but Omitted**: `security-research` - not a security audit task.

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 with Tasks 2, 3, 4, 5
  - **Blocks**: 6, 7, 9, 10, 11, 13, 14
  - **Blocked By**: None

  **References**:
  - `docs/prd/headroom-influence-prd.md:140-195` - envelope requirements and acceptance criteria.
  - `src/codescent/core/models.py` - existing Pydantic/shared model patterns such as `PageOptions`, `ContextOptions`, `ContextPack`, `SearchResult`.
  - `src/codescent/services/search_support.py` - existing search payload TypedDicts and pagination conventions.
  - `tests/unit/test_models.py` - model validation and boundary test style.
  - `tests/contract/test_mcp_tool_surface.py` - public schema sensitivity and item key assertions.

  **Acceptance Criteria**:
  - [ ] New envelope model/module serializes exact, summarized, filtered, sample, and truncated modes with documented fields.
  - [ ] Unit tests assert required fields and warnings for partial/heuristic results.
  - [ ] Compatibility note exists in code comments or docs-facing contract text.

  **QA Scenarios**:
  ```text
  Scenario: Envelope serializes summarized large result
    Tool: Bash
    Preconditions: Dependencies synced with `uv sync` if needed.
    Steps:
      1. Run `uv run pytest tests/unit/test_models.py -q` plus the new envelope unit test path.
      2. Capture stdout/stderr to `.omo/evidence/task-1-envelope-unit.txt`.
    Expected Result: pytest exits 0; output includes the new summarized envelope tests passing.
    Failure Indicators: missing required envelope fields, non-zero pytest exit, or warnings not represented.
    Evidence: .omo/evidence/task-1-envelope-unit.txt

  Scenario: Invalid partial mode is rejected or warned
    Tool: Bash
    Preconditions: New unit test includes invalid/partial mode case.
    Steps:
      1. Run the new envelope test file with `uv run pytest <new-test-file> -q`.
      2. Confirm the invalid case asserts a validation error or explicit warning field.
    Expected Result: Invalid/partial case is deterministic and test passes.
    Evidence: .omo/evidence/task-1-envelope-invalid.txt
  ```

  **Commit**: YES
  - Message: `feat(context): add summarized envelope contract`
  - Files: model/module + unit tests
  - Pre-commit: `uv run pytest <new-test-file> && uv run ruff check .`

- [x] 2. Preservation rules and token estimator

  **What to do**:
  - Implement deterministic importance-preservation rules before reduction.
  - Add fast local token/size estimate helper with disclosed basis (e.g., character/word approximation) and no external tokenizer dependency.
  - Unit-test priority ordering for errors, tracebacks, failing assertions, public APIs, security findings, highest severity findings, circular dependencies, unreadable files, permission errors, environment errors, and failed commands.

  **Must NOT do**:
  - Do not use an LLM or remote tokenizer.
  - Do not drop exact source ranges when edit context is likely.

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: deterministic helper module plus unit tests.
  - **Skills**: []
  - **Skills Evaluated but Omitted**: `security-research` - preservation includes security findings but not full vuln research.

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 with Tasks 1, 3, 4, 5
  - **Blocks**: 9, 10, 13, 16
  - **Blocked By**: None

  **References**:
  - `docs/prd/headroom-influence-prd.md:451-499` - Always Preserve list and acceptance criteria.
  - `src/codescent/mcp/finding_payloads.py` - finding severity/confidence payload fields.
  - `src/codescent/services/reports.py` - score explanation and finding detail shaping.
  - `src/codescent/core/models.py:ContextPack` - existing `token_estimate` concept.
  - `src/codescent/storage/schema.py` - `chunks.token_estimate` and `files.size_bytes` metadata references.

  **Acceptance Criteria**:
  - [ ] Preservation helper ranks critical items ahead of ordinary items for every MVP content type.
  - [ ] Token estimator returns deterministic integer estimates and records estimate basis.
  - [ ] Unit tests cover empty input, oversized critical input, mixed severity, and non-UTF8-safe string handling.

  **QA Scenarios**:
  ```text
  Scenario: Critical findings are preserved first
    Tool: Bash
    Preconditions: New preservation unit tests exist.
    Steps:
      1. Run `uv run pytest <new-preservation-test-file> -q`.
      2. Verify stdout shows tests for errors, tracebacks, failing assertions, and security findings.
    Expected Result: pytest exits 0 and preserved items appear before low-priority items in assertions.
    Evidence: .omo/evidence/task-2-preservation.txt

  Scenario: Oversized critical item remains retrievable
    Tool: Bash
    Preconditions: Test fixture includes oversized traceback or assertion text.
    Steps:
      1. Run the preservation tests.
      2. Confirm test asserts summary warning plus retrieval-required metadata for oversized critical content.
    Expected Result: Oversized critical content is not silently dropped.
    Evidence: .omo/evidence/task-2-oversized-critical.txt
  ```

  **Commit**: YES
  - Message: `feat(context): add preservation rules`
  - Files: preservation/token helper + tests
  - Pre-commit: `uv run pytest <new-preservation-test-file>`

- [x] 3. Storage schema migration

  **What to do**:
  - Add `stored_results` and `session_events` tables to `src/codescent/storage/schema.py`.
  - Bump `SCHEMA_VERSION` from 4 to 5 and add migration from v4.
  - Include fields from PRD: result ID, repo/project identifier, session ID, tool name, input JSON, raw result JSON, summary JSON, content type, raw/returned token estimates, timestamps, expiration, retrieval count; event ID, event type, tool name, result ID, payload JSON, timestamp.
  - Ensure fresh init and migration are idempotent.

  **Must NOT do**:
  - Do not store data outside `.codescent`.
  - Do not store full source in `session_events.payload_json` unless explicit debug mode exists; MVP has no debug mode.

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: focused schema/migration work with tests.
  - **Skills**: []
  - **Skills Evaluated but Omitted**: `sbh` - no disk pressure issue is present.

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 with Tasks 1, 2, 4, 5
  - **Blocks**: 6, 8, 15
  - **Blocked By**: None

  **References**:
  - `docs/prd/headroom-influence-prd.md:198-267` - local result store requirements.
  - `docs/prd/headroom-influence-prd.md:567-623` - session event log shape and requirements.
  - `docs/prd/headroom-influence-prd.md:942-993` - data model sketch.
  - `src/codescent/storage/schema.py` - canonical schema/migration location.
  - `tests/integration/test_storage.py` - fresh init/idempotency tests.
  - `tests/integration/test_storage_migrations.py` and `tests/fixtures/storage/mvp_v2_schema.sql` - migration test patterns.

  **Acceptance Criteria**:
  - [ ] Fresh `initialize_storage()` creates both new tables.
  - [ ] v4 database migrates to v5 without losing existing tables/data.
  - [ ] Re-running initialization leaves schema stable.
  - [ ] Reset remains `.codescent` scoped.

  **QA Scenarios**:
  ```text
  Scenario: Fresh storage includes context tables
    Tool: Bash
    Preconditions: Schema task implemented.
    Steps:
      1. Run `uv run pytest tests/integration/test_storage.py -q`.
      2. Capture sqlite table assertion output.
    Expected Result: pytest exits 0; new tests confirm `stored_results` and `session_events` exist.
    Evidence: .omo/evidence/task-3-fresh-storage.txt

  Scenario: v4 migration creates new tables without data loss
    Tool: Bash
    Preconditions: Migration test fixture or setup creates v4 DB.
    Steps:
      1. Run `uv run pytest tests/integration/test_storage_migrations.py -q`.
      2. Confirm tests assert schema version 5 and preserved legacy rows.
    Expected Result: Migration succeeds idempotently.
    Evidence: .omo/evidence/task-3-v4-migration.txt
  ```

  **Commit**: YES
  - Message: `feat(storage): add context result tables`
  - Files: `src/codescent/storage/schema.py`, storage tests/fixtures
  - Pre-commit: `uv run pytest tests/integration/test_storage.py tests/integration/test_storage_migrations.py`

- [x] 4. Public surface/docs test planning updates

  **What to do**:
  - Prepare public surface changes for `retrieve_result` and `context_stats`: names, stage, registered status, docs placeholders, and contract-test expectations.
  - Update docs/changelog tests only as needed so future names are no longer treated as forbidden once implemented.
  - Keep changes synchronized with actual tool registration in Task 14; if this task runs first, use TODO comments/tests skipped only if existing project style permits, otherwise keep as a planning branch note for Task 14.

  **Must NOT do**:
  - Do not register tools before implementation exists.
  - Do not add post-MVP tools (`project_guidance`, `project_learnings`, `record_agent_failure`, `record_successful_recovery`).

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: public registry/docs/test boundary preparation.
  - **Skills**: []
  - **Skills Evaluated but Omitted**: `writing` - technical docs are small and tied to tests.

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 with Tasks 1, 2, 3, 5
  - **Blocks**: 11, 12, 14
  - **Blocked By**: None

  **References**:
  - `src/codescent/core/public_surface.py` - canonical public surface registry.
  - `src/codescent/mcp/server.py` - registration order.
  - `docs/mcp-tools.md` - required human-facing contract docs.
  - `tests/docs/test_docs.py` - docs sync and forbidden future-name rules.
  - `tests/contract/test_public_surface_registry.py` and `tests/contract/test_mcp_tool_surface.py` - public registry/tool surface assertions.

  **Acceptance Criteria**:
  - [ ] Plan-compatible registry/docs strategy is documented in changed tests/docs or deferred explicitly to Task 14.
  - [ ] No post-MVP tool names become registered.
  - [ ] Existing public surface tests still pass if this task lands before Task 14.

  **QA Scenarios**:
  ```text
  Scenario: Public surface remains coherent before tool registration
    Tool: Bash
    Preconditions: Any preparatory public-surface updates are made.
    Steps:
      1. Run `uv run pytest tests/contract/test_public_surface_registry.py tests/docs/test_docs.py -q`.
      2. Capture output.
    Expected Result: Tests pass; no implemented/non-implemented mismatch.
    Evidence: .omo/evidence/task-4-public-surface-prep.txt

  Scenario: Post-MVP tools remain excluded
    Tool: Bash
    Preconditions: Registry/docs tests include exclusions.
    Steps:
      1. Search via test assertions or run docs tests.
      2. Confirm `project_guidance`, `project_learnings`, and optional Headroom tools are not registered.
    Expected Result: Only MVP tools are in scope.
    Evidence: .omo/evidence/task-4-post-mvp-excluded.txt
  ```

  **Commit**: NO
  - Message: group with Task 14 if no standalone passing state exists
  - Files: public surface/docs/tests
  - Pre-commit: `uv run pytest tests/contract/test_public_surface_registry.py tests/docs/test_docs.py`

- [x] 5. Test fixtures for symbol and test output shaping

  **What to do**:
  - Add deterministic test fixtures or inline fixture builders for large symbol-like results and large pytest-like output.
  - Include empty result, large exact match set, mixed definition/reference results, failing assertion, traceback root cause, environmental failure, non-UTF8-safe text, and very long single-line output.
  - Use temp repos or pure fixture strings; do not mutate checked-in fixture source.

  **Must NOT do**:
  - Do not run real integration tests requiring Docker/network.
  - Do not edit `tests/fixtures/python-basic` source as part of fixture setup.

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: test fixture setup only.
  - **Skills**: []
  - **Skills Evaluated but Omitted**: `debugging` - no runtime bug investigation.

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 with Tasks 1, 2, 3, 4
  - **Blocks**: 9, 10, 17
  - **Blocked By**: None

  **References**:
  - `tests/AGENTS.md` - test layout and fixture rules.
  - `tests/fixtures/python-basic` - analyzed repo fixture conventions; use read-only.
  - `tests/integration/test_search.py` - search result fixture/test style.
  - `tests/integration/test_context.py` - context result expectations.
  - `docs/prd/headroom-influence-prd.md:344-448` - result type shaping requirements.

  **Acceptance Criteria**:
  - [ ] Fixtures/builders cover symbol search and test output MVP cases.
  - [ ] Fixtures are deterministic and local-only.
  - [ ] New tests using fixtures fail before formatter implementation and pass after Tasks 9-10.

  **QA Scenarios**:
  ```text
  Scenario: Symbol fixture produces deterministic large result
    Tool: Bash
    Preconditions: Fixture builder exists.
    Steps:
      1. Run `uv run pytest <new-fixture-test-file> -q`.
      2. Confirm fixture size and ordering assertions pass.
    Expected Result: Deterministic symbol fixture with definitions/references/exact/partial examples.
    Evidence: .omo/evidence/task-5-symbol-fixture.txt

  Scenario: Test-output fixture preserves failure data
    Tool: Bash
    Preconditions: Pytest-output fixture exists.
    Steps:
      1. Run fixture tests.
      2. Confirm failing test name, assertion line, traceback root cause, command, and environmental error examples are present.
    Expected Result: Fixture supports formatter preservation tests.
    Evidence: .omo/evidence/task-5-test-output-fixture.txt
  ```

  **Commit**: YES
  - Message: `test(context): add shaping fixtures`
  - Files: tests fixture/helper files
  - Pre-commit: `uv run pytest <new-fixture-test-file>`

- [x] 6. Stored result repository

  **What to do**:
  - Add repository module under `src/codescent/storage/repositories/` for `stored_results` CRUD and retrieval-count updates.
  - Support create, get by ID, expire/cleanup, increment retrieval count, and list largest/recent summarized results for stats.
  - Use `RepositoryStorage.write_transaction()` / read patterns consistent with existing repositories.

  **Must NOT do**:
  - Do not put SQLite logic in MCP tools.
  - Do not expose absolute sensitive paths in summary fields if path redaction is later enabled.

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
    - Reason: persistence layer with edge cases and integration tests.
  - **Skills**: []
  - **Skills Evaluated but Omitted**: `security-research` - privacy is covered by tests, no audit requested.

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2 with Tasks 7, 8, 9, 10 after Wave 1
  - **Blocks**: 7, 11, 15
  - **Blocked By**: 1, 3

  **References**:
  - `src/codescent/storage/repositories/findings.py` - repository class and event persistence pattern.
  - `src/codescent/storage/repository.py` - storage state, transactions, concurrency guard.
  - `src/codescent/services/search_support.py` - serializable payload patterns.
  - `tests/integration/test_findings.py` - repository lifecycle persistence tests.
  - `tests/integration/test_storage_concurrency.py` - concurrency expectations.

  **Acceptance Criteria**:
  - [ ] Repository stores and retrieves full raw JSON and summary JSON by `ctx_<short_hash>` ID.
  - [ ] Unknown/expired IDs return deterministic not-found/expired results at service layer.
  - [ ] Cleanup removes expired rows without touching unrelated tables.
  - [ ] Retrieval count increments transactionally.

  **QA Scenarios**:
  ```text
  Scenario: Repository round-trips stored result
    Tool: Bash
    Preconditions: Repository tests exist.
    Steps:
      1. Run `uv run pytest <new-result-repository-test-file> -q`.
      2. Confirm stored raw JSON, summary JSON, token estimates, and retrieval count assertions pass.
    Expected Result: Full result survives SQLite round trip.
    Evidence: .omo/evidence/task-6-repository-roundtrip.txt

  Scenario: Expired result is cleaned up
    Tool: Bash
    Preconditions: Expiry test exists.
    Steps:
      1. Run repository tests.
      2. Confirm expired row retrieval fails deterministically and cleanup removes it.
    Expected Result: Expired data is unavailable and cleanup is scoped.
    Evidence: .omo/evidence/task-6-expiry-cleanup.txt
  ```

  **Commit**: YES
  - Message: `feat(storage): add stored result repository`
  - Files: repository module + integration tests
  - Pre-commit: `uv run pytest <new-result-repository-test-file>`

- [x] 7. Result store service

  **What to do**:
  - Add service layer for storing summarized full results, generating opaque stable IDs, retrieving exact/summary/filtered/sample modes, applying limits, and building retrieval hints.
  - Define collision handling for `ctx_<short_hash>` IDs and deterministic errors for missing/expired IDs.
  - Ensure restart persistence by reinitializing service against existing `.codescent/index.sqlite`.

  **Must NOT do**:
  - Do not make `retrieve_result` a broad history search over all stored results.
  - Do not rerun expensive searches when exact stored content exists.

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
    - Reason: service API plus filtering/limits/error semantics.
  - **Skills**: []
  - **Skills Evaluated but Omitted**: `debugging` - implementation, not bug triage.

  **Parallelization**:
  - **Can Run In Parallel**: YES, after Task 6 API is available or coordinated with it
  - **Parallel Group**: Wave 2 with Tasks 6, 8, 9, 10
  - **Blocks**: 11, 13, 17
  - **Blocked By**: 1, 6

  **References**:
  - `docs/prd/headroom-influence-prd.md:270-341` - `retrieve_result` parameters/modes/requirements.
  - `src/codescent/services/context.py` - service-layer pattern with bounded payloads.
  - `src/codescent/services/search.py` - service API and result payload construction.
  - `src/codescent/storage/repository.py` - storage initialization.
  - `tests/integration/test_storage.py` - restart/idempotency style.

  **Acceptance Criteria**:
  - [ ] Service returns exact stored content for exact mode subject to explicit limit safety.
  - [ ] Service supports filtering by query, file, symbol, and result type where fields exist in stored payload.
  - [ ] Service marks partial results with remaining/omitted counts and warnings.
  - [ ] Missing, expired, and invalid IDs have deterministic parseable error shapes.

  **QA Scenarios**:
  ```text
  Scenario: Exact retrieval survives service restart
    Tool: Bash
    Preconditions: Service integration test uses tmp_path repo.
    Steps:
      1. Run `uv run pytest <new-result-service-test-file> -q`.
      2. Confirm test stores result, recreates service/storage, and retrieves exact content by ID.
    Expected Result: Exact result persists across process/service recreation.
    Evidence: .omo/evidence/task-7-restart-retrieval.txt

  Scenario: Missing result ID returns deterministic error
    Tool: Bash
    Preconditions: Error-path test exists.
    Steps:
      1. Run service tests.
      2. Confirm `ctx_missing` response has documented error code/message and no traceback leak.
    Expected Result: Missing ID is handled gracefully.
    Evidence: .omo/evidence/task-7-missing-id.txt
  ```

  **Commit**: YES
  - Message: `feat(context): add result store service`
  - Files: service module + integration tests
  - Pre-commit: `uv run pytest <new-result-service-test-file>`

- [x] 8. Session event and stats service

  **What to do**:
  - Add service/repository support for local-only session events: `tool_called`, `large_result_summarized`, `result_retrieved`, `agent_repeated_query`, `agent_requested_exact_large_result`, `server_warning_returned`.
  - Aggregate basic `context_stats` from stored results and events.
  - Track repeated broad queries by normalized tool/input fingerprint without storing sensitive full source content in event payloads.

  **Must NOT do**:
  - Do not implement failure learning or project guidance.
  - Do not transmit telemetry externally.

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
    - Reason: service aggregation and privacy-sensitive event persistence.
  - **Skills**: []
  - **Skills Evaluated but Omitted**: `security-research` - privacy assertions are local tests, not adversarial audit.

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2 with Tasks 6, 7, 9, 10
  - **Blocks**: 12, 13, 17
  - **Blocked By**: 3

  **References**:
  - `docs/prd/headroom-influence-prd.md:502-564` - `context_stats` requirements.
  - `docs/prd/headroom-influence-prd.md:567-623` - event log requirements.
  - `src/codescent/services/search_support.py:record_frecency` - existing persisted signal example.
  - `src/codescent/storage/schema.py:telemetry` - local event-style table pattern.
  - `tests/security/test_runtime_safety.py` - no-network/local-only safety style.

  **Acceptance Criteria**:
  - [ ] Stats include tool calls, summarized results, retrievals, estimated raw/returned/avoided tokens, largest summarized results, most-used tools, repeated broad queries, and warnings.
  - [ ] Empty project/session returns bounded zero-valued stats.
  - [ ] Event payloads omit full source/raw result content.
  - [ ] Event writes are local-only and reset-compatible.

  **QA Scenarios**:
  ```text
  Scenario: Stats aggregate stored events
    Tool: Bash
    Preconditions: Stats service tests exist.
    Steps:
      1. Run `uv run pytest <new-stats-service-test-file> -q`.
      2. Confirm fixture events produce expected counts and token estimates.
    Expected Result: Aggregated stats match deterministic fixture values.
    Evidence: .omo/evidence/task-8-stats-aggregate.txt

  Scenario: Event payload avoids full source leakage
    Tool: Bash
    Preconditions: Privacy test inserts event for source-like content.
    Steps:
      1. Run stats/privacy tests.
      2. Confirm persisted `payload_json` contains fingerprints/metrics but not the full source string `SECRET_SOURCE_SENTINEL`.
    Expected Result: Sensitive content sentinel is absent from event payloads.
    Evidence: .omo/evidence/task-8-event-privacy.txt
  ```

  **Commit**: YES
  - Message: `feat(context): add context stats service`
  - Files: event/stats services + tests
  - Pre-commit: `uv run pytest <new-stats-service-test-file>`

- [x] 9. Symbol-search formatter

  **What to do**:
  - Implement deterministic formatter for symbol-search-like results using existing `find_symbol`/search payload data.
  - Group by exact/partial match, definition/reference when available, file/module, symbol type, and relevance.
  - Preserve symbol name, kind, file path, line/range, and rank/reason; store full original when summarized.

  **Must NOT do**:
  - Do not invent semantic classifications not present in payloads without warning.
  - Do not lose cursor/pagination behavior.

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
    - Reason: content-specific shaping plus contract-sensitive integration.
  - **Skills**: []
  - **Skills Evaluated but Omitted**: `frontend-ui-ux` - no UI work.

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2 with Tasks 6, 7, 8, 10
  - **Blocks**: 13, 17
  - **Blocked By**: 1, 2, 5

  **References**:
  - `docs/prd/headroom-influence-prd.md:361-371` - symbol search grouping requirements.
  - `src/codescent/services/context.py:find_symbol` - symbol lookup service path.
  - `src/codescent/services/context_support.py` - context payload schemas and caps.
  - `src/codescent/mcp/context_tools.py` - MCP symbol/context tool wrappers.
  - `tests/contract/test_mcp_context_tools.py` and `tests/integration/test_context.py` - symbol/context JSON expectations.

  **Acceptance Criteria**:
  - [ ] Formatter produces compact grouped response for large symbol result fixture.
  - [ ] Exact matches and definitions appear before partial/less relevant items where data supports it.
  - [ ] Omitted counts and retrieval hints are correct.
  - [ ] Empty symbol results produce exact empty envelope without result storage.

  **QA Scenarios**:
  ```text
  Scenario: Large symbol results are grouped and bounded
    Tool: Bash
    Preconditions: Symbol formatter and tests exist.
    Steps:
      1. Run `uv run pytest <new-symbol-formatter-test-file> -q`.
      2. Confirm grouped exact/partial/file/type output and omitted count assertions pass.
    Expected Result: Large symbol result returns compact deterministic envelope.
    Evidence: .omo/evidence/task-9-symbol-grouping.txt

  Scenario: Empty symbol result remains exact
    Tool: Bash
    Preconditions: Empty result test exists.
    Steps:
      1. Run symbol formatter tests.
      2. Confirm empty result has `mode="exact"`, no misleading omitted count, and no stored result ID.
    Expected Result: Empty results are clear and not over-summarized.
    Evidence: .omo/evidence/task-9-empty-symbol.txt
  ```

  **Commit**: YES
  - Message: `feat(context): shape symbol results`
  - Files: formatter module + tests
  - Pre-commit: `uv run pytest <new-symbol-formatter-test-file>`

- [x] 10. Test-output formatter

  **What to do**:
  - Implement deterministic formatter for pytest/test-output strings or structured test-output payloads.
  - Preserve failed test names, assertion messages, traceback root cause, relevant file paths/line numbers, rerun command, and deterministic/environmental classification when possible.
  - Summarize passing/noisy output more aggressively than failures and expose retrieval metadata for exact output.

  **Must NOT do**:
  - Do not execute tests from this formatter.
  - Do not hide failing assertions behind prose-only summaries.

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: deterministic parser/formatter with fixture tests.
  - **Skills**: []
  - **Skills Evaluated but Omitted**: `debugging` - formatter implementation, not live failure triage.

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2 with Tasks 6, 7, 8, 9
  - **Blocks**: 11, 17
  - **Blocked By**: 1, 2, 5

  **References**:
  - `docs/prd/headroom-influence-prd.md:383-393` - test output shaping requirements.
  - `tests/fixtures/python-basic` - local Python project fixture for realistic paths.
  - `tests/evals/test_deterministic_eval.py` - deterministic command output style.
  - `scripts/prove_source_read_only.py` - evidence-output convention.
  - `tests/security/test_runtime_safety.py` - command-safety test style.

  **Acceptance Criteria**:
  - [ ] Formatter handles passing output, failing assertions, traceback-heavy output, environmental failures, empty output, non-UTF8-safe replacement, and very long lines.
  - [ ] Failing assertions and test names are always preserved before truncation.
  - [ ] Output includes rerun command when provided.
  - [ ] Exact original is available via result store when summarized.

  **QA Scenarios**:
  ```text
  Scenario: Failing pytest output preserves assertion
    Tool: Bash
    Preconditions: Test-output formatter tests exist.
    Steps:
      1. Run `uv run pytest <new-test-output-formatter-test-file> -q`.
      2. Confirm failing test name, assertion text, file path, and line number assertions pass.
    Expected Result: Failure details survive summarization.
    Evidence: .omo/evidence/task-10-pytest-failure.txt

  Scenario: Very long passing output is compacted
    Tool: Bash
    Preconditions: Long-output fixture exists.
    Steps:
      1. Run formatter tests.
      2. Confirm passing noise is summarized with omitted count and retrieval metadata.
    Expected Result: Long passing output is bounded and retrievable.
    Evidence: .omo/evidence/task-10-long-passing-output.txt
  ```

  **Commit**: YES
  - Message: `feat(context): shape test output`
  - Files: formatter + tests
  - Pre-commit: `uv run pytest <new-test-output-formatter-test-file>`

- [x] 11. retrieve_result MCP tool

  **What to do**:
  - Add `retrieve_result` MCP tool with parameters `result_id`, optional `query`, `file`, `symbol`, `limit`, and `mode` (`exact`, `summary`, `filtered`, `sample`).
  - Route through result store service; return parseable response with `kind="retrieved_result"`, `result_id`, `mode`, `summary`, `items`, `remaining_count`, and `warnings`.
  - Record `result_retrieved` and exact-large retrieval events.

  **Must NOT do**:
  - Do not allow filesystem path reads outside the stored result.
  - Do not rerun broad searches to satisfy retrieval.

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
    - Reason: new public MCP tool with contract/security tests.
  - **Skills**: []
  - **Skills Evaluated but Omitted**: `security-research` - targeted security tests suffice.

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 3 with Tasks 12, 13, 14 after Wave 2
  - **Blocks**: 14, 17
  - **Blocked By**: 1, 4, 7, 10

  **References**:
  - `docs/prd/headroom-influence-prd.md:270-341` - tool spec and modes.
  - `src/codescent/mcp/server.py` - MCP registration.
  - `src/codescent/mcp/search_tools.py` and `src/codescent/mcp/context_tools.py` - FastMCP tool wrapper style.
  - `tests/contract/test_mcp_tool_surface.py` - tool surface assertions.
  - `tests/contract/test_mcp_context_tools.py` - MCP JSON parse/contract style.

  **Acceptance Criteria**:
  - [ ] Tool is registered exactly once and documented.
  - [ ] Exact, summary, filtered, and sample modes are contract-tested.
  - [ ] Missing/expired/invalid result IDs return deterministic error JSON without traceback leakage.
  - [ ] Limit prevents huge follow-up responses.

  **QA Scenarios**:
  ```text
  Scenario: retrieve_result returns filtered test-related items
    Tool: Bash
    Preconditions: MCP contract test seeds stored result.
    Steps:
      1. Run `uv run pytest tests/contract/test_mcp_tool_surface.py <new-retrieve-result-contract-test> -q`.
      2. Confirm response includes `kind`, `result_id`, `mode="filtered"`, bounded `items`, and `remaining_count`.
    Expected Result: MCP client retrieves filtered stored data without rerunning search.
    Evidence: .omo/evidence/task-11-retrieve-filtered.txt

  Scenario: retrieve_result handles unknown ID
    Tool: Bash
    Preconditions: Contract error test exists.
    Steps:
      1. Run retrieve_result contract tests.
      2. Confirm `ctx_doesnotexist` returns documented error/warning and no Python traceback.
    Expected Result: Unknown ID produces clear deterministic error.
    Evidence: .omo/evidence/task-11-retrieve-missing.txt
  ```

  **Commit**: YES
  - Message: `feat(mcp): add retrieve_result tool`
  - Files: MCP tool module/registration + contract tests
  - Pre-commit: `uv run pytest tests/contract/test_mcp_tool_surface.py <new-retrieve-result-contract-test>`

- [x] 12. context_stats MCP tool

  **What to do**:
  - Add `context_stats` MCP tool backed by stats service.
  - Return bounded stats with `session_id`, `tool_calls`, `summarized_results`, `retrievals`, `estimated_raw_tokens`, `estimated_returned_tokens`, `estimated_tokens_avoided`, `largest_summarized_results`, `most_used_tools`, repeated-query indicators, and `warnings`.
  - Ensure stats avoid sensitive raw content.

  **Must NOT do**:
  - Do not include raw source or full query payloads in stats.
  - Do not require a live agent session host.

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
    - Reason: new public MCP tool plus aggregation contract.
  - **Skills**: []
  - **Skills Evaluated but Omitted**: `frontend-ui-ux` - no dashboard UI.

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 3 with Tasks 11, 13, 14
  - **Blocks**: 14, 17
  - **Blocked By**: 4, 8

  **References**:
  - `docs/prd/headroom-influence-prd.md:502-564` - stats tool requirements and response shape.
  - `src/codescent/mcp/repo_tools.py` - simple MCP reporting tool style.
  - `src/codescent/services/search_support.py` - persisted frecency signal example.
  - `tests/contract/test_mcp_repo_tools.py` - bounded MCP report contract patterns.
  - `tests/security/test_runtime_safety.py` - no-network/source-read-only assertions.

  **Acceptance Criteria**:
  - [ ] Tool is registered exactly once and documented.
  - [ ] Empty stats return zero counts and empty arrays without failure.
  - [ ] Seeded stats return deterministic counts/estimates.
  - [ ] Response contains no full source/content sentinel strings.

  **QA Scenarios**:
  ```text
  Scenario: context_stats returns bounded metrics
    Tool: Bash
    Preconditions: MCP stats contract test seeds events/results.
    Steps:
      1. Run `uv run pytest <new-context-stats-contract-test> -q`.
      2. Confirm counts and token estimates match seeded data.
    Expected Result: context_stats returns parseable bounded JSON metrics.
    Evidence: .omo/evidence/task-12-stats-contract.txt

  Scenario: context_stats handles empty state
    Tool: Bash
    Preconditions: Empty tmp_path repo test exists.
    Steps:
      1. Run stats contract tests.
      2. Confirm empty state returns zeros and no exception.
    Expected Result: Empty stats are safe and useful.
    Evidence: .omo/evidence/task-12-empty-stats.txt
  ```

  **Commit**: YES
  - Message: `feat(mcp): add context_stats tool`
  - Files: MCP tool + contract tests
  - Pre-commit: `uv run pytest <new-context-stats-contract-test>`

- [x] 13. Integrate symbol/search summarized envelope

  **What to do**:
  - Apply summarized envelope/result-store path to the existing high-volume symbol/search surface selected from current CodeScent tools (`find_symbol`/related symbol context or the closest existing symbol-search equivalent).
  - Store raw full result when output exceeds configured threshold; return compact grouped summary with `original_result_id` and retrieval hints.
  - Record tool-called and large-result-summarized events.
  - Preserve existing public contract expectations or update them intentionally with docs in Task 14.

  **Must NOT do**:
  - Do not apply envelopes to all tools immediately.
  - Do not break exact source-range retrieval for edit contexts.

  **Recommended Agent Profile**:
  - **Category**: `deep`
    - Reason: cross-cutting integration across services, MCP adapter, storage, and public contracts.
  - **Skills**: []
  - **Skills Evaluated but Omitted**: `debugging` - no observed bug.

  **Parallelization**:
  - **Can Run In Parallel**: YES, with coordination on public docs/tests
  - **Parallel Group**: Wave 3 with Tasks 11, 12, 14
  - **Blocks**: 14, 17
  - **Blocked By**: 1, 2, 7, 8, 9

  **References**:
  - `docs/prd/headroom-influence-prd.md:73-82` - compressed/summary + retrieval ID pattern.
  - `src/codescent/services/context.py:find_symbol` - likely symbol result source.
  - `src/codescent/mcp/context_tools.py` - MCP-facing symbol/context adapter.
  - `src/codescent/services/search.py` and `src/codescent/mcp/search_tools.py` - search payload and adapter patterns.
  - `tests/contract/test_mcp_context_tools.py` and `tests/contract/test_mcp_search_tools.py` - contract tests to update/add.

  **Acceptance Criteria**:
  - [ ] Large symbol/search response returns summarized envelope with stored original result ID.
  - [ ] Small response remains exact or clearly marked exact.
  - [ ] Retrieval hints include `retrieve_result(result_id='ctx_...')` and filtered examples.
  - [ ] Existing cursor/limit behavior remains tested.

  **QA Scenarios**:
  ```text
  Scenario: Large symbol search returns retrievable summary
    Tool: Bash
    Preconditions: MCP/integration test can trigger large symbol result.
    Steps:
      1. Run `uv run pytest tests/contract/test_mcp_context_tools.py tests/contract/test_mcp_search_tools.py -q`.
      2. Confirm new test asserts `mode="summarized"`, `original_result_id` starts with `ctx_`, and omitted count is positive.
    Expected Result: Large result is compact and retrievable.
    Evidence: .omo/evidence/task-13-large-symbol-summary.txt

  Scenario: Small symbol search remains exact
    Tool: Bash
    Preconditions: Existing small symbol fixture remains.
    Steps:
      1. Run context/search contract tests.
      2. Confirm small result has exact mode or unchanged exact fields and no misleading omission warning.
    Expected Result: Compatibility is preserved for small results.
    Evidence: .omo/evidence/task-13-small-symbol-exact.txt
  ```

  **Commit**: YES
  - Message: `feat(mcp): summarize symbol search results`
  - Files: service/MCP integration + contract tests
  - Pre-commit: `uv run pytest tests/contract/test_mcp_context_tools.py tests/contract/test_mcp_search_tools.py`

- [x] 14. Contract/docs/public surface lockstep update

  **What to do**:
  - Update `src/codescent/core/public_surface.py`, `src/codescent/mcp/server.py`, `docs/mcp-tools.md`, contract tests, and docs tests so `retrieve_result`, `context_stats`, and any shaped response changes are documented and registered consistently.
  - Remove `retrieve_result`/`context_stats` from any future-forbidden docs/changelog assertions as appropriate after implementation.
  - Document bounds, example shapes, modes, warnings, and privacy rules.

  **Must NOT do**:
  - Do not register post-MVP tools.
  - Do not leave docs claiming old unbounded behavior for summarized tools.

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: lockstep docs/registry/test updates.
  - **Skills**: []
  - **Skills Evaluated but Omitted**: `writing` - concise public contract docs only.

  **Parallelization**:
  - **Can Run In Parallel**: YES with Tasks 11-13, but final assertions depend on them
  - **Parallel Group**: Wave 3 with Tasks 11, 12, 13
  - **Blocks**: 18
  - **Blocked By**: 11, 12, 13

  **References**:
  - `src/codescent/core/public_surface.py` - registered tool names.
  - `src/codescent/mcp/server.py` - registration order.
  - `docs/mcp-tools.md` - public tool documentation.
  - `tests/docs/test_docs.py` - docs requirements per tool.
  - `scripts/audit_plan_compliance.py` - registry/docs audit behavior.

  **Acceptance Criteria**:
  - [ ] Public surface registry includes `retrieve_result` and `context_stats` exactly once as registered MVP tools.
  - [ ] `docs/mcp-tools.md` includes required sections for both tools and shaped response bounds.
  - [ ] `tests/docs/test_docs.py`, `tests/contract/test_public_surface_registry.py`, and `tests/contract/test_mcp_tool_surface.py` pass.

  **QA Scenarios**:
  ```text
  Scenario: Public surface and docs are synchronized
    Tool: Bash
    Preconditions: New tools implemented and documented.
    Steps:
      1. Run `uv run pytest tests/docs/test_docs.py tests/contract/test_public_surface_registry.py tests/contract/test_mcp_tool_surface.py -q`.
      2. Capture output.
    Expected Result: Docs and registry contract pass with new tools.
    Evidence: .omo/evidence/task-14-docs-surface.txt

  Scenario: No post-MVP tools are exposed
    Tool: Bash
    Preconditions: Public surface tests cover exclusions.
    Steps:
      1. Run public surface tests.
      2. Confirm `project_guidance`, `project_learnings`, `compress_generic_output`, and `retrieve_original_output` are absent from registered tools.
    Expected Result: MVP scope remains locked.
    Evidence: .omo/evidence/task-14-post-mvp-absent.txt
  ```

  **Commit**: YES
  - Message: `docs(mcp): document context optimization tools`
  - Files: public surface, server, docs, contract/docs tests
  - Pre-commit: `uv run pytest tests/docs/test_docs.py tests/contract/test_public_surface_registry.py tests/contract/test_mcp_tool_surface.py`

- [x] 15. Storage and migration edge-case tests

  **What to do**:
  - Add/extend tests for fresh init, v4→v5 migration, idempotent init, restart retrieval, cleanup, TTL expiry, concurrent writes, interrupted/rolled-back transactions, oversized payloads, and reset behavior.
  - Ensure reset removes stored results/events by deleting `.codescent` only.

  **Must NOT do**:
  - Do not require manual database inspection.
  - Do not leave flaky timing-dependent TTL tests; use fixed timestamps/injected clock if needed.

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
    - Reason: integration edge-case coverage across storage layers.
  - **Skills**: []
  - **Skills Evaluated but Omitted**: `debugging` - proactive test hardening.

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 4 with Tasks 16, 17, 18
  - **Blocks**: 18
  - **Blocked By**: 3, 6

  **References**:
  - `tests/integration/test_storage.py` - init/idempotency.
  - `tests/integration/test_storage_migrations.py` - migration patterns.
  - `tests/integration/test_storage_concurrency.py` - concurrent behavior.
  - `tests/contract/test_cli.py` - reset safety.
  - `src/codescent/cli/admin.py` - reset implementation.

  **Acceptance Criteria**:
  - [ ] Storage edge-case tests pass deterministically.
  - [ ] Reset deletes new tables by removing `.codescent` and does not touch source.
  - [ ] Concurrent writes either serialize or return documented concurrency error without corruption.

  **QA Scenarios**:
  ```text
  Scenario: Storage edge-case suite passes
    Tool: Bash
    Preconditions: Edge-case tests are implemented.
    Steps:
      1. Run `uv run pytest tests/integration/test_storage.py tests/integration/test_storage_migrations.py tests/integration/test_storage_concurrency.py -q`.
      2. Capture output.
    Expected Result: All storage edge cases pass without flakiness.
    Evidence: .omo/evidence/task-15-storage-edge-cases.txt

  Scenario: reset remains source-read-only
    Tool: Bash
    Preconditions: CLI reset test covers result store state.
    Steps:
      1. Run `uv run pytest tests/contract/test_cli.py -q`.
      2. Confirm reset removes `.codescent` state and leaves source fixtures unchanged.
    Expected Result: Reset is scoped to `.codescent`.
    Evidence: .omo/evidence/task-15-reset-scope.txt
  ```

  **Commit**: YES
  - Message: `test(storage): cover context result edge cases`
  - Files: storage/CLI tests
  - Pre-commit: `uv run pytest tests/integration/test_storage.py tests/integration/test_storage_migrations.py tests/integration/test_storage_concurrency.py tests/contract/test_cli.py`

- [x] 16. Security and privacy tests

  **What to do**:
  - Add security tests proving no network calls, no source mutation, no full-source event payload leakage, no path traversal through `retrieve_result(file=...)`, and no traceback leakage for invalid IDs.
  - Include sensitive sentinel strings in raw results and verify they are stored only where expected and not surfaced in stats/events summaries.

  **Must NOT do**:
  - Do not use real secrets.
  - Do not connect to network or install extra tools.

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
    - Reason: security/privacy regression suite across new public tools.
  - **Skills**: []
  - **Skills Evaluated but Omitted**: `security-research` - targeted tests, not full vulnerability audit.

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 4 with Tasks 15, 17, 18
  - **Blocks**: 18
  - **Blocked By**: 2, 11, 12, 13

  **References**:
  - `docs/prd/headroom-influence-prd.md:997-1020` - safety/correctness requirements.
  - `tests/security/test_runtime_safety.py` - security test style.
  - `scripts/prove_source_read_only.py` - source read-only proof pattern.
  - `src/codescent/engine/inventory.py` - `.codescent` exclusion from indexing.
  - `src/codescent/services/context_support.py` - path/range bounded context patterns.

  **Acceptance Criteria**:
  - [ ] Security tests prove no runtime network for new features.
  - [ ] `retrieve_result` cannot path-traverse outside stored result content.
  - [ ] `context_stats` and events do not expose full source/sensitive sentinel content.
  - [ ] Source-read-only proof still passes.

  **QA Scenarios**:
  ```text
  Scenario: New context tools do not mutate source or call network
    Tool: Bash
    Preconditions: Security tests updated.
    Steps:
      1. Run `uv run pytest tests/security/test_runtime_safety.py -q`.
      2. Capture output.
    Expected Result: Security tests pass for no-network and source-read-only behavior.
    Evidence: .omo/evidence/task-16-security-runtime.txt

  Scenario: Stats do not leak source sentinel
    Tool: Bash
    Preconditions: Sentinel privacy test exists.
    Steps:
      1. Run the security/privacy test.
      2. Confirm response JSON for `context_stats` omits `SECRET_SOURCE_SENTINEL`.
    Expected Result: Sensitive raw content is absent from stats/events summaries.
    Evidence: .omo/evidence/task-16-no-sentinel-leak.txt
  ```

  **Commit**: YES
  - Message: `test(security): protect context result privacy`
  - Files: security tests + any supporting fixtures
  - Pre-commit: `uv run pytest tests/security/test_runtime_safety.py`

- [x] 17. End-to-end MCP workflow test

  **What to do**:
  - Add an MCP end-to-end test using `fastmcp.Client`: trigger a large summarized symbol/search response, capture `original_result_id`, call `retrieve_result` with filtered mode, then call `context_stats` and assert stats reflect the workflow.
  - Include negative path for missing ID and empty state.

  **Must NOT do**:
  - Do not rely on external MCP clients or Pi.
  - Do not require manual server process management; use in-process FastMCP test pattern.

  **Recommended Agent Profile**:
  - **Category**: `deep`
    - Reason: cross-tool integration and public behavior proof.
  - **Skills**: []
  - **Skills Evaluated but Omitted**: `playwright` - no browser UI.

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 4 with Tasks 15, 16, 18
  - **Blocks**: 18
  - **Blocked By**: 7, 8, 9, 10, 11, 12, 13

  **References**:
  - `tests/contract/test_mcp_tool_surface.py` - `fastmcp.Client` tool invocation style.
  - `tests/contract/test_mcp_search_tools.py` - search MCP contract style.
  - `tests/contract/test_mcp_context_tools.py` - context MCP contract style.
  - `docs/prd/headroom-influence-prd.md:1044-1069` - example before/after agent flow.
  - `src/codescent/mcp/server.py` - in-process MCP app.

  **Acceptance Criteria**:
  - [ ] E2E test proves summarize → retrieve filtered → stats workflow.
  - [ ] Evidence includes actual MCP JSON responses with bounded payloads.
  - [ ] Missing ID and empty stats are covered.

  **QA Scenarios**:
  ```text
  Scenario: MCP summarize-retrieve-stats flow works
    Tool: Bash
    Preconditions: E2E contract test exists.
    Steps:
      1. Run `uv run pytest <new-mcp-context-optimization-e2e-test> -q`.
      2. Confirm test extracts `ctx_...`, retrieves filtered results, and sees retrieval count in stats.
    Expected Result: End-to-end MCP workflow passes without external server.
    Evidence: .omo/evidence/task-17-mcp-e2e.txt

  Scenario: E2E negative paths are deterministic
    Tool: Bash
    Preconditions: Missing-ID and empty-state cases exist in E2E file.
    Steps:
      1. Run E2E tests.
      2. Confirm missing ID returns documented error and empty stats returns zeros.
    Expected Result: Negative paths are parseable and stable.
    Evidence: .omo/evidence/task-17-mcp-negative.txt
  ```

  **Commit**: YES
  - Message: `test(mcp): cover context optimization workflow`
  - Files: MCP E2E contract test
  - Pre-commit: `uv run pytest <new-mcp-context-optimization-e2e-test>`

- [x] 18. Quality gate cleanup

  **What to do**:
  - Run and fix issues from full project gates: pytest, ruff check, ruff format check, basedpyright.
  - Ensure evidence files from tasks exist.
  - Ensure no fixture repos were unintentionally modified and `.codescent` runtime state is not committed.

  **Must NOT do**:
  - Do not weaken tests or public contracts to pass gates.
  - Do not commit `.codescent`, `.omo/evidence`, caches, or generated runtime state unless project explicitly tracks them.

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: final gate execution and small cleanups.
  - **Skills**: []
  - **Skills Evaluated but Omitted**: `git-master` - no commit requested by user here; executor may use if committing.

  **Parallelization**:
  - **Can Run In Parallel**: YES after Wave 4 tasks land, but gate fixes may be sequential.
  - **Parallel Group**: Wave 4 with Tasks 15, 16, 17
  - **Blocks**: F1-F4
  - **Blocked By**: 14, 15, 16, 17

  **References**:
  - `AGENTS.md` - canonical project commands.
  - `pyproject.toml` - pytest/ruff/basedpyright config.
  - `tests/AGENTS.md` - fixture and test conventions.
  - `.gitignore` - runtime state ignore rules.
  - `docs/prd/headroom-influence-prd.md:1023-1041` - success metrics.

  **Acceptance Criteria**:
  - [ ] `uv run pytest` passes.
  - [ ] `uv run ruff check .` passes.
  - [ ] `uv run ruff format --check .` passes.
  - [ ] `uv run basedpyright` passes.
  - [ ] No unintended fixture/runtime files are staged.

  **QA Scenarios**:
  ```text
  Scenario: Full project quality gates pass
    Tool: Bash
    Preconditions: All implementation tasks complete.
    Steps:
      1. Run `uv run pytest`.
      2. Run `uv run ruff check .`.
      3. Run `uv run ruff format --check .`.
      4. Run `uv run basedpyright`.
    Expected Result: All commands exit 0.
    Evidence: .omo/evidence/task-18-quality-gates.txt

  Scenario: Runtime artifacts are not included
    Tool: Bash
    Preconditions: Quality gates complete.
    Steps:
      1. Run `git status --short`.
      2. Confirm changed files are only intentional source/docs/tests and no `.codescent`, caches, or fixture runtime state are present.
    Expected Result: Working tree changes are intentional and reviewable.
    Evidence: .omo/evidence/task-18-git-status.txt
  ```

  **Commit**: YES
  - Message: `chore(context): finalize context optimization gates`
  - Files: final cleanup only
  - Pre-commit: `uv run pytest && uv run ruff check . && uv run ruff format --check . && uv run basedpyright`

---

## Final Verification Wave (MANDATORY — after ALL implementation tasks)

> 4 review agents run in PARALLEL. ALL must APPROVE. Present consolidated results to the user as a handoff artifact. User acknowledgement, if requested by the executor, is outside the automated verification Definition of Done.

- [x] F1. **Plan Compliance Audit** — `oracle`
  Read the plan end-to-end. For each Must Have, verify implementation exists by reading files and running targeted tests. For each Must NOT Have, search for forbidden patterns: Headroom dependency, network calls, provider routing, post-MVP tools, lossy source compression. Check evidence files exist in `.omo/evidence/`.
  Output: `Must Have [N/N] | Must NOT Have [N/N] | Tasks [N/N] | VERDICT: APPROVE/REJECT`

- [x] F2. **Code Quality Review** — `unspecified-high`
  Run `uv run pytest`, `uv run ruff check .`, `uv run ruff format --check .`, and `uv run basedpyright`. Review changed files for broad adapter logic, `Any` misuse, swallowed exceptions, unbounded payloads, source leakage, and AI slop.
  Output: `Build [PASS/FAIL] | Lint [PASS/FAIL] | Tests [N pass/N fail] | Files [N clean/N issues] | VERDICT`

- [x] F3. **Real Manual QA** — `unspecified-high`
  Execute every task QA scenario exactly, using Bash and FastMCP/pytest evidence. Validate summarize → retrieve → stats workflow, missing/expired IDs, empty state, storage reset, and security/privacy cases. Save consolidated evidence to `.omo/evidence/final-qa/`.
  Output: `Scenarios [N/N pass] | Integration [N/N] | Edge Cases [N tested] | VERDICT`

- [x] F4. **Scope Fidelity Check** — `deep`
  Compare actual diff to PRD MVP and this plan. Verify post-MVP features are absent, Headroom is not a dependency, docs reflect only implemented behavior, and no unrelated tools were globally wrapped.
  Output: `Tasks [N/N compliant] | Contamination [CLEAN/N issues] | Unaccounted [CLEAN/N files] | VERDICT`

---

## Commit Strategy

- **Wave 1**: `feat(context): define context optimization foundations` - envelope, preservation, schema, fixtures, targeted tests.
- **Wave 2**: `feat(context): add result store and formatters` - repositories, services, symbol/test formatters.
- **Wave 3**: `feat(mcp): expose context retrieval and stats` - MCP tools, symbol integration, public docs/contracts.
- **Wave 4**: `test(context): harden context optimization workflow` - edge/security/E2E tests and quality fixes.

---

## Success Criteria

### Verification Commands
```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run basedpyright
uv run pytest tests/contract/test_mcp_tool_surface.py tests/docs/test_docs.py
uv run pytest tests/security/test_runtime_safety.py
```

### Final Checklist
- [ ] PRD MVP features 1-7 are implemented.
- [ ] Post-MVP features are not implemented or registered.
- [ ] Large symbol/search output is summarized and retrievable.
- [ ] Test output shaping preserves failures/assertions.
- [ ] Stored results expire/cleanup correctly and survive restart before expiry.
- [ ] `retrieve_result` and `context_stats` are registered, documented, and contract-tested.
- [ ] No runtime network, Headroom dependency, provider routing, or lossy source edit compression exists.
- [ ] All final verification agents approve; any later user acknowledgement is outside automated verification.
