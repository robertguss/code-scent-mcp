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

## Maintainability Thresholds

The deterministic maintainability rules use size/count thresholds that you can
tune per repo. Defaults are calibrated for real codebases — they flag genuinely
large or repetitive code, not the median file. Override any subset in
`.codescent/config.toml`:

```toml
[thresholds]
# Python
large_file_lines = 300
large_function_lines = 50
large_class_lines = 200
too_many_imports = 20
deep_nesting = 4
todo_cluster_size = 3
duplicate_literal_min_count = 4
duplicate_literal_min_length = 8
# Relative ("large for this repository") thresholds
relative_thresholds_enabled = true
relative_outlier_iqr_multiplier = 1.5
relative_min_sample_size = 12
# TypeScript / React / Next
ts_large_component_lines = 150
ts_too_many_hooks = 8
ts_too_many_props = 8
ts_too_many_exports = 10
ts_route_handler_lines = 40
```

The values above are the defaults. Lower them to surface more findings (useful
on small or strict codebases); raise them to reduce noise on large legacy
repositories. Every finding records the threshold it was measured against in its
evidence, so `explain_score` and `get_finding` always show why something was
flagged. Thresholds are a pure input to the deterministic scan — the same repo
and the same thresholds always produce the same findings.

### Relative thresholds

The absolute thresholds above are a fixed floor. The relative thresholds add an
_outlier-for-this-repo_ flavor on top: a file, function, or class that is well
under the absolute floor but unusually large **for this repository** is flagged
as `python.relative_large_file` / `python.relative_large_function` /
`python.relative_large_class` (severity `info`). The cutoff is the standard IQR
outlier rule over the repo's own size distribution
(`Q3 + relative_outlier_iqr_multiplier * IQR`), so it fires only on genuine
outliers — not a fixed fraction of the codebase — and stays silent when the
absolute floor is already the binding constraint. Each finding's evidence
carries `repo_median`, `repo_q3`, `outlier_cutoff`, and `sample_size` for
explainability, and the metrics never enter the finding's stable id (adding an
unrelated file does not re-key existing outliers).

Tuning knobs: `relative_outlier_iqr_multiplier` raises/lowers the cutoff (higher
= fewer, more extreme outliers); `relative_min_sample_size` skips the rule on
metrics with too few samples to be meaningful;
`relative_thresholds_enabled = false` turns the flavor off entirely.

## CI Ratchet

The CI ratchet (`codescent ci --ratchet`) fails only on _new_ debt versus an
accepted baseline, never on the pre-existing backlog. Configure its defaults in
`.codescent/config.toml`:

```toml
[ratchet]
enabled = false                      # reserved; --ratchet enables per-run today
base_ref = ""                        # default git ref for diff scoping ("" = whole repo)
fail_on_new_severity = "warning"     # block new findings at this severity or worse
require_non_negative_net_health = false
```

Accept a baseline with `codescent ci --update-baseline`; it records the current
findings by stable key. A finding is _new_ when its stable key is absent from
the baseline. `fail_on_new_severity` gates which new findings fail CI —
`warning` (the default) ignores new `info` findings (e.g. a new TODO), `info`
fails on any new finding. `base_ref` (or `--base <ref>`) restricts the check to
files changed since that ref. The transient
`python.changed_source_without_related_test` rule is excluded from the baseline
comparison. CodeScent never runs tests; the ratchet reads only its own scan
output and the local git diff.

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
