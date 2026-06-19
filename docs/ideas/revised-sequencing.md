# Revised Sequencing: A Counter-Proposal

A counter-proposal to the build order in
[`implementation-plan-feedback-autofix-ratchet.md`](./implementation-plan-feedback-autofix-ratchet.md),
informed by the [`dogfooding-feedback.md`](./dogfooding-feedback.md) session.

**This does not reject the plan.** The ideas are good and the plan's designs are
sound and verified-accurate. It changes _what ships in what order_, and inserts
two items the plan omits.

---

## 1. The core argument

The current plan sequences **#6 ratchet → #1 adaptive → #3 safe-refactor**,
optimizing for _"adoption on a large legacy repo."_ That is a real goal — but
dogfooding shows the tool is not yet trustworthy enough on _any_ repo to earn
adoption:

1. It **can't bound its own report** (P0 bug — `get_smell_report` overflowed the
   context window at 338 KB). _Not in the plan._
2. It **cries wolf 1,270 times** because absolute thresholds are mis-tuned
   (`LARGE_FILE_LINES = 70` flags 70% of files). The plan treats this as part of
   adaptive learning (#1), i.e. something to _learn around_ rather than _fix_.
3. The backlog is a **flat list of 1,270 items**. The plan demotes clustering
   (#4) to honorable mentions.

You cannot build a credible autofix loop (#3) on a detector that overflows
context and flags most of the codebase. Fix the foundation first.

## 2. Proposed order

| Phase  | Item                                              | In plan?  | Size | Rationale                                                                              |
| ------ | ------------------------------------------------- | --------- | ---- | -------------------------------------------------------------------------------------- |
| **P0** | Bounded list/aggregate envelope                   | **No**    | S    | Bug. Blocks every list tool, current and future. See `boundedness-bug-fix.md`.         |
| **P1** | Threshold sanity + relative thresholds (#5 + #1c) | Partial   | S/M  | Stop generating noise before learning to suppress it.                                  |
| **P2** | Root-cause clustering + ROI / fix-order (#4)      | **No**    | M    | Turns a 1,270-item dump into an executable plan. Cheap; directly fixes the pain.       |
| **P3** | CI ratchet baseline (#6)                          | Yes (1st) | S/M  | Keep — adoption unlock, mostly scaffolded. But it follows P1 (don't ratchet on noise). |
| **P4** | Adaptive confidence + learned suppression (#1)    | Yes (2nd) | M    | Keep — but lower value once defaults are sane.                                         |
| **P5** | `verify_refactor` only (half of #3)               | Yes (3rd) | M/L  | High value, low risk. The deterministic safety net.                                    |
| **P6** | `propose_patch` / extract-function (rest of #3)   | Yes (3rd) | L    | Defer. Highest corruption risk; not what makes or breaks the tool.                     |

## 3. Phase detail and rationale

### P0 — Bounded envelope (new; ~Small)

The single highest-leverage change. One shared helper applied to
`get_smell_report`, `scan_code_health`, `get_backlog`, `get_regressions`,
`rescan` makes every list tool — present and future — safe. Reuses the
`find_symbol` / `ResultStoreService` / `retrieve_result` machinery that already
ships. Full spec in [`boundedness-bug-fix.md`](./boundedness-bug-fix.md).

### P1 — Threshold sanity first, then relative thresholds (split from #1; ~S/M)

**Status: shipped 2026-06-19 (both parts).**

- _Part 1 (absolute re-tune)._ Thresholds are now a configurable `[thresholds]`
  section (`MaintainabilityThresholds`) with sane production defaults; the
  historical aggressive values live behind a `strict()` profile used by the tiny
  fixtures/evals. On the CodeScent repo this dropped the scan from **1,208 → 470
  findings** (duplicate_literal −73%, large_function −78%, large_file −83%).
- _Part 2 (relative thresholds)._ Adds an IQR-based outlier-for-this-repo flavor
  (`python.relative_large_file` / `_function` / `_class`) over the repo's own
  size distribution, on top of the absolute floor. Conservative by construction
  (fires only on genuine outliers under the absolute threshold; silent when the
  floor already binds). On the CodeScent repo it adds 27 `relative_large_class`
  findings and nothing for files/functions (the absolute floor already binds
  there). See [configuration.md](../configuration.md#relative-thresholds).

The plan bundles relative thresholds inside the adaptive feature (#1c) and keeps
the absolute constants. Reverse the emphasis:

1. **Re-tune the absolute defaults** to values that don't flag the majority of a
   normal codebase. `LARGE_FILE_LINES = 70` should be ~300–400; `large_function`
   ~50; revisit `duplicate_literal` to ignore short/trivial literals (it is 40%
   of all findings). This is a config/constant change — hours, not weeks — and
   it is the biggest single noise reduction available.
2. **Then add relative ("large _for this repo_") thresholds** (#1c / #5) as an
   additional flavor on top of sane absolutes.

Ship P1 standalone and re-run the dogfooding scan; the finding count should drop
by an order of magnitude before any learning machinery exists.

### P2 — Clustering / ROI / fix-order (promoted #4; ~Medium)

**Status: shipped 2026-06-19.** New `get_improvement_plan` MCP tool
(`ImprovementPlanService`) clusters open findings by theme (rule + directory),
estimates effort (`S`/`M`/`L` with a cluster-economy model), health gain
(severity × confidence), and ROI (gain ÷ effort), then returns the clusters
ROI-ordered through the P0 bounded envelope. On the CodeScent repo it collapses
503 findings into 97 clusters with the cheapest high-impact work first — e.g.
"Consolidate 39 duplicate literal(s) in tests/integration" (ROI 3.86) ahead of
the structural refactors. Effort/ROI are deterministic functions of the finding
set. _Note:_ ordering is ROI-based; true dependency-graph topological ordering
(untangle cycles before extract-function) remains a follow-up.

The plan lists #4 in "honorable mentions," but it is precisely the experience an
agent hits: 510 `duplicate_literal` findings are really a handful of missing
constants modules. Clustering is a pure transform over existing findings plus
the import/call graph — cheap — and it converts `get_backlog` from a to-do dump
into an ordered campaign. After P0/P1 shrink the raw count, P2 makes the
remainder _actionable_. This is top-3 leverage, not an honorable mention.

### P3 — CI ratchet (#6, kept; ~S/M)

**Status: core shipped 2026-06-19.** `codescent ci --ratchet` now fails only on
_new_ findings versus an accepted baseline (`--update-baseline`), keyed by
stable finding key (migration 8 `finding_baseline`), never on the pre-existing
backlog. New findings are severity-gated (`fail_on_new_severity`, default
`warning`), and `--base <ref>` scopes the check to files changed since a git ref
(merge-base). This catches the resolve-one-add-one swap that the old count-based
ratchet missed. New `[ratchet]` config section; the transient
`changed_source_without_related_test` rule is excluded. _Deferred:_ the
coverage-delta / changed-line-coverage gate (axis c) and the net-health gate —
both need changed-line coverage diffing.

Keep the plan's design (stable-key baseline, diff scoping, coverage gate). One
change: it comes **after** P1, because "fail only on _new_ findings" is only
meaningful once "finding" means something. Ratcheting on mis-tuned detectors
just gates PRs on new noise.

### P4 — Adaptive (#1, kept but lower; ~Medium)

Confidence recalibration and learned suppression remain valuable, but their
marginal value drops sharply once P1 makes defaults sane and P2 clusters the
rest. Learned suppression is, in effect, a runtime band-aid over bad thresholds;
prefer fixing thresholds (P1) and keep suppression as the long-tail refinement
the plan already designed (opt-in, deferred-not-deleted, reversible — all good).

### P5 / P6 — Split the safe-refactor loop (#3)

The plan bundles `verify_refactor` and `propose_patch` (including
extract-function) into one phase. Split them:

- **P5 — `verify_refactor` only.** This is the deterministic safety net no LLM
  can self-certify, it secures _any_ agent edit (proposed or hand-written), and
  it is far lower risk because it only _reads_ two states. Highest
  value-per-risk in all of #3.
- **P6 — `propose_patch` / extract-function.** Defer. It is the highest
  corruption-risk surface in the whole roadmap, and a tool that today cannot
  bound its own report has not earned the right to emit source diffs. Revisit
  once P0–P5 land and the tool is demonstrably trustworthy.

## 4. What stays exactly as the plan has it

- All schema-migration, config-section, and public-surface-lockstep conventions
  (§4 of the plan) — adopt verbatim.
- The ratchet design internals (stable-key baseline, rename forgiveness,
  coverage gate) — unchanged, just resequenced after P1.
- The adaptive determinism guarantees (materialized-per-scan cache, explain
  everything, cold-start = no change) — unchanged.
- The extract-function refusal-gate safety contract — unchanged, just deferred.

## 5. One-line summary

> Keep the ideas and the designs. Fix boundedness (P0) and detector tuning (P1)
> before the adaptive/autofix work, promote clustering (P2) into the near-term
> build, and ship `verify_refactor` before `propose_patch`. Earn trust on the
> fundamentals before turbocharging.

## 6. Open questions for the maintainer

1. Are the low thresholds (`70`/`25`/`60`) intentional for a specific target
   (tiny-module style), or inherited defaults? This changes whether P1 is a
   re-tune or a config-surface decision.
2. Is `duplicate_literal` meant to fire on short literals (it is 40% of
   findings), or should it require a minimum length / occurrence count?
3. Is there appetite to ship P0+P1 as a fast "trust" release before resuming the
   feature roadmap?
