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
- `get_finding`
- `explain_score`
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
- `start_task`
- `record_verification`

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
`verify_change`, `select_tests`

Risk tools:

`review_diff_risk`, `get_changed_file_health`

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
  preview, and `returned_count`/`omitted_count`.
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
  preview with `returned_count`/`omitted_count`.
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
- Purpose: Recommend verification commands for a finding or change.
- Inputs: repository root plus tool-specific arguments such as query, path,
  symbol, finding id, status, or limit.
- Outputs: JSON-compatible structured payload with local evidence and no
  unbounded source dump.
- Bounds: source-read-only for analyzed files; bounded output by default;
  runtime no-network.
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
