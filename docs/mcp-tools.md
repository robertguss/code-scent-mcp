# CodeScent MCP Tools

CodeScent registers MCP tools in `codescent.core.public_surface`. The MCP server
is local stdio and source-read-only for analyzed source. Tools may write or
update `.codescent/` state for indexes, scan runs, findings, lifecycle events,
result storage, and telemetry.

Every tool should return bounded output by default. Inputs are the tool
arguments supplied by the MCP client. Outputs are structured payloads validated
by the service and contract tests.

## Current Registered MCP Tools

- `get_repo_map`
- `get_repo_status`
- `search_files`
- `search_content`
- `find_symbol`
- `get_file_context`
- `get_symbol_context`
- `scan_code_health`
- `get_smell_report`
- `get_finding_context`
- `get_next_improvement`
- `plan_refactor`
- `suggest_tests`
- `mark_finding`
- `rescan`

## Registered Post-MVP MCP Tools

- `multi_search_content`
- `search_changed_files`
- `search_todos`
- `search_tests`
- `find_references`
- `find_callers`
- `find_callees`
- `get_related_files`
- `get_impact`
- `verify_change`
- `verify_refactor`
- `get_finding`
- `explain_score`
- `explain_finding`
- `get_backlog`
- `get_improvement_plan`
- `get_calibration`
- `get_progress`
- `get_regressions`
- `review_diff_risk`
- `get_changed_file_health`
- `retrieve_result`
- `context_stats`
- `select_tests`
- `refactor_preflight`
- `subjective_review`
- `start_task`
- `record_verification`
- `how_to_use`
- `resume_task`

## Locked Post-MVP MCP Tools

No MCP tools are locked in the current local PRD-remainder stage. Task 14
remains the final docs/public lockstep check for Headroom MCP tools.

## Current Registered CLI Commands

- `init`
- `serve`
- `index`
- `scan`
- `status`
- `doctor`
- `report`
- `reset`
- `watch`
- `findings`
- `next`
- `explain`
- `export`
- `config`
- `rules`
- `ci`
- `review-diff`

## Locked Post-MVP CLI Commands

No CLI commands are locked in the current local PRD-remainder stage.

## Tool Groups

Repository tools:

`get_repo_map`, `get_repo_status`, `start_task`

Search and context tools:

`search_files`, `search_content`, `find_symbol`, `get_file_context`,
`get_symbol_context`, `find_references`, `find_callers`, `find_callees`,
`get_related_files`, `retrieve_result`

Code health and finding lifecycle tools:

`scan_code_health`, `get_smell_report`, `get_next_improvement`, `mark_finding`,
`record_verification`, `rescan`, `get_finding`, `explain_score`, `get_backlog`,
`get_improvement_plan`, `get_calibration`, `get_progress`, `get_regressions`,
`context_stats`

Planning tools:

`get_finding_context`, `plan_refactor`, `suggest_tests`, `get_impact`,
`verify_change`, `verify_refactor`, `select_tests`, `refactor_preflight`

Risk tools:

`review_diff_risk`, `get_changed_file_health`

Guidance tools:

`how_to_use`

All tools are local and source-read-only for analyzed source. Tools may create
or update `.codescent` state for indexing, scan runs, findings, lifecycle
events, and telemetry.

## Tool Reference

### `get_repo_map`

- Group: `repository`
- Purpose: Return a compact repository map for orientation.
- Inputs: repository root plus tool-specific arguments such as query, path,
  symbol, finding id, status, or limit.
- Outputs: JSON-compatible structured payload with local evidence and no
  unbounded source dump.
- Bounds: source-read-only for analyzed files; bounded output by default;
  runtime no-network.
- Example shape: `{"tool": "scan_code_health", "ok": true, "data": {...}}`
  `next_tools` so agents know how much to trust the miss and what to try next.
- Bounds: source-read-only for analyzed files; bounded output by default;
  runtime no-network.
- Example shape: `{"tool": "get_repo_map", "ok": true, "data": {...}}`

### `get_repo_status`

- Group: `repository`
- Purpose: Report index, finding, database, and git status.
- Inputs: repository root plus tool-specific arguments such as query, path,
  symbol, finding id, status, or limit.
- Outputs: JSON-compatible structured payload with local evidence and no
  unbounded source dump.
- Bounds: source-read-only for analyzed files; bounded output by default;
  runtime no-network.
- Example shape: `{"tool": "get_repo_status", "ok": true, "data": {...}}`

### `start_task`

- Group: `repository`
- Purpose: Return a bounded deterministic task brief for a natural-language task
  plus optional focus path or focus symbol.
- Inputs: repository root, required `query`, optional `focus_path`, and optional
  `focus_symbol`.
- Outputs: `query`, `relevant_files`, `relevant_symbols`, `related_tests`,
  `open_findings`, `index_fresh`, `index_was_stale`, `auto_refreshed`,
  `changed_files`, `refresh_error`, `warnings`, `confidence`, and `next_tools`.
