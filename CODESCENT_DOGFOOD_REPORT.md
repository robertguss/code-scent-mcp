# CodeScent MCP — Dogfood & Regression Report

**Date:** 2026-07-01
**Target repo:** `code-scent-mcp` (self / dogfood)
**Scope:** Verify the fixes merged in #11 (retrieval/scan quality + optional cbm), #12 (recoverable errors, guided loop, agent UX), #13 (findings FK indexes + tier/confidence axes); exercise all 48 MCP tools; flag bugs, noise, and UX gaps.
**Method:** Live MCP calls against a fresh index, cross-checked against source and the SQLite state DB (`.codescent/index.sqlite`). No source files were modified.

---

## 1. Executive summary

- **48/48 tools were reachable.** Most work well. The search, context/call-graph, planning, risk, and guided-loop groups are in good shape.
- **One P0 data/robustness bug**: findings on **non-indexed files** (docs `.md`, `.html`, `.json`) persist with `file_id = NULL`, so their `file_path` comes back empty and three snippet tools (`explain_finding`, `plan_refactor`, `get_finding_context`) **hard-crash** with `{"code":"internal","recoverable":false}` — the worst possible agent error (no cause, no fix hint, not recoverable).
- **One P0 first-run trap**: the repo's persisted findings were **all stale** (`file_id NULL` for every one of 28,689 findings) while `get_repo_status` reported `index_fresh:true`. Every finding tool returned empty `file_path` and every snippet tool crashed until I ran a manual `rescan`. An agent landing here has no signal to rescan.
- **Fixes confirmed working**: #12 recoverable errors (bad ids), constraints DSL + graceful bad-token handling, the resolution gate on `mark_finding`, `resume_task`; #11 collapse-to-signature search, frecency ranking, native call graph; #13 `confidence_tier` present and correctly orthogonal to `confidence`.
- **Dead telemetry**: `session_events` table has **0 rows**. `context_stats` returns all zeros and `resume_task.recent_tools` is always empty, even after 40+ tool calls. The token-savings story reports nothing.
- **Noise**: finding **counts are dominated by stale history** (24,899 resolved `generic.duplicate_literal`), and `get_smell_report`/`get_backlog` inline samples are hash-ordered rather than actionable-first.

---

## 2. Recent fixes — verification results

### #11 retrieval / scan quality + optional cbm
| Feature | Status | Evidence |
|---|---|---|
| Collapse-to-signature search | ✅ works | `search_content("def search_content")` → `collapsed_to_symbol`, symbol name/kind/line-range, `duplicate_twin`, hotspot flags |
| Frecency / multi-signal ranking | ✅ works (with caveat) | `get_related_files` reasons: `co_change, git_history, import_graph, search_similarity, frecency` — see §4 noise note |
| Native call graph (cbm fallback) | ✅ works | `find_callers("build_finding")` returns real callers w/ qualified names; cbm absent → native, per prior memory |
| `search_content` output modes | ✅ works | `content / usage / files / count` all returned correct shapes |

### #12 recoverable errors, guided loop, agent UX
| Feature | Status | Evidence |
|---|---|---|
| Recoverable errors on bad input | ✅ excellent | bad `finding_id` → `recoverable:true`, `fix_hint`, `available_options`, `total_findings`, `severity` |
| Constraints DSL prefilter | ✅ works | `src/ *.py !tests/` filtered correctly |
| Constraints — bad token handling | ✅ graceful | `garbage:token` → `constraint_warnings:["ignored 'garbage:token' — unknown constraint scheme"]`, valid tokens still applied |
| `mark_finding` resolution gate | ✅ excellent | `resolved` w/o verification → `gated:true`, downgraded to `needs_review`, clear message; after `record_verification` (exit 0) → `gated:false`, resolves |
| `resume_task` reconstruction | ✅ works | active findings (with paths), recently-touched files, ratchet, next_tools |
| `start_task` brief | ✅ works | relevant files/symbols/tests, in-scope findings, bootstrap status |

### #13 findings FK indexes + tier/confidence axes
| Feature | Status | Evidence |
|---|---|---|
| `confidence_tier` present on findings | ✅ works | `verified` vs `heuristic` populated across all list/detail tools |
| tier ⟂ confidence (orthogonal, not normalized) | ✅ works | e.g. `verified` finding at `confidence:0.6`; `heuristic` at `0.9` — matches `model.py` docstring intent |
| findings-child FK indexes | ⚠️ present but see §3.1 | `findings.file_id` FK exists and the read path LEFT JOINs on it — but `file_id` is written NULL for non-indexed files, so the index has nothing to resolve for those rows |

---

## 3. Bugs

### 3.1 — P0: findings on non-indexed files lose their path and crash the snippet tools

**Symptom.** `explain_finding`, `plan_refactor`, `get_finding_context` return `{"code":"internal","message":"An internal error occurred","recoverable":false}` for any finding whose file is not a code file. `get_finding` returns the row but with `file_path:""` even though the message carries the real path (e.g. `"FFF_MINING_REPORT.html has 395 lines"`).

