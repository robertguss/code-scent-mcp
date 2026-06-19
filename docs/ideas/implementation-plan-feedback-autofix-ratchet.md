# Implementation Plan: Adaptive Findings, Safe-Refactor Loop, and CI Ratchet

A combined, decision-complete design and implementation plan for three of the
ten ideas in [`./ideas.md`](./ideas.md):

- **Idea #6 — CI ratchet baseline** (built first; adoption unlock, mostly
  hardening existing scaffolding).
- **Idea #1 — Adaptive, self-calibrating findings** (built second; compounding
  signal-quality gain over data already captured).
- **Idea #3 — Safe-refactor loop: `propose_patch` + `verify_refactor`** (built
  third; the value-chasm crossing and the most ambitious work).

This is a design/PRD-style plan in the spirit of `docs/prd.md` and
`docs/implementation-plan.md` — comprehensive on design, data model, surface,
and testing, lighter on the per-todo `.omo/evidence/` ceremony.

---

## 1. Scope decisions (locked)

| Decision       | Choice                                                                                                                                                                                                                                         |
| -------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Documents      | Both in `docs/`; this plan is one combined document.                                                                                                                                                                                           |
| Idea #3 scope  | Full, **including extract-function** (phased internally; mechanical transforms first, extract-function last).                                                                                                                                  |
| Language scope | #1 and #6 cover **Python + TS/React/Next** for free (they operate on findings/coverage, which are language-agnostic). #3 `verify_refactor` covers both; #3 `propose_patch` is **Python-first**, with TS transforms as an explicit later phase. |
| Build order    | #6 → #1 → #3 (ascending size and risk).                                                                                                                                                                                                        |

**Non-goals (unchanged from product invariants).** No automatic source edits by
CodeScent itself; no runtime network by default; no execution of the target
project's tests/build; no HTTP/SSE transport or hosted service. `propose_patch`
_emits_ diffs but never applies them — the agent or human applies.

---

## 2. Guiding invariants

Every change in this plan must preserve CodeScent's five load-bearing
properties. These are acceptance criteria, not aspirations.

1. **Local-first / no runtime network.** All new analysis reads local files, the
   local `.codescent` SQLite state, and `git` (a local read). No network.
2. **Source-read-only.** CodeScent never mutates analyzed source.
   `verify_refactor` reads two states; `propose_patch` returns diff text.
   Applying a patch to produce an "after" tree for verification happens **in
   memory**, never on disk.
3. **Deterministic given state.** Output is a pure function of (repo bytes +
   `.codescent` state + git history). The adaptive features in #1 are
   deterministic _given the stored lifecycle history_ — same database, same
   output. No clocks or randomness influence findings.
4. **Bounded / token-aware output.** New tools return bounded payloads through
   the existing `ResponseEnvelope` machinery; no raw source dumps; respect
   `ContextOptions` budgets.
5. **Transparent.** Anything adaptive (a recalibrated confidence, a learned
   suppression, a ratchet failure, a refused patch) is explainable in the tool
   output. CodeScent never silently changes behavior the user cannot inspect.

---

## 3. Current-state grounding

What already exists, so the plan extends rather than reinvents.