- Bounds: source-read-only for analyzed files; bounded output by default;
  runtime no-network; no raw source dumps. If the index is stale, `start_task`
  refreshes `.codescent` state before answering and reports that refresh in the
  advisory fields.
- Example shape: `{"tool": "start_task", "ok": true, "data": {...}}`

### `resume_task`

- Group: `repository`
- Purpose: Reconstruct a bounded "where was I, what's next" session brief after
  context loss (e.g. a compaction), purely from persisted state. The mirror of
  `start_task` for continuing in-flight work rather than starting fresh.
- Inputs: repository root, optional `session_id` (enriches the recent tool
  trail), and optional `project_id`.
- Outputs: `status`, `summary`, `active_findings` (the in-flight/last findings),
  `verified_findings` (what the verification ledger shows passing),
  `recently_touched_files`, `recent_tools`, `ratchet` (baseline accepted state
  and finding count), and `next_tools` (the recommended next call derived from
  the top active finding plus the ledger).
- Bounds: source-read-only for analyzed files; reads no analyzed source at all;
  deterministic; bounded output by default; runtime no-network. All lists are
  capped. Reconstructed entirely from findings, the verification ledger, the
  ratchet baseline, and sanitized session events; adds no new storage. Session
  events are sanitized, so the active finding and touched files come from the
  findings/ledger tables, not from event payloads.
- Example shape:
  `{"ok": true, "status": "in_progress", "active_findings": [...], "next_tools": [...]}`

### `search_files`

- Group: `search`
- Purpose: Find files by ranked path query.
- Inputs: repository root plus tool-specific arguments such as query, path,
  symbol, finding id, status, or limit.
- Outputs: JSON-compatible structured payload with local evidence and no
  unbounded source dump. Empty results include `warnings`, `confidence`, and
  `next_tools` so agents know how much to trust the miss and what to try next.
- Bounds: source-read-only for analyzed files; bounded output by default;
  runtime no-network.
- Example shape: `{"tool": "search_files", "ok": true, "data": {...}}`

### `search_content`

- Group: `search`
- Purpose: Find bounded content matches by query.
- Inputs: repository root plus tool-specific arguments such as query, path,
  symbol, finding id, status, or limit.
- Outputs: JSON-compatible structured payload with local evidence and no
  unbounded source dump. Empty results include `warnings`, `confidence`, and
  `next_tools` so agents know how much to trust the miss and what to try next.
- Bounds: source-read-only for analyzed files; bounded output by default;
  runtime no-network.
- Example shape: `{"tool": "search_content", "ok": true, "data": {...}}`

### `find_symbol`

- Group: `context`
- Purpose: Find indexed symbols by name and return a bounded symbol-search
  envelope.
- Inputs: repository root, query, and limit. Large responses may include `mode`,
  `original_result_id`, `omitted_count`, `retrieval_available`,
  `retrieval_hints`, `warnings`, and `stats`.
- Outputs: JSON-compatible structured payload with local evidence and no
  unbounded source dump. The payload also includes `index_fresh`,
  `index_was_stale`, `auto_refreshed`, `changed_files`, `refresh_error`,
  `confidence`, and `next_tools`.
- Bounds: source-read-only for analyzed files; bounded output by default;
  `find_symbol` envelopes large results instead of returning unbounded symbol
  lists; runtime no-network. If the index is stale, `find_symbol` refreshes
  `.codescent` state before answering.
- Example shape:
  `{"ok": true, "kind": "symbol_search", "mode": "exact", "items": []}`

### `get_file_context`

- Group: `context`
- Purpose: Return bounded context for one file.
- Inputs: repository root plus tool-specific arguments such as query, path,
  symbol, finding id, status, or limit.
- Outputs: JSON-compatible structured payload with local evidence and no
  unbounded source dump. Index-backed context tools include `index_fresh`,
  `index_was_stale`, `auto_refreshed`, `changed_files`, `refresh_error`,
  `warnings`, `confidence`, and `next_tools`.
- Bounds: source-read-only for analyzed files; bounded output by default;
  runtime no-network. If the index is stale, the tool refreshes `.codescent`
  state before answering.
- Example shape: `{"tool": "get_file_context", "ok": true, "data": {...}}`

### `get_symbol_context`

- Group: `context`
- Purpose: Return bounded context for one symbol.
- Inputs: repository root plus tool-specific arguments such as query, path,
  symbol, finding id, status, or limit.
- Outputs: JSON-compatible structured payload with local evidence and no
  unbounded source dump. Index-backed context tools include `index_fresh`,
  `index_was_stale`, `auto_refreshed`, `changed_files`, `refresh_error`,
  `warnings`, and `confidence`.
- Bounds: source-read-only for analyzed files; bounded output by default;
  runtime no-network. If the index is stale, the tool refreshes `.codescent`
  state before answering.
- Example shape: `{"tool": "get_symbol_context", "ok": true, "data": {...}}`

### `scan_code_health`

