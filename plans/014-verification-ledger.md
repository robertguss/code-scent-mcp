# Plan 014: Evidence-gated finding resolution + verification ledger

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving on. If a
> STOP condition occurs, stop and report — do not improvise. When done, update
> the status row for this plan in `plans/README.md`.
>
> **Drift check (run first)**:
> `git diff --stat 40cbf50..HEAD -- src/codescent/storage/schema.py src/codescent/storage/repositories src/codescent/services/findings.py src/codescent/mcp/finding_tools.py src/codescent/core/public_surface.py tests docs/mcp-tools.md plans/README.md`
> If any in-scope file changed, compare excerpts against live code; on a
> mismatch, treat it as a STOP condition.

## Status

- **Priority**: P2
- **Effort**: M/L
- **Risk**: MED
- **Depends on**: none (coordinate schema version with plan 013 — see notes)
- **Category**: direction / reliability (trust in lifecycle)
- **Planned at**: commit `40cbf50`, 2026-06-15

## Why this matters

Agents love to declare victory. Today `mark_finding(resolved)` trusts the caller
blindly — there is no record of *how* the finding was verified. Adding a
verification ledger (what command ran, exit code, summary) plus **evidence-gated
resolution** (mark "resolved" → recorded as `needs_review` unless verification
evidence or a clean rescan exists) makes "resolved" mean *proven resolved*. This
converts the backlog from optimistic to auditable — exactly what teams reviewing
AI-generated PRs need. CodeScent never executes anything; the agent reports
results, CodeScent records and gates.

## Current state

- `mark_finding` is a thin pass-through to the repository:

```python
# src/codescent/services/findings.py:123-130
    def mark_finding(self, finding_id, status, *, note="") -> FindingRow:
        return _repository(self.repo_root).update_status(finding_id, status, note=note)
```
```python
# src/codescent/storage/repositories/findings.py:83-116
    def update_status(self, finding_id, status, *, note) -> FindingRow:
        ... update findings set status = ?, resolved_at = ? where id = ? ...
        ... insert into finding_events (..., 'status_changed', ...) ...
```

- The schema already has a `suggested_verifications` table (recommend-only
  commands) but NO table for *executed/reported* verification results:

```python
# src/codescent/storage/schema.py:100-107
    create table if not exists suggested_verifications (
        id integer primary key,
        finding_id text references findings(id) on delete cascade,
        command text not null,
        reason text not null,
        executes_in_v1 integer not null default 0
    )
```
  `SCHEMA_VERSION` is `5`; add tables by bumping it and adding a
  `MIGRATION_STATEMENTS` key (see `schema.py:138-211`).

- `FindingStatus` enum already includes `NEEDS_REVIEW`
  (`core/models.py:16-24`).

- Finding MCP tools (scan/mark/rescan/backlog) live in
  `src/codescent/mcp/finding_tools.py`. New MCP tools must also be added to
  `core/public_surface.py` (frozensets + `PUBLIC_SURFACE` tuple).

Repo conventions: strict typing; write state only under `.codescent`; no
execution of project commands; MCP tools thin.

## Commands you will need

| Purpose | Command | Expected |
|---|---|---|
| Contract tests | `uv run pytest tests/contract` | exit 0 |
| Focused tests | `uv run pytest tests -k "verification_ledger or evidence_gate or mark_finding"` | exit 0 |
| Full tests | `uv run pytest` | exit 0 |
| Lint | `uv run ruff check .` | exit 0 |
| Format | `uv run ruff format --check .` | exit 0 |
| Typecheck | `uv run basedpyright` | exit 0 |

## Scope

**In scope**:
- `src/codescent/storage/schema.py` — add `verification_runs` table.
- `src/codescent/storage/repositories/findings.py` (or a new
  `verification.py` repository) — insert/read verification runs.
- `src/codescent/services/findings.py` — evidence-gated `mark_finding` +
  `record_verification`.
- `src/codescent/mcp/finding_tools.py` — register a `record_verification` MCP
  tool; adjust `mark_finding` description to note gating.
- `src/codescent/core/public_surface.py` — register `record_verification`.
- `docs/mcp-tools.md` — document the new tool + gating semantics.
- `tests/` — gating + ledger tests (contract + behavior).
- `plans/README.md` status row.

**Out of scope**:
- Do NOT execute any command. `record_verification` only stores results the
  caller passes in (command string, exit code, summary).
- Do NOT change how the scanner auto-resolves absent findings
  (`code_health.py` `_record_resolved_absent`) — that is rescan-based evidence
  and is already legitimate.
- `tests/fixtures/` source.

## Steps

