# CodeScent Audit Phase 3 — design diagrams

Referenced from beads epic `code-scent-mcp-audit-phase3-internals-signal-ul1r` and its units. These are design assets only; work state lives in beads (`br show <id>`, `br dep tree <id>`).

## Finding-view severity/tier gate (firehose fix) — bead P3.1 (`…ul1r.1`)

Every default view funnels through one no-`WHERE`-clause choke (`FindingRepository.list_findings`). The gate is inserted once, at that shared boundary, reading the axes findings already carry. The full unfiltered set stays reachable behind an explicit parameter — nothing is deleted.

```mermaid
flowchart TB
  subgraph rules[engine/rules -- emit findings today]
    D1[python.duplicate_literal<br/>severity=info, tier=heuristic]
    D2[generic.duplicate_literal<br/>severity=info, tier=heuristic]
    D3[python.structural_near_duplicate<br/>severity=info, tier=heuristic]
    W[warning-severity / verified-tier findings]
  end
  D1 & D2 & D3 & W --> Store[(findings table<br/>severity + confidence + confidence_tier)]
  Store --> Choke["FindingRepository.list_findings()<br/>+ NEW default severity/tier gate"]
  Choke -->|default: actionable first, noise as bounded tail| V1[get_next_improvement]
  Choke -->|default gate| V2[get_smell_report]
  Choke -->|default gate| V3[get_backlog]
  Choke -->|default gate| V4[get_improvement_plan]
  Choke -.->|explicit include_all / min_severity param| Full[full unfiltered set -- opt-in]
```

## Envelope conformance fix (one constructor, 16 call sites) — beads P3.3 (`…ul1r.3`) + P3.4 (`…ul1r.4`)

```mermaid
flowchart LR
  subgraph today[16 non-conforming tools]
    SA["Class A (10): ok:True, no next_tools"]
    SAp["Class A-prime (2): terminal -- how_to_use, get_schema"]
    SApp["Class A-dbl (1): explain_score emits next_steps"]
    SB["Class B (1): context_stats -- bare dict, no ok"]
    SC["Class C (2): ok overloaded as domain verdict"]
  end
  SA & SAp & SApp & SB --> Helper["NEW ok_envelope(next_tools, **fields)<br/>injects ok:True + next_tools"]
  SC --> Decouple["decouple transport-ok from domain verdict<br/>verdict to its own field, ok:True always"]
  Helper --> Pass[envelope_conformance 48/48]
  Decouple --> Pass
```