- Group: `health`
- Purpose: Run deterministic code-health scanning.
- Inputs: repository root plus tool-specific arguments such as query, path,
  symbol, finding id, status, or limit.
- Outputs: a bounded scan envelope with aggregate counts (`total_count`,
  `severity_counts`, `rule_counts`, `rule_ids`), a capped `finding_ids`/`items`
  preview, and `returned_count`/`omitted_count`. Each item carries a
  `confidence_tier` (`verified` for AST-resolved Python findings anchored to a
  symbol, `heuristic` for regex/TS-pack or file-level findings) and a small
  `provenance` object (`rule_id`, `language`, `resolution` = `ast`|`regex`,
  `symbol_resolved`). Tier and provenance are deterministically derived metadata,
  not part of a finding's stable identity.
- Bounds: source-read-only for analyzed files; bounded output by default;
  runtime no-network. The inline preview holds at most `INLINE_ITEM_LIMIT`
  (default 25) items; when findings are omitted the envelope carries a
  `result_id` with `retrieval_available` and `retrieval_hints` so the full set
  is reachable via `retrieve_result`. It never dumps every finding id inline.
- Example shape:
  `{"ok": true, "kind": "scan", "total_count": 1270, "rule_counts": {...}, "items": [...], "omitted_count": 1245, "result_id": "ctx_…", "retrieval_available": true}`

### `get_smell_report`

- Group: `health`
- Purpose: Return summarized open finding report data.
- Inputs: repository root plus tool-specific arguments such as query, path,
  symbol, finding id, status, or limit.
- Outputs: a bounded list envelope: `open_count`, `total_count`,
  `status_counts`, `severity_counts`, `rule_counts`, and a capped `items`
  preview with `returned_count`/`omitted_count`. Each item carries
  `confidence_tier` and a bounded `provenance` object (see `scan_code_health`).
- Bounds: source-read-only for analyzed files; bounded output by default;
  runtime no-network. The inline preview holds at most `INLINE_ITEM_LIMIT`
  (default 25) findings; when findings are omitted the envelope carries a
  `result_id` with `retrieval_available` and `retrieval_hints` so the full
  report is reachable via `retrieve_result`. It does not return every finding
  inline.
- Example shape:
  `{"ok": true, "kind": "smell_report", "open_count": 1270, "total_count": 1270, "items": [...], "omitted_count": 1245, "result_id": "ctx_…", "retrieval_available": true}`

### `get_finding_context`

- Group: `planning`
- Purpose: Return evidence and bounded context for a finding.
- Inputs: repository root plus tool-specific arguments such as query, path,
  symbol, finding id, status, or limit.
- Outputs: JSON-compatible structured payload with local evidence and no
  unbounded source dump. Index-backed graph tools include `index_fresh`,
  `index_was_stale`, `auto_refreshed`, `changed_files`, `refresh_error`,
  `warnings`, `confidence`, and `next_tools`.
- Bounds: source-read-only for analyzed files; bounded output by default;
  runtime no-network. If the index is stale, the tool refreshes `.codescent`
  state before answering.
- Example shape: `{"tool": "get_finding_context", "ok": true, "data": {...}}`

### `explain_finding`

- Group: `planning`
- Purpose: Return one bounded, fix-ready explanation of a finding: why it
  matters (`why` message + structured `evidence`), the suggested `fix`
  (`suggested_action`), confidence tier/provenance, and a bounded source
  `snippet` anchored at the finding's lines.
- Inputs: repository root plus the finding id.
- Outputs: JSON-compatible structured payload with local evidence and a bounded
  source snippet (`snippet.source`); no unbounded source dump. Carries
  `confidence_tier`, `provenance`, `snippet_truncated`, and `next_tools`.
- Bounds: source-read-only for analyzed files; the snippet is clipped to a line
  cap and a character cap (and dropped for files beyond the source-read byte
  budget) so output stays bounded by default; runtime no-network.
- Example shape: `{"tool": "explain_finding", "ok": true, "data": {...}}`

### `subjective_review`

- Group: `health`
- Purpose: Opt-in subjective second opinion on deterministic findings. CodeScent
  asks the **client's own LLM** to judge findings via MCP **sampling** and
  returns the model's notes as findings that are explicitly labeled subjective
  (`confidence_tier: "subjective"`, `provenance: "subjective"`). They are
  persisted separately and never merge into or masquerade as deterministic
  findings.
- Inputs: repository root only. There is no per-call enable flag — the feature is
  gated solely by `privacy.allow_llm_review` (default `false`).
- Outputs: JSON payload with `enabled`, `sampling_available`, `provider`, a
  status `message`, a `privacy_notice`, and the labeled `subjective_findings`.
- Data exposure (PRD 14.5): when enabled, the sampling prompt carries **only**
  finding metadata (rule id, file path, severity, title, message) — never whole
  source files — and that metadata is run through a secret/PII scrub before the
  request leaves. The **CodeScent server makes no network call**: the sampling
  request travels back through the MCP session and the client's model produces
  the judgment.
