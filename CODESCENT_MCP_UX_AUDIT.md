# CodeScent MCP — Agent-Experience & Architecture Audit

**Report date:** 2026-07-01 · **Version audited:** 0.1.0 (pre-1.0) · **Surface:** 48 MCP tools, 6 prompts, 1 resource
**Method:** static code audit (three parallel investigators) + live first-person dogfooding of the running stdio server
**Yardstick:** CodeScent's own North Star — *get the right code into the model with fewer tokens and tighter focus*, deterministic floor with an opt-in LLM layer. Every finding below is scored against that sentence.

---

## Executive Summary

CodeScent is already a *sophisticated* MCP server, not a naïve one. It ships a self-describing discovery backbone (`how_to_use`, `get_schema`), a `constraints` mini-DSL, frecency-ranked search, token-measured output bounding with `result_id` offload, freshness auto-refresh, and macro-style orientation tools (`start_task`, `answer_pack`, `refactor_preflight`). The deterministic-floor / opt-in-LLM discipline is genuinely well thought out. The foundation is strong enough that the remaining gaps are specific and fixable rather than structural rewrites.

That said, the surface has drifted past the point where an agent can navigate it cleanly, and — more seriously — it speaks **two contradictory dialects**. The *happy path* is excellent: rich, bounded, `next_tools`-chained payloads. The *unhappy path* and the *edges* are where agents fall off:

- **The error path is effectively unusable.** Roughly 30 tools hardcode `"ok": true` on success, while the five most common agent mistakes (unknown `finding_id`, unknown `qualified_name`, bad `path`, invalid `status`, bad `repo`) raise **bare Python exceptions** that escape as out-of-band FastMCP tool errors. Success and failure do not share a shape, so an agent cannot branch on a single field. *(Reproduced live — see F1.)*
- **A malformed filter is silently dropped.** `search_content(query="parse", constraints="size:banana")` returns normal, *unfiltered* results with `warnings: []`. The agent believes it filtered by size and reasons on wrong data. This is the most dangerous finding in the report because it is silent. *(Reproduced live — see F2.)*
- **The guided improvement loop does not close.** Only 12 of 48 tools are ever named as a `next_tools` target; the advertised spine `plan → tests → verify → mark → rescan` is **five consecutive dead ends**. An agent driven by hints can never reach `mark_finding` or `record_verification`. *(Reproduced live — see F6.)*
- **The surface is 48 tools with heavy overlap.** All 48 have **zero docstrings** (the one-line `description=` is the entire contract), 36 of them open with the boilerplate phrase "Use CodeScent…", and the same conceptual input — "a symbol" — is spelled six different ways across the surface (`query`, `pattern`, `qualified_name`, `symbol`, `target`). *(See F4, F5.)*
- **The next-improvement signal is drowned.** The live index reports **25,690 findings across 719 files** (~36 per file). The single most valuable promise — "tell me what to improve next" — is buried under an unfiltered firehose. *(Reproduced live — see F10.)*

None of these require abandoning what works. The highest-leverage fixes are small and structural: one boundary error-decorator, six one-line `next_tools` additions, one `constraint_warnings` field, and deleting the "Use CodeScent…" prefix. The consolidation work (48 → ~31 tools) is bigger but is pure win at pre-1.0, where breaking changes are free.

### The verdict in one line

> A strong, idiomatic core wrapped in a surface that is too large, a doc layer that is too thin, an error contract that barely exists, and a guided loop that stops halfway. All four are cheap to fix relative to the value already built.

### Top 10 fixes, ranked by (impact ÷ effort)

| # | Fix | Severity | Effort | Finding |
|---|---|---|---|---|
| 1 | One boundary error-decorator → uniform `{ok:false, code, message, recoverable, data}` for every tool | High | Low | F1 |
| 2 | Surface dropped `constraints` tokens as `constraint_warnings` (stop silent wrong-scope results) | Critical | Low | F2 |
| 3 | Wire the 6 missing `next_tools` keys so the improvement loop closes end-to-end | High | Low | F6 |
| 4 | Convert the 5 bare-`raise` sites into recovery payloads (valid ids / near-match symbols / valid statuses) — `rapidfuzz` is already a dependency | High | Low | F1 |
| 5 | Delete the "Use CodeScent…" prefix from all 48 descriptions; reclaim the one-line slot for disambiguation | Medium | Low | F5 |
| 6 | Add `finding/{id}`, `backlog`, `repo-map` MCP resources (wrap existing services) | High | Low | F7 |
| 7 | Merge the four confusable finding clusters (48 → ~31 tools) behind `mode=`/`status=`/`view=`/`kind=` params | High | Med | F4 |
| 8 | Settle `confidence` on one meaning; give `retrieve_result`/`context_stats` real typed returns | Medium | Low | F3 |
| 9 | Route every `.codescent` write through one guarded `state_path()` choke point | High | Med | F9 |
| 10 | Fix index hygiene (exclude nested worktrees, `.omo/`, tool state) and cap the finding firehose | High | Med | F10 |