**Reproduced on a fresh scan** (not just stale data): `generic.large_file:4c471987dd89` (a `.html`), `generic.todo_cluster:7eb4ed51ac8a`. 67 open findings are currently in this state (all `generic.*`).

**Root cause (proven end-to-end):**
1. The `files` index table holds only the 364 **code** files (`.py/.ts/.js`). The generic rule pack legitimately fires on non-code files — `docs/plans/*.md`, `*.html`, `scripts/dogfood_allowlist.json`.
2. At persist time (`src/codescent/services/code_health.py:237`), `file_ids.get(finding.file_path)` looks the path up in a `{files.path → id}` map built at `:186`. Non-code paths aren't in that map → `file_id = NULL`.
3. The read path (`src/codescent/storage/repositories/findings.py:93`, `left join files on files.id = findings.file_id`) yields `file_path = ""`.
4. Snippet tools call `source_range(repo_root, "")` (`src/codescent/services/explain.py:57-63`, and the refactor-planning service) with an empty path → unguarded exception → wrapped by the error boundary as `recoverable:false`.

**Two independent fixes recommended:**
- **Data**: give generic-pack findings a resolvable location. Either index non-code files into `files`, or store `file_path` directly on the finding row (the string is already known at build time — it is even correct in the fresh `rescan`/`retrieve_result` payloads), rather than only as an FK to the code-only `files` table.
- **Robustness**: guard the empty path in the snippet path so `explain_finding`/`plan_refactor`/`get_finding_context` **degrade gracefully** (return the finding without a snippet, or a `recoverable:true` error such as “finding has no resolvable source location; the path is in `message`/`evidence`”). A hard `recoverable:false` for a valid finding id the tool itself handed out is the worst-case agent experience.

### 3.2 — P0: stale findings + `index_fresh:true` = broken first run, no rescan signal

**Symptom.** On arrival (before I ran anything), **every** one of 28,689 persisted findings had `file_id = NULL`, so **all** finding tools returned empty `file_path` and **all** snippet tools crashed — while `get_repo_status` reported `index_fresh:true`, `database_ok:true`. An agent following the documented workflow (`get_backlog` → `explain_finding`/`plan_refactor`) is dead in the water with no hint to rescan.

**Cause.** The stale rows predate the current persistence logic. A fresh `rescan` fixed 927 findings' `file_id` immediately (matching an in-process repro of the current insert path: 927/1000 resolve). So the current code is mostly correct for code files; the DB simply carried forward pre-fix NULL rows, and `resolved`-status rows are never re-touched by the upsert.

**Fix recommendations:** bump a persistence/schema epoch so stale-`file_id` findings are re-resolved (or migrated) on first read; and/or have `get_repo_status`/`index_fresh` account for findings that fail to resolve a path, surfacing a “run rescan” hint instead of `index_fresh:true`.

### 3.3 — P1: session-event telemetry records nothing

**Symptom.** `session_events` table = **0 rows** (verified in the DB). Consequently `context_stats` returns all zeros (`tool_calls:0`, `estimated_tokens_avoided:0`, `cbm_present_rate:0`) after 40+ tool calls, and `resume_task.recent_tools` is always `[]`. By contrast `finding_events` has 27,707 rows, so lifecycle logging works — only the tool-call/telemetry stream is dead.

**Impact.** The entire token-savings / context-optimization narrative (a headline value prop) reports nothing, and the resume brief can't show a real tool trail. Either events aren't being emitted for this MCP transport, or the writer is keyed on a `session_id` the tools never populate. Worth confirming whether `context_stats(session_id=...)` should default to the server's live session rather than a caller-supplied `"default"`.

---

## 4. Noise & UX gaps (not bugs, but agent-experience friction)

1. **Counts dominated by stale history.** `total_count` ≈ 28,760, of which 24,899 are *resolved* `generic.duplicate_literal` from an earlier, broader scan. `get_progress`/`get_smell_report` totals read as alarming but ~96% is dead history. Consider reporting open/actionable counts prominently and de-emphasizing resolved history, or pruning resolved rows past N scans.

2. **Inline finding samples are hash-ordered, not actionable-first.** `get_smell_report` and `get_backlog` return the first 25 by finding-id hash — so the sample was full of `generic.large_file` with empty paths and even `resolved`/`suppressed` items, instead of the highest-severity open findings. Sort inline items by severity/status so the 25 the agent actually sees are the 25 worth acting on.

3. **`search_files` over-claims confidence on zero-signal queries.** A query for `auth middleware jwt login` (none of which exist in this repo) returned `code_health.py` etc. at `confidence:"high"`, driven by `frecency`/`recent_query` (files *I* had just touched), not relevance. Frecency shouldn't manufacture "high" confidence when the content signal is absent.

