# CodeScent Audit Phase 2 — design diagrams

Referenced from beads epic `code-scent-mcp-audit-phase2-consolidation-yzsz` and its units. Design assets only; work state and dependencies live in beads (`br show <id>`, `br dep tree <id>`).

## Eval-gated cluster merge loop (KF1) — the pending-consolidation workflow — beads P2.1 (`…yzsz.2`), P2.3 (`…yzsz.4`)

Every consolidation cluster lands as its own commit, re-runs the offline `run_agent_ux.py --check` (deterministic dims + R6), and is backed out if any dimension regresses beyond its band.

```mermaid
flowchart TB
  Start[Baseline recorded] --> Pick[Pick next cluster]
  Pick --> Merge[Merge behind mode/view param]
  Merge --> Run[Re-run suite]
  Run --> Cmp{Any dimension<br/>below baseline?}
  Cmp -->|no| Keep[Keep merge]
  Cmp -->|yes| Back[Back out and revise]
  Keep --> More{More clusters?}
  Back --> Pick
  More -->|yes| Pick
  More -->|no| Done[Consolidated surface ships]
```

## Eval-suite no-network architecture (shipped PR #15; reference for the gate the merges run) — epic `…yzsz`

The deterministic dimensions (R2–R6) stay inside the pure-Python floor; R1's model driver is the single network-touching component, isolated behind a `ToolSelector` Protocol, never imported by the deterministic path or the default CI gate.

```mermaid
flowchart TB
  subgraph runner[evals/run_agent_ux.py - Typer CLI]
    CLI["--check / --update-baseline / --repeat N / --live-model"]
  end
  subgraph det[deterministic.py - NO network]
    R2[R2 error_recovery]
    R3[R3 loop_connectivity]
    R4[R4 envelope_conformance]
    R5[R5 constraint_drop]
    R6[R6 manifest_token_cost]
  end
  subgraph sel[tool_selection.py - R1]
    P{{ToolSelector Protocol}}
    Heur[HeuristicToolSelector<br/>rapidfuzz, offline proxy]
    Live[LiveModelToolSelector<br/>network, marker+creds, milestone-only]
  end
  Client[fastmcp.Client mcp - in-memory]
  CLI --> det
  CLI --> sel
  det --> Client
  P --> Heur & Live
  sel --> Client
  Client -->|call_tool / list_tools| MCP[codescent.mcp.server.mcp]
```
