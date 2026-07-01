# ADR-0001: codebase-memory-mcp stays optional (deferred hard dependency)

**Status:** Decided — 2026-07-01
**Requirements:** R11, R12 (see
`docs/plans/2026-07-01-002-feat-retrieval-quality-cbm-plan.md`)

## Context

Dogfooding raised the question of whether `codebase-memory-mcp` (cbm) should
become a hard dependency "like `fff-search`" — installed and required on every
CodeScent install, with the native fallback removed.

That question conflates two orthogonal levers:

1. **Wire cbm deeper** — route `find_callers`, `find_callees`, and the dead-code
   rule through cbm's real call graph when a local cbm process is present. This
   is a pure quality win and needs no hard requirement. (Done: see U6–U8.)
2. **Require cbm** — drop the native fallback so every install must run the cbm
   binary. This is an operational and identity change.

`fff-search` could take both at once because a pinned wheel is cheap. cbm cannot:
it is an out-of-process server reached over IPC.

## Decision

**cbm remains optional.** The native backend is the always-on floor; cbm is used
only when a local process is present, healthy, and applicable (Hybrid-LSP
languages). We do **not** promote cbm to a hard dependency at this time.

## Rationale

1. **Latency.** A required IPC handshake with a 5s timeout in front of tools —
   especially the `hook-augment` path that runs before every grep — works
   against the cold-start reduction (~680ms → ~275ms) landed in PR #9.
2. **Identity.** CodeScent advertises "local, deterministic, bounded, zero
   network." A required external server with its own drifting index dents both
   "zero-setup" and "deterministic."
3. **Native path is unavoidable anyway.** cbm's call graph is dropped for
   non-Hybrid-LSP languages (the tree-sitter tail), so the native backend must
   stay a real path regardless — it cannot be removed.
4. **External release cadence.** cbm is a separately released project (DeusData),
   adding version-skew and IPC-contract-drift risk that a pinned wheel does not
   carry.

## Revisit trigger (R12)

Revisit hardening cbm into a required dependency **only if the cbm-present rate
across real sessions sustains above 85%** — i.e. the native fallback is rarely
exercised in practice.

**Measurement.** The `context_stats` MCP tool reports the signal per session:

```
cbm_present_rate = cbm_resolutions / backend_resolutions
```

`backend_resolutions` counts every structural-backend resolution
(`find_callers` / `find_callees`); `cbm_resolutions` counts the subset that
resolved cbm. Sessions that never touch a structural tool contribute zero
resolutions and are excluded from the denominator.

If that rate holds ≥85% for a sustained window, re-weigh the latency and
identity costs above and reconsider. If adoption stays low (<50%), consider
removing the cbm seam entirely.

## Consequences

- cbm stays opt-in; no install breakage, no new required process.
- The cold-start path is unaffected when cbm is absent (a `shutil.which` check,
  no subprocess).
- `find_callers` / `find_callees` / dead-code are higher quality when cbm is
  present; behavior is byte-for-byte the current native path when it is absent.
- Future cbm releases (v2, IPC-contract changes) never block a CodeScent release.
