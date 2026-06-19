# Dashboard

CodeScent includes a local health dashboard backed by the same `.codescent/`
state as the CLI and MCP tools.

The dashboard binds to `127.0.0.1` loopback only. It has no auth, no remote
dashboard, and no hosted mode. Do not expose it beyond the local machine.

There is no public CLI command for launching the dashboard in this release. The
current verified path is the dashboard server used by integration tests and
`scripts/smoke_dashboard.py`.

## Current Surface

The dashboard shows:

- repository status and health summary;
- findings and progress;
- rule configuration updates;
- JSON export data.

Rule updates write CodeScent config under `.codescent/` and should preserve
existing project config sections.

## Smoke Verification

Run the dashboard smoke when Chrome and Node are available:

```bash
uv run python scripts/smoke_dashboard.py --repo tests/fixtures/python-basic --out .omo/evidence/dashboard-smoke.json
```

The smoke starts a loopback server, captures a screenshot, writes JSON and
Markdown export artifacts, checks source-read-only behavior, and tears down the
server/profile.

If Google Chrome or Node is missing, use the integration tests for the
non-browser gate:

```bash
uv run pytest tests/integration/test_dashboard.py
```

## Related Docs

- [Configuration](configuration.md)
- [Workflows](workflows.md)
- [Evals](evals.md)
