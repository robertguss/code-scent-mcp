# Workflows

CodeScent is designed for small, evidence-backed improvement loops. It gives an
agent or human enough local context to choose and verify a change without
editing analyzed source automatically.

## Source-Read-Only Improvement Loop

1. Initialize CodeScent state with `init`.
2. Build the local index with `index`.
3. Run `scan` to persist deterministic findings.
4. Use `next`, `findings`, `report`, or MCP tools to choose a finding.
5. Retrieve bounded finding or symbol context.
6. Ask for a refactor plan and suggested tests.
7. Run the target repo checks yourself.
8. Rescan after the source change.
9. Mark findings only after separate verification evidence exists.

## MCP Loop

An MCP client should prefer CodeScent tools before broad shell search:

- repository status and map;
- bounded file/content search;
- symbol and graph context;
- finding context and next improvement;
- refactor planning and suggested verification commands.

CodeScent recommendations are not proof by themselves. Verification commands
are recommendations; CodeScent does not execute target project tests as part of
the V1 improvement loop.

## Reporting Loop

Use reports when you need a human-readable checkpoint:

```bash
uv run codescent report --repo "$repo" --format markdown
uv run codescent export --repo "$repo" --format json
```

Use CI/diff review when checking changed files:

```bash
uv run codescent ci --repo "$repo" --format json --threshold high
uv run codescent review-diff --repo "$repo" --format markdown
```

## Safety Boundaries

- Runtime writes stay under `.codescent/`.
- Analyzed source is source-read-only from CodeScent's perspective.
- Runtime no-network applies to indexing, scanning, search, context, dashboard,
  CI mode, and eval execution.
- Optional subjective review is disabled unless explicitly requested.

## Related Docs

- [CLI reference](cli-reference.md)
- [MCP tools](mcp-tools.md)
- [Configuration](configuration.md)
- [Evals](evals.md)
