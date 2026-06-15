# Plan 010: Detect structural near-duplicate functions (AI-slop signal)

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving on. If a
> STOP condition occurs, stop and report — do not improvise. When done, update
> the status row for this plan in `plans/README.md`.
>
> **Drift check (run first)**:
> `git diff --stat 40cbf50..HEAD -- src/codescent/engine/rules tests plans/README.md`
> If any in-scope file changed, compare excerpts against live code; on a
> mismatch, treat it as a STOP condition.

## Status

- **Priority**: P1
- **Effort**: M
- **Risk**: MED
- **Depends on**: none
- **Category**: direction (new deterministic rule; core product thesis)
- **Planned at**: commit `40cbf50`, 2026-06-15

## Why this matters

"AI slop" is CodeScent's headline thesis, yet today the duplicate detection only
catches repeated _string literals_ (`python.duplicate_literal`). The disease AI
agents actually cause is **copy-paste-and-rename**: two or more functions with
the same structure under different names. Detecting type-2/3 clones via an
AST-normalized, rename-invariant fingerprint is deterministic, local, and
directly differentiating — no linter does "you wrote this function three times."

## Current state

- The literal-duplication rule shows the existing AST + finding pattern:

```python
# src/codescent/engine/rules/python.py:154-185
def _duplicate_literals(parsed, source_path):
    try:
        tree = ast.parse(source_path.read_text(), filename=parsed.path)
    except SyntaxError:
        return ()
    literals = Counter(... ast.walk(tree) ...)
    return tuple(build_finding(FindingSpec(rule_id="python.duplicate_literal", ...)) ...)
```

- `scan_python_health` (`engine/rules/python.py:31-50`) iterates the inventory
  once, parses each file, and composes rule outputs (including
  `secondary_findings(...)` from `engine/rules/python_patterns.py`). **Read
  `python_patterns.py` first** to match the composition style.

- `FindingSpec.evidence` values must be scalar (`int|float|str|bool`) — see
  `engine/rules/model.py:6`. `ParsedSymbol` carries `qualified_name`,
  `start_line`, `end_line`, `kind`.

Repo conventions: strict typing; deterministic-first; bounded output; no
network; never edit analyzed source.

## Commands you will need

| Purpose       | Command                                                          | Expected |
| ------------- | ---------------------------------------------------------------- | -------- |
| Focused tests | `uv run pytest tests -k "near_duplicate or clone or structural"` | exit 0   |
| Full tests    | `uv run pytest`                                                  | exit 0   |
| Lint          | `uv run ruff check .`                                            | exit 0   |
| Format        | `uv run ruff format --check .`                                   | exit 0   |
| Typecheck     | `uv run basedpyright`                                            | exit 0   |

## Scope

**In scope**:

- `src/codescent/engine/rules/structural_dup.py` (create) — the fingerprint +
  near-duplicate scan, operating across all python files.
- `src/codescent/engine/rules/python.py` — compose the new scan into
  `scan_python_health` (project-level, after the per-file loop).
- `tests/unit/` and/or `tests/integration/` — tests.
- `plans/README.md` status row.

**Out of scope**:

- Do NOT touch `_duplicate_literals` (different rule, keep it).
- Do NOT attempt cross-language clone detection (Python only).
- Do NOT auto-extract or edit source.
- No semantic/embedding similarity — structural hashing only (deterministic).
- `tests/fixtures/` source.

## Steps

### Step 1: Build a rename-invariant structural fingerprint

In `src/codescent/engine/rules/structural_dup.py`, implement a function that,
for a given function/method AST node, produces a canonical token sequence that
is invariant to identifier names and literal values but sensitive to
control-flow structure:

```python
MIN_FUNCTION_NODES: Final = 12  # skip trivial functions

def _structure_fingerprint(node: ast.AST) -> str:
    """Stable hash of a node's AST shape, ignoring names/literals."""
    tokens: list[str] = []
    for child in ast.walk(node):
        name = type(child).__name__
        if isinstance(child, ast.Name):
            tokens.append("Name")          # normalize identifier
        elif isinstance(child, ast.Constant):
            tokens.append(f"Const:{type(child.value).__name__}")  # keep type, drop value
        elif isinstance(child, (ast.arg,)):
            tokens.append("arg")
        else:
            tokens.append(name)
    return hashlib.sha256("|".join(tokens).encode()).hexdigest()[:16]
```

