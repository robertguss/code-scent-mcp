# Language Packs

CodeScent keeps language support behind internal pack interfaces before opening
an external plugin API. The first non-Python pack will cover JavaScript,
TypeScript, JSX, TSX, React, and basic Next.js routing.

## Parser Decision

The TypeScript/JavaScript pack will use `tree-sitter` through a local deterministic parser
adapter. The adapter must run from installed local
dependencies, require no runtime network, and degrade gracefully when a grammar
cannot produce high-confidence references.

This keeps parsing source-read-only and gives CodeScent one parser strategy for
plain JavaScript, JSX, TypeScript, and TSX instead of separate ad hoc regex
paths.