---

## Methodology

This audit combined two independent evidence streams so that no claim rests on reading code alone:

1. **Static investigation** — three parallel agents read the full `src/codescent/` tree with non-overlapping scope: (a) tool surface + documentation, (b) error handling + input forgiveness + output envelope + bounding, (c) architecture + resources + prompts + workflow chaining + safety enforcement. Every finding below carries a `file:line` citation from that pass.
2. **Live dogfooding** — the running stdio server was driven as an agent would drive it, with deliberately valid *and* malformed inputs, to observe the *actual* payloads an agent receives. Quotes marked "reproduced live" are verbatim tool outputs, not inferences.

Findings are scored on two axes: **Severity** (Critical / High / Medium / Low — how badly it degrades agent success) and **Effort** (Low / Med / High — implementation cost). Because the project is pre-1.0 with an empty "Unreleased" changelog, recommendations assume breaking changes are acceptable and pair each with a migration note.

---

## Scorecard

| Dimension | Grade | One-line assessment |
|---|:--:|---|
| Output bounding | **A−** | Token-measured, `result_id` offload, hard caps. The strongest part of the surface. One gap: `answer_pack` without a budget. |
| Discovery backbone (`how_to_use` / `get_schema`) | **B+** | Generated from a single registry, genuinely useful. Under-referenced: no param-hungry tool points *to* it. |
| Orientation macros (`start_task` / `answer_pack` / `refactor_preflight`) | **B** | Real service-computed `next_tools`, dynamic deep-links. The good citizens of the surface. |
| Safety model (design) | **B** | Deterministic floor + opt-in LLM is principled and clearly documented. |
| Search graceful degradation | **B−** | Empty/miss queries return structured envelopes with `next_tools`. Undercut by the silent-constraint hazard (F2). |
| Architecture / layering | **C+** | Mostly clean delegation, but raw SQL and storage orchestration leak into the transport layer. |
| Naming & param consistency | **C−** | Five verbs for overlapping jobs; six param names for "a symbol." |
| Tool clustering | **C−** | 48 tools; the `health` group alone has 15 (agents degrade past ~7). |
| Documentation | **D+** | Zero docstrings; 36/48 boilerplate-fronted; one example on the entire surface. |
| Workflow chaining | **D** | 36/48 tools are never a `next_tools` target; the action spine is five dead ends. |
| Error handling & recovery | **D** | Bare exceptions escape; no `ok:false` shape; no fuzzy/enum/available-options recovery. |
| Discovery surface (resources/prompts) | **D** | One resource total; six prompts that fetch nothing. |
| Input forgiveness | **D−** | Three helpers wide; malformed filters silently dropped — a correctness hazard. |

---

## Findings

Each finding: **Severity · Effort · North-Star impact**, then evidence, then the fix and its migration.

### F1 — The error path is a different, unusable contract

**Severity: High · Effort: Low · North-Star: agents waste turns on unrecoverable failures.**

The success path is excellent and the failure path barely exists. About 30 tools construct payloads that hardcode `"ok": true`; the common agent mistakes raise bare exceptions that no MCP tool catches, so they surface out-of-band as FastMCP tool-error strings. The only `try/except` in the entire `mcp/` layer is at `result_tools.py:68`.

Reproduced live (verbatim outputs an agent receives):

```text
get_file_context(path="does/not/exist.py")
  → Error calling tool 'get_file_context': does/not/exist.py

get_finding(finding_id="bogus-123")
  → Error calling tool 'get_finding': bogus-123

get_symbol_context(qualified_name="no.such.symbol")
  → Error calling tool 'get_symbol_context': no.such.symbol

mark_finding(finding_id="bogus-123", status="banana")
  → Error calling tool 'mark_finding': 'banana' is not a valid FindingStatus
```

Every one echoes the offending value with no `ok`, no machine-readable code, no recovery data — and, for `mark_finding`, without listing the nine valid statuses that sit one line away in the enum. Contrast the search cluster, which *does* degrade gracefully:

```text
search_content(query="")
  → {"ok": true, "results": [], "confidence": "low",
     "warnings": ["no content matches found; if this miss matters, try a
      narrower query, search_files, search_content, or get_repo_map"],
     "next_tools": ["search_files", "get_repo_map"]}
```

The server already knows how to fail well — it just does so in one cluster and throws bare in the others.

Bare-raise sites (all should become structured, recoverable errors):

- `storage/repositories/findings.py:152` — `raise LookupError(finding_id)`
- `services/context.py:104` — `raise LookupError(relative_path)`
- `services/symbols.py:107` — `raise LookupError(qualified_name)`
- `finding_payloads.py:510` — `FindingStatus(status)` → bare `ValueError`
- `core/paths.py:10` — `CodeScentError(INVALID_REPO_ROOT)` (structured, but never caught at the boundary)

