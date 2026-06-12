# SERVICES GUIDANCE

## OVERVIEW

`src/codescent/services` is the main business-logic layer shared by CLI, MCP,
dashboard, tests, and smoke/eval flows.

## WHERE TO LOOK

| Task | Location | Notes |
| --- | --- | --- |
| Repo indexing | `repo_index.py`, `symbols.py` | Builds persisted inventory and symbols. |
| Search | `search.py`, `search_support.py`, `search_queries.py` | Bounded ranked results. |
| Context | `context.py`, `context_support.py` | File, symbol, graph, and related-file context. |
| Findings | `findings.py`, `code_health.py`, `rules.py` | Deterministic scan and lifecycle state. |
| Planning | `refactor_planning.py`, `verification.py`, `risk.py` | Plans and tests without executing fixes. |
| Config | `config.py` | Preserve unknown TOML sections when updating. |
| Reports | `reports.py`, `status.py`, `ci.py` | Operator-facing summaries and thresholds. |

## CONVENTIONS

- Services should accept repo paths or typed option models and return structured
  payloads; adapters decide how to serialize them.
- Keep deterministic and subjective findings separated. Subjective review must
  not masquerade as deterministic analysis.
- Preserve raw config content where the caller may have hand-edited TOML.
- Keep search/context limits explicit and testable.
- Git helpers should exclude `.codescent` state from source status.

## ANTI-PATTERNS

- Do not import FastMCP or Typer here.
- Do not mutate source files as part of scanning, planning, search, context, or
  risk analysis.
- Do not make service methods depend on network availability.
- Do not collapse dashboard, CLI, and MCP response shapes into service logic
  unless the shape is a real domain model.
