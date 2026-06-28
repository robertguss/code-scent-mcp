# Learnings & Ideas from codebase-memory-mcp

> Source: empirical analysis of **codebase-memory-mcp** (cbm) v0.8.1 on 2026-06-28 —
> driving its 14 MCP tools against real repos (including this one) and verifying
> results against ground truth. cbm is a pure-C, tree-sitter + Hybrid-LSP
> knowledge-graph MCP server. This doc distills what's worth borrowing and, more
> importantly, what cbm got *wrong* — because its failure modes are a ready-made
> design spec for a code-quality tool like CodeScent.
>
> Advisory only (not beads — a parallel session owns the backlog). Each idea is
> tagged against the current 21 open beads so nothing here duplicates planned work.

## TL;DR

The single highest-value takeaway: **cbm's biggest failures are exactly the traps
a smell engine sits in.** cbm produces confident false positives because it
resolves symbols by bare name and optimizes recall with no precision gate. Proof
points, observed directly:

- A *private* Elixir `defp get` was reported with 211 callers — including Python
  files that cannot call it. Bare-name call resolution collapses every `get` onto
  one node. (Hotspots/fan-in for tree-sitter-only languages are noise.)
- A distinctively-named public function showed **0 callers** despite real call
  sites — the same resolver under-attributes unique names.
