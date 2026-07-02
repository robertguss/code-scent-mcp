# Plan 004: Stop one bad file from aborting the whole index/scan

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving on. If a
> "STOP condition" occurs, stop and report — do not improvise. When done,
> update the status row in `plans/README.md`.
>
> **Drift check (run first)**:
> `git diff --stat 5dca8d5..HEAD -- src/codescent/engine/source_read.py src/codescent/engine/parsers/python.py src/codescent/services/repo_index.py`
> If any changed, compare the "Current state" excerpts to the live code before
> proceeding; on a mismatch, STOP.

## Status

- **Priority**: P1
- **Effort**: S–M
- **Risk**: LOW
- **Depends on**: none (verifies more cleanly if plan 001 has greened the suite, but is independent)
- **Category**: bug / security
- **Planned at**: commit `5dca8d5`, 2026-07-02

## Why this matters

CodeScent's core function — index a repo, then scan it for findings — aborts
**entirely and persistently** when it meets a single file it can't read or
parse cleanly. Three independent failure modes all have the same root cause
(the per-file read/parse path has no error isolation):

1. **Non-UTF-8 bytes.** `read_source_text` calls bare `path.read_text()`, which
   decodes with the platform locale and raises `UnicodeDecodeError` on a
   Latin-1 accented comment, a Windows-1252 smart quote, or a PEP-263 non-UTF-8
   module. `parse_python_file` reads the same way and catches only
   `SyntaxError`.
2. **TOCTOU.** The inventory walk lists files, then reads them; a file deleted,
   truncated, or replaced in between (a concurrent editor save, `git checkout`,
   a build tool — exactly the concurrent workflow the tool targets) raises
   `OSError` from the unguarded `stat`/`read_bytes`.
3. **Pathological AST.** A deeply nested expression makes `ast.parse` or the
   recursive visitor raise `RecursionError`/`ValueError`, neither caught by
   `except SyntaxError`.

Any one of these propagates out of `index_repo` (aborting the write
transaction) and out of the health scan. One bad byte in one file breaks the
whole tool, on every run. The Go and generic packs already read defensively
(`content.decode("utf-8", errors="replace")`); this plan brings the Python/TS
read+parse path and the index loop up to the same standard, plus a backstop so
*any* future per-file failure skips that file instead of the repo.

## Current state

**The read primitives** (`src/codescent/engine/source_read.py:33-56`) — both
`stat`/`read` calls are unguarded, and `read_text()` has no `encoding`/`errors`:

```python
def read_source_bytes(path: Path, *, max_bytes: int = MAX_SOURCE_BYTES) -> SourceBytes:
    size_bytes = path.stat().st_size                 # <-- OSError on TOCTOU delete
    if size_bytes > max_bytes:
        return SourceBytes(content=None, size_bytes=size_bytes, oversized=True)
    return SourceBytes(content=path.read_bytes(), size_bytes=size_bytes, oversized=False)  # <-- OSError

def read_source_text(path: Path, *, max_bytes: int = MAX_SOURCE_BYTES) -> SourceText:
    size_bytes = path.stat().st_size                 # <-- OSError
    if size_bytes > max_bytes:
        return SourceText(text=None, size_bytes=size_bytes, oversized=True)
    return SourceText(text=path.read_text(), size_bytes=size_bytes, oversized=False)  # <-- UnicodeDecodeError + OSError
```

`content=None` / `text=None` is the **existing sentinel** every caller already
handles as "skip this file" (e.g. `inventory.py:109-111` does `if content is
None: continue`). So the fix returns that sentinel on failure rather than
raising.

**The exemplar to match** (`src/codescent/engine/packs_generic.py:65-70`) —
this is the defensive pattern already in the tree:

```python
source = read_source_bytes(repo_root / relative)
content = source.content
if content is None or b"\x00" in content:
    continue
text = content.decode("utf-8", errors="replace")
```

**The Python parser** (`src/codescent/engine/parsers/python.py:118-142`) reads
directly and catches only `SyntaxError`; the recursive `visitor.visit(tree)` is
outside the `try`:

```python
def parse_python_file(path: Path | str, relative_path: str) -> ParsedPythonFile:
    source_path = Path(path)
    module = _module_name(relative_path)
    try:
        tree = ast.parse(source_path.read_text(), filename=relative_path)  # <-- UnicodeDecodeError / ValueError
    except SyntaxError as error:
        return ParsedPythonFile(..., parse_error=_syntax_error_message(error))
    visitor = _PythonParser(module=module)
    visitor.visit(tree)                                                    # <-- RecursionError on deep AST
    return ParsedPythonFile(...)
```

`ParsedPythonFile` already carries a `parse_error: str | None` field and a
`_syntax_error_message` helper — the "record a parse error and move on" path
exists; it just isn't reached for non-`SyntaxError` failures.

**The index loop** (`src/codescent/services/repo_index.py:121-156`, abbreviated)
calls the parser per file inside the write transaction with no per-file guard;
a raise there rolls back the whole index:

