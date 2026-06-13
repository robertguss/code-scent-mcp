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
- `get_progress`
- `get_regressions`
- `review_diff_risk`
- `get_changed_file_health`
- `retrieve_result`
- `context_stats`

## Locked Post-MVP MCP Tools

No MCP tools are locked in the current local PRD-remainder stage. Task 14 remains the final docs/public lockstep check for Headroom MCP tools.

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

`get_repo_map`, `get_repo_status`

Search and context tools:

`search_files`, `search_content`, `find_symbol`, `get_file_context`,
`get_symbol_context`, `find_references`, `find_callers`, `find_callees`,
`get_related_files`, `retrieve_result`

Code health and finding lifecycle tools:

`scan_code_health`, `get_smell_report`, `get_next_improvement`, `mark_finding`,
`rescan`, `get_finding`, `explain_score`, `get_backlog`, `get_progress`,
`get_regressions`, `context_stats`

Planning tools:

`get_finding_context`, `plan_refactor`, `suggest_tests`, `get_impact`,
`verify_change`

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

### `search_files`

- Group: `search`
- Purpose: Find files by ranked path query.
- Inputs: repository root plus tool-specific arguments such as query, path,
  symbol, finding id, status, or limit.
- Outputs: JSON-compatible structured payload with local evidence and no
  unbounded source dump.
- Bounds: source-read-only for analyzed files; bounded output by default;
  runtime no-network.
- Example shape: `{"tool": "search_files", "ok": true, "data": {...}}`

### `search_content`

- Group: `search`
- Purpose: Find bounded content matches by query.
- Inputs: repository root plus tool-specific arguments such as query, path,
  symbol, finding id, status, or limit.
- Outputs: JSON-compatible structured payload with local evidence and no
  unbounded source dump.
- Bounds: source-read-only for analyzed files; bounded output by default;
  runtime no-network.
- Example shape: `{"tool": "search_content", "ok": true, "data": {...}}`

### `find_symbol`

- Group: `context`
- Purpose: Find indexed symbols by name and return a bounded symbol-search
  envelope.
- Inputs: repository root, query, and limit. Large responses may include
  `mode`, `original_result_id`, `omitted_count`, `retrieval_available`,
  `retrieval_hints`, `warnings`, and `stats`.
- Outputs: JSON-compatible structured payload with local evidence and no
  unbounded source dump.
- Bounds: source-read-only for analyzed files; bounded output by default;
  `find_symbol` envelopes large results instead of returning unbounded symbol
  lists; runtime no-network.
- Example shape: `{"ok": true, "kind": "symbol_search", "mode": "exact",
  "items": []}`

### `get_file_context`

- Group: `context`
- Purpose: Return bounded context for one file.
- Inputs: repository root plus tool-specific arguments such as query, path,
  symbol, finding id, status, or limit.
- Outputs: JSON-compatible structured payload with local evidence and no
  unbounded source dump.
- Bounds: source-read-only for analyzed files; bounded output by default;
  runtime no-network.
- Example shape: `{"tool": "get_file_context", "ok": true, "data": {...}}`

### `get_symbol_context`

- Group: `context`
- Purpose: Return bounded context for one symbol.
- Inputs: repository root plus tool-specific arguments such as query, path,
  symbol, finding id, status, or limit.
- Outputs: JSON-compatible structured payload with local evidence and no
  unbounded source dump.
- Bounds: source-read-only for analyzed files; bounded output by default;
  runtime no-network.
- Example shape: `{"tool": "get_symbol_context", "ok": true, "data": {...}}`

### `scan_code_health`

- Group: `health`
- Purpose: Run deterministic code-health scanning.
- Inputs: repository root plus tool-specific arguments such as query, path,
  symbol, finding id, status, or limit.
- Outputs: JSON-compatible structured payload with local evidence and no
  unbounded source dump.
- Bounds: source-read-only for analyzed files; bounded output by default;
  runtime no-network.
- Example shape: `{"tool": "scan_code_health", "ok": true, "data": {...}}`

### `get_smell_report`

- Group: `health`
- Purpose: Return summarized open finding report data.
- Inputs: repository root plus tool-specific arguments such as query, path,
  symbol, finding id, status, or limit.
- Outputs: JSON-compatible structured payload with local evidence and no
  unbounded source dump.
- Bounds: source-read-only for analyzed files; bounded output by default;
  runtime no-network.
- Example shape: `{"tool": "get_smell_report", "ok": true, "data": {...}}`

### `get_finding_context`

- Group: `planning`
- Purpose: Return evidence and bounded context for a finding.
- Inputs: repository root plus tool-specific arguments such as query, path,
  symbol, finding id, status, or limit.
- Outputs: JSON-compatible structured payload with local evidence and no
  unbounded source dump.
- Bounds: source-read-only for analyzed files; bounded output by default;
  runtime no-network.
- Example shape: `{"tool": "get_finding_context", "ok": true, "data": {...}}`

### `get_next_improvement`