- Bounds: source-read-only for analyzed files; disabled by default (clean no-op);
  degrades gracefully to a clear "sampling unavailable" result when the client
  cannot sample; bounded output. The CodeScent process itself performs no
  runtime network I/O.
- Example shape: `{"tool": "subjective_review", "ok": true, "data": {...}}`

### `get_next_improvement`

- Group: `health`
- Purpose: Return the next recommended finding to address.
- Inputs: repository root plus tool-specific arguments such as query, path,
  symbol, finding id, status, or limit.
- Outputs: JSON-compatible structured payload with local evidence and no
  unbounded source dump. Index-backed graph tools include `index_fresh`,
  `index_was_stale`, `auto_refreshed`, `changed_files`, `refresh_error`,
  `warnings`, `confidence`, and `next_tools`.
- Bounds: source-read-only for analyzed files; bounded output by default;
  runtime no-network. If the index is stale, the tool refreshes `.codescent`
  state before answering.
- Example shape: `{"tool": "get_next_improvement", "ok": true, "data": {...}}`

### `plan_refactor`

- Group: `planning`
- Purpose: Return a safe refactor plan for a finding.
- Inputs: repository root plus tool-specific arguments such as query, path,
  symbol, finding id, status, or limit.
- Outputs: JSON-compatible structured payload with local evidence and no
  unbounded source dump. Index-backed related-file results include
  `index_fresh`, `index_was_stale`, `auto_refreshed`, `changed_files`,
  `refresh_error`, `warnings`, `confidence`, and `next_tools`.
- Bounds: source-read-only for analyzed files; bounded output by default;
  runtime no-network. If the index is stale, the tool refreshes `.codescent`
  state before answering.
- Example shape: `{"tool": "plan_refactor", "ok": true, "data": {...}}`

### `suggest_tests`

- Group: `planning`
- Purpose: Recommend verification commands for a finding or change, and
  optionally emit an honest characterization-test skeleton.
- Inputs: repository root, a finding id, and an optional `scaffold` flag
  (default `false`).
- Outputs: JSON-compatible structured payload with local evidence and no
  unbounded source dump (`commands`, `likely_tests`, `executes_in_v1`). When
  `scaffold=true`, an opt-in `scaffold` object is added with `language`,
  `module`, `symbol`, `test_name`, `filename`, `code`, `honest`, and `notes`.
- Scaffold honesty: the generated `code` imports the finding's target and leaves
  TODO placeholders that `raise NotImplementedError` — it collects under pytest
  but never reports a fake-green pass, so it must be filled in to pin current
  behavior before refactoring. The field is omitted unless `scaffold=true`.
- Bounds: source-read-only for analyzed files; bounded output by default
  (one short skeleton, single test function); runtime no-network.
- Example shape: `{"tool": "suggest_tests", "ok": true, "data": {...}}`

### `select_tests`

- Group: `planning`
- Purpose: Recommend the minimal pytest test set for current changes or given
  paths.
- Inputs: repository root plus optional changed paths.
- Outputs: `changed_files`, `test_files`, a single `command`, and
  `executes_in_v1: false`.
- Bounds: source-read-only for analyzed files; bounded output by default;
  runtime no-network; recommend-only and does not execute pytest.
- Example shape: `{"tool": "select_tests", "ok": true, "data": {...}}`

### `refactor_preflight`

- Group: `planning`
- Purpose: Run a one-call refactor preflight before editing: a bounded, deduped
  blast-radius bundle for a file, symbol, or finding that an agent would
  otherwise have to assemble by chaining four tools. Pure composition of
  already-shipped analyses — `get_impact` (callers/refs), git co-change
  coupling, `select_tests` (the minimal verification set), and
  `get_changed_file_health`. No new analysis is invented; each section equals
  what its component tool returns when called directly.
- Inputs: repository root, plus one of `target` (file path or symbol name with
  `target_type` of `file` or `symbol`) or `finding_id`.
- Outputs: `ok`, `target_type`, `target`, `file_path`, `impact` (same shape as
  `get_impact`), `co_change` (a capped list of `{path, commits}` coupling
  entries), `test_selection` (same shape as `select_tests`),
  `changed_file_health` (same shape as `get_changed_file_health`), `warnings`,
  and `next_tools`.
- Bounds: source-read-only for analyzed files; bounded output by default;
  runtime no-network. Every list section honors the most restrictive existing
  component cap (git co-change tops out at 10) and no section carries source
  ranges. Missing inputs (no shared git history, an unindexed target) degrade to
  an empty section with a reason in `warnings` rather than failing.
- Example shape:
  `{"ok": true, "file_path": "src/pkg/core.py", "impact": {...}, "co_change": [{"path": "src/pkg/caller.py", "commits": 2}], "test_selection": {...}, "changed_file_health": {...}, "warnings": [], "next_tools": [...]}`

### `mark_finding`

