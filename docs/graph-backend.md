# GraphBackend: optional cbm structural backend

CodeScent owns the quality verdicts (smells, findings, risk). The *structural*
layer underneath — symbols, complexity props, call edges, clusters — is exposed
through a small read-only interface, `GraphBackend`, so it can optionally be
sourced from [codebase-memory-mcp](https://example.invalid) (cbm), a fast local
structural index, instead of CodeScent's own parser.

This is an **additive** abstraction. The native backend is the default and the
fallback; nothing in the live scan pipeline requires cbm. When cbm is absent or
unhealthy, behaviour is exactly as it was before this layer existed.

## Interface

`codescent.services.graph_backend.GraphBackend` (a `runtime_checkable` Protocol):

| Method | Returns | Meaning |
| --- | --- | --- |
| `name()` | `str` | Backend identity (`"native"` / `"cbm"`). |
| `available()` | `bool` | Whether the backend can serve data right now. |
| `symbols()` | `tuple[SymbolNode, ...]` | Defined symbols with location + language. |
| `complexity()` | `tuple[ComplexityProps, ...]` | Per-symbol complexity props. |
| `call_edges()` | `tuple[CallEdge, ...]` | Caller → callee references. |
| `clusters()` | `tuple[Cluster, ...]` | Cohesion clusters. |

All results are deterministic (stable ordering) and read-only over the source.

## Native backend (default)

`NativeGraphBackend` wraps CodeScent's existing SQLite index (the same
`symbols`, `symbol_references`, and `files` tables read by the context service).
It changes no existing service. Notes:

- **complexity** uses the symbol's line span as a complexity proxy — the native
  indexer computes no cyclomatic metric.
- **clusters** are directory groupings, not Leiden communities.

cbm supplies richer values for both when present.

## cbm adapter

`CbmGraphBackend` (in `codescent.services.cbm_backend`) wraps a `CbmClient` and a
`NativeGraphBackend` for fallback. `select_graph_backend(repo_root)` returns the
cbm backend when a healthy local cbm process is detected, else the native one.

### Detection (local IPC only, never the network)

`detect_cbm()` looks for a local cbm CLI via the `CODESCENT_CBM_CMD` environment
variable or `shutil.which("cbm" | "codebase-memory-mcp")`. If none is found it
returns `None` and CodeScent uses the native backend. The `CbmCliClient` talks
to the discovered binary over a JSON contract using `subprocess` only — there is
no socket or HTTP path anywhere in this module. `tests/security/test_runtime_safety.py`
asserts the adapter performs no network I/O.

### Language tiering (the hard constraint)

cbm resolves the tree-sitter tail by **bare name** and collapses every
same-named symbol across languages (it once reported a private Elixir `defp get`
with 211 cross-language callers). That collision must never leak into findings,
so the adapter tiers cbm output:

| Data | Hybrid-LSP language | Tree-sitter tail |
| --- | --- | --- |
| symbols | trusted | trusted (name + location only, no resolution) |
| complexity | trusted | trusted (per-symbol, no cross-refs) |
| **call edges** | trusted | **dropped** |
| **clusters** | trusted | **dropped if any member language is non-Hybrid-LSP** |

Hybrid-LSP languages: Python, TypeScript/JavaScript, Go, Java, Rust, C#, Kotlin,
PHP, C, C++ (`graph_backend.HYBRID_LSP_LANGUAGES`).

Tiering applies **only** to cbm-sourced data. Native data is already trustworthy
and is returned unfiltered, including on fallback.

### Fallback

If cbm is unhealthy, raises, or returns invalid data, every method falls back to
the native backend for that call and logs the reason. The result is
quality-equivalent to running without cbm and can never inherit a bare-name
collision.

### Assumed CLI JSON contract

`CbmCliClient` expects `cbm <subcommand> --repo <path> --format json` to emit:

- `health` → object with an `ok` boolean.
- `symbols` / `complexity` / `call_edges` / `clusters` → a JSON array of records
  matching the corresponding `graph_backend` dataclass fields.

Payloads are validated with pydantic; anything malformed raises `CbmClientError`
and triggers native fallback.

## Scope

The deliverable is the abstraction + native default + cbm adapter (tiering,
fallback, detection, no-network proof) and a parity demonstration. Wiring cbm
into live finding production beyond that demo is intentionally out of scope.
