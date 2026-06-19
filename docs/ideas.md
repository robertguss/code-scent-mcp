# CodeScent: Ten High-Leverage Ideas

This document captures ten ideas for making CodeScent dramatically more
compelling, useful, intuitive, versatile, powerful, robust, and reliable for the
AI coding agents (and humans) that consume it.

It is a curated shortlist. Roughly a hundred candidates were considered across
nine areas — feedback/learning loops, git-history mining, new detectors, agent-
loop ergonomics, autofix bridges, architecture intelligence, diff/CI gating,
durable memory, and reporting. The ten below survived a single filter:

> Does it exploit CodeScent's actual DNA — **deterministic, local-first,
> source-read-only, bounded/token-aware, MCP-first, agent-oriented** — as an
> *advantage* rather than fighting it, is it high-leverage, and is it
> pragmatically buildable on what already lives under `.codescent/`?

Ideas are ranked by leverage. Each entry states the insight, the concrete
mechanism (tools and data sources), why CodeScent specifically wins, and a
feasibility note grounded in the current code.

A companion implementation plan for the top three (#1, #3, #6) lives at
[`docs/implementation-plan-feedback-autofix-ratchet.md`](./implementation-plan-feedback-autofix-ratchet.md).

---

## 1. Adaptive, self-calibrating findings

**Insight.** Today the rules are static: `LARGE_FILE_LINES = 70` is an arbitrary
constant in `engine/rules/python.py`, and `confidence = 0.9` is hardcoded into
each `FindingSpec`. Meanwhile CodeScent already records every human/agent verdict
in SQLite — the `finding_events` table (lifecycle transitions), the `findings`
status column, the `scan_runs` history, and the `verification_runs` table. None
of that feedback flows back into what CodeScent surfaces. Close the loop.

**Mechanism.**

- **Empirical confidence recalibration.** For each `rule_id`, compute this repo's
  historical resolve-vs-`wontfix`/`ignored` ratio from `finding_events` and
  down- or up-weight that rule's confidence. Confidence becomes empirical instead
  of guessed, and the adjustment is surfaced in `explain_score`.
- **Learned suppression.** When findings of a rule in a directory scope are
  repeatedly marked `wontfix`/`ignored`, auto-defer their siblings — but visibly,
  as `deferred` with reason "learned suppression," never deleted, always
  reversible.
- **Relative thresholds.** Flag the file that is large *for this repo* (e.g., the
  p90 of the codebase's own size distribution), not a magic 70 lines.

**Why CodeScent wins.** Signal-to-noise is the number-one reason code-health
tools get muted. CodeScent is the rare tool with a persistent, structured record
of what its users actually did with each finding — so it can get quieter and
smarter the more it is used. The adaptation stays a pure, deterministic function
of `.codescent` state, preserving reproducibility.

**Feasibility — high.** Pure analysis over tables that already exist. No new
indexing, no network.

---

## 2. Git-history risk intelligence

**Insight.** `_hotspot_score` in `services/findings.py` already multiplies churn
by evidence size, so CodeScent touches git history — but only shallowly. The
local git log (fully offline, fully deterministic) is a goldmine of signal the
AST physically cannot see.

**Mechanism.** Mine the log for three new, durable signals and fold them into
prioritization and a new `risk.*` finding class:

- **Defect hotspots** — files recurring in `fix`/revert/bugfix commits.
  Historical defect density is the strongest known predictor of future bugs
  (Google, Microsoft research), beating any static metric.
- **Hidden coupling** — files that always change together but share no import
  edge: shotgun-surgery risk, invisible to structural analysis.
- **Bus-factor / knowledge risk** — complex files with a single author.

**Why CodeScent wins.** This is a whole predictive dimension above static
analysis, it costs no new infrastructure, and it stays inside the local/no-
network guarantee — `git log` is just another read.

**Feasibility — high.** Builds on the existing `services/git.py` surface.

---

## 3. The safe-refactor loop: `propose_patch` + `verify_refactor`

**Insight.** The biggest value chasm in any code-health tool is "tells me what's
wrong" → "hands me the fix that's provably safe." CodeScent can cross it without
breaking its sacred source-read-only constraint.

**Mechanism.**

- **`propose_patch`** returns a ready-to-apply **unified diff suggestion** for a
  finding (literal → named constant, dead-code removal, add/remove import, and —
  ambitiously — extract-function with variable-capture analysis). CodeScent emits
  the diff; the *agent or human* applies it. CodeScent itself still never writes
  analyzed source.
- **`verify_refactor`** proves an edit (CodeScent's proposal *or* any agent's own
  hand-written change) preserved behavior: the set of exported symbols and their
  signatures is unchanged, structural deltas are within the claimed transform,
  and no new untested branch slipped in. When it cannot prove safety, it
  **refuses** rather than bless a risky change.

**Why CodeScent wins.** `verify_refactor` is the deterministic safety net no LLM
can self-certify — exactly the assurance an autonomous agent loop is missing. And
`propose_patch` turns CodeScent from critic into collaborator while keeping the
trust model intact.

**Feasibility — medium (the most ambitious idea here).** *Correction to the
initial pitch:* the foundation is the existing **symbol indexer** — the `symbols`
table already stores `exported` and `signature` — plus the language parsers, not
`core/preservation.py` (which governs bounded-output preservation) or
`core/public_surface.py` (CodeScent's own tool registry). The behavior-
preservation logic is genuinely new work, and extract-function is the single
hardest piece in all three top ideas.

---

## 4. Root-cause clustering with ROI and fix-order

**Insight.** Agents drown in flat finding lists and end up fixing symptoms. A
backlog of two hundred findings is often a dozen underlying problems.

**Mechanism.** Cluster findings into themes ("12 duplicate-literal findings = one
missing constants module"), estimate effort S/M/L from evidence, compute
**ROI = health-gain ÷ effort**, and emit a **topologically ordered** plan
(untangle the dependency cycle *before* extracting the function). `get_backlog`
stops being a to-do dump and becomes an executable improvement campaign.

**Why CodeScent wins.** It already has the findings and the call/import graph; it
only needs to organize them. This is the difference between handing an agent a
list and handing it a plan.

**Feasibility — high.** A transform over existing findings plus the graph.

---

## 5. The composite "danger zone" score

**Insight.** Line count is a weak proxy for complexity, and any single metric is
easy to dismiss. The empirically dangerous code is the *intersection*: complex
**and** frequently changed **and** untested.

**Mechanism.** Add genuine **cyclomatic/cognitive complexity** and **nesting-
depth** detectors over the AST CodeScent already parses (~200 LOC per language),
then fuse complexity × churn × (1 − coverage), using the `coverage_path` config
that already exists, into one score that drives `get_next_improvement` and the PR
risk gate.

**Why CodeScent wins.** It already has the parser, the churn signal, and the
coverage hook. Fusing them surfaces the precise places teams get burned.

**Feasibility — high.**

---

## 6. The CI "ratchet" baseline

**Insight.** Point a code-health tool at a mature repo and it emits a mountain of
red that everyone mutes. The fix is to fail only on *new* debt.

**Mechanism.** Fail `codescent ci` only on net-new findings and on coverage/
health regressions *in changed lines* — never on the pre-existing backlog. Every
PR ratchets health upward instead of drowning in legacy noise.

**Why CodeScent wins.** This is the single feature that makes the tool adoptable
on a large legacy codebase (the lint-baseline / "new code only" pattern). And
it is nearly free here: schema migration 6 already created a `health_baseline`
table and `CiService.run()` already accepts a `ratchet` flag — but the current
baseline is coarse (per-file finding *count*). The work is to deepen it to
stable-key-level new-finding detection, add coverage-delta gating, and scope to
the merge-base diff.

**Feasibility — high.** Mostly completing and hardening machinery that is already
scaffolded.

---

## 7. Persistent codebase memory

**Insight.** Every agent session starts from zero. CodeScent is uniquely placed
to be the codebase's long-term memory because it already persists structured
state per repo.

**Mechanism.** A read/write knowledge store under `.codescent/`, keyed to files
and symbols, holding durable notes: architectural decisions, gotchas, "this looks
wrong but is intentional because…", canonical examples — including the *reasons*
captured by idea #1's learned suppressions. It surfaces automatically inside the
existing bounded context packs and the `start_task` brief.

**Why CodeScent wins.** This is the natural payoff of being MCP-first and stateful
per repo. No stateless linter can offer it.

**Feasibility — medium.** SQLite writes plus injection into the existing context-
pack surface.

---

## 8. Convention inference and "show me the canonical example"

**Insight.** A fix that ignores house style gets bounced in review. The repo
already contains its own conventions; CodeScent can read them out.

**Mechanism.** Deterministically infer the repo's conventions (error-handling
pattern, test layout, naming, the canonical shape of an API route / model /
component) and add `get_canonical_example`, which returns the best existing
instance of a pattern. The agent then writes code that matches the codebase
instead of generic code.

**Why CodeScent wins.** Pure local analysis over the index it already builds, and
it directly raises the merge-rate of agent-authored changes.

**Feasibility — medium.**

---

## 9. Deterministic security and correctness smells

**Insight.** CodeScent already has AST parsing and a rule engine; it is one rule
pack away from feeling safety-critical rather than merely tidy.

**Mechanism.** Add the rules people viscerally care about, all deterministic and
fully offline: hardcoded-secret patterns, `subprocess(shell=True)`,
`eval`/`exec`/`pickle.loads`, mutable default arguments, bare `except: pass`,
`== None`, and TypeScript `any`-leakage.

**Why CodeScent wins.** A large jump in perceived value for almost no
architectural cost, and it stays squarely inside the deterministic/no-network
ethos.

**Feasibility — high.**

---

## 10. Local semantic / intent search

**Insight.** Keyword and graph search are precise but miss intent: "where do we
handle retries / parse dates / check auth?" fails when the words do not match.

**Mechanism.** Add an **optional, fully-local** embedding index (a small on-device
model, no network — consistent with the privacy stance) so agents can query by
meaning. Keep it opt-in so the no-network-by-default guarantee holds.

**Why CodeScent wins.** It adds the one dimension nothing else on this list
provides — recall — while respecting the local ethos.

**Feasibility — medium-heavy.** The only idea here with real new infrastructure,
hence its rank. Worth doing, but after the cheaper wins land.

---

## Honorable mentions (the funnel)

Cut for leverage-per-unit-complexity, not because they are bad:

- **Auto-inferred architecture layers** — derive layering from the import graph so
  `architecture.boundary_violation` needs no manual config (overlaps #2/#8).
- **Characterization-test scaffolding** — generate a golden-master test before a
  risky refactor; best folded into #3's safe-refactor loop.
- **Monorepo / workspace scoping** — per-package baselines and scans.
- **Dependency-cycle / SCC detection** — circular-import smells from the import
  graph.
- **PR-reviewer attention routing** — point human reviewers at the riskiest hunks.
- **Health badge + plain-English health narrative** — a README badge and a
  generated story of the repo's health over time.
- **Blast-radius-gated refactor safety** — refuse to recommend refactoring a
  high-fan-in symbol without extra tests.
- **Effort-DAG visualization** in the loopback dashboard.

---

## Where to start

Build, in this order:

1. **#6 — CI ratchet.** Smallest, mostly hardening existing scaffolding, and the
   adoption unlock.
2. **#1 — Adaptive findings.** Compounding signal-quality gain, pure analysis over
   data already captured.
3. **#3 — Safe-refactor loop.** The value-chasm crossing; largest and most
   ambitious, sequenced last of the three.

All three sit on machinery CodeScent has already shipped. The detailed plan is in
[`docs/implementation-plan-feedback-autofix-ratchet.md`](./implementation-plan-feedback-autofix-ratchet.md).