- Group: `health`
- Purpose: Record finding lifecycle status after external evidence. Requested
  `resolved` status is evidence-gated: without a passing verification record or
  clean rescan evidence, CodeScent stores `needs_review` and reports that the
  request was gated.
- Inputs: repository root plus tool-specific arguments such as query, path,
  symbol, finding id, status, or limit.
- Outputs: JSON-compatible structured payload with local evidence and no
  unbounded source dump.
- Bounds: source-read-only for analyzed files; bounded output by default;
  runtime no-network.
- Example shape: `{"tool": "mark_finding", "ok": true, "data": {...}}`

### `record_verification`

- Group: `health`
- Purpose: Record the result of a verification command that the caller already
  ran for a finding. CodeScent stores the caller-supplied command, exit code,
  and bounded output summary; it never executes commands.
- Inputs: repository root, finding id, command, exit code, and short output
  summary.
- Outputs: JSON-compatible structured payload with the verification row id,
  status code, bounded summary, and truncation signal.
- Bounds: source-read-only for analyzed files; writes only `.codescent` ledger
  state; bounded output by default; runtime no-network; no command execution.
- Example shape: `{"tool": "record_verification", "ok": true, "data": {...}}`

### `rescan`

- Group: `health`
- Purpose: Run scan again and report resolved or regressed findings.
- Inputs: repository root plus tool-specific arguments such as query, path,
  symbol, finding id, status, or limit.
- Outputs: a bounded scan envelope (same shape as `scan_code_health`) plus
  `regressed_finding_ids` (capped) and `regressed_count`.
- Bounds: source-read-only for analyzed files; bounded output by default;
  runtime no-network. The inline preview holds at most `INLINE_ITEM_LIMIT`
  (default 25) items; when findings are omitted the envelope carries a
  `result_id` with `retrieval_available` and `retrieval_hints` for
  `retrieve_result`.
- Example shape:
  `{"ok": true, "kind": "rescan", "total_count": 1270, "items": [...], "omitted_count": 1245, "regressed_count": 2, "result_id": "ctx_…", "retrieval_available": true}`

### `multi_search_content`

- Group: `search`
- Purpose: Run multiple bounded content queries together.
- Inputs: repository root plus tool-specific arguments such as query, path,
  symbol, finding id, status, or limit.
- Outputs: JSON-compatible structured payload with local evidence and no
  unbounded source dump. Empty results include `warnings`, `confidence`, and
  `next_tools` so agents know how much to trust the miss and what to try next.
- Bounds: source-read-only for analyzed files; bounded output by default;
  runtime no-network.
- Example shape: `{"tool": "multi_search_content", "ok": true, "data": {...}}`

### `search_changed_files`

- Group: `search`
- Purpose: Rank files changed in git status or diff context.
- Inputs: repository root plus tool-specific arguments such as query, path,
  symbol, finding id, status, or limit.
- Outputs: JSON-compatible structured payload with local evidence and no
  unbounded source dump.
- Bounds: source-read-only for analyzed files; bounded output by default;
  runtime no-network.
- Example shape: `{"tool": "search_changed_files", "ok": true, "data": {...}}`

### `search_todos`

- Group: `search`
- Purpose: Find TODO/FIXME/HACK style comments.
- Inputs: repository root plus tool-specific arguments such as query, path,
  symbol, finding id, status, or limit.
- Outputs: JSON-compatible structured payload with local evidence and no
  unbounded source dump. Empty results include `warnings`, `confidence`, and
  `next_tools` so agents know how much to trust the miss and what to try next.
- Bounds: source-read-only for analyzed files; bounded output by default;
  runtime no-network.
- Example shape: `{"tool": "search_todos", "ok": true, "data": {...}}`

### `search_tests`

- Group: `search`
- Purpose: Find likely relevant tests.
- Inputs: repository root plus tool-specific arguments such as query, path,
  symbol, finding id, status, or limit.
- Outputs: JSON-compatible structured payload with local evidence and no
  unbounded source dump. Empty results include `warnings`, `confidence`, and
  `next_tools` so agents know how much to trust the miss and what to try next.
- Bounds: source-read-only for analyzed files; bounded output by default;
  runtime no-network.
- Example shape: `{"tool": "search_tests", "ok": true, "data": {...}}`

### `find_references`

- Group: `context`
- Purpose: Return indexed references for a symbol or path.
- Inputs: repository root plus tool-specific arguments such as query, path,
  symbol, finding id, status, or limit.
- Outputs: JSON-compatible structured payload with local evidence and no
  unbounded source dump. Index-backed graph tools include `index_fresh`,
  `index_was_stale`, `auto_refreshed`, `changed_files`, `refresh_error`,
  `warnings`, `confidence`, and `next_tools`.
- Bounds: source-read-only for analyzed files; bounded output by default;
  runtime no-network. If the index is stale, the tool refreshes `.codescent`
  state before answering.
- Example shape: `{"tool": "find_references", "ok": true, "data": {...}}`

### `find_callers`