### Step 1: Add the ledger table

In `schema.py`: bump `SCHEMA_VERSION` to the next free integer (expected `6`, or
`7` if plan 013 already took `6` — **if `SCHEMA_VERSION` is not what you
expect, use the next free number and report**). Add under that version:

```sql
create table if not exists verification_runs (
    id integer primary key,
    finding_id text references findings(id) on delete cascade,
    command text not null,
    exit_code integer not null,
    output_summary text not null,
    created_at text not null
)
```

### Step 2: Repository methods

Add to the finding repository (or a small new repository class following the
existing dataclass-over-`RepositoryStorage` pattern in
`storage/repositories/findings.py`):
- `record_verification(finding_id, command, exit_code, output_summary) -> int`
  → insert, return row id (use `write_transaction()`).
- `has_passing_verification(finding_id) -> bool` → true if any
  `verification_runs` row for the finding has `exit_code == 0`.

### Step 3: Evidence-gate `mark_finding`

In `FindingsService.mark_finding`, when the requested status is
`FindingStatus.RESOLVED`:
- If `has_passing_verification(finding_id)` is `True`, allow `resolved`.
- Otherwise, downgrade to `FindingStatus.NEEDS_REVIEW`, append a `finding_events`
  note explaining the gate (e.g. "resolution requires a passing verification or
  a clean rescan"), and return that row. Add a clear field/return signal so the
  MCP layer can tell the agent it was gated.

Keep all other statuses pass-through unchanged.

### Step 4: `record_verification` service + MCP tool

- Service: `FindingsService.record_verification(finding_id, command, exit_code,
  output_summary)` → repository insert; return a small dataclass.
- MCP: in `finding_tools.py`, add a `record_verification` tool (thin) with a
  `TypedDict` payload, description:
  > "Use CodeScent to record the result of a verification you ran (command, exit
  > code, short summary) against a finding. CodeScent does not execute commands.
  > A passing record lets `mark_finding` resolve the finding."
- Update the `mark_finding` tool description to mention evidence gating.

### Step 5: Public surface + docs

- `core/public_surface.py`: add `"record_verification"` to
  `POST_MVP_MCP_TOOL_NAMES`, `REGISTERED_POST_MVP_MCP_TOOL_NAMES`, and a
  `_registered_post_mvp_entry("record_verification", "health")` entry.
- `docs/mcp-tools.md`: add the reference entry + a sentence on gating in the
  `mark_finding` entry.

**Verify**: `uv run pytest tests/contract` → exit 0.

### Step 6: Tests

- Gate: `mark_finding(id, RESOLVED)` with no verification → row status is
  `needs_review`, and a gate event is recorded.
- Allow: after `record_verification(id, "pytest ...", 0, "ok")`,
  `mark_finding(id, RESOLVED)` → status is `resolved`.
- Ledger: `record_verification` persists and `verification_runs` has the row.
- Contract: `record_verification` appears in the registered surface.

**Verify**: `uv run pytest`, `ruff check .`, `ruff format --check .`,
`basedpyright` → all exit 0.

## Test plan

- Evidence gate downgrades unverified resolution to `needs_review`.
- Passing verification unlocks `resolved`.
- Ledger row persisted; contract surface includes the tool.
- Verification: `uv run pytest` → all pass, including the new migration.

## Done criteria

- [ ] `verification_runs` table created via a new migration; `SCHEMA_VERSION`
      bumped by exactly 1 (coordinated with plan 013).
- [ ] `mark_finding(RESOLVED)` without evidence yields `needs_review`; with a
      passing `verification_runs` row yields `resolved`.
- [ ] `record_verification` MCP tool registered + documented; executes nothing.
- [ ] `uv run pytest`, `ruff check`, `ruff format --check`, `basedpyright` exit 0.
- [ ] No project command executed; no source edited; `tests/fixtures/` untouched.
- [ ] `plans/README.md` status row for 014 updated.

## STOP conditions

Stop and report if:
- Existing tests assert that `mark_finding(RESOLVED)` always yields `resolved`
  unconditionally — report; the gate intentionally changes this and those tests
  may need updating, which the reviewer should approve.
- `SCHEMA_VERSION` collides with plan 013's migration — use the next free number
  and report.
- Verification fails twice after a reasonable fix.

## Maintenance notes

- Coordinate `SCHEMA_VERSION` with plan 013; whichever lands second takes the
  next integer. `migrate()` applies versions in ascending order.
- A future plan can let `get_progress`/`get_backlog` surface "resolved-but-
  unverified" counts using this ledger.
- Reviewers should confirm CodeScent still never runs commands — only records
  caller-supplied results.
