# CLI Reference

The `codescent` CLI is the human/admin surface over the same local services used
by MCP. Commands write only CodeScent state under `.codescent/` unless they emit
output to stdout.

## Repository Commands

### `init`

Creates `.codescent/config.toml` and `.codescent/index.sqlite`.

```bash
uv run codescent init --repo "$repo" --json
```

### `index`

Indexes included source files and reports changed files. Indexing is
**incremental by default**: only added or modified files (detected by comparing
on-disk content hashes to the persisted index) are re-parsed, and rows for
modified or deleted files are removed via foreign-key cascade. Pass `--full` to
force a complete rebuild. Both modes produce an equivalent index for the same
on-disk state.

```bash
uv run codescent index --repo "$repo" --json          # incremental delta
uv run codescent index --repo "$repo" --full --json   # full rebuild
```

The JSON result reports `indexed_files` (total in the index), `reindexed_files`
(files actually reprocessed this pass), `changed_files`, `deleted_files`, and
`full`.

### `scan`

Runs deterministic code-health rules and persists findings.

```bash
uv run codescent scan --repo "$repo" --json
```

### `status`

Reports index freshness, finding counts, database state, and git status.

```bash
uv run codescent status --repo "$repo" --json
```

### `watch`

Watches the repository and runs a **debounced incremental reindex** when files
change. The watcher polls for changes every `--interval` seconds and only
reindexes once the set of changed files has stayed stable for `--debounce`
seconds, so a burst of edits collapses into a single incremental pass. Use
`--once` for a single bounded reindex (e.g. local checks or CI).

```bash
uv run codescent watch --repo "$repo" --once --json              # one pass, exit
uv run codescent watch --repo "$repo" --interval 1 --debounce 2  # poll + debounce
```

Options: `--once` (single pass), `--interval` (seconds between change polls,
default `1.0`), `--debounce` (seconds a change set must stay stable before
reindexing, default `2.0`).

### `reset`

Lists or removes `.codescent/` state. `reset` is intentionally guarded: reset
requires --dry-run or --yes.

```bash
uv run codescent reset --repo "$repo" --dry-run --json
uv run codescent reset --repo "$repo" --yes --json
```

## Diagnostics And Config

### `doctor`

Checks local CodeScent state, MCP availability, exclusions, and optional routing
templates. It does not run target repo tests.

```bash
uv run codescent doctor --repo "$repo" --json
```

### `config`

Prints effective project configuration.

```bash
uv run codescent config --repo "$repo" --json
```

### `rules`

Prints enabled and disabled rule packs.

```bash
uv run codescent rules --repo "$repo" --json
```

## Finding And Report Commands

### `report`

Emits JSON or Markdown report data. Subjective review is opt-in.

```bash
uv run codescent report --repo "$repo" --format json
uv run codescent report --repo "$repo" --format markdown
```

### `export`

Exports the deterministic report without subjective review.

```bash
uv run codescent export --repo "$repo" --format markdown
```

### `findings`

Lists persisted findings.

```bash
uv run codescent findings --repo "$repo" --json
```

### `next`

Returns the next recommended improvement.

```bash
uv run codescent next --repo "$repo" --json
```

### `explain`

Explains a finding score.

```bash
uv run codescent explain "$finding_id" --repo "$repo" --json
```

### `precision`

Reports runtime **acceptance precision** — per-rule
`accepted / (accepted + dismissed)` from the persisted finding status history,
the calibration suppression-candidate count per rule, and an ordered health-trend
timeline. Read-only. This is distinct from the labeled-corpus **eval precision**
in [Evals](evals.md).

```bash
uv run codescent precision --repo "$repo" --format json
uv run codescent precision --repo "$repo" --format markdown
```

The JSON payload reports overall `accepted`/`dismissed`/`sample_size`/
`acceptance_precision`, a `rules` array (each with `rule_id`, `accepted`,
`dismissed`, `sample_size`, `acceptance_precision`, `suppression_candidates`),
and a bounded `trend` array of daily `{date, accepted, dismissed,
acceptance_precision}` points. `acceptance_precision` is `null` until a rule has a
verdict.

## MCP And CI

### `serve`

Starts the local stdio MCP server.

```bash
uv run codescent serve
```

### `ci`

Runs deterministic local CI/risk reporting and exits nonzero when the threshold
is exceeded.

```bash
uv run codescent ci --repo "$repo" --format json --threshold high
```

To gate only new debt (and never the pre-existing backlog), accept a baseline,
then enable ratchet mode:

```bash
uv run codescent ci --repo "$repo" --update-baseline
uv run codescent ci --repo "$repo" --ratchet
uv run codescent ci --repo "$repo" --ratchet --base origin/main
```

`--update-baseline` snapshots the current findings as the accepted baseline (by
stable finding key). In ratchet mode a finding is **new** when its stable key is
absent from the baseline; CI fails only when a new finding is at least
`fail_on_new_severity` severe (default `warning`), so resolving one finding and
introducing a different one is caught even when the per-file count is unchanged.
The pre-existing backlog never fails the build. `--base <ref>` scopes the check
to files changed since that git ref (merge-base). With no accepted baseline — or
one accepted before stable-key tracking shipped (`baseline_stale: true`) — the
ratchet is a no-op that recommends re-running `--update-baseline` rather than
failing. Defaults live in the `[ratchet]` config section; omitting `--ratchet`
keeps the absolute threshold behavior.

`ci` and `review-diff` also accept `--format sarif` and `--format github` to surface
findings on pull requests. `sarif` emits a SARIF 2.1.0 log (one run, one tool) for
upload to GitHub code scanning; each result maps `rule_id`, `severity` (→ SARIF
`level`), `file_path`, the evidence line range, `message`, and `suggested_action`
(in result `properties`), with the stable finding key as a `partialFingerprints`
entry. `github` emits one workflow-command annotation line per finding —
`::<level> file=<path>,line=<n>::<message>` — that GitHub renders inline on the
diff. The `json` and `markdown` formats are unchanged. `ci` still exits nonzero
when the gate fails regardless of format; use `review-diff --format sarif` for an
always-zero upload step.

```bash
uv run codescent ci --repo "$repo" --format sarif > codescent.sarif
uv run codescent review-diff --repo "$repo" --format github
```

### `review-diff`

Runs the diff review report without threshold failure semantics.

```bash
uv run codescent review-diff --repo "$repo" --format markdown
uv run codescent review-diff --repo "$repo" --format sarif
uv run codescent review-diff --repo "$repo" --format github
```

## Common Errors

- Missing state: run `init` before `doctor` or inspect the warning payload.
- Invalid format: use `--format json` or `--format markdown` (also `sarif` or
  `github` for `ci` and `review-diff`).
- Reset without confirmation: use `reset --dry-run` to inspect targets or
  `reset --yes` to delete `.codescent/`.

## Related Docs

- [Getting started](getting-started.md)
- [MCP tools](mcp-tools.md)
- [Configuration](configuration.md)