- Group: `context`
- Purpose: Return callers for an indexed callable.
- Inputs: repository root plus tool-specific arguments such as query, path,
  symbol, finding id, status, or limit.
- Outputs: JSON-compatible structured payload with local evidence and no
  unbounded source dump. Index-backed graph tools include `index_fresh`,
  `index_was_stale`, `auto_refreshed`, `changed_files`, `refresh_error`,
  `warnings`, `confidence`, and `next_tools`.
- Bounds: source-read-only for analyzed files; bounded output by default;
  runtime no-network. If the index is stale, the tool refreshes `.codescent`
  state before answering.
- Example shape: `{"tool": "find_callers", "ok": true, "data": {...}}`

### `find_callees`

- Group: `context`
- Purpose: Return callees from an indexed callable.
- Inputs: repository root plus tool-specific arguments such as query, path,
  symbol, finding id, status, or limit.
- Outputs: JSON-compatible structured payload with local evidence and no
  unbounded source dump. Index-backed graph tools include `index_fresh`,
  `index_was_stale`, `auto_refreshed`, `changed_files`, `refresh_error`,
  `warnings`, `confidence`, and `next_tools`.
- Bounds: source-read-only for analyzed files; bounded output by default;
  runtime no-network. If the index is stale, the tool refreshes `.codescent`
  state before answering.
- Example shape: `{"tool": "find_callees", "ok": true, "data": {...}}`

### `get_related_files`

- Group: `context`
- Purpose: Return related implementation, test, and config files.
- Inputs: repository root plus tool-specific arguments such as query, path,
  symbol, finding id, status, or limit.
- Outputs: JSON-compatible structured payload with local evidence and no
  unbounded source dump. Index-backed related-file results include
  `index_fresh`, `index_was_stale`, `auto_refreshed`, `changed_files`,
  `refresh_error`, `warnings`, `confidence`, and `next_tools`.
- Bounds: source-read-only for analyzed files; bounded output by default;
  runtime no-network. If the index is stale, the tool refreshes `.codescent`
  state before answering.
- Example shape: `{"tool": "get_related_files", "ok": true, "data": {...}}`

### `get_impact`

- Group: `planning`
- Purpose: Summarize likely blast radius for a path or symbol.
- Inputs: repository root plus tool-specific arguments such as query, path,
  symbol, finding id, status, or limit.
- Outputs: JSON-compatible structured payload with local evidence and no
  unbounded source dump.
- Bounds: source-read-only for analyzed files; bounded output by default;
  runtime no-network.
- Example shape: `{"tool": "get_impact", "ok": true, "data": {...}}`

### `get_finding`

- Group: `health`
- Purpose: Return one finding by id.
- Inputs: repository root plus tool-specific arguments such as query, path,
  symbol, finding id, status, or limit.
- Outputs: JSON-compatible structured payload with local evidence and no
  unbounded source dump.
- Bounds: source-read-only for analyzed files; bounded output by default;
  runtime no-network.
- Example shape: `{"tool": "get_finding", "ok": true, "data": {...}}`

### `explain_score`

- Group: `health`
- Purpose: Explain deterministic score inputs and ranking reasons.
- Inputs: repository root plus tool-specific arguments such as query, path,
  symbol, finding id, status, or limit.
- Outputs: JSON-compatible structured payload with local evidence and no
  unbounded source dump.
- Bounds: source-read-only for analyzed files; bounded output by default;
  runtime no-network.
- Example shape: `{"tool": "explain_score", "ok": true, "data": {...}}`

### `verify_change`

- Group: `planning`
- Purpose: Record a recommend-only verification plan.
- Inputs: repository root plus tool-specific arguments such as query, path,
  symbol, finding id, status, or limit.
- Outputs: JSON-compatible structured payload with local evidence and no
  unbounded source dump.
- Bounds: source-read-only for analyzed files; bounded output by default;
  runtime no-network.
- Example shape: `{"tool": "verify_change", "ok": true, "data": {...}}`

### `verify_refactor`

- Group: `planning`
- Purpose: Deterministically check that an edit preserved a Python file's public
  surface. It compares the file's working-tree state against a git ref (default
  `HEAD`) and proves — without LLM judgment — that the set of exported symbols
  and their signatures is unchanged and that no net-new control-flow branches
  slipped in. When it cannot prove safety it reports concrete violations rather
  than blessing a risky change.
- Inputs: repository root, required `path`, optional `base_ref` (default
  `HEAD`), optional `transform_kind` (default `generic`).
- Outputs: `verifiable` (bool — `preserved` is only meaningful when true; false
  for unsupported languages or an unreadable/unparseable state), `preserved`
  (bool), `violations` (each with `kind`, `symbol`, `detail` — `removed_symbol`
  and `signature_changed` are blocking), `warnings` (added public symbols,
  net-new branches), `added_symbols`, `removed_symbols`, `changed_symbols`,
  `language`, `base_ref`, `transform_kind`, and `confidence`. Signatures track
  parameter names, order, kind, and default presence.
