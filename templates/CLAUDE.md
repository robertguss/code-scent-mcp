# CLAUDE.md

Use CodeScent before broad grep when you need repository context, likely
findings, related files, changed-file risk, or test suggestions.

Keep CodeScent source-read-only. It may write local `.codescent` state, but it
must not edit analyzed source files. Treat deterministic findings and optional
subjective review as evidence to inspect, not as automatic changes.

This template does not auto-write itself into projects; adopt it manually when
it matches the repo workflow.