- Skip functions whose walked-node count `< MIN_FUNCTION_NODES` (too trivial to
  be meaningful duplicates — avoids flagging one-line getters).

### Step 2: Group functions by fingerprint across the repo

`scan_structural_duplicates(root, *, config=None) -> tuple[CodeHealthFinding, ...]`:

- Iterate inventory; `ast.parse` each python file (guard `SyntaxError` → skip).
- For each top-level and nested `FunctionDef`/`AsyncFunctionDef`, compute the
  fingerprint and record
  `(fingerprint -> list of (path, qualified-ish name, lineno))`. Use the node's
  `name` and `lineno`; qualified name can be `f"{module}.{name}"` approximated
  from the relative path, or just `name` — keep it informative.
- A fingerprint group with `>= 2` distinct `(path, lineno)` members is a clone
  cluster.

### Step 3: Emit ONE finding per cluster (bounded)

Emit a single finding for each cluster, anchored to the first member's file:

```python
build_finding(
    FindingSpec(
        rule_id="python.structural_near_duplicate",
        title="Structurally duplicated function",
        message=f"{count} functions share the same structure (rename-invariant).",
        file_path=first_path,
        symbol=first_name,
        severity="warning",
        confidence=0.7,
        evidence={
            "occurrences": count,
            "fingerprint": fingerprint,
            "locations": locations_str,  # e.g. "a.py:10, b.py:40" (scalar str)
        },
        suggested_action="Extract a shared helper or parameterize the duplicated logic.",
    ),
)
```

- `locations_str` must be a single string (evidence values are scalar). Cap the
  listed locations to e.g. 5 with a trailing "(+N more)".

### Step 4: Compose into the scan

In `engine/rules/python.py`, call
`scan_structural_duplicates(repo_root, config=...)` once (it does its own
inventory pass, OR refactor to accept the already-parsed files — prefer the
simplest correct version: its own pass) and extend the returned findings tuple.
Keep it after the per-file loop in `scan_python_health`.

**Verify**: `uv run pytest tests -k near_duplicate` → exit 0 after Step 5.

### Step 5: Tests

- Temp repo with `a.py` and `b.py` each containing a non-trivial function with
  identical structure but different names/variables/strings. Assert exactly one
  `python.structural_near_duplicate` finding with `occurrences == 2`.
- Assert two _structurally different_ functions produce no finding.
- Assert a trivial one-liner duplicated twice is NOT flagged (below
  `MIN_FUNCTION_NODES`).

**Verify**: `uv run pytest`, `ruff check .`, `ruff format --check .`,
`basedpyright` → all exit 0.

## Test plan

- Clone cluster detected with correct count and locations string.
- Different structures → no finding. Trivial functions → no finding.
- Verification: `uv run pytest` → all pass.

## Done criteria

- [ ] `python.structural_near_duplicate` fires for rename-invariant duplicates
      and not for distinct or trivial functions.
- [ ] One finding per cluster; `locations` is a single bounded string.
- [ ] `uv run pytest`, `ruff check`, `ruff format --check`, `basedpyright`
      exit 0.
- [ ] No analyzed source edited; `tests/fixtures/` untouched.
- [ ] `plans/README.md` status row for 010 updated.

## STOP conditions

Stop and report if:

- Running against `tests/fixtures/python-basic` floods findings (the
  `MIN_FUNCTION_NODES` threshold is too low) — report the count and tune the
  threshold before shipping.
- The fingerprint collides for clearly-different functions in the fixture repo —
  report examples; the normalization is too aggressive.
- Verification fails twice after a reasonable fix.

## Maintenance notes

- Tune `MIN_FUNCTION_NODES` against real repos; too low = noise, too high =
  misses. Document the chosen value with a comment explaining the trade-off.
- A future plan can add a per-file "slop score" aggregating this rule with
  comment-narration and over-defensive-try/except detectors.
- Reviewers should confirm output is bounded (one finding per cluster, capped
  locations) so a heavily-duplicated repo cannot flood context.