- Bounds: source-read-only for analyzed files; both before/after states are read
  read-only (working tree on disk, baseline via `git show`) and compared in
  memory; bounded output by default; runtime no-network. Python (`.py`/`.pyi`)
  in v1; other languages return an unsupported note. Deterministic given the two
  states.
- Example shape:
  `{"tool": "verify_refactor", "ok": true, "preserved": false, "violations": [{"kind": "signature_changed", "symbol": "load_config", "detail": "(path) -> str -> (path, strict) -> str"}], "removed_symbols": [], "changed_symbols": ["load_config"]}`

### `get_backlog`

- Group: `health`
- Purpose: Return backlog-style finding summary.
- Inputs: repository root plus tool-specific arguments such as query, path,
  symbol, finding id, status, or limit.
- Outputs: a bounded list envelope: `open_count`, `total_count`,
  `status_counts`, `severity_counts`, `rule_counts`, and a capped `items`
  preview with `returned_count`/`omitted_count`.
- Bounds: source-read-only for analyzed files; bounded output by default;
  runtime no-network. The inline preview holds at most `INLINE_ITEM_LIMIT`
  (default 25) findings; when findings are omitted the envelope carries a
  `result_id` with `retrieval_available` and `retrieval_hints` for
  `retrieve_result`.
- Example shape:
  `{"ok": true, "kind": "backlog", "open_count": 1245, "items": [...], "omitted_count": 1220, "result_id": "ctx_…", "retrieval_available": true}`

### `get_improvement_plan`

- Group: `health`
- Purpose: Turn the flat finding backlog into a deterministic, ROI-ordered
  improvement campaign. Findings are clustered by theme (rule + directory) — for
  example "39 duplicate literals in tests/integration" instead of 39 separate
  to-dos — and each cluster carries an effort estimate (`S`/`M`/`L` and
  `effort_points`), a `health_gain` estimate, an `roi` (health-gain ÷ effort),
  the affected `files`, and a capped list of member `finding_ids`. Clusters are
  ordered by ROI so the cheapest, highest-impact work comes first.
- Inputs: repository root.
- Outputs: a bounded plan envelope: `total_clusters`, `total_findings`, and a
  capped `clusters` preview with `returned_count`/`omitted_count`. Each cluster
  has `theme`, `rule_id`, `scope`, `size`, `severity`, `effort`,
  `effort_points`, `health_gain`, `roi`, `files`, `finding_ids`, and
  `suggested_action`.
- Bounds: source-read-only for analyzed files; bounded output by default;
  runtime no-network. A pure transform over open findings — no new indexing. The
  inline preview holds at most `INLINE_ITEM_LIMIT` (default 25) clusters; when
  clusters are omitted the envelope carries a `result_id` with
  `retrieval_available` and `retrieval_hints` for `retrieve_result`. Effort and
  ROI are deterministic functions of the finding set.
- Example shape:
  `{"ok": true, "kind": "improvement_plan", "total_clusters": 97, "total_findings": 503, "clusters": [{"theme": "Consolidate 39 duplicate literal(s) in tests/integration", "effort": "M", "roi": 3.86, ...}], "omitted_count": 72, "result_id": "ctx_…", "retrieval_available": true}`

### `get_calibration`

- Group: `health`
- Purpose: Report adaptive, self-calibrating signal derived from this repo's own
  lifecycle verdicts. For each rule it returns the empirical accept rate
  (resolved vs wontfix/ignored), the base confidence, and an
  `adjusted_confidence` nudged toward that accept rate once enough verdicts
  exist — plus learned `suppression_candidates` (rule + directory scopes
  dismissed often enough to be auto-deferred, when learned suppression is
  enabled).
- Inputs: repository root.
- Outputs: `confidence_recalibration`, `learned_suppression`, `min_sample_size`,
  a `rules` list (each with `rule_id`, `base_confidence`, `adjusted_confidence`,
  `accepted`, `rejected`, `sample_size`, `accept_rate`, `calibrated`), and
  `suppression_candidates`.
- Bounds: source-read-only for analyzed files; bounded output by default;
  runtime no-network. A pure, deterministic function of the stored findings —
  below `min_sample_size` verdicts the base confidence is used unchanged (cold
  start), so new repos see no change. `explain_score` carries the same
  calibration block for a single finding.
- Example shape:
  `{"ok": true, "confidence_recalibration": true, "min_sample_size": 8, "rules": [{"rule_id": "python.dead_code_candidate", "base_confidence": 0.6, "adjusted_confidence": 0.8, "accepted": 13, "rejected": 0, "sample_size": 13, "calibrated": true}], "suppression_candidates": []}`

### `get_progress`

- Group: `health`
- Purpose: Return progress over finding lifecycle states.
- Inputs: repository root plus tool-specific arguments such as query, path,
  symbol, finding id, status, or limit.
- Outputs: JSON-compatible structured payload with local evidence and no
  unbounded source dump.
