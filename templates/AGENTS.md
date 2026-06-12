# TEMPLATE GUIDANCE

## OVERVIEW

`templates` contains optional downstream agent-routing files. They are examples
for repos that choose to route coding agents through CodeScent.

## WHERE TO LOOK

| Task | Location | Notes |
| --- | --- | --- |
| Codex/OpenAI agents | `AGENTS.md`, `CODEX.md` | Source-read-only CodeScent routing text. |
| Claude agents | `CLAUDE.md` | Same routing contract for Claude-style repos. |
| Template docs | `docs/agent-routing.md` | Explains that templates are optional. |

## CONVENTIONS

- Templates must say CodeScent is source-read-only for analyzed source.
- Templates may tell agents to use CodeScent before broad grep or large reads.
- Keep the template names aligned with agent ecosystems; avoid repo-specific
  filenames that would not be recognized downstream.
- Keep the text generic enough to copy into another repo, but accurate to this
  product's actual runtime behavior.
- CodeScent does not auto-write these files into analyzed repositories.

## ANTI-PATTERNS

- Do not imply CodeScent can edit source automatically.
- Do not add product promises that are not supported by the current tool surface.
- Do not make templates depend on this repo's private `.omo` workflow.
