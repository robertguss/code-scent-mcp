# Language Packs

CodeScent keeps language support behind internal pack interfaces before opening
an external plugin API.

## Shipped Packs

### Python

The Python pack covers inventory, symbol extraction, bounded context,
deterministic maintainability findings, test proximity, and the Python-first
MVP workflow.

### TypeScript/React/Next

The TypeScript/React/Next pack covers JavaScript, TypeScript, JSX, TSX, React,
and basic Next.js routing patterns. It is implemented as an internal pack, not
an external plugin API.

## Parser Decision

The TypeScript/JavaScript pack uses a local deterministic parser adapter. The
adapter must run from installed local dependencies, require no runtime network,
and degrade gracefully when a grammar cannot produce high-confidence
references.

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
