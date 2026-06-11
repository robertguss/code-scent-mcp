# CodeScent MCP Tools

CodeScent exposes exactly these MVP tools:

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

CodeScent does not expose post-MVP tools in this release. The MVP excludes
hosted review, dashboard workflows, automatic source edits, CI/PR mode, and
additional graph tools outside this list.

## Tool Groups

Repository tools:

`get_repo_map`, `get_repo_status`

Search and context tools:

`search_files`, `search_content`, `find_symbol`, `get_file_context`,
`get_symbol_context`

Code health and finding lifecycle tools:

`scan_code_health`, `get_smell_report`, `get_next_improvement`,
`mark_finding`, `rescan`

Planning tools:

`get_finding_context`, `plan_refactor`, `suggest_tests`

All tools are local and source-read-only for analyzed source. Tools may create
or update `.codescent` state for indexing, scan runs, findings, lifecycle
events, and telemetry.
