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
- per-rule acceptance precision and a health trend (`/api/precision`);
- rule configuration updates;
- JSON export data.

Rule updates write CodeScent config under `.codescent/` and should preserve
existing project config sections.

## Acceptance Precision (`/api/precision`)

`GET /api/precision` returns runtime **acceptance precision** — per-rule
`accepted / (accepted + dismissed)` from the persisted finding status history,
plus the calibration suppression-candidate count per rule and an ordered
health-trend timeline. This is read-only and loopback-only like every other
route; it adds no new network surface.

A finding counts as *accepted* when resolved and *dismissed* when marked
`wontfix`/`ignored` (mirrors calibration's accept rate). Open, deferred, and
needs-review findings are not yet verdicts. This runtime metric is distinct from
the labeled-corpus **eval precision** in [Evals](evals.md).

Response shape:

```json
{
  "read_only": true,
  "accepted": 2,
  "dismissed": 1,
  "sample_size": 3,
  "acceptance_precision": 0.667,
  "rules": [
    {
      "rule_id": "python.duplicate_literal",
      "accepted": 0,
      "dismissed": 1,
      "sample_size": 1,
      "acceptance_precision": 0.0,
      "suppression_candidates": 0
    }
  ],
  "trend": [
    {"date": "2026-06-28", "accepted": 2, "dismissed": 1, "acceptance_precision": 0.667}
  ]
}
```

`acceptance_precision` is `null` until a rule has at least one verdict. The trend
is bounded to the most recent 90 daily points. The same data is available from
the `codescent precision` CLI command (see the CLI reference).

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
