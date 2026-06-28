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

## Auto-Bootstrap

The first-run sequence is `init -> index -> scan`. By default CodeScent runs it
for you on the first tool call: when `.codescent/` state is missing or the index
is clearly stale, the entry path (and `start_task`) lazily runs the minimal
init -> index -> scan before answering, writing only under `.codescent/` and
performing no network I/O. Present-and-fresh state is a no-op.

`start_task` carries a bounded `bootstrap` note so callers see what happened:

```json
{
  "bootstrap": {
    "bootstrapped": true,
    "ran": ["init", "index", "scan"],
    "reason": "created",
    "guidance": []
  }
}
```

`reason` is one of `created` (state was missing), `refreshed` (stale index was
rebuilt), `fresh` (no-op), `disabled` (opt-out, see below), or `failed` (the
refresh raised; `guidance` then points back to `scan_code_health`).

Opt out by setting `auto_bootstrap = false` in `.codescent/config.toml`:

```toml
auto_bootstrap = false
```

With auto-bootstrap disabled, CodeScent never auto-creates or refreshes state.
When state is missing or stale it leaves `.codescent/` untouched and returns
clear "run `scan_code_health` to initialize" guidance (legacy behavior) in the
tool warnings and the `bootstrap.guidance` note instead.

## Incremental Indexing

Indexing is incremental by default. CodeScent compares each on-disk file's
content hash against the hash persisted in `.codescent/index.sqlite` and only
re-parses added or modified files; rows for modified or deleted files are
removed through foreign-key cascade. Unchanged files are left untouched, so
re-indexing a large repo after a small edit reprocesses only the delta. This
applies everywhere indexing runs (the `index` command, `scan`, auto-bootstrap,
and `watch`).

The incremental index is always equivalent to a full rebuild for the same
on-disk state. Force a full rebuild with `codescent index --full` if you ever
need to rebuild from scratch (for example after manually editing the database).

`codescent watch` reindexes incrementally on change, debounced so a burst of
edits collapses into one pass:

- `--interval` — seconds between change polls (default `1.0`).
- `--debounce` — seconds a change set must stay stable before reindexing
  (default `2.0`).
- `--once` — run a single incremental pass and exit.

## Inline Suppression

Silence a specific finding at its location with an inline comment, the way most
linters do. CodeScent reads the comment during a scan (it never edits source) and
gives the matched finding a `suppressed` status instead of `open`.

```python
# codescent: ignore[python.dead_code_candidate]
def _legacy_helper() -> int:
    return 1
```

Grammar (Python `#` and TypeScript/Go `//` line comments):

| Form | Effect |
| --- | --- |
| `# codescent: ignore[rule_id]` | silence one rule |
| `# codescent: ignore[rule_a, rule_b]` | silence several rules |
| `# codescent: ignore` | bare form: silence every rule on the line |
| `// codescent: ignore[rule_id]` | same, for `//`-comment languages |

A comment matches a finding when it sits **on the finding's own line or the line
directly above it**. A finding's line comes from its `start_line`/`line` evidence,
or from its resolved symbol's definition line; purely file-level findings (for
example `python.large_file`) have no line and are not inline-suppressible — use a
config-level exclusion or `mark_finding` for those.

Suppressed findings are:

- **excluded from open counts** (`get_smell_report`, `get_backlog`,
  `get_next_improvement`) and from the **CI ratchet** baseline and new-debt gate;
- **still inspectable** — they remain listed under the `suppressed` status with an
  audit-trail `suppressed` event recording the exact comment text.

Removing the comment and rescanning reopens the finding.

Disable the feature entirely by setting `inline_suppression = false` in
`.codescent/config.toml` (default `true`):

```toml
inline_suppression = false
```

With it disabled, ignore comments are ignored and every finding is `open`.

## Inspecting State

```bash
uv run codescent doctor --repo "$repo" --json
uv run codescent config --repo "$repo" --json
uv run codescent rules --repo "$repo" --json
```

`doctor` reports database/config health and `routing_templates`. Templates are
examples only and are not auto-written into analyzed repos.

## Language Packs & Generic Fallback

`language_packs` and `rule_packs` select the per-language packs (Python,
TypeScript/React/Next, Go); remove an entry to disable that language's parser
and rules. Defaults:

```toml
language_packs = ["python", "typescript", "go"]
rule_packs = ["python-maintainability", "ts-react-next", "go-maintainability"]
```

On top of those, a **generic text-only fallback** covers files in any language
that has no specific pack. It runs at lowest precedence (specific packs always
win for their own suffixes) and emits only line/text heuristics --
`generic.large_file`, `generic.todo_cluster`, `generic.duplicate_literal` -- with
no symbol/structural claims. It is on by default; turn it off with:

```toml
generic_fallback = false
```

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
findings by stable key (and a marker so a zero-finding baseline is distinguished
from a pre-v8 one). A finding is _new_ when its stable key is absent from the
baseline. With `require_non_negative_net_health = true`, CI also fails when a
run resolves fewer findings than it introduces (`net_health_delta < 0`).
`fail_on_new_severity` gates which new findings fail CI — `warning` (the
default) ignores new `info` findings (e.g. a new TODO), `info` fails on any new
finding. `base_ref` (or `--base <ref>`) restricts the check to files changed
since that ref. The transient `python.changed_source_without_related_test` rule
is excluded from the baseline comparison. CodeScent never runs tests; the
ratchet reads only its own scan output and the local git diff.

## Adaptive Findings

CodeScent can learn from how its findings are actually resolved. The
`[adaptive]` section turns the stored lifecycle verdicts into empirical per-rule
confidence and learned-suppression candidates:

```toml
[adaptive]
confidence_recalibration = true   # nudge confidence toward the empirical accept rate
learned_suppression = false       # opt-in; flag heavily-dismissed rule+scope pairs
min_sample_size = 8               # verdicts required before recalibrating (cold start below)
max_confidence_delta = 0.2        # most a rule's confidence can move
confidence_floor = 0.3            # recalibrated confidence never drops below this
suppression_threshold = 5         # dismissals in a rule+directory scope to flag suppression
```

For each rule, CodeScent counts `resolved` (accepted) versus `wontfix`/`ignored`
(rejected) findings; once at least `min_sample_size` verdicts exist it pulls the
rule's confidence toward that accept rate, bounded by `max_confidence_delta` and
never below `confidence_floor`. Below the sample size the base confidence is
used unchanged, so new repositories see no change. Inspect it with the
`get_calibration` MCP tool; `explain_score` carries the same block for a single
finding. The adjustment is a pure, deterministic function of `.codescent` state
— same verdicts in, same calibration out.

### Per-repo severity calibration (noise normalization)

The same `[adaptive]` block also drives a per-repo *noise baseline* used when
ranking diff-risk findings. CodeScent measures how often each rule fires across
the repo's stored findings (its firing rate = a rule's finding count ÷ total
findings) and turns that into a ranking weight: a rule that fires *everywhere*
is down-weighted, while a *rare* rule stands out. This keeps the backlog
signal-rich across very different repos — a TODO-heavy or large-file-heavy repo
no longer drowns its own rare-but-important findings — without any manual
threshold tuning.

- **Derived, not stored.** The baseline is recomputed from the findings already
  in `.codescent` (no new config key, no new table); the same findings always
  produce the same baseline.
- **Bounds reuse the existing knobs.** A rule's weight is
  `clamp(1 - max_confidence_delta × firing_rate, confidence_floor, 1)`. With the
  defaults a rule that is 100% of findings drops to `0.8`; a rare rule stays near
  `1.0`. Normalization only kicks in once the repo has at least `min_sample_size`
  findings and `confidence_recalibration` is enabled (below that, every weight is
  `1.0`, so small/new repos see no change).
- **Transparent, never hides findings.** The weight multiplies a finding's
  confidence *only for ordering*; it sinks noisy-rule findings within their
  severity/tier band rather than removing them. Severity stays the primary sort
  key and verified findings still rank above heuristic ones at equal severity.
  Inspect the baseline (per-rule firing count, rate, and weight) via
  `CalibrationService.get_noise_baseline()`.

## Coverage Report

Coverage ingestion reads an existing Cobertura XML report when present. By
default CodeScent looks for `coverage.xml` at the repository root. To use a
different repo-relative path, set `coverage_path` in `.codescent/config.toml`:

```toml
coverage_path = "reports/coverage.xml"
```

Paths outside the analyzed repository are ignored. CodeScent reads coverage
reports only; it does not run tests or generate coverage files.

## Subjective LLM Review (Privacy)

Everything in CodeScent is deterministic and offline by default. The optional
`subjective_review` MCP tool is the one exception, and it is **off unless you
turn it on**. It is gated by a single key in `.codescent/config.toml`:

```toml
[privacy]
allow_llm_review = false   # default
runtime_network = false    # default
```

With `allow_llm_review = false` (the default), `subjective_review` is a clean
no-op: no model is consulted, no data leaves, and no findings are produced.

Set `allow_llm_review = true` only when you intend to let your MCP client's own
LLM judge findings. Even then:

- The **CodeScent server makes no network call.** The request is sent back
  through the MCP session as an MCP **sampling** request, and your client's model
  produces the judgment.
- Only **finding metadata** (rule id, file path, severity, title, message) is
  sent — never whole source files — and that metadata is run through a secret/PII
  scrub first (per PRD 14.5 data minimization).
- Results are stored separately and labeled `subjective`; they never merge into
  or masquerade as the deterministic findings.

If the client cannot sample, the tool returns a clear "sampling unavailable"
result instead of failing.

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
- Invalid output format: use `--format json` or `--format markdown`. The `ci` and
  `review-diff` commands additionally accept `--format sarif` (SARIF 2.1.0 for
  GitHub code scanning) and `--format github` (inline PR annotation lines).
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
