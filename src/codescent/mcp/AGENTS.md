# MCP GUIDANCE

## OVERVIEW

`src/codescent/mcp` exposes CodeScent capabilities through FastMCP. This layer
is transport glue and user-facing tool descriptions, not business logic.

## WHERE TO LOOK

| Task | Location | Notes |
| --- | --- | --- |
| Server setup | `server.py` | Creates `FastMCP(name="CodeScent")` and registers groups. |
| Repo/status tools | `repo_tools.py` | Read-only orientation and status. |
| Search tools | `search_tools.py` | Ranked, bounded source search. |
| Context graph tools | `context_tools.py` | File/symbol/reference/caller/callee context. |
| Finding tools | `finding_tools.py` | Scan, explain, backlog, lifecycle updates. |
| Planning tools | `planning_tools.py` | Refactor plan and suggested tests. |
| Prompt resources | `prompts.py` | Bounded prompt templates. |
| Payload models | `finding_payloads.py` | MCP-facing Pydantic payloads. |

## CONVENTIONS

- Tool descriptions are part of the contract. Preserve read-only, bounded, and
  `.codescent`-only wording when editing them.
- Tool bodies should instantiate/call services and return structured payloads.
- The exposed surface is checked by contract tests and `core/public_surface.py`.
- Lifecycle tools may write `.codescent` finding state; repo/source tools must
  stay read-only for analyzed source.

## ANTI-PATTERNS

- Do not put analysis algorithms in MCP modules.
- Do not return full source files when a bounded snippet or context object is
  sufficient.
- Do not expose reset/admin-only behavior as MCP tools unless the public surface
  and safety docs explicitly change.