Two structured error types already exist and disagree: `CodeScentError.to_payload()` → `{code, message, severity, details}` (`core/errors.py:32`) and `StoredResultErrorPayload.to_payload()` → `{kind, code, message, result_id, retryable}` (`services/result_store.py:77`). Neither carries `ok`; only the second is ever delivered to an agent, by exactly one tool.

**Fix.** Add one boundary wrapper — a decorator applied where each `register_*` calls `mcp.tool(...)`, or a FastMCP middleware — that catches `CodeScentError`, `ResultStoreError`, `LookupError`, and `ValueError` and returns a single uniform shape:

```json
{ "ok": false, "code": "not_found",
  "message": "No finding 'bogus-123'.",
  "recoverable": true,
  "data": { "available_options": ["python.large_file:cf58…", "…"],
            "fix_hint": "Get valid ids from get_next_improvement or list_findings." } }
```

Then convert the five bare-raise sites to populate `data`: unknown finding → a bounded sample of real ids; unknown symbol/path → nearest `find_symbol` matches; invalid status → `[s.value for s in FindingStatus]`. **`rapidfuzz>=3.0` is already a declared dependency** (`pyproject.toml`), so "did you mean" costs no new install. *Migration:* additive — success payloads are unchanged; only the failure shape becomes usable.

### F2 — A malformed `constraints` token is silently dropped (silent wrong results)

**Severity: Critical · Effort: Low · North-Star: the model reasons on data it believes was filtered but wasn't.**

`parse_constraints` never raises: bad size/time tokens parse to `None` and unknown schemes are ignored (`engine/search/constraints.py:15-17, 177-180, 197-227`). The search then runs *as if the token were absent*, with no warning.

Reproduced live:

```text
search_files(query="settings", constraints="size:banana")
  → {"ok": true, "results": [ …normal unfiltered hits… ],
     "confidence": "high", "warnings": []}
```

The agent asked for a size filter, got none, and received `confidence: high` with an empty `warnings` array. Nothing signals that `size:banana` was discarded. An agent that typo'd `size:<10kb` as `size:10kb` (a real, likely mistake) silently searches the whole repo and trusts the result.

**Fix.** Have `parse_constraints` also return the tokens it ignored, and add a `constraint_warnings` field to every search payload:

```json
"constraint_warnings": ["ignored 'size:banana' — expected size:<10kb (operators < <= > >=, units b/kb/mb)"]
```

Optionally lower `confidence` when a constraint was dropped. *Migration:* additive field; no signature change.

### F3 — The response envelope is not uniform; `confidence` means three different things

**Severity: Medium · Effort: Low · North-Star: agents can't write one parser for the surface.**

Four success shapes coexist — bounded-list, freshness/search, detail/scalar, and `retrieve_result` (which omits `ok` entirely) — and success never shares a shape with error (F1). Two "canonical" envelopes disagree: `ResponseEnvelope` (`core/models.py:321`) uses `original_result_id` and has no `ok`, while `finding_payloads.bounded_finding_list` hand-builds `{ok, result_id, next_tools}` with no `mode`/`summary`.

`confidence` is overloaded three ways an agent cannot reconcile:

- an enum `high/medium/low` (`core/models.py:315`, `ResponseEnvelope.confidence`)
- a string label from `confidence_for_results` (`context_tools.py:49`)
- a float 0–1 (`finding_payloads.py:146`, `architecture_tools.py:76`, `Symbol.confidence`)

Separately, `retrieve_result` and `context_stats` return bare `dict[str, object]` (`result_tools.py:22`, `session_stats_tools.py:27`), so `get_schema` derives **empty `response_keys`** for them (`schema.py:160-169`) — the discovery backbone advertises no shape for two tools, and one of them silently omits `ok`.

**Fix.** Adopt one success envelope (`{ok, kind, data|items, warnings, confidence, next_tools, result_id, retrieval_*}`) and one error envelope (F1). Pick a single meaning for `confidence` — recommend the enum — and rename the float to `confidence_value`/`score`. Give `retrieve_result` and `context_stats` real `TypedDict` returns including `ok`. *Migration:* breaking for the two bare-dict tools and any `confidence`-as-float consumer; both are internal-only today.

### F4 — 48 tools with heavy overlap; the same input has six names

**Severity: High · Effort: Med · North-Star: menu size and inconsistency both cost tool-selection accuracy and tokens.**

Agent tool-selection accuracy degrades sharply past ~7 tools per cluster. CodeScent groups are repository 6, search 6, context 8, **health 15**, planning 9, risk 2, guidance 2 (authoritative, from `core/public_surface.py`). Beyond raw count, several clusters are near-synonyms an agent will pick wrong between:

- **`get_smell_report` / `get_backlog` / `get_regressions` / `get_progress`** — one query (`get_smell_report()`) exposed as four tools via status filters; `get_progress` is a strict subset of the aggregates the others already return.
- **`get_finding` / `explain_score` / `explain_finding` / `get_finding_context`** — four "tell me about this finding" tools, all keyed by `finding_id`, *split across two groups* (`health` and `planning`), so an agent browsing `health` cannot even see two of the four.
- **`scan_code_health` / `rescan`** — the same `build_scan_envelope` call; `rescan` only adds `regressed_finding_ids`. Nothing says "first run vs subsequent."
- **`find_symbol` / `find_references` / `find_callers` / `find_callees` / `get_related_files`** — four graph-neighbor lookups, three with byte-identical 12-word descriptions differing by one word.
- **`search_content` / `multi_search_content`** — the latter is the former with a list argument.
- **`verify_change` / `record_verification` / `verify_refactor`** — three "verify" verbs, three meanings, two groups.

And the highest-friction inconsistency: **"a symbol" is spelled six ways** — `query`, `pattern` (both accepted on `find_symbol`), `qualified_name` (`get_symbol_context`), `symbol` (`search_tests`, `retrieve_result`), `target` (`get_impact`, `refactor_preflight`). "Find callers of X" wants `query=X`; "context for X" wants `qualified_name=X`; "tests for X" wants `symbol=X`.

**Fix.** Consolidate to ~31 tools, every group ≤7, capability preserved behind a `mode`/`status`/`view`/`kind` parameter (full mapping in **Appendix B**). The two highest-value, lowest-risk merges:

- `list_findings(status="all"|"open"|"backlog"|"regressed")` replaces the smell/backlog/regressions/progress quartet.
- `explain_finding(view="summary"|"score"|"fix"|"context")` unifies the four-way finding-explanation cluster that currently straddles two groups.

Standardize the locator parameter to **`target`** everywhere and reserve `query` for genuine free-text search. *Migration:* ship one-release forwarding shims that map each old name to the new `mode=`; the empty "Unreleased" changelog is the right moment.

### F5 — Documentation: zero docstrings, boilerplate-fronted, one example on the whole surface

**Severity: Medium · Effort: Low · North-Star: the description *is* the contract; a thin contract costs both accuracy and tokens.**

Every one of the 48 tool functions has an **empty docstring**, so the one-line `description=` is the entire contract — and 36 of 48 spend the highest-signal position on the boilerplate "Use CodeScent to…" / "Use CodeScent before…" rather than on disambiguation. Grades across the surface: **0 A, 7 B-range, 30 C-range, 11 D** (full table in **Appendix A**). The ceiling is universal: descriptions state a *trigger* but almost never provide (a) an example, (b) a "prefer sibling X instead" steer, or (c) discovery of where a required id/name comes from. Only `search_content` carries an inline example; only `answer_pack` tells the agent where its ids come from.

Concretely, an agent calling `mark_finding` is never told the nine valid `status` values inline (must round-trip to `get_schema`); an agent calling `get_symbol_context` is never told that `qualified_name` comes from `find_symbol`; an agent calling `get_impact` is never told the valid `target_type` values.

**Fix (applies regardless of consolidation):**

1. Delete the "Use CodeScent…" prefix everywhere; lead with the differentiator.
2. Add a one-line **discovery** clause to every id/name consumer ("`finding_id` comes from `get_next_improvement` / `list_findings`"; "`qualified_name` comes from `find_symbol`").
3. Enumerate enum params **inline** (`mark_finding.status`, `get_impact.target_type`).
4. Add one concrete example per tool.
5. Add an explicit "prefer sibling" steer to each confusable pair (`start_task` = fresh work; `answer_pack` = token-budgeted pack).

*Migration:* pure text; no signature change. This is the single cheapest quality lift in the report and is measurable against the existing `run_token_efficiency.py` baseline.

### F6 — The guided improvement loop does not close

**Severity: High · Effort: Low · North-Star: the whole "navigate me through an improvement" value prop stalls halfway.**

Across the entire codebase only **12 distinct tools are ever named as a `next_tools` target; 36 of 48 are never pointed to.** Tracing the advertised spine:

| Step | `next_tools` emitted |
|---|---|
| `scan_code_health` | `(get_next_improvement, get_smell_report)` |
| `get_next_improvement` | **none** ✗ |
| `get_smell_report` | `(get_next_improvement, plan_refactor, retrieve_result)` |
| `plan_refactor` | **none** ✗ |
| `suggest_tests` | **none** ✗ |
| `verify_change` | **none** ✗ |
| `mark_finding` | **none** ✗ |
| `record_verification` | **none** ✗ |

Reproduced live — `get_next_improvement` (the hop `scan_code_health` recommends *first*) is an immediate dead end:

