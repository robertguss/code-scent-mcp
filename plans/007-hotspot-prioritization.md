# Plan 007: Rank improvements by hotspot score (churn × size)

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving on. If a
> STOP condition occurs, stop and report — do not improvise. When done, update
> the status row for this plan in `plans/README.md`.
>
> **Drift check (run first)**:
> `git diff --stat 40cbf50..HEAD -- src/codescent/services/findings.py src/codescent/services/git.py tests/integration plans/README.md`
> If any in-scope file changed, compare the Current state excerpts against live
> code before proceeding; on a mismatch, treat it as a STOP condition.

## Status

- **Priority**: P1
- **Effort**: M
- **Risk**: MED
- **Depends on**: plans/006-git-cochange-coupling.md (reuses the single-pass git
  log helper idiom; can proceed independently but land 006 first)
- **Category**: tech-debt / direction (smarter ranking)
- **Planned at**: commit `40cbf50`, 2026-06-15

## Why this matters

`get_next_improvement` currently ranks findings by severity then a tiny
hard-coded rule bonus. A 600-line file nobody touches outranks a churny 120-line
file edited weekly — exactly backwards from where bugs and slop accumulate.
Adding a **hotspot score** = (recent change frequency) × (file size) makes
"what should I improve next?" track real risk, which is the product's promise.
The inputs are already available: git history (churn) and `line_count` (size,
present in the `files` table and in finding evidence).

## Current state

- `src/codescent/services/findings.py:70-83` — `get_next_improvement` sorts by
  `_finding_priority` then walks status buckets:

```python
# src/codescent/services/findings.py:70-83
    def get_next_improvement(self) -> FindingRow | None:
        report = self.get_smell_report()
        actionable = (
            FindingStatus.REGRESSED,
            FindingStatus.NEEDS_REVIEW,
            FindingStatus.OPEN,
            FindingStatus.IN_PROGRESS,
        )
        ranked_findings = sorted(report.findings, key=_finding_priority)
        for status in actionable:
            for finding in ranked_findings:
                if finding.status is status:
                    return finding
        return None
```

- `src/codescent/services/findings.py:156-162` — the current key:

```python
# src/codescent/services/findings.py:156-162
def _finding_priority(finding: FindingRow) -> tuple[int, int, str]:
    severity_rank = {"warning": 0, "error": 0, "info": 1}.get(finding.severity, 2)
    rule_rank = {
        "python.changed_source_without_related_test": 9,
        "python.missing_nearby_test": 8,
    }.get(finding.rule_id, 0)
    return (severity_rank, rule_rank, finding.id)
```

  `FindingRow` (in `src/codescent/storage/repositories/findings.py`) has
  `.file_path`, `.severity`, `.rule_id`, `.id`, `.evidence_json`. There is no
  churn or size field on the row today.

- Git churn: plan 006 added single-pass git history parsing. For this plan add a
  `git_change_counts(repo_root)` helper returning `dict[str, int]` (commits
  touching each path) from ONE `git log --name-only` pass over the whole repo.

Repo conventions: strict typing, no network, services return structured data,
git helpers degrade to empty on failure with a timeout.

## Commands you will need

| Purpose | Command | Expected |
|---|---|---|
| Focused tests | `uv run pytest tests/integration -k "next_improvement or hotspot or priority"` | exit 0 |
| Full tests | `uv run pytest` | exit 0 |
| Lint | `uv run ruff check .` | exit 0 |
| Format | `uv run ruff format --check .` | exit 0 |
| Typecheck | `uv run basedpyright` | exit 0 |

## Scope

**In scope**:
- `src/codescent/services/git.py` — add `git_change_counts(repo_root)`.
- `src/codescent/services/findings.py` — compute a hotspot score and use it in
  `get_next_improvement` ranking (and expose it on `get_backlog` ordering if
  trivial — otherwise leave backlog alone).
- `tests/integration/` — tests for hotspot ordering.
- `plans/README.md` status row.

**Out of scope**:
- Do NOT change `FindingRow`'s persisted schema. Compute the score at ranking
  time from git + evidence; do not add a DB column in this plan.
- Do NOT remove severity as the primary sort key — hotspot is a tiebreaker/
  secondary signal, not a replacement (keeps existing tests stable).
