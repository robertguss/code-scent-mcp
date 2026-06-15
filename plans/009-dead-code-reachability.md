# Plan 009: Detect dead-code / unused-export candidates

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving on. If a
> STOP condition occurs, stop and report — do not improvise. When done, update
> the status row for this plan in `plans/README.md`.
>
> **Drift check (run first)**:
> `git diff --stat 40cbf50..HEAD -- src/codescent/engine/rules src/codescent/engine/packs.py src/codescent/engine/parsers/python.py tests plans/README.md`
> If any in-scope file changed, compare excerpts against live code; on a
> mismatch, treat it as a STOP condition.

## Status

- **Priority**: P2
- **Effort**: M
- **Risk**: MED
- **Depends on**: none
- **Category**: direction (new deterministic rule)
- **Planned at**: commit `40cbf50`, 2026-06-15

## Why this matters

Dead code is the safest, most satisfying class of improvement: high confidence,
near-zero behavioral risk, ideal for the "fix one finding safely" loop. AI
agents accrete unused helpers constantly. The PRD lists "dead code candidates"
and "unused exports" but neither is implemented. CodeScent already parses
symbols, imports, and (low-confidence) call references per file, so a
module-level reachability heuristic is cheap to add — emitted with honest
confidence so dynamic-dispatch gray areas are clearly labeled.

## Current state

- The Python parser produces, per file, `symbols` (functions/classes/methods
  with `kind`), `imports`, and `references` (call names, low confidence):

```python
# src/codescent/engine/parsers/python.py:84-92
@dataclass(frozen=True, slots=True)
class ParsedPythonFile:
    path: str
    module: str
    is_test: bool
    symbols: tuple[ParsedSymbol, ...]
    imports: tuple[ParsedImport, ...]
    references: tuple[ParsedReference, ...]
    parse_error: str | None = None
```
  `ParsedReference.name` is the called name (`ast.Name.id` or `ast.Attribute.attr`),
  confidence `0.4`. `ParsedImport` has `.module` and `.name` (imported symbol).

- Rule emission pattern and the scan loop are in
  `src/codescent/engine/rules/python.py` (`scan_python_health`, lines 31-50) and
  registered via `src/codescent/engine/packs.py`. `FindingSpec.evidence` values
  must be scalar (`int | float | str | bool`) — see `engine/rules/model.py:6`.

Repo conventions: strict typing; deterministic-first; degrade with confidence
rather than imply certainty; no network; never edit analyzed source.

## Commands you will need

| Purpose | Command | Expected |
|---|---|---|
| Focused tests | `uv run pytest tests -k "dead_code or unused"` | exit 0 |
| Full tests | `uv run pytest` | exit 0 |
| Lint | `uv run ruff check .` | exit 0 |
| Format | `uv run ruff format --check .` | exit 0 |
| Typecheck | `uv run basedpyright` | exit 0 |

## Scope

**In scope**:
- `src/codescent/engine/rules/dead_code.py` (create) — the reachability scan.
- `src/codescent/engine/packs.py` — register it in the python rule pack OR call
  it from `scan_python_health` (choose one; see Step 3).
- `tests/unit/` and/or `tests/integration/` — dead-code tests.
- `plans/README.md` status row.

**Out of scope**:
- Do NOT delete or edit any analyzed source.
- Do NOT attempt cross-language reachability (Python only here).
- Do NOT mark anything dead with high confidence — cap confidence at 0.6 and
  exclude the ambiguous cases listed below.
- `tests/fixtures/` source.

## Steps

### Step 1: Build the project-wide name-use index

Create `src/codescent/engine/rules/dead_code.py`. Implement
`scan_dead_code(root, *, config=None) -> tuple[CodeHealthFinding, ...]`
mirroring `scan_python_health`'s inventory iteration.

First pass — collect, across ALL python files:
- `used_names: set[str]` = every `ParsedReference.name` plus every
  `ParsedImport.name` that is not `None` (a name imported elsewhere counts as
  "used"). Also add any name appearing in a `__all__` assignment (parse the AST
  for a module-level `__all__` list of string constants).