```text
get_next_improvement()
  → {"ok": true, "finding_id": "python.large_file:cf58d980c270",
     "rule_id": "python.large_file",
     "file_path": "src/codescent/core/models.py",
     "suggested_action": "Split cohesive responsibilities into smaller modules."}
     ← no next_tools
```

`verify_change`, `mark_finding`, and `record_verification` are **never** a `next_tools` target anywhere, so a hint-driven agent can never reach them and the loop never closes. (The macro tools are the exception and the model to copy: `start_task`, `resume_task`, `refactor_preflight`, and `answer_pack` all emit service-computed `next_tools`, including dynamic deep-links like `get_symbol_context:{symbol}`.)

**Fix.** Six one-line additions restore end-to-end chaining — no mega-macro required:

- `get_next_improvement` → `(get_finding_context, plan_refactor)`
- `plan_refactor` → `(suggest_tests, get_impact)`
- `suggest_tests` → `(verify_change,)`
- `verify_change` → `(record_verification, mark_finding)`
- `mark_finding` → `(rescan, get_next_improvement)`
- `record_verification` → `(mark_finding,)`

A single server-side "run the whole loop" macro is *not* warranted and cannot work: the loop has a mandatory agent-edit step between `plan_refactor` and `verify_change`, and the server never edits source (F9). Add a test asserting the spine tools form a connected chain via `next_tools`. *Migration:* additive.

### F7 — The discovery surface is thin: one resource, six inert prompts

**Severity: High (resources) / Medium (prompts) · Effort: Low · North-Star: every noun that isn't a resource costs a tool round-trip and a remembered tool name.**

**Resources.** `mcp.resource(...)` is registered exactly once — `codescent://guide` (`guide_tools.py:32`). Every browsable entity (a finding, the backlog, the repo map) is reachable only by tool call, so an agent cannot `ReadMcpResource` a finding by address; it must burn a round-trip and know the tool name first. The backing services already exist, so exposing nouns as resources is nearly free:

| URI | Returns | Backing (exists today) |
|---|---|---|
| `codescent://finding/{id}` | one finding + score explanation | `detail_payload` (`finding_payloads.py:475`) |
| `codescent://backlog` | open findings + counts | `FindingsService.get_smell_report` |
| `codescent://repo-map` | inventory, languages, entrypoints | `get_repo_map` (`repo_tools.py:168`) |
| `codescent://architecture` | module/cluster map | `get_architecture` |
| `codescent://improvement-plan` | clustered plan | `ImprovementPlanService` |
| `codescent://progress` | resolved/open/regressed ratchet | `get_progress` |

Templated `finding/{id}` is the highest-value one — it turns "call `get_finding` with the right id" into a browsable address. *Migration:* additive; handlers call the same service methods.

**Prompts.** Six exist (`prompts.py:17-40`), correctly safety-gated and discoverable — but they are inert stubs: each emits a title, safety text, and 2–4 lines naming tools to call, and **fetches nothing** (`prompts.py:113`), even though they accept `finding_id`/`symbol`/`path`. `safe_refactor_finding(repo, finding_id)` could pre-embed the finding context so the first turn is actionable. Prompt bodies also hard-code tool names in free text (`prompts.py:49`) with no binding to the registry, so a rename drifts silently. Missing high-value prompts: `improve_top_finding` (drives the full F6 loop), `resume_session` (wraps `resume_task`), `review_diff` (surfaces the risk tools no prompt currently names).

**Fix.** Add the six resources; enrich prompts to pre-fetch context; add the three missing prompts; add a test asserting every tool named in a prompt body is in `registered_mcp_tool_names()`.

### F8 — Architecture: raw SQL and orchestration leak into the transport layer

**Severity: High (lock bypass) / Medium (leak + dead code) · Effort: Med · North-Star: indirect, but the read/write hole can hand an agent a mid-write snapshot.**

The intended separation (transport → service → engine/storage) mostly holds — `server.py` is pure registration and tool functions are thin delegators — but three leaks matter:

- **Raw `sqlite3` in the transport layer.** `mcp/repo_tools.py` imports `sqlite3` (`:3`), hand-builds the DB path (`:211`), and runs `select` queries directly (`:253`, `:266`), **bypassing `RepositoryStorage` and its reader/writer lock** (`storage/repository.py:64`). These reads are not coordinated with `write_transaction` and can observe a mid-write database. (This is the code path behind the bare-exception `get_repo_status` seen in F1.) *Fix:* route through a repository/service.
- **Storage orchestration in transport.** `mcp/result_tools.py:15` and `mcp/context_tools.py:24` import storage internals and record session events inline; that orchestration belongs in a service.
- **Quadruplicated tool registry + dead code.** `core/public_surface.py` maintains the tool names in four parallel structures (`MVP_MCP_TOOL_NAMES:74`, `POST_MVP_MCP_TOOL_NAMES:94`, `REGISTERED_POST_MVP_MCP_TOOL_NAMES:132`, and the `PUBLIC_SURFACE` tuple `:198`). `POST_MVP == REGISTERED_POST_MVP` exactly, so `locked_mcp_tool_names()` (`:277`) is permanently empty — dead. Collapse to the single `PUBLIC_SURFACE` tuple and derive the sets from it.

