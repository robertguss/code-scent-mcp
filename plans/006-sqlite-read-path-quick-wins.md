# Plan 006: SQLite read-path quick wins — direct id lookup, WAL, pragmas

> **Executor instructions**: Follow this plan step by step. Confirm each
> verification before moving on. Honor "STOP conditions". When done, update the
> status row in `plans/README.md`.
>
> **Drift check (run first)**:
> `git diff --stat 5dca8d5..HEAD -- src/codescent/storage/repository.py src/codescent/storage/repositories/findings.py`
> If either changed, re-read and compare against "Current state"; on a mismatch, STOP.

## Status

- **Priority**: P2
- **Effort**: S–M
- **Risk**: LOW–MED (WAL changes on-disk journaling — see STOP conditions)
- **Depends on**: none
- **Category**: perf
- **Planned at**: commit `5dca8d5`, 2026-07-02

## Why this matters

Three isolated, high-confidence inefficiencies on the storage read path. On the
live target the index reported ~25,690 findings across 719 files, so "load
everything to answer one question" is a real cost:

1. **`get_finding` loads *all* findings to return one row.** It calls
   `list_findings()` (a full `findings ⋈ files` scan, ordered, plus a full
   `finding_events` scan) then linearly scans in Python for one id. It runs
   after **every** `mark_finding` (via `update_status`) and on every not-found
   error path — so marking one finding is O(all findings + all events).
2. **No performance pragmas.** `_connect` sets only `foreign_keys` and
   `busy_timeout`; there is no `journal_mode=WAL`, `synchronous=NORMAL`, or
   cache sizing. Large index/scan commits fsync under full durability, and every
   per-operation read connection starts with a cold 2 MB page cache against a DB
   holding tens of thousands of rows.
3. **Inconsistent read-error handling.** `write_transaction` maps
   `sqlite3.OperationalError` → a structured, recoverable `CONCURRENT_WRITE`
   error; `read_connection` wraps nothing, and some read repos catch
   `DatabaseError` while others don't — so under contention the same "database
   is locked" is a clean empty result on one surface and a raw unhandled error
   on another. Enabling WAL (fix 2) removes most reader-blocks-on-writer cases;
   a small read-side guard covers the rest.

## Current state

**`get_finding`** (`storage/repositories/findings.py:153-158`):

```python
    def get_finding(self, finding_id: str) -> FindingRow:
        findings = self.list_findings()          # <-- full table scan + full events scan
        for finding in findings:                 # <-- linear Python scan for one id
            if finding.id == finding_id:
                return finding
        raise _finding_not_found(finding_id, findings)
```

`list_findings` (`:58-116`) selects all findings joined to files, ordered, and
calls `_events_by_finding()` (`:230-238`) which is `select finding_id,
event_type, created_at, details_json from finding_events order by created_at`
— **no `WHERE`**, scanning and filesorting every event row on each call.
`_finding_not_found` (`:251-268`) already builds a bounded id-sample recovery
payload and only needs the id list for the sample.

**`_connect`** (`storage/repository.py:160-164`):

```python
def _connect(database_path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(database_path, timeout=5.0)
    _ = connection.execute("pragma foreign_keys = on")
    _ = connection.execute("pragma busy_timeout = 5000")
    return connection
```

**Read vs write error handling** (`storage/repository.py:64-90`):
`write_transaction` catches `sqlite3.OperationalError` → `_concurrent_write_error`
(recoverable); `read_connection` has no such mapping.

Conventions: repositories are frozen dataclasses wrapping `RepositoryStorage`;
reads go through `with self.storage.read_connection() as connection:`; the repo
already has a `has_passing_verification` method (`:217-228`) showing the
`select … where finding_id = ? limit 1` single-row query pattern to copy.
`initialize_storage` runs `pragma quick_check` after migrate, so pragmas must
not break that.

## Commands you will need

| Purpose | Command | Expected |
|---|---|---|
| Install | `uv sync` | exit 0 |
| Storage tests | `uv run pytest tests/integration/test_storage_concurrency.py tests/integration/test_storage_migrations.py -q` | pass |
| Findings tests | `uv run pytest tests/contract/test_mcp_finding_tools.py tests/unit -q -k finding` | pass |
| Full suite | `uv run pytest` | no new failures |
| Lint / types | `uv run ruff check . && uv run basedpyright` | clean |

## Scope

**In scope**:

- `src/codescent/storage/repository.py` (`_connect` pragmas; `read_connection` guard)
- `src/codescent/storage/repositories/findings.py` (`get_finding` → direct query)
- `tests/integration/test_storage_pragmas.py` (create) or extend
  `test_storage_migrations.py`
- `tests/` finding-repository test (extend existing)

**Out of scope**:

- The no-op-rescan re-persist (PERF-04), indexing `executemany` (PERF-10),
  `resume_task` N+1 (PERF-08), dashboard pagination (PERF-09) — separate
  findings, not this plan.
- Adding an index on `finding_events(created_at)` — not needed once `get_finding`
  stops calling `_events_by_finding`; only add one if a benchmark shows
  `list_findings` itself is the bottleneck (it isn't the target here).
- Changing `list_findings`'s shape or `FindingRow` — callers depend on it.
- `codescent reset` behavior — but see STOP conditions re: WAL sidecar files.

## Git workflow

- Branch off `main`: `git switch -c advisor/006-sqlite-read-path-quick-wins`.
- Suggested commits: `perf(storage): direct id lookup for get_finding` and
  `perf(storage): enable WAL + read pragmas`.
- Do NOT push or open a PR.

## Steps

### Step 1: Replace `get_finding`'s full-scan with a direct query

Add a method that fetches one finding by id and only that finding's events,
copying the join/column list from `list_findings` but adding `where findings.id
= ?`, plus a scoped events query `select event_type, created_at, details_json
from finding_events where finding_id = ? order by created_at`. Build the
`FindingRow` the same way `list_findings` does (same column order and
`FindingEventRow` construction). Then rewrite `get_finding`:

```python
    def get_finding(self, finding_id: str) -> FindingRow:
        row = self._get_by_id(finding_id)
        if row is not None:
            return row
        raise _finding_not_found(finding_id, self._id_sample())
```

Where `_id_sample()` returns just a bounded list for the recovery payload —
either add a cheap `select id from findings limit ?` (respecting
`_ID_SAMPLE_LIMIT`), or keep passing `self.list_findings()` **only on the
not-found path** (rare) if you want the smallest diff. Prefer the bounded
`select id … limit` so even the error path is cheap. Note `_finding_not_found`
takes `tuple[FindingRow, ...]` today and uses `finding.id` and `len(findings)`;
if you switch to an id-only sample, adjust `_finding_not_found` to accept ids
directly (it only reads `.id` and the count) — keep the payload shape
identical (`available_options`, `total_findings`, `fix_hint`).

**Verify**:
- `uv run pytest tests/contract/test_mcp_finding_tools.py -q` → pass (mark/get
  behavior unchanged).
- A bad id still returns the structured NOT_FOUND envelope with a bounded
  `available_options` sample (covered by existing error-contract tests; run
  `uv run pytest tests/contract/test_mcp_error_contract.py -q`).

### Step 2: Add performance pragmas to `_connect`

Extend `_connect`:

```python
def _connect(database_path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(database_path, timeout=5.0)
    _ = connection.execute("pragma foreign_keys = on")
    _ = connection.execute("pragma busy_timeout = 5000")
    _ = connection.execute("pragma journal_mode = wal")
    _ = connection.execute("pragma synchronous = normal")
    _ = connection.execute("pragma cache_size = -8000")  # ~8 MB page cache
    _ = connection.execute("pragma temp_store = memory")
    return connection
```

`journal_mode=WAL` is persisted on the database file (set once, sticks); setting
it every connect is idempotent and cheap. `synchronous=NORMAL` is the standard,
safe durability trade under WAL. Do **not** add `mmap_size` unless a benchmark
justifies it (it can complicate some filesystems).

**Verify**:
- `uv run codescent init --repo tests/fixtures/python-basic` then
  `uv run codescent scan --repo tests/fixtures/python-basic --json` → exit 0,
  and `ls tests/fixtures/python-basic/.codescent/` shows `index.sqlite` plus
  `index.sqlite-wal` / `index.sqlite-shm` sidecars (WAL is active).
- `uv run pytest tests/integration/test_storage_migrations.py tests/integration/test_storage_concurrency.py -q` → pass (the `pragma quick_check` in `initialize_storage` still succeeds).

### Step 3: Give `read_connection` a consistent error mapping

In `read_connection`, map a lock error to the same structured, recoverable
error the write path uses, so no read surface leaks a raw `sqlite3` error:

```python
    @contextmanager
    def read_connection(self):
        self._claim_reader()
        connection = _connect(self.state.database_path)
        try:
            yield connection
        except sqlite3.OperationalError as exc:
            raise _concurrent_write_error(self.state.database_path) from exc
        finally:
            connection.close()
            self._release_reader()
```

(WAL from Step 2 removes most reader-blocks-on-writer; this covers the residual
`SQLITE_BUSY`.) If `_concurrent_write_error`'s message reads oddly for a read,
add a sibling `_locked_read_error` with a read-appropriate message but the same
`recoverable=True` shape — keep it recoverable.

**Verify**: `uv run pytest tests/integration/test_storage_concurrency.py -q` →
pass. The existing single-writer/blocked-reader test must still pass.

### Step 4: Tests

Create `tests/integration/test_storage_pragmas.py` (or extend
`test_storage_migrations.py`):

- **WAL is on**: after `initialize_storage(tmp_repo)`, open a read connection
  and assert `connection.execute("pragma journal_mode").fetchone()[0] == "wal"`.
- **`get_finding` correctness**: seed a repo with findings (reuse the setup in
  `tests/contract/test_mcp_finding_tools.py` or the findings-repo tests), then
  assert `get_finding(known_id)` returns the right row with its events, and an
  unknown id raises the NOT_FOUND `CodeScentError` with a bounded
  `available_options` sample.

**Verify**: `uv run pytest tests/integration/test_storage_pragmas.py -q` → pass.

### Step 5: Full green

**Verify**:
- `uv run pytest` → no new failures.
- `uv run ruff check .` / `uv run ruff format --check .` / `uv run basedpyright`
  → clean.

## Test plan

- `tests/integration/test_storage_pragmas.py`: WAL-is-on assertion + `get_finding`
  correctness (hit and miss). Model after `test_storage_migrations.py` /
  `test_storage_concurrency.py` for the `initialize_storage`/`tmp_path` setup.
- The `get_finding` change is behavior-preserving, so existing finding/mark
  tests are the regression guard; run them explicitly.
- Verification: `uv run pytest tests/integration/test_storage_pragmas.py tests/contract/test_mcp_finding_tools.py -q` → all pass.

## Done criteria

ALL must hold:

- [ ] `get_finding` no longer calls `list_findings()` on the success path
      (`grep -n "def get_finding" -A6 src/codescent/storage/repositories/findings.py`
      shows a direct id query, not a loop over `list_findings()`).
- [ ] `_connect` sets `journal_mode = wal` and `synchronous = normal`; a live
      init produces `index.sqlite-wal`.
- [ ] `read_connection` maps `sqlite3.OperationalError` to a recoverable
      structured error.
- [ ] `tests/integration/test_storage_pragmas.py` exists and passes.
- [ ] `uv run pytest` no new failures; lint + types clean.
- [ ] No files outside scope modified.
- [ ] `plans/README.md` status row for 006 updated.

## STOP conditions

Stop and report if:

- Enabling WAL breaks an existing test — most likely a test that asserts on the
  exact set of files under `.codescent/` (now includes `-wal`/`-shm`), or the
  `state_path` containment check / `codescent reset` cleanup that does not
  expect sidecar files. Report the failing test; the fix is to teach that
  code about the sidecars, but that may widen scope — get confirmation.
- `pragma quick_check` in `initialize_storage` starts failing after the pragma
  change (should not happen; if it does, a pragma is malformed).
- The `_finding_not_found` signature change ripples into callers you can't see —
  keep the returned payload shape byte-identical and, if unsure, retain the
  `tuple[FindingRow, ...]` signature and just avoid calling it on the hot path.

## Maintenance notes

- WAL adds `index.sqlite-wal` and `index.sqlite-shm` next to the DB. Anything
  that enumerates, copies, or deletes `.codescent` state (reset, backup,
  containment assertions) should treat those as part of the database. Flag this
  for the reviewer.
- The process-local reader/writer lock is unchanged; WAL only improves
  cross-process read-during-write behavior. True cross-process concurrency
  testing is a separate coverage gap (not this plan).
- If `list_findings`/`_events_by_finding` later shows up as a real bottleneck on
  a large repo, the next step is scoping `_events_by_finding` to the returned
  finding set (accept an optional `finding_ids` filter) — deliberately deferred
  here because Step 1 already removes the hot-path caller.