- Bounds: source-read-only for analyzed files; bounded output by default;
  runtime no-network.
- Example shape: `{"tool": "get_progress", "ok": true, "data": {...}}`

### `get_regressions`

- Group: `health`
- Purpose: Return findings that regressed across scans.
- Inputs: repository root plus tool-specific arguments such as query, path,
  symbol, finding id, status, or limit.
- Outputs: a bounded list envelope: `count`, `total_count`, `status_counts`,
  `severity_counts`, `rule_counts`, and a capped `items` preview with
  `returned_count`/`omitted_count`.
- Bounds: source-read-only for analyzed files; bounded output by default;
  runtime no-network. The inline preview holds at most `INLINE_ITEM_LIMIT`
  (default 25) findings; when findings are omitted the envelope carries a
  `result_id` with `retrieval_available` and `retrieval_hints` for
  `retrieve_result`.
- Example shape:
  `{"ok": true, "kind": "regressions", "count": 3, "items": [...], "omitted_count": 0, "result_id": null, "retrieval_available": false}`

### `review_diff_risk`

- Group: `risk`
- Purpose: Return deterministic risk report for changed files.
- Inputs: repository root plus tool-specific arguments such as query, path,
  symbol, finding id, status, or limit.
- Outputs: JSON-compatible structured payload with local evidence and no
  unbounded source dump.
- Bounds: source-read-only for analyzed files; bounded output by default;
  runtime no-network.
- Example shape: `{"tool": "review_diff_risk", "ok": true, "data": {...}}`

### `get_changed_file_health`

- Group: `risk`
- Purpose: Return health summary for changed files.
- Inputs: repository root plus tool-specific arguments such as query, path,
  symbol, finding id, status, or limit.
- Outputs: JSON-compatible structured payload with local evidence and no
  unbounded source dump.
- Bounds: source-read-only for analyzed files; bounded output by default;
  runtime no-network.
- Example shape:
  `{"tool": "get_changed_file_health", "ok": true, "data": {...}}`

### `retrieve_result`

- Group: `context`
- Purpose: Retrieve exact, summarized, filtered, or sampled stored CodeScent
  results by opaque result id.
- Inputs: repository root, opaque result id, retrieval mode (`exact`, `summary`,
  `filtered`, or `sample`), optional query/file/symbol/result-type filters, and
  limit.
- Outputs: JSON-compatible stored-result payload or bounded error payload;
  filters only inspect stored JSON.
- Bounds: does not rerun searches or read filesystem paths from filters; bounded
  output by default; runtime no-network.
- Example shape:
  `{"result_id": "ctx_123", "mode": "summary", "items": [], "warnings": []}`

### `context_stats`

- Group: `health`
- Purpose: Report bounded context and token-savings stats for a local MCP
  session.
- Inputs: repository root, project id, and session id.
- Outputs: JSON-compatible structured counters, fingerprints, tool names, and
  warnings; no raw source, raw results, or full query payloads.
- Bounds: reads sanitized `.codescent` session events only; bounded output by
  default; runtime no-network.
- Example shape: `{"session_id": "sess_123", "tool_calls": 0, "warnings": []}`

### `how_to_use`

- Group: `guidance`
- Purpose: Return the CodeScent capability and workflow guide: the recommended
  workflow, every registered tool grouped by job with a one-line "reach for this
  when", and the runtime safety boundaries. Generated dynamically from the
  registered surface so the documented tool set can never drift.
- Inputs: none.
- Outputs: a bounded guide payload with `server`, `summary`, `workflow`,
  `tool_groups` (each with `group`, `reach_for_when`, a capped `tools` list, and
  `omitted_count`), `safety_boundaries`, and `tool_count`. The same payload is
  served as the `codescent://guide` MCP resource so resource-only clients can
  read it too.
- Bounds: source-read-only for analyzed files; reads no analyzed source at all;
  bounded output by default; runtime no-network. Per-group tool lists are capped.
- Example shape:
  `{"ok": true, "server": "CodeScent", "workflow": [...], "tool_groups": [...], "safety_boundaries": [...], "tool_count": 41}`

## Reference Pattern

Each registered tool follows this reference contract:

- Inputs: a repository root plus tool-specific arguments such as query, path,
  symbol, finding id, limit, status, or output bounds.
- Outputs: JSON-compatible structured payloads with bounded output and evidence
  fields where applicable.
- Safety: tools do not edit analyzed source and do not require runtime network
  access.

Repository tools report repo map and status. Search and context tools return
bounded matches, source ranges, graph relationships, and related files. Code
health tools scan, report, prioritize, mark, and rescan findings. Planning tools
return finding context, refactor plans, impact, and recommended verification.
Risk tools summarize changed-file health and diff risk.

Future tools and commands remain unregistered until their stage passes contract
tests, real-surface QA, source-read-only proof, and the required evidence
capture.

## Related Docs

- [Getting started](getting-started.md)
- [Workflows](workflows.md)
- [CLI reference](cli-reference.md)