*Migration:* all internal; `registered_mcp_tool_names()` (the public accessor) is unchanged.

### F9 — The `.codescent`-only-write guarantee is by convention, not enforced

**Severity: High · Effort: Med · North-Star: a headline safety promise should be a runtime invariant, not a test signal.**

DB writes *are* centralized: `RepositoryStorage.write_transaction()` (`storage/repository.py:74`) is the single write path, guarded by a process-wide lock and `begin immediate`. Filesystem/state writes are **not**. State paths are built ad hoc in at least four places — `repository.py:124`, `services/scan_cache.py:223`, `services/config.py:35`, `cli/hooks.py:198` — each independently hardcoding a `.codescent`-relative path, and **no runtime assertion** checks that a write target is inside `.codescent`. The read-only-on-source property is verified only by an eval (`evals/deterministic.py:121` snapshots source before/after), which is a test signal, not a guarantee.

**Fix.** Add one `state_path(repo_root, *parts) -> Path` in `storage/` that asserts the resolved path `is_relative_to(repo_root/".codescent")` (mirroring the existing containment check at `dashboard/payloads.py:56`), and route every state write through it. Keep the eval as defense-in-depth. *Migration:* internal refactor of writers; no API change.

### F10 — Index hygiene and the 25,690-finding firehose

**Severity: High · Effort: Med · North-Star: directly violates "fewer tokens, tighter focus" — the core promise is buried in noise.**

Reproduced live, `get_repo_status` reports **25,690 findings across 719 indexed files** (~36 per file). The one promise an agent most wants — "what should I improve next" — is drawn from an unfiltered ocean. Calibration and suppression machinery exists (`get_calibration`), but the default surface still overwhelms.

The index is also polluted. Live results for a plain query surfaced the tool's **own nested worktree** and internal state:

```text
search_files(query="settings")
  → .claude/worktrees/prancy-scribbling-emerson/.claude/settings.json
    .claude/worktrees/prancy-scribbling-emerson/src/codescent/services/findings.py   (dup of src/…)
    .claude/settings.json
    .omo/evidence/prd-remainder-plan-compliance.json      (from start_task results)
```

Nested worktrees are being indexed as if they were source, so every file is double-counted and CodeScent even flags its own worktree copies as `duplicate`. That inflates the finding count, pollutes search, and wastes agent attention.

**Fix.** Exclude nested worktrees (`.claude/worktrees`, any linked-worktree path), `.omo/`, and tool-internal state from indexing by default; respect `.gitignore` and a `.codescentignore`. Separately, make the default finding view **severity-gated** (surface non-`info` first) and lead the agent with `get_next_improvement` / `get_improvement_plan` rather than the raw backlog. *Migration:* re-index required; finding counts drop (a feature, not a regression).

### F11 — Minor polish

**Severity: Low · Effort: Low.**

- The empty-query `search_content` warning suggests `search_content` — the tool the agent is already in. Don't recommend the current tool as an alternative.
- `answer_pack` is not token-bounded unless the caller passes a budget (`services/answer_pack.py:54` stores a `result_id` only `if budget is not None`); the configured `TokenBudgets` default (`core/models.py:59`) is not wired in. Default the budget so the pack always self-bounds and always offers a `result_id` when it truncates.
- The `limit` field echoed by search is cosmetically clamped while the service hard-caps separately (`search_tools.py:193` vs `services/search_support.py:27`) — harmless, but two clamps in two places invite drift.

---

## Prioritized Roadmap

Three phases, ordered so the cheap structural wins land first and the consolidation follows once the contract is uniform.

### Phase 1 — Make the contract uniform and the loop close (Low effort, High impact)

1. Boundary error-decorator → one `{ok:false, code, message, recoverable, data}` shape (F1).
2. Convert the five bare-raise sites into recovery payloads using the already-present `rapidfuzz` (F1).
3. `constraint_warnings` for dropped tokens (F2).
4. Wire the six missing `next_tools` keys + a chain-connectivity test (F6).
5. Delete the "Use CodeScent…" prefix; add discovery clauses, inline enums, one example per tool (F5).
6. Default the `answer_pack` budget; fix the self-referential search warning (F11).

### Phase 2 — Consolidate the surface and enrich discovery (Med effort, High impact)

7. Merge to ~31 tools behind `mode`/`status`/`view`/`kind`, with one-release shims (F4, Appendix B).
8. Standardize the locator param to `target`; reserve `query` for free-text (F4).
9. Add the six `codescent://…` resources (F7).
10. Settle `confidence` on the enum; give `retrieve_result`/`context_stats` typed returns with `ok` (F3).
11. Enrich prompts to pre-fetch context; add `improve_top_finding` / `resume_session` / `review_diff`; add the prompt-name registry test (F7).

