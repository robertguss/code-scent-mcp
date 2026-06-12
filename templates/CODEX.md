# CODEX.md

Use CodeScent before broad grep for repo orientation, finding context,
changed-file risk, and suggested verification commands.

Respect source-read-only behavior. CodeScent can maintain `.codescent` local
state, but it must not modify analyzed source. Use its output to choose focused
reads and tests, then make explicit code changes yourself.

This template does not auto-write itself into projects; copy it only after
reviewing the instructions.