| Capability              | Where it lives today                                                                                                                              | Gap this plan closes                                                                                                     |
| ----------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------ |
| CI run + thresholds     | `services/ci.py` `CiService.run(threshold, ratchet)`, `_passes`, `_risk_rank`                                                                     | Ratchet is coarse (per-file finding _count_); no stable-key new-finding detection, no coverage gate, no diff scoping.    |
| Baseline storage        | `health_baseline` table (schema migration 6): `file_path, finding_count, created_at`; `update_baseline` writer                                    | Count-based only; cannot answer "_which_ findings are new."                                                              |
| Finding lifecycle       | `findings.status`, `finding_events` table, `FindingStatus` enum (8 states), `services/findings.py` `mark_finding` / `record_verification`         | Recorded but never consumed: no calibration, no learned suppression.                                                     |
| Verification records    | `verification_runs` table (schema migration 7)                                                                                                    | Not yet fed back into scoring or used by a refactor loop.                                                                |
| Prioritization          | `services/findings.py` `_finding_priority` (severity, rule rank, `-_hotspot_score`), `_hotspot_score` = churn × evidence line count               | No adaptive confidence; no relative thresholds.                                                                          |
| Score explanation       | `services/reports.py` `explain_score` → `ScoreExplanation`; MCP `explain_score`                                                                   | No calibration breakdown.                                                                                                |
| Static thresholds       | `engine/rules/python.py` (`LARGE_FILE_LINES=70`, `LARGE_FUNCTION_LINES=25`, …), hardcoded `confidence` per `FindingSpec`                          | Absolute and global; not relative to the repo.                                                                           |
| Symbol index            | `symbols` table: `name, qualified_name, kind, signature, start_line, end_line, exported, confidence`; parsers `engine/parsers/python.py` (and TS) | Foundation for `verify_refactor` — exported-symbol + signature diffing — exists but is unused for behavior preservation. |
| Read-only source        | `engine/source_read.py`, line ranges in `engine/context/ranges.py`                                                                                | Reusable for in-memory patch application and range extraction.                                                           |
| Git access              | `services/git.py` (changed files, churn)                                                                                                          | Needs merge-base / `--base <ref>` diff scoping and bug-fix commit mining (the latter is idea #2, out of scope here).     |
| Config                  | `services/config.py` reads `.codescent/config.toml` → `ProjectConfig`; `coverage_path` already a field                                            | Needs new `[ratchet]` and `[adaptive]` sections.                                                                         |
| Public surface lockstep | `core/public_surface.py` (`PUBLIC_SURFACE`, `POST_MVP_MCP_TOOL_NAMES`, `REGISTERED_POST_MVP_MCP_TOOL_NAMES`), contract tests, `docs/mcp-tools.md` | New tools must be added in lockstep.                                                                                     |

---

## 4. Cross-cutting conventions

### 4.1 Adding an MCP tool or CLI command (the lockstep recipe)

For every new tool/command in this plan:

1. Implement the service in `src/codescent/services/` (thin MCP/CLI adapters
   call it). Keep adapters in `src/codescent/mcp/*_tools.py` /
   `src/codescent/cli/`.
2. Register in `core/public_surface.py`:
   - MCP tool: add `_registered_post_mvp_entry("<name>", "<group>")` to
     `PUBLIC_SURFACE.mcp_tools`, and add the name to both
     `POST_MVP_MCP_TOOL_NAMES` and `REGISTERED_POST_MVP_MCP_TOOL_NAMES`.
   - CLI command: add `_registered_post_mvp_cli_entry("<name>", "<group>")` to
     `PUBLIC_SURFACE.cli_commands`.
3. Wire the handler into the MCP server registration and the CLI dispatcher.
4. Update `docs/mcp-tools.md` (tool reference + group) and
   `docs/cli-reference.md` in the same change — the public-surface contract test
   asserts docs/surface parity.
5. Add a contract test that asserts the tool's presence, group, and
   bounded-output envelope shape.

### 4.2 Schema migrations

`storage/schema.py` holds `SCHEMA_VERSION` (currently **7**) and
`MIGRATION_STATEMENTS: dict[int, tuple[str, ...]]`. To add tables: bump
`SCHEMA_VERSION` and add the next integer key with `create table if not exists`
statements. Migrations are forward-only and idempotent. This plan introduces
versions **8** (ratchet) and **9** (adaptive); #3 reuses `verification_runs` and
adds an optional version **10** table for patch telemetry.

### 4.3 Config additions

Extend `ProjectConfig` (in `core/models.py`) with two new frozen sub-models and
teach `services/config.py` `_render_config` to serialize them. All new knobs
ship with conservative defaults so existing repos behave identically until opted
in.

### 4.4 Determinism and "explain everything"

Any value the user could be surprised by must be inspectable:

- Recalibrated confidence → shown in `explain_score` with the sample it came
  from.
- Learned suppression → finding remains visible as `deferred` with a reason and
  the evidence count that triggered it.
- Ratchet failure → the report lists the exact new findings / coverage delta.
- Refused patch → `propose_patch` returns the refusal reason and the blocking
  condition.

### 4.5 Testing strategy (applies to every phase)

Each phase ships with, and is gated by:

- **Unit tests** for the new pure logic (diffing, calibration math, AST
  analysis).
- **Integration tests** against `tests/fixtures/` repos with seeded state
  (baselines, lifecycle events, before/after trees).
- **Contract tests** for any new public surface (#4.1).
- **Determinism test** — identical state in, identical bytes out, run twice.
- **Source-read-only proof** extension — assert CodeScent mutated nothing under
  the analyzed tree (reuse `scripts/prove_source_read_only.py`).
- **No-network assertion** for the new code paths.
- Final gates unchanged: `uv run pytest`, `uv run ruff check .`,
  `uv run ruff format --check .`, `uv run basedpyright`, MCP smoke, real-repo
  smoke, deterministic eval.

---

## 5. Phase 1 — CI Ratchet (Idea #6)

**Goal.** Make `codescent ci` fail only on _new_ debt and on coverage/health
regressions in changed code, so the tool is adoptable on a large legacy repo.

**Sizing — Small/Medium.** Mostly completing scaffolding that exists.

### 5.1 Problem and current state

`CiService.run(threshold, ratchet=False)` already scans, computes a risk level,
and — when `ratchet=True` — compares per-file finding counts against the
`health_baseline` table, flagging a file `regressed` when
`finding_count > baseline_count`. This is real but coarse: it cannot say _which_
findings are new, it ignores coverage, and it evaluates the whole repo rather
than the diff. Net result: a file that resolves one finding and introduces a
different one looks unchanged, and a huge legacy repo still trips on totals.

### 5.2 Design

Upgrade the ratchet along three axes.

**(a) Stable-key baseline.** Capture the baseline as the _set of finding
`stable_key`s_ at baseline time (the `stable_key` is the deterministic
fingerprint built in `engine/rules/model.py`). A finding is **new** iff its
`stable_key` is not in the baseline set. This is exact and immune to count
coincidences.

**(b) Diff scoping.** Add `--base <ref>` (default: merge-base with the repo's
default branch). Restrict ratchet evaluation to findings in files changed since
`<ref>`, via `services/git.py`. This keeps the gate focused on the PR and avoids
tripping on unrelated drift.

**(c) Coverage and net-health deltas.** If `coverage_path` (already in config)
resolves to a coverage report, compute changed-line coverage and fail if it
falls below `coverage_floor` (or below baseline). Separately report
`net_health_delta = findings_resolved − findings_created` for the diff so a PR
can require non-negative movement.

CodeScent still does not run tests. The coverage report is produced by the
user's own CI step _before_ `codescent ci`; the gate only reads it. This
preserves the no-execute invariant and is documented as a prerequisite.

### 5.3 Data model (migration 8)

```sql
-- migration 8
create table if not exists finding_baseline (
    id integer primary key,
    stable_key text not null unique,
    rule_id text not null,
    file_path text not null,
    severity text not null,
    captured_scan_id text references scan_runs(id),
    created_at text not null
);
create index if not exists idx_finding_baseline_file on finding_baseline(file_path);
```

`health_baseline` (count-based) is retained for backward compatibility and the
existing `changed_file_health` summary; `finding_baseline` is the new source of
truth for "new finding" decisions. `update_baseline` writes both.

### 5.4 Surface

- **CLI** (extend the existing `ci` and add a `baseline` command):
  - `codescent ci --ratchet --base <ref> [--coverage-floor 0.0] [--format json]`
  - `codescent baseline accept [--base <ref>]` — snapshot current findings as
    the baseline (writes `finding_baseline` + `health_baseline`).
  - `codescent baseline show [--format json]` — inspect the current baseline.
- **MCP** (optional, for agent-driven PR checks): `review_diff_risk` and
  `get_changed_file_health` already exist; add `ratchet_status` fields to their
  payloads rather than a brand-new tool, to keep the surface small.
- **Config** — new `[ratchet]` section:

```toml
[ratchet]
enabled = false            # opt-in; preserves current default behavior
mode = "stable_key"        # "stable_key" | "count" (legacy)
base_ref = "origin/main"   # default merge-base target
fail_on_new_severity = "warning"  # fail if any new finding >= this severity
coverage_floor = 0.0       # 0.0 disables the coverage gate
require_non_negative_net_health = false
```

- **Report contract** — extend `CiReport` with:
  `new_findings: tuple[FindingSummary, ...]`, `resolved_findings: tuple[...]`,
  `coverage_delta: float | None`, `net_health_delta: int`,
  `base_ref: str | None`. `ok` becomes:
  `_passes(threshold, risk_level) AND no disallowed new findings AND coverage gate AND (net-health gate if required)`.

### 5.5 Algorithm

```text
run_ratchet(threshold, base_ref, coverage_floor):
    scan        = CodeHealthService.scan()          # current findings
    baseline    = load_finding_baseline()           # set[stable_key]
    changed     = git_changed_files(base_ref)        # set[path]
    in_scope    = [f for f in scan.findings if f.file_path in changed]   # or all if base_ref is None
    new         = [f for f in in_scope if f.stable_key not in baseline]
    blocking    = [f for f in new if rank(f.severity) >= rank(fail_on_new_severity)]
    cov_delta   = changed_line_coverage(coverage_path, changed) if coverage_path else None
    cov_ok      = (cov_delta is None) or (cov_delta >= coverage_floor)
    net_health  = scan.findings_resolved - scan.findings_created
    ok          = base_threshold_passes(threshold) and not blocking and cov_ok and net_health_ok
    return CiReport(ok, new_findings=new, coverage_delta=cov_delta, net_health_delta=net_health, ...)
```

### 5.6 Edge cases

- **First run / no baseline.** No `finding_baseline` rows ⇒ ratchet is a no-op
  that _recommends_ `codescent baseline accept` (does not fail the build).
- **Renames.** `stable_key` embeds `file_path`, so a moved finding can look
  "new." Mitigated by diff scoping (a pure rename touches the file, but the
  finding's content fingerprint is unchanged) — add a secondary match on
  `(rule_id, symbol, content-fingerprint)` ignoring `file_path` to forgive
  rename-only churn. Documented as a known limitation with the mitigation on.
- **Shallow clones / missing merge-base.** Fall back to `--base` HEAD~1 or
  whole-repo mode with a warning; never crash.
- **No coverage report.** Coverage gate disabled with a one-line note;
  everything else still runs.
- **Baseline staleness.** `baseline show` reports `created_at` and the scan id
  so staleness is visible.

### 5.7 Acceptance

- Fixture repo with a seeded baseline: adding one new `warning` finding fails
  CI; resolving an old finding and adding none passes; pre-existing backlog
  never fails on its own.
- Coverage gate fails when changed-line coverage < floor, passes otherwise.
- Determinism, source-read-only, and no-network proofs extended to the ratchet
  path. Contract test for the extended `CiReport` JSON shape.

---

## 6. Phase 2 — Adaptive, self-calibrating findings (Idea #1)

**Goal.** Let CodeScent learn from how its findings are actually resolved so it
gets quieter and more accurate per repo — deterministically and transparently.

**Sizing — Medium.** Pure analysis over already-captured data + new config and a
small surface.

### 6.1 Problem and current state

`finding_events`, `findings.status`, `scan_runs`, and `verification_runs` record
a rich history of verdicts, but nothing consumes it. Thresholds
(`LARGE_FILE_LINES = 70`, …) and per-finding `confidence` are global constants.

### 6.2 Design — three mechanisms

**(a) Empirical confidence recalibration.** For each `rule_id`, derive an
acceptance rate from lifecycle history:

```text
accepted   = count(events where finding of rule transitioned to RESOLVED via real fix)
rejected   = count(events where finding of rule transitioned to WONTFIX or IGNORED)
sample     = accepted + rejected
if sample < min_sample_size:        adjusted = base_confidence      # cold start: no change
else:
    accept_rate = accepted / sample
    # pull confidence toward the empirical accept rate, bounded
    adjusted = clamp(base_confidence + max_confidence_delta * (accept_rate - 0.5) * 2,
                     low=confidence_floor, high=base_confidence_cap)
```

The adjusted confidence is what `explain_score` reports and what feeds
prioritization. It is a deterministic function of the database.

**(b) Learned suppression.** When, within a directory scope, findings of a given
`rule_id` are marked `WONTFIX`/`IGNORED` at least `suppression_threshold` times,
new sibling findings of that `(rule_id, scope)` are auto-set to `DEFERRED` with
`suggested_action` annotated
`learned suppression (N prior dismissals in <scope>)`. Crucially: deferred, not
deleted — they still appear in `get_backlog` under a filter, and a single
`mark_finding ... --status open` (or removing the rule from the suppression set)
reverses it. Off by default; opt-in via config.

**(c) Relative thresholds.** Compute, per language, the repo's own distribution
of the size metrics (file lines, function span, class span) and emit an
_additional_ "outlier-for-this-repo" finding flavor (e.g., p90/IQR-based)
alongside the absolute-threshold finding. The absolute thresholds remain the
floor; relative thresholds add repo-aware signal. Distribution stats are
recomputed at scan time and stored for explainability.

### 6.3 Data model (migration 9)

Two options were considered:

- **Compute-on-read** from `finding_events` (no new table). Cheapest, always
  fresh, but recomputed each call.
- **Materialized snapshot** table, refreshed on `scan`/`rescan`.

**Recommendation:** materialize, because prioritization touches calibration on
every `get_next_improvement`/`get_backlog` call and recomputing aggregates per
call is wasteful. Keep it a cache derived purely from `finding_events`, rebuilt
on scan, so determinism holds.

```sql
-- migration 9
create table if not exists rule_calibration (
    rule_id text not null,
    scope text not null default '',     -- '' = repo-wide; else directory prefix
    accepted_count integer not null default 0,
    rejected_count integer not null default 0,
    sample_size integer not null default 0,
    adjusted_confidence real,
    suppressed integer not null default 0,
    updated_at text not null,
    primary key (rule_id, scope)
);
create table if not exists metric_distribution (
    language text not null,
    metric text not null,               -- 'file_lines' | 'function_span' | 'class_span'
    p50 real not null, p90 real not null, p95 real not null,
    sample_size integer not null,
    updated_at text not null,
    primary key (language, metric)
);
```

### 6.4 Surface

- **MCP** — new `get_calibration` (group `health`): returns per-rule sample
  size, accept rate, adjusted confidence, suppression status, and the metric
  distributions. Registered via the §4.1 lockstep.
- **Extend `explain_score`** payload with a `calibration` block: base vs
  adjusted confidence, the sample it came from, and whether a relative-threshold
  outlier contributed.
- **CLI** — `codescent calibration [--format json]` to inspect;
  `codescent rules` gains `--reset-calibration`.
- **Config** — new `[adaptive]` section:

```toml
[adaptive]
confidence_recalibration = true
relative_thresholds = true
learned_suppression = false       # opt-in; conservative default
min_sample_size = 8
max_confidence_delta = 0.2
confidence_floor = 0.3
suppression_threshold = 5
```

- **Prioritization integration.** Extend `_finding_priority` in
  `services/findings.py` to use adjusted confidence as a tiebreaker and to sink
  `DEFERRED`/suppressed findings, without disturbing the existing severity →
  rule-rank → hotspot ordering for everything else.

### 6.5 Edge cases

- **Cold start.** `sample < min_sample_size` ⇒ no adjustment; behaves exactly
  like today. New repos see zero behavior change.
- **Tiny repos.** `min_sample_size` guard prevents overfitting to two events.
- **Adversarial / oscillation.** `confidence_floor` keeps a chronically
  dismissed but occasionally real rule from vanishing; bounded
  `max_confidence_delta` and a materialized-per-scan refresh (not per-event)
  avoid thrash.
- **Interaction with regression tracking.** Calibration reads `finding_events`
  but must not change how `resolved`/`regressed` are computed in
  `services/code_health.py`; it is strictly additive to scoring.
- **Suppression safety.** Suppressed findings remain queryable and reversible;
  `explain_score` always shows why something was deferred.

### 6.6 Acceptance

- Seed lifecycle events for a fixture: a rule with 8 `wontfix`/0 `resolved`
  shows a reduced adjusted confidence and (with suppression on) defers new
  siblings; a rule with high resolve rate is unchanged or boosted.
- Determinism: same `finding_events` → identical calibration table and identical
  `explain_score` output across two runs.
- Relative-threshold outlier surfaces a finding on a file that is large for the
  repo even when below the absolute threshold (and vice-versa).
- Cold-start test proves zero behavior change with an empty history.

---

## 7. Phase 3 — Safe-refactor loop (Idea #3)

**Goal.** Cross the "what's wrong" → "here's the provably safe fix" chasm with
two tools — `verify_refactor` (prove behavior preserved) and `propose_patch`
(emit a diff) — without CodeScent ever writing analyzed source.

**Sizing — Large.** New behavior-preservation logic plus AST transforms;
extract-function is the single hardest piece in this plan.

### 7.1 Problem and current state

CodeScent is read-only and gives advice (`plan_refactor`, `suggest_tests`) but
agents then apply edits blind, with no deterministic safety check. The
foundations — `engine/parsers/python.py`, the `symbols` table (`exported`,
`signature`, `kind`, `start_line`, `end_line`), `engine/rules/dead_code.py`,
`engine/rules/structural_duplicates.py`, `engine/source_read.py`, and
`verification_runs` — exist, but there is no behavior-preservation module and no
patch generator. (Note: `core/preservation.py` is about bounded-output item
preservation, and `core/public_surface.py` is CodeScent's own tool registry —
neither is the basis for this; the symbol indexer is.)

### 7.2 Internal phasing

1. **7.4 `verify_refactor`** (Python + TS) — ship first; it secures _any_ edit,
   including an agent's own hand-written change, and is the self-check
   `propose_patch` will call.
2. **7.5 `propose_patch` — mechanical transforms** (Python): literal → named
   constant, dead-code removal, add/remove import.
3. **7.6 `propose_patch` — extract-function** (Python), guarded by
   `verify_refactor`.
4. TS `propose_patch` transforms — explicitly deferred to a follow-on plan.

### 7.3 The read-only "after" model

`verify_refactor` compares a **before** and an **after** tree. Sources of
"after":

- two git refs, or HEAD vs working tree (read both read-only); or
- a supplied patch: apply it to the **in-memory** text of the affected files and
  parse the result. Never write to disk.

`propose_patch` produces unified-diff text only; it self-verifies by applying
the diff in memory and running `verify_refactor` against the result before
returning.

### 7.4 `verify_refactor`

**Input:** repo root, a `before`/`after` selector (refs, or `working_tree`, or a
`patch` string), optional `scope` (file or symbol), and an optional declared
`transform_kind` (`extract_function`, `rename_local`, `dedup_literal`,
`remove_dead_code`, `add_import`, `generic`).

**Checks (all deterministic):**

1. **Public-symbol set.** Diff the set of `exported` symbols (from the parser /
   `symbols` extraction) before vs after. Any added/removed/renamed exported
   symbol is a preservation violation unless the declared transform allows it.
2. **Signature stability.** For surviving exported symbols, diff `signature`.
3. **Structural delta bounds.** Compare the AST shape outside the declared edit
   region; a `generic` verify only warns, a declared mechanical transform
   asserts the change is confined to its expected footprint.
4. **New-branch / new-untested check.** Count control-flow branches
   before/after; flag net-new branches (a hook into idea #5's complexity metric
   and the coverage data) so "refactors" that quietly add logic are caught.

**Output:**
`{ preserved: bool, violations: [...], warnings: [...], public_surface_diff: {...}, transform_kind, confidence }`,
bounded. On `preserved=false`, the violations are concrete and cite symbol +
line.

**Persistence:** record the verdict in `verification_runs` (already present) so
the loop and `explain_score` can reference it.

### 7.5 `propose_patch` — mechanical transforms (Python first)

**Input:** a `finding_id` (or `rule_id` + target), repo root, options.
**Output:** a unified diff (bounded), plus a `verify_refactor` self-check
result; or a structured **refusal** with the blocking reason.

**Formatting-preservation decision.** Python's `ast` discards comments and
layout. For faithful diffs, use **AST analysis for _decisions_, source-slicing
for _edits_** — compute line/column ranges from the parser, then splice raw
source text. This preserves all formatting outside the edited region, needs no
new dependency, and reuses `engine/source_read.py` + `engine/context/ranges.py`.
(Adopt `libcst` only if transforms outgrow slicing; recorded as an open decision
in §9.)

Transforms:

- **literal → named constant.** Source: `python.duplicate_literals` findings.
  Insert a module-level constant, replace each occurrence, choose a
  non-colliding UPPER_SNAKE name. Refuse on dynamic/f-string contexts.
- **dead-code removal.** Source: `engine/rules/dead_code.py`. Delete the unused
  symbol's line range; verify nothing references it (cross-check
  `symbol_references` / `call_edges`). Refuse if any inbound reference exists or
  the symbol is `exported`.
- **add/remove import.** Add a missing import (from an unresolved reference) or
  remove a provably-unused one, respecting existing import grouping.

### 7.6 `propose_patch` — extract-function (Python)

The ambitious piece. Given a finding (e.g., `python.large_function`) and a
selected statement range:

```text
extract_function(file, start_line, end_line):
    fn   = enclosing_function(start_line, end_line)        # must be fully inside one function
    body = ast_nodes_in_range(fn, start_line, end_line)

    # --- refusal gates (refuse rather than risk corruption) ---
    refuse_if range is not a contiguous statement list at one block level
    refuse_if body contains  return / yield / await / break / continue / global / nonlocal
              that crosses the extraction boundary
    refuse_if body references a name bound by a comprehension/with/except target it doesn't own
    refuse_if extraction would capture `self`/`cls` in a way that changes semantics (allow as param)

    # --- def-use / variable-capture analysis ---
    reads_before  = names read in body that are bound earlier in fn      -> become parameters
    writes_in     = names assigned in body
    used_after    = writes_in that are read in fn after end_line          -> become return values
    params  = ordered(reads_before)
    returns = ordered(used_after)

    # --- render via source-slicing (formatting preserved) ---
    new_fn  = "def {name}({params}){ret_hint}:\n" + reindent(source[start:end]) +
              ("\n    return " + ",".join(returns) if returns else "")
    call    = ("{ ', '.join(returns) } = " if returns else "") + "{name}({args})"
    diff    = splice(file, replace=source[start:end] with call, insert new_fn above fn)

    # --- mandatory self-check ---
    result  = verify_refactor(before=file, after=apply_in_memory(diff),
                              transform_kind="extract_function", scope=fn)
    if not result.preserved: return Refusal(result.violations)
    return Patch(diff, verify=result)
```

The refusal gates are the safety contract: when extraction is not provably
behavior-preserving, CodeScent returns _why_, not a guess. This is what makes an
ambitious transform trustworthy in an autonomous loop.

### 7.7 Loop integration

Wire the existing `next_tools` hints into a coherent campaign:

`get_next_improvement → get_finding_context → propose_patch → (agent applies) → verify_refactor → rescan → record_verification → mark_finding`.

`plan_refactor` gains a pointer to `propose_patch` when a mechanical transform
is available; `verify_refactor` is recommended after any agent edit, proposed or
not.

### 7.8 Data model

- Reuse `verification_runs` for verdicts.
- Optional **migration 10** `patch_proposals` table
  (`id, finding_id, transform_kind, diff_hash, verified, created_at`) for
  telemetry/retrieval via the existing `stored_results` pattern. Optional; not
  required for function.

### 7.9 Surface

- **MCP** — `propose_patch` (group `planning`), `verify_refactor` (group
  `planning`).
- **CLI** — `codescent propose-patch --finding <id>` and
  `codescent verify-refactor --base <ref>` (or `--patch <file>`).
- Registered via §4.1 lockstep; `docs/mcp-tools.md` + `docs/cli-reference.md`
  updated in the same change.

### 7.10 Edge cases and refusals

- Comments/formatting → preserved by source-slicing.
- Name collisions for the extracted function or new constant →
  suffix-disambiguate or refuse.
- Multiple/early returns, generators, async, closures over loop variables,
  decorators → refusal gates above.
- Type annotations → carried through where present; never invented.
- Non-parseable / syntactically broken file → refuse cleanly with a parse error.
- TS transforms → `verify_refactor` works on TS; `propose_patch` TS transforms
  are deferred and the tool says so for `.ts/.tsx` targets.

### 7.11 Acceptance

- Golden before/after fixtures per transform; applying the proposed diff yields
  a file that (a) parses, (b) passes `verify_refactor`, (c) has an unchanged
  public surface.
- **Property test:** for a corpus of functions, every _non-refused_
  extract-function proposal round-trips through `verify_refactor` as
  `preserved=true`; refusals are never silently wrong (manual-labeled refusal
  fixtures stay refused).
- Refusal coverage for each blocking condition.
- Source-read-only proof: `propose_patch`/`verify_refactor` mutate nothing under
  the analyzed tree (in-memory apply only). Determinism and no-network proofs
  extended.

---

## 8. Risks and mitigations

| Risk                                                        | Phase | Mitigation                                                                                                             |
| ----------------------------------------------------------- | ----- | ---------------------------------------------------------------------------------------------------------------------- |
| Ratchet false "new" on renames                              | #6    | Diff scoping + secondary content-fingerprint match ignoring `file_path`; documented limitation.                        |
| Coverage gate depends on a report CodeScent doesn't produce | #6    | Read-only consumption; gate auto-disables with a note when absent; prerequisite documented.                            |
| Adaptive features feel non-deterministic                    | #1    | Deterministic _given state_; materialized-per-scan cache; everything shown in `explain_score`; cold-start = no change. |
| Learned suppression hides a real issue                      | #1    | Off by default; deferred not deleted; reversible; floor on confidence; visible reason.                                 |
| Extract-function corrupts code                              | #3    | Refuse-by-default gates + mandatory `verify_refactor` self-check before returning any patch.                           |
| `ast` loses formatting in diffs                             | #3    | Source-slicing for edits; AST only for analysis; `libcst` held as an option.                                           |
| Surface drift vs docs                                       | all   | Public-surface lockstep contract test (§4.1) fails the build on mismatch.                                              |
| Scope creep into idea #2 (bug-fix mining)                   | #6/#1 | Explicitly out of scope; ratchet uses only diff + baseline, not commit-message mining.                                 |

---

## 9. Open design decisions (with recommendations)

1. **Patch fidelity library.** Source-slicing (recommended, no new dep) vs
   `libcst` (cleaner for complex transforms, adds a dependency). _Recommend
   slicing for v1; revisit for TS and for rename-across-files._
2. **Calibration storage.** Materialized `rule_calibration` (recommended) vs
   compute-on-read. _Recommend materialized for prioritization performance._
3. **Learned-suppression default.** _Recommend off by default_ (opt-in), given
   the product's trust posture; confidence recalibration and relative thresholds
   on by default since they never hide findings.
4. **Ratchet baseline scope.** Per-branch vs single repo baseline. _Recommend a
   single committed baseline plus `--base` diff scoping for v1; per-branch later
   if monorepo demand appears._
5. **Rename forgiveness.** Whether to ship the content-fingerprint rename match
   in v1. _Recommend yes — it removes the most common false positive._

---

## 10. Sequencing, milestones, and sizing

| Milestone                                            | Idea | Size | Depends on                             |
| ---------------------------------------------------- | ---- | ---- | -------------------------------------- |
| M1: stable-key ratchet + `baseline` CLI              | #6   | S    | existing `health_baseline`/`CiService` |
| M2: coverage + net-health gates, diff scoping        | #6   | S/M  | M1, `services/git.py`                  |
| M3: confidence recalibration + `explain_score` block | #1   | M    | `finding_events`                       |
| M4: relative thresholds + `get_calibration`          | #1   | M    | M3                                     |
| M5: learned suppression (opt-in)                     | #1   | S    | M3                                     |
| M6: `verify_refactor` (Python + TS)                  | #3   | M/L  | symbol index                           |
| M7: `propose_patch` mechanical transforms            | #3   | M    | M6                                     |
| M8: `propose_patch` extract-function                 | #3   | L    | M6, M7                                 |
| M9: loop wiring + docs/contract lockstep             | #3   | S    | M6–M8                                  |

Ship M1–M2 first (adoption), then M3–M5 (signal quality), then M6–M9 (the
safe-refactor loop). Each milestone is independently shippable and gated by
§4.5.

---

## 11. Backward compatibility and rollout

- All new config sections default to today's behavior:
  `[ratchet] enabled = false`, `[adaptive] learned_suppression = false`. A repo
  that does nothing sees no change.
- Confidence recalibration and relative thresholds are additive to scoring and
  fully explainable; they can be disabled in `[adaptive]`.
- New schema versions (8, 9, optional 10) are forward-only
  `create table if not exists` migrations; existing `.codescent` databases
  upgrade in place.
- New MCP tools are post-MVP registered entries; no existing tool changes shape.
  `explain_score` and the CI/diff-risk payloads gain _additive_ fields only.

---

## 12. Related documents

- [`docs/ideas.md`](./ideas.md) — the ten ideas this plan draws from.
- [`docs/mcp-tools.md`](./mcp-tools.md) — tool surface (update in lockstep).
- [`docs/cli-reference.md`](./cli-reference.md) — CLI surface (update in
  lockstep).
- [`docs/configuration.md`](./configuration.md) — `.codescent/` config (add the
  new sections).
- [`docs/workflows.md`](./workflows.md) — improvement loop (extend with the
  safe-refactor loop).
- [`docs/architecture.md`](./architecture.md) — services, engine, storage
  layers.