### Phase 3 — Harden internals and the signal (Med effort, structural)

12. One guarded `state_path()` write choke point (F9).
13. Remove raw `sqlite3` from `mcp/repo_tools.py`; move session-event orchestration into a service (F8).
14. Collapse the quadruplicated registry; delete the dead `locked` machinery (F8).
15. Index hygiene: exclude nested worktrees / `.omo` / tool state; severity-gate the default finding view (F10).
16. Add an **agent-UX eval** to the existing harness: measure tool-selection accuracy and error-recovery success, and track the token cost of the description layer against `token_baselines.json` (leverages `evals/run_token_efficiency.py`, `run_precision.py`).

---

## What CodeScent Already Gets Right

A fair audit names the strengths, because the recommendations above are refinements to a good design, not a rescue:

- **Output bounding is genuinely excellent** — token-measured envelopes, `result_id` offload with `retrieval_hints`, `INLINE_ITEM_LIMIT`, `SOURCE_LINE_CAP`, cursor paging. This is the hardest thing to get right for agent context economy, and it is the strongest part of the surface.
- **The orientation macros are the model to copy** — `start_task`, `resume_task`, `answer_pack`, and `refactor_preflight` return service-computed `next_tools` with dynamic deep-links. The `next_tools` fix in F6 is simply making the rest of the surface behave like these already do.
- **Search degrades gracefully** — empty and miss queries return structured envelopes with actionable `next_tools`, exactly the pattern the error path (F1) should adopt.
- **The discovery backbone is real** — `how_to_use` and `get_schema` are generated from a single registry and are legitimately useful; they just need param-hungry tools to *point at* them.
- **The safety philosophy is principled** — deterministic floor, opt-in and clearly-labeled LLM layer, no network in the fact paths. F9 asks only that the filesystem guarantee be enforced as tightly as the design already promises.
- **The eval harness exists** — precision and token-efficiency baselines are already in `evals/`, which is exactly the infrastructure needed to make the Phase-1 doc and error fixes *measurable* rather than aesthetic.

---

## Appendix A — Per-Tool Doc-Quality Table (48 tools)

`when?` = does the description steer *when to reach for it vs a sibling* (`trig` = only a generic trigger). `disc?` = does it say where a required id/name comes from. `ex?` = concrete example present. Group assignments are authoritative from `core/public_surface.py`.

| tool | group | ≈words | when? | disc? | ex? | grade | biggest gap |
|---|---|--:|:--:|:--:|:--:|:--:|---|
| how_to_use | guidance | 41 | trig | Y | N | B | no worked-workflow example |
| get_schema | guidance | 47 | Y | Y | N | B | nothing points to it from param-hungry tools |
| start_task | repository | 50 | trig | N | N | B− | no "not answer_pack/resume_task" steer |
| resume_task | repository | 50 | Y | N | N | B− | no example of the returned brief |
| subjective_review | health | 52 | Y | N | N | B− | strong text, but misfiled in health |
| verify_refactor | planning | 30 | Y | N | N | B− | no example of a surface violation |
| search_content | search | 55 | trig | partial | Y | B− | only tool with an inline example |
| answer_pack | repository | 70 | trig | Y | N | C+ | overlaps start_task, no cross-steer |
| get_architecture | repository | 59 | Y | N | N | C+ | silent on when *not* to use |
| get_improvement_plan | health | 24 | trig | N | N | C+ | vs get_next_improvement (plan vs single) |
| suggest_tests | planning | 47 | trig | N | N | C+ | vs select_tests / search_tests |
| refactor_preflight | planning | 46 | trig | N | N | C+ | overlaps get_impact + plan_refactor |
| explain_finding | planning | 29 | trig | N | N | C | split from explain_score across groups |
| record_verification | health | 26 | Y | N | N | C | vs verify_change (near-identical intent) |
| plan_refactor | planning | 15 | trig | N | N | C | needs finding_id; no discovery |
| select_tests | planning | 28 | trig | N | N | C | vs suggest_tests / search_tests |
| get_file_context | context | 24 | trig | N | N | C | no "vs get_changed_file_health" |
| find_symbol | context | 24 | trig | N | N | C | dual query='' + pattern=None unexplained |
| get_related_files | context | 16 | N | N | N | C | vs find_references overlap |
| search_files | search | 29 | trig | N | N | C | constraints/pattern undocumented inline |
| search_changed_files | search | 27 | trig | N | N | C | vs review_diff_risk |
| search_todos | search | 18 | trig | N | N | C | thin |
| get_calibration | health | 21 | trig | N | N | C | no "when would I care" |
| get_next_improvement | health | 13 | trig | N | N | C | vs get_improvement_plan / get_backlog |
| scan_code_health | health | 18 | trig | N | N | C− | vs rescan — no disambiguation |
| rescan | health | 13 | N | N | N | C− | vs scan_code_health |
| get_smell_report | health | 15 | N | N | N | C− | vs get_backlog / get_regressions |
| get_finding | health | 15 | N | N | N | C− | needs finding_id; vs explain_* |
| explain_score | health | 19 | trig | N | N | C− | vs explain_finding (other group) |
| get_finding_context | planning | 18 | trig | N | N | C− | fourth "one-finding" tool |
| mark_finding | health | 15 | Y | N | N | C− | status enum not listed inline |
| get_impact | planning | 17 | trig | N | N | C− | target_type values not enumerated |
| get_symbol_context | context | 20 | trig | N | N | C− | needs qualified_name; no discovery |
| retrieve_result | context | 28 | N | partial | N | C− | which tools mint result_id not stated |
| get_repo_map | repository | 24 | trig | N | N | C− | near-clone of get_repo_status |
| get_repo_status | repository | 25 | trig | N | N | C− | near-clone of get_repo_map |
| multi_search_content | search | 24 | N | N | N | C− | = search_content with a list |
| review_diff_risk | risk | 17 | trig | N | N | C | vs get_changed_file_health scope |
| get_changed_file_health | risk | 17 | trig | N | N | C | vs review_diff_risk |
| context_stats | health | 34 | N | N | N | D | misgrouped in health; needs session_id |
| get_backlog | health | 8 | N | N | N | D | 8-word desc; = smell_report filtered |
| get_progress | health | 8 | N | N | N | D | 8-word desc; subset of smell_report |
| get_regressions | health | 9 | N | N | N | D | overlaps rescan's regressed output |
| verify_change | planning | 14 | N | N | N | D | 3-way collision w/ verify siblings |
| search_tests | search | 19 | N | N | N | D | 4 locator params, no guidance |
| find_references | context | 12 | N | N | N | D | 12-word clone shape |
| find_callers | context | 12 | N | N | N | D | 12-word clone shape |
| find_callees | context | 12 | N | N | N | D | 12-word clone shape |