4. **`find_symbol` has no fuzzy fallback.** A typo (`SarchServic`) returns zero results and a generic hint. The #12 fuzzy machinery (used well for `finding_id` recovery) isn't wired to symbol lookup — an obvious place to reuse it. Relatedly, the bad-`finding_id` `available_options` list returned arbitrary `duplicate_literal` ids rather than same-rule / near-match suggestions.

5. **Impact/blast-radius includes docs & plans.** `get_impact(symbol=SearchService)` and `refactor_preflight` list `.omo/plans/*.md` and `docs/*.md` in `affected_files`. Doc/plan co-change is not code blast radius and inflates the set an agent thinks it must touch.

6. **`find_callees` semantics are muddled.** For `build_pack_registry` it returns callees with `caller` set to the *query* symbol (not the callee's container) and lists `ProjectConfig` twice (lines 83/84). Usable, but the field naming/dedup could be tightened.

7. **Verbosity.** `get_file_context.next_tools` enumerated 24 `get_symbol_context:<symbol>` entries; `likely_tests` returned 30. Bounded, but a lot to feed back. A top-k would be friendlier.

8. **`get_improvement_plan` leaks the empty-path bug.** The `generic.large_file` cluster has `"files":[""]`, so the agent can't tell which files to split (same root cause as §3.1).

9. **Calibration signal is degenerate.** `get_calibration` shows every rule at `accept_rate:1.0` with `0` rejected — because "accepted" is inferred from resolved/seen findings, and nothing was ever explicitly rejected. Result: several rules calibrate *up* (e.g. `generic.duplicate_literal` 0.7→0.9, `structural_near_duplicate` 0.8→1.0) on a signal that contains no negative evidence. Confidence inflation from absence-of-rejection is worth revisiting.

---

## 5. Full tool matrix (48)

**Guidance:** `how_to_use` ✅, `get_schema` ✅
**Repository:** `get_repo_status` ✅ (but see §3.2 `index_fresh`), `get_repo_map` ✅, `get_architecture` ✅, `start_task` ✅, `resume_task` ✅, `answer_pack` ✅ (weak relevance)
**Search:** `search_content` ✅, `multi_search_content` ✅, `search_files` ⚠️ (§4.3), `search_changed_files` ✅ (graceful empty), `search_todos` ✅, `search_tests` ✅
**Context:** `find_symbol` ✅ (⚠️ no fuzzy), `find_callers` ✅, `find_callees` ⚠️ (§4.6), `find_references` ✅, `get_file_context` ✅ (verbose), `get_symbol_context` ✅, `get_related_files` ✅, `retrieve_result` ✅
**Health:** `scan_code_health`/`rescan` ✅, `get_smell_report` ⚠️ (sample order + empty paths), `get_backlog` ⚠️ (same), `get_next_improvement` ✅, `get_finding` ✅ (⚠️ empty `file_path` for §3.1 rows), `explain_score` ✅, `get_progress` ✅, `get_regressions` ✅, `get_calibration` ✅ (⚠️ §4.9), `get_improvement_plan` ✅ (⚠️ §4.8), `mark_finding` ✅ (gate excellent), `record_verification` ✅, `context_stats` ❌ (§3.3), `subjective_review` ✅ (disabled by default)
**Planning:** `get_finding_context` ❌ crash (§3.1), `explain_finding` ❌ crash (§3.1), `plan_refactor` ❌ crash (§3.1) — **all three work on findings with a resolvable path; crash only on empty-path (non-indexed-file) findings**; `get_impact` ✅ (⚠️ §4.5), `refactor_preflight` ✅ (⚠️ §4.5), `verify_refactor` ✅, `verify_change` ✅, `suggest_tests` ✅ (honest RED scaffold; ⚠️ targets first helper not finding's symbol), `select_tests` ✅
**Risk:** `review_diff_risk` ✅ (graceful empty), `get_changed_file_health` ✅

Legend: ✅ works · ⚠️ works with noise/UX caveat · ❌ broken for a real input class.

---

## 6. State touched during dogfood

All writes were confined to `.codescent/` (per the tool contract — source was never modified):
- Ran `rescan` twice (this is what surfaced/repaired the stale `file_id` rows).
- `python.large_class:8fa8f0c5ffc6` was marked `needs_review` → `resolved`, with one recorded verification (`pytest tests/integration/test_search.py`, exit 0). A subsequent `rescan` will re-open/regress it normally.

## 7. Suggested priority order

1. **§3.1** guard empty path in snippet tools **and** give generic-pack findings a resolvable location (store `file_path` on the row). Highest impact: turns three hard crashes into working tools.
2. **§3.2** re-resolve stale `file_id` on read / surface a rescan hint instead of `index_fresh:true`.
3. **§3.3** wire session-event emission so `context_stats`/`resume_task` telemetry is real.
4. **§4** noise passes: actionable-first inline ordering, open-vs-history counts, frecency-vs-confidence separation, fuzzy symbol lookup.
