# Agent Routing Templates

CodeScent ships optional routing templates for agent tools. They are examples
that teams can inspect and copy into their own repos when they want agent
instructions to prefer CodeScent context before broad grep.

The templates cover:

- `templates/AGENTS.md`
- `templates/CLAUDE.md`
- `templates/CODEX.md`

Each template tells agents to use CodeScent before broad grep when looking for
repo context, to keep CodeScent source-read-only, and to treat CodeScent output
as local evidence rather than an automatic source edit.

CodeScent does not auto-write these files into analyzed repos.
`codescent doctor --json` reports the available routing templates so users can
adopt them intentionally.