```python
with RepositoryStorage(state).write_transaction() as connection:
    ...
    for item in to_index:
        cursor = connection.execute("insert into files ( ...", ...)
        ...
        parsed = parser(state.repo_root / item.path, item.path)   # <-- any raise aborts the whole index
        ...
```

(Read the real loop; the exact variable names and the parser dispatch are what
you wrap in Step 3.)

Repo conventions: frozen dataclasses for value objects; `content=None`/
`text=None` is the established "unreadable/oversized → skip" sentinel; the Go
parser (`src/codescent/engine/parsers/go.py:49-61`) already wraps its read in
`except (OSError, UnicodeDecodeError)` — match that spirit.

## Commands you will need

| Purpose | Command | Expected |
|---|---|---|
| Install | `uv sync` | exit 0 |
| Targeted tests | `uv run pytest tests/integration/test_repo_index.py tests/unit -q` | pass |
| New robustness test | `uv run pytest tests/integration/test_index_robustness.py -q` | pass (after Step 4) |
| Full suite | `uv run pytest` | no new failures |
| Lint | `uv run ruff check .` | `All checks passed!` |
| Typecheck | `uv run basedpyright` | no new errors |

## Scope

**In scope**:

- `src/codescent/engine/source_read.py` (harden `read_source_bytes`, `read_source_text`)
- `src/codescent/engine/parsers/python.py` (broaden parse guards)
- `src/codescent/engine/packs_ts.py` (the TS read at line ~48 — same encoding hardening; read it first)
- `src/codescent/services/repo_index.py` (per-file backstop `try/except`)
- `tests/integration/test_index_robustness.py` (create)
- A tiny non-UTF-8 fixture file if the test needs one on disk (create under a
  `tmp_path`, not under `tests/fixtures/` — keep it in-test).

**Out of scope**:

- `src/codescent/engine/inventory.py`'s `rglob`-vs-prune performance issue —
  that is a separate perf plan; here you only make its read (via the hardened
  `read_source_bytes`) not raise.
- Changing the `parse_error` message format or the `ParsedPythonFile` schema
  beyond reaching the existing `parse_error` path for new exception types.
- `MemoryError` handling / an AST-nesting cap — catching `MemoryError`
  reliably needs a size bound; note it as a follow-up, do not attempt it here.
- The `is_test` predicate divergence (separate finding) — do not touch
  `_is_test_path`.

## Git workflow

- Branch off `main`: `git switch -c advisor/004-per-file-failure-isolation`.
- Commit: `fix(engine): isolate per-file read/parse failures so one bad file cannot abort indexing`.
- Do NOT push or open a PR.

## Steps

### Step 1: Harden `read_source_bytes` and `read_source_text`

In `source_read.py`, make both functions return the existing `None`-content
sentinel on `OSError`, and decode text as UTF-8 with replacement:

- `read_source_bytes`: wrap the `path.stat()` + `path.read_bytes()` in
  `try/except OSError`; on error return `SourceBytes(content=None,
  size_bytes=0, oversized=False)`.
- `read_source_text`: implement it by calling the now-hardened
  `read_source_bytes` and decoding: if `content is None` return
  `SourceText(text=None, size_bytes=..., oversized=...)` preserving the
  `oversized` flag; else `text = content.decode("utf-8", errors="replace")`.
  This single-sources the OSError handling and matches
  `packs_generic.py:70` exactly.

Keep `read_source_lines` as-is — it already builds on `read_source_text`.

**Verify**: `uv run pytest tests/unit -q -k "source_read or source or read"` →
pass (or "no tests ran" if none target it directly; the robustness test in
Step 4 will exercise it). `uv run basedpyright src/codescent/engine/source_read.py`
→ no errors.

### Step 2: Broaden the Python parser's guards

In `parse_python_file`:

- Change the read to `source_path.read_text(encoding="utf-8", errors="replace")`
  (or read via `read_source_bytes` + decode, matching Step 1 — either is fine as
  long as non-UTF-8 no longer raises).
- Broaden the parse `except SyntaxError` to also catch `ValueError` (raised for
  e.g. source containing null bytes) and return the `parse_error` record.
- Protect the recursive walk: wrap `visitor.visit(tree)` so a `RecursionError`
  returns a `parse_error` record too, e.g.:

  ```python
  try:
      visitor.visit(tree)
  except RecursionError:
      return ParsedPythonFile(
          path=relative_path, module=module,
          is_test=_is_test_path(relative_path),
          symbols=(), imports=(), references=(),
          parse_error="ast too deeply nested to analyze",
      )
  ```

Keep the existing `SyntaxError` branch and its `_syntax_error_message`.

**Verify**: `uv run pytest tests/integration/test_repo_index.py -q` → pass
(existing behavior for valid files unchanged).

### Step 3: Repeat the encoding hardening for the TS reader, then add the index backstop

Read `src/codescent/engine/packs_ts.py` around line 48. If it does
`Path(path).read_text().splitlines()` unguarded, route it through
`read_source_lines`/`read_source_text` (now hardened) or add
`encoding="utf-8", errors="replace"` and a `content is None` skip. Do not
change what it detects — only how it reads.

Then in `src/codescent/services/repo_index.py`, wrap the per-file parse call in
the indexing loop so a failure skips that one file:

```python
try:
    parsed = parser(state.repo_root / item.path, item.path)
except Exception:  # noqa: BLE001 — one malformed file must not abort the index
    continue
```

Place the `try` around the parse + that file's graph inserts so a half-inserted
file is not left behind (read the loop to see where the symbol/import/reference
inserts happen and include them). If ruff's `BLE001` (blind-except) is
configured as an error, keep the `# noqa: BLE001` with the explanatory comment —
a deliberate catch-all backstop is the correct design here (mirror the
`contextlib.suppress(Exception)` already used on the `hook-reindex` path).

**Verify**: `uv run ruff check src/codescent/services/repo_index.py` → passes
(with the `# noqa` if needed). `uv run pytest tests/integration/test_repo_index.py -q` → pass.

### Step 4: Add a robustness test

Create `tests/integration/test_index_robustness.py`, modeled structurally on
`tests/integration/test_repo_index.py` (read it for the `initialize_storage` /
index / scan setup pattern). Cover:

- **Non-UTF-8 file does not abort indexing**: in a `tmp_path` repo, write a
  valid `good.py` plus a `bad.py` whose bytes are invalid UTF-8 (e.g.
  `(repo / "bad.py").write_bytes(b"# comment \xff\xfe caf\xe9\nx = 1\n")`).
  Index the repo; assert it completes and `good.py` is indexed (the run does not
  raise; `bad.py` is either indexed with a `parse_error` or skipped, but the
  operation succeeds).
- **Scan over the same repo completes**: run the health scan on that repo and
  assert it returns (does not raise).
- **Deleted-mid-walk is tolerated** (optional, if cheaply expressible): call
  `read_source_bytes` on a path that does not exist and assert it returns
  `content=None` rather than raising.
- **Deeply nested source does not abort**: write a file with a deeply nested
  expression (e.g. `"(" * 200 + "1" + ")" * 200`) and assert indexing
  completes. (If this doesn't trigger `RecursionError` on the CI Python, the
  test still passes — it's a regression guard, not a hard requirement to raise.)

**Verify**: `uv run pytest tests/integration/test_index_robustness.py -q` →
all new tests pass.

### Step 5: Full green

**Verify**:
- `uv run pytest` → no new failures vs. the pre-plan baseline.
- `uv run ruff check .` and `uv run ruff format --check .` → pass.
- `uv run basedpyright` → no new errors.

## Test plan

- New file `tests/integration/test_index_robustness.py` with the cases in Step
  4 (non-UTF-8 does not abort, scan completes, missing-path read returns the
  sentinel, deep-nesting does not abort). Model after
  `tests/integration/test_repo_index.py`.
- These are true regression tests: on the unpatched code the non-UTF-8 case
  raises `UnicodeDecodeError` and fails; after the fix it passes.
- Verification: `uv run pytest tests/integration/test_index_robustness.py -q` →
  all pass; full `uv run pytest` → no new failures.

## Done criteria

ALL must hold:

- [ ] `read_source_bytes` and `read_source_text` return the `None`-content
      sentinel (never raise) on `OSError`; text decodes UTF-8 with `errors="replace"`.
      `grep -n 'errors="replace"' src/codescent/engine/source_read.py` → matches.
- [ ] `parse_python_file` no longer raises on non-UTF-8, null-byte, or
      deeply-nested input (covered by the new test).
- [ ] The index loop in `repo_index.py` isolates a per-file parse failure
      (backstop `try/except` present around the per-file work).
- [ ] `tests/integration/test_index_robustness.py` exists and passes.
- [ ] `uv run pytest` has no new failures; `ruff` and `basedpyright` clean.
- [ ] No files outside the in-scope list modified.
- [ ] `plans/README.md` status row for 004 updated.

## STOP conditions

Stop and report if:

- Making `read_source_text` decode as UTF-8 changes newline handling in a way
  that breaks an existing test (e.g. a test asserting exact `\r\n` content) —
  report the failing test; the fix may need to preserve `read_text()`'s
  universal-newline translation.
- The index loop's structure differs materially from the excerpt (e.g. parsing
  happens outside the transaction, or in a helper) — wrap the real call site and
  note the difference, but if it's unclear where the backstop belongs, STOP.
- The scan path (`services/code_health.py`) still raises on the non-UTF-8
  fixture after Steps 1–3 (a rule reads source through a path this plan didn't
  harden) — report which reader, do not blindly wrap every rule.

## Maintenance notes

- The hardened `read_source_*` primitives are now the single choke point for
  "unreadable/undecodable → skip"; future readers should go through them, not
  call `path.read_text()` directly. A reviewer should reject new bare
  `read_text()` calls in `engine/`.
- Deferred follow-ups (out of scope, worth a future plan): a `MemoryError`
  guard with an explicit file-size/AST-node bound; unifying the divergent
  `is_test` predicates; and pruning excluded directories during the walk (perf).
- The `# noqa: BLE001` backstop is intentional defense-in-depth — do not
  "tighten" it to a specific exception later without keeping a catch-all,
  because its whole purpose is to survive an *unanticipated* per-file failure.