**Distribution:** 0 A · 7 B-range · 30 C-range · 11 D.

---

## Appendix B — Proposed Tool Consolidation (48 → ~31)

Every merge preserves capability behind a parameter and can ship a one-release forwarding shim.

| old tool(s) | new home | action | migration |
|---|---|---|---|
| get_smell_report, get_backlog, get_regressions, get_progress | `list_findings(status=…)` | merge 4→1 | default `status="all"` = old get_smell_report; shims forward |
| scan_code_health, rescan | `scan_code_health(compare=bool)` | merge 2→1 | rescan → `compare=True` |
| get_finding, explain_score, explain_finding, get_finding_context | `explain_finding(view=…)` | merge 4→1 (unifies across groups) | `view` default = current explain_finding |
| find_symbol, find_references, find_callers, find_callees, get_related_files | `code_relations(target, kind=…)` | merge 5→1 | one param `target`; `kind` selects |
| search_files, search_content, multi_search_content | `search(queries=[…], output_mode=…)` | merge 3→1 | single query still allowed |
| suggest_tests, select_tests | `plan_tests(mode=…, scaffold=bool)` | merge 2→1 | preserve `scaffold` |
| verify_change, record_verification | `record_verification` | merge 2→1 | add a commands-only path |
| review_diff_risk, get_changed_file_health | `review_diff_risk(path=None)` | merge 2→1 | `path` set → single-file |
| get_repo_map, get_repo_status | `get_repo(view=…)` | merge 2→1 | shim both |
| context_stats | health → task | regroup | grouping-only |
| subjective_review | health → subjective | regroup | grouping-only |
| start_task, answer_pack | keep (task) | cross-doc only | not a break — steer in descriptions |

**Proposed groups (all ≤7):** orient (4) · task (5) · search (4) · navigate (3) · health (7) · change-safety (7) · subjective (1). **Result: 48 → ~31 tools, 7 groups, none over 7.**

---

## Appendix C — Evidence Index

- **Live dogfooding:** `get_repo_status`, `start_task`, `search_content`, `search_files`, `find_symbol`, `get_file_context`, `get_symbol_context`, `get_finding`, `explain_finding`, `mark_finding`, `get_next_improvement` — driven against the running server with valid and malformed inputs; quotes marked "reproduced live" are verbatim.
- **Static citations** reference `src/codescent/` at commit-time of the audit (branch `main`, worktree `prancy-scribbling-emerson`).
- **North Star** and safety guarantees quoted from `AGENTS.md` ("NAVIGATOR NORTH STAR", anti-drift checklist).
- **Dependency note:** `rapidfuzz>=3.0` is already declared in `pyproject.toml`, so the "did you mean" recovery in F1 requires no new dependency.
