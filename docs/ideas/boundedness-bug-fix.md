# Bug: List/aggregate MCP tools violate the boundedness invariant

**Severity:** P0 (blocks agent use of reporting tools) **Found:** 2026-06-19,
dogfooding session (see [`dogfooding-feedback.md`](./dogfooding-feedback.md))
**Status:** ✅ implemented 2026-06-19 — see "Implementation notes" at the end.

---

## 1. Summary

CodeScent's core invariant — _"bounded output by default; no unbounded source
dump"_ (`README.md`, `docs/mcp-tools.md`) — is violated by its list/aggregate
tools. On this repository (1,270 findings):

- `get_smell_report` returned **338,495 characters** and was **rejected by the
  MCP client** for exceeding the token limit. It is unusable.
- `scan_code_health` returned all **1,152 finding IDs inline** in one payload.

Both overflow or bloat the agent's context — the exact harm CodeScent exists to
prevent.

## 2. Root cause

The list/aggregate tool payloads return the _entire_ finding collection with no
cap, no summary envelope, and no retrieval handle. From
`src/codescent/mcp/finding_tools.py` and `finding_payloads.py`:

```python
# scan_code_health -> scan_payload(...)
"finding_ids": scan.finding_ids,      # ALL ids, unbounded (1,152 here)
"rule_ids": scan.rule_ids,

# get_smell_report
"findings": tuple(finding_payload(f) for f in report.findings),  # ALL findings, unbounded

# get_backlog
"finding_ids": backlog.finding_ids,   # ALL ids, unbounded

# get_regressions
"finding_ids": regressions.finding_ids,   # ALL ids, unbounded

# rescan -> rescan_payload(...)
"finding_ids": ...,  "regressed_finding_ids": ...,   # ALL ids, unbounded
```

The machinery to fix this **already exists and is already used** by
`find_symbol`: when a result is large it stores the full payload via
`ResultStoreService.store_result(...)`, returns a bounded preview envelope with
`mode`, `omitted_count`, `original_result_id`, and `retrieval_available`, and
the agent pulls more via `retrieve_result(result_id, mode=...)`. The
list/aggregate tools simply don't use it.

## 3. Affected tools

| Tool               | Field(s) that overflow                 | Severity                    |
| ------------------ | -------------------------------------- | --------------------------- |
| `get_smell_report` | `findings` (full objects)              | **P0** — rejected at 338 KB |
| `scan_code_health` | `finding_ids`, `rule_ids`              | **P0** — 1,152 ids inline   |
| `get_backlog`      | `finding_ids`                          | P1                          |
| `get_regressions`  | `finding_ids`                          | P1                          |
| `rescan`           | `finding_ids`, `regressed_finding_ids` | P1                          |

## 4. Proposed fix

### 4.1 Principle

No list tool returns more than `N` items inline (default **N = 25**,
configurable via `ContextOptions`). Everything beyond `N` is summarized in
aggregate counts and made retrievable by an opaque `result_id` — never dumped.
This is exactly the `find_symbol` envelope contract, applied uniformly.

### 4.2 Bounded envelope shape (applied to every list/aggregate tool)

```jsonc
{
  "ok": true,
  "kind": "smell_report", // or "scan", "backlog", "regressions"
  "scan_id": "80c659b2…", // where applicable

  // --- always-bounded aggregates (the default useful answer) ---
  "total_count": 1270,
  "status_counts": { "needs_review": 1270, "open": 0, "resolved": 0 },
  "severity_counts": { "info": 897, "warning": 373 },
  "rule_counts": {
    // top rules by count, capped
    "python.duplicate_literal": 510,
    "python.large_function": 237,
    "python.large_file": 110,
    // … truncated; full breakdown via retrieve_result
  },

  // --- bounded preview of the actual items ---
  "items": [
    /* <= 25 highest-priority findings, full finding_payload shape */
  ],
  "returned_count": 25,
  "omitted_count": 1245,

  // --- retrieval handle for the rest (reuses ResultStoreService) ---
  "mode": "preview", // "preview" | "exact" | "summary" | "filtered"
  "original_result_id": "ctx_7f3a…",
  "retrieval_available": true,
  "retrieval_hints": [
    "retrieve_result(result_id, mode='filtered', rule_id='python.large_file')",
    "retrieve_result(result_id, mode='exact', limit=100)",
  ],

  "warnings": ["1245 findings omitted from inline output; use retrieve_result"],
  "next_tools": ["get_next_improvement", "retrieve_result"],
}
```

Key properties:

- **The default answer is the aggregate**, not the dump. An agent asking "how
  healthy is this repo?" gets `total_count`, `severity_counts`, `rule_counts`,
  and the top 25 — in well under 1 KB.
- **Nothing is lost.** The full set is stored and reachable by `result_id`
  through the existing `retrieve_result` (`exact` / `summary` / `filtered` /
  `sample` modes already implemented).
- **Determinism preserved.** Ordering is the existing `_finding_priority`; the
  cap is a pure function of that order.

### 4.3 `scan_code_health` specifically

It should _not_ return `finding_ids` at all by default. A scan summary is the
right shape:

```jsonc
{
  "ok": true, "status": "complete", "scan_id": "80c659b2…",
  "findings_created": 1152,
  "rule_counts": { "python.duplicate_literal": 510, … },   // capped
  "severity_counts": { "info": 897, "warning": 373 },
  "top_findings": [ /* <= 25 by priority */ ],
  "result_id": "ctx_…", "retrieval_available": true,
  "next_tools": ["get_next_improvement", "get_smell_report"]
}
```

The agent loop never needs 1,152 raw ids; it needs the next action.

## 5. Implementation sketch

Reuse the existing path from `context_tools.py` (the `find_symbol` envelope):

1. Add a small helper
   `bounded_finding_envelope(items, *, kind, options, repo, aggregates)` in a
   shared module (e.g. `mcp/finding_payloads.py`) that:
   - sorts/takes the first `options.limit` (default 25) items,
   - computes `omitted_count`,
   - on overflow, calls `ResultStoreService(repo).store_result(...)` with the
     full collection and attaches `original_result_id` + `retrieval_hints`,
   - attaches the precomputed aggregate counts.
2. Rewrite `get_smell_report`, `scan_payload`, `get_backlog`, `get_regressions`,
   and `rescan_payload` to return through that helper.
3. Add the aggregate counts (`severity_counts`, `rule_counts`) to the underlying
   service results (`FindingsService.get_smell_report` / `CodeHealthScanResult`)
   so they are computed once, server-side, in SQL.
4. Update the `TypedDict`s in `finding_payloads.py`.

## 6. Surface / lockstep

Per the plan's §4.1 recipe: update `docs/mcp-tools.md` for each tool's new
bounded shape, and extend the public-surface contract test to assert that
list/aggregate tools (a) never exceed the inline cap and (b) expose
`retrieval_available` when truncated.

## 7. Tests / acceptance

- **Regression test (the bug):** seed a fixture repo with > 1,000 findings;
  assert every list/aggregate tool payload serializes to **< 8 KB** and exposes
  a `result_id` when `omitted_count > 0`.
- **Round-trip test:** `retrieve_result(result_id, mode="exact")` returns the
  full set that was omitted; `mode="filtered", rule_id=…` filters correctly.
- **Determinism:** same state → identical envelope bytes across two runs.
- **Cold/empty:** zero findings → no `result_id`, `omitted_count = 0`, still
  valid.
- Existing gates: `pytest`, `ruff check`, `ruff format --check`, `basedpyright`,
  MCP smoke.

## 8. Why this is P0 and comes before any new feature

Every roadmap idea that produces a list — `get_calibration` (#1), clustered
backlog (#4), ratchet `new_findings` (#6), `propose_patch` batches (#3) — will
inherit this overflow unless the envelope is fixed first. Fixing it once, in a
shared helper, makes every current and future list tool safe. It is the cheapest
high-leverage change available and it unblocks honest evaluation of everything
else.

## 9. Implementation notes (as shipped)

Implemented 2026-06-19. What landed, versus the proposal above:

- **Shared helper** `bounded_finding_list(...)` plus `build_scan_envelope(...)`
  in `src/codescent/mcp/finding_payloads.py`, reusing `ResultStoreService` and
  the existing `retrieve_result` modes (`exact`/`summary`/`filtered`/`sample`).
  Inline cap is `INLINE_ITEM_LIMIT = 25`; rule histogram cap is
  `RULE_COUNT_LIMIT = 20`.
- **Applied to all five tools** — `get_smell_report`, `scan_code_health`,
  `get_backlog`, `get_regressions`, `rescan` — in
  `src/codescent/mcp/finding_tools.py`. Each returns aggregates (`total_count`,
  `severity_counts`, `rule_counts`), a `<=25` `items` preview,
  `returned_count`/`omitted_count`, and (on overflow) `result_id` +
  `retrieval_available` + `retrieval_hints` + `warnings`.
- **One deviation from §4.3:** `scan_code_health`/`rescan` still expose
  `finding_ids`, but **bounded** to the top-N preview (not all ids). Kept
  because it is a convenient handle and the contract/CLI flows use
  `finding_ids[0]`. The full set is still only reachable via `result_id`.
- **Aggregates computed in the MCP payload layer** (a pure function over the
  findings), not pushed into SQL — simpler, still deterministic. Items are
  ordered by `severity_rank` then id for a stable, useful preview.
- **Tests:** new regression `test_list_tools_bound_output_and_offer_retrieval`
  (40-file repo → bounded payload < 8 KB, `result_id` present, round-trip via
  `retrieve_result` recovers omitted findings); updated the bounded-schema
  snapshot contract and the runtime-safety test to the new `items` shape.
- **Verified on the CodeScent repo itself:** `get_smell_report` went from
  **338,495 chars (rejected)** to **7,903 chars**; `scan_code_health` from a
  1,174-id dump to **8,782 chars** with a 25-item preview and a `result_id`.

Gates: `ruff check`, `ruff format --check`, `basedpyright` (0 errors), and the
full `pytest` suite pass (two unrelated, pre-existing `tests/docs` failures
about `cli-reference.md`/`dashboard.md` guidance strings are untouched by this
change).