- Group: `health`
- Purpose: Return the next recommended finding to address.
- Inputs: repository root plus tool-specific arguments such as query, path,
  symbol, finding id, status, or limit.
- Outputs: JSON-compatible structured payload with local evidence and no
  unbounded source dump.
- Bounds: source-read-only for analyzed files; bounded output by default;
  runtime no-network.
- Example shape: `{"tool": "get_next_improvement", "ok": true, "data": {...}}`

### `plan_refactor`

- Group: `planning`
- Purpose: Return a safe refactor plan for a finding.
- Inputs: repository root plus tool-specific arguments such as query, path,
  symbol, finding id, status, or limit.
- Outputs: JSON-compatible structured payload with local evidence and no
  unbounded source dump.
- Bounds: source-read-only for analyzed files; bounded output by default;
  runtime no-network.
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

### `mark_finding`

- Group: `health`
- Purpose: Record finding lifecycle status after external evidence.
- Inputs: repository root plus tool-specific arguments such as query, path,
  symbol, finding id, status, or limit.
- Outputs: JSON-compatible structured payload with local evidence and no
  unbounded source dump.
- Bounds: source-read-only for analyzed files; bounded output by default;
  runtime no-network.
- Example shape: `{"tool": "mark_finding", "ok": true, "data": {...}}`

### `rescan`

- Group: `health`
- Purpose: Run scan again and report resolved or regressed findings.
- Inputs: repository root plus tool-specific arguments such as query, path,
  symbol, finding id, status, or limit.
- Outputs: JSON-compatible structured payload with local evidence and no
  unbounded source dump.
- Bounds: source-read-only for analyzed files; bounded output by default;
  runtime no-network.
- Example shape: `{"tool": "rescan", "ok": true, "data": {...}}`

### `multi_search_content`

- Group: `search`
- Purpose: Run multiple bounded content queries together.
- Inputs: repository root plus tool-specific arguments such as query, path,
  symbol, finding id, status, or limit.
- Outputs: JSON-compatible structured payload with local evidence and no
  unbounded source dump.
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
  unbounded source dump.
- Bounds: source-read-only for analyzed files; bounded output by default;
  runtime no-network.
- Example shape: `{"tool": "search_todos", "ok": true, "data": {...}}`

### `search_tests`

- Group: `search`
- Purpose: Find likely relevant tests.
- Inputs: repository root plus tool-specific arguments such as query, path,
  symbol, finding id, status, or limit.
- Outputs: JSON-compatible structured payload with local evidence and no
  unbounded source dump.
- Bounds: source-read-only for analyzed files; bounded output by default;
  runtime no-network.
- Example shape: `{"tool": "search_tests", "ok": true, "data": {...}}`

### `find_references`

- Group: `context`
- Purpose: Return indexed references for a symbol or path.
- Inputs: repository root plus tool-specific arguments such as query, path,
  symbol, finding id, status, or limit.
- Outputs: JSON-compatible structured payload with local evidence and no
  unbounded source dump.
- Bounds: source-read-only for analyzed files; bounded output by default;
  runtime no-network.
- Example shape: `{"tool": "find_references", "ok": true, "data": {...}}`

### `find_callers`

- Group: `context`
- Purpose: Return callers for an indexed callable.
- Inputs: repository root plus tool-specific arguments such as query, path,
  symbol, finding id, status, or limit.
- Outputs: JSON-compatible structured payload with local evidence and no
  unbounded source dump.
- Bounds: source-read-only for analyzed files; bounded output by default;
  runtime no-network.
- Example shape: `{"tool": "find_callers", "ok": true, "data": {...}}`

### `find_callees`

- Group: `context`
- Purpose: Return callees from an indexed callable.
- Inputs: repository root plus tool-specific arguments such as query, path,
  symbol, finding id, status, or limit.
- Outputs: JSON-compatible structured payload with local evidence and no
  unbounded source dump.
- Bounds: source-read-only for analyzed files; bounded output by default;
  runtime no-network.
- Example shape: `{"tool": "find_callees", "ok": true, "data": {...}}`

### `get_related_files`

- Group: `context`
- Purpose: Return related implementation, test, and config files.
- Inputs: repository root plus tool-specific arguments such as query, path,
  symbol, finding id, status, or limit.
- Outputs: JSON-compatible structured payload with local evidence and no
  unbounded source dump.
- Bounds: source-read-only for analyzed files; bounded output by default;
  runtime no-network.
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
- Outputs: JSON-compatible structured payload with local evidence and no
  unbounded source dump.
- Bounds: source-read-only for analyzed files; bounded output by default;
  runtime no-network.
- Example shape: `{"tool": "get_backlog", "ok": true, "data": {...}}`

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
- Outputs: JSON-compatible structured payload with local evidence and no
  unbounded source dump.
- Bounds: source-read-only for analyzed files; bounded output by default;
  runtime no-network.
- Example shape: `{"tool": "get_regressions", "ok": true, "data": {...}}`

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
- Example shape:
  `{"session_id": "sess_123", "tool_calls": 0, "warnings": []}`

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
