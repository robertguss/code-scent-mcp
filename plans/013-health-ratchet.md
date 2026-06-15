# Plan 013: Add a code-health ratchet (per-file debt budget) to CI

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving on. If a
> STOP condition occurs, stop and report — do not improvise. When done, update
> the status row for this plan in `plans/README.md`.
>
> **Drift check (run first)**:
> `git diff --stat 40cbf50..HEAD -- src/codescent/storage/schema.py src/codescent/services/ci.py src/codescent/cli tests plans/README.md`
> If any in-scope file changed, compare excerpts against live code; on a
> mismatch, treat it as a STOP condition.

## Status

- **Priority**: P1
- **Effort**: M/L
- **Risk**: MED
- **Depends on**: none (but coordinate schema version with plan 014 — see notes)
- **Category**: direction / dx (enforceable quality gate)
- **Planned at**: commit `40cbf50`, 2026-06-15

## Why this matters

Absolute thresholds are useless on legacy or AI-generated code — everything
fails on day one, so teams disable the gate. A **ratchet** records a per-file
baseline of finding counts and fails CI only when a file gets *worse than its
baseline*. Existing debt is grandfathered; new debt is blocked. This is what
makes CodeScent enforceable in practice and is the perfect leash for AI agents:
an agent cannot make a file messier than it found it.

## Current state

- The CI report is computed in `src/codescent/services/ci.py:35-49`:

```python
# src/codescent/services/ci.py:35-49
    def run(self, *, threshold: str) -> CiReport:
        scan = CodeHealthService(self.repo_root).scan()
        diff_risk = RiskService(self.repo_root).review_diff_risk()
        risk_level = _scan_risk_level(tuple(f.severity for f in scan.findings))
        changed_file_health = _health_from_scan(scan.findings)
        return CiReport(ok=_passes(threshold, risk_level), ...)
```
  `scan.findings` is a tuple of `CodeHealthFinding` each with `.file_path`.

- Schema migrations: `src/codescent/storage/schema.py`. `SCHEMA_VERSION` is
  currently `5`. New tables are added by bumping `SCHEMA_VERSION` and adding a
  key to `MIGRATION_STATEMENTS`:

```python
# src/codescent/storage/schema.py:4 and 138-211
SCHEMA_VERSION: Final = 5
MIGRATION_STATEMENTS: Final[dict[int, tuple[str, ...]]] = {
    3: (... symbol_references, call_edges ...),
    4: (... subjective_findings ...),
    5: (... stored_results, session_events ...),
}
```

- `RepositoryStorage` exposes `read_connection()` and `write_transaction()`
  (used throughout, e.g. `services/code_health.py:56`).

- CLI commands register through `src/codescent/cli/` (the `ci` command already
  exists per `core/public_surface.py:201`). The reporting/admin command modules
  are `cli/reporting.py` and `cli/admin.py`.

Repo conventions: strict typing; write state only under `.codescent`; no network.

## Commands you will need

| Purpose | Command | Expected |
|---|---|---|
| Focused tests | `uv run pytest tests -k "ratchet or baseline or ci"` | exit 0 |
| Full tests | `uv run pytest` | exit 0 |
| Lint | `uv run ruff check .` | exit 0 |
| Format | `uv run ruff format --check .` | exit 0 |
| Typecheck | `uv run basedpyright` | exit 0 |

## Scope

**In scope**:
- `src/codescent/storage/schema.py` — add a `health_baseline` table (new
  migration version).
- `src/codescent/services/ci.py` — add ratchet comparison + a way to write the
  baseline.
- `src/codescent/cli/reporting.py` (or wherever `ci` is defined) — add a
  `--ratchet` flag and a `--update-baseline` flag to the existing `ci` command.
  Do NOT add a brand-new top-level command (avoids public-surface churn).
- `tests/` — ratchet behavior tests.
- `docs/` — short note in the CI docs.
- `plans/README.md` status row.

