# Mining `codebase-memory-mcp` for CodeScent

**Goal of this report.** Identify ideas, features, and design moves in
[`DeusData/codebase-memory-mcp`](https://github.com/DeusData/codebase-memory-mcp)
(hereafter **cbm**) worth borrowing, adapting, or stealing for **CodeScent**, ranked by
their impact on the three things we care about most:

1. **Find code faster** — fewer round-trips to locate the right symbol/file.
2. **Spend fewer tokens** — return the minimum bytes that answer the question.
3. **Keep context tight & focused** — composed, deduped, bounded payloads.

Status: **report for review**. Beads come after you approve a slice.

---

## 1. The two projects, briefly

**CodeScent** — Python / FastMCP. A *deterministic code-health scanner* fused with an
*LLM context-router*. ~40 MCP tools across context, search, findings, planning, repo,
risk, results, session-stats, subjective. Design DNA: every payload **bounded**,
**confidence-labelled**, **freshness-stamped**; **result-handles** (`ctx_` ids) let an
agent re-slice a stored result without rerunning; **offline by default**, **no autofix**,
privacy-first. Parsing = stdlib `ast` for Python, regex/pattern packs for TS/React and Go.
Store = JSON artifacts in `.codescent/`. Search = `rapidfuzz` (lexical fuzzy).

**cbm** — C++ single static binary. A *knowledge-graph code-memory engine*. Tree-sitter
(158 grammars) + a bundled **Hybrid-LSP** type resolver, an in-memory **SQLite** graph with
**FTS5 BM25** + **bundled semantic embeddings**, **Cypher** queries, **Louvain/Leiden**
community detection, per-node **complexity metrics**, cross-service + cross-repo edges, a 3D
graph UI, and an 11-agent installer. Headline claim: *5 structural queries = ~3,400 tokens
vs ~412,000 file-by-file (99.2% fewer)*.

They are **architecturally opposite**: CodeScent is lean, offline, deterministic, bounded;
cbm is heavy, powerful, graph-native. That contrast is exactly what makes cbm a good mine —
it has solved the retrieval/structural problems CodeScent has so far left lexical.

### The decisive context: the `cbm_backend` seam already exists

CodeScent already ships `src/codescent/services/cbm_backend.py` (closed bead
`cbm-backend-66b`). Its own docstring:

> *cbm is a fast LOCAL structural index. When a cbm process is reachable on this machine,
> this adapter pulls symbols / complexity / call edges / clusters from it; otherwise it falls
> back to the native backend and behaves exactly as CodeScent does today.*
> *Hard constraint: cbm's CALL GRAPH is only trusted for Hybrid-LSP languages…*

So CodeScent can already *consume* cbm's symbols, complexity, call edges, and clusters
internally (gated to Hybrid-LSP langs to avoid cross-language same-name collapse, via
`CODESCENT_CBM_CMD`). **But CodeScent exposes none of that to the agent as a tool** — there
is no `get_architecture`, no cluster/module view, no `query_graph`, no complexity surface,
no semantic search. The richest data the adapter fetches dies as an internal ranking input.

**This reframes the whole exercise into two tracks:**

- **Track A — Borrow-by-integration**: *surface and deepen* what the `cbm_backend` adapter
  can already fetch. Low cost (plumbing exists). Cost/tradeoff: only helps users who have cbm
  installed; adds a soft external dependency; must preserve the Hybrid-LSP gating.
- **Track B — Borrow-by-reimplementation**: rebuild the *idea* natively so it works with
  **zero external deps**, preserving CodeScent's offline/plug-and-play/deterministic posture.
  Higher cost, but it's the default experience for every user.

The best moves below are usually **both**: ship a native baseline (Track B) and let the
adapter upgrade it when cbm is present (Track A).

---

## 2. Already built — do NOT re-propose

CodeScent's backlog is **193 beads, all closed**. The following cbm-adjacent capabilities
already exist and are explicitly *out of scope* for new ideas (noted so we don't duplicate):

- Optional cbm structural backend + path containment + availability cache.
- `detect_changes`-equivalents: `review_diff_risk`, `get_impact`, `get_changed_file_health`,
  `refactor_preflight` (blast-radius bundle).
- Dead-code / unused-export, import-cycle (SCC) detection, structural near-duplicate (AI-slop),
  architecture-boundary enforcement, hotspot ranking (churn × size), bus-factor/knowledge-silo.
- Git logical **co-change coupling** (plan 006) in related-files & impact.
- `start_task` (one-shot brief / context router), `resume_task` (post-compaction recovery).
- Coverage ingestion → test-gap findings; `select_tests` (minimal verification set);
  health ratchet (CI debt budget); verification ledger (evidence-gated resolution).
- Per-repo severity **calibration** + learned suppression; finding confidence/provenance;
  edit-stable finding identity; inline suppression comments.
- Incremental dirty-file reindex + debounced watch; content-hash scan cache + parallel scan.
- SARIF / GitHub PR annotation output; precision harness + CI gate; dogfood gate.
- `how_to_use` self-describing capability guide; subjective review via client MCP sampling.

---

## 3. Capability gap at a glance

| Capability | cbm | CodeScent today | Gap → opportunity |
|---|---|---|---|
| Full-text search quality | FTS5 **BM25** + `cbm_camel_split` (camel/snake aware) | `rapidfuzz` lexical fuzzy, **no** identifier tokenization | **Large.** Retrieval quality + token waste. |
| Symbol/code store | In-mem SQLite graph | JSON files in `.codescent/` | Medium. Limits ranked search & queryability. |
| Grep ergonomics | `search_code`: collapse hits → enclosing symbol, rank by importance, **signatures-only** mode | `search_content`: bounded snippets, no collapse-to-symbol | **Large.** Direct fewer-tokens win. |
| One-call architecture | `get_architecture`: langs, packages, entry pts, routes, hotspots, boundaries, layers, **clusters** | `get_repo_map` (paths/counts only) | **Large.** Orientation in 1 call. |
| De-facto modules | Louvain/Leiden community detection | none exposed (adapter fetches clusters, unused) | Medium–large. |
| Arbitrary structural Q&A | `query_graph` (openCypher read subset) | none | **Large** for power use. |
| Self-description | `get_graph_schema` ("run first") | `how_to_use` (prose) | Small–medium; cheap orientation win. |
| Per-symbol complexity | cyclomatic, cognitive, loop_depth, **transitive_loop_depth**, **linear_scan_in_loop**, alloc/recursion-in-loop, param_count | health rules exist; **no per-symbol queryable metric / hot-path** | Medium; cheap via `ast`. |
| Semantic search | bundled Nomic embeddings, vocab-bridging, 11-signal scoring | none | Medium (tradeoff: model/offline). |
| Call-graph precision | Hybrid-LSP ~95% (11 langs) | `ast` (Py) + patterns (TS/Go); confidence-labelled | Moonshot (or lean on cbm adapter). |
| Data-flow / cross-service trace | `trace_path` data_flow + cross_service + risk_labels | callers/callees only | Medium–moonshot. |
| Cross-repo intelligence | `CROSS_*` edges, multi-repo store, 3D galaxy | single-repo | Moonshot. |
| Agent-surface reach | PreToolUse Grep/Glob **context-injection** hook; 11-agent install; full CLI parity + `--raw` | MCP tools; partial CLI | **Large** adoption/token lever (the hook). |
| Shareable index | `.codebase-memory/graph.db.zst` (zstd, two-tier, bootstrap, merge=ours) | local `.codescent/` only | Medium. |
| Prove the value | token-efficiency benchmark (99.2%) | `context_stats` telemetry; precision evals | Medium; closes the loop + guards regressions. |

---

## 4. Ranked roadmap (the headline)

Impact legend per goal — ● strong, ◐ moderate, ○ minor. Effort S/M/L/XL.
Track: **Int** = borrow-by-integration, **Nat** = native reimplementation, **New** = net-new,
**Moon** = moonshot.

| # | Idea | Faster | Fewer tokens | Tighter ctx | Effort | Track | Notes / tradeoff |
|---|---|:--:|:--:|:--:|:--:|:--:|---|
| 1 | **Identifier-aware BM25 retrieval core** (camel/snake tokenizer + BM25 over a real index) | ● | ● | ◐ | L | Nat | Keystone. Unlocks 2,4,9. Adds SQLite/FTS5 or pure-py BM25. |
| 2 | **Collapse-to-symbol grep + signatures-only mode** (`search_code`-style) | ● | ● | ● | M | Nat | Biggest token win for the smallest lift. Reuses `ast` + `ranking.py`. |
| 3 | **Answer-pack + universal `budget`/`max_tokens` param** | ● | ● | ● | M | New | Generalizes `start_task` + result-handles to any query. One call, bounded. |
| 4 | **`get_architecture` one-call overview + module/community view** | ● | ◐ | ● | M | Int+Nat | Surfaces clusters the adapter already fetches; native Louvain fallback. |
| 5 | **PreToolUse Grep/Glob context-injection hook** | ● | ● | ◐ | M | New | Meets agents where they are; token win with zero behavior change. |
| 6 | **`get_schema` machine-readable self-description ("run first")** | ◐ | ◐ | ● | S | New | Cheap; orients agent, prevents flailing. |
| 7 | **`query_graph` bounded passthrough (cbm) + native mini-query** | ● | ● | ◐ | M | Int | Arbitrary structural Q&A in 1 call when cbm present; small native DSL otherwise. |
| 8 | **Per-symbol complexity + hot-path finder** | ◐ | ◐ | ◐ | M | Int+Nat | `linear_scan_in_loop`/`transitive_loop_depth` are cheap, high-signal. New perf-scent rule. |
| 9 | **Token-efficiency benchmark harness** (CodeScent vs naive grep/read) | ○ | ● | ◐ | M | New | Proves the thesis; CI-guards token bloat. Extends `evals/`. |
| 10 | **Embeddings-free semantic expansion** (identifier co-occurrence map) | ◐ | ◐ | ◐ | M | New | Offline vocab-bridge ("send"↔"publish") without a model. |
| 11 | **Precise `get_code_snippet` by qualified name ±neighbors** | ● | ● | ● | S | Nat | Minimal-token symbol fetch; pairs with `find_symbol`. |
| 12 | **Optional semantic search via cbm's bundled embeddings** | ◐ | ◐ | ◐ | M | Int | Opt-in; avoids shipping a model in CodeScent. Needs cbm. |
| 13 | **Cross-service route↔handler linking** | ◐ | ◐ | ◐ | L | New | Client→server jump in 1 hop for web apps. |
| 14 | **ADR / decision memory** (`manage_adr`-style in `.codescent/`) | ○ | ◐ | ● | M | New | Stops agents re-litigating; cross-session context. |
| 15 | **Team-shared compressed index artifact** (`.codescent/index.db.zst`) | ● | ○ | ○ | M | Nat | Teammate bootstraps without rescan; merge=ours. |
| 16 | **"Anti-context" / do-not-read hints** (generated/vendored/low-signal) | ◐ | ● | ● | S | New | Cheap negative signal; prevents wasted reads. |
| 17 | **Full CLI parity + `--raw` JSON for every tool** | ◐ | ○ | ○ | M | Int | Non-MCP agents, scripts, evals share one surface. |
| 18 | **Adaptive result sizing from `context_stats` feedback** | ○ | ● | ● | M | New | Closes the loop: auto-tune default payload sizes per session. |
| M1 | **Moonshot: Hybrid-LSP-lite for TS/Go precision** (or lean on cbm) | ● | ◐ | ◐ | XL | Moon | Raises confidence of *everything*. Adapter already gates to LSP langs. |
| M2 | **Moonshot: cross-repo / multi-repo intelligence** | ● | ◐ | ◐ | XL | Moon | "Who calls this API" across services. Big lift; single-repo today. |
| M3 | **Moonshot: data-flow / taint-lite trace mode** | ◐ | ◐ | ◐ | XL | Moon | "Where does this value come from/go." Hard for dynamic langs natively. |
| M4 | **Moonshot: 3D/loopback graph visualization** | ○ | ○ | ○ | L | Moon | Human-facing; off-thesis for token goals but great for adoption/demos. |

**If we only do five:** 1, 2, 3, 4, 5. They attack all three goals directly, reuse existing
CodeScent machinery, and (except #1's store work) are M-effort. #6 and #11 are S-effort
"while we're here" wins worth folding in.

---

## 5. Detail — the high-value borrows

### 5.1 Identifier-aware BM25 retrieval core *(#1, Track Nat, L)*
**What.** Replace pure `rapidfuzz` ranking with a tokenizer that splits `getUserProfile` /
`get_user_profile` into `get user profile`, then rank with BM25 over a persisted index.
**Why it serves the goals.** Lexical fuzzy match misses the obvious (`UserAuth` vs query
`auth user`) and over-returns near-noise — both *slow discovery* and *waste tokens* on wrong
results. BM25 + identifier splitting is the single biggest retrieval-quality lever, and it's
exactly what cbm uses (`cbm_camel_split`, FTS5).
**How.** Either (a) move `.codescent/` symbol/file data into **SQLite + FTS5** with a custom
tokenizer, or (b) a pure-Python BM25 over the existing JSON inventory (no new native dep).
**Tradeoffs.** (a) is the right long-term store (unlocks #4/#7/#11) but is the larger change;
(b) preserves zero-dep purity and ships faster but doesn't scale as well. Recommend (b) first,
(a) as the follow-on keystone. **cbm ref.** README "Search" + FTS5 tokenizer.

### 5.2 Collapse-to-symbol grep + signatures-only mode *(#2, Track Nat, M)*
**What.** A search mode that takes raw text hits, **deduplicates them into the enclosing
function/class**, returns the **signature + 1 context line**, and ranks definitions >
popular callers > tests. A `mode=compact|full|files` switch like cbm's `search_code`.
**Why.** Today an agent greps, gets N line-hits, then reads each file to find the function —
many tokens, many round-trips. Returning "these 4 symbols, here are their signatures" answers
"where is X" in one bounded call. **Highest token-win per unit effort.**
**How.** CodeScent already parses Python to AST and has `engine/search/ranking.py`; add a
"line → enclosing symbol" map and a signature renderer. TS/Go via existing packs (lower
fidelity, label confidence).
**Tradeoffs.** Symbol resolution is exact for Python, heuristic for TS/Go — surface the
confidence label that already exists. **cbm ref.** `search_code` compact mode.

### 5.3 Answer-pack + universal token budget *(#3, Track New, M)*
**What.** A single composing tool: given a task/query, return **one** bounded object — top
files, key symbols + signatures, likely tests, in-scope findings, related files — deduped
across sources. Plus a first-class `budget`/`max_tokens` param on the heavy tools that
auto-summarizes/samples to fit and returns a `ctx_` handle to expand.
**Why.** This *is* "tight context": fewer round-trips, predictable payload size. CodeScent
already has the pieces — `start_task` composes a brief, `retrieve_result` samples/summarizes by
handle. Generalize them to ad-hoc queries and make the budget explicit.
**Tradeoffs.** Composition risks over-fetching internally; cap each contributor and short-circuit.
**cbm ref.** the 99.2%-fewer-tokens framing (one composed query beats dozens of reads).

### 5.4 One-call architecture + module view *(#4, Track Int+Nat, M)*
**What.** A `get_architecture` returning languages, packages, entry points, layers,
architecture boundaries (CodeScent already computes these in rules), hotspots (already has
churn×size), and **de-facto modules** via community detection over the import/call graph.
**Why.** Orientation today takes many `get_repo_map` + read cycles. One structured overview
collapses that. The adapter **already fetches cbm clusters** — we just don't expose them.
**How.** Track A: pass cbm clusters through when present. Track B: native Louvain/
label-propagation over the import graph CodeScent already builds for import-cycle detection.
**Tradeoffs.** Community detection is approximate; label clusters as heuristic.
**cbm ref.** `get_architecture` + Louvain/Leiden.

### 5.5 PreToolUse Grep/Glob context-injection hook *(#5, Track New, M)*
**What.** Ship a **non-blocking** Claude Code (and Codex/Gemini) hook: when the agent runs
Grep/Glob, intercept the search token, and inject matching CodeScent symbols/findings as
`additionalContext`. Never gate `Read` (preserves read-before-edit). Exit 0 on every path.
**Why.** The agent gets structural context **inside its normal workflow** — no new tool to
learn, no behavior change — and is less likely to spray reads. cbm proves the pattern works
across 11 agents. This is the cheapest path to "find faster" for the average session.
**Tradeoffs.** Hook plumbing is per-agent; start with Claude Code. Must be provably
non-blocking (cbm's `cbm-code-discovery-gate` is exit-0 on every failure path).
**cbm ref.** README "Multi-Agent Support".

### 5.6 `get_schema` self-description *(#6, Track New, S)*
**What.** A machine-readable companion to `how_to_use`: node/finding/edge **types + counts**
for this repo, and the shape each tool returns. "Run this first."
**Why.** Agents waste turns probing what's available. A 1-call schema orients them and keeps
the exploration focused. Tiny effort. **cbm ref.** `get_graph_schema`.

### 5.7 `query_graph` passthrough + native mini-query *(#7, Track Int, M)*
**What.** When cbm is present, expose a **bounded, read-only** Cypher passthrough (wrapped in
CodeScent's bounding + confidence + path-containment). When it isn't, a tiny native query
verb that composes existing callers/callees/references/related filters.
**Why.** One structural question ("functions with zero callers that import X") in one call
instead of a tool chain. **Tradeoffs.** Raw Cypher is power-user surface — keep it bounded,
read-only, and path-contained (CodeScent already validates cbm paths). **cbm ref.**
`query_graph` openCypher subset.

### 5.8 Per-symbol complexity + hot-path finder *(#8, Track Int+Nat, M)*
**What.** Attach cheap complexity signals to symbols (cyclomatic, cognitive, loop depth) and
add a "hot path" finder for the two highest-signal cbm metrics: **`linear_scan_in_loop`**
(hidden O(n²) a loop-depth scan misses) and **`transitive_loop_depth`** (interprocedural
worst-case nesting). Use as both a finding (perf-scent) and a context-ranking signal.
**Why.** "Show me the gnarly/slow functions" becomes one call; ranking can prefer or flag
hotspots. Adapter already pulls complexity from cbm; native `ast` gives loop nesting cheaply.
**Tradeoffs.** Interprocedural metrics need the call graph (accurate for Py, heuristic else).
**cbm ref.** `query_graph` complexity properties.

*(Ideas 9–18 and moonshots M1–M4 are specified in the roadmap table §4 with their tradeoffs;
each becomes its own bead with full detail when we operationalize.)*

---

## 6. What CodeScent should NOT copy from cbm

Keeping these out is as valuable as the borrows — they'd dilute CodeScent's identity:

- **Heavy native binary / 158 tree-sitter grammars / RAM-first C++ pipeline.** CodeScent's
  value is a lean, `uv`-installable Python server. Wholesale tree-sitter adoption is a moonshot
  (M1), not a default.
- **Always-on embeddings.** cbm compiles a model into its binary; CodeScent's "no network,
  no model" default is a feature. Keep semantic search **opt-in** or **via the cbm adapter**.
- **Raw, unbounded tool outputs.** cbm returns large graph payloads; CodeScent's bounding +
  result-handles are its edge. Every borrow must inherit bounding, not bypass it.
- **Autofix / write paths.** Out of scope by design; nothing here changes that.

---

## 7. Recommended next step

Approve a slice and I'll turn it into a granular, self-documenting bead tree (via `br`, with
unit + e2e tests and dependency structure, per the idea-wizard method). Suggested first cut:

- **Phase 1 (token wins, mostly native, M-effort):** #2 collapse-to-symbol grep, #11 precise
  snippet, #6 `get_schema`, #3 answer-pack + budget.
- **Phase 2 (retrieval keystone):** #1 BM25/identifier tokenizer (pure-py first), then the
  SQLite/FTS5 store; #4 architecture+modules.
- **Phase 3 (reach & proof):** #5 grep-injection hook, #9 token-efficiency benchmark.
- **Track A deepening (parallel, cbm-gated):** #7 query passthrough, #8 complexity/hot-path,
  #12 semantic — all surfacing what `cbm_backend` can already fetch.
- **Moonshots (separate epic):** M1–M4.

Tell me which phases/ideas to bead, and whether to keep moonshots in or park them.
