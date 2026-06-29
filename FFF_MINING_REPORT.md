# Mining `fff` for CodeScent — fast search, in concert with cbm

**Goal of this report.** Mine [`dmtrKovalenko/fff`](https://github.com/dmtrKovalenko/fff)
(*"Fabulous Fast File Finder"*) for ideas, features, and code CodeScent can borrow to make
LLMs **find code faster**, **spend fewer tokens**, and **keep context tight** — and to show how
fff composes *in concert with* `codebase-memory-mcp` (cbm) and CodeScent's native engine.

Status: **report for review**. Beads after you approve a slice.

---

## 1. What fff is — and why it matters here

fff is not just a Neovim fuzzy-finder (its origin). It deliberately became **"accurate, fast file
search as a library for AI harnesses."** It already powers file search in **opencode** and
**nushell**. Concretely it ships as:

- **`fff-core`** (crate `fff-search`) — the engine: typo-resistant fuzzy **path** search, a
  **grep** content engine, **frecency** ranking, a **background watcher**, a lightweight in-memory
  **content index** (~360 B/file, ~36 MB for 100k files, mmap-backable), git awareness, a
  **constraints DSL**, and SIMD/bigram performance work. Sub-10 ms repeat search.
- **`fff-mcp`** — fff's **own MCP server**: a "drop-in replacement for AI code-assistant search
  tools" (`grep`, `multi_grep`, fuzzy file search), with cursor pagination and an
  agent-instructions prompt.
- **`fff-c`** — a **stable C ABI** (versioned, append-only options struct) → bind from C/Zig/Go/Python.
- **`fff-python`** — published to PyPI: **`pip install fff-search`** (maturin/PyO3 wheel).
- **`fff-nvim`** + `lua/` — the original Neovim picker (optional; same ranking as the SDK/MCP).
- **License: MIT** — clean to vendor, bind, or borrow from.

**Why this matters for CodeScent.** CodeScent's weakest layer is exactly fff's core competency.
CodeScent search today = `rapidfuzz` lexical fuzzy over a JSON store, no identifier tokenization,
no frecency, no content index, no constraints DSL. fff is a drop-in, pip-installable, MIT engine
that solves all of that — and adds ranking signals (frecency, query history, git) CodeScent
doesn't have.

**The key symmetry.** CodeScent already ships `cbm_backend` — an *optional* native backend that
upgrades results when cbm is present and *falls back* to native when it isn't. fff slots into the
**exact same pattern**: an optional **`fff_backend`** that upgrades retrieval when `fff-search` is
importable, falling back to today's `rapidfuzz` path otherwise. Lowest-friction, proven integration.

### The three-layer "concert" model (full detail in §6)

| Layer | Owner | Answers |
|---|---|---|
| **Retrieval** — fuzzy path, grep, frecency, git | **fff** | "Where is this file/string, ranked by what I actually touch — fast." |
| **Structure** — graph, type-accurate calls, clusters | **cbm** | "Who calls what, what's dead, what are the modules." |
| **Brain** — bounding, confidence, freshness, health, orchestration | **CodeScent** | "Compose the above into one bounded, deterministic, LLM-shaped answer." |

CodeScent is the only one of the three that *bounds* output for token discipline. fff and cbm are
fast engines; CodeScent is the context-router that keeps the window tight.

---

## 2. Capability gap — search layer

| Capability | fff | CodeScent today | Gap → opportunity |
|---|---|---|---|
| Fuzzy path search | Typo-resistant (frizbee/SIMD), bigram-prefiltered, sub-10 ms | `rapidfuzz`, no identifier tokenization | **Large.** Core retrieval quality + speed. |
| Ranking signals | **frecency** (freq+recency), **query history**, git status, filename/special-file bonuses, distance penalties | churn×size hotspots; no per-user access frecency / query history | **Large.** Rank by what's actually touched. |
| Content grep | SIMD plain matcher + ripgrep regex engine + **aho-corasick multi-pattern**; content index for repeat search | `search_content` over JSON; no content index | **Large.** Faster, multi-pattern, warm. |
| Token-smart grep output | **`auto_expand_defs`** (line → enclosing def, skip import-only lines), `truncate_line_for_ai`, output modes content/files/count/**usage** | bounded snippets; no def-expansion at grep layer | **Large.** Direct fewer-tokens win. |
| Prefilter DSL | **constraints**: `git:modified`, `*.rs`, `!test/`, `src/`, size, time — inline in the query | many separate params | Medium–large. One compact, agent-friendly param. |
| Freshness | background watcher + live in-memory index | incremental reindex + watch (already has) | Small. Mine the **content** index idea. |
| Pagination | opaque **cursor**, "only use if previous insufficient" | result-handles (`ctx_`) — already has | Small. Adopt the agent-guidance wording. |
| Embeddability | **`pip install fff-search`**, stable C ABI | pure-Python | **Large** (enabler). Makes "embed" nearly free. |
| LLM-defensive API | `pattern` alias, float `maxResults`, accept sloppy input, plain-grep fallback on 0 | careful, but no aho/alias/fallback specifics | Medium. Cheap robustness/ergonomics. |

---

## 3. Ranked roadmap

Impact per goal — ● strong · ◐ moderate · ○ minor. Effort S/M/L/XL.
**Borrow-mode**: **E** embed (`pip install fff-search` / C ABI) · **S** shell-out / run `fff-mcp` ·
**R** reimplement natively in Python · **C** concept/design lesson.

| # | Idea | Faster | Tokens | Tight ctx | Effort | Mode | Notes / tradeoff |
|---|---|:--:|:--:|:--:|:--:|:--:|---|
| 1 | **`fff_backend` — optional fff retrieval engine** (mirror `cbm_backend`) | ● | ● | ◐ | M | E | Upgrades the weakest layer; falls back to `rapidfuzz`. Adds a native wheel (optional). |
| 2 | **Frecency ranking** (freq+recency of access/edit) across search, related-files, start_task | ● | ● | ● | M | R / E | Rank by what's actually touched → fewer wrong hits. Native or via fff's LMDB. |
| 3 | **`auto_expand_defs` for grep/content search** (line → enclosing def, skip import-only) | ● | ● | ● | M | R / E | Collapse-to-symbol at the grep layer. CodeScent's Python AST does this natively. |
| 4 | **Constraints DSL prefilter** (`git:modified`, `*.rs`, `!test/`, `src/`, size, time) | ● | ◐ | ◐ | M | R / E | One compact param replaces many. Reuse `fff-query-parser` (embed) or small native parser. |
| 5 | **Query-history-aware ranking** (learn from prior searches this session/repo) | ◐ | ◐ | ● | M | R | Pairs with frecency; biases results toward the active thread of work. |
| 6 | **`truncate_line_for_ai`** — cap match-line length, keep matched span visible | ○ | ● | ◐ | S | R | Trivial token-saver for minified/long lines. |
| 7 | **Output modes: content / files / count / usage** | ◐ | ● | ● | S | R / C | Let the agent pick payload shape; `files`/`count` are near-free. |
| 8 | **Multi-grep via aho-corasick** (OR of many literals, one pass) | ● | ◐ | ◐ | M | E / R | "Trace these 8 identifiers at once." `pyahocorasick` natively, or free via fff. |
| 9 | **`fuzzy` mode for content search** (plain / regex / **fuzzy**) | ◐ | ◐ | ◐ | S | E / R | "I don't remember the exact string." |
| 10 | **Git status as a first-class search + rank signal** (inline + `git:` filter) | ◐ | ◐ | ● | M | R | Bias toward the diff you're working on. |
| 11 | **Time-budgeted search** (`time_budget_ms`, mark truncation) | ◐ | ◐ | ○ | S | R / C | Bounds latency on huge repos; honest truncation. |
| 12 | **LLM-defensive tool API** (param aliases, float nums, 0-result fallbacks) | ◐ | ◐ | ○ | S | C | Fewer failed tool calls = fewer wasted turns. |
| 13 | **Warm in-memory content index** (~360 B/file, mmap-backable) | ● | ○ | ○ | L | E / R | Sub-10 ms repeat grep. CodeScent has symbol index; add **content**. |
| 14 | **fff behind the grep-injection hook** (cbm-report idea #5) | ● | ● | ◐ | M | E | PreToolUse Grep → fff sub-10 ms frecency-ranked context. Concert play. |
| 15 | **Mixed file+dir search** (dir score = max child frecency) | ◐ | ○ | ◐ | S | R | "Where's the auth stuff" returns ranked dirs for orientation. |
| 16 | **Adopt fff's MCP server patterns** (instructions prompt, idle timeout, update notice) | ○ | ○ | ◐ | S | C | Design polish for CodeScent's MCP surface. |
| 17 | **Stable versioned options-struct pattern** (append-only, `version` field) | ○ | ○ | ○ | S | C | ABI/protocol-stability lesson for `cbm_backend`/`fff_backend`. |
| 18 | **Cursor-discipline guidance** ("only page if previous insufficient") | ○ | ◐ | ◐ | S | C | Already have handles; adopt the token-discipline wording. |
| M1 | **Moonshot: fff as CodeScent's default retrieval substrate** | ● | ● | ◐ | XL | E | Standardize on fff (pure-py fallback) for path+grep+frecency+watcher. Built for exactly this. |
| M2 | **Moonshot: cross-session frecency / query "code memory"** | ● | ◐ | ● | XL | R/E | Persist what's searched/opened/edited → personalized ranking feeding fff + cbm + the hook. |
| M3 | **Moonshot: unified retrieval planner** (route query → fff / cbm / native) | ● | ● | ● | XL | — | One `search` entrypoint that picks the engine. The full concert vision (§6). |
| M4 | **Moonshot: frecency-driven context budgeting** | ◐ | ● | ● | L | R | Use frecency + history to decide what goes in answer-pack / start_task. |

**If we only do five:** 1, 2, 3, 4, 7. #1 unlocks the engine, #2 is the highest-value signal
CodeScent lacks, #3 and #7 are direct token wins, #4 is the agent-ergonomic prefilter. #6 (S-effort)
is a free add.

---

## 4. Detail — the high-value borrows

### 4.1 `fff_backend` — optional fff retrieval engine *(#1 · Embed · M)*
**What.** A backend adapter, symmetric to `cbm_backend`: if `fff-search` is importable (or an `fff`
binary/`fff-mcp` is reachable), route path-search and content-grep through it; otherwise fall back
to today's `rapidfuzz` path. **How.** `pip install fff-search` gives a PyO3 wheel; wrap its
`file_search`/`content_search` behind CodeScent's existing search service interface, preserving
bounding + confidence + freshness on the way out. **Why.** One change upgrades CodeScent's weakest
layer to sub-10 ms, typo-resistant, frecency-ranked retrieval. **Tradeoff.** Adds an optional native
wheel; keep it optional so the pure-Python, offline, uv-only install still works (the `cbm_backend`
precedent proves this is acceptable).

### 4.2 Frecency ranking *(#2 · Reimplement or Embed · M)*
**What.** Rank files/symbols by **frequency × recency** of access and edits — fff's headline signal
("ranks results by how often you actually open them"). **Why.** The right file is usually one you've
touched recently; frecency floats it to the top, cutting wrong-result reads (tokens) and round-trips
(speed). CodeScent has churn×size hotspots but no per-session access/edit frecency or query history.
**How.** Native: a small LMDB/SQLite of (path → access/edit timestamps + counts), decayed; or embed
fff's frecency DB directly. Feed it into search ranking, `get_related_files`, and the `start_task`
brief. **Tradeoff.** Frecency is per-user/per-checkout state — store under `.codescent/`, keep it
out of shared artifacts unless opted in.

### 4.3 `auto_expand_defs` for grep *(#3 · Reimplement · M)*
**What.** When a content match has no explicit context, **expand the matched line to its enclosing
definition**, and **skip import-only lines** once real definitions are shown; truncate long lines.
**Why.** This is the collapse-to-symbol token win — but at the grep layer, where agents spend the
most. fff ships it; CodeScent's Python AST can do it natively (exact for Python, heuristic for TS/Go
via packs). **Tradeoff.** Needs the enclosing-symbol map; CodeScent already builds symbol ranges, so
the lift is wiring, not new parsing.

### 4.4 Constraints DSL prefilter *(#4 · Reimplement or Embed · M)*
**What.** A compact inline prefilter language shared by path + content search:
`git:modified`, `*.rs`, `!test/`, `src/` (path prefix), plus size/time/extension. One param scopes
the search. **Why.** Fewer tool params, fewer tokens, and the agent expresses intent precisely
("search `*.py` under `src/`, modified files only") in one string. **How.** Embed `fff-query-parser`
(MIT) via fff, or a ~100-line native parser. **Tradeoff.** A mini-language to document; mitigate with
a `get_schema`/instructions entry (and fff's MCP instructions prompt is a ready template).

### 4.5 Multi-grep via aho-corasick *(#8 · Embed or `pyahocorasick` · M)*
**What.** Search many literal patterns in a single pass (OR logic), returning files where *any*
match. **Why.** "Find every usage of these 8 symbols" in one call instead of 8 — a big speed + token
win for impact/usage tracing (complements cbm's call graph). **How.** Free via fff's `multi_grep`, or
`pyahocorasick` natively. **Tradeoff.** Literal-only (no regex) — which is the point (and matches how
agents should search: bare identifiers, not syntax).

*(Ideas 5–18 and moonshots M1–M4 are specified in the roadmap table §3 with tradeoffs; each becomes
its own bead when we operationalize.)*

---

## 5. What CodeScent should NOT copy from fff

- **The Neovim picker / Lua UI.** CodeScent is a headless MCP server; the interactive picker is
  off-scope. Mine the *core*, not the UX.
- **Unbounded result payloads.** fff returns large result arrays for a UI to render; CodeScent must
  keep its bounding + result-handles on everything routed through `fff_backend`.
- **Mandatory native dependency.** Keep fff **optional** with a pure-Python fallback — the offline,
  uv-only install is a CodeScent feature, same call made for `cbm_backend`.
- **fff's own MCP server as a replacement.** CodeScent's value is the bounding/health/orchestration
  brain; running `fff-mcp` standalone loses that. Use fff as an *engine under* CodeScent, not beside it.

---

## 6. In concert with cbm — the composition

Three engines, one brain. CodeScent routes each request to the layer that answers it cheapest, then
bounds the result.

**Routing table — query type → engine:**

| The agent wants… | Best engine | CodeScent's job |
|---|---|---|
| "Find files matching `auth`" (fuzzy path) | **fff** | frecency + bound + confidence-label |
| "Where is the string `InProgressQuote`" (grep) | **fff** | `auto_expand_defs`, bound, dedupe |
| "Who calls `charge_card`" (call graph) | **cbm** | bound, risk-label, fall back to native AST |
| "What are the modules / dead code / hotspots" | **cbm** + native | compose into architecture overview |
| "Is this code healthy / smelly" | **native** | the deterministic health lifecycle |
| "Brief me to start this task" | **all three** | answer-pack: fff (relevant files, frecency) + cbm (key symbols, calls) + native (in-scope findings), all bounded |

**Why CodeScent stays the brain.** Both fff and cbm ship their own MCP servers and could be used
directly — but neither bounds output, dedupes across sources, attaches confidence/freshness, or runs
the deterministic health lifecycle. CodeScent is the only layer optimizing for a *tight LLM context
window*. The concert is: **fff finds, cbm relates, CodeScent decides what the model actually sees.**

**The two backends, one pattern.** `cbm_backend` (exists) + `fff_backend` (proposed) are the same
optional-native-with-fallback shape. A future **retrieval planner** (M3) picks per query: fuzzy/grep
→ fff, structural → cbm, health → native — a single `search` entrypoint over three engines.

**Frecency × graph (the compounding idea).** fff's frecency says *which files this developer touches*;
cbm's graph says *which symbols are structurally central*. Multiplying them ranks "what matters to
**this** work on **this** codebase" — a signal neither tool has alone, and exactly what a tight
context window needs (M2/M4).

---

## 7. Recommended next step

Approve a slice and I'll turn it into a granular, self-documenting bead tree (via `br`, with unit +
e2e tests and dependencies, per the idea-wizard method). Suggested cut:

- **Phase 1 — token wins (native, S/M):** #3 `auto_expand_defs`, #7 output modes, #6 line truncation,
  #12 LLM-defensive API. No new deps.
- **Phase 2 — the engine:** #1 `fff_backend` (optional `pip install fff-search`, fallback), #4
  constraints DSL, #8 aho-corasick multi-grep.
- **Phase 3 — the signal:** #2 frecency, #5 query history, #10 git-status ranking.
- **Concert (parallel):** #14 fff behind the grep-injection hook; wire the §6 routing table.
- **Moonshots (separate epic):** M1–M4 (retrieval planner, cross-session code memory, frecency×graph).

Tell me which phases/ideas to bead, whether to prefer **embed (`pip install fff-search`)** vs
**reimplement** as the default borrow-mode, and whether moonshots are in or parked.
