# TEST GUIDANCE

## OVERVIEW

`tests` is organized by behavior surface: unit, integration, contract, smoke,
eval, docs, security, and fixture validation.

## STRUCTURE

```text
tests/
+-- unit/          # pure logic
+-- integration/   # services, storage, dashboard, parser, git behavior
+-- contract/      # CLI and MCP public-surface contracts
+-- smoke/         # smoke-plan and runtime-state checks
+-- evals/         # deterministic eval behavior
+-- docs/          # docs-to-behavior assertions
+-- security/      # no-network and source-read-only proofs
+-- fixtures/      # checked-in analyzed repos and migration seed data
```

## WHERE TO LOOK

| Task | Location | Notes |
| --- | --- | --- |
| CLI surface | `contract/test_cli.py` | Typer runner contract. |
| MCP surface | `contract/test_mcp_*` | Uses `fastmcp.Client` in-process. |
| Dashboard behavior | `integration/test_dashboard.py` | Starts local server and checks traversal/config. |
| Storage behavior | `integration/test_storage*.py` | SQLite state, migration, concurrency. |
| Read-only safety | `security/test_runtime_safety.py` | Source hash, no network, dashboard smoke. |
| Deterministic eval | `evals/test_deterministic_eval.py` | Manifest-backed fixtures. |
| Docs contract | `docs/test_docs.py` | README/docs must mention required safety/gates. |

## CONVENTIONS

- Pytest config lives in `pyproject.toml`: strict config/markers, warnings as
  errors, and `tests/fixtures/python-basic` excluded from direct recursion.
- Prefer `tmp_path` for repos that need mutation or `.codescent` state.
- Contract tests protect public names, descriptions, bounded schemas, and safety
  language. Update them with any public surface change.
- Some tests intentionally create git repos, SQLite files, live local servers,
  or temp Chrome profiles.
- Fixture repos are inputs under analysis; tests may write `.codescent` inside
  them, but should not silently modify checked-in source.

## ANTI-PATTERNS

- Do not weaken source-read-only, no-network, or bounded-output assertions to
  make tests pass.
- Do not add broad direct recursion into fixture sample test suites.
- Do not remove docs-contract assertions when changing docs; update the docs or
  product contract instead.
