# CodeScent Dogfooding Feedback

A field report from driving the CodeScent MCP server through a realistic agent
loop against **its own codebase**, on 2026-06-19, with Claude Code as the MCP
client. The goal was to evaluate the current tool surface in light of
[`ideas.md`](./ideas.md) and
[`implementation-plan-feedback-autofix-ratchet.md`](./implementation-plan-feedback-autofix-ratchet.md),
and answer one question: _should we build the next features as planned, or
something else first?_

Companion documents produced from this session:

- [`boundedness-bug-fix.md`](./boundedness-bug-fix.md) — the P0 bug below, with
  a concrete fix and envelope shape.
- [`revised-sequencing.md`](./revised-sequencing.md) — a counter-proposal to the
  current build order.

---

## 1. What was exercised

A full agent improvement loop, all against `repo="."` (this repository):

`get_repo_map` → `scan_code_health` → `get_next_improvement` →
`get_finding_context` → `explain_score` → `plan_refactor` → `get_smell_report`,
cross-checked against `.codescent/index.sqlite` and the source tree.

The plan's "current-state" claims were also verified against the code (see §4).

---

## 2. Headline findings

Two problems dominate, and **neither appears in `ideas.md` or the implementation
plan**. Both are about the tool's own trustworthiness, not about missing
features.

### 2.1 P0 bug — the boundedness invariant is violated by the flagship tools

CodeScent's central promise (README, `mcp-tools.md`) is _"bounded output by
default; no unbounded source dump."_ Two of the most important tools break it:

- **`get_smell_report` returned 338,495 characters** and was **rejected by the
  MCP client for exceeding the token limit.** The single tool whose entire pitch
  is "bounded, token-aware" overflowed the context window. It is currently
  unusable by an agent.
- **`scan_code_health` dumped all 1,152 finding IDs inline** in one response — a
  multi-thousand-token wall of opaque hashes with no summary.

The same unbounded shape exists in `get_backlog`, `get_regressions`, and
`rescan` (all return a full `finding_ids` / `findings` tuple). See
[`boundedness-bug-fix.md`](./boundedness-bug-fix.md). The irony is sharp: the
product exists to keep agents out of context overload, and its own reporting
tools cause it.

### 2.2 P1 — signal-to-noise is a five-alarm fire, by construction

Hard numbers from `.codescent/index.sqlite` after a live scan:

| Metric             | Value                                    |
| ------------------ | ---------------------------------------- |
| Total findings     | **1,270** across 163 files (~8 per file) |
| `info` severity    | 897 (71%)                                |
| `warning` severity | 373                                      |

Per-rule distribution:

| Rule                                         | Count |
| -------------------------------------------- | ----- |
| `python.duplicate_literal`                   | 510   |
| `python.large_function`                      | 237   |
| `python.large_file`                          | 110   |
| `python.changed_source_without_related_test` | 99    |
| `python.dead_code_candidate`                 | 89    |
| `python.missing_nearby_test`                 | 79    |
| `python.too_many_imports`                    | 46    |
| `python.structural_near_duplicate`           | 40    |
| `python.todo_cluster`                        | 21    |
| `python.large_class`                         | 18    |
| (TS/React/Next + misc)                       | ~21   |

The defaults manufacture noise:

- `LARGE_FILE_LINES = 70` — **60 of 86 source `.py` files (70%) exceed it.** A
  threshold that flags 70% of the codebase is not a signal; it is a constant.
- `LARGE_FUNCTION_LINES = 25` produces 237 hits.
- `duplicate_literal` alone is **40% of all findings** (510), almost certainly
  over-firing on trivial/short literals.

An agent asking "what should I fix?" is handed 1,270 undifferentiated items, 71%
of them `info`. This is exactly the "tools get muted" failure `ideas.md` #1
describes — but worse than the doc admits, because it is driven by mis-tuned
absolute thresholds, not just by lack of learning.

### 2.3 Minor bug — misattributed evidence in `get_next_improvement` / `get_finding_context`

The #1 recommendation was `python.large_class:18369997c0ac` on
`src/codescent/dashboard/server.py`. But the `get_finding_context` evidence
range pointed at `DashboardServer` (lines 26–39, a **13-line** class), while the
actually-large classes in that file are `DashboardRequestHandler` (lines
153–277, ~124 lines) and `DashboardApplication` (lines 44–153, ~109 lines). The
bounded context aimed the agent at the wrong class. Worth a targeted look at the
evidence-range selection for `large_class`.

---

## 3. What works well

Not everything is broken — the bounded, single-item tools are good:

- `get_repo_map` — compact, paths/counts only, exactly right.
- `get_next_improvement` — tight single-finding payload.
- `get_finding_context`, `plan_refactor`, `explain_score` — well-shaped,
  bounded, with useful `next_tools` hints and `subjective: false` honesty.
- The `next_tools` breadcrumbs genuinely guide a loop.

The problem is concentrated in the **list/aggregate** tools, and in the
**detector tuning** behind them.

---

## 4. The implementation plan is well-grounded (verified)

Credit where due: the plan's "current-state grounding" table was checked against
the source and is **accurate**. Confirmed:

- `SCHEMA_VERSION = 7` ✓
- `health_baseline` table (migration 6) ✓
- `verification_runs` table (migration 7) ✓
- `CiService.run(self, *, threshold, ratchet=False)` with a count-based
  `health_baseline` and `update_baseline` writer ✓ (coarse, exactly as the plan
  states)
- `LARGE_FILE_LINES = 70`, `LARGE_FUNCTION_LINES = 25`,
  `LARGE_CLASS_LINES = 60`, hardcoded `confidence = 0.9 / 0.85` per
  `FindingSpec` ✓
- `_hotspot_score`, `_finding_priority`, `_passes`, `_risk_rank` ✓

This plan was written against the real code, not hallucinated. The designs are
sound and honest about risk (especially the refusal-gated extract-function). The
ten ideas correctly exploit CodeScent's DNA.

---

## 5. The disagreement: sequencing, not substance

The ideas are good. The plan is solid. **But the build order optimizes for the
wrong thing given what dogfooding reveals.**

- Both docs treat signal-to-noise as an _enhancement_ (#1 adaptive, #5 composite
  score) and relegate root-cause clustering (#4) to honorable mentions.
- Neither doc mentions the boundedness bug at all.

Dogfooding says the priority order is inverted:

1. The tool **cannot bound its own report** (P0 bug, in no doc).
2. The tool **cries wolf 1,270 times** because of mis-tuned defaults (P1,
   treated as "nice to have").
3. The backlog is a **flat undifferentiated list** (#4, demoted to honorable
   mention) — the exact pain an agent hits.

Building the autofix / safe-refactor loop (#3) on top of a detector that
overflows the context window and flags 70% of files is putting a turbocharger on
a car with no brakes. The full counter-proposal is in
[`revised-sequencing.md`](./revised-sequencing.md).

**Bottom line:** keep the ideas, do most of the plan, but (a) fix boundedness
and (b) re-tune thresholds _before_ the ambitious adaptive/autofix work, and (c)
promote clustering into the near-term build.