- CodeScent's own `get_smell_report` was flagged `self_recursive` /
  `unguarded_recursion` by cbm. It is not recursive — it delegates to a
  same-named *service method*. Bare-name match again (upstream cbm issue #599).
- cbm's `get_smell_report` node shows `in_degree=0`, yet it is a live registered
  MCP tool. A naive dead-code rule would flag it dead.
- cbm's Route extractor turns plain path-like strings (test fixtures, config
  values, regex literals) into `Route` nodes (upstream #598).

These are not edge cases; they are structural consequences of (a) name-based
resolution and (b) no precision measurement. CodeScent should be built so it
cannot make these mistakes — and should *advertise* that it doesn't.

## Cross-cutting learnings

1. **Recall without a precision gate = shipped false positives.** Every rule
   needs a measured precision number and a regression gate, not just "does it
   fire on the bad case."
2. **Name-based resolution is a trap.** Be resolution-aware *and*
   entry-point-aware. Dynamic dispatch, decorators, framework/MCP-tool
   registration, and CLI entry points all break naive caller/dead-code logic.
3. **Confidence is language-dependent — tier it and surface it.** cbm silently
   mixes high-confidence (Hybrid-LSP: Python, TS/JS, Go, Java, Rust, C#, Kotlin,
   PHP, C, C++) with heuristic (everything else) output. A finding that doesn't
   carry its own confidence is untrustworthy by default.
4. **Don't reimplement the structural layer.** A fast graph backend already
   yields symbols, complexity metrics, call edges, and community clusters.
   Re-parsing in Python won't match pure-C tree-sitter on speed or language
   coverage.
5. **Dogfood.** The way these bugs surfaced was running the tool on real code,
   including its own. Make "scan yourself, expect zero false positives" a
   standing CI gate.

## Ideas, deduped against the open backlog

Legend: **NEW** = not in backlog · **EXTENDS** = hardens/builds on an open or
shipped bead · **OVERLAPS** = substantially covered already.

### Top 5

**1. Optional cbm structural backend (`GraphBackend` adapter).** — NEW
When cbm is available, pull symbols + complexity props + call edges + clusters
from it (via MCP/CLI) instead of re-parsing; keep CodeScent owning
smells/findings/risk. Inherits 158 languages and millisecond indexing for the
structural layer; falls back to the native engine when cbm is absent.
*Hard constraint from testing:* trust cbm's **call graph only for Hybrid-LSP
languages**; degrade to symbol-only for the tree-sitter tail. Bake that tiering
into the adapter so cbm's collision bug can't leak into CodeScent findings.
Note: CodeScent already builds its own import graph (see `import_cycle` epic
`code-scent-mcp-import-cycle-rule-7md`), so the backend is additive, not a
replacement.

**2. Confidence tier + provenance on every finding.** — NEW
Add `confidence` (verified | heuristic) and `provenance` (rule id, evidence,
resolution source, language tier) to each finding; extend
`services/risk.py:_severity_score`. A resolved Python finding ranks "verified";
a heuristic one is labeled as such. This is the cheapest trust win and the exact
thing cbm lacks. Feeds idea #13 (dashboard badges).

**3. Per-rule precision/recall harness + labeled false-positive corpus.** — EXTENDS evals
Build on the existing `evals/` + `run_deterministic.py` and the autofix-ratchet
work. Add per-rule corpora of known-clean and known-smelly snippets, measure
**precision per rule**, and gate rule changes on precision regression in CI.
This is the structural defense against becoming cbm (#598/#599). Pairs naturally
with the ratchet already in `docs/ideas/implementation-plan-feedback-autofix-ratchet.md`.

**4. Resolution-aware + entry-point-aware `dead_code` and structural duplicates.** — EXTENDS
`engine/rules/dead_code.py` and the (shipped) structural near-duplicate rule are
the two most exposed to the bare-name trap. Dead-code must exclude dynamic
dispatch, decorators, `__all__`, framework/MCP-tool registration, and CLI entry
points — otherwise it flags things like a registered `how_to_use` tool as dead
(the `in_degree=0` case). Add an entry-point registry the rule consults.

**5. Dogfood gate — CodeScent scans CodeScent in CI.** — EXTENDS `docs/ideas/dogfooding-feedback.md`
Run the engine on this codebase and assert ~zero findings (allowlist the real
ones); a living precision test. The dogfooding doc already exists; this makes it
an enforced gate rather than a one-off exercise.

### Next 10

6. **Complexity smells via cbm Cypher.** — NEW (depends on #1)
   `transitive_loop_depth`, `linear_scan_in_loop`, `alloc_in_loop` are
   precomputed in cbm; query them instead of reimplementing hidden-O(n²)
   detection.
7. **Coupling/modularity smell from cbm Leiden clusters.** — EXTENDS `refactor_preflight`
   Flag functions bridging many clusters (god-objects, high coupling); cbm gives
   cohesion scores for free. Complements `refactor_preflight`
   (`code-scent-mcp-refactor-preflight-sdz`) and the `import_cycle` SCC rule.
8. **Incremental diff-time scan.** — EXTENDS `review_diff_risk` / `refactor_preflight`
   cbm `detect_changes` → re-scan only changed symbols and remap to findings;
   wire into the existing changed-file-health / `review_diff_risk` path for fast
   PR-time review.
9. **Finding re-verification on fingerprint change.** — EXTENDS verification ledger / ratchet
   cbm exposes a per-node `fp` fingerprint; when a symbol's fp changes,
   re-verify the finding instead of carrying status blindly. Strengthens the
   baseline/regression + verification-ledger machinery used by
   `resume_task` (`code-scent-mcp-resume-task-u18`).
10. **Versioned rule packs + provenance.** — EXTENDS `PackRegistry`
    Add semver, pinning, and "which pack@version produced this finding" to
    `engine/packs.py`.
11. **Per-repo severity calibration.** — NEW
    Learn baseline noise levels so a TODO-heavy repo doesn't drown signal;
    extend the risk service.
12. **`explain_finding` MCP tool.** — EXTENDS `get_finding_context`
    Return exact snippet + why + suggested fix, not just a flag. Actionable
    layer over existing finding payloads.
13. **Confidence/tier badges in the dashboard.** — NEW (depends on #2)
    Surface per-finding confidence and language tier in `dashboard.md`.
14. **Inline suppression.** — NEW
    Honor `# codescent: ignore[rule]` with an audit trail; standard linter
    ergonomic that cuts noise.
15. **Content-hash scan cache + parallelism.** — NEW
    Cache by file content hash and parallelize the scan so the Python engine
    feels fast next to cbm; perf is an adoption gate.

## What's net-new vs already planned

- **Net-new, highest leverage:** cbm structural backend + language tiering (#1),
  confidence/provenance on findings (#2), entry-point-aware dead-code hardening
  (#4), per-repo calibration (#11), inline suppression (#14), scan cache (#15).
- **Extends existing backlog:** precision harness (evals/ratchet),
  coupling/cluster smell (`refactor_preflight`), incremental scan
  (`review_diff_risk`), fp re-verification (`resume_task` ledger), pack
  versioning (`PackRegistry`), `explain_finding` (`get_finding_context`),
  dogfood gate (`dogfooding-feedback.md`).
- **Already covered — do not duplicate:** import-cycle / dependency-SCC
  detection (`code-scent-mcp-import-cycle-rule-7md`), blast-radius bundling
  (`code-scent-mcp-refactor-preflight-sdz`), structural near-duplicate detection
  (shipped, Plan 010).

## Strategic note

The cbm signals that are *weakest* — smells, recursion flags, hotspots,
quality judgments — are precisely CodeScent's domain. So the two tools
complement rather than compete: use cbm as a fast structural index/navigator
(symbols, snippets, complexity, clusters) and let CodeScent own the quality
verdicts cbm gets wrong. Positioning CodeScent as "the precision-gated,
confidence-tiered quality layer" is a real differentiator, directly motivated by
cbm's observed failure modes.
