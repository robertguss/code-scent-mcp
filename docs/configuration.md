# Configuration

CodeScent stores local project state under `.codescent/` in the analyzed
repository.

```text
.codescent/
  config.toml
  index.sqlite
```

The database stores indexes, symbols, scan runs, findings, lifecycle events,
suggested verification records, and telemetry. Runtime writes belong there;
CodeScent does not edit analyzed source files.

## Inspecting State

```bash
uv run codescent doctor --repo "$repo" --json
uv run codescent config --repo "$repo" --json
uv run codescent rules --repo "$repo" --json
```

`doctor` reports database/config health and `routing_templates`. Templates are
examples only and are not auto-written into analyzed repos.

## Architecture Rules

Architecture boundary checks are opt-in and report-only. Add rules to
`.codescent/config.toml` when a layer must not import another package or module
prefix:

```toml
[architecture]
rules = [
  { layer = "src/codescent/services", forbidden_imports = ["codescent.cli"] },
]
```

`layer` matches repo-relative path prefixes. `forbidden_imports` matches dotted
Python import prefixes, so `codescent.cli` also matches `codescent.cli.main`.
When no architecture rules are configured, the scanner returns no findings.

## Coverage Report

Coverage ingestion reads an existing Cobertura XML report when present. By
default CodeScent looks for `coverage.xml` at the repository root. To use a
different repo-relative path, set `coverage_path` in `.codescent/config.toml`:

```toml
coverage_path = "reports/coverage.xml"
```

Paths outside the analyzed repository are ignored. CodeScent reads coverage
reports only; it does not run tests or generate coverage files.

## Reset

`reset` is intentionally explicit because it deletes CodeScent state:

```bash
uv run codescent reset --repo "$repo" --dry-run --json
uv run codescent reset --repo "$repo" --yes --json
```

reset requires --dry-run or --yes.

## Common Recovery

- Missing `.codescent/config.toml`: run `init`.
- Missing `.codescent/index.sqlite`: run `init`, then `index`.
- Invalid output format: use `--format json` or `--format markdown`.
- Unexpected analyzed-source changes: inspect target repo git status; CodeScent
  runtime should only write `.codescent/`.

## Runtime Boundaries

- source-read-only for analyzed source;
- runtime no-network by default;
- local stdio MCP transport only;
- loopback dashboard only;
- no hosted service, remote dashboard, or auth.

## Related Docs

- [Agent routing](agent-routing.md)
- [CLI reference](cli-reference.md)
- [Dashboard](dashboard.md)