Second pass — for each file, examine **module-level** symbols only
(`kind in {"function", "async_function", "class"}` whose `qualified_name` has no
intervening class/function beyond the module — detect by checking the symbol is
not nested; the simplest reliable proxy: only consider symbols whose
`qualified_name` equals `module + "." + name`).

A symbol is a **dead-code candidate** when ALL hold:
- its `name` is NOT in `used_names`;
- `name` does not start with `_` is NOT required (unused private is still a
  candidate) — but DO exclude dunder names (`__init__`, `__main__`, etc.);
- the file is not a test file (`parsed.is_test` is `False`);
- the symbol is not a known entrypoint name: exclude `main`, `app`, `cli`,
  `run`, and any name referenced from a `[project.scripts]`/`[project.entry-points]`
  — for this plan, just exclude the fixed set `{"main", "app", "run"}` and note
  the entry-points refinement as future work.

### Step 2: Emit findings with honest confidence

```python
build_finding(
    FindingSpec(
        rule_id="python.dead_code_candidate",
        title="Possibly unused symbol",
        message=f"{symbol.qualified_name} is defined but never referenced in the indexed sources.",
        file_path=parsed.path,
        symbol=symbol.qualified_name,
        severity="info",
        confidence=0.6,
        evidence={"symbol": symbol.name, "kind": symbol.kind, "start_line": symbol.start_line},
        suggested_action="Confirm it is unused (including dynamic/CLI/test usage) before removing.",
    ),
)
```

### Step 3: Wire it into the scan

Add `scan_dead_code` to the python pack. Simplest integration that matches the
codebase: call it inside `scan_python_health` and extend the returned findings
(like `secondary_findings` is already composed at
`engine/rules/python.py:49`), OR add it as a separate rule pack in
`packs.py`. Prefer composing inside `scan_python_health` so it shares the single
inventory pass. **Read `engine/rules/python_patterns.py` `secondary_findings`
first to copy the exact composition style.**

**Verify**: `uv run pytest tests -k dead_code` → exit 0 after Step 4.

### Step 4: Tests

- Temp repo: `a.py` defines `used_fn` (called from `b.py`) and `orphan_fn`
  (never referenced). Assert exactly one `python.dead_code_candidate` for
  `orphan_fn` and none for `used_fn`.
- Assert `main`/`app`/`run` and dunders are never flagged.
- Assert names listed in `__all__` are not flagged.
- Assert symbols used only in a test file ARE still counted as used (references
  from tests count).

**Verify**: `uv run pytest`, `ruff check .`, `ruff format --check .`,
`basedpyright` → all exit 0.

## Test plan

- Orphan detected; used symbol not flagged; entrypoints/dunders/`__all__`
  excluded; confidence is 0.6 (not high).
- Verification: `uv run pytest` → all pass.

## Done criteria

- [ ] `python.dead_code_candidate` findings appear for genuinely unreferenced
      module-level symbols, with confidence 0.6.
- [ ] Entrypoints (`main`/`app`/`run`), dunders, `__all__` exports, and
      test-referenced symbols are never flagged.
- [ ] `uv run pytest`, `ruff check`, `ruff format --check`, `basedpyright` exit 0.
- [ ] No analyzed source edited; `tests/fixtures/` untouched.
- [ ] `plans/README.md` status row for 009 updated.

## STOP conditions

Stop and report if:
- The name-use heuristic produces obvious false positives on this repo's own
  source (run a scan against `tests/fixtures/python-basic` and eyeball) — report
  the false-positive shape rather than shipping a noisy rule.
- Determining "module-level only" from `qualified_name` is unreliable for the
  parser's naming scheme — report and propose adding a `is_module_level` flag to
  `ParsedSymbol` as a separate plan.
- Verification fails twice after a reasonable fix.

## Maintenance notes

- This is intentionally name-based (not full resolution), so confidence is
  capped at 0.6. Do not raise it without real reference resolution.
- A future plan can promote confidence by using the persisted `symbol_references`
  / `call_edges` tables (schema migration 3) for resolved references.
- Reviewers should check the exclusion list prevents flagging public API and
  CLI/MCP entrypoints.
