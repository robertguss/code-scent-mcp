# CodeScent Public Surface

CodeScent currently registers the MVP MCP tools below. Post-MVP tools are
declared in `codescent.core.public_surface` so docs, contract tests, and plan
audits can track upcoming public surface without exposing it at runtime before
its implementation lands.

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

The post-MVP plan intentionally does not register future tools until their
implementation, tests, documentation, and smoke evidence are complete.

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

## Locked Post-MVP MCP Tools

No MCP tools are locked in the current verification/risk stage.

## Current Registered CLI Commands

- `init`
- `serve`
- `index`
- `scan`
- `status`
- `doctor`

## Locked Post-MVP CLI Commands

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

## Tool Groups

Repository tools:

`get_repo_map`, `get_repo_status`

Search and context tools:

`search_files`, `search_content`, `find_symbol`, `get_file_context`,
`get_symbol_context`, `find_references`, `find_callers`, `find_callees`,
`get_related_files`

Code health and finding lifecycle tools:

`scan_code_health`, `get_smell_report`, `get_next_improvement`,
`mark_finding`, `rescan`, `get_finding`, `explain_score`, `get_backlog`,
`get_progress`, `get_regressions`

Planning tools:

`get_finding_context`, `plan_refactor`, `suggest_tests`, `get_impact`,
`verify_change`

Risk tools:

`review_diff_risk`, `get_changed_file_health`

All tools are local and source-read-only for analyzed source. Tools may create
or update `.codescent` state for indexing, scan runs, findings, lifecycle
events, and telemetry.

Locked post-MVP tools and commands remain unregistered until their stage passes
contract tests, real-surface QA, source-read-only proof, and the required
evidence capture.
