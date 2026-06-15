# Plan 015: Add `start_task` — one-shot task brief (context router)

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving on. If a
> STOP condition occurs, stop and report — do not improvise. When done, update
> the status row for this plan in `plans/README.md`.
>
> **Drift check (run first)**:
> `git diff --stat 40cbf50..HEAD -- src/codescent/services src/codescent/mcp src/codescent/core/public_surface.py tests docs/mcp-tools.md plans/README.md`
> If any in-scope file changed, compare excerpts against live code; on a
> mismatch, treat it as a STOP condition.

## Status

- **Priority**: P1
- **Effort**: M
- **Risk**: LOW/MED
- **Depends on**: none (richer when 006 is landed; works without it)
- **Category**: direction (new MCP tool) / dx
- **Planned at**: commit `40cbf50`, 2026-06-15

## Why this matters

To start any task an agent must chain many calls — `find_symbol` →
`get_symbol_context` → `find_callers` → `get_related_files` → `search_tests` →
`get_smell_report` — 8–12 round trips, each a context hit, and the agent has to
know which tool to call. `start_task` takes a natural-language task plus an
optional focus path/symbol and returns ONE bounded bundle: relevant files, key
symbols, related files/tests, open findings in scope, an index-freshness note,
and the recommended next tool calls. It is the intuitive entry point and the
biggest token-and-latency win — and it is pure orchestration over services that
already exist.

## Current state

The services to orchestrate (all already implemented):

- `ContextService` (`services/context.py`): `find_symbol(query, limit)`,
  `get_file_context(path)`, `get_related_files(path, limit)`.
- `SearchService` (`services/search.py`) — read this file for the exact method
  names/signatures for file and content search (used to resolve a NL query to
  candidate files).
- `FindingsService` (`services/findings.py`): `get_smell_report()` returns
  `SmellReport(findings: tuple[FindingRow, ...], ...)`; `FindingRow` has
  `.file_path`, `.id`, `.rule_id`, `.severity`.
- `RepoStatusService`/status (`services/status.py`) — read it for an index
  freshness signal to include (e.g. `index_fresh`).

The MCP tool pattern (thin function + `TypedDict` payload + `register_*_tools`)
is in `src/codescent/mcp/planning_tools.py:75-149`. New tools must be added to
`core/public_surface.py` (frozensets + `PUBLIC_SURFACE` tuple — see
`public_surface.py:72-184`). Server registration is in `mcp/server.py:13-22`
(each `register_*_tools(mcp)` call).

Repo conventions: MCP thin; services hold logic; bounded output; no network;
read-only source. The output MUST be bounded — this tool aggregates several
sources, so cap every list (files ≤ 8, symbols ≤ 12, tests ≤ 8, findings ≤ 10).

## Commands you will need

| Purpose        | Command                                             | Expected |
| -------------- | --------------------------------------------------- | -------- |
| Contract tests | `uv run pytest tests/contract`                      | exit 0   |
| Focused tests  | `uv run pytest tests -k "start_task or task_brief"` | exit 0   |
| Full tests     | `uv run pytest`                                     | exit 0   |
| Lint           | `uv run ruff check .`                               | exit 0   |
| Format         | `uv run ruff format --check .`                      | exit 0   |
| Typecheck      | `uv run basedpyright`                               | exit 0   |

## Scope

**In scope**:

- `src/codescent/services/task_brief.py` (create) — `TaskBriefService`.
- `src/codescent/mcp/repo_tools.py` (add the tool here, or a new
  `task_tools.py` + register it in `server.py`) — register `start_task`.
- `src/codescent/core/public_surface.py` — register `start_task`.
- `docs/mcp-tools.md` — document the tool.
- `tests/contract/`, `tests/integration/` — contract + behavior tests.
- `plans/README.md` status row.

**Out of scope**:

- Do NOT add LLM calls or any network. Resolution is deterministic: search +
  graph + findings only.
- Do NOT return raw file source (only summaries/paths/symbol names and the
  existing bounded source ranges from `get_file_context` if needed — keep caps).
- Do NOT modify the orchestrated services' behavior; only call them.
- `tests/fixtures/` source.

## Steps

### Step 1: Build `TaskBriefService`

Create `src/codescent/services/task_brief.py`:

```python
@dataclass(frozen=True, slots=True)
class TaskBrief:
    query: str
    relevant_files: tuple[str, ...]      # cap 8
    relevant_symbols: tuple[str, ...]    # cap 12 (qualified names)
    related_tests: tuple[str, ...]       # cap 8
    open_findings: tuple[dict[str, str], ...]  # cap 10: {id, rule_id, file_path, severity}
    index_fresh: bool
    next_tools: tuple[str, ...]          # suggested follow-up tool calls

@dataclass(frozen=True, slots=True)
class TaskBriefService:
    repo_root: Path | str

    def start_task(self, query: str, *, focus_path: str | None = None,
                   focus_symbol: str | None = None) -> TaskBrief:
        ...
```

Resolution logic (all deterministic, all bounded):

1. Determine seed files:
   - if `focus_path` given, seed = `[focus_path]`;
   - elif `focus_symbol` given,
     `ContextService.find_symbol(focus_symbol, limit=3)` → seed = their `path`s;
   - else use `SearchService` file + content search on `query` (read
     `services/search.py` for the exact call) → top file paths.
2. For each seed file (cap the seed set to ~4): collect `get_file_context(path)`
   symbols + likely_tests, and `get_related_files(path, limit=6)` results
   (paths + which are tests).
3. `open_findings`: from `FindingsService(...).get_smell_report().findings`,
   keep those whose `file_path` is in the relevant-files set, status open/
   actionable, cap 10.
4. `index_fresh`: from the status service.
5. `next_tools`: e.g.
   `("get_symbol_context:<top symbol>", "get_finding_context:<top finding id>", "select_tests")`
   — only include entries that exist.
6. Dedupe + apply caps to every list.

### Step 2: Register the MCP tool

Add a `StartTaskToolPayload(TypedDict)` and a thin
`start_task(query: str, repo: str = ".", focus_path: str | None = None, focus_symbol: str | None = None)`
that calls `TaskBriefService(...).start_task(...)` and serializes to the
payload. Register with a description:

> "Use CodeScent FIRST when beginning a task. Returns a bounded brief: relevant
> files, key symbols, related tests, in-scope findings, index freshness, and the
> next tool calls to make — so you avoid broad greps and many round trips. Read-
> only; bounded output."

If you add it to `repo_tools.py`, no `server.py` change is needed (already
registered). If you create `task_tools.py`, add `register_task_tools(mcp)` and
call it in `server.py`.

### Step 3: Public surface + docs

- `core/public_surface.py`: add `"start_task"` to `POST_MVP_MCP_TOOL_NAMES`,
  `REGISTERED_POST_MVP_MCP_TOOL_NAMES`, and a
  `_registered_post_mvp_entry("start_task", "repository")` entry.
- `docs/mcp-tools.md`: add the reference entry.

**Verify**: `uv run pytest tests/contract` → exit 0.

### Step 4: Tests

- Integration: temp repo with `src/app/x.py` (a symbol `do_thing`),
  `tests/test_x.py`, and a finding on `x.py`. Call
  `TaskBriefService(repo).start_task("do thing", focus_path="src/app/x.py")` and
  assert: `relevant_files` includes `src/app/x.py`; `relevant_symbols` includes
  the symbol; `related_tests` includes `tests/test_x.py`; `open_findings` is
  bounded and references `x.py`; every list respects its cap.
- Contract: `start_task` is in the registered surface.

**Verify**: `uv run pytest`, `ruff check .`, `ruff format --check .`,
`basedpyright` → all exit 0.

## Test plan

- Brief aggregates files/symbols/tests/findings for a focused task; all caps
  enforced; no raw source dump.
- Contract surface includes `start_task`.
- Verification: `uv run pytest` → all pass.

## Done criteria

- [ ] `start_task` MCP tool registered, documented, and listed in
      `public_surface.py`.
- [ ] Returns a bounded brief (every list capped) with no network and no raw
      file dumps.
- [ ] `uv run pytest`, `ruff check`, `ruff format --check`, `basedpyright`
      exit 0.
- [ ] No orchestrated service behavior changed; `tests/fixtures/` untouched.
- [ ] `plans/README.md` status row for 015 updated.

## STOP conditions

Stop and report if:

- `SearchService`'s method names/signatures differ from what Step 1 assumes —
  read the file and adapt; if search cannot return file candidates for a NL
  query, report and fall back to requiring `focus_path`/`focus_symbol`.
- The aggregated payload exceeds a sensible bound even after caps (e.g. source
  ranges balloon it) — report; drop source ranges from the brief.
- Verification fails twice after a reasonable fix.

## Maintenance notes

- This is the marquee agent-ergonomics tool; keep its output tight. If you add
  signals later (co-change from 006, coverage from 011), keep the caps.
- Reviewers should confirm it is read-only, bounded, and adds exactly one new
  public tool name.
- Consider a CLI `codescent brief "<task>"` wrapper in a follow-up for humans.