- No new MCP tool or public-surface change.
- `tests/fixtures/` source.

## Git workflow

- Branch: `advisor/007-hotspot-prioritization`. Conventional commits. No push.

## Steps

### Step 1: Add `git_change_counts` to `services/git.py`

```python
def git_change_counts(repo_root: Path) -> dict[str, int]:
    """Return commit counts per path from one ``git log --name-only`` pass.

    Counts how many recent commits (capped at ``GIT_LOG_MAX_COMMITS``) touched
    each path. Excludes ``.codescent``. Returns ``{}`` on any git failure.
    """
```
- Single subprocess: `git -C <root> log --no-renames --format=%H --name-only -n <cap> -- . ":(exclude).codescent"`.
- `check=False`, `timeout=GIT_HISTORY_TIMEOUT_SECONDS`; return `{}` on failure.
- Reuse `GIT_LOG_MAX_COMMITS` if plan 006 added it; otherwise add it.

**Verify**: covered by Step 3 tests.

### Step 2: Compute the hotspot score in `findings.py`

Add a private helper:

```python
def _hotspot_score(finding: FindingRow, change_counts: dict[str, int]) -> float:
    churn = change_counts.get(finding.file_path, 0)
    size = _evidence_line_count(finding)  # parse evidence_json -> line_count or 1
    return float(churn + 1) * float(size + 1)
```
- `_evidence_line_count` parses `finding.evidence_json` (JSON string) and reads
  `line_count` if present, else returns 0. Use `json.loads`; on any error return 0.

Then make ranking hotspot-aware. Replace the sort in `get_next_improvement` so
the key is `(severity_rank, rule_rank, -hotspot_score, finding.id)`. Compute
`change_counts = git_change_counts(resolve_repo_root(self.repo_root))` ONCE
before sorting and pass it into the key. Keep `_finding_priority` for the
severity/rule portion (call it inside the new key or extend its return).

Concretely, update `get_next_improvement`:

```python
        change_counts = git_change_counts(resolve_repo_root(self.repo_root))
        ranked_findings = sorted(
            report.findings,
            key=lambda f: (*_finding_priority(f)[:2], -_hotspot_score(f, change_counts), f.id),
        )
```
(Import `git_change_counts` and `resolve_repo_root` at module top — no inline
imports; see the repo's no-inline-imports rule.)

**Verify**: `uv run pytest tests/integration -k next_improvement` → exit 0.

### Step 3: Test hotspot ordering

In `tests/integration/`, add a test that builds a temp git repo with two
findings of equal severity where one file has higher churn and size, and assert
`get_next_improvement()` returns the hotspot finding. Reuse the temp-git idiom
from `tests/integration/test_context.py`.

**Verify**: `uv run pytest` → exit 0.

### Step 4: Static checks

**Verify**: `uv run ruff check .`, `uv run ruff format --check .`,
`uv run basedpyright` → all exit 0.

## Test plan

- New integration test: equal-severity findings, hotspot wins.
- New integration test: zero-git repo (no `.git`) still returns a finding (score
  falls back to size only; `git_change_counts` returns `{}`).
- Verification: `uv run pytest` → all pass.

## Done criteria

- [ ] `get_next_improvement` ranking incorporates churn × size as a secondary
      key after severity.
- [ ] Behavior is unchanged when git is unavailable (graceful `{}`).
- [ ] `uv run pytest`, `ruff check`, `ruff format --check`, `basedpyright` exit 0.
- [ ] No DB schema change; no new public-surface entry.
- [ ] No files outside in-scope modified.
- [ ] `plans/README.md` status row for 007 updated.

## STOP conditions

Stop and report if:
- Existing `get_next_improvement` tests assert an exact ordering that hotspot
  would break — report the conflict rather than weakening severity precedence.
- `evidence_json` is not valid JSON for some findings (handle by returning size
  0, but if it is structurally different than `{"line_count": int}`, report).
- Verification fails twice after a reasonable fix.

## Maintenance notes

- If churn computation becomes a latency concern on huge repos, cache
  `git_change_counts` per server session.
- A reviewer should confirm severity remains the dominant signal and hotspot is
  a tiebreaker, so the change is additive not disruptive.
- Future: persist a `hotspot_score` column and surface it in `explain_score`.