**Out of scope**:
- Do NOT change the default `ci` behavior when `--ratchet` is not passed.
- Do NOT add a new MCP tool.
- Do NOT execute project commands.
- `tests/fixtures/` source.

## Steps

### Step 1: Add the baseline table

In `schema.py`: bump `SCHEMA_VERSION` to the next free integer (expected `6`;
**if it is not currently `5`, STOP** — plan 014 may have taken `6`; then use the
next free number and tell the reviewer). Add under that version key:

```sql
create table if not exists health_baseline (
    id integer primary key,
    file_path text not null unique,
    finding_count integer not null,
    created_at text not null
)
```

### Step 2: Baseline read/write + comparison in `ci.py`

Add to `CiService`:
- `update_baseline() -> int`: run a scan, count findings per `file_path`, and
  upsert into `health_baseline` (delete-all-then-insert, or upsert on
  `file_path`). Return the number of files recorded. Use `write_transaction()`.
- `run(..., ratchet: bool = False)`: when `ratchet` is `True`, after scanning,
  load the baseline counts, compute current per-file counts (reuse
  `_health_from_scan`'s grouping logic — factor it into a small helper returning
  `dict[str, int]`), and mark the report `ok=False` if ANY file's current count
  exceeds its baseline (files with no baseline row use baseline 0 — i.e. a brand
  new file with findings fails the ratchet, which is intended). Add the
  offending files to the report (extend `CiReport` with an optional
  `ratchet_regressions: tuple[str, ...] = ()` field).

Keep non-ratchet behavior byte-for-byte identical.

### Step 3: CLI flags

In the module defining the `ci` command, add `--ratchet/--no-ratchet` (default
off) and `--update-baseline` (writes the baseline and exits 0). Wire them to the
new `CiService` methods. Match the existing Typer option style in that file.

**Verify**: `uv run pytest tests -k ratchet` → exit 0 after Step 4.

### Step 4: Tests

- Establish a baseline on a temp repo, then add a finding to one file (e.g.
  enlarge a file past `LARGE_FILE_LINES`), run `ci --ratchet`, assert `ok is
  False` and the file is in `ratchet_regressions`.
- Reduce/keep findings at-or-below baseline → `ci --ratchet` `ok is True`.
- `ci` without `--ratchet` behaves exactly as before (assert against an existing
  CI test if present).

**Verify**: `uv run pytest`, `ruff check .`, `ruff format --check .`,
`basedpyright` → all exit 0.

## Test plan

- Regression above baseline fails; at-or-below passes; baseline-absent file with
  findings fails.
- Non-ratchet path unchanged.
- Verification: `uv run pytest` → all pass, including migration creating
  `health_baseline`.

## Done criteria

- [ ] `health_baseline` table created via a new migration; `SCHEMA_VERSION`
      bumped by exactly 1.
- [ ] `ci --update-baseline` records per-file counts; `ci --ratchet` fails only
      on per-file regressions.
- [ ] Default `ci` behavior unchanged.
- [ ] `uv run pytest`, `ruff check`, `ruff format --check`, `basedpyright` exit 0.
- [ ] No MCP tool added; no source edited; `tests/fixtures/` untouched.
- [ ] `plans/README.md` status row for 013 updated.

## STOP conditions

Stop and report if:
- `SCHEMA_VERSION` is not `5` at start (another schema plan landed first) — use
  the next free version and report the coordination.
- Existing CI tests assert a fixed `CiReport` field set that adding
  `ratchet_regressions` would break — report; consider a default-empty field to
  stay backward compatible.
- Verification fails twice after a reasonable fix.

## Maintenance notes

- Coordinate with plan 014 (also adds a table). Whichever lands second takes the
  next free `SCHEMA_VERSION`. The `migrate()` loop applies versions in order, so
  this is safe as long as numbers don't collide.
- Reviewers should confirm the ratchet is opt-in and that a fresh repo without a
  baseline doesn't break default CI.
- Future: ratchet on metrics (complexity/lines) not just finding counts.
