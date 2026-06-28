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

### Go

The Go pack covers symbol extraction and deterministic maintainability findings
for `.go` files. Like the TypeScript pack it is **regex-heuristic** (no
tree-sitter, no parser dependency): `engine/parsers/go.py` extracts `package`,
`func`/method, `type` (struct/interface/alias), and single- and block-form
`import` declarations into the shared `ParsedSymbol`/`ParsedImport` model, tagged
`LOW_CONFIDENCE` because the parse is heuristic rather than an AST. Unreadable or
undecodable files degrade gracefully to an empty parse with a recorded
`parse_error`.

The `go-maintainability` rule pack emits four smells: `go.large_file`,
`go.large_function`, `go.missing_nearby_test` (an exported-function file with no
`_test.go` in its package directory), and `go.duplicate_literal`. Findings are
regex-derived, so they carry the `heuristic` confidence tier and `resolution:
regex` provenance (language `go`). The Go language + rule packs are config-gated
(enabled by default) and the language pack is registered as a *specific* pack
keyed on `.go`, ahead of any generic fallback pack.

### Knowledge silo (bus factor)

The cross-language `knowledge-silo` rule pack flags files that are both
high-churn **and** dominated by a single author -- a maintainability /
bus-factor risk that size and complexity rules miss. It emits
`python.knowledge_silo` for `.py`/`.pyi` files and `typescript.knowledge_silo`
for `.js`/`.jsx`/`.ts`/`.tsx` files.

The signal extends the existing single-pass `git log` parse in
`services/git.py` to capture the commit author (`%H%x00%an`) and aggregates,
per file, the recent commit count (`churn`), the dominant author's share
(`top_author_share`), and the distinct `author_count` -- one `git log`
invocation, no per-commit subprocess. A file is flagged when `churn >= 5` and
`top_author_share >= 0.8`: confidence is **HIGH** (0.9) for a true single-author
file and **LOW** (0.5) when ownership is concentrated but shared. Findings are
git-derived, so they carry the `heuristic` confidence tier and `resolution:
git` provenance. The pack self-disables (no findings) when there is no git
history, so non-git and shallow trees stay clean.

## Parser Decision

The non-Python packs use **local, dependency-free regex parsers** (corrected per
code audit — there is no tree-sitter or any parser dependency in this project).
Both the TypeScript/JavaScript pack (`engine/packs_ts.py`) and the Go pack
(`engine/parsers/go.py`) extract symbols/imports with regexes and emit
`LOW_CONFIDENCE` results, sharing the same `ParsedSymbol`/`ParsedImport` model the
Python AST pack returns. The parsers run from local source only, require no
runtime network, are source-read-only, and degrade gracefully when a file cannot
be read or a construct cannot be matched at high confidence.

Only the Python pack is AST-backed (via the standard-library `ast` module), which
is why Python findings can be tagged `verified` while regex-derived findings are
always `heuristic`.

## Future Packs

Future packs may add Go, Rust, Ruby, Elixir, PHP, or other language support.
Future packs should keep the same source-read-only and runtime no-network
contracts.

## Related Docs

- [MCP tools](mcp-tools.md)
- [Workflows](workflows.md)
