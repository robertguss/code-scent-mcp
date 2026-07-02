# CodeScent MCP — Comprehensive Audit Findings

**Date:** 2026-07-02 · **Mode:** recon only, nothing fixed · **Purpose:** convert into beads for follow-up work.

## 1. Executive summary

Full-surface audit of the CodeScent MCP server: all 42 public tools exercised with realistic and adversarial inputs, full test/lint/type/eval/smoke suite run, the PreToolUse/PostToolUse hook audited, and last night's bead-implementation pass verified. Every tool-level claim below survived an adversarial verification pass (a verifier per group attempted to refute each finding by re-running its repro and reading the implementation; 1 sub-claim refuted out of 187).

**Totals: 204 documented findings** — 186 verified tool findings (2 critical, 25 high, 96 medium, 63 low), 12 hook findings (3 high), 3 infrastructure findings (1 critical), 3 suite/hygiene findings.

The one-paragraph version: **the plumbing is honest but the intelligence is not.** Bounded envelopes, read-only-source guarantees, and never-block hooks mostly hold. But the *answers* frequently do not: impact analysis returns alphabetical frecency neighbors instead of actual callers at confidence 0.95 (both criticals), search truncates silently while asserting completeness, confidence fields are near-constant decorations, deleted files are served as fresh results, a mandatory frecency write on every read path throws `concurrent_write` under strictly serial use and can hang the server forever on an out-of-repo path, and the documented tool contract (`docs/mcp-tools.md`) was deleted from the repo while README, tests, the index, and the tools themselves still reference it.

Highest-priority items for beads:

1. **CRIT** `get_impact`/`refactor_preflight` impact sets are wrong (omit real dependents, include deleted/unrelated files, confidence 0.95) — root cause shared: symbol impact routes through file-level `get_related_files` instead of `find_references` (`refactor_planning.py:183-215`).
2. **CRIT (infra)** Out-of-repo path (`search_changed_files {repo:"/etc"}`) hangs the server call **forever** — no timeout, no containment; wedged this audit's tooling twice for hours.
3. **HIGH** Fail-fast writer claim + mandatory frecency write on read paths → `concurrent_write` hard failures under serial single-client use, across ≥6 tool families; no WAL, no retry, no `retry_after`.
4. **HIGH** Tools auto-create `.codescent/` state (3.3 MB+) inside *any* directory they are pointed at, including subdirectories of the analyzed repo — violates the source-read-only contract.
5. **HIGH** `docs/mcp-tools.md` and the docs reference tree deleted (commit b9f122d) without updating dependents — root cause of the 15 "pre-existing" test failures, dead README links, and stale index entries still served as results.
6. **HIGH** Silent truncation asserted as complete: `output_mode=count` returns limit-capped counts with `partial:false` (off by orders of magnitude vs. `get_repo_map`'s 371 files); echoed `limit` desyncs from applied cap.
7. **HIGH (hook)** Grep-injection hook enriches on common words (`def`, `the`), steals flag values (`--include "*.test.js"` → enriches `test`), ignores search scope — most injections in live sessions are noise.

## 2. Scope & methodology

- **Phase 1 — bead audit:** cross-checked last night's implement-all pass (16 beads) against the beads DB and git log.
- **Phase 2 — suite:** `pytest` (877 tests), `ruff check`, `ruff format --check`, `basedpyright`, deterministic eval, source-read-only proof, MCP smoke, dogfood gate.
- **Phase 3 — tool sweep:** 11 auditor agents covering all 42 MCP tools in groups (search, symbols, context, repo-meta, findings, planning, review/pack, docs-contract, cross-tool consistency, mutating/session), each tool called ≥3× realistic + ≥2× adversarial.
- **Phase 4 — verification:** one adversarial verifier per group re-ran repros and read implementations with instructions to refute; severities corrected downward where inflated. 186/187 upheld (many downgraded), 1 refuted.
- **Phase 5 — hook audit:** dedicated agent read the full hook path (`cli/hooks.py`, `hook_support.py`, `hook_payload.py`, `hook_retrieval.py`, `hook_install.py`) and validated behavior empirically.

Caveats: the finding store, frecency tables, and session events were mutated by the audit itself (searches write frecency; the mutating-group agent ran task lifecycles, `mark_finding` round-trips, and a final `rescan`). Source files verified unchanged (`git status` clean, smoke `source_hashes_unchanged: true`).

## 3. Verification of last night's bead pass

**Result: all 16 beads genuinely closed, with matching commits.** No in-progress or blocked beads.

- Closed and verified: `4y8o`, `5b6j`, `dzte`, `f5gn`, `reindex-debounce-jtuz`, `ul1r.1`–`ul1r.8` (+ epic), `yzsz.1`–`yzsz.3`.
- Still open (expected, not regressions): `yzsz.4`/`yzsz.5` (deliberately skipped — spec conflicts), `yzsz.6`, `yzsz.7` (dep-blocked on the P2.5→P2.4 chain), `yzsz.8` (full-surface re-baseline), Phase 4 epic `6ynu.*`, Phase 5 epic `hrrz.*`, moonshots `oi9v.*`.
- One regression from the pass itself: **format gate red** (see §4).

## 4. Test suite & static checks

| Check | Result | Notes |
|---|---|---|
| `pytest` | **15 failed** / 860 passed / 2 skipped | All 15 ⊂ the known 16-failure baseline (one docs test now passes). **No new failures.** Root cause of the baseline identified this audit: `docs/**` deleted in commit b9f122d (see S4). |
| `ruff check` | pass | |
| `ruff format --check` | **FAIL — regression** | `engine/search/multi_grep.py` (d86b089) and `services/findings.py` (36bc566) left unformatted by last night's pass. `services/verification.py` drift is pre-existing (already unformatted at 8ebf913). |
| `basedpyright` | 95 errors, 2 warnings | Pre-existing; all sampled errors in test files last touched weeks ago. |
| Deterministic eval | pass (score 1.0) | |
| Source-read-only proof | pass | |
| MCP smoke (5 core tools) | pass | `source_hashes_unchanged: true`. |
| Dogfood gate | pass | **2 stale allowlist entries** (`python.large_file` hashes no longer present) should be pruned. |

Suite/hygiene findings for beads: **(a)** format regression (medium), **(b)** basedpyright debt — 95 errors (medium), **(c)** stale dogfood allowlist entries (low).

## 5. Systemic themes

Cross-cutting patterns behind the 186 catalog findings. Each theme is a natural epic; catalog entries give the per-tool detail.

### S1 — Reads take write transactions; fail-fast writer claim breaks read tools (HIGH, ~8 findings)
Every content/file search routes hits through `record_frecency`, and `context_stats` routes through `initialize_storage()` (migrate + `quick_check` + `config.toml` write). The writer claim is fail-fast — no WAL, no retry, no backoff — so **read-shaped tools hard-fail with `concurrent_write` even under strictly serial single-client use** (observed on `search_content`, `find_symbol`, `find_callees`, `answer_pack`, `get_related_files`, `get_changed_file_health`, `plan_refactor`, `context_stats`), and multiple concurrent clients wedge outright (see INF-2). Errors carry no `retry_after` hint. Affects: search-core, symbols, review-pack, context, findings-read, planning-tests, repo-meta, consistency groups.

### S2 — No repo containment; state auto-created anywhere; out-of-repo calls can hang forever (CRIT/HIGH)
`repo` parameters accept any existing directory. Consequences: (a) `search_changed_files {repo:"/etc"}` **hangs indefinitely** (INF-1); (b) `review_diff_risk`, `find_symbol`, `list_findings`, `get_repo_map` etc. **silently create a full `.codescent/` state dir (3.3 MB index.sqlite) inside whatever directory they are pointed at** — including subdirectories of the analyzed repo, i.e. inside the source tree the project promises to keep read-only; (c) a subdirectory passed as `repo` yields plausible-but-wrong answers (`not_git`, "every file changed" with confidence high); (d) `answer_pack.focus_path` rejects escapes but `get_repo_map.repo` does not — inconsistent containment policy.

### S3 — Impact analysis returns the wrong files (CRIT ×2)
`get_impact` and `refactor_preflight` omit actual importers/callers and list unrelated co-change/frecency/alphabetical neighbors — including files deleted from disk — at constant confidence 0.95. Shared root cause: symbol impact resolves the symbol to its file and calls file-level `get_related_files(limit=10)` instead of consulting `find_references` (`refactor_planning.py:183-215`); related-file confidence saturates at 1.0 (`context_support.py:348-351`) so ordering degrades to alphabetical. `select_tests`/`suggest_tests` inherit pieces of this (wrong scaffold target, full-suite fallback on nonexistent paths).

### S4 — Docs contract deleted; stale index serves ghosts (HIGH)
Commit b9f122d removed `docs/**` (including `docs/mcp-tools.md`, the declared tool contract) without updating dependents. Fallout: 15 baseline test failures (docs/contract suites read the deleted files), 9 dead README links, `how_to_use`/schema docstrings pointing at nothing — and because the index still holds the deleted files, they are **served as live results**: `start_task.relevant_files`, `answer_pack.related_files`, `get_related_files` (confidence 1, `index_fresh:true`), `refactor_preflight` blast radius. Stale entries survive a full `rescan`. Decide: restore docs or finish the deletion (purge index, fix README/tests/hints).

### S5 — Truncation is silent and asserted as complete (HIGH)
`output_mode=count` returns limit-capped counts with `partial:false` (`search_files` says 20 python files; `get_repo_map` says 371). The service fetch window is hard-capped at 20 collapsed hits and every output mode presents that window as complete. Echoed `limit` desyncs from the applied cap (echo 20, return 100 — `search_todos`, `search_tests`; the aa42b17 fix covered only `search_content`/`search_files`). Silent caps with no truncation marker: `changed_files` (20), `get_architecture` module members (25), `review_diff_risk.changed_files` (20), `multi_search_content` count-mode undercounts ~2×.

### S6 — Confidence/risk fields are decorations, not signals (HIGH-adjacent)
`confidence: "high"` is emitted whenever any results exist — including for zero-match fallbacks, nonexistent symbols, and no-baseline directories. Per-item confidences are near-constant (1.0 / 0.899999…), risk_scores saturate at exactly 0.95 for nearly every file, and `get_calibration` inflates per-rule confidence by counting mechanical auto-resolves as human "accept" verdicts. Raw float artifacts (0.8649999999999999) leak into payloads.

### S7 — Frecency contamination of ranking (HIGH)
Session frecency self-reinforces and contaminates unrelated queries: `answer_pack` returns frecency-boosted clusters instead of the named symbol's files; `search_files` bonuses (up to +165) swamp name relevance and pad results to the limit with no relevance cutoff; earlier queries' files outrank the actual answer; `top_files` ordering is unstable across identical calls because each call's own frecency write shifts the next.

### S8 — Error envelope: everything is `internal, recoverable:false` (HIGH)
The d0a980c "recoverable errors" work is undermined at the boundary: missing required argument (pydantic ValidationError), unknown `finding_id` (FK insert failure), nonexistent paths, unwritable directories, unexpected parameters — all surface as generic `{"code":"internal","recoverable":false}` with empty details, while the true cause is logged server-side only. Error envelopes also duplicate `details`/`severity` at two nesting levels, and `fix_hint` presence is inconsistent.

### S9 — Finding store: bloat, misnamed counters, false positives (HIGH)
28,865 finding rows (27,582 resolved, kept forever) in a 97 MB sqlite for a 394-file repo; no pruning. `unresolved_finding_count` is a migration diagnostic (open/regressed rows missing `file_path`), not what its name says; `finding_count` is all-time rows; `findings_created` reports detected-count every scan even when nothing is new; `deferred_count`/`gate_notes` ignore the status filter (always 25,896). Largest open rule `python.missing_nearby_test` (149 open) is systematically false-positive — it never checks the filesystem. Scan rules fire on generated artifacts (HTML report CSS), JSON data, and the intentionally-flawed fixture repos.

### S10 — Zero-result and invalid-input handling: silent success + backwards advice (MEDIUM)
Nonexistent symbols return 100 "likely tests" at confidence high; nonexistent focus_path echoed back as the pack's top file; unknown `session_id` returns a full ok:true brief; empty queries match everything or return "try a narrower query" on zero results (narrowing an empty result cannot help); invalid enum values (`target_type`, `output_mode`) silently coerce to defaults; negative limits bypass clamping (`multi_search_content` returns len(all)−3 results).

### S11 — "Read-only" claims are false in three distinct ways (MEDIUM)
(a) every successful search writes frecency rows; (b) `context_stats` (self-described read-only) migrates the DB and writes `config.toml`; (c) lookup tools create `.codescent/` in un-indexed directories. Descriptions, `read_only` flags, and docs should match actual write behavior — or the writes should move off the read path (ties into S1).

## 6. Verified tool findings catalog

186 findings, each upheld by an adversarial verifier (verdict `confirmed` = reproduced as claimed; `partial` = real but severity/scope corrected — the text reflects the corrected version). `concurrent_write`-family entries are instances of theme S1.


### 6.1 Search core (search_content, multi_search_content, search_files) — 18 findings


#### CS-001 · HIGH · bug · `multi_search_content`

**Per-path dedupe merge combines fields from two different hits ('snippet': existing or result, 'symbol': existing or result) producing chimera rows that pair a module-docstring snippet with a symbol from a different match site, and drops definition hits entirely.**

- **Repro:** `multi_search_content {queries:['ok_envelope','state_path','_compose']}`
- **Observed:** Reproduced exactly: tests/contract/test_envelope_conformance.py row has snippet '"""ok_envelope() + the tools wired through it' (module docstring, line 1) glued to symbol test_ok_envelope_injects_ok_and_next_tools (start_line 43, end_line 48) with reasons containing both module_level and collapsed_to_symbol; src/codescent/storage/paths.py row pairs a docstring line with the state_path def symbol (24-43); for '_compose' the answer_pack.py row shows only symbol answer_pack (43-77) while the _compose definition at answer_pack.py:79 is dropped (grep confirms _compose at lines 52 and 79).
- **Expected:** Snippet and symbol in one result must describe the same match site; dedupe should keep the highest-value hit intact rather than fabricating a row that points at line-1 content while claiming lines 43-48.
- **Verification (confirmed):** Live repro plus code at src/codescent/services/search.py:194-200: the merge dict keyed by path builds {'snippet': existing['snippet'] or result['snippet'], 'symbol': existing['symbol'] or result['symbol']}, so a symbol-less module-level hit that arrives first donates its snippet while a later hit donates its symbol; single search_content keeps per-symbol hits and is unaffected.


#### CS-002 · HIGH · bug · `search_content`

**Service fetch window is hard-capped at 20 collapsed hits and every output mode presents that window as complete: files mode returned 8 of 40 real files with confidence high and next_cursor null, count mode returns partial=false when thousands of matches exist, and cursor pagination dead-ends at the 20-hit window leaving real matches unreachable.**

- **Repro:** `search_content {query:'resolve_repo_root', output_mode:'files'} -> 8 paths, next_cursor null, confidence high (grep -rln finds 40 .py files). search_content {query:'def', output_mode:'count'} -> {total_matches:20, file_count:3, partial:false}. search_content {query:'ok_envelope', expand:true, limit:5, cursor:'15'} -> 5 results, next_cursor null (window exhausted at offset 20).`
- **Observed:** All three repros reproduced. services/search.py:148-157 search_content_page fetches limit=MAX_LIMIT offset=0 (MAX_LIMIT=20, search_support.py:31); page_results (search_support.py:86-96) derives next_cursor only inside that <=20 window; search_tools.py:263 sets more_available=next_cursor is not None, so with the default limit=20 count-mode partial is structurally always false and window saturation is undetectable.
- **Expected:** partial=true / a truncation warning / non-null cursor whenever matches exist beyond the 20-hit service window; the MatchCountPayload docstring (search_tools.py:70-72) and _match_count comment (search_tools.py:462-465) explicitly promise partial flags this truncation 'so an agent never mistakes the floor for a total', but it never fires on window saturation.
- **Verification (partial):** Fully reproduced in all three modes plus code inspection (services/search.py:148-157, services/search_support.py:31,86-96, mcp/search_tools.py:263,268,457-472). Severity downgraded critical->high: the tool remains correct for its documented bounded top-N retrieval; the defect is that every completeness signal (partial, next_cursor, confidence) affirmatively asserts a complete result set that is a 20-hit floor, and hits past the window are unreachable via cursor. Minor count corrections vs the claim: 8/40 files (not 9/41), 'def' count total 20 (not 22).


#### CS-003 · HIGH · bug · `search_content`

**Read-only searches intermittently fail with concurrent_write because the mandatory per-query frecency write uses a fail-fast writer claim (_claim_writer raises if any reader or writer is active, never waits) and record_frecency is not best-effort.**

- **Repro:** `search_content {query:'resolve_repo_root', output_mode:'files'} and other plain searches while any other codescent activity (e.g. the repo's own PreToolUse hook) is in flight; in this verification session 4 of 17 codescent MCP calls (~24%) failed with concurrent_write, each succeeding on retry.`
- **Observed:** {code:'concurrent_write', message:'Another CodeScent write transaction is already active.', recoverable:true} returned for pure read queries 4 times in this session. src/codescent/storage/repository.py:92-98 _claim_writer raises immediately when a reader or writer is active while _claim_reader (lines 106-112) waits; services/search.py:92,135,209 call record_frecency unconditionally with no try/except (search_support.py:186-206 opens a write_transaction).
- **Expected:** A search should never fail because its telemetry write lost a race: record_frecency should be best-effort or the writer claim should wait briefly like the reader claim does.
- **Verification (confirmed):** Reproduced naturally 4/17 calls this session (~24%, close to the claimed ~33%); mechanism confirmed by code read at src/codescent/storage/repository.py:92-112 and src/codescent/services/search.py:92,135,209 and src/codescent/services/search_support.py:186-206.


#### CS-004 · HIGH · gap · `search_content`

**Content search silently covers only .py/.pyi/.js/.jsx/.ts/.tsx while search_files returns .md and other non-code paths, so a literal string that verifiably exists in an in-repo markdown file yields ok:true 'no content matches found' with a misleading 'try a narrower query' hint.**

- **Repro:** `search_content {query:'flowchart'} -> results:[], warning 'no content matches found; if this miss matters, try a narrower query...'; grep -rln flowchart finds docs/diagrams/codescent-phase2-diagrams.md and codescent-phase3-diagrams.md; search_files {query:'codescent-phase3-diagrams'} returns that same .md as the top hit with confidence high.`
- **Observed:** Reproduced exactly. src/codescent/engine/inventory.py:51-58 LANGUAGE_BY_SUFFIX lists only the six code suffixes and inventory.py:104-106 skips every other suffix, so md/yaml/json/toml/txt content is invisible to search_content with no scope disclosure anywhere in the payload or tool description.
- **Expected:** Either index non-code file types for content search or emit an explicit out-of-scope warning; the cross-tool inconsistency plus the 'narrower query' recovery hint leads agents to conclude the string does not exist in the repo.
- **Verification (confirmed):** Live repro (empty results for 'flowchart' while grep and search_files both find the md files) plus code inspection at src/codescent/engine/inventory.py:51-58,104-106. docs/mcp-tools.md does not exist to document the scope, and the registered description (search_tools.py:142-150) says nothing about file-type coverage.


#### CS-005 · MEDIUM · bug · `multi_search_content`

**count mode undercounts roughly 2x versus running the same queries through search_content individually, because per-path dedupe keeps only one collapsed hit's symbol (and thus match_count) per file, and reports the result with partial=false.**

- **Repro:** `multi_search_content {queries:['ok_envelope','state_path'], output_mode:'count'} vs search_content count for each query separately.`
- **Observed:** Reproduced exactly as claimed: multi returns {total_matches:18, file_count:15, partial:false}; singles return 15 (ok_envelope) + 17 (state_path) = 32 for the identical queries.
- **Expected:** Multi count should tally all collapsed hits per file across queries or flag that dedupe made the total incomparable with single-search counts.
- **Verification (confirmed):** Live repro (18 vs 32, 1.78x); mechanism is the path-keyed merge at src/codescent/services/search.py:186-200 feeding _match_count (search_tools.py:457-472) which sums symbol['match_count'] over the single surviving row per path.


#### CS-006 · MEDIUM · bug · `multi_search_content`

**Negative limit bypasses clamping: the raw value reaches the service's plain list slice so limit=-3 returns len-3 results via Python negative-slice semantics while the payload echoes limit:1; single search_content clamps the same input correctly.**

- **Repro:** `multi_search_content {queries:['state_path'], limit:-3, output_mode:'files'} vs search_content {query:'state_path', limit:-3, output_mode:'files'}`
- **Observed:** Reproduced exactly: multi payload says "limit":1 but returns 4 results (7 merged state_path files minus the 3 lowest-ranked, silently dropped); single search_content with limit=-3 echoes limit 1 and returns exactly 1 result.
- **Expected:** Same clamp as the single-search path; search_tools.py:293 already computes effective_limit = min(max(limit,1),20) but line 298 passes the raw limit to the service, which slices [:limit] at services/search.py:202.
- **Verification (confirmed):** Live repro (echoed limit 1, 4 results returned) plus code at src/codescent/mcp/search_tools.py:292-298 (effective_limit computed but raw limit passed) and src/codescent/services/search.py:202 (plain [:limit] slice, no PageOptions).


#### CS-007 · MEDIUM · bug · `search_content`

**count mode silently excludes import-only module-level matches via a deliberate collapse rule, so total_matches=15 with partial=false where grep finds 22 in the same in-scope .py files — the exclusion is documented only in an internal docstring, never in the tool contract or payload.**

- **Repro:** `search_content {query:'ok_envelope', output_mode:'count'} vs grep -rn ok_envelope over src+tests .py files.`
- **Observed:** Reproduced exactly: {total_matches:15, file_count:8, partial:false}; grep finds 22 matches of which exactly 7 are import lines (22-7=15).
- **Expected:** Count import lines in the tally (they are real matches for impact scans) or disclose the exclusion in the payload/tool description; nothing caller-visible hints that a whole match class is omitted.
- **Verification (partial):** Live repro matches the import-exclusion theory to the digit. The drop is intentional, documented design inside src/codescent/core/symbol_formatter.py:490-524 ('any import-only module-level match is dropped once a real definition is shown', enforced at lines 522-524), sensible for content display but leaking unannounced into count mode; verdict partial because it is a deliberate collapse rule whose defect is disclosure in the count contract, not an accidental coding error — real and medium for impact-count use either way.


#### CS-008 · MEDIUM · ux · `search_content`

**Garbage constraint tokens are only partially surfaced: an unknown scheme gets a constraint_warning, but unmatchable path/glob tokens silently filter out every result and the miss-warning then advises 'try a narrower query' — the opposite of the actual fix.**

- **Repro:** `search_content {query:'ok_envelope', constraints:'bogus:nonsense !!weird [[', output_mode:'files'}`
- **Observed:** Reproduced exactly: constraint_warnings=["ignored 'bogus:nonsense' — unknown constraint scheme"], results:[], ok:true, warning 'no content matches found; if this miss matters, try a narrower query, search_files, or get_repo_map'; the same query unconstrained returns 8 files, so '!!weird' and '[[' became silent match-nothing filters.
- **Expected:** Warn when a constraint token matched zero inventory paths and tailor the miss hint to 'loosen or fix constraints' when constraints are present.
- **Verification (confirmed):** Live repro; unconstrained baseline for the same query returned 8 files earlier in this session, so the empty result is provably constraint-inflicted while the payload blames the query.


#### CS-009 · MEDIUM · docs · `search_content`

**The documented MCP tool contract docs/mcp-tools.md does not exist even though README.md:99, AGENTS.md:65/102/138 and tests/docs/test_docs.py:15 all reference it (the known baseline docs-test failures are this missing file).**

- **Repro:** `ls docs/ ; grep -rn mcp-tools README.md AGENTS.md tests/docs/test_docs.py`
- **Observed:** Reproduced: docs/ contains only decisions/ and diagrams/; AGENTS.md:65 calls it 'Current public tool surface and safety wording', README.md:99 links it, tests/docs/test_docs.py:15 hardcodes the path. No per-tool contract exists anywhere, so the registered descriptions in search_tools.py are the only spec for output modes, limit caps, partial semantics, or the frecency write side-effect.
- **Expected:** The referenced contract doc should exist; several behavioral surprises verified in this audit (window cap, import-drop in counts, content-search file-type scope) have no documentable home today.
- **Verification (confirmed):** ls shows docs/{decisions,diagrams} only; grep hits at README.md:99, AGENTS.md:65,102,138, tests/docs/test_docs.py:15. Consistent with the known-baseline memory note that 16 docs/contract tests fail on clean main with FileNotFoundError.


#### CS-010 · MEDIUM · ux · `search_content`

**Content results carry no match line numbers: collapsed hits only expose the enclosing symbol's start_line, and expand=true results have symbol:null and no line field at all, so an agent must re-grep to locate any expanded match.**

- **Repro:** `search_content {query:'ok_envelope', expand:true, limit:5}`
- **Observed:** Reproduced: every expanded result is {path, score, reasons, snippet, symbol:null} with no line field; identical snippets from the same file are indistinguishable and unlocatable from the payload.
- **Expected:** A line (or match_lines) field per result; the engine already tracks match_lines internally but never emits them.
- **Verification (confirmed):** Live repro payloads contain no line data in any mode except usage; src/codescent/core/symbol_formatter.py CollapsedHit carries match_lines (line 403) and _append_match maintains it (lines 541-545), but the public SearchResultPayload drops it — only symbol.start_line/end_line survive.


#### CS-011 · MEDIUM · noise · `search_files`

**Frecency/recent_query bonuses (up to +165: min(frecency,5)*30 + 15) swamp name relevance (exact path match = flat 100), so exact-name matches rank below recently-touched files; the feedback loop is self-inflicted by the agent's own earlier MCP searches, though NOT by the PreToolUse hook as claimed.**

- **Repro:** `search_files {query:'finding_tools', limit:5}`
- **Observed:** Reproduced in direction: src/codescent/mcp/finding_tools.py (exact stem) ranks 2nd at 256.5 behind planning_tools.py at 261, whose lead is pure frecency/recent_query from files this session's searches touched. Ranking math confirms the swamp: engine/search/ranking.py:15-17,100-105 gives frecency up to 5.0*30=+150 plus recent_query +15, versus exact_path score 100 (ranking.py:119-120).
- **Expected:** An exact filename/stem match should outrank frecency-boosted fuzzy hits; frecency should be a tiebreak, not a bonus 1.65x the exact-match score.
- **Verification (partial):** Live repro plus code at src/codescent/engine/search/ranking.py:15-17,100-105,115-125. One sub-claim REFUTED: the hook does not write frecency — src/codescent/services/hook_retrieval.py:4-5 states 'write nothing — no frecency, no index mutation (R10/AE5)'; the self-inflation loop is real but comes from record_frecency on the agent's own search_files/search_content calls (services/search.py:92,135).


#### CS-012 · MEDIUM · noise · `search_files`

**Results always pad to the 20-item cap with low-relevance 'fff_path' fuzzy filler and no relevance cutoff, so for a specific query most of the payload is irrelevant paths presented under confidence:high.**

- **Repro:** `search_files {query:'answer pack service'}`
- **Observed:** Reproduced: 20 results; after ~5 genuinely relevant answer-pack files the tail is graph_backend.py, cbm_backend.py, risk.py, hook_retrieval.py, search_run.py etc. in a flat score band whose match reason is only the opaque backend tag 'fff_path' (plus session frecency); no drop-off detection, confidence high.
- **Expected:** A score cutoff or drop-off detection so the default response is the relevant head, not a fixed 20; 'fff_path' should be translated into a meaningful ranking reason instead of leaking backend naming.
- **Verification (confirmed):** Live repro shows the exact pattern (relevant head, ~15-item fuzzy filler tail, 'fff_path' reason string verbatim in the payload); fuzzy threshold 60 with no result-set cutoff at src/codescent/engine/search/ranking.py:11,122-125 admits weak partial-ratio matches which the 20-slot page then keeps.


#### CS-013 · LOW · ux · `multi_search_content`

**Empty query input ('' or queries:[]) returns ok:true with the generic 'no content matches found; try a narrower query' warning — advising the agent to narrow a query that does not exist instead of saying a query is required.**

- **Repro:** `multi_search_content {queries:[]} ; search_content {query:''}`
- **Observed:** Reproduced both: ok:true, results:[], confidence:low, warning 'no content matches found; if this miss matters, try a narrower query...'; services/search.py:168-169 short-circuits empty queries to () and the generic miss-warning path treats it as an ordinary no-hit.
- **Expected:** A distinct 'empty query — nothing was searched; provide a query' warning.
- **Verification (confirmed):** Live repro of both variants; _advisory_fields (search_tools.py:493-518) keys warnings only on has_results, with no empty-input branch.


#### CS-014 · LOW · ux · `search_content`

**usage mode reports the enclosing symbol's start_line rather than the actual reference line, and multiple module-level matches in one file emit duplicate indistinguishable {line:null, symbol:null} rows.**

- **Repro:** `search_content {query:'state_path', output_mode:'usage'}`
- **Observed:** Reproduced exactly: src/codescent/services/config.py 'load' reported at line 26 (the def) while the state_path reference is at line 28 (verified by sed); src/codescent/storage/__init__.py appears twice as {line:null, symbol:null} for its module-level matches at lines 1 and 14 with no way to tell them apart.
- **Expected:** usage rows described as 'reference-style match sites' (search_tools.py:60) should carry the match line; module-level sites have known line numbers and should not degrade to null.
- **Verification (confirmed):** Live repro plus code: _usage_sites (src/codescent/mcp/search_tools.py:438-454) emits symbol['start_line'] or null; the true match lines exist in CollapsedHit.match_lines (core/symbol_formatter.py:403) but are unavailable at that layer.


#### CS-015 · LOW · noise · `search_content`

**Inline quality annotations mislead at result granularity: finding_payloads.py results, including the ok_envelope definition imported by 7 modules, render file-level flags ['dead_code','duplicate','hotspot'] on every result row, stamping live widely-imported code as dead.**

- **Repro:** `multi_search_content {queries:['ok_envelope',...]} or search_content {query:'ok_envelope'} — inspect the src/codescent/mcp/finding_payloads.py rows' quality field.`
- **Observed:** Reproduced: the ok_envelope definition row (finding_payloads.py:261) carries quality {flags:['dead_code','duplicate','hotspot'], duplicate_twin:'src/codescent/mcp/search_tools.py'}; grep shows 7 files import ok_envelope, so the code is provably live; the identical file-level flag block repeats on every result from that file.
- **Expected:** Quality flags scoped or worded per file, not attached undifferentiated to each symbol hit, and not contradicting obvious liveness.
- **Verification (confirmed):** Live repro plus code: _annotate_quality (services/search.py:51-60) applies quality_annotation_for(result['path']) — a per-path annotation — to every result row, and PathQuality (engine/search/ranking.py:45-55) is file-granular by design, so a file flagged dead_code anywhere stamps all its symbols in every search response.


#### CS-016 · LOW · ux · `search_content`

**Any existing directory is accepted as repo with no indexed-repo check, so a mistyped repo path that happens to exist reads as an empty search result with the generic 'try a narrower query' hint; only nonexistent paths get invalid_repo_root.**

- **Repro:** `Verified by code inspection only — live repro with repo:'/etc' was skipped per the hang guard (out-of-repo codescent calls are known to hang this server with no timeout).`
- **Observed:** src/codescent/core/paths.py:6-16 resolve_repo_root checks only Path.is_dir(): an existing directory passes with no .codescent-index presence check, no repo-marker check, and no timeout/path guard, while a nonexistent path raises INVALID_REPO_ROOT — matching the claimed split. Nothing downstream distinguishes 'unindexed directory' from 'no matches'.
- **Expected:** A warning when the target directory has no .codescent index (e.g. 'directory is not indexed; run rescan or check the path') so mistyped repo paths do not read as empty search results.
- **Verification (confirmed):** Confirmed by inspection at src/codescent/core/paths.py:6-16 (is_dir() is the sole gate; INVALID_REPO_ROOT only for missing paths). Per the audit hang guard the /etc repro was not re-run; the absence of any index/timeout guard in the accept path also corroborates the known hang-on-foreign-path behavior.


#### CS-017 · LOW · ux · `search_files`

**A malformed cursor silently coerces to offset 0 (cursor_to_offset swallows ValueError) with no warning, so an agent paging with a corrupted cursor re-receives page 1 and can loop — inconsistent with the tool's own degrade-surfacing pattern for output_mode.**

- **Repro:** `search_files {query:'search tools', cursor:'banana', limit:3}`
- **Observed:** Reproduced exactly: ok:true, first page returned, next_cursor:'3', warnings:[] — indistinguishable from a legitimate first-page request.
- **Expected:** A warning like the output_mode degrade message produced by _degrade_warnings (search_tools.py:475-490).
- **Verification (confirmed):** Live repro plus code at src/codescent/services/search_support.py:99-105: except ValueError: return 0, no signal propagated; contrast with the explicit output_mode degrade warning pattern in the same transport module.


#### CS-018 · LOW · docs · `search_files`

**Tool description says 'Read-only' but every successful search_files/search_content call writes frecency rows into .codescent/index.sqlite, which is exactly the write that makes searches fail with concurrent_write.**

- **Repro:** `Any search_files call, then read frecency_signals from .codescent/index.sqlite (read-only connection); contrast with the registered 'Read-only' description at src/codescent/mcp/search_tools.py:136.`
- **Observed:** Confirmed: frecency_signals holds 1053 rows with max(updated_at) timestamped seconds after this session's searches; record_frecency (search_support.py:186-206) opens a write_transaction on every non-empty search result set, and this session saw 4 concurrent_write failures on 'Read-only' searches.
- **Expected:** Drop the 'Read-only' claim (document the telemetry write) or make the write best-effort so the read-only contract holds from the caller's perspective.
- **Verification (confirmed):** Direct DB read (1053 rows, fresh updated_at) plus code at src/codescent/mcp/search_tools.py:136 ('Read-only' in the registered description) and src/codescent/services/search.py:92 (unconditional record_frecency in search_files).


### 6.2 Specialized search (search_tests, search_todos, search_changed_files) — 13 findings


#### CS-019 · HIGH · bug · `search_tests`

**Nonexistent symbol returns up to 100 irrelevant 'likely tests' at base score with confidence 'high' and no warning**

- **Repro:** `search_tests {"repo": "/home/robert/Projects/code-scent-mcp", "symbol": "qqqqzzzz_wxyzv", "limit": 5} (variation: limit=100000)`
- **Observed:** Live MCP call returned 5 junk files (incl. src/codescent/engine/rules/test_quality.py, 0-byte tests/__init__.py) all score 40, reasons ["likely_test"], warnings [], confidence "high". Variation with limit=100000 returned exactly 100 results, all score 40 / reasons ("likely_test",), warnings (), confidence high.
- **Expected:** Zero-match queries return empty results or a clearly-flagged fallback with lowered confidence/warning, not a full page of unranked files presented as likely tests.
- **Verification (confirmed):** Reproduced live twice (MCP call + direct handler at max limit: 100 results, all base-score, no warning, confidence high). Code confirms: rank_test_file keeps TEST_FILE_BONUS=40 base even with zero term matches (src/codescent/services/search_queries.py:21,172-176), so every test-shaped file passes the score filter. Advisory fields set confidence high whenever results exist.


#### CS-020 · MEDIUM · bug · `search_changed_files`

**Non-git directory with no index reports every file as 'changed' (index_changed) with confidence 'high' and no warning about the missing baseline**

- **Repro:** `search_changed_files {"repo": "/home/robert/Projects/code-scent-mcp/evals", "limit": 5} (safe in-repo variation of the original /etc repro, which was NOT re-run per hang-guard policy)`
- **Observed:** evals/ (no .git, no .codescent) returned all files with reasons ["changed_file","index_changed"], score 100, confidence "high", warnings [] — nothing changed, there is simply no baseline. Probe verified side-effect-free (no .codescent created, git tree clean).
- **Expected:** A warning like 'no git repo / no index baseline; listing unindexed files' and lowered confidence, so agents don't read 'index_changed' as an actual modification.
- **Verification (confirmed):** Reproduced with an in-repo non-git subdirectory; code confirms mechanism: changed_file_reasons sets include_unindexed=not git_available (src/codescent/services/search_support.py:305-312) and index_changed_files returns the full inventory when no index DB exists and include_unindexed=True (lines 332-337). Out-of-repo /etc repro verified by inspection only, per hang guard.


#### CS-021 · MEDIUM · ux · `search_changed_files`

**Zero-result warning gives backwards advice ('try a narrower query') and treats a clean repo — the tool's most common, definitive state — as a low-confidence miss**

- **Repro:** `search_changed_files {"repo": "/home/robert/Projects/code-scent-mcp"} on a clean tree`
- **Observed:** Returned warnings ["no changed files found; if this miss matters, try a narrower query, search_files, search_content, or get_repo_map"] with confidence "low". Narrowing an empty result cannot produce more results, and 'no changed files' on a clean tree is the correct definitive answer, not an unreliable miss.
- **Expected:** Advice should say 'broader query'; a clean tree should report 'working tree clean, no index drift' with high confidence.
- **Verification (confirmed):** Reproduced verbatim on the clean repo root; shared wording confirmed at src/codescent/services/freshness.py:136 (no_result_warning), used by all three tools via _advisory_fields.


#### CS-022 · MEDIUM · bug · `search_tests`

**'symbol_match'/'content_match' reasons are fabricated for files that do not contain the symbol, because terms are split into ultra-common fragments that each earn the symbol bonus**

- **Repro:** `search_tests {"repo": "/home/robert/Projects/code-scent-mcp", "query": "state_path", "limit": 5}`
- **Observed:** tests/contract/cli_payloads.py, tests/contract/test_cli.py, and tests/contract/test_hook_augment_cli.py returned with reasons ["likely_test","content_match","symbol_match"] at score 120; grep -c 'state_path' on all three = 0 (fragments 'state'/'path' matched instead). Real match tests/unit/test_state_path.py did rank first at 265.
- **Expected:** 'symbol_match' asserted only when the requested symbol actually appears; fragment hits labeled and scored distinctly.
- **Verification (partial):** Reproduced exactly; mechanism confirmed: split_test_terms fragments 'state_path' into 'state'/'path' (search_queries.py:154-164) and looks_like_symbol accepts any identifier-like fragment (lines 202-203), so substring hits earn symbol_match (lines 189-191). Downgraded high->medium: in every tested case the genuine match still ranked top-1 (score 265 vs 120), so the fabricated reasons pollute tail entries rather than inverting the ranking; still a real metadata falsehood (also seen in the finding_id repro where 'Too many open files' fixtures scored 160 via 'too'/'many').


#### CS-023 · MEDIUM · gap · `search_tests`

**finding_id is never resolved to the finding's file/symbol — it is only tokenized as text, so results reflect rule-name word fragments, and fake ids are accepted silently**

- **Repro:** `search_tests {"repo": "/home/robert/Projects/code-scent-mcp", "finding_id": "python.too_many_imports:3bd21a89e5ee", "limit": 5}; variation with finding_id="totally.fake_rule:deadbeef0000"`
- **Observed:** Results #2/#3 were tests/fixtures/headroom_influence_fixtures.py and its test, matched via fragments 'too'/'many' on 'OSError: Too many open files' at score 160 — the finding's target file plays no role. The fake finding_id returned ok:true with results matched via the fragment 'fake' (score 155/120), no warning or error, confidence high.
- **Expected:** Resolve the finding id to its file_path/symbol and rank tests for that target; warn or error on unknown ids.
- **Verification (confirmed):** Both repros reproduced live; code confirms no lookup exists: test_search_terms just runs split_test_terms over the raw finding_id string alongside query/path/symbol (src/codescent/services/search_queries.py:145-151) — no storage/finding access anywhere in the search_tests path.


#### CS-024 · MEDIUM · bug · `search_tests`

**is_test_path misclassifies production code and non-test helpers as 'likely tests'**

- **Repro:** `search_tests {"repo": "/home/robert/Projects/code-scent-mcp", "symbol": "qqqqzzzz_wxyzv", "limit": 5}`
- **Observed:** Results include src/codescent/engine/rules/test_quality.py (verified: 619-line production rules module with 0 test functions — it detects test smells, it isn't a test), tests/__init__.py (verified 0 bytes), and helper module tests/contract/cli_payloads.py. In the fake-finding_id repro test_quality.py even ranked #1 at 155.
- **Expected:** Exclude src/ modules that merely start with test_, empty __init__.py files, and non-test helpers.
- **Verification (confirmed):** Reproduced live twice; classifier confirmed at src/codescent/services/search_queries.py:136-142 — any path under tests/ or any basename starting with 'test_' or ending '_test.py' counts, with no content check.


#### CS-025 · MEDIUM · bug · `search_todos`

**Echoed 'limit' desyncs from the actually-applied cap: response claims limit 20 but returns up to 100 results (search_todos, search_tests; latent in search_changed_files)**

- **Repro:** `search_todos {"repo": "/home/robert/Projects/code-scent-mcp", "limit": 100000}`
- **Observed:** Live MCP call: payload echoed "limit": 20 but results array held 100 entries. Direct handler check: search_todos echo 20/returns 100, search_tests echo 20/returns 100, search_changed_files echo 20/service clamp 100 (0 on clean tree), while search_content (fixed by aa42b17) echoes 20 and returns 20.
- **Expected:** Echoed limit equals the cap actually applied to the result set, matching the aa42b17 contract already applied to search_content/search_files.
- **Verification (partial):** Fully reproduced; mechanism confirmed in code: transport echoes min(limit, SAMPLE_FILE_LIMIT=MAX_LIMIT=20) at src/codescent/mcp/search_tools.py:338,361,393 while services clamp via PageOptions/clamp_limit at MAX_PAGE_LIMIT=100 (src/codescent/core/models.py:6,374; search.py PageOptions usage). Downgraded high->medium: metadata/contract desync with a silent 5x payload, but results themselves are correct and output stays bounded at 100 — no wrong data.


#### CS-026 · MEDIUM · gap · `search_todos`

**Truncation is completely silent (no count/cursor/'more results' signal) and the FIXME score-boost makes the default page 100% FIXME, hiding all TODO/HACK markers**

- **Repro:** `search_todos {"repo": "/home/robert/Projects/code-scent-mcp"}`
- **Observed:** Default call returned exactly 20 results — every one marker:FIXME (score 92 outranks TODO 90, ties sorted by path) — with warnings [] and no count/next_cursor/more_available field. Ground truth: git grep finds 152 marker lines; the limit=100000 call returned 100 results, so 80+ hidden results with zero signal.
- **Expected:** A more_available/total-count indicator (search_content/multi_search_content already report count and more_available) or a 'results truncated at limit' warning.
- **Verification (confirmed):** Reproduced live: 20/20 results FIXME, no truncation field anywhere in the payload; marker boost table confirmed at search_queries.py:122-133 (FIXME 12.0 > TODO 10.0 > HACK 8.0) with tie-sort by path (sort_todo_results:107-113). multi_search_content contrast confirmed in search_tools.py:306-317 (count + more_available).


#### CS-027 · MEDIUM · docs · `search_todos`

**No user-facing documentation exists for these tools: docs/mcp-tools.md is absent despite README/AGENTS declaring it the tool contract, and no doc mentions search_tests/search_todos/search_changed_files**

- **Repro:** `ls docs/mcp-tools.md; grep -rn 'search_todos|search_tests|search_changed_files' README.md docs/`
- **Observed:** docs/ contains only decisions/ and diagrams/; docs/mcp-tools.md does not exist though README.md:99 links it and AGENTS.md:65,102,138 call it the authoritative MCP tool contract. Zero hits for any of the three tool names in README.md or docs/.
- **Expected:** The referenced contract file present (or references updated), documenting parameters, caps, reason vocabulary, and empty-state semantics.
- **Verification (confirmed):** Verified directly: file absent, dangling references confirmed at README.md:99 and AGENTS.md:65/102/138. Matches the known baseline of 16 docs/contract test failures (FileNotFoundError) on clean main.


#### CS-028 · LOW · noise · `search_changed_files`

**Envelope carries permanently-dead fields (output_mode='content' with snippet always null, next_cursor/count always null) and disagrees with sibling payload shapes**

- **Repro:** `search_changed_files {"repo": "/home/robert/Projects/code-scent-mcp"}`
- **Observed:** Both live search_changed_files responses (empty and populated) carried output_mode:"content", next_cursor:null, count:null, and per-result snippet:null/symbol:null; search_todos and search_tests responses omit all of these fields, so the three siblings have three different envelope shapes.
- **Expected:** Drop always-null fields or align the sibling payload shapes.
- **Verification (confirmed):** Observed in every live response this session; hardcoded in src/codescent/mcp/search_tools.py:335-342 (next_cursor=None, count=None, output_mode='content') and src/codescent/services/search.py:240-242 (snippet=None, symbol=None on every row).


#### CS-029 · LOW · noise · `search_tests`

**Result snippet is the first line matching the first (least specific) term, usually an unrelated import line**

- **Repro:** `search_tests {"repo": "/home/robert/Projects/code-scent-mcp", "path": "src/codescent/services/answer_pack.py", "limit": 5}`
- **Observed:** Top hit tests/integration/test_answer_pack.py (correct file) shows snippet 'from codescent.core.models import TokenBudgets' — the first line matching the path-derived term 'codescent', nothing about answer_pack. All 5 results show similarly irrelevant import-line snippets.
- **Expected:** Snippet drawn from the most specific matched term (e.g. the line containing 'answer_pack').
- **Verification (confirmed):** Reproduced live; mechanism confirmed in rank_test_file: matched_snippet is set on the first content_match in term iteration order (search_queries.py:183-188), and test_search_terms emits path tokens like 'codescent' before specific ones.


#### CS-030 · LOW · gap · `search_tests`

**Defensive input coercion (coerce_int etc.) is applied to search_files/search_content but not to search_tests/search_todos/search_changed_files, so malformed input handling differs across the family**

- **Repro:** `Direct handler calls: search_files(limit='abc') vs search_todos(limit='abc') (src/codescent/mcp/search_tools.py:198,246,292 vs 329-401)`
- **Observed:** search_files(limit='abc') degrades gracefully (ok:true, limit coerced to default 20, 20 results); search_todos(limit='abc') raises an unhandled pydantic ValidationError from PageOptions. The three tools in this group pass raw params straight to the service with no coerce_int.
- **Expected:** Consistent defensive handling across the search tool family.
- **Verification (partial):** Asymmetry demonstrated directly in-process (ValidationError vs graceful degrade). However, the MCP transport schema types limit as integer, so remote MCP callers are validated before the handler and cannot hit the raw exception — impact is limited to in-process/CLI callers and family consistency. Recategorized bug->gap; severity low stands.


#### CS-031 · LOW · noise · `search_todos`

**Marker mentions inside string literals, regexes, and scoring tables are reported as real TODO/FIXME items**

- **Repro:** `search_todos {"repo": "/home/robert/Projects/code-scent-mcp"}`
- **Observed:** Default top-20 includes src/codescent/services/search_queries.py:124 ('"FIXME": 12.0,' — the tool's own score table); the full listing includes TODO_PATTERN's own regex definition (search_queries.py:20), rule titles ('title="TODO/FIXME/HACK cluster"'), assertion strings, and test-fixture write_text literals.
- **Expected:** Prefer comment-context matches or down-rank matches inside string literals/regex definitions.
- **Verification (confirmed):** Reproduced live in both default and full-limit calls; TODO_PATTERN confirmed at search_queries.py:20 — a bare word-boundary regex over every line with no comment-context check.


### 6.3 Symbol graph (find_symbol, find_callers, find_callees, find_references) — 18 findings


#### CS-032 · HIGH · bug · `find_references`

**find_references only returns call edges: constants report zero references and import statements are omitted entirely**

- **Repro:** `find_references {"query":"SYMBOL_CAP"} and find_references {"query":"ok_envelope","limit":50}`
- **Observed:** SYMBOL_CAP -> ok:true, results:[], warning 'no graph results found' despite 4 real references (definition src/codescent/services/answer_pack_support.py:23, use :273, import src/codescent/services/answer_pack.py:11, use :88). ok_envelope -> exactly 12 call-site rows; all 7 'from codescent.mcp.finding_payloads import ok_envelope' lines (planning_tools.py:5, context_tools.py:13, risk_tools.py:5, repo_tools.py:8, session_stats_tools.py:6, architecture_tools.py:5, test_envelope_conformance.py:17) absent.
- **Expected:** References include imports, definitions, and non-call identifier uses, or the tool states it covers only call edges; an agent doing rename/impact analysis will conclude a live constant is unused.
- **Verification (confirmed):** Re-ran both repros live 2026-07-02: SYMBOL_CAP returned empty with 'no graph results found' while grep found 4 references; ok_envelope returned the 12 call sites and none of the 7 grep-verified import lines. Tool description ('Bounded persisted references for a symbol or identifier') promises references, not call edges. docs/mcp-tools.md is absent so no doc excuses the behavior.


#### CS-033 · HIGH · bug · `find_symbol`

**find_symbol and find_callees hard-fail with concurrent_write whenever any index write is active (fail-fast writer claim, no WAL, no retry); find_callers/find_references are not affected**

- **Repro:** `Hold a write lock (python: sqlite3 connect .codescent/index.sqlite; begin immediate; sleep 20) then call find_symbol {"query":"ok_envelope"} and find_callees {"query":"answer_pack"}`
- **Observed:** Both failed with {code:'concurrent_write', message:'Another CodeScent write transaction is already active.', recoverable:true} while the lock was held; find_callers and find_references succeeded under the identical lock. Mechanism verified in source: find_symbol records a session event on every call (src/codescent/mcp/context_tools.py:439-442 -> SessionEventRepository.record_event, session_events.py:82 write_transaction), _claim_writer raises immediately when any reader/writer is active (src/codescent/storage/repository.py:92-98), _connect has no WAL pragma (repository.py:160-163, busy_timeout 5000ms) and no index.sqlite-wal exists.
- **Expected:** Read-oriented lookups should not require the write lock (defer/skip the session-event write, use WAL, or wait like _claim_reader does); failing during any concurrent write (including the tool's own per-call writes, so parallel find_symbol calls collide) makes the lookup unreliable for agents.
- **Verification (partial):** Deterministically reproduced for find_symbol and find_callees with a held cross-process write lock; refuted the 'all four tools' scope claim by running find_callers and find_references under the same lock (both succeeded, so only the two tools that write per-call are exposed). Original ~35% in-session failure rate not verifiable, but the fail-fast mechanism is confirmed in code and live. Lock was rolled back and released; post-test find_symbol call healthy.


#### CS-034 · MEDIUM · bug · `find_callees`

**A query naming a real function returns only a substring-matched unrelated function's callees at envelope confidence 'high', and a resolvable qualified name returns 'no graph results found' with backwards advice instead of distinguishing 'function makes no non-builtin calls'**

- **Repro:** `find_callees {"query":"describe"} and find_callees {"query":"evals.precision_corpus.pkg.tidy.add"}`
- **Observed:** 'describe' returned 6 rows, all callees of tests.integration.test_findings.test_backlog_status_counts_describe_only_the_returned_rows (name contains 'describe'), envelope confidence 'high'; the function evals.precision_corpus.pkg.tidy.describe (tidy.py:10, located by find_symbol) is invisible. Exact qualified names ('evals.precision_corpus.pkg.tidy.add', 'tidy') return empty with 'no graph results found; ... try a narrower query'.
- **Expected:** Exact-name matches should outrank substring matches; a resolvable name with no non-builtin callees should say so explicitly rather than a not-found warning advising a narrower query.
- **Verification (partial):** Reproduced both repros exactly. Downgraded from high: tidy.describe's body ('return f"value is {value}"', tidy.py:10-11) makes no calls and tidy.add's only edges are builtin annotations, so nothing rankable was actually dropped - the defect is misattributed substring rows presented as the answer (caller field does disclose the mismatch) plus an empty/missing ambiguity with backwards advice, not silent data loss for functions with real callees ('_compose' shows its true callees alongside the junk).


#### CS-035 · MEDIUM · noise · `find_callees`

**Bare-name queries substring-match every symbol containing the string, merging callee sets of unrelated functions into one undifferentiated list**

- **Repro:** `find_callees {"query":"_compose","limit":30}`
- **Observed:** Returns AnswerPackService._compose's 7 true callees (answer_pack.py:86-94) merged with 7 rows from tests.integration.test_output_modes.test_output_mode_composes_with_expand - matched only because '_composes' contains '_compose' - with no notice that 2 different functions matched; envelope confidence 'high'.
- **Expected:** Symbol-name-boundary matching by default, or per-function grouping with an explicit 'matched N functions' notice; qualified-name scoping exists but is undocumented.
- **Verification (confirmed):** Reproduced live: 14 rows spanning two unrelated functions, distinguishable only by reading each row's caller field. The correct callees for _compose were verified present, so this is noise/merging rather than data loss.


#### CS-036 · MEDIUM · bug · `find_callers`

**Empty-string query is accepted and pages out the raw repository call-edge table (builtin edges, caller:null rows) instead of a validation error**

- **Repro:** `find_callers {"query":"","limit":5}`
- **Observed:** ok:true with rows like text:'list'/'str' at evals/__init__.py:1 (caller:null), 'int' at evals/precision_corpus/pkg/deep_nesting.py:6, 'json'/'GET' from a .ts fixture, next_cursor:5 inviting a paginated walk of the whole graph; envelope confidence 'high', no warnings.
- **Expected:** Required query='' returns an actionable validation error (find_symbol at least returns an empty result set).
- **Verification (confirmed):** Reproduced live with limit=5: raw graph internals including builtins and null-caller rows, next_cursor set. Schema marks query as required yet empty string passes through as a match-everything filter.


#### CS-037 · MEDIUM · noise · `find_references`

**Confidence labels are near-constant and contradict sibling tools for identical facts**

- **Repro:** `find_callers {"query":"ok_envelope"} vs find_references {"query":"ok_envelope"}`
- **Observed:** The identical rows (same path:line) are certainty 'medium'/0.6 from find_callers but 'low'/0.4 from find_references, while both envelopes say top-level confidence 'high'. Within a named query, every row carries the same constant value (0.6 for callers/callees, 0.4 for references).
- **Expected:** Confidence should discriminate (direct call vs heuristic match) and agree across tools for the same edge; per-row 'low' under envelope 'high' invites second-guessing of correct data.
- **Verification (confirmed):** Reproduced live: find_callers rows 0.6/medium, find_references rows 0.4/low for the same 12 ok_envelope call sites, both envelopes 'high'. Minor correction to the original claim of total uniformity: the empty-query dump shows caller:null builtin rows at 0.4 within find_callers, but named-query rows are constant.


#### CS-038 · MEDIUM · bug · `find_symbol`

**stats.total_results and omitted_count are computed after the limit cap, so search-level truncation is invisible and completeness metadata lies**

- **Repro:** `find_symbol {"query":"__init__","limit":5}`
- **Observed:** Response: total_results:5, omitted_count:0, warnings [], though grep finds 14 'def __init__' plus partial matches (__post_init__, _git_init_commit, ...); the default-limit run reports total_results:20, exactly the cap, with omitted_count:14 referring only to display compaction of the 20, never to search-cap truncation. Mechanism: src/codescent/core/symbol_formatter.py:108 sets total_results = len(results) on the already-capped list.
- **Expected:** total_results reflects the true match count or the response flags 'limit reached, more matches exist'; omitted_count:0 must not be emitted when matches were dropped by the cap.
- **Verification (partial):** Reproduced live and traced to symbol_formatter.py:108. Downgraded from high to medium: the returned results themselves are correct and an agent can raise the limit; the harm is confidently wrong exhaustiveness metadata (omitted_count:0, no cursor, no warning) rather than wrong data - lower blast radius than find_references' missing references.


#### CS-039 · MEDIUM · ux · `find_symbol`

**Lookup tools described as 'Read-only for source' silently create a .codescent state directory (index.sqlite, config.toml, scan_cache.json) in any existing directory passed as repo**

- **Repro:** `mkdir probe_dir with one sample.py; find_symbol {"query":"anything","repo":"<probe_dir>"}`
- **Observed:** Call returned ok:true (warning only says 'index was stale and was automatically refreshed') and left probe_dir/.codescent/ with a 221KB index.sqlite, config.toml, and scan_cache.json. No mention of state creation in the payload.
- **Expected:** No state bootstrap into arbitrary paths without opt-in; wrong-path typos pollute unrelated directories, and this is the likely source of the opaque /etc permission failure.
- **Verification (confirmed):** Reproduced in a fresh scratchpad directory 2026-07-02: .codescent/ with 221k index.sqlite materialized by a single find_symbol call. Probe directory removed after the test. 'Read-only for source' in the tool description is technically honest about source files but conceals state creation.


#### CS-040 · MEDIUM · bug · `find_symbol`

**repo pointing at an unwritable directory yields a generic non-recoverable 'internal' error with empty details**

- **Repro:** `find_symbol {"query":"root","repo":"/etc"}`
- **Observed:** {"code":"internal","data":{},"message":"An internal error occurred while handling the tool call.","ok":false,"recoverable":false} - consistent with a swallowed PermissionError from the silent index bootstrap (initialize_storage attempts to create /etc/.codescent).
- **Expected:** A specific recoverable error such as 'cannot initialize index: permission denied for /etc/.codescent', matching the quality of the invalid_repo_root path.
- **Verification (confirmed):** Reproduced live: exact generic internal error with data:{} and recoverable:false. Coheres with the verified silent-bootstrap behavior (finding above): the same call that creates .codescent in writable dirs must fail on unwritable ones, and the failure is not translated.


#### CS-041 · MEDIUM · noise · `find_symbol`

**Query matches module/path substrings and rank_reason claims 'partial definition match ... score=1.00' for symbols whose names do not contain the query**

- **Repro:** `find_symbol {"query":"ok","limit":6}`
- **Observed:** Results: useThing (module hooks_heavy - 'hOOKs'), main (run_token_efficiency - 'tOKen'), SmokePaths/main (smoke_dashboard - 'smOKe'); none contain 'ok' in the symbol name, yet each row says "partial definition match for 'ok' with score=1.00" and envelope confidence is 'high'.
- **Expected:** Path/module matches labeled as such and scored below name matches; a uniform maximum score on junk destroys the ranking signal.
- **Verification (confirmed):** Reproduced live 2026-07-02 with limit=6: all returned groups were module-substring matches at claimed score 1.00 with 'definition match' rank_reasons.


#### CS-042 · MEDIUM · ux · `find_symbol`

**'pattern' parameter is an undocumented query-alias silently ignored whenever query is non-empty**

- **Repro:** `find_symbol {"query":"envelope","pattern":"src/codescent/mcp/*"} vs the same call with pattern:"[invalid("`
- **Observed:** Byte-identical result sets for both patterns, including files outside src/codescent/mcp/ (core/models.py, core/output_formatter.py, evals/agent_ux/envelope.py). Source confirms: core/defensive.py resolve_query (lines 25-37) consults aliases only when query is empty; the schema gives pattern no description.
- **Expected:** Document pattern as a query alias, warn when ignored, or remove it; agents will trust 'filtered' results that were never filtered.
- **Verification (confirmed):** Reproduced with two contradictory patterns producing identical output, and read resolve_query in src/codescent/core/defensive.py showing pattern is dead when query is set.


#### CS-043 · MEDIUM · docs · `find_symbol`

**No documented contract exists for any of the four graph tools: docs/mcp-tools.md is absent though README, AGENTS.md, and tests declare it authoritative**

- **Repro:** `ls docs/mcp-tools.md; grep mcp-tools README.md AGENTS.md tests/docs/test_docs.py; grep find_symbol/find_callers/find_references README.md AGENTS.md`
- **Observed:** docs/ contains only decisions/ and diagrams/; README.md:99 links docs/mcp-tools.md, AGENTS.md:65/102/138 call it the tool contract, tests/docs/test_docs.py:15 requires it; no README/AGENTS mention of the four tool names. Behavior like qualified-name scoping, builtin filtering, and pattern-as-alias is discoverable only by experiment.
- **Expected:** The contract file present (or references and tests updated); this is the known pre-existing baseline behind the 16 failing docs/contract tests on clean main.
- **Verification (confirmed):** Verified file absence and all four references live. Matches the recorded project baseline (16 docs/contract tests fail with FileNotFoundError on clean main), so it is a real, acknowledged gap rather than a regression.


#### CS-044 · LOW · bug · `find_callers`

**Type annotations are recorded as call edges (phantom callees normally hidden behind the builtin filter, exposed via the empty-query dump)**

- **Repro:** `find_callers {"query":"","limit":5}`
- **Observed:** Row text:'int' at evals/precision_corpus/pkg/deep_nesting.py:6 attributed to caller nested with certainty 'medium' - that line is 'def nested(flag: bool) -> int:' which contains no calls; also list/str edges at evals/__init__.py:1 ('__all__: list[str] = []', caller:null).
- **Expected:** Annotations should not be call edges; they inflate the graph and surface through any unfiltered path.
- **Verification (confirmed):** Reproduced the dump and read both source lines: deep_nesting.py:6 is a def signature with annotations only, evals/__init__.py:1 is an annotated assignment; both carry 'call' edges in the graph.


#### CS-045 · LOW · ux · `find_callers`

**Out-of-range paging inputs are silently coerced: negative cursor treated as 0 and oversized limits clamped without any warning**

- **Repro:** `find_callers {"query":"ok_envelope","cursor":-10,"limit":3}`
- **Observed:** cursor:-10 returned the first page with next_cursor:3 and warnings []; oversized limits (e.g. 100000) are silently clamped to the 20-row page cap with no coercion notice (consistent with the PageOptions clamp verified in the sibling search-tools group).
- **Expected:** A warnings entry noting the coercion so agents do not assume an exhaustive scan happened.
- **Verification (confirmed):** Reproduced the negative-cursor case live: silent coercion to page 0, empty warnings.


#### CS-046 · LOW · gap · `find_references`

**find_references drops information its siblings provide and lacks their parameters (caller always null; no project_id/session_id)**

- **Repro:** `find_references {"query":"ok_envelope"} vs find_callers {"query":"ok_envelope"}; compare loaded schemas`
- **Observed:** All 12 ok_envelope reference rows have caller:null while find_callers attributes the enclosing function (e.g. codescent.mcp.architecture_tools._architecture_payload) for the identical path:line rows; the loaded find_references schema omits project_id/session_id that the other three tools accept.
- **Expected:** Parity: caller attribution on reference rows and a consistent parameter surface across the four graph tools.
- **Verification (confirmed):** Verified live with side-by-side calls on the same symbol and by inspecting the four fetched tool schemas: find_references is the only one without project_id/session_id, and its rows carry caller:null where find_callers fills the field.


#### CS-047 · LOW · noise · `find_symbol`

**Summary strings misstate group counts and the stats key set varies between responses**

- **Repro:** `find_symbol {"query":"__init__"} (default limit) vs any zero-result call`
- **Observed:** Summary says 'returned 6 compact items across 19 groups' while stats show groups_returned:6 of total_groups:19 (items span 6 groups, not 19). The zero-result response's stats omit total_groups and raw_token_estimate that populated responses include ({"total_results":0,"returned_results":0,"groups_returned":0}; shape hardcoded at src/codescent/core/symbol_formatter.py:65 vs :108).
- **Expected:** 'returned 6 items across 6 of 19 groups' and a stable stats shape.
- **Verification (confirmed):** Reproduced both: default __init__ run emitted the misleading 'across 19 groups' wording; probe-dir empty result carried the reduced 3-key stats dict, and both shapes are visible in symbol_formatter.py.


#### CS-048 · LOW · ux · `find_symbol`

**Contradictory retrieval hints: retrieval_available:true with original_result_id:null plus internal jargon 'No storage attached; preserve original payload upstream'**

- **Repro:** `find_symbol {"query":"ok","limit":6}`
- **Observed:** Response omitted 2 results, said retrieval_available:true, original_result_id:null, and hint 'No storage attached; preserve original payload upstream' - nothing is actually retrievable. Contrast: the default __init__ run correctly pairs retrieval_available:true with original_result_id 'ctx_...' and a usable retrieve_result hint, proving the null-id case is the broken branch.
- **Expected:** retrieval_available:false when no result id exists; hints phrased for the calling agent, not leaking storage wiring.
- **Verification (confirmed):** Reproduced both branches live in this session: the 'ok' query showed the contradiction, the '__init__' query showed the working storage-attached path.


#### CS-049 · LOW · noise · `find_symbol`

**next_tools is a static ['search_files','search_content','get_repo_map'] triple on every response and never suggests the documented follow-up get_symbol_context**

- **Repro:** `Any call: find_symbol/find_callers/find_callees/find_references, success or miss`
- **Observed:** Identical next_tools triple on every one of ~12 successful, empty, and zero-hit responses across all four tools this session, though find_symbol's own description says 'The qualified_name it returns feeds get_symbol_context'.
- **Expected:** Context-sensitive hints (get_symbol_context after a definition hit) or omit the constant field.
- **Verification (confirmed):** Observed on all responses in this verification session without exception, including definition hits where get_symbol_context is the documented next step.


### 6.4 Context (get_symbol_context, get_file_context, get_related_files, get_impact) — 18 findings


#### CS-050 · CRITICAL · bug · `get_impact`

**Impact set does not match actual importers/callers: real dependents are omitted and unrelated co-change/frecency/alphabetical files are returned at constant confidence 0.95**

- **Repro:** `mcp__codescent__get_impact {"target_type":"symbol","target":"codescent.mcp.finding_payloads.ok_envelope","repo":"/home/robert/Projects/code-scent-mcp"}; variation: {"target_type":"file","target":"src/codescent/services/freshness.py"}`
- **Observed:** Symbol run: affected_files = finding_payloads.py + docs/configuration.md, docs/mcp-tools.md (both deleted from repo), evals/*, plans/README.md, cli/hooks.py, cli/reporting.py, core/errors.py, core/json_decode.py, core/models.py at confidence 0.95; rg shows the actual importers of ok_envelope are architecture_tools.py, context_tools.py, planning_tools.py, repo_tools.py, risk_tools.py, session_stats_tools.py — zero returned. File run on freshness.py: all 6 real importers (context_tools.py, search_tools.py, bootstrap.py, context.py, context_support.py, task_brief.py) missing, likely_tests [], confidence 0.95 again.
- **Expected:** affected_files should be the files that actually import/call the target, ranked by graph evidence, with confidence reflecting the signal used; refactor_preflight.py:174 consumes affected_files[0], so the wrongness propagates to other tools.
- **Verification (confirmed):** Reproduced live for both target types; exact-match wrongness. Root cause read in src/codescent/services/refactor_planning.py:190-215: affected_files = target + top-10 of ContextService.get_related_files, which sorts by (-confidence, path) (context.py:842) where confidence saturates at 1.0 via min(sum(reason weights),1.0) (context_support.py:348-351) — i.e. an alphabetical slice of frecency/co-change noise, not dependents. _impact_confidence (refactor_planning.py:294-298) = mean of ~1.0 values capped at 0.95, so 0.95 on effectively every call. Exact affected list varies slightly run-to-run with frecency, but the invariant (no true importers, deleted docs present, 0.95) held on every run.


#### CS-051 · HIGH · bug · `get_related_files`

**Deleted files are served as top related results with confidence 1 while index_fresh:true, and the same path is simultaneously 'related' and 'not indexed'**

- **Repro:** `mcp__codescent__get_related_files {"path":"src/codescent/mcp/finding_tools.py","repo":"/home/robert/Projects/code-scent-mcp","limit":10} then mcp__codescent__get_file_context {"path":"docs/mcp-tools.md",...}`
- **Observed:** First result: docs/mcp-tools.md (reasons co_change,git_history, confidence 1), index_fresh:true. ls confirms docs/ contains only decisions/ and diagrams/; git log -1 -- docs/mcp-tools.md = b9f122d 'remove docs/**'. get_file_context on docs/mcp-tools.md returns not_found 'No indexed file'. get_file_context(context_tools.py).related_files and get_impact affected_files also list docs/mcp-tools.md, docs/configuration.md, docs/plans/2026-07-01-*.md.
- **Expected:** Co-change/git-history edges for files no longer in the index should be filtered or purged; a fresh index must not recommend paths its own read path rejects.
- **Verification (confirmed):** Reproduced live exactly. Internal inconsistency verified in code: get_related_files builds reasons from git history without the _persisted_file_exists check that the same service applies to its input path (src/codescent/services/context.py:373-374), so deleted paths flow through with saturated confidence.


#### CS-052 · HIGH · bug · `get_related_files`

**Read-shaped context tools intermittently fail with concurrent_write under strictly serial single-client use, with no retry_after hint**

- **Repro:** `Ordinary serial session: codescent tool calls interleaved with Bash calls that trigger the codescent PreToolUse hook; observed on get_impact {"target_type":"file","target":"src/codescent/services/freshness.py"} and get_related_files {"path":"src/codescent/does_not_exist.py"}`
- **Observed:** 2 of ~14 strictly serial codescent calls in this verification session returned {"code":"concurrent_write","message":"Another CodeScent write transaction is already active.","recoverable":true} against .codescent/index.sqlite; immediate retry succeeded both times. The original report's ~10 errors/3-attempt retries is rate variance from hook timing, same defect.
- **Expected:** Read/context tools should tolerate a concurrent hook-reindex writer (wait/retry internally) or include a retry-after hint; a context query should not fail because a background frecency/session-stats write is in flight.
- **Verification (confirmed):** Reproduced live twice under one-call-at-a-time use. Mechanism verified in src/codescent/storage/repository.py: read-shaped tool calls still open write transactions (initialize_storage migration check at repository.py:39 plus session-event/frecency writes), _claim_writer (repository.py:92-98) fails fast instead of waiting when another writer/reader is registered, and cross-process contention with the hook's reindex converts sqlite OperationalError (busy_timeout 5000, repository.py:161-163) into concurrent_write (repository.py:82-84) with no retry_after in the payload.


#### CS-053 · MEDIUM · noise · `get_file_context`

**Symbol names are emitted three times per response: prose summary, symbols array, and one next_tools entry per symbol including private helpers**

- **Repro:** `mcp__codescent__get_file_context {"path":"src/codescent/mcp/context_tools.py","repo":"/home/robert/Projects/code-scent-mcp"}`
- **Observed:** Reproduced verbatim: summary = 'context_tools.py defines FileContextToolPayload, ... get_related_files.' (all 23 names), symbols = the same 23 names, next_tools = 23 'get_symbol_context:codescent.mcp.context_tools.<name>' strings including _record_session_event, _project_id, and other private helpers.
- **Expected:** Summary should add information the symbols array does not, and next_tools should be a bounded shortlist rather than an unbounded per-symbol expansion.
- **Verification (confirmed):** Live repro matched the claim exactly (23/23/23). Same pattern on answer_pack.py (4/4/4). Token-padding in every file-context response; severity/category as reported.


#### CS-054 · MEDIUM · bug · `get_impact`

**Missing/empty symbol target returns silent empty success (ok:true, affected_files [], confidence 0.5) instead of a missing-argument error**

- **Repro:** `mcp__codescent__get_impact {"target_type":"symbol","repo":"/home/robert/Projects/code-scent-mcp"}`
- **Observed:** {"ok":true,"target":"","affected_files":[],"likely_tests":[],"confidence":0.5} — reproduced live, no error or warning.
- **Expected:** A recoverable invalid_value/missing-argument error stating target is required when target_type=symbol.
- **Verification (partial):** Confirmed live; root cause at src/codescent/services/refactor_planning.py:176-177 (resolved_target = target or "") and _impact_file_signals's `if not file_path: return (), ()` (refactor_planning.py:268-269), which _impact_confidence then maps to 0.5. Downgraded high→medium: real validation gap, but the response echoes target:"" and confidence 0.5, giving an attentive agent some signal; 'dangerously misinterpretable' is somewhat overstated.


#### CS-055 · MEDIUM · bug · `get_impact`

**Invalid target_type is silently accepted and treated as 'file'**

- **Repro:** `mcp__codescent__get_impact {"target_type":"banana","target":"src/codescent/services/answer_pack.py","repo":"/home/robert/Projects/code-scent-mcp"}`
- **Observed:** ok:true with target_type:'banana' echoed and file semantics applied — reproduced live. Tool description says target_type must be file, symbol, or finding.
- **Expected:** Recoverable invalid_value error listing valid values.
- **Verification (partial):** Confirmed live; code inspection shows refactor_planning.py:175-188 only special-cases target_type=='symbol' and finding_id, with no validation of the enum. Downgraded high→medium: the claimed worst case (typo 'symbols' silently getting file semantics) actually surfaces as an error, because a qualified symbol name fails _persisted_file_exists and the LookupError propagates (tolerate_missing=False); silent wrong semantics only occurs when the bogus type is paired with a valid file path.


#### CS-056 · MEDIUM · bug · `get_impact`

**Nonexistent symbol target yields a generic non-recoverable 'internal' error instead of not_found with suggestions**

- **Repro:** `mcp__codescent__get_impact {"target_type":"symbol","target":"codescent.services.nonexistent.TotallyFakeService","repo":"/home/robert/Projects/code-scent-mcp"}`
- **Observed:** {"code":"internal","ok":false,"recoverable":false} — reproduced live. get_symbol_context on the same input returns recoverable not_found with 5 fuzzy suggestions and a fix_hint (also verified live).
- **Expected:** The not_found + suggestions envelope get_symbol_context produces.
- **Verification (partial):** Confirmed live; root cause is `find_symbol(target, limit=1)[0]` at src/codescent/services/refactor_planning.py:184-187 — find_symbol returns an empty tuple for a miss, so [0] raises IndexError (not the LookupError the report guessed), which the error boundary swallows as internal. Downgraded high→medium: error-path inconsistency on a typo'd input, recoverable by using get_symbol_context/find_symbol first as the tool description instructs.


#### CS-057 · MEDIUM · bug · `get_related_files`

**Nonexistent path yields a generic non-recoverable 'internal' error instead of the not_found-with-suggestions envelope its sibling tool produces**

- **Repro:** `mcp__codescent__get_related_files {"path":"src/codescent/does_not_exist.py","repo":"/home/robert/Projects/code-scent-mcp"}`
- **Observed:** {"code":"internal","message":"An internal error occurred while handling the tool call.","ok":false,"recoverable":false} — reproduced live. get_file_context on the same bad path returns recoverable not_found with fix_hint and suggestions.
- **Expected:** The same recoverable not_found envelope get_file_context produces (context_tools.py:206-211 handles LookupError with nearest-path suggestions).
- **Verification (partial):** Confirmed live and by inspection: ContextService.get_related_files raises LookupError at src/codescent/services/context.py:374 and the tool wrapper at src/codescent/mcp/context_tools.py:571-597 has no LookupError handler, unlike get_file_context (context_tools.py:206-211, the repo's own 'U2' recoverable-error contract). Downgraded high→medium: error-path polish bug on invalid input; main flow with valid paths is unaffected and the agent can recover by switching tools.


#### CS-058 · MEDIUM · noise · `get_related_files`

**Results ordered alphabetically within a saturated confidence tier, so the strongest structural relations fall off page 1 while session-frecency echoes fill it**

- **Repro:** `mcp__codescent__get_related_files {"path":"src/codescent/services/answer_pack.py","repo":"/home/robert/Projects/code-scent-mcp"} then same with {"cursor":20}`
- **Observed:** Page 1 (20 items, all confidence 1) is dominated by frecency/recent_query/search_similarity-only entries (cli/hooks.py, engine/rules/*, mcp/* — echoes of this session's own queries); answer_pack_support.py, the strongest relation (7 reasons incl. co_change, directory_proximity, import_graph), sits at position 29 on page 2, alongside context.py (import_graph). Minor correction to the claim: two direct imports (core/paths.py, core/token_estimate.py with import_graph reason) did make page 1 by alphabetical luck — 'omits every direct import' is overstated.
- **Expected:** Order by evidence strength (reason count/structural signals) so a default limit=20 call surfaces the files an agent needs; the caller's own recent queries should not outrank imports.
- **Verification (partial):** Reproduced live. Root cause read: sort key is (-confidence, path) at src/codescent/services/context.py:836-843, and confidence = min(sum(RELATED_REASON_WEIGHTS),1.0) (context_support.py:348-351) saturates at 1.0 for nearly any 2-3 reason combination (frecency 0.4 + recent_query 0.45 + search_similarity 0.3 = 1.15), so ordering degenerates to alphabetical path within the tier. Severity/category as reported; verdict partial only for the 'every direct import' overstatement.


#### CS-059 · MEDIUM · noise · `get_related_files`

**Confidence labels carry no signal: per-item confidence is 1 or 0.8999999999999999 for everything, envelope confidence is always 'high', get_impact always 0.95**

- **Repro:** `mcp__codescent__get_related_files {"path":"src/codescent/services/context.py","repo":"/home/robert/Projects/code-scent-mcp","limit":100000} (+cursor 100)`
- **Observed:** 200+ files reported 'related' to one file (next_cursor 200 after two pages); every single item is confidence 1 or 0.8999999999999999 regardless of whether reasons are import_graph+co_change+test_match or a lone frecency echo; envelope confidence 'high' on every successful call this session; get_impact returned 0.95 on both calls including the demonstrably wrong ones.
- **Expected:** Confidence should discriminate (import-backed >> frecency-only) as the 'confidence-labeled evidence' in the tool description implies.
- **Verification (confirmed):** Reproduced live (results even worse than claimed: >200 related, not >100). Root cause: min(sum(weights),1.0) saturation at src/codescent/services/context_support.py:26-37,348-351 — weights (test_match .7, import_graph .65, co_change .62, git_history .6, frecency .4, recent_query .45, search_similarity .3) mean almost any multi-reason file clamps to 1.0; the only sub-1.0 tier is exactly git_history+search_similarity = 0.6+0.3. Impact confidence is mean-capped at 0.95 (refactor_planning.py:294-298).


#### CS-060 · MEDIUM · ux · `get_symbol_context`

**next_tools hardcodes explain_finding, which requires a finding_id that does not exist in the symbol-context flow**

- **Repro:** `mcp__codescent__get_symbol_context {"qualified_name":"codescent.services.context.ContextService","repo":"/home/robert/Projects/code-scent-mcp"}`
- **Observed:** next_tools = ["explain_finding","find_references","plan_refactor"] — reproduced on every get_symbol_context call this session (success and repro variants alike).
- **Expected:** Hints executable from this state, e.g. find_references/find_callers/get_file_context.
- **Verification (confirmed):** Confirmed live and in source: literal tuple ("explain_finding", "find_references", "plan_refactor") hardcoded at src/codescent/mcp/context_tools.py:470. explain_finding's schema requires a finding_id, which no symbol-context flow produces.


#### CS-061 · LOW · noise · `get_file_context`

**source_ranges overlap and duplicate lines across adjacent symbols**

- **Repro:** `mcp__codescent__get_file_context {"path":"src/codescent/services/answer_pack.py","repo":"/home/robert/Projects/code-scent-mcp"}`
- **Observed:** Reproduced verbatim: range 1 = lines 40-47 (class AnswerPackService header + start of answer_pack), range 2 = lines 43-50 (answer_pack again); lines 43-47 sent twice.
- **Expected:** Non-overlapping ranges or merged adjacent symbols.
- **Verification (confirmed):** Live repro exact (40-47 and 43-50 with 5 duplicated lines); per-symbol ranges are cut independently via source_range(line_cap) in engine/context/ranges.py with no overlap merge.


#### CS-062 · LOW · docs · `get_file_context`

**No documented tool contract exists: docs/mcp-tools.md was deleted from the repo while tests and tooling still reference it**

- **Repro:** `ls docs/; git log -1 -- docs/mcp-tools.md`
- **Observed:** docs/ contains only decisions/ and diagrams/; docs/mcp-tools.md gone since b9f122d 'remove docs/**'; tests/docs/test_docs.py still exists and references it (matches the known 16 baseline FileNotFoundError docs-test failures on clean main); the only per-tool contract left is the one-line MCP descriptions. Ironically the index still serves the deleted doc as a top related file (see the deleted-files finding).
- **Expected:** Restore per-tool documentation or update tests/references so the contract lives somewhere checkable.
- **Verification (confirmed):** Verified: ls shows no docs/mcp-tools.md, git log -1 -- docs/mcp-tools.md = b9f122d 'remove docs/**', tests/docs/test_docs.py present. Pre-existing baseline (per project memory), not a new regression — correctly categorized low/docs. This also means no doc existed to refute any finding in this group against; tool descriptions were used as the only contract.


#### CS-063 · LOW · bug · `get_related_files`

**Raw floating-point artifact 0.8999999999999999 leaks into serialized confidence values**

- **Repro:** `mcp__codescent__get_related_files {"path":"src/codescent/services/context.py","repo":"/home/robert/Projects/code-scent-mcp","limit":100000,"cursor":100}`
- **Observed:** ~65 items on the second page report "confidence":0.8999999999999999 (files with exactly git_history+search_similarity reasons).
- **Expected:** Round confidence to sane precision before serialization.
- **Verification (confirmed):** Reproduced live at scale. Root cause: RELATED_REASON_WEIGHTS git_history=0.6 + search_similarity=0.3 (src/codescent/services/context_support.py:29,32) summed in IEEE-754 = 0.8999999999999999, emitted unrounded from related_file_payload (context_support.py:348-355).


#### CS-064 · LOW · ux · `get_related_files`

**Out-of-range limits and cursors are silently absorbed with warnings [] — clamped limit and past-the-end cursor give no signal**

- **Repro:** `mcp__codescent__get_related_files {"path":"src/codescent/services/context.py",...,"limit":100000} and mcp__codescent__get_file_context {"path":"src/codescent/services/answer_pack.py",...,"related_cursor":100000}`
- **Observed:** Reproduced both legs: limit=100000 silently returns 100 rows with next_cursor=100 and warnings []; related_cursor=100000 returns related_files [] with related_files_next_cursor null and warnings [].
- **Expected:** A warning noting the limit was clamped / cursor is past the end, so an empty page is not misread as 'no more related files'.
- **Verification (confirmed):** Both live repros matched exactly; warnings array empty in each response despite silent clamping/absorption.


#### CS-065 · LOW · gap · `get_symbol_context`

**Fixed 8-line source_ranges truncate mid-docstring and omit the body even for a 12-line function; a 267-line class shows only two dataclass fields**

- **Repro:** `mcp__codescent__get_symbol_context {"qualified_name":"codescent.mcp.finding_payloads.ok_envelope","repo":"/home/robert/Projects/code-scent-mcp"}`
- **Observed:** Reproduced: symbol reports start_line 261/end_line 272 but the snippet covers 261-268, ending mid-docstring ('...for tools whose payload is a plain,') with the return body dropped; ContextService (142-409) snippet shows the class line, two fields, and the first lines of find_symbol only.
- **Expected:** Include whole small symbols, or signature+docstring+member list for classes; as-is the agent must Read the file anyway.
- **Verification (confirmed):** Live repro exact. Cap implemented in src/codescent/engine/context/ranges.py source_range(): capped_end = min(end_line, start_line + line_cap - 1) — a deliberate bound ('bounded, not whole files' per tool description) but applied with no small-symbol exception, so even a 12-line function loses its body. Low/gap as reported.


#### CS-066 · LOW · gap · `get_symbol_context`

**likely_tests empty for private methods whose enclosing file has a direct integration test mapping**

- **Repro:** `mcp__codescent__get_symbol_context {"qualified_name":"codescent.services.answer_pack.AnswerPackService._compose","repo":"/home/robert/Projects/code-scent-mcp"}`
- **Observed:** likely_tests: [] — reproduced; get_file_context on src/codescent/services/answer_pack.py lists tests/integration/test_answer_pack.py (verified live in the same session), and get_impact on freshness.py also returned likely_tests: [].
- **Expected:** Fall back to the enclosing class/file test mapping when method-level matching finds nothing.
- **Verification (confirmed):** Both legs reproduced live in this session: symbol-level [] vs file-level ['tests/integration/test_answer_pack.py'], and get_impact(file=freshness.py) likely_tests [].


#### CS-067 · LOW · noise · `get_symbol_context`

**Error envelopes duplicate the details object at data.details and top-level details, and fix_hint is present on not_found but absent on invalid_repo_root/path_outside_root**

- **Repro:** `mcp__codescent__get_symbol_context {"qualified_name":"nonexistent.Thing","repo":"/home/robert/Projects/code-scent-mcp"}; out-of-repo leg verified by code inspection per hang guard`
- **Observed:** Live: not_found error carries identical {"qualified_name":"nonexistent.Thing"} at both data.details and top-level details, with fix_hint present; the concurrent_write errors observed this session show the same double-details shape. Inspection: invalid_repo_root (src/codescent/core/paths.py:10-15) and path_outside_root (paths.py:26-31) are raised with details but no fix_hint argument.
- **Expected:** One details location; fix_hint on all recoverable errors.
- **Verification (confirmed):** Double-details observed on every error envelope in this session (not_found, concurrent_write, internal). fix_hint inconsistency confirmed by reading core/paths.py — the out-of-repo repro (repo='../../etc/passwd') was NOT executed per the hang-guard rule; CodeScentError construction at paths.py:10-15 and 26-31 shows no fix_hint, versus the not_found paths (context_tools.py _unknown_path_error, symbol not_found) which set one.


### 6.5 Repo meta (get_repo_map, get_architecture, get_repo_status, context_stats, get_schema) — 19 findings


#### CS-068 · HIGH · bug · `context_stats`

**context_stats is not read-only: it routes through initialize_storage() which takes a write transaction (migrate + quick_check), writes config.toml, and silently creates .codescent state in any directory passed as repo**

- **Repro:** `mkdir empty_probe; context_stats {"repo": "<abs>/empty_probe"}; ls -laR empty_probe`
- **Observed:** Re-ran live: ok:true with all-zero stats and a fresh .codescent/ containing a 221k index.sqlite plus config.toml materialized in a pristine empty directory, no warning. Source: src/codescent/services/session_stats.py:75 calls initialize_storage; src/codescent/storage/repository.py:32-57 does mkdir + write_transaction(migrate+quick_check) + config write.
- **Expected:** Stats read uses the read path (state_for + read_connection, the exact convention get_repo_status documents at src/codescent/mcp/repo_tools.py:222-226) and reports 'no CodeScent state at this root' for unindexed dirs.
- **Verification (confirmed):** Live repro reproduced byte-for-byte (221k index.sqlite + config.toml created, ok:true, warnings:[]). Downstream harm is real, not theoretical: a shadow src/.codescent created this way is what feeds finding #8's bogus subdir status. Probe dir removed after test.


#### CS-069 · HIGH · bug · `get_repo_status`

**unresolved_finding_count does not count unresolved findings; it counts open/regressed findings missing a persisted file_path — the live payload now reports 0 while the DB holds 793 open+regressed findings**

- **Repro:** `get_repo_status {"repo": "/home/robert/Projects/code-scent-mcp"} vs sqlite: select status, count(*) from findings group by status`
- **Observed:** Live payload: finding_count:28865, unresolved_finding_count:0, warnings:[]. DB ground truth: 714 open + 79 regressed = 793 unresolved (0 with empty file_path since the mid-audit rescan re-persisted paths). The docstring at src/codescent/storage/repositories/index_status.py:43-50 confirms the key is intentionally a missing-file-path diagnostic; the public key name and the tool description ('finding counts') say otherwise, and when the count is 0 no warning explains anything.
- **Expected:** A key named unresolved_finding_count reports the open+regressed total; the missing-path diagnostic gets its own name or lives only in the warning.
- **Verification (confirmed):** Verification made it starker than filed: the original session saw a ~6x understatement (127 vs 745); post-rescan the same payload reads '0 unresolved' against a 793-finding open backlog with zero warnings — an agent orienting here would conclude the backlog is clean. Query: findings by status = resolved 27582, open 714, suppressed 490, regressed 79.


#### CS-070 · MEDIUM · bug · `context_stats`

**context_stats contends for the fail-fast writer lock, so it hard-fails with concurrent_write whenever any other reader/writer on the same DB is in flight (claim that BOTH parallel calls fail holds only when a third writer such as the reindex is active)**

- **Repro:** `Two threads calling ContextStatsService(root).context_stats through a barrier; also one call while a read_connection is held open (in-process probe against a scratch state dir, same code path as the single-process MCP server)`
- **Observed:** Probe A (two concurrent stats calls): ['error:concurrent_write', 'ok'] — exactly one fails. Probe B (stats while a reader is open): error:concurrent_write. Mechanism at src/codescent/storage/repository.py:92-98: _claim_writer raises immediately when a writer OR any reader is active; context_stats enters via write_transaction (session_stats.py:75 -> repository.py:39).
- **Expected:** A stats read never claims the writer lock (read_connection waits for writers and always succeeds); concurrent stats reads all succeed.
- **Verification (partial):** Root cause confirmed live with a deterministic in-process repro. Overstated details corrected: (a) two bare concurrent calls fail one-of-two, not both — both fail only when a third writer holds the claim, plausible in the original session during the debounced reindex; (b) severity downgraded high→medium: recoverable, retry succeeds seconds later, and it is an introspection tool off the critical code path. Probe state removed.


#### CS-071 · MEDIUM · bug · `context_stats`

**tool_calls and token-savings stats undercount massively: only find_symbol and retrieve_result emit session events, so every other tool on the 42-tool surface is invisible to context_stats**

- **Repro:** `Call get_repo_status/get_schema/get_repo_map/get_architecture/context_stats repeatedly, then context_stats {"repo": "."}`
- **Observed:** Live session payload: tool_calls:22, most_used_tools:["find_symbol"] only, all 5 largest_summarized_results are find_symbol — despite this session making a dozen non-find_symbol codescent calls that never incremented anything. Grep confirms SessionEventWrite emitters exist only in src/codescent/mcp/context_tools.py (tool_name hardcoded 'find_symbol' at lines 278/400/427) and src/codescent/mcp/result_tools.py:100; services/code_health.py's _record_event writes finding events, not session events. scan_code_health/list_findings summarize results but record no savings events either.
- **Expected:** All registered tools emit tool_called events, or the payload/description states which subset is instrumented.
- **Verification (partial):** Fully reproduced; severity downgraded high→medium: the numbers are internally consistent for the instrumented subset and the tool is introspection-only, but the description ('MCP context and token-savings stats for a local agent session') promises session-wide coverage it does not have.


#### CS-072 · MEDIUM · docs · `get_architecture`

**Test files are silently excluded from packages/layers/hotspots/modules/entry_points while file_count and languages include them, so 'the largest files (hotspots)' is factually wrong and nothing documents the exclusion**

- **Repro:** `get_architecture {"repo": "/home/robert/Projects/code-scent-mcp"}; wc -l tests/contract/test_mcp_finding_tools.py`
- **Observed:** Live: file_count:394 (includes 200 test files per get_repo_map), yet hotspots' 10 entries are all src/ files and omit tests/contract/test_mcp_finding_tools.py — verified 662 lines, larger than 8 of the 10 reported hotspots (843/702/597/552/552/551/527/518/512/505). Filter at src/codescent/services/architecture.py:86 (source_files = non-test); tool description and payload never mention it.
- **Expected:** Document/flag the exclusion (e.g. 'hotspots (non-test)') or include tests; counts and structure in one payload should cover the same file set.
- **Verification (confirmed):** Line count and hotspot list verified live against wc -l; the filter is one line of code with zero surfaced documentation, so recategorizing to docs is already correct as filed.


#### CS-073 · MEDIUM · noise · `get_architecture`

**Module member lists are silently truncated at 25 entries while the size field says more, with no omitted_count or truncation marker**

- **Repro:** `get_architecture {"repo": "/home/robert/Projects/code-scent-mcp"}`
- **Observed:** Live: module 'pkg:src/codescent/services' reports size:101 with exactly 25 members listed and no partial-list marker. MEMBER_CAP=25 at src/codescent/services/architecture.py:34; slices at lines 167 and 203 while size=len(members).
- **Expected:** An explicit omitted_count/truncated flag (the convention scan_code_health already uses).
- **Verification (confirmed):** Reproduced live; size-vs-members disagreement is the only clue and reads as exhaustive membership.


#### CS-074 · MEDIUM · ux · `get_repo_status`

**finding_count aggregates all-time findings (~96% resolved/suppressed) and no field reports the actual open count, so the payload's two counts together misrepresent the backlog**

- **Repro:** `get_repo_status {"repo": "/home/robert/Projects/code-scent-mcp"}`
- **Observed:** Live: finding_count:28865 (27582 resolved + 490 suppressed included), unresolved_finding_count:0; the real open+regressed count (793) appears nowhere in the payload. finding_count() at src/codescent/storage/repositories/index_status.py:33-41 counts all statuses.
- **Expected:** Report open_count (as list_findings already does) or a status breakdown; an all-time cumulative total has near-zero orientation value.
- **Verification (confirmed):** DB ground truth re-verified via read-only sqlite: total 28865, open 714, regressed 79. Compounds finding #3: an agent currently reads '28865 findings, 0 unresolved'.


#### CS-075 · MEDIUM · ux · `get_repo_status`

**Passing a subdirectory as repo yields a plausible but wrong status: 'not_git' despite being inside the git work tree, silently reading a nested shadow .codescent with no root-mismatch warning**

- **Repro:** `get_repo_status {"repo": "/home/robert/Projects/code-scent-mcp/src"}`
- **Observed:** Live: git_available:false, git_status:"not_git", indexed_files:150, finding_count:481, warnings:[] — a confident shadow status read from src/.codescent (left by an earlier session's state-creating tool call). detect_git_state at src/codescent/services/git.py:122-124 only checks repo_root/.git existence and never walks up.
- **Expected:** Detect the enclosing git work tree / indexed CodeScent root and warn, instead of confidently reporting not_git plus a shadow index.
- **Verification (confirmed):** Reproduced live exactly as filed; source confirms no upward walk. Interacts with finding #1: the shadow index this reads was itself created by the silent-bootstrap behavior.


#### CS-076 · MEDIUM · gap · `get_schema`

**response_keys is empty for context_stats, retrieve_result, and explain_finding, contradicting the tool's own 'every registered tool with its params and response keys' summary**

- **Repro:** `get_schema {}`
- **Observed:** Live output: exactly those three tools carry "response_keys":[] out of 42; context_stats actually returns 16+ keys. Root cause at src/codescent/mcp/schema.py:164-173: _response_keys resolves the return-annotation string as a module attribute expecting a TypedDict; context_stats returns dict[str, object] (session_stats_tools.py:29), retrieve_result returns the plain alias ResultToolPayload = dict[str, object] (result_tools.py:23), explain_finding returns the union ExplainFindingResult (finding_tools.py:124) — all three fail get_type_hints and silently fall back to ().
- **Expected:** Response keys derived for dict/union-returning tools too, or an explicit response_keys_unknown marker instead of a silent empty list.
- **Verification (confirmed):** Reproduced live; root-cause detail refined (only context_stats literally annotates dict[str, object]; the other two fail via a dict alias and a union type respectively — same silent-fallback path).


#### CS-077 · MEDIUM · docs · `get_schema`

**The documented MCP tool contract docs/mcp-tools.md does not exist, though README.md and AGENTS.md declare it authoritative**

- **Repro:** `test -f docs/mcp-tools.md; grep -n mcp-tools.md README.md AGENTS.md`
- **Observed:** File ABSENT; docs/ contains only decisions/ and diagrams/. References confirmed live: README.md:99, AGENTS.md:65 ('MCP tool contract'), AGENTS.md:102, AGENTS.md:138 ('outrank older docs'). Known baseline: 16 docs/contract tests fail with FileNotFoundError on clean main.
- **Expected:** The contract file present, or README/AGENTS references and tests updated to the real location.
- **Verification (confirmed):** All four references verified present and the file verified absent; this also blocked the doc-cross-check step of this audit for every tool in the group — no prose contract exists to validate the 42-tool surface against.


#### CS-078 · LOW · ux · `context_stats`

**Unknown session_id returns ok:true with all-zero stats, indistinguishable from a real idle session**

- **Repro:** `context_stats {"repo": "/home/robert/Projects/code-scent-mcp", "session_id": "totally-bogus-session-xyz-verify"}`
- **Observed:** Live: ok:true, tool_calls:0, warnings:[], only the echoed session_id distinguishes it — same shape as a genuinely empty session.
- **Expected:** A warning like 'no events recorded for this session id' so typos are catchable.
- **Verification (confirmed):** Reproduced live with a fresh bogus id; the same repo returns tool_calls:22 for the real live session id, so the zero response is purely the missing-key case.


#### CS-079 · LOW · gap · `context_stats`

**Stats aggregate only the first 500 session events — and it is the OLDEST 500 (order by created_at asc, limit 500), so long sessions' stats freeze and all NEW activity beyond 500 events becomes invisible, with no window indicator in the payload**

- **Repro:** `Read src/codescent/services/session_stats.py:20,77-81 and src/codescent/storage/repositories/session_events.py:118-146`
- **Observed:** MAX_EVENTS=500; list_events runs 'order by created_at, id limit ?' with safe_limit=min(max(limit,0),500) — ascending, so the window keeps the earliest 500 events, the opposite of the filed 'newest 500'. to_payload (session_stats.py:43-67) carries no events_considered/window_truncated field.
- **Expected:** Payload notes the event window; and the window should keep recent events, not the session's opening ones.
- **Verification (partial):** Real and confirmed in source, but the filed detail was inverted: the clamp drops the newest events, not the oldest — arguably worse (stats stop updating mid-session) though still low impact for an introspection tool; live session is well under 500 events.


#### CS-080 · LOW · ux · `context_stats`

**warnings field shape is inconsistent with every other tool: objects with warning_code/count instead of plain strings**

- **Repro:** `Read src/codescent/services/session_stats.py:258-268 vs RepoStatusToolPayload warnings: tuple[str, ...]`
- **Observed:** _warnings builds [{"warning_code": ..., "count": ...}, ...] under the same 'warnings' key every other tool populates with plain strings (e.g. repo_tools.py:54, and every live payload captured this session).
- **Expected:** One warnings shape across the envelope, or a differently named field (warning_counts) for the aggregated form.
- **Verification (confirmed):** Source verified at the exact cited lines; string-shaped warnings confirmed live on get_repo_status.


#### CS-081 · LOW · bug · `get_architecture`

**packages field lists plain files as packages when the root has top-level source files**

- **Repro:** `get_architecture {"repo": "/home/robert/Projects/code-scent-mcp/tests"}`
- **Observed:** Live: packages includes "__init__.py", "precision_payloads.py", "sarif_support.py", "test_package_metadata.py". _package_root at src/codescent/services/architecture.py:121-125 returns parts[0], which for a root-level file is the filename. get_repo_map's _top_level (repo_tools.py:272-274) shares the derivation.
- **Expected:** packages/top_level restricted to directories, or files split into their own key.
- **Verification (confirmed):** Reproduced live; also verified the call is genuinely read-only — no tests/.codescent existed before or after the call.


#### CS-082 · LOW · noise · `get_repo_map`

**sample_files is just the first 20 inventory paths alphabetically, so on this repo it always returns evals/precision_corpus fixtures and zero production source**

- **Repro:** `get_repo_map {"repo": "/home/robert/Projects/code-scent-mcp"}`
- **Observed:** Live: all 20 sample_files are evals/ corpus fixtures, identical across calls; inventory[:SAMPLE_FILE_LIMIT] at src/codescent/mcp/repo_tools.py:190 with SAMPLE_FILE_LIMIT=20 at line 26.
- **Expected:** A representative sample (per top-level dir, or largest/most-referenced) or drop the field.
- **Verification (partial):** Reproduced live exactly; severity downgraded medium→low: the field is pure dead weight (~20 lines of fixture paths) but sits beside accurate top_level/languages/entrypoints, so it is unlikely to drive a wrong decision on its own.


#### CS-083 · LOW · noise · `get_repo_map`

**entrypoints includes a test-fixture CLI and disagrees with get_architecture's entry_points on the same repo**

- **Repro:** `get_repo_map {"repo": "/home/robert/Projects/code-scent-mcp"} vs get_architecture {"repo": "/home/robert/Projects/code-scent-mcp"}`
- **Observed:** Live: get_repo_map entrypoints = [src/codescent/__main__.py, src/codescent/cli/main.py, tests/fixtures/python-basic/src/acme_tasks/cli.py]; get_architecture entry_points = the first two only (its is_test filter removes the fixture). Name-match via ENTRYPOINT_NAMES at repo_tools.py:28 / architecture.py:35.
- **Expected:** Consistent entry-point semantics across both orientation tools; fixtures not presented as project entry points.
- **Verification (confirmed):** Both payloads captured live in the same session; disagreement is exactly one fixture path.


#### CS-084 · LOW · noise · `get_repo_status`

**Error envelope duplicates details and severity at both top level and inside data on every error**

- **Repro:** `get_repo_status {"repo": "/nonexistent/other"}`
- **Observed:** Live: {"code": "invalid_repo_root", "data": {"details": {"root": "/nonexistent/other"}, "severity": "error"}, "details": {"root": "/nonexistent/other"}, ..., "severity": "error"} — details and severity each appear twice with identical content.
- **Expected:** One copy of details/severity in the error envelope.
- **Verification (confirmed):** Reproduced byte-for-byte live.


#### CS-085 · LOW · perf · `get_repo_status`

**finding_count()/unresolved_finding_count() materialize every findings row via fetchall()+len() instead of COUNT(*)**

- **Repro:** `Read src/codescent/storage/repositories/index_status.py:33-62; get_repo_status on the dogfood DB`
- **Observed:** Confirmed in source: 'select id from findings' + fetchall() + len(rows) (lines 36-41) and 'select 1 from findings where ...' + fetchall() + len (lines 53-62) — pulls all 28,865 id rows per status call against the ~46MB DB.
- **Expected:** SELECT COUNT(*) — constant memory, one row back.
- **Verification (confirmed):** Source verified directly; DB row count (28,865) verified via read-only sqlite. Low is the right severity: wasteful but sub-second at this scale.


#### CS-086 · LOW · gap · `get_repo_status`

**changed_files silently caps at 20 entries with no total count or truncation marker**

- **Repro:** `Read src/codescent/mcp/repo_tools.py:254 and the RepoStatusToolPayload TypedDict`
- **Observed:** changed_files=changed_files[:CHANGED_FILE_LIMIT] (limit 20 at line 27); RepoStatusToolPayload (lines 43-55) has no changed_file_count or truncated field, so 20 and 200 changed files render identically. Note index_fresh (line 248-252) does still go false, so staleness itself is not hidden.
- **Expected:** A changed_file_count alongside the bounded list.
- **Verification (confirmed):** Structurally certain from source; live repro not run since it would require dirtying 20+ tracked files, which this audit forbids.


### 6.6 Findings (scan_code_health, list_findings, explain_finding, get_calibration, get_changed_file_health) — 19 findings


#### CS-087 · HIGH · bug · `get_calibration`

**Calibration counts mechanical auto-resolves (findings absent on rescan) as human 'accept' verdicts, inflating per-rule confidence toward 1.0**

- **Repro:** `get_calibration(repo='.')`
- **Observed:** Live payload: generic.duplicate_literal accepted=24,901 rejected=0 accept_rate=1 base 0.7->adjusted 0.9; all 30 rules show rejected=0; 12+ rules boosted, several to 1.0; python.missing_nearby_test 0.65->0.85 (feeds its tier-verified gate visibility).
- **Expected:** Only deliberate verdicts should feed calibration; churn-driven auto-resolution must be excluded.
- **Verification (confirmed):** src/codescent/services/calibration.py:32 _ACCEPTED_STATUSES = {FindingStatus.RESOLVED}; module docstring (lines 1-4) claims the signal is 'what humans/agents did with each finding'. But code_health.py:154 _resolved_absent_ids + :658-668 _record_resolved_absent mechanically set status=resolved for any finding absent from the current scan (file churn). Store holds 27,582 resolved rows for a 394-file repo, so accepts are overwhelmingly mechanical; the 490 suppressed rows count as neither accept nor reject (calibration.py:33 only WONTFIX/IGNORED reject).


#### CS-088 · HIGH · bug · `get_changed_file_health`

**Empty path returns ok:true with all 27,779 empty-file_path findings inline (~6.1 MB) instead of a validation error; no inline bound on this tool at all**

- **Repro:** `get_changed_file_health(path='', repo='.') — reproduced at service layer via .venv/bin/python calling codescent.mcp.risk_tools.get_changed_file_health(path='') to avoid detonating the verifier's context`
- **Observed:** ok:True, file_ok:True, path:'', risk_score 0.9/high, 27,779 finding_ids + 27,779 findings, 6,093,867 JSON chars, risk_notes[0]='not currently changed: ' with empty path interpolated. Store grew since the original audit (5.7M -> 6.09M).
- **Expected:** Recoverable invalid_value error for empty path, or the 25-item inline bound + result_id paging that list_findings applies.
- **Verification (partial):** Reproduced exactly. Root cause: src/codescent/services/risk.py:128-132 filters findings by finding.file_path == path (''-matches the 27,779 legacy empty-file_path rows) and src/codescent/mcp/risk_tools.py:72-114 applies no path validation and no inline bound. Severity downgraded critical->high: no data loss/corruption; most MCP clients reject the oversized response so the practical failure is a broken call plus potential context blowout, recoverable by the caller.


#### CS-089 · HIGH · bug · `get_changed_file_health`

**Read-only tools intermittently fail with concurrent_write under strictly serial calls because every read path opens a write transaction and the writer claim raises instead of waiting**

- **Repro:** `Serial calls to explain_finding / get_calibration / get_changed_file_health while the debounced background reindex is writing`
- **Observed:** Reproduced 6 times in this verification session on strictly serial calls: explain_finding(view=summary) x1, get_calibration x3 consecutive (needed a sleep before succeeding), get_changed_file_health(status.py) x2. scan_runs shows a background scan completed at 17:49 during the session, matching the contention window.
- **Expected:** Read paths should use the reader path (RepositoryStorage.read_connection waits for writers) or the writer claim should wait with a timeout instead of raising immediately.
- **Verification (confirmed):** Root cause in code: explain.py:134, risk.py:170, calibration.py:269, verification.py:90, refactor_planning.py:219 all call initialize_storage(), which runs storage.write_transaction() (migrate + quick_check) on every call (src/codescent/storage/repository.py:39-44); _claim_writer (repository.py:92-98) raises concurrent_write immediately instead of waiting (only _claim_reader waits), and cross-process 'begin immediate' fails after the 5s busy_timeout when the reindex hook holds the lock. Only get_repo_status uses the true reader path via state_for (repo_tools.py:227).


#### CS-090 · HIGH · noise · `list_findings`

**python.missing_nearby_test (149 open, largest open rule) is systematically false-positive: the rule never checks the filesystem at all — it fires on every non-test module with symbols regardless of existing tests**

- **Repro:** `explain_finding(finding_id='python.missing_nearby_test:f355ee8278f9', view='fix') vs get_changed_file_health(path='src/codescent/services/answer_pack.py')`
- **Observed:** Finding claims answer_pack.py 'has symbols but no nearby tests/test_answer_pack.py' (tier verified, confidence boosted 0.65->0.85 by the calibration bug), while tests/integration/test_answer_pack.py exists (11 KB) and get_changed_file_health on the same file returns suggested_tests=['tests/integration/test_answer_pack.py'] in the same server. sqlite: 149 open missing_nearby_test rows.
- **Expected:** Resolve tests via the same test-mapping machinery suggest_tests already uses.
- **Verification (confirmed):** Worse than claimed: src/codescent/engine/rules/python_patterns.py:93-113 _missing_nearby_tests contains no filesystem check whatsoever — tests/test_<stem>.py is only a string used in the message; the rule unconditionally emits for every non-test file with symbols (minus three hardcoded name exclusions). Suppression (engine/suppression.py:45-56) only drops it inside test files, never when a test exists.


#### CS-091 · MEDIUM · bug · `explain_finding`

**Human-readable message is stale and contradicts the fresh structured evidence in the same payload because the rescan upsert refreshes evidence_json but never message/title**

- **Repro:** `explain_finding(finding_id='python.large_class:8fa8f0c5ffc6', view='summary')`
- **Observed:** message: 'codescent.services.search.SearchService spans 225 lines.' while evidence in the same response is {line_count:212, threshold:200}. Independent ast check of src/codescent/services/search.py: SearchService spans lines 64-275 = exactly 212 lines, so evidence is fresh and the message is stale.
- **Expected:** Regenerate message from current evidence when a finding is re-detected/regressed.
- **Verification (partial):** Reproduced live. Root cause located: src/codescent/services/code_health.py:216-233 — the 'on conflict(stable_key) do update' sets evidence_json/confidence/provenance but omits message and title, so the message stays frozen at first detection. Severity downgraded high->medium: the structured evidence in the same payload is correct, so the contradiction misleads rather than corrupts.


#### CS-092 · MEDIUM · ux · `explain_finding`

**Fix view's 'bounded source snippet' collapses to the file's first line whenever the rule records no line anchor in evidence, making the 'fix-ready explanation' locationless**

- **Repro:** `explain_finding(finding_id='python.deep_nesting:04d533a87f9b', view='fix')`
- **Observed:** Live: evidence is only {depth:7, threshold:4} with no line/function; snippet is start_line:1 end_line:1 'from __future__ import annotations'. Same pattern reproduced on generic.duplicate_literal:20b09c30a9f7 (snippet line 1: '<!DOCTYPE html>') and on the missing_nearby_test fix view (line-1 import).
- **Expected:** Rules should persist a line anchor (deep_nesting knows the deepest node) and fix view should show the offending range.
- **Verification (confirmed):** Reproduced live on three findings. Note the identity design (model.py:134-151) excludes 'line'/'start_line' from the stable_key but rules like deep_nesting simply never emit any positional evidence at all, so the snippet fallback is line 1.


#### CS-093 · MEDIUM · noise · `get_changed_file_health`

**risk_score saturates at 0.95/'high' for nearly every file because the score is a max() dominated by a near-constant impact confidence; change-state and severity barely discriminate**

- **Repro:** `get_changed_file_health(path='src/codescent/services/status.py') and (path='src/codescent/services/answer_pack.py')`
- **Observed:** Live: status.py (2 info findings, max confidence 0.65) -> 0.95/high; answer_pack.py (3 info findings, max confidence 0.75) -> 0.95/high; both with risk_notes 'not currently changed'. 0.95 can only come from impact_confidence since severity_score(info)=0.3 and finding confidences are lower.
- **Expected:** Risk should scale with severity/status/change-state; unchanged info-only files must not tie with warning-laden hotspots.
- **Verification (confirmed):** src/codescent/services/risk.py:230-238 _file_risk_score = min(max(severity_score, max finding confidence, impact_confidence), 1.0) — a pure max, so a saturated impact_confidence (0.95) flattens everything; :234-235 zero-finding files get impact*0.5 (=0.475 'medium'); is_changed only feeds the risk_notes string (:125,156-159, comment R6), never the score; findings are filtered only by file_path with no status filter (:128-132).


#### CS-094 · MEDIUM · bug · `get_changed_file_health`

**Nonexistent in-repo file path returns the generic unrecoverable 'internal' error**

- **Repro:** `get_changed_file_health(path='src/codescent/services/ghost_module.py', repo='.')`
- **Observed:** Live: {code:'internal', data:{}, message:'An internal error occurred while handling the tool call.', ok:false, recoverable:false}.
- **Expected:** Recoverable not_found naming the path, ideally with nearest-match suggestions.
- **Verification (confirmed):** Reproduced live in this session. The unhandled exception in the health pipeline is not a CodeScentError, so error_boundary.py maps it to internal/unrecoverable; path-traversal is separately handled via normalize_repo_path (paths.py:19-33, path_outside_root recoverable), confirming only the missing-file branch is unguarded.


#### CS-095 · MEDIUM · ux · `get_repo_status`

**get_repo_status count semantics mislead: finding_count is every row ever stored (28,865) while unresolved_finding_count=0 means 'no open/regressed rows with missing file_path', not 'nothing unresolved'; a third finding_count semantic exists in services/status.py**

- **Repro:** `get_repo_status(repo='.') vs sqlite status counts`
- **Observed:** Live payload: {finding_count: 28865, unresolved_finding_count: 0, indexed_files: 394} while the store holds open=714, regressed=79, suppressed=490, resolved=27,582. An agent reading the payload concludes '28,865 findings, 0 unresolved'.
- **Expected:** Rename the diagnostic (e.g. unlocated_finding_count), expose open/regressed counts, unify the three finding_count semantics.
- **Verification (partial):** Confirmed live and in code: index_status.py:33-41 finding_count = select id from findings (all rows); :43-62 unresolved_finding_count counts open/regressed rows with EMPTY file_path (persistence-migration diagnostic per its docstring); services/status.py:69-73 _finding_count = status != 'resolved' (=1,283) under the same name. Corrections: the tool is get_repo_status (the original filed it under get_changed_file_health), and severity high->medium — misleading status payload, but correct lifecycle counts are one list_findings call away.


#### CS-096 · MEDIUM · bug · `list_findings`

**deferred_count and gate_notes report the store-wide 25,896 gate-hidden count regardless of the status filter**

- **Repro:** `list_findings(repo='.', status='regressed')`
- **Observed:** Live: status=regressed returns total_count=79 (78 info + 1 warning), all 79 items available (25 inline + 54 pageable, i.e. nothing in this filter was gate-hidden), yet deferred_count=25896 and gate_notes claim '25896 lower-severity info/heuristic finding(s) hidden by the default gate'. Default status='all' call returns the identical 25896.
- **Expected:** deferred_count should count gate-hidden items within the requested status filter (0 for regressed).
- **Verification (confirmed):** Reproduced live on status=regressed and status=all; identical deferred_count=25896 while the regressed filter demonstrably hid zero items (returned_count 25 + omitted_count 54 = total_count 79).


#### CS-097 · MEDIUM · noise · `list_findings`

**Default status='all' fills the 25-slot inline window mostly with resolved/suppressed rows that have empty file_path, ordered alphabetically by finding_id, contradicting the docstring's 'leads with the actionable set'**

- **Repro:** `list_findings(repo='.')`
- **Observed:** Live: 16 of the 25 inline items are status='resolved' with file_path:'' (plus 1 suppressed); items are ordered by finding_id alphabetically (generic.large_file:1a..., :27..., :2c...); open_count=714 but only ~8 open items made the inline window.
- **Expected:** Order inline items open/regressed first or default to status='backlog'; hide or backfill empty-file_path resolved rows.
- **Verification (confirmed):** Reproduced live; counted 16/25 resolved+empty-path inline items. Tool docstring promises 'Leads with the actionable set (warning+ severity or verified tier)' — the window is instead alphabetical warning-severity rows dominated by dead pre-migration resolved rows.


#### CS-098 · MEDIUM · bug · `list_findings`

**Existing directory without CodeScent state yields a generic unrecoverable 'internal' error (unwritable dirs) or silently creates .codescent state (writable dirs) instead of an actionable not-indexed error**

- **Repro:** `list_findings(repo='/etc') — NOT re-run per hang-guard rule; verified by code inspection`
- **Observed:** Per original audit: {code:'internal', recoverable:false} with no hint; nonexistent paths correctly get recoverable invalid_repo_root.
- **Expected:** Recoverable 'No .codescent state at <root>; run scan_code_health first' with fix_hint.
- **Verification (confirmed):** Confirmed by inspection (out-of-repo repro forbidden by hang guard): core/paths.py:6-16 only checks is_dir (so /etc passes; nonexistent paths get invalid_repo_root, matching the observed contrast); the read path then calls initialize_storage which does state_dir.mkdir (repository.py:35) — PermissionError on an unwritable dir is not a CodeScentError, so mcp/error_boundary.py:58-64,85-92 maps it to code:internal, recoverable:false. No is-indexed check exists anywhere; on a writable dir it would silently create .codescent state instead of erroring, which the tool's own 'read-only for source' framing makes worse.


#### CS-099 · MEDIUM · bug · `scan_code_health`

**findings_created reports the number of findings emitted by the scan (1,056), not rows created; every no-op rescan claims 1,056 created**

- **Repro:** `scan_code_health(repo='.') — verified via code + scan_runs history instead of another side-effecting scan`
- **Observed:** scan_runs table (read-only sqlite): 8 most recent runs all record findings_created=1056, findings_resolved=0; sum(findings_created)=98,388 across 18 runs while the findings table holds only 28,865 rows and did not grow between runs.
- **Expected:** Name the field findings_emitted/findings_active or report actual created/reopened/resolved deltas.
- **Verification (confirmed):** src/codescent/services/code_health.py:267 findings_created=len(findings) — the full emitted set, upserted with 'on conflict(stable_key) do update' (:216) so existing rows are updated, not created. scan_runs insert (:169,181) persists the same inflated number.


#### CS-100 · MEDIUM · noise · `scan_code_health`

**Generic text rules fire nonsensically on generated artifacts: duplicate_literal on HTML report CSS classes (24,966 rows, 86% of the store) and warning-severity large_file on generated reports and a JSON allowlist**

- **Repro:** `explain_finding(finding_id='generic.duplicate_literal:20b09c30a9f7', view='fix') and list_findings default view`
- **Observed:** Live: finding says 'CBM_MINING_REPORT.html repeats a literal 10 times' (literal: 'badge b-int', a CSS class), fix: 'Name the repeated literal once and reuse it.' — meaningless for HTML. sqlite: generic.duplicate_literal = 24,966 of 28,865 rows (86.5%). All 5 open generic.large_file warnings target FFF_MINING_REPORT.html, CODESCENT_ROADMAP.html, CBM_MINING_REPORT.html, scripts/dogfood_allowlist.json, CODESCENT_MCP_UX_AUDIT.md — zero source files.
- **Expected:** Exclude or downweight generated reports/data files for generic text-resolution rules.
- **Verification (confirmed):** Reproduced live; artifact targets read directly from the default list_findings inline window and the explain_finding payload; row shares verified against .codescent/index.sqlite read-only.


#### CS-101 · MEDIUM · perf · `scan_code_health`

**Finding rows accumulate without any pruning: 28,865 rows (27,582 resolved kept forever) for a 394-file repo, 97 MB sqlite; the stale mass inflates counts, calibration, and the empty-path payload**

- **Repro:** `sqlite counts + get_repo_status(indexed_files=394) + grep for any 'delete from findings'`
- **Observed:** 28,865 total vs 714 open; 27,582 resolved (27,779 rows with empty file_path); index.sqlite is 97 MB; no code path ever deletes finding rows (only a schema.py comment mentions 'delete from findings'). sum(scan_runs.findings_created)=98,388 vs 28,865 actual rows.
- **Expected:** Compact or age out superseded auto-resolved rows so totals reflect meaningful history.
- **Verification (partial):** Accumulation, permanence, and downstream inflation (calibration accepts, finding_count=28865, 6.1MB empty-path payload) all confirmed. Mechanism correction: current stable_key deliberately excludes line positions and magnitudes (engine/rules/model.py:116-151, which admits earlier versions 'leaked' line keys and re-keyed findings on line shifts), and the 8 most recent rescans show findings_resolved=0 — so the churn is largely historical backlog, not ongoing per-rescan stranding; content changes still re-key. The unpruned stale mass and its side effects stand.


#### CS-102 · LOW · ux · `explain_finding`

**Success responses are wrapped in {'result': {...}} while sibling finding tools and explain_finding's own error payloads are flat envelopes**

- **Repro:** `explain_finding(finding_id='python.large_class:94ff1820cf18', view='score') vs list_findings / get_calibration / get_changed_file_health / get_repo_status`
- **Observed:** All five explain_finding successes in this session nest everything (including ok) under 'result'; list_findings, get_calibration, get_changed_file_health, get_repo_status return top-level ok; explain_finding's own not_found and concurrent_write errors are flat.
- **Expected:** One envelope shape across the consolidated finding tools.
- **Verification (confirmed):** Observed directly on every explain_finding success and error payload during this verification session.


#### CS-103 · LOW · ux · `explain_finding`

**not_found available_options ignores the requested rule prefix, offering 10 generic.duplicate_literal ids for a python.dead_code_candidate request**

- **Repro:** `explain_finding(finding_id='python.dead_code_candidate:deadbeef0000')`
- **Observed:** Live: available_options = 10x generic.duplicate_literal:* ids (first-N of the store), none matching the requested rule; sqlite shows 185 real python.dead_code_candidate rows that could have been suggested.
- **Expected:** Filter suggestions by the requested id's rule prefix before falling back.
- **Verification (confirmed):** Reproduced live; dead_code_candidate row count (185) verified read-only against .codescent/index.sqlite.


#### CS-104 · LOW · ux · `explain_finding`

**view=score next_steps circularly advises 'Use explain_finding for evidence' from inside explain_finding**

- **Repro:** `explain_finding(finding_id='python.large_class:94ff1820cf18', view='score')`
- **Observed:** Live: next_steps = ['Extract smaller classes or collaborators.', 'Use explain_finding for evidence before editing source.'].
- **Expected:** Hint at the specific next view (view='fix'/'context') or another tool.
- **Verification (confirmed):** Reproduced live verbatim.


#### CS-105 · LOW · docs · `scan_code_health`

**docs/mcp-tools.md does not exist, so no tool has a verifiable documented contract and several schema docstrings contradict observed behavior**

- **Repro:** `ls docs/ (contains only decisions/ and diagrams/); grep mcp-tools.md in tests`
- **Observed:** docs/mcp-tools.md absent; tests/docs/test_docs.py:15 hardcodes MCP_TOOLS = Path('docs/mcp-tools.md') and three contract tests also reference it — matching the known 16 baseline docs/contract FileNotFoundError failures. Docstring contradictions verified this session: explain_finding 'all read-only' vs live concurrent_write errors; list_findings 'leads with the actionable set' vs alphabetical resolved-first inline window.
- **Expected:** Restore docs/mcp-tools.md or repoint the docs tests; align docstrings with actual gate/ordering/locking behavior.
- **Verification (confirmed):** File absence and test references verified directly; both cited docstring contradictions independently reproduced in this session.


### 6.7 Planning & tests (select_tests, suggest_tests, plan_refactor, refactor_preflight, improvement plan) — 17 findings


#### CS-106 · CRITICAL · bug · `refactor_preflight`

**impact.affected_files omits every true dependent and lists unrelated/deleted files at confidence 0.95; symbol impact never consults symbol references**

- **Repro:** `mcp__codescent__refactor_preflight {"target_type": "symbol", "target": "ok_envelope", "repo": "/home/robert/Projects/code-scent-mcp"}`
- **Observed:** Reproduced exactly. affected_files = [finding_payloads.py, docs/configuration.md, docs/mcp-tools.md, evals/precision_corpus/pkg/todo_cluster.py, evals/tool_selection_tasks.json, plans/README.md, cli/hooks.py, cli/reporting.py, core/errors.py, core/json_decode.py], confidence 0.95. Grep ground truth: ok_envelope is referenced by exactly 7 src files (its definition + 6 mcp/*_tools.py callers: session_stats_tools, planning_tools, architecture_tools, repo_tools, context_tools, risk_tools) — zero of the 6 callers appear; the listed cli/core/evals files contain no references; both docs files are deleted from disk. File-target variation confirmed too: for src/codescent/services/answer_pack.py the sole importer src/codescent/mcp/answer_pack_tools.py is absent from affected_files.
- **Expected:** affected_files should contain actual callers/importers ranked before any cap (tool description promises 'impact (callers/refs)'), never zero-reference files, and confidence should not read 0.95 on this signal.
- **Verification (confirmed):** Root cause in code: RefactorPlanningService.get_impact (src/codescent/services/refactor_planning.py:183-203) resolves a symbol to its file then builds affected_files from file-level get_related_files(limit=10) — import-graph/co-change/similarity signals, never symbol references, even though the server has find_references. Confidence per related file = sum of reason weights capped at 1.0 (context_support.py:348-351); _related_rows sorts by (-confidence, path) (context.py:836-843) so saturated ties resolve alphabetically and the real src/codescent/mcp/* callers fall off the 10-item cap; _impact_confidence = mean capped at 0.95 (refactor_planning.py:294-298). Systematic for every symbol target in every repo.


#### CS-107 · HIGH · bug · `plan_refactor`

**Planning tools fail hard with concurrent_write for minutes at a time under strictly serial single-client use**

- **Repro:** `Any planning tool call (refactor_preflight, suggest_tests, plan_refactor) interleaved with Bash activity that triggers the codescent PostToolUse reindex hook`
- **Observed:** Reproduced live during this audit: 7 concurrent_write errors ('Another CodeScent write transaction is already active', db=.codescent/index.sqlite, 86MB) under strictly serial one-call-at-a-time use — 1 on refactor_preflight, then 5 consecutive failures of the identical suggest_tests call spanning ~4 minutes with back-to-back retries and no interleaved writes, before the same call succeeded. select_tests succeeded seconds before a suggest_tests failure, showing intermittent per-call lock collisions.
- **Expected:** Nominally read-only planning tools should not take an exclusive write transaction per call, or the server should queue behind the background reindex instead of hard-erroring.
- **Verification (confirmed):** Code confirms both halves: initialize_storage (src/codescent/storage/repository.py:32-57) runs migrate + quick_check inside write_transaction and is called by _repository() on every planning call (refactor_planning.py:218-220), so pure reads demand the write lock; _claim_writer (repository.py:92-98) raises concurrent_write immediately with no wait when another in-process writer (the debounced hook reindex) is active — in contrast _claim_reader waits on the condition variable (repository.py:106-112); cross-process contention errors after the 5s busy_timeout (repository.py:82-84,163). No retry/queue anywhere.


#### CS-108 · HIGH · bug · `suggest_tests`

**scaffold=true characterizes the first symbol in the file instead of the finding's target symbol**

- **Repro:** `mcp__codescent__suggest_tests {"finding_id": "python.dead_code_candidate:47700b78263f", "repo": "/home/robert/Projects/code-scent-mcp", "scaffold": true}`
- **Observed:** Reproduced on both cited findings. Finding 47700b78263f's message is 'codescent.services.context_support.symbol_payload is not referenced...' (evidence start_line 131, verified in the index DB), but the scaffold imports and characterizes SymbolMatchPayload — the first class in the file (line 41). python.large_class:8fa8f0c5ffc6 (about class SearchService) scaffolds _annotate_quality, an unrelated module-level private helper.
- **Expected:** Scaffold should target the symbol the finding is about; the symbol name is present in the finding message and the line range in evidence_json.
- **Verification (confirmed):** src/codescent/mcp/planning_tools.py:264-272 passes context.relevant_symbols — ALL symbols of the file in file order (refactor_planning.py:119-123) — and build_characterization_scaffold takes qualified_symbols[0] (src/codescent/services/scaffold.py:87-88). The finding's own message/evidence (which name symbol_payload and lines 131-143) are never consulted. Pinning an unrelated symbol misdirects the refactoring agent, so high severity stands.


#### CS-109 · MEDIUM · ux · `get_improvement_plan`

**min_severity is effectively ignored: verified-tier info/warning findings bypass the severity gate with no explanation in the output**

- **Repro:** `mcp__codescent__get_improvement_plan {"repo": "/home/robert/Projects/code-scent-mcp", "min_severity": "error"}`
- **Observed:** Reproduced exactly: min_severity='error' returns 82 clusters / 476 findings dominated by severity:'info' clusters (dead_code_candidate, missing_nearby_test) and severity:'warning' (large_function). No note in the response explains why sub-error findings appear.
- **Expected:** Honor min_severity strictly or surface the verified-tier bypass in the response and tool docs.
- **Verification (confirmed):** Root cause verified at src/codescent/services/findings.py:113-116: gate_findings treats confidence_tier=='verified' as actionable regardless of severity (documented only in the code docstring, findings.py:100-105). Read-only DB check confirms all bypassing rules are verified-tier (dead_code_candidate 45, large_function 81, missing_nearby_test 149 open/regressed rows, all tier='verified'). The tool description and payload carry no hint, so the parameter appears broken to a caller.


#### CS-110 · MEDIUM · noise · `get_improvement_plan`

**Plan clusters recommend 'fixing' intentionally-flawed test fixtures and generated report artifacts**

- **Repro:** `mcp__codescent__get_improvement_plan {"repo": "/home/robert/Projects/code-scent-mcp"}`
- **Observed:** Reproduced: 7 clusters target tests/fixtures/test-quality-flawed/** (python+typescript no_op_test, assertion_free_test, over_mocked_test) with 'Add a meaningful assertion' advice, and a generic.large_file cluster advises 'Split cohesive responsibilities into smaller files' for CBM_MINING_REPORT.html, CODESCENT_ROADMAP.html, FFF_MINING_REPORT.html plus a separate cluster for scripts/dogfood_allowlist.json.
- **Expected:** Exclude or de-prioritize fixture directories and non-source artifacts with a stated reason; executing these clusters would break the scanner's own tests.
- **Verification (confirmed):** tests/fixtures/test-quality-flawed/tests/quality_smells_fixture.py opens with '# INTENTIONALLY FLAWED CodeScent fixture ... Do NOT "fix" the smells below' and is consumed by tests/integration/test_test_quality_pack.py — following the cluster's advice breaks that test. 'Split cohesive responsibilities' on generated HTML and a JSON allowlist is meaningless.


#### CS-111 · MEDIUM · noise · `plan_refactor`

**Plan is boilerplate: identical generic steps for every rule; relevant_symbols dumps all file symbols without naming the offender**

- **Repro:** `mcp__codescent__plan_refactor {"finding_id": "python.large_function:c84fa408b227", "repo": "/home/robert/Projects/code-scent-mcp"}`
- **Observed:** Reproduced: goal is 'Address python.large_function in src/codescent/mcp/search_tools.py.' although the finding message names the offender ('codescent.mcp.search_tools.register_search_tools spans 55 lines', verified in the index DB); relevant_symbols lists all 23 symbols of the file with no marker; steps, non_goals, fallback and expected_behavior_preservation are fixed template strings.
- **Expected:** Name the offending symbol and line range (both in the finding message/evidence) and tailor at least one step to the rule.
- **Verification (confirmed):** src/codescent/services/refactor_planning.py:137-159: goal=f'Address {rule_id} in {location}.' plus hardcoded steps/non_goals/fallback tuples identical for every finding; the only rule-sensitive output is _risk() returning 'medium' vs 'low' (refactor_planning.py:244-247). The finding's message and evidence_json (line_count/threshold) are available but unused in the plan text.


#### CS-112 · MEDIUM · bug · `refactor_preflight`

**Impact/co-change output serves files deleted from disk (docs/mcp-tools.md, docs/configuration.md, .omo/plans/...) as blast radius**

- **Repro:** `mcp__codescent__refactor_preflight {"target_type": "symbol", "target": "ok_envelope", "repo": "/home/robert/Projects/code-scent-mcp"}`
- **Observed:** Reproduced: affected_files includes docs/configuration.md and docs/mcp-tools.md; the finding-target variant (python.large_class:8fa8f0c5ffc6) returns docs/mcp-tools.md and .omo/plans/codescent-prd-remainder.md. None exist on disk — docs/ contains only decisions/ and diagrams/; both docs files were deleted in commit b9f122d ('remove docs/**', 2026-06-29) and the .omo plan file is absent.
- **Expected:** Blast-radius candidates from git history should be filtered by on-disk existence before being presented as files to update.
- **Verification (partial):** Mechanism confirmed by code: related-file reasons include git_related_paths and git_co_change_counts (src/codescent/services/context.py:656-659) which read git history and never check existence; ls and git log confirm the files are gone. Downgraded from high to medium: it shares the root cause of the critical affected_files finding, and the concrete harm is one wasted agent turn per phantom file rather than a wrong edit.


#### CS-113 · MEDIUM · bug · `refactor_preflight`

**Invalid target_type silently accepted, echoed back with ok:true, and treated as 'file'**

- **Repro:** `mcp__codescent__refactor_preflight {"target_type": "banana", "target": "src/codescent/services/answer_pack.py", "repo": "/home/robert/Projects/code-scent-mcp"}`
- **Observed:** Reproduced exactly: ok:true, preflight_ok:true, target_type:'banana' echoed in payload and impact, silently treated as file. No warning or error.
- **Expected:** Unknown target_type should return an invalid_value error listing valid values, matching the strict validation the same server applies to min_severity/status/view.
- **Verification (confirmed):** Code: get_impact (src/codescent/services/refactor_planning.py:175-188) only special-cases target_type=='symbol'; any other string falls through to file semantics with no validation. Contrast confirmed: validate_min_severity/_validate_list_status/_validate_explain_view all return invalid_value + valid_values (src/codescent/mcp/finding_tools.py:42,70-100). An agent passing e.g. target_type='function' silently gets file semantics.


#### CS-114 · MEDIUM · bug · `refactor_preflight`

**changed_file_health contradicts itself: missing_nearby_test finding coexists with the suggested test it claims is missing**

- **Repro:** `mcp__codescent__refactor_preflight {"target_type": "file", "target": "src/codescent/services/answer_pack.py", "repo": "/home/robert/Projects/code-scent-mcp"}`
- **Observed:** Reproduced in one response: changed_file_health lists python.missing_nearby_test:f355ee8278f9 for answer_pack.py while suggested_tests/test_selection resolve tests/integration/test_answer_pack.py, which imports codescent.services.answer_pack directly (verified line 8 of the test). The 48-module 'Add nearby tests' plan cluster (31.2 effort points) is inflated by the same false positives.
- **Expected:** missing_nearby_test should consider the tests/ mirror hierarchy or actual test imports — the same data the test-selection service resolves in the same payload.
- **Verification (confirmed):** Rule confirmed blind at src/codescent/engine/rules/python_patterns.py:93-113: it fires whenever the literal flat path tests/test_<stem>.py is absent, never consulting tests/integration|unit/** or the import graph. The preflight's own test_match signal finds the real test in the same response — two subsystems emit contradictory guidance in one payload.


#### CS-115 · MEDIUM · noise · `refactor_preflight`

**risk_score saturates at exactly 0.95/'high' for every file checked, making the risk signal uninformative**

- **Repro:** `mcp__codescent__refactor_preflight {"target_type": "file", "target": "src/codescent/services/answer_pack.py", "repo": "/home/robert/Projects/code-scent-mcp"}`
- **Observed:** Reproduced on all three cited files: answer_pack.py (3 info-only findings, risk_note 'not currently changed'), finding_payloads.py, and search.py all return risk_score:0.95, risk_level:'high'.
- **Expected:** Info-only, unchanged files should not score identically to the repo's worst files; the score is saturated, not calibrated.
- **Verification (confirmed):** Root cause at src/codescent/services/risk.py:230-238: _file_risk_score = min(max(severity_score, max finding confidence, impact_confidence), 1.0), and impact_confidence is the mean of related-file confidences capped at 0.95 (refactor_planning.py:294-298) which itself saturates for any file with 10 max-weight related files — so virtually every indexed file floors at 0.95 regardless of its findings. risk_level threshold then reads 'high' always.


#### CS-116 · MEDIUM · bug · `select_tests`

**Nonexistent path accepted with ok:true and the fallback 'focused command' is the full test suite (bare pytest)**

- **Repro:** `mcp__codescent__select_tests {"paths": ["src/codescent/services/does_not_exist.py"], "repo": "/home/robert/Projects/code-scent-mcp"}`
- **Observed:** Reproduced exactly: ok:true, changed_files echoes the nonexistent path, test_files:[], command:"pytest" — no warning, and the recommended command runs the entire suite despite the tool description promising a 'Bounded minimal test set ... plus one focused command'.
- **Expected:** Nonexistent paths should warn or error (normalize_repo_path already raises PATH_OUTSIDE_ROOT for traversal, so a validation layer exists); an empty selection should not recommend the unbounded full suite as focused.
- **Verification (confirmed):** Code: _changed_files (src/codescent/services/verification.py:123-126) normalizes paths with no existence check; _pytest_command (verification.py:157-160) returns bare 'pytest' for an empty set — same fallback for an empty changed set on a clean repo. Traversal contrast confirmed at src/codescent/core/paths.py:19-33 (PATH_OUTSIDE_ROOT error).


#### CS-117 · MEDIUM · docs · `select_tests`

**The documented tool contract docs/mcp-tools.md does not exist in the repo while tests and the index still expect it**

- **Repro:** `ls /home/robert/Projects/code-scent-mcp/docs/ (contains only decisions/ and diagrams/)`
- **Observed:** Confirmed: docs/mcp-tools.md was deleted in commit b9f122d ('remove docs/**', 2026-06-29); docs/ contains only decisions/ and diagrams/. Four test files still reference it (tests/contract/test_capability_guide.py, test_mcp_resume_task.py, test_mcp_refactor_preflight.py, tests/docs/test_docs.py) and 16 docs/contract tests fail on clean main with FileNotFoundError (known baseline). refactor_preflight still serves the deleted file in impact/co_change outputs.
- **Expected:** Ship docs/mcp-tools.md or update the tests/index to the new contract location; none of the 6 planning/test tools currently have a documented contract to audit against.
- **Verification (confirmed):** git log --diff-filter=D shows b9f122d removed docs/**; grep -rl mcp-tools.md over tests/ lists 4 referencing test files; project memory confirms the 16-test FileNotFoundError baseline on clean main. The deletion was deliberate but left contract tests and index references dangling — a genuine docs gap, correctly categorized.


#### CS-118 · LOW · noise · `get_improvement_plan`

**Inline plan payload carries unbounded per-cluster finding_ids arrays while files arrays are silently capped at 10 — an inconsistent bound**

- **Repro:** `mcp__codescent__get_improvement_plan {"repo": "/home/robert/Projects/code-scent-mcp"}`
- **Observed:** Reproduced: the 'Add nearby tests for 48 module(s) in src/codescent/services' cluster inlines all 48 finding_ids while its files array is truncated to 10 entries with no truncation marker; inline response with 25 clusters is well over 10KB for a docstring-promised 'Bounded output'.
- **Expected:** Cap finding_ids like files (exemplars + count, rest via retrieve_result) and mark the files truncation.
- **Verification (partial):** Confirmed in live output from both default and min_severity=error runs. Downgraded medium→low: cluster count IS bounded (25 inline + result_id/retrieve_result paging), and each cluster's size/theme states the true count ('48 module(s)'), so the silent files cap misleads little; the residual defect is payload bloat and bound inconsistency, not wrong guidance.


#### CS-119 · LOW · ux · `plan_refactor`

**not_found error metadata is confusing: 10 arbitrary duplicate_literal ids as available_options and total_findings 28865 vs the plan's 793**

- **Repro:** `mcp__codescent__plan_refactor {"finding_id": "python.fake_rule:deadbeef0000", "repo": "/home/robert/Projects/code-scent-mcp"}`
- **Observed:** Reproduced exactly: not_found with good fix_hint, but available_options is 10 generic.duplicate_literal ids (the first findings-table rows in id order: generic.duplicate_literal:0002..., :0003..., verified via read-only DB query) and data.total_findings=28865 while get_improvement_plan(include_all=true) reports total_findings 793.
- **Expected:** Sample diverse/high-priority findings (or drop available_options for the fix_hint) and label the two counts' populations consistently.
- **Verification (confirmed):** Read-only index query resolves the 36x discrepancy: 28865 = every findings row across all statuses (27582 resolved + 714 open + 79 regressed + 490 suppressed) while 793 = open+regressed exactly (714+79). Both are emitted under the same unqualified 'total_findings' label; the options sample is arbitrary insertion order, mostly-resolved noise rules.


#### CS-120 · LOW · bug · `refactor_preflight`

**test_selection.test_files (capped at 10) and command string (uncapped, 11 files) disagree**

- **Repro:** `mcp__codescent__refactor_preflight {"finding_id": "python.large_class:8fa8f0c5ffc6", "repo": "/home/robert/Projects/code-scent-mcp"}`
- **Observed:** Reproduced exactly: test_selection.test_files has 10 entries ending at tests/smoke/test_smoke_mcp_search.py; test_selection.command ends '... tests/smoke/test_smoke_mcp_search.py tests/unit/test_search_support.py' — 11 files. impact.likely_tests shows the same 10-item cap.
- **Expected:** The structured list and the runnable command should be built from the same set; programmatic consumers of test_files silently skip tests/unit/test_search_support.py.
- **Verification (confirmed):** Root cause at src/codescent/services/refactor_preflight.py:231-236: _bound_selection truncates test_files to SECTION_ITEM_CAP (10) via dataclasses.replace but leaves the command field — built earlier from the uncapped set in verification.py:81-85 — untouched.


#### CS-121 · LOW · bug · `select_tests`

**Empty-string path is normalized to '.' and reported as a changed file with zero tests selected**

- **Repro:** `mcp__codescent__select_tests {"paths": [""], "repo": "/home/robert/Projects/code-scent-mcp"}`
- **Observed:** Reproduced exactly: ok:true, changed_files:["."], test_files:[], command:"pytest" — the empty string silently coerces to the repo root, which then maps to no tests.
- **Expected:** Empty-string paths should be rejected with an invalid_value error, like traversal already is (PATH_OUTSIDE_ROOT).
- **Verification (confirmed):** Code path: _repo_relative_path -> normalize_repo_path(repo_root, '') resolves (repo_root / '') to repo_root (src/codescent/core/paths.py:19-33), relative_to yields '.'; '.' is neither a test path nor .py so it contributes zero tests (verification.py:72-79) — incoherent 'whole repo changed, no tests relevant' result.


#### CS-122 · LOW · noise · `suggest_tests`

**commands array is a verbatim per-file duplication of likely_tests, inconsistent with select_tests' single combined command**

- **Repro:** `mcp__codescent__suggest_tests {"finding_id": "python.large_class:8fa8f0c5ffc6", "repo": "/home/robert/Projects/code-scent-mcp"}`
- **Observed:** Reproduced: 11 likely_tests and 11 'pytest <file>' commands duplicating the identical paths string-for-string, roughly doubling the payload; sibling select_tests emits one combined 'pytest a b c' for the same purpose.
- **Expected:** One combined command consistent with select_tests.
- **Verification (confirmed):** src/codescent/services/verification.py:59: commands = tuple(f'pytest {path}' for path in likely_tests) — mechanical 1:1 duplication; select_tests uses _pytest_command joining all files (verification.py:157-160). Zero information gain confirmed in live output.


### 6.8 Review & packs (review_diff_risk, subjective_review, answer_pack, how_to_use) — 17 findings


#### CS-123 · HIGH · bug · `answer_pack`

**answer_pack hard-fails with concurrent_write under contention because every call routes search hits through record_frecency, which takes a fail-fast write transaction; writers never wait while readers do.**

- **Repro:** `mcp__codescent__answer_pack {"query": "...", "repo": "src"} while any index write/read is active (e.g. during the debounced PostToolUse reindex)`
- **Observed:** Code confirms the mechanism end-to-end: SearchService.search_files/search_content/search_changed_files call record_frecency (src/codescent/services/search.py:92,135,209), which does initialize_storage + write_transaction (src/codescent/services/search_support.py:197-198); _claim_writer raises immediately if ANY reader or writer is registered (src/codescent/storage/repository.py:92-99) with no wait/retry, while _claim_reader waits for writers. This session review_diff_risk itself returned {code:'concurrent_write', recoverable:true} while the reindex hook ran, succeeding on retry 8s later. Uncontended answer_pack calls (5/5) succeeded, so the original 18-minute total outage was contention/starvation-specific, but the fail-fast design is structural.
- **Expected:** A read-oriented tool should not require the writer claim per call: defer/skip the frecency write on contention, or make _claim_writer wait briefly; error should carry retry guidance.
- **Verification (confirmed):** Confirmed by code inspection (search.py:92,135,209 -> search_support.py:197-198 -> repository.py:92-99 fail-fast) plus a live concurrent_write hit on the same storage layer this session. Original 7/7 failure streak not re-reproduced (uncontended calls succeed), which is consistent with the contention-dependent mechanism.


#### CS-124 · HIGH · bug · `answer_pack`

**Relevance is broken and frecency self-reinforces: a query naming the indexed symbol ok_envelope returns a frecency-boosted cluster of unrelated files, key_symbols is always empty for natural-language queries, and each call writes frecency rows that boost its own outputs in later queries.**

- **Repro:** `mcp__codescent__answer_pack {"query": "where is ok_envelope defined and how do tools build success envelopes", "repo": "src"}`
- **Observed:** Reproduced exactly: top_files=[services/risk.py, services/search_queries.py, services/graph_backend.py, engine/search/ranking.py, services/code_health.py] — none contain ok_envelope (defined in codescent/mcp/finding_payloads.py); key_symbols=[] here and in all 5 calls this session (matching the reporter's 8/8). A second query 'risk scoring for changed files' ranked graph_backend.py, ranking.py and AGENTS.md above risk.py (risk.py demoted to related_files) — the same drift the reporter saw. Root causes in code: _compose feeds the ENTIRE natural-language sentence to find_symbol (src/codescent/services/answer_pack.py:88), which can never match a symbol name; top_files come from search_files/search_content whose ranking consumes frecency_scores while record_frecency writes new signals for every answer_pack result set (search.py:92,135).
- **Expected:** Query relevance should dominate: extract symbol-like terms for find_symbol so key_symbols populates and the defining file surfaces; cap or exclude the tool's own frecency feedback.
- **Verification (confirmed):** Live repro this session reproduced both the junk cluster and empty key_symbols; code inspection pinpoints answer_pack.py:88 (whole-sentence find_symbol) and the record_frecency write/read loop (search.py:92,135; search_support.py:186-198).


#### CS-125 · HIGH · bug · `review_diff_risk`

**Pointing repo at a subdirectory of an indexed repo silently creates a full .codescent state dir (3.3MB index.sqlite + scan_cache.json) inside the source tree and, on first touch, reports every file as 'changed' at high risk because a non-git root counts all unindexed files as changed.**

- **Repro:** `mcp__codescent__review_diff_risk {"repo": "src"} against a src/ with no prior .codescent`
- **Observed:** The artifact is still present and matches the reporter's session: src/.codescent/ with config.toml, 3.3MB index.sqlite and 455KB scan_cache.json, mtimes 2 Jul 13:34 (the original audit window). Code confirms the all-changed mechanism: changed_file_reasons sets include_unindexed=not git_available (src/codescent/services/search_support.py:305-310) and _reasons returns the whole inventory when include_unindexed (lines 328-337); src has no .git, so a fresh state dir marks every file changed. _ensure_findings additionally runs a full CodeHealthService scan (src/codescent/services/risk.py:180-183). Re-running today returns changed_files=[] because the auto-created index now serves as baseline — confirming first-touch-only fabrication. No warning in either payload.
- **Expected:** Error or warn that the root sits inside an already-initialized repo, or at minimum disclose that git is unavailable and 'changed' means 'unindexed' — and never silently write megabytes of state into the source tree.
- **Verification (confirmed):** Persisted src/.codescent artifact (3.3MB, timestamps matching the original call) plus code inspection of search_support.py:305-337 and risk.py:180-183; post-index live call shows the misleading first-touch behavior silently flips to 'all clean'.


#### CS-126 · MEDIUM · bug · `answer_pack`

**When both budget and max_tokens are passed, budget silently wins even when max_tokens is smaller: asking for <=100 tokens returns a 665-token response with truncated:false and no warning.**

- **Repro:** `mcp__codescent__answer_pack {"query": "risk scoring for changed files", "repo": "src", "budget": 4000, "max_tokens": 100}`
- **Observed:** Reproduced live: estimated_tokens=665, truncated:false, warnings:[] — max_tokens=100 ignored. Root cause is a one-liner: effective_budget = budget if budget is not None else max_tokens (src/codescent/mcp/answer_pack_tools.py:58); no min() of the two, no validation, no warning. The tool description advertises max_tokens as THE budget knob ('Pass max_tokens to fit a budget').
- **Expected:** Take min(budget, max_tokens) or reject the ambiguous combination; never silently exceed an explicit max_tokens.
- **Verification (partial):** Live repro + code at answer_pack_tools.py:58. Downgraded high->medium: only bites when the caller passes both overlapping params, and output stays bounded by the larger budget — a contract bug, not an unbounded blowout.


#### CS-127 · MEDIUM · bug · `answer_pack`

**A nonexistent focus_path is echoed back as the pack's only top file with ok:true and no warning, fabricating a source of truth that does not exist.**

- **Repro:** `mcp__codescent__answer_pack {"query": "what does this file do", "repo": "src", "focus_path": "codescent/services/never_existed.py"}`
- **Observed:** Reproduced live: {ok:true, top_files:['codescent/services/never_existed.py'], key_symbols:[], findings:[], warnings:[]}. Root cause: _top_files just normalizes and returns the focus path with no existence check (src/codescent/services/answer_pack.py:105-107); normalize_repo_path only guards traversal, not existence.
- **Expected:** Recoverable file_not_found error, or a warning plus exclusion from top_files.
- **Verification (confirmed):** Live repro this session plus code at answer_pack.py:105-107.


#### CS-128 · MEDIUM · docs · `how_to_use`

**docs/mcp-tools.md does not exist and docs/ contains no per-tool reference (only decisions/ and diagrams/), while README.md and AGENTS.md declare it the authoritative tool contract.**

- **Repro:** `ls docs/; grep -n mcp-tools README.md AGENTS.md`
- **Observed:** Verified: docs/ holds only decisions/ and diagrams/; docs/mcp-tools.md absent. README.md:99 links it; AGENTS.md:65 calls it 'MCP tool contract', AGENTS.md:102 requires updating it, AGENTS.md:138 ranks it authoritative. 16 docs/contract tests fail on clean main with FileNotFoundError (known baseline). Payload semantics (risk_score scale, budget vs max_tokens precedence, truncation caps, auto-init side effects) are documented nowhere.
- **Expected:** The contract file present, or README/AGENTS references and tests updated to the real location.
- **Verification (confirmed):** Direct filesystem check plus README.md:99 and AGENTS.md:65,102,138 references; adversarial doc cross-check for every finding in this group was impossible precisely because the contract file is missing.


#### CS-129 · MEDIUM · bug · `review_diff_risk`

**review_diff_risk can silently report a clean tree while an untracked file exists when the git status pass degrades under contention; no degraded-git warning exists in the payload. (Original hard-miss not reproducible on demand.)**

- **Repro:** `Create an untracked .py at repo root, then mcp__codescent__review_diff_risk {"repo": "."}`
- **Observed:** My repro shows CORRECT behavior: the live server reported the fresh untracked probe as changed_files=['verify_probe_untracked.py'], risk 0.475 medium — the reporter's 5-calls-over-30-minutes miss did not reproduce. However the silent-degradation path is real in code: git_working_state returns available=False + empty set on timeout/error (src/codescent/services/git.py:97-100); with the PostToolUse hook having already indexed the new file (hashes match, index_changed empty) and git degraded, changed_file_reasons yields an empty set with no warning field anywhere in the RiskService payload (risk.py builds no git-degradation indicator). So a false 'clean tree' is possible under load and undetectable by the caller.
- **Expected:** Carry a degraded/timeout indicator or warning when the git status pass fails, so an empty changed_files is distinguishable from a genuinely clean tree.
- **Verification (partial):** Live repro today contradicts the headline (file correctly detected); code inspection confirms the silent-degradation path (git.py:97-100 returns available=False silently; no warning plumbing in risk.py payload). Downgraded high->medium: real gap, intermittent trigger, not reproducible on demand.


#### CS-130 · MEDIUM · bug · `review_diff_risk`

**changed_files is silently capped at 20 (DEFAULT_CHANGED_FILE_LIMIT) with no truncation flag, omitted count, or retrieval id, and the aggregate risk_score/findings are computed only from the visible 20.**

- **Repro:** `mcp__codescent__review_diff_risk on a tree with >20 changed files`
- **Observed:** Code confirms: DEFAULT_CHANGED_FILE_LIMIT=20 and _changed_files caps via search_changed_files(limit=20) (src/codescent/services/risk.py:22,163-165); review_diff_risk builds file_health and the aggregate risk_score only from that capped tuple (risk.py:68-94). The payload TypedDicts (src/codescent/mcp/risk_tools.py) carry no truncated/omitted_count/result_id field, and live payloads this session show none.
- **Expected:** Report the total changed count or mark truncation explicitly (count + retrieve_result id), matching the 'large result sets are summarized and retrievable by id' safety boundary how_to_use advertises.
- **Verification (confirmed):** Code inspection risk.py:22,163-165,68-94 and risk_tools.py payload shape; live responses contain no truncation marker. Reporter's 149-file case consistent with the alphabetical 20-file slice.


#### CS-131 · MEDIUM · noise · `review_diff_risk`

**Every finding is serialized up to three times in one response (top-level findings[], file_health[].finding_ids, file_health[].findings) plus repeated per-file boilerplate, inflating changed-tree payloads to ~20k tokens.**

- **Repro:** `mcp__codescent__review_diff_risk {"repo": "src"} on a tree with findings`
- **Observed:** Code confirms triple emission: report-level findings at src/codescent/mcp/risk_tools.py:87, per-file finding_ids at :108 AND full per-file findings objects at :109. My live repo='.' call shows the duplicated shape per file_health entry (finding_ids + findings + repeated risk_notes boilerplate 'confidence is bounded by deterministic local graph signals' and per-file next_tools/recommended_commands).
- **Expected:** Emit each finding once at top level and reference by id in file_health; drop the per-file duplicate objects and repeated boilerplate.
- **Verification (confirmed):** risk_tools.py:87,108,109 plus live payload shape observed this session; with 75 findings across 20 files the reporter's ~20k-token payload follows arithmetically.


#### CS-132 · MEDIUM · bug · `review_diff_risk`

**suggested_tests and recommended_commands point at a production rules module (codescent/engine/rules/test_quality.py, zero test functions) because test discovery is pure name/path matching on test_* basenames.**

- **Repro:** `mcp__codescent__review_diff_risk {"repo": "src"} with changed files near engine/rules/`
- **Observed:** Verified: grep -c 'def test' on src/codescent/engine/rules/test_quality.py returns 0, so 'pytest codescent/engine/rules/test_quality.py' collects nothing. Discovery is name-based: is_test_path treats any test_* basename or tests/ path segment as a test (src/codescent/services/answer_pack_support.py:291-293; same pattern in services/search_queries.py), and RiskService takes suggested.likely_tests verbatim (risk.py:154).
- **Expected:** Suggested tests should be actual runnable tests (contain test functions or live under a test root); a verification command that collects zero tests gives false confidence.
- **Verification (confirmed):** 0 'def test' occurrences confirmed by grep; name-matching classifier confirmed at answer_pack_support.py:291-293 and risk.py:154. Cross-corroborated by the search-special group's identical is_test_path finding.


#### CS-133 · MEDIUM · bug · `review_diff_risk`

**Any tool call against any existing directory silently initializes CodeScent state there (auto-creates .codescent with index.sqlite and runs a full code-health scan), so a typo'd repo path writes state into and indexes arbitrary directories.**

- **Repro:** `Any codescent tool with repo=<existing uninitialized dir> (verified in-repo only; out-of-repo repro skipped per hang guard)`
- **Observed:** Confirmed by code inspection: initialize_storage unconditionally creates the state dir, DB and config (src/codescent/storage/repository.py:32-57) and is reached from read paths (record_frecency at search_support.py:197, RiskService via SearchService); _ensure_findings runs a full CodeHealthService scan when no findings exist (risk.py:180-183). In-repo artifact proves it live: src/.codescent (3.3MB) was auto-created by a review_diff_risk {repo:'src'} call with no warning. how_to_use meanwhile instructs 'run the init CLI once', so the auto-init is undocumented behavior contradicting the stated workflow.
- **Expected:** Uninitialized roots should produce a recoverable 'not initialized' error or the response should disclose that state was just created; repo='/home/<user>' would silently index a whole home directory.
- **Verification (confirmed):** Confirmed by inspection (repository.py:32-57, search_support.py:197, risk.py:180-183) plus the persisted src/.codescent artifact; out-of-repo live repro deliberately not run because codescent calls with out-of-repo paths hang (audit hang guard).


#### CS-134 · LOW · bug · `answer_pack`

**Negative max_tokens is accepted silently and misreported as 'query alone exceeds the token budget' instead of being rejected as invalid.**

- **Repro:** `mcp__codescent__answer_pack {"query": "risk scoring", "repo": "src", "max_tokens": -5}`
- **Observed:** Reproduced live: {ok:true, truncated:true, estimated_tokens:34, warnings:['answer pack query alone exceeds the token budget; expand the full set via ctx_9acf8fff05321aab']}. No validation exists anywhere on the path: answer_pack_tools.py:58 passes the raw value and fit_budget just loops while tokens > budget (answer_pack_support.py:121-134), so any value <= 0 lands in the budget_exceeded branch.
- **Expected:** invalid_argument-style recoverable error for max_tokens/budget <= 0.
- **Verification (confirmed):** Live repro plus code inspection (answer_pack_tools.py:47-65, answer_pack_support.py:121-134 — no positivity check).


#### CS-135 · LOW · ux · `answer_pack`

**Empty query returns ok:true with backwards advice ('broaden the query'), and next_tools is effectively always ['select_tests'] because the key_symbols branch that would vary it never fires.**

- **Repro:** `mcp__codescent__answer_pack {"query": "", "repo": "src"}`
- **Observed:** Reproduced live: empty query -> ok:true, warnings:['no answer pack context found; broaden the query or run a scan'] — an empty query cannot be broadened. next_tools was ['select_tests'] on all 5 calls this session. Nuance vs. the original claim: next_tools is not literally hardcoded — code prepends get_symbol_context when key_symbols exist (answer_pack_tools.py:86-93) — but since key_symbols is empty for every natural-language query (the whole-sentence find_symbol bug), the constant ['select_tests'] is the de facto behavior.
- **Expected:** Empty query should be an invalid_argument error; next_tools should reflect response content once key_symbols actually populates.
- **Verification (confirmed):** Live repro; code at answer_pack_tools.py:86-93 shows the conditional that never fires, tying this to the key_symbols defect.


#### CS-136 · LOW · noise · `answer_pack`

**top_files ordering is unstable across consecutive identical-intent calls — but the cause is each call's own frecency writes mutating ranking state, not the max_tokens value; budget trimming cannot reorder.**

- **Repro:** `Same query twice with different max_tokens; order of the shared head differs`
- **Observed:** Code refutes the budget-causes-reorder attribution: fit_budget only pops from the tail via _drop_last and never reorders (src/codescent/services/answer_pack_support.py:121-149), and _top_files runs before any budget logic. The real instability is confirmed: record_frecency writes signals for every returned path on every call (search.py:92,135), so the second call ranks against different state — consistent with the reporter's observed head reorder and with the ranking drift I observed across queries this session.
- **Expected:** Ranking stable for a given query and index state; the per-call frecency self-write (already covered by the frecency-loop finding) is the thing to fix.
- **Verification (partial):** Code inspection: answer_pack_support.py:121-149 (_drop_last tail-pop only, no reorder), search.py:92,135 (per-call frecency writes). Real symptom, mis-attributed cause; effectively a facet of the frecency-loop finding.


#### CS-137 · LOW · docs · `how_to_use`

**how_to_use's workflow and safety claims disagree with runtime behavior: it instructs running init/index CLIs although every tool auto-inits and auto-indexes, claims 'deterministic' and 'bounded' output that review_diff_risk's duplicated payload and answer_pack's frecency-drifting rankings violate, and next_tools is always empty.**

- **Repro:** `mcp__codescent__how_to_use {}`
- **Observed:** Reproduced live: workflow step 1 'Initialize CodeScent state for the repo (run the `init` CLI once)', step 2 'run the `index` CLI'; summary claims 'Every tool is local, deterministic, bounded'; next_tools:[]. Contradictions verified this session: src/.codescent was auto-created without any init CLI; answer_pack rankings changed between identical-intent queries as frecency accumulated; review_diff_risk triple-serializes findings.
- **Expected:** Guidance matches runtime (document auto-init or make init required); next_tools populated for a guidance tool.
- **Verification (confirmed):** Live how_to_use output captured this session; contradicting behaviors independently confirmed (auto-init artifact, frecency drift across my own calls, risk_tools.py:87,108,109 duplication).


#### CS-138 · LOW · ux · `review_diff_risk`

**risk_score values are emitted as raw unrounded floats (0.8649999999999999-style) with the scale undocumented; no rounding exists at any serialization boundary.**

- **Repro:** `mcp__codescent__review_diff_risk on a tree with findings-bearing changed files`
- **Observed:** Code confirms: no round() call anywhere in src/codescent/services/risk.py or src/codescent/mcp/risk_tools.py; scores come from float arithmetic (_file_risk_score min/max over confidences and impact_confidence*0.5, risk.py:230-240) and are serialized verbatim. My no-findings probe produced an exactly-representable 0.475 (0.95*0.5), consistent with fp dust appearing only on the findings/confidence paths the reporter exercised (0.8649999999999999, 0.7999999999999999).
- **Expected:** Round to 2-3 decimals at the serialization boundary and document the 0-1 scale.
- **Verification (confirmed):** Grep confirms zero rounding in risk.py/risk_tools.py; float provenance traced at risk.py:230-240; reporter's observed values are the natural output of that arithmetic.


#### CS-139 · LOW · ux · `subjective_review`

**The disabled response's message and privacy_notice are byte-identical duplicates and the payload never names the enable flag or where to set it (only the MCP tool description mentions privacy.allow_llm_review=true).**

- **Repro:** `mcp__codescent__subjective_review {"repo": "."}`
- **Observed:** Reproduced live: message == privacy_notice == 'Subjective LLM review is disabled by default. Enable it only when you intend to send prompt context to the selected provider.' — no flag name, no config path in the payload. Mitigating fact the original finding underweighted: the tool's own MCP description states 'Disabled unless privacy.allow_llm_review=true', so the flag IS discoverable to the calling agent; only the config file location is truly undocumented.
- **Expected:** message should state the concrete enable step (privacy.allow_llm_review=true in .codescent/config.toml) and differ from the boilerplate privacy_notice.
- **Verification (partial):** Live repro confirms the duplicate fields and missing enable step in the payload; downgraded medium->low because the tool description already names the flag, leaving only the config-file location undiscoverable.


### 6.9 Docs contract (surface vs documentation) — 4 findings


#### CS-140 · HIGH · docs · `get_schema`

**docs/mcp-tools.md and the entire docs/ reference tree are absent (deliberately deleted in commit b9f122d without updating dependents), so the documented contract for the 42-tool surface does not exist and the docs/contract test suites fail on clean main.**

- **Repro:** `get_schema() -> tool_count 42; ls docs/ -> only decisions/ and diagrams/; ls docs/mcp-tools.md -> No such file; uv run pytest tests/docs/test_docs.py -> FileNotFoundError.`
- **Observed:** docs/ contains only decisions/ and diagrams/. git log shows commit b9f122d ('remove docs/**', 2026-06-29) deleted 21 files / 10,230 lines including docs/mcp-tools.md (874 lines), cli-reference.md, getting-started.md, prd.md, architecture.md, etc. Four test files still hardcode Path('docs/mcp-tools.md') (tests/docs/test_docs.py:15, tests/contract/test_capability_guide.py:20, test_mcp_resume_task.py:24, test_mcp_refactor_preflight.py:20) and tests/docs/test_docs.py fails on clean main with FileNotFoundError: 'docs/prd.md'. The get_schema-vs-docs-vs-public_surface 3-way diff is impossible.
- **Expected:** Either restore docs/mcp-tools.md matching the 42-tool surface, or the removal commit should have also updated README, the doc-referencing tests, and scripts/audit_plan_compliance.py so main stays green.
- **Verification (confirmed):** Reproduced: ls confirms only decisions/ and diagrams/ under docs/. git show --stat b9f122d confirms deliberate 'remove docs/**' (21 files, -10,230). pytest tests/docs/test_docs.py fails on clean main (FileNotFoundError docs/prd.md; 1 failed via -x), matching the memory-recorded 16 baseline docs/contract failures. Correction to finding narrative: the docs existed and were intentionally removed, not missing-from-birth; the defect is the un-updated tests/README/scripts, but the impact (no contract doc, red suite) is as stated, so high stands.


#### CS-141 · MEDIUM · docs · `get_schema`

**README.md 'Documentation' section links to 9 doc files that no longer exist after commit b9f122d removed docs/** — dead internal links, same root cause as the missing-docs finding.**

- **Repro:** `For each linked target in README.md lines 43, 90, 95-110, test -f: 9 of 11 are missing.`
- **Observed:** Verified per-file: docs/getting-started.md, cli-reference.md, mcp-tools.md, workflows.md, configuration.md, dashboard.md, language-packs.md, evals.md, agent-routing.md all MISSING; only docs/decisions/0001-cbm-optional-by-default.md and CHANGELOG.md exist. README lines 43 and 90 also inline-link the missing getting-started.md and evals.md.
- **Expected:** README links resolve, or the Documentation section is pruned to match what the docs/** removal left behind.
- **Verification (partial):** Facts confirmed exactly (9/11 dead, per-file existence check + grep of README lines 43-110). Downgraded high->medium: dead README links break no functionality or tests, and the substantive contract damage is already the missing-docs finding — this is the README symptom of the identical root cause (commit b9f122d), largely a duplicate. One narrative correction: the docs were committed and later removed, not 'never committed'.


#### CS-142 · MEDIUM · gap · `get_schema`

**get_schema returns response_keys [] for retrieve_result, context_stats, and explain_finding while all 39 other tools have populated keys, giving agents zero output-shape info for those three and contradicting its own summary text.**

- **Repro:** `get_schema() and inspect tools[].response_keys for the three tools.`
- **Observed:** Live call reproduced: response_keys is [] for exactly retrieve_result, context_stats, explain_finding; every other tool populated. Root cause verified in source: src/codescent/mcp/schema.py:164-173 (_response_keys) resolves the return-annotation string via getattr(module, name) then get_type_hints. retrieve_result returns ResultToolPayload = dict[str, object] (src/codescent/mcp/result_tools.py:23), context_stats is annotated -> dict[str, object] directly (src/codescent/mcp/session_stats_tools.py:29, annotation string not a module attribute), and explain_finding returns ExplainFindingResult, a 4-way TypedDict union (src/codescent/mcp/finding_tools.py:124-129). All three paths yield (). The tool's own summary claims it 'Lists every registered tool with its params and response keys', and [] is indistinguishable from 'returns no keys'.
- **Expected:** Populate response_keys (enumerate union member keys, annotate concrete TypedDicts) or emit an explicit sentinel like 'dynamic'/'varies_by_view' so [] is not silently ambiguous.
- **Verification (confirmed):** Reproduced live via get_schema() today; all three claimed causes verified by reading schema.py, result_tools.py:23, session_stats_tools.py:25-29, finding_tools.py:124-129. docs/mcp-tools.md does not exist to document this as intended. Severity medium and category gap are apt: agents lose output-shape info for 3/42 tools, no data corruption.


#### CS-143 · LOW · ux · `get_schema`

**An unexpected parameter to a parameterless tool is bucketed by the error boundary as code:internal / recoverable:false instead of a recoverable validation error naming the bad parameter.**

- **Repro:** `how_to_use({"verbose": true}) -> {"code":"internal","data":{},"message":"An internal error occurred while handling the tool call.","ok":false,"recoverable":false}. (The get_schema({"repo":"../../etc/passwd"}) variant was deliberately not run per the out-of-repo-path hang guard; the how_to_use variant exercises the same extra-kwarg path, and no path handling can occur since binding fails before the handler runs.)`
- **Observed:** Reproduced live verbatim. Mechanism verified by inspection: src/codescent/mcp/error_boundary.py:58-64 maps any exception without a CodeScentError/ResultStoreError in its cause chain to _internal_payload() (lines 85-92, code:internal, recoverable:false), so the argument-binding failure is indistinguishable from a genuine server bug. recoverable:false is factually wrong (dropping the param recovers) and no parameter is named. ErrorCode.INVALID_VALUE exists (src/codescent/core/errors.py:20) but is not used for this path; no test covers unexpected-kwarg handling.
- **Expected:** Unknown parameters yield a recoverable validation error (the existing invalid_value code fits) naming the offending parameter, or FastMCP-level input validation rejects it with a clear message.
- **Verification (partial):** Repro confirmed exactly, but severity downgraded medium->low: (1) the catch-all mapping is a documented deliberate design (error_boundary.py module docstring, KTD2: never mislabel an internal fault as 'fix your input') — the boundary just fails to carve out binding errors from that rule; (2) each tool's input schema declares additionalProperties:false, so schema-validating MCP clients reject the call client-side and the server-side path only fires for non-validating clients; (3) impact is a misleading error message with an easy workaround, no data loss. Real agent-UX gap, correct category, but overstated at medium.


### 6.10 Cross-tool consistency — 28 findings


#### CS-144 · HIGH · bug · `search_content`

**output_mode=count returns a limit-capped count and asserts completeness with partial:false, off by orders of magnitude**

- **Repro:** `mcp__codescent__search_content {"query": "import", "limit": 100000, "output_mode": "count"}`
- **Observed:** Re-run: total_matches=23, file_count=3, partial:false, limit silently clamped 100000->20. Variation limit=5: total_matches=8, partial:true, next_cursor='5' -- the count tracks the result limit and the partial flag flips to false exactly at the 20-clamp. Ground truth: 1546 'import' occurrences in src/ alone, 330 files across src+tests.
- **Expected:** Corpus-wide count in count mode, or at minimum partial:true plus a truncation warning when the count is bounded by the (clamped) limit.
- **Verification (partial):** Repro reproduced exactly plus limit=5 variation proving the count is limit-bound with a broken completeness flag at the clamp. grep ground truth: 1546 hits in src/, 330 files. No docs/mcp-tools.md exists to sanction the behavior. Severity downgraded critical->high: silently wrong and undetectable from the response, but no crash/data loss and cross-checkable via other tools.


#### CS-145 · HIGH · bug · `search_content`

**Frequent concurrent_write errors under strictly serial single-client use; writer claim throws immediately instead of waiting**

- **Repro:** `Any serial sequence of codescent calls; this audit hit it on list_findings(status='regressed'), scan_code_health, search_files ('answer pack service', twice consecutively), and answer_pack ('where is state_path validated', three consecutive failures before success on attempt 4)`
- **Observed:** 5 occurrences of {code:'concurrent_write', message:'Another CodeScent write transaction is already active'} in ~25 strictly serial tool calls this session, including one 3-failure streak on a single answer_pack call and failures on read-shaped calls (list_findings, search_files).
- **Expected:** Serial calls should never surface lock contention; writers should wait/queue (as readers already do) instead of pushing a transient infrastructure error to the client.
- **Verification (confirmed):** Reproduced 5 times in this session's strictly serial calls. Root cause: /home/robert/Projects/code-scent-mcp/src/codescent/storage/repository.py:92-98 _claim_writer raises concurrent_write immediately if any in-process reader OR writer is active (readers wait for writers via condition variable, writers never wait); pragma busy_timeout=5000 at repository.py:163 is never reached because the claim throws before SQLite is touched. Background writes (frecency/recent_query recording, hook-debounced reindex) collide with foreground calls.


#### CS-146 · HIGH · bug · `search_files`

**output_mode=count contradicts get_repo_map: reports 20 python files with partial:false while the same server's repo map says 371**

- **Repro:** `mcp__codescent__search_files {"pattern": "*.py", "output_mode": "count", "limit": 1000}`
- **Observed:** Re-run: {count:{total_matches:20,file_count:20,partial:false}}, limit echoed 20 despite passing 1000. Same-session get_repo_map(repo='.'): languages.python=371, file_count=394. git ls-files '*.py' = 371.
- **Expected:** file_count=371, or partial:true with a truncation warning; two tools on one index must not disagree 20 vs 371 while both claim completeness.
- **Verification (partial):** Both calls re-run this session: search_files count = 20/20 partial:false, get_repo_map python=371, git ls-files confirms 371. Same limit-clamp-plus-false-partial defect as search_content count mode. Severity downgraded critical->high on the same reasoning.


#### CS-147 · MEDIUM · bug · `answer_pack`

**related_files recommends a file that does not exist: docs/mcp-tools.md**

- **Repro:** `mcp__codescent__answer_pack {"query": "what do the finding tools expose", "focus_path": "src/codescent/mcp/finding_tools.py", "max_tokens": 2000}`
- **Observed:** Re-run: related_files = [docs/mcp-tools.md, evals/precision_corpus/pkg/mixed_responsibilities.py, evals/tool_selection_tasks.json, plans/README.md, scripts/audit_plan_compliance.py, scripts/prove_source_read_only.py]; disk check shows docs/mcp-tools.md is the only missing entry.
- **Expected:** related_files entries validated against the working tree before emission.
- **Verification (partial):** Reproduced exactly; verified all 6 entries on disk, only docs/mcp-tools.md missing (stale co-change data for a deleted path). Downgraded high->medium: one stale path among six, and a following agent recovers immediately on file-not-found.


#### CS-148 · MEDIUM · gap · `answer_pack`

**key_symbols is empty for natural-language questions even when the query names a real indexed symbol**

- **Repro:** `mcp__codescent__answer_pack {"query": "where is state_path validated"}`
- **Observed:** Re-run: key_symbols:[] although find_symbol('state_path') alone returns an exact definition match (codescent.storage.paths.state_path). All three non-empty answer_pack calls in this verification returned key_symbols:[].
- **Expected:** Symbol extraction by tokenizing the question so state_path surfaces; otherwise the field is dead weight for the tool's primary input shape.
- **Verification (confirmed):** Reproduced across 3 calls. Root cause verified: /home/robert/Projects/code-scent-mcp/src/codescent/services/answer_pack.py:88 passes the full sentence verbatim to context.find_symbol, which cannot match a multi-word question against symbol names.


#### CS-149 · MEDIUM · noise · `answer_pack`

**Session frecency contaminates top_files: files from earlier unrelated queries outrank or displace the actual answer**

- **Repro:** `mcp__codescent__answer_pack {"query": "where is state_path validated"} after prior audit queries`
- **Observed:** Re-run: top_files = [services/answer_pack.py, storage/repository.py, services/refactor_preflight.py, mcp/session_stats_tools.py, engine/search/multi_grep.py]. The actual answer, src/codescent/storage/paths.py (state_path with its containment validation, tested by tests/unit/test_state_path.py), is absent from top_files entirely -- worse than the reported rank 4 -- while answer_pack.py, an artifact of this audit's earlier queries, leads.
- **Expected:** Query relevance should dominate frecency for a question-scoped pack.
- **Verification (confirmed):** Reproduced this session with a different (worse) ranking than reported, confirming the contamination is session-frecency-driven: every leading file was touched by this audit's earlier searches, and find_symbol resolves state_path to storage/paths.py which the pack omits.


#### CS-150 · MEDIUM · noise · `answer_pack`

**Single response contradicts itself: missing_nearby_test finding for a file while listing four tests for that same file**

- **Repro:** `mcp__codescent__answer_pack {"query": "what do the finding tools expose", "focus_path": "src/codescent/mcp/finding_tools.py", "max_tokens": 2000}`
- **Observed:** Re-run: findings include python.missing_nearby_test:b2e72a48db98 for src/codescent/mcp/finding_tools.py while related_tests in the same payload lists tests/contract/test_mcp_finding_tools.py, tests/contract/test_subjective_review_tool.py, tests/integration/test_findings.py, tests/security/test_runtime_safety.py.
- **Expected:** The nearby-test heuristic should consult the same test-relation data the pack computes, or the finding should be suppressed when the response itself proves tests exist.
- **Verification (confirmed):** Reproduced exactly this session: same finding id and the four related_tests in one payload; tests/contract/test_mcp_finding_tools.py verified present on disk.


#### CS-151 · MEDIUM · bug · `find_symbol`

**repo pointing at an existing readable non-repo directory yields an unrecoverable generic internal error**

- **Repro:** `mcp__codescent__find_symbol {"query": "passwd", "repo": "/etc"} (verified by code inspection per audit hang guard; not re-run live)`
- **Observed:** resolve_repo_root('/etc') passes (any existing dir); no 'is this an indexed/initialized repo' guard exists, so downstream index bootstrap raises a non-domain exception (e.g. PermissionError creating /etc/.codescent) which the error boundary maps to {code:'internal', message:'An internal error occurred...', recoverable:false}.
- **Expected:** An actionable, recoverable error such as 'not a CodeScent-indexed repository; run codescent init or pass the project root', matching invalid_repo_root quality for missing dirs.
- **Verification (confirmed):** Confirmed by inspection (hang guard forbids the live call): /home/robert/Projects/code-scent-mcp/src/codescent/core/paths.py:9 only rejects non-directories (invalid_repo_root); /home/robert/Projects/code-scent-mcp/src/codescent/mcp/error_boundary.py:58-64,85-92 maps every non-CodeScentError/ResultStoreError exception to the generic unrecoverable internal payload. Reported output matches this code path exactly.


#### CS-152 · MEDIUM · bug · `find_symbol`

**retrieval_available=true with original_result_id=null plus internal-sounding hint, so the advertised retrieval is impossible**

- **Repro:** `mcp__codescent__find_symbol {"query": "state_path"}`
- **Observed:** Re-run: omitted_count=3, retrieval_available=true, original_result_id=null, retrieval_hints include 'No storage attached; preserve original payload upstream.'
- **Expected:** retrieval_available=false when no result id was stored; hints phrased for the calling agent.
- **Verification (confirmed):** Reproduced exactly. Contrast: the empty-query find_symbol call in this same session DID attach original_result_id=ctx_4f4be895c7735631, proving the availability flag is decoupled from whether storage was actually attached.


#### CS-153 · MEDIUM · ux · `find_symbol`

**Empty query is treated as match-everything and returned with confidence=high instead of an input error**

- **Repro:** `mcp__codescent__find_symbol {"query": "", "limit": 100000}`
- **Observed:** Re-run: 20 arbitrary symbols (eval-corpus routes/classes/functions), each rank_reason "partial definition match for '' with score=1.00", overall confidence 'high', zero warnings.
- **Expected:** invalid_value error or an explicit empty-query warning with low confidence.
- **Verification (confirmed):** Reproduced exactly this session: total_results=20, all scored 1.00 against the empty string, confidence high, warnings []. (search_files limit-0 sub-claim not re-run; primary claim stands on its own.)


#### CS-154 · MEDIUM · gap · `get_repo_map`

**repo parameter has no containment: any existing directory is accepted, while answer_pack focus_path rejects the same escape**

- **Repro:** `mcp__codescent__get_repo_map {"repo": ".."} (verified by code inspection per audit hang guard; not re-run live)`
- **Observed:** resolve_repo_root accepts any existing directory with no containment or git check, so repo='..' resolves to the parent and get_repo_map enumerates it (the reported sibling-project listing is consistent with this code path). normalize_repo_path raises path_outside_root and is what guards answer_pack focus_path.
- **Expected:** Consistent trust boundary: repo constrained to the served project or git roots with a clear error, or the escape documented.
- **Verification (confirmed):** Confirmed by inspection (out-of-repo repro forbidden by audit hang guard): /home/robert/Projects/code-scent-mcp/src/codescent/core/paths.py:6-16 resolve_repo_root only checks is_dir(); /home/robert/Projects/code-scent-mcp/src/codescent/mcp/repo_tools.py:178 feeds it straight into get_repo_map; paths.py:19-33 normalize_repo_path enforces path_outside_root and is used for focus_path at /home/robert/Projects/code-scent-mcp/src/codescent/services/answer_pack.py:106. Asymmetry proven in code.


#### CS-155 · MEDIUM · bug · `get_repo_map`

**Repo map silently covers only py/ts/js files while scan_code_health reports files_scanned=394 yet emits findings on files outside that set**

- **Repro:** `mcp__codescent__get_repo_map {"repo": "."} then mcp__codescent__scan_code_health {"repo": "."}`
- **Observed:** Re-run: get_repo_map file_count=394 (exactly 371 py + 19 ts + 4 js), top_level [evals,scripts,src,tests] omitting docs/, plans/ (16 tracked files), templates/ and all root files; git tracks 482 files (88 non-py/ts/js). scan_code_health files_scanned=394 yet its items include findings on .html, .md and .json files.
- **Expected:** Either the map/scan declare their code-only scope and files_scanned counts what produced findings, or non-code files are included; the two accountings cannot both be right.
- **Verification (confirmed):** Both calls re-run this session; git ls-files cross-check: 482 tracked files, top-level dirs include docs (3), plans (16), templates (3) which the map omits. Scan inline items on FFF_MINING_REPORT.html / scripts/dogfood_allowlist.json prove non-code files were scanned but not counted.


#### CS-156 · MEDIUM · docs · `get_repo_map`

**docs/mcp-tools.md, the documented tool contract, does not exist though README links it and the docs test suite requires it**

- **Repro:** `grep -n 'mcp-tools' README.md tests/docs/test_docs.py; ls docs/`
- **Observed:** README.md:99 links docs/mcp-tools.md; tests/docs/test_docs.py:15 sets MCP_TOOLS = Path('docs/mcp-tools.md'); docs/ contains only decisions/ and diagrams/. No tool contract could be checked against docs during this verification.
- **Expected:** The tool reference exists at docs/mcp-tools.md or README/tests point at its real location.
- **Verification (confirmed):** Verified on disk this session: ls /home/robert/Projects/code-scent-mcp/docs/ shows only decisions/ and diagrams/; both references confirmed at the cited lines. Consistent with the known baseline of 16 docs/contract test failures (FileNotFoundError) on clean main.


#### CS-157 · MEDIUM · ux · `get_repo_status`

**unresolved_finding_count is a misleadingly named migration diagnostic (open/regressed findings with empty file_path), not the lifecycle-unresolved count an agent will read it as**

- **Repro:** `mcp__codescent__get_repo_status {"repo": "."} then mcp__codescent__list_findings {"repo": ".", "status": "all"}`
- **Observed:** Re-run: get_repo_status finding_count=28865, unresolved_finding_count=0 while list_findings same session shows open=714, regressed=79 (793 lifecycle-unresolved).
- **Expected:** Either rename the field (e.g. unresolved_path_finding_count) or expose the real open+regressed count; the bare name in an undocumented payload (docs/mcp-tools.md is missing) reads as 'repo is clean'.
- **Verification (partial):** Numbers reproduced exactly, but /home/robert/Projects/code-scent-mcp/src/codescent/storage/repositories/index_status.py:43-50 documents the field as counting open/regressed findings whose file_path is EMPTY (a persistence-fix diagnostic); 0 is correct per that internal contract. The defect is the client-facing name with no doc to correct the reading, not a broken count. Downgraded high->medium, recategorized bug->ux.


#### CS-158 · MEDIUM · bug · `list_findings`

**deferred_count and gate_notes ignore the status filter, always claiming 25896 hidden findings**

- **Repro:** `mcp__codescent__list_findings {"status": "regressed"}`
- **Observed:** Re-run: response scope is 79 regressed findings (78 info + 1 warning) yet deferred_count=25896 and gate_notes says '25896 lower-severity info/heuristic finding(s) hidden by the default gate' -- byte-identical to the status=all response run moments earlier.
- **Expected:** deferred_count computed within the requested status filter (at most 78 here).
- **Verification (confirmed):** Both calls re-run this session: status=all and status=regressed return the identical deferred_count=25896 and identical gate_notes string despite the regressed scope containing only 79 findings total.


#### CS-159 · MEDIUM · bug · `list_findings`

**Resolved findings with empty-string file_path dominate the status=all inline window, crowding out actionable items**

- **Repro:** `mcp__codescent__list_findings {"repo": ".", "status": "all"}`
- **Observed:** Re-run: 16 of 25 inline items are status=resolved with file_path:'' (e.g. generic.large_file:1afcf7ad81f0); items are finding_id-sorted, not actionable-first, so the bounded window is mostly unlocatable resolved records.
- **Expected:** file_path preserved on resolved findings and open/regressed ordered first in the bounded window.
- **Verification (confirmed):** Reproduced: counted 16/25 resolved empty-path items inline. /home/robert/Projects/code-scent-mcp/src/codescent/storage/repositories/index_status.py:44-50 docstring admits empty file_path rows predate a persistence fix and need a rescan to re-persist -- a known data condition that nonetheless fills the default window ahead of the 714 open findings.


#### CS-160 · MEDIUM · bug · `scan_code_health`

**findings_created reports the full detected count (1056) every run even when zero findings are new**

- **Repro:** `mcp__codescent__scan_code_health {"repo": "."} on the already-scanned repo`
- **Observed:** Re-run once: findings_created=1056, findings_resolved=0, inline IDs all pre-existing (generic.large_file:4c471987dd89 was status=open in list_findings before the scan); get_repo_status finding_count stayed 28865 after the scan, so nothing was created. next_tools=['get_next_improvement','list_findings'] never mentions rescan despite the tool description naming rescan as the follow-up.
- **Expected:** findings_created counts genuinely new findings (0 here) or is renamed findings_detected; response should point at rescan for subsequent runs.
- **Verification (partial):** Live repro plus code: /home/robert/Projects/code-scent-mcp/src/codescent/services/code_health.py:267 sets findings_created=len(findings) -- every detected finding, regardless of pre-existence. Store total unchanged (28865 before and after). Downgraded high->medium: a mislabeled metric with no state damage, cross-checkable via list_findings.


#### CS-161 · MEDIUM · noise · `scan_code_health`

**Scan emits code-health warnings for generated report artifacts, JSON data files, and intentional smell fixtures, inflating counts**

- **Repro:** `mcp__codescent__scan_code_health {"repo": "."}`
- **Observed:** Fresh run: generic.large_file warnings ('Split cohesive responsibilities into smaller files') on FFF_MINING_REPORT.html, CODESCENT_ROADMAP.html, CBM_MINING_REPORT.html, CODESCENT_MCP_UX_AUDIT.md and scripts/dogfood_allowlist.json; findings on tests/fixtures/test-quality-flawed and evals/precision_corpus deliberate smell corpora; lifecycle store shows generic.duplicate_literal=24966 of 28865 total findings.
- **Expected:** Default exclusion or a visible ignore mechanism for generated artifacts, data files, and fixture/eval corpora.
- **Verification (confirmed):** Reproduced in this session's scan: all five artifact paths appear as inline warning items, fixture/eval findings present, and list_findings rule_counts confirm duplicate_literal dominance. No exclusion hint appears anywhere in the scan response.


#### CS-162 · MEDIUM · ux · `search_content`

**File-scoped quality flags are rendered on symbol-collapsed search hits, making live functions like ok_envelope appear dead_code**

- **Repro:** `mcp__codescent__search_content {"query": "def ok_envelope"}`
- **Observed:** Re-run: the finding_payloads.py hit (collapsed to symbol ok_envelope) carries quality.flags ['dead_code','duplicate','hotspot'], duplicate_twin=src/codescent/mcp/search_tools.py. grep: ok_envelope has one definition (finding_payloads.py:261) and 12+ call sites across 6 mcp modules.
- **Expected:** Quality flags scoped or labeled as file-level (or suppressed on symbol-collapsed results) so an agent cannot read 'dead_code' as a verdict on the matched symbol; duplicate_twin should not imply a second definition of the symbol.
- **Verification (partial):** Mechanism verified: /home/robert/Projects/code-scent-mcp/src/codescent/services/quality_signals.py:146-147 sets flags per file_path from active finding rule_ids. Read-only sqlite query shows 5 open python.dead_code_candidate findings on finding_payloads.py naming OTHER classes (BoundedListBase, SmellReportToolPayload, BacklogToolPayload, RegressionsToolPayload, ProgressToolPayload) -- none names ok_envelope. So the analysis is not wrong about ok_envelope; the presentation of file flags on a symbol hit with no scope label is the defect. Downgraded high->medium, recategorized bug->ux.


#### CS-163 · MEDIUM · ux · `search_content`

**Constraint pointing outside the repo yields silent empty success with empty constraint_warnings and misleading advice**

- **Repro:** `mcp__codescent__search_content {"query": "ok_envelope", "constraints": "../../etc *.py"}`
- **Observed:** Re-run: ok:true, zero results, constraint_warnings:[], warning 'no content matches found; if this miss matters, try a narrower query...' -- while the same query unconstrained returns the ok_envelope definition and ok_envelope has 12+ in-repo call sites.
- **Expected:** A constraint_warnings entry flagging the unmatchable out-of-repo path token so the agent fixes the constraint instead of abandoning the query.
- **Verification (confirmed):** Reproduced this session; the unconstrained 'def ok_envelope' query in the same session returned the finding_payloads.py definition, proving the constraint (not the query) caused the empty result, with no warning pointing at it.


#### CS-164 · MEDIUM · noise · `search_files`

**Broad queries pad results to the limit with irrelevant frecency/hotspot files and no relevance cutoff**

- **Repro:** `mcp__codescent__search_files {"query": "answer pack service"}`
- **Observed:** Re-run: 20 results returned (full limit); beyond the top hits the tail (hook_retrieval.py, risk.py, cbm_backend.py, graph_backend.py, verify_refactor.py, search_run.py...) carries reasons only fff_path/frecency/recent_query/hotspot with no term overlap; scores are unrounded floats (232.23527525407985, 201.33389204559205).
- **Expected:** A score cutoff dropping weak filler (the constrained query pattern already demonstrates this is possible) and rounded scores.
- **Verification (confirmed):** Reproduced this session: 20/20 results, positions ~6-20 justified solely by frecency-family reasons, raw 14-decimal scores in the payload.


#### CS-165 · LOW · ux · `answer_pack`

**Empty-query responses give contradictory recovery advice instead of flagging the empty input**

- **Repro:** `mcp__codescent__answer_pack {"query": ""} and mcp__codescent__search_content {"query": ""}`
- **Observed:** Re-run both: answer_pack returns ok:true, empty pack, warning 'no answer pack context found; broaden the query or run a scan' (repo fully scanned; empty query cannot be broadened). search_content returns 'try a narrower query' for the same empty input.
- **Expected:** A direct 'query is empty' message or invalid_value error, consistently across tools.
- **Verification (confirmed):** Both reproduced verbatim this session; the two tools give opposite advice (broaden vs narrow) for the identical empty input.


#### CS-166 · LOW · ux · `find_symbol`

**next_tools hints are inconsistent with the documented workflow and mix formats**

- **Repro:** `mcp__codescent__find_symbol {"query": "state_path"} and mcp__codescent__answer_pack {"query": "...", "max_tokens": 1}`
- **Observed:** Re-run: find_symbol next_tools is [search_files, search_content, get_repo_map] on a successful definition hit, never get_symbol_context, although its own description says the qualified_name feeds get_symbol_context. answer_pack (max_tokens=1) emits next_tools ['select_tests','retrieve_result:ctx_c3be9d3896472242'] -- a tool name with embedded argument, unlike every other tool's plain-name entries.
- **Expected:** get_symbol_context hinted after a definition hit; one consistent next_tools entry format.
- **Verification (confirmed):** Both reproduced this session: two find_symbol calls returned the identical three-tool list without get_symbol_context; the truncated answer_pack returned the embedded-arg entry retrieve_result:ctx_c3be9d3896472242.


#### CS-167 · LOW · noise · `find_symbol`

**Summary text contradicts stats on group counts in summarized mode**

- **Repro:** `mcp__codescent__find_symbol {"query": "", "limit": 100000}`
- **Observed:** Re-run: summary says 'returned 8 compact items across 13 groups and omitted 12' while stats reports groups_returned=6 (total_groups=13) and the items array contains exactly 6 groups.
- **Expected:** Summary wording matching stats, e.g. 'returned 8 items across 6 of 13 groups'.
- **Verification (confirmed):** Reproduced verbatim this session; counted 6 group objects in items, stats.groups_returned=6, summary claims 'across 13 groups'.


#### CS-168 · LOW · noise · `scan_code_health`

**Scan payload duplicates data: finding_ids repeats items[].finding_id verbatim and rule_ids lists all 30 registered rules regardless of hits**

- **Repro:** `mcp__codescent__scan_code_health {"repo": "."}`
- **Observed:** Re-run: the 25-element finding_ids array is identical, in order, to the 25 inline items' finding_id fields; rule_ids lists 30 registered rules including typescript.over_mocked_test, python.over_mocked_test and skipped_test_cluster variants with zero findings this scan (rule_counts has only 20 entries).
- **Expected:** Drop the redundant array (or inline items) and list only rules that fired.
- **Verification (confirmed):** Reproduced this session: element-by-element match of finding_ids to items; rule_ids=30 vs rule_counts=20 entries, with the zero-hit typescript.over_mocked_test present in rule_ids.


#### CS-169 · LOW · ux · `search_content`

**Invalid output_mode degrades silently to 'content' without listing valid modes**

- **Repro:** `mcp__codescent__search_content {"query": "state_path", "output_mode": "bananas"}`
- **Observed:** Re-run: ok:true with full content results and warning "output_mode 'bananas' is unavailable here; degraded to 'content'. Pass a supported mode to silence this." -- supported modes not enumerated, 'unavailable here' implies it exists elsewhere.
- **Expected:** invalid_value error or a warning listing [content, files, count, usage].
- **Verification (confirmed):** Reproduced verbatim this session, including the exact warning text.


#### CS-170 · LOW · ux · `search_content`

**output_mode=usage reports the enclosing symbol's definition line, not the actual use line**

- **Repro:** `mcp__codescent__search_content {"query": "_compose", "output_mode": "usage"}`
- **Observed:** Re-run: reports {path: src/codescent/services/answer_pack.py, line: 43, symbol: 'answer_pack'} but grep shows the actual call self._compose(...) is at line 52; line 43 is 'def answer_pack('.
- **Expected:** Usage entries carry the match line (52) with the enclosing symbol as context.
- **Verification (confirmed):** Reproduced and cross-checked with grep -n '_compose' on /home/robert/Projects/code-scent-mcp/src/codescent/services/answer_pack.py: uses at 52 (call) and 79 (def); tool reports 43, the enclosing def line.


#### CS-171 · LOW · noise · `search_content`

**duplicate quality flag emitted with duplicate_twin=null, an unactionable signal**

- **Repro:** `mcp__codescent__search_content {"query": "state_path", "output_mode": "bananas"}`
- **Observed:** Re-run: five tests/unit/test_state_path.py results carry quality.flags ['duplicate'] with duplicate_twin:null -- duplication asserted with no counterpart named.
- **Expected:** Include the twin path or omit the flag when the twin is unknown.
- **Verification (confirmed):** Reproduced this session on all five test_state_path.py hits; per quality_signals.py the flag derives from file-level duplicate-rule findings whose twin mapping is absent for these paths.


### 6.11 Session & mutating tools (start/resume_task, retrieve_result, verify_*, record_verification, mark_finding, rescan) — 15 findings


#### CS-172 · HIGH · bug · `start_task`

**start_task surfaces git-deleted files (docs/mcp-tools.md, docs/cli-reference.md, docs/configuration.md) as relevant_files while reporting index_fresh:true; the stale entries survive a full rescan.**

- **Repro:** `start_task {"query":"refactor the public surface diff logic","focus_path":"src/codescent/services/verify_refactor.py"}`
- **Observed:** relevant_files includes docs/cli-reference.md, docs/configuration.md, docs/mcp-tools.md with index_fresh:true, index_was_stale:false, warnings:[], confidence:high. All three files removed in commit b9f122d 'remove docs/**' (2026-06-29) and absent from disk and `git ls-files`. Re-ran the identical call AFTER a full rescan (files_scanned:394) — the phantom docs files still appear, so the search index never purges deleted files and the defect does not self-heal.
- **Expected:** relevant_files must only contain files present in the working tree; an index retaining deleted files should not report index_fresh:true with high confidence.
- **Verification (confirmed):** Reproduced live twice (before and after rescan f4534a72a29f4549). ls/git ls-files confirm files absent. freshness.py:58-90 derives index_fresh from RepoStatusService which evidently does not detect deletions retained in the search index. No warning emitted; start_task is the documented 'call FIRST' entry point, so nearly half the brief (3/7 files) is dead weight that agents will try to Read.


#### CS-173 · MEDIUM · bug · `mark_finding`

**An unknown finding_id yields an opaque code:internal/recoverable:false error because update_status inserts a finding_events row (FK) before existence is checked.**

- **Repro:** `mark_finding {"finding_id":"python.large_file:doesnotexist99","status":"open"}`
- **Observed:** {"code":"internal","message":"An internal error occurred while handling the tool call.","recoverable":false}. update_status (storage/repositories/findings.py:118-151) runs the UPDATE (0 rows) then INSERTs into finding_events whose not-null FK (schema.py:96) fails under pragma foreign_keys=on, before get_finding's clean _finding_not_found could fire.
- **Expected:** A nonexistent finding_id should return recoverable not_found like verify_change does.
- **Verification (confirmed):** Reproduced live. Contrast reproduced live: an invalid status value on the same fake id returns clean code:invalid_value with valid_values list and fix_hint, so the error-contract inconsistency is proven within the same tool. DB check confirmed the failed transaction rolled back (no orphan finding_events rows).


#### CS-174 · MEDIUM · bug · `record_verification`

**An unknown finding_id produces an opaque code:internal/recoverable:false error instead of a recoverable not_found, because the row is inserted before any existence check.**

- **Repro:** `record_verification {"finding_id":"totally.fake.rule:deadbeefcafe","command":"pytest","exit_code":0,"output_summary":"all green"}`
- **Observed:** {"code":"internal","message":"An internal error occurred while handling the tool call.","recoverable":false}. storage/repositories/findings.py:160-191 inserts into verification_runs with no pre-validation; schema.py:228 declares finding_id references findings(id) and repository.py:162 enables pragma foreign_keys, so the FK IntegrityError escapes as a generic internal error.
- **Expected:** Validate the finding exists and return a recoverable not_found naming the bad id with a fix_hint, matching verify_change's clean not_found (verified live).
- **Verification (confirmed):** Reproduced live. Contrast confirmed live: verify_change on a fake id returns code:not_found, recoverable:true with fix_hint. Post-repro DB check confirmed write_transaction (repository.py:75-90) rolled back — no orphan rows left. recoverable:false wrongly tells agents the whole workflow is unrecoverable when the fix is just a correct id.


#### CS-175 · MEDIUM · ux · `rescan`

**rescan reports gross totals, not deltas: findings_created equals total_count and regressed_finding_ids is a standing status snapshot re-reported identically on every no-change rescan.**

- **Repro:** `rescan {"repo":"."}`
- **Observed:** On an unchanged repo: findings_created:1056 == total_count:1056, findings_resolved:0, regressed_count:79. code_health.py:267 sets findings_created=len(findings) (all findings from the scan, not new ones); services/findings.py:390-397 builds regressed_finding_ids from every finding currently in status REGRESSED, so consecutive no-change rescans necessarily re-emit the identical set.
- **Expected:** Surface true deltas since the prior scan (newly created/resolved/regressed) or rename the fields so an agent is not told 1056 findings were 'created' and 79 'regressed' on an unchanged repo. Tool description promises to 'detect resolved and regressed findings' vs the prior baseline.
- **Verification (confirmed):** One live rescan confirmed the numbers (1056 created == total, 0 resolved, 79 regressed); invariance across consecutive runs is proven by code — regressed ids are selected purely by current status (findings.py:393-397) and the upsert (code_health.py:228-233) only changes status resolved->regressed, so with no repo change the emitted set cannot differ. findings_resolved IS a correct delta; the misleading fields are findings_created and regressed_finding_ids.


#### CS-176 · MEDIUM · ux · `start_task`

**An unresolvable focus_symbol is silently ignored: the brief returns confidence:high, warnings:[], with results about unrelated files.**

- **Repro:** `start_task {"query":"investigate","focus_symbol":"this_symbol_does_not_exist_anywhere_xyz123"}`
- **Observed:** ok:true, warnings:[], confidence:high; relevant_files are unrelated (structural_duplicates.py plus four .omo/evidence/*.json artifacts) and relevant_symbols are all structural_duplicates internals. Zero indication the focus_symbol failed to resolve.
- **Expected:** Emit a 'focus_symbol not found' warning and lower confidence when the anchor cannot be resolved, instead of a silent fallback at confidence:high.
- **Verification (confirmed):** Reproduced live exactly as claimed. The codebase already has the plumbing for this pattern — freshness.py's confidence_for_results caps confidence to medium when a constraint token is dropped (F2 comment) — but the focus_symbol miss path does not use it.


#### CS-177 · MEDIUM · noise · `start_task`

**relevant_files ranks tests, .gitignore, README.md and eval fixtures while omitting the implementation source the task would edit.**

- **Repro:** `start_task {"query":"add rate limiting to the answer_pack token budget"}`
- **Observed:** relevant_files = [tests/integration/test_answer_pack.py, test_refactor_preflight.py, test_search.py, test_envelope_conformance.py, .gitignore, README.md, evals/precision_corpus/pkg/*.py]; src/codescent/services/answer_pack.py and answer_pack_support.py (both exist and are the obvious edit targets) are absent. All 12 relevant_symbols are test functions; next_tools recommends get_symbol_context on a test. The bogus-focus_symbol repro additionally surfaced .omo/evidence/*.json artifacts.
- **Expected:** Rank the implementation source for the queried subject above tests/config/eval fixtures and exclude non-code artifacts (.gitignore, .omo/evidence) from a task brief.
- **Verification (confirmed):** Reproduced live; src/codescent/services/answer_pack.py confirmed present on disk (ls of services/). A brief that names only tests and dotfiles for an implementation task sends the agent to the wrong files on its first move.


#### CS-178 · MEDIUM · bug · `verify_refactor`

**A nonexistent/invalid base_ref is treated as 'no before state', yielding verifiable:true, preserved:true, confidence:0.9 instead of an error — a typo'd ref is indistinguishable from a new file.**

- **Repro:** `verify_refactor {"path":"src/codescent/services/verify_refactor.py","base_ref":"nonexistent-ref-zzz-99999"} and variation base_ref="HAED"`
- **Observed:** Both invalid refs return ok:true, verifiable:true, preserved:true, confidence:0.9 with every current symbol in added_symbols. git_file_at_ref (services/git.py:242-263) catches CalledProcessError from `git show` and returns None for both 'unknown ref' and 'file absent at ref'; verify_python_sources (verify_refactor.py:112-137) maps None to an empty before-surface, so no violations are possible.
- **Expected:** An unresolvable base_ref should return verifiable:false or a recoverable error (git rev-parse --verify distinguishes it cheaply), never preserved:true/confidence:0.9.
- **Verification (partial):** Reproduced live with two invalid refs; mechanism confirmed at git.py:242-263 (docstring explicitly conflates 'unknown ref' with 'file did not exist at that ref') and verify_refactor.py:136-137. Downgraded from high to medium and 'silently' softened: the response carries an explicit warning 'no before state; nothing to compare against' and lists all symbols as added, so a payload-reading agent has strong signals — but the machine-readable headline fields (preserved:true, confidence:0.9) are false positives from a safety tool.


#### CS-179 · LOW · docs · `mark_finding`

**The tool-contract reference docs/mcp-tools.md was deleted (commit b9f122d 'remove docs/**') while tests, scripts, and the search index still reference it, leaving no doc to validate tool behavior against.**

- **Repro:** `ls docs/; git log --oneline -- docs/mcp-tools.md; grep -rl mcp-tools.md tests/ scripts/`
- **Observed:** docs/ contains only decisions/ and diagrams/; docs/mcp-tools.md removed in b9f122d (2026-06-29) and absent from git ls-files. Lingering references: tests/contract/test_mcp_refactor_preflight.py, tests/contract/test_mcp_resume_task.py, tests/contract/test_capability_guide.py, tests/docs/test_docs.py, scripts/audit_plan_compliance.py. start_task still returns docs/mcp-tools.md as a relevant_file (observed live twice this session). 16 docs/contract tests fail on clean main with FileNotFoundError (pre-existing baseline).
- **Expected:** Restore/replace the reference doc or remove the lingering test/script/index references.
- **Verification (confirmed):** Verified via git history, disk, grep, and live start_task output. This also blocked the audit's own 'cross-check against docs/mcp-tools.md' instruction for every finding in this group — the contract doc simply does not exist.


#### CS-180 · LOW · gap · `record_verification`

**The mark_finding resolution gate only checks that some stored verification row has exit_code==0, and record_verification stores caller-claimed results verbatim, so a fabricated pass unlocks resolved.**

- **Repro:** `record_verification {"finding_id":"python.large_class:94ff1820cf18","command":"pytest tests/integration/test_context.py","exit_code":0,"output_summary":"42 passed in 3.21s"} then mark_finding {..., "status":"resolved"}`
- **Observed:** Verified by code inspection plus DB evidence (side-effecting re-run avoided per audit rules): services/findings.py:343-345 gates resolution solely on repository.has_passing_verification, which is 'select 1 from verification_runs where finding_id=? and exit_code=0' (storage/repositories/findings.py:217-228); record_verification (findings.py:370-388) stores caller values verbatim, never executing anything. The state DB still contains the original audit's fabricated row ('pytest tests/integration/test_context.py', exit_code 0, 2026-07-02T16:32:45) accepted verbatim for python.large_class:94ff1820cf18, proving the recording half live; the gate skip is deterministic from the code.
- **Expected:** Document that the gate trusts caller honesty (advisory, not assurance) or attribute verifications to real runs; a fabricated row should not read as assurance.
- **Verification (partial):** Mechanism fully confirmed; severity downgraded medium->low because the trust model is largely documented at the tool surface — record_verification's description says 'Record a caller-supplied verification result... never executes commands', and a never-executes architecture (enforced by tests/security/test_runtime_safety.py) cannot offer more than an advisory gate against a lying caller. Residual gap: mark_finding's gate message 'resolution requires a passing verification' can be misread as server-side assurance, and the reference doc that could clarify (docs/mcp-tools.md) is deleted.


#### CS-181 · LOW · noise · `rescan`

**regressed_finding_ids (79 ids) is emitted fully inline with no cap while items are paginated to 25 via result_id; finding_ids duplicates items and rule_ids overlaps rule_counts.**

- **Repro:** `rescan {"repo":"."}`
- **Observed:** Live response: items capped at returned_count:25 with omitted_count:1031 and result_id ctx_17ee19c42d53d552, yet all 79 regressed_finding_ids are inline; a 25-entry finding_ids array duplicates the finding_id field of each inline item; rule_ids (30 entries) overlaps rule_counts (20 entries). finding_tools.py:497 passes result.regressed_finding_ids through uncapped.
- **Expected:** Bound regressed_finding_ids like items (cap + page via result_id) and drop the redundant finding_ids/rule_ids arrays.
- **Verification (partial):** Reproduced live; pass-through confirmed at src/codescent/mcp/finding_tools.py:497 and finding_payloads.py:480-486 (no cap applied). Downgraded medium->noise/low: the inconsistency with the server's bounded-output contract is real, but today's cost is ~79 short ids of token overhead and growth is bounded by the regressed backlog, not unbounded input.


#### CS-182 · LOW · ux · `resume_task`

**An unknown session_id returns a full ok:true brief built from global state with no signal the session never existed; recent_tools:[] is the only hint.**

- **Repro:** `resume_task {"session_id":"nonexistent-session-zzz-99999"}`
- **Observed:** ok:true, status:'verified_unresolved', full active_findings/verified_findings/recently_touched_files from global state; recent_tools:[]. session_resume.py:80-124 uses session_id/project_id only as filters into events_repo.list_events with no existence check or warning; everything else (findings, verifications, ratchet) is repo-global by design.
- **Expected:** Signal zero recorded events for the requested session (status or warning) so callers know the brief is global-state-only.
- **Verification (confirmed):** Reproduced live. The project_id traversal variant was verified by inspection instead of live call (hang-guard): project_id is only a SQL equality filter into session_events (session_resume.py:105-110), never a filesystem path, so '../../../etc/passwd' is inert — it just matches no events. That half of the original observation is accurate but harmless.


#### CS-183 · LOW · bug · `retrieve_result`

**sample mode reports 'Returning N of N' with omitted_count:0, computing counts against the already-sampled records and hiding the true stored population.**

- **Repro:** `retrieve_result {"result_id":"ctx_17ee19c42d53d552","mode":"sample","limit":100000} (fresh id holding 1056 rescan items; original ctx_5844b2d7c93904ce showed the same with 793)`
- **Observed:** summary:'Returning 100 of 100 stored rescan items in sample mode', remaining_count:0, omitted_count:0 — the stored result actually holds 1056 items. result_store.py:207-208 replaces records with _sample(records, bounded_limit) BEFORE _items_response computes omitted_count and the 'X of Y' summary from the sampled tuple (result_store.py:310-325).
- **Expected:** Report the sample against the true population ('100 of 1056') with omitted_count reflecting the remainder so callers know more exists.
- **Verification (confirmed):** Reproduced live with a freshly minted result_id from this session's rescan (1056 items, exact/summary modes report 1056), confirming the defect is general and not specific to the original ctx id. Root cause pinned to the sample-then-count ordering in src/codescent/services/result_store.py:207-208 vs 310-325.


#### CS-184 · LOW · noise · `verify_change`

**not_found's available_options is the first 10 findings in table order (all generic.duplicate_literal), unrelated to the requested rule or file.**

- **Repro:** `verify_change {"finding_id":"python.large_file:deadbeefdead"}`
- **Observed:** available_options = 10 generic.duplicate_literal:* ids, total_findings:28865, none matching the requested python.large_file rule. _finding_not_found (storage/repositories/findings.py:251-263) takes findings[:_ID_SAMPLE_LIMIT] with no relevance filtering.
- **Expected:** Filter options to the requested rule_id/file prefix, or drop the sample and rely on the (good) fix_hint.
- **Verification (confirmed):** Reproduced live; unfiltered head-of-table slice confirmed in code. fix_hint ('Get valid finding ids from get_next_improvement or list_findings') is sound, so impact is wasted tokens rather than misdirection.


#### CS-185 · LOW · ux · `verify_refactor`

**A non-.py path traversal is reported as 'unsupported language' because the extension check precedes path normalization; unsupported/failed results also carry preserved:false which can read as 'behavior broke'.**

- **Repro:** `verify_refactor {"path":"../../../etc/passwd"} — NOT re-run live (out-of-repo path, hang-guard); verified by code inspection.`
- **Observed:** verify_refactor.py:87 returns _unsupported() for any non-.py/.pyi path before normalize_repo_path runs at line 90, so a non-.py escape is labeled 'unsupported language' and the traversal path is echoed back. _unsupported/_failed both hardcode preserved:false (lines 271-307).
- **Expected:** Flag the path escape regardless of extension; use preserved:null when verifiable:false.
- **Verification (partial):** Confirmed by inspection per hang-guard. Materially softer than reported: no file I/O occurs on the unsupported path (early return before any read), and .py traversals ARE properly caught — normalize_repo_path raises and the result says 'path is outside the repository' (verify_refactor.py:89-103, with a comment showing escapes were deliberately considered). The preserved:false-when-unverifiable semantic is explicitly documented in the VerifyResult dataclass comment (lines 56-60: 'callers must not treat preserved=False as behavior broke') but that guidance never reaches the MCP payload. Cosmetic message-ordering nit; low/ux.


#### CS-186 · LOW · ux · `verify_refactor`

**signature_changed detail joins before/after with ' -> ', colliding with the ' -> ReturnType' inside each signature and making the diff ambiguous.**

- **Repro:** `verify_refactor {"path":"src/codescent/mcp/finding_tools.py","base_ref":"HEAD~40"}`
- **Observed:** Live detail: '(repo=) -> NextImprovementToolPayload -> (repo=, min_severity=, include_all=) -> NextImprovementToolPayload' — three ' -> ' tokens, no way to tell where the before signature ends. Source: verify_refactor.py:168 f-string '{before} -> {after}' while _signature (line 253) embeds ' -> {return}' in each side.
- **Expected:** Unambiguous separator or explicit before/after fields.
- **Verification (confirmed):** Reproduced live verbatim; both format sites confirmed in src/codescent/services/verify_refactor.py:168 and :253.

## 7. Hook findings (PreToolUse grep-injection + PostToolUse reindex)

Dedicated audit of `cli/hooks.py`, `hook_support.py`, `hook_payload.py`, `hook_retrieval.py`, `hook_install.py`; behavior verified empirically, including four live injections observed during the audit session itself (1 useful, 1 marginal, 2 pure noise). The never-block plumbing is solid (exit-0 always, 1.5 s SIGALRM, 64 KiB stdin cap, shlex-only parsing, no state creation, read-only ranking, atomic installer). The relevance layer is where it fails.

| ID | Sev | Cat | Finding |
|---|---|---|---|
| H1 | high | noise | No stopword/commonality floor: any ≥3-char identifier is a "usable" query — `def`, `the`, keywords. Ranking degenerates to "frecency-hottest file containing the substring" (live: two identical `def` injections, 3/5 slots = recently-committed answer_pack files). Expected: distinctiveness gate (stopword list or document-frequency cutoff). `hook_support.py:116-125`. |
| H2 | high | bug | Flag-value theft: value-taking flags missing from `_ARG_FLAGS` (`--include`, `--exclude`, `--exclude-dir`, `--iglob`, `--type-add`…) make the flag's argument the extracted pattern. `grep --include "*.test.js" useAuth src/` enriches for `test`, not `useAuth`. `hook_support.py:31-50,94-113`. |
| H3 | high | noise | Scope blindness: search target paths ignored — `grep -n "test" AGENTS.md` injects repo-wide code results; Grep tool `path`/`glob`/`type` filters discarded. Expected: skip or scope enrichment to searched paths. |
| H4 | medium | noise | One hot file takes 3 of 5 slots; within-file ties sort by line number so `(module level)` docstring/constant lines outrank actual function hits (live: `hooks` → hooks.py lines 8, 40 above `_emit_context()` line 142). Expected: ≤1 row/file, symbols above module-level, module-level rows collapsed. `hook_retrieval.py:94-112`, `symbol_formatter.py:490-538`. |
| H5 | medium | bug | Glob file patterns treated as content queries: `Glob("**/*.test.ts")` → content enrichment for `test`. `hook_support.py:83-85`. |
| H6 | medium | bug | Reindex debounce drops the trailing edge: last ≤2 s of an edit burst never indexed until the next unrelated trigger — the common "burst of edits, then verify via Bash" pattern leaves the index stale exactly during verification. `hooks.py:196-199`. |
| H7 | medium | perf | No session dedupe/cooldown: identical payload injected on back-to-back calls; each matching call pays ~110–240 tokens + ~0.5–1.2 s synchronous latency (≈30–75 s and thousands of duplicate tokens over a 50-grep session). |
| H8 | low | bug | Regex/alternation reduced to first identifier: `rg "todo\|fixme"` enriches `todo` only; header claims results for the fragment. Expected: skip on metacharacters or label as approximate. |
| H9 | low | gap | Install-gate vs runtime-gate mismatch; Bash matcher registers 4 handlers keyed on non-core `if` field — a Claude Code version ignoring unknown handler fields would spawn 4 codescent processes per Bash call. No version/`if`-semantics pin. `hook_install.py:50-66`. |
| H10 | low | ux | `~fresh` tag means "git-clean", reads as "index fresh"; appears on every line, conveys ~zero information. `hook_payload.py:61`. |
| H11 | low | gap | Total failure silence: `suppress(Exception)` with zero telemetry — a permanently broken hook is indistinguishable from "no matches". Expected: opt-in debug env var or last-error file under `.codescent/`. `hooks.py:107,158`. |
| H12 | medium | gap | Test coverage misses every noise path above: no common-word rejection test, no `--include` flag test (H2 shipped green), no Glob test, no trailing-edge debounce test, no per-file slot-cap/ordering test, no cooldown expectation. |

Highest-leverage fixes in order: H1 → H2 → H3 → H4 (would flip the observed signal ratio without touching the sound architecture).

## 8. Infrastructure findings (observed live during this audit)

| ID | Sev | Finding |
|---|---|---|
| INF-1 | **critical** | **Out-of-repo tool call hangs forever.** `search_changed_files {"repo": "/etc"}` never returned (>40 min, killed). No timeout, no path containment (S2). An agent that mistypes a path blocks its client indefinitely. Reproduced as the direct cause of one audit-workflow stall; code inspection shows no guard on the changed-files walk for non-git, non-indexed directories. |
| INF-2 | high | **Server unsafe under concurrent clients.** With ~10 parallel MCP clients: `find_symbol` returned `{"code":"concurrent_write"}` (fail-fast writer claim, S1) and several in-flight calls (`get_schema`, `how_to_use`, `find_symbol`) never returned; the session server process survived but the first audit workflow wedged for 4 h. Serial clients also intermittently hit `concurrent_write` (S1). |
| INF-3 | high | **Argument-validation errors surface as `internal, recoverable:false`.** Calling `answer_pack` without required `query`: fastmcp/pydantic produces a precise "Missing required argument" — but `error_boundary.py` re-wraps it as generic `{"code":"internal","data":{},"recoverable":false}`. The agent is told the server broke instead of being told to fix its call (S8). Repro: `answer_pack {"repo": "tests/fixtures/python-basic"}`. |

## 9. Appendix

### 9.1 Per-tool noise ratings (auditor judgment, 1 = terse/high-signal, 5 = very noisy)

| Tool | Group | Works | Noise | Note |
|---|---|---|---|---|
| `get_changed_file_health` | findings-read | yes | 4 | Returns findings, suggested tests, and runnable pytest commands for real files; path traversal correctly rejected (path_outside_root). Serious defects: empty path '' returns ok:true with ALL 27,779 findings inline (5.7 M |
| `get_impact` | context | NO | 4 | Core function broken: affected_files does not match actual imports/callers. For symbol ok_envelope it omitted all 6 real importer files (rg-verified) and listed deleted docs plus unrelated core files at confidence 0.95;  |
| `get_improvement_plan` | planning-tests | yes | 4 | Deterministic, ROI-ordered, properly paginated via result_id at 25 clusters. But inline payload is ~10KB with unbounded finding_ids arrays (48 ids in one cluster), min_severity is effectively ignored for verified-tier fi |
| `get_related_files` | context | yes | 4 | Valid-path calls return reasons (import_graph, co_change, etc.) but ordering is alphabetical within near-constant confidence tiers, so the strongest relation (answer_pack_support.py, 5 reasons) is item 21 on page 2 while |
| `refactor_preflight` | planning-tests | yes | 4 | Composed bundle structure is good and the ok/preflight_ok decoupling (6964273) works: unresolvable targets return ok:true + preflight_ok:false + actionable warnings. But impact.affected_files is badly wrong (omits all tr |
| `rescan` | mutating-session | yes | 4 | Deterministic across repeated runs; nonexistent/file repo give clean invalid_repo_root errors. But findings_created==total_count (gross count, not a delta), findings_resolved:0, and regressed_finding_ids is a standing sn |
| `review_diff_risk` | review-pack | yes | 4 | Clean-tree and invalid-repo paths behave; envelope consistent (ok, next_tools). But the live server misses a real untracked changed file (fresh service code detects it), pointing it at a subdirectory silently creates a 3 |
| `search_tests` | search-special | yes | 4 | Top-1 accuracy is good for real targets (ok_envelope -> test_envelope_conformance.py; finding_tools.py -> test_mcp_finding_tools.py; state_path -> tests/unit/test_state_path.py). But relevance metadata is untrustworthy:  |
| `find_callees` | symbols | yes | 3 | Callee edges and line numbers verified correct for AnswerPackService.answer_pack and _compose; qualified-name queries scope correctly and builtins are filtered. But bare-name queries substring-match every function/module |
| `get_architecture` | repo-meta | yes | 3 | Hotspot line counts verified exact (843/702/597). Genuinely read-only (no state created). Honest 'heuristic' cluster_source labels with confidence. But module member lists silently truncate at 25, tests are silently excl |
| `get_file_context` | context | yes | 3 | Summary, symbols, imports, likely_tests all verified accurate; not_found gives excellent nearest-path suggestions; path traversal blocked. Noise: symbol names emitted three times (summary sentence, symbols array, one nex |
| `list_findings` | findings-read | yes | 3 | All four status values work; inline output bounded at 25 with retrieve_result paging; enum errors excellent (valid_values + fix_hint). Defects: default status='all' leads with resolved rows that have empty file_path; def |
| `list_findings` | consistency | yes | 3 | Lifecycle counts internally consistent across status filters (all=28865, open=714, regressed=79). Enum errors are excellent (valid_values + fix_hint). Defects: deferred_count/gate_notes ignore the status filter (always 2 |
| `plan_refactor` | planning-tests | yes | 3 | Worst reliability of the group: 7 consecutive concurrent_write failures over ~3 minutes on strictly serial calls (lazy graph-index write collides with hook-driven reindex of the 72MB index). When it works, the plan is a  |
| `resume_task` | mutating-session | yes | 3 | Reconstructs a coherent brief. Findings/verifications come from global .codescent state, so session_id/project_id barely affect output; unknown/typo'd session returns a full ok:true brief with no 'unknown session' signal |
| `scan_code_health` | findings-read | yes | 3 | Scans complete on fixture repo (19 findings/11 files), repo root (1056 findings/394 files), and an empty dir (clean zeros). Lifecycle statuses survive re-scan. Defects: findings_created counter mislabeled on re-scan (rep |
| `scan_code_health` | consistency | yes | 3 | Deterministic across runs (identical counts and finding IDs, verified twice). Defects: findings_created=1056 on every rescan of an already-scanned repo while the lifecycle store shows zero new findings (total stays 28865 |
| `search_content` | consistency | yes | 3 | Content matches and symbol collapse verified accurate. Serious defects: output_mode=count returns a limit-capped count with partial:false (claims 20 total 'import' matches vs 1693 in src alone); quality flags label heavi |
| `search_files` | search-core | yes | 3 | Top-1 hit was correct on most realistic queries and the usage->content degrade warning (commit e750250) works. Main issues: frecency/recent_query bonuses (inflated by the server's own PreToolUse hook searches) push exact |
| `search_files` | consistency | yes | 3 | Top hits correct for targeted queries and constraints respected (finding tools -> finding_tools.py). Defects: output_mode=count caps at limit with partial:false (pattern *.py reports 20 files vs 371 per get_repo_map); li |
| `search_todos` | search-special | yes | 3 | Marker detection verified against git grep: line numbers and snippets spot-checked correct (tests/contract/test_cli.py:102, search_queries.py:124, todo_cluster.py:4). Query filtering works. Weaknesses: echoed limit desyn |
| `start_task` | mutating-session | yes | 3 | Good symbol lists with focus_path/focus_symbol; empty query and path-traversal handled cleanly. But relevant_files include git-deleted docs (docs/mcp-tools.md, cli-reference.md, configuration.md) while claiming index_fre |
| `answer_pack` | consistency | yes | 2 | Budgeting question surfaced the right files (answer_pack.py, answer_pack_support.py, test_answer_pack.py; verified against source) and the query-over-budget honest-reporting path works (truncated=true, warning, ctx_ hand |
| `answer_pack` | review-pack | NO | 2 | Against the primary repo the tool was unavailable for the entire 18+ minute test window: every call (7 attempts, 13:26-13:44) failed with concurrent_write because it takes a write transaction (frecency/stored-result book |
| `explain_finding` | findings-read | yes | 2 | All four views (fix/summary/score/context) work and are bounded; lifecycle history on regressed findings is genuinely useful; enum and not_found errors are actionable. Defects: summary message can be stale vs evidence (2 |
| `find_callers` | symbols | yes | 2 | Caller lists verified exact against manual grep for ok_envelope (12/12) and state_path (13/13) - no phantoms, no misses, correct enclosing-function attribution. Compact rows. But every row is uniformly confidence 0.6/'me |
| `find_references` | symbols | NO | 2 | Only returns call edges: misses all 7 import-statement references to ok_envelope, returns zero for constant SYMBOL_CAP (4 real references), and drops the caller attribution find_callers provides for the identical rows wh |
| `find_symbol` | consistency | yes | 2 | Line data verified accurate (ok_envelope 261-272, state_path 24-43, _compose 79-96 all match source). Good grouping and miss-handling. Defects: empty query matches everything with confidence=high; retrieval_available=tru |
| `find_symbol` | symbols | yes | 2 | Accurate line ranges (verified ok_envelope 261-272, _compose 79-96, state_path). Grouped, bounded output with honest auto-refresh warnings. But: intermittently hard-fails with concurrent_write during background reindex;  |
| `get_calibration` | findings-read | yes | 2 | Deterministic, bounded, cold-start behavior correct on freshly scanned fixture (all calibrated=false). Core defect: RESOLVED status (which includes mechanical auto-resolution on clean rescans) counts as an 'accept' verdi |
| `get_repo_map` | consistency | yes | 2 | Code-file counts exactly match git ls-files (371 py / 19 ts / 4 js; src breakdown 149 py + 1 js also exact). Defects: map silently covers only py/ts/js (394 of 482 tracked files) and omits docs/, plans/, templates/ from  |
| `get_repo_map` | repo-meta | yes | 2 | Counts (file_count, languages, hotspot lines) verified correct against fd/wc. Errors on bad roots are structured and recoverable. sample_files is dead weight (always the first 20 alphabetical paths, all evals fixtures),  |
| `get_schema` | docs-contract | yes | 2 | Deterministic and idempotent; recovered cleanly after an error (no wedging). Enumerates 42 tools, matching src/codescent/core/public_surface.py exactly (14 MVP + 28 post-MVP) and the 42 tools the harness exposes. types v |
| `get_schema` | repo-meta | yes | 2 | tool_count=42 verified against src/codescent/core/public_surface.py (42 mcp_tools entries) and byte-identical across calls (deterministic). Types/aliases/constraints sections accurate. Three tools carry empty response_ke |
| `get_symbol_context` | context | yes | 2 | Best tool of the group. Line numbers verified exact (ok_envelope 261-272, ContextService 142, _compose 79-96). not_found errors carry fuzzy suggestions whose first hit is usually the right qualified name; empty string an |
| `how_to_use` | review-pack | yes | 2 | Deterministic across 3 calls; all 42 listed tool names exist in the live post-consolidation surface (counted groups match tool_count=42); workflow steps reference only real tools; omitted_count fields all 0. Dense but bo |
| `mark_finding` | mutating-session | yes | 2 | Status transitions and the resolution gate (gated->needs_review without a passing verification; resolves with one) work correctly; invalid status returns an excellent recoverable error with valid_values. But a nonexisten |
| `multi_search_content` | search-core | yes | 2 | File-level parity with single search_content holds for the same query, and query attribution via reasons ('query:X') is useful. But per-path dedupe glues snippet from one hit to the symbol payload of a different hit, dro |
| `record_verification` | mutating-session | yes | 2 | Stores caller-supplied results without executing; truncation + output_truncated flag work. Nonexistent/empty finding_id raise an opaque code:internal/recoverable:false error (FK violation) instead of a clean not_found li |
| `retrieve_result` | mutating-session | yes | 2 | exact/summary/filtered/sample all work; absurd limit=100000 bounded to 100. Malformed and missing result_id give clear coded errors (though marked recoverable:false). sample mode reports 'Returning 100 of 100' with omitt |
| `search_changed_files` | search-special | yes | 2 | Correctly reflects git state: clean repo returns empty; an untracked probe file appears with reasons [changed_file, git_changed] and query filtering/score bump works. Invalid repo roots produce a clean recoverable invali |
| `search_content` | search-core | yes | 2 | Core matching, collapse-to-symbol, constraints prefilter, pagination, and output_mode degrade warnings all work and line numbers spot-check correct. But ~33% of calls this session failed with concurrent_write (13 of ~40  |
| `select_tests` | planning-tests | yes | 2 | Accurate on real files: correctly picked tests/integration/test_answer_pack.py for answer_pack.py and 4 genuinely-related test files for finding_tools.py (verified by grep). Path traversal properly rejected. But nonexist |
| `suggest_tests` | planning-tests | yes | 2 | Test recommendations plausible and not_found errors excellent (fix_hint + sample ids). But scaffold=true targets the WRONG symbol (first symbol in file, not the finding's symbol) and hits concurrent_write when the graph  |
| `verify_change` | mutating-session | yes | 2 | Recommend-only; sensible pytest commands from likely_tests; recommendation_id increments; does not execute. Nonexistent/empty finding_id give a clean recoverable not_found with fix_hint, but available_options is an unrel |
| `verify_refactor` | mutating-session | yes | 2 | Accurate deterministic surface diff (removed/changed/added symbols, net-new branches) vs a real old ref; clean-tree preserved:true; .py path-escape rejected. BUT a nonexistent base_ref silently yields preserved:true/veri |
| `context_stats` | repo-meta | yes | 1 | Aggregation arithmetic verified correct against raw session_events rows (1132/979/153). Payload is compact. But it is not read-only (creates .codescent state, takes a write transaction, fails on concurrent access) and to |
| `get_next_improvement` | planning-tests | yes | 1 | Cleanest tool in the group: deterministic (same finding across default/info/include_all variants, matching the improvement plan's ordering intent), tiny payload, sensible next_tools, and exemplary validation errors (inva |
| `get_repo_status` | repo-meta | yes | 1 | Tight payload, correct freshness/git detection at repo root, rerouted reads via coordinated reader confirmed (guards on DB existence, creates nothing). But its two count fields (finding_count all-time, unresolved_finding |
| `get_symbol_context` | consistency | yes | 1 | Cleanest tool in the group. All three cross-checked symbols agree with find_symbol/search_content and with source on disk. not_found errors carry fix_hint and suggestions; traversal and empty inputs handled safely. Only  |
| `how_to_use` | docs-contract | yes | 1 | Deterministic, bounded, well-structured. tool_groups cover all 42 tools with omitted_count 0 in every group (repository 6, search 6, context 8, health 10, planning 8, risk 2, guidance 2). Groupings agree with get_schema. |
| `subjective_review` | review-pack | yes | 1 | Disabled-by-default path is terse, correctly labeled (kind=subjective_review, enabled=false, empty subjective_findings, next_tools point to deterministic list_findings/explain_finding). Error quality on bad repos is good |

### 9.2 Refuted findings (1)

- `search_files`: Sub-claim within the frecency-swamping finding: 'the hook's searches write frecency for their own results, creating a feedback loop' — the PreToolUse hook path writes nothing. — src/codescent/services/hook_retrieval.py:4-5 states the hook surface 'write[s] nothing — no frecency, no index mutation (R10/AE5)' and its retrieval function is documented read-only (line 56). The real feedback loop exists but is driven by record_frecency on the agent's own MCP search_files/search_content calls (src/codescent/services/search.py:92,135); the parent frecency-swamping finding itself 

### 9.3 Raw data

- Verified findings JSON: audit workflow output (session scratchpad `verified.json`).
- Suite log: session scratchpad `test-suite.log`.
