# Language Packs

CodeScent keeps language support behind internal pack interfaces before opening
an external plugin API.

## Shipped Packs

### Python

The Python pack covers inventory, symbol extraction, bounded context,
deterministic maintainability findings, test proximity, and the Python-first MVP
workflow.

It also ships import-cycle / dependency-SCC detection under the rule id
`python.import_cycle`. The rule reuses the existing Python import parser to build
a file-to-file dependency graph (resolving module names to repo files; external
imports are skipped), computes strongly connected components, and emits one
finding per cycle of size > 1 and one per re-export self-loop. Each finding's
evidence carries the ordered `cycle_path`, the sorted `cycle_members`, and the
`cycle_size`; the suggested action names a concrete edge to break. Findings are
ranked largest-cycle-first (the "cycle size x churn" ranking degrades to size at
the engine layer, which cannot read the git churn signal). The rule is part of
the `python-maintainability` pack and is gated by the same config flag.

### TypeScript/React/Next

The TypeScript/React/Next pack covers JavaScript, TypeScript, JSX, TSX, React,
and basic Next.js routing patterns. It is implemented as an internal pack, not
an external plugin API.

Import-cycle detection (`typescript.import_cycle`) is **not yet shipped**. The
TypeScript pack is regex-based, and resolving TS/JS import specifiers to files
(relative paths, extensionless imports, `index` files, and `tsconfig` path
aliases) cannot currently be done at high enough confidence to avoid false or
missing cycles. The rule id is reserved; Python ships first.

## Parser Decision

The TypeScript/JavaScript pack uses a local deterministic parser adapter backed
by tree-sitter. The adapter must run from installed local dependencies, require
no runtime network, and degrade gracefully when a grammar cannot produce
high-confidence references.

This keeps parsing source-read-only and gives CodeScent one parser strategy for
plain JavaScript, JSX, TypeScript, and TSX instead of separate ad hoc regex
paths.

## Future Packs

Future packs may add Go, Rust, Ruby, Elixir, PHP, or other language support.
Future packs should keep the same source-read-only and runtime no-network
contracts.

## Related Docs

- [MCP tools](mcp-tools.md)
- [Workflows](workflows.md)
