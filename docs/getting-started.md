# Getting Started

This guide runs CodeScent against a temporary copy of the Python fixture repo so
the checked-in fixture stays clean. CodeScent writes runtime state under the
analyzed repo's `.codescent/` directory and does not edit analyzed source files.

## Install

```bash
uv sync
uv run codescent --help
```

## Create A Temporary Repo

```bash
tmp=$(mktemp -d)
cp -R tests/fixtures/python-basic "$tmp/repo"
```

Use `$tmp/repo` for commands that create `.codescent/` state:

```bash
uv run codescent init --repo "$tmp/repo" --json
uv run codescent index --repo "$tmp/repo" --json
uv run codescent scan --repo "$tmp/repo" --json
uv run codescent status --repo "$tmp/repo" --json
uv run codescent report --repo "$tmp/repo" --format json
uv run codescent doctor --repo "$tmp/repo" --json
```

Remove the temporary repo when done:

```bash
rm -rf "$tmp"
```

## MCP Stdio

Run the local MCP server over stdio:

```bash
uv run codescent serve
```

Connect an MCP client to that command. The MCP server exposes repository,
search, context, finding, planning, and risk tools documented in
[MCP tools](mcp-tools.md).

## First Improvement Loop

1. Initialize and index the repo.
2. Run `scan` to create deterministic findings.
3. Use `report`, `findings`, `next`, or MCP tools to inspect the highest-value
   issue.
4. Ask CodeScent for bounded context, a refactor plan, and suggested tests.
5. Run your own verification commands.
6. Rescan and mark findings only after separate evidence exists.

See [Workflows](workflows.md) for the complete source-read-only loop.

## Common First Errors

- `doctor` reports missing database or config: run
  `uv run codescent init --repo "$tmp/repo"` before diagnostics.
- `reset` fails without confirmation: reset requires --dry-run or --yes.
- `report` or `ci` rejects a format: use `--format json` or `--format markdown`.

## Next Docs

- [CLI reference](cli-reference.md)
- [Configuration](configuration.md)
- [Dashboard](dashboard.md)
- [Evals](evals.md)
