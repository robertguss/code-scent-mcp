# Plan 008: Generate the MCP/CLI reference docs from the surface registry (kill doc-rot durably)

> **Executor instructions**: This plan has a design step (Step 1) — do it before
> writing code. Follow the rest step by step, verifying as you go. Honor "STOP
> conditions". When done, update the status row in `plans/README.md`.
>
> **Drift check (run first)**:
> `git diff --stat 5dca8d5..HEAD -- src/codescent/core/public_surface.py src/codescent/mcp/schema.py src/codescent/mcp/guide_tools.py tests/docs/test_docs.py`
> If `public_surface.py` or `schema.py` changed materially, re-read them before
> writing the generator; on a big mismatch, STOP.

## Status

- **Priority**: P2
- **Effort**: M
- **Risk**: LOW
- **Depends on**: plans/001-green-the-test-suite.md (001 removes the stale
  mcp-tools/cli-reference coverage tests that this plan restores against
  generated output). Best sequenced after 003 (CI) so the `--check` gate can be
  wired in, but not required.
- **Category**: docs / direction
- **Planned at**: commit `5dca8d5`, 2026-07-02

## Why this matters

The `docs/*.md` reference tree was deleted wholesale (`0ab5610`) because
hand-maintained tool/CLI docs drifted so far from the code that they became
worse than useless — and doc-contract tests plus README links still pointed at
them (that fallout is repaired by plan 001). The **durable** fix is to stop
hand-writing the reference docs at all: the tool/CLI surface already lives in a
single, tested source of truth (`core/public_surface.py`), and the runtime
`get_schema` / `how_to_use` tools already render machine-readable descriptions
of every tool from it. This plan adds a generator that emits
`docs/mcp-tools.md` and `docs/cli-reference.md` from that registry, plus a
`--check` mode that fails when the committed docs drift — converting a recurring
rot problem into a CI gate. It restores the human-facing reference (and the
contract tests) that plan 001 had to remove, this time backed by generation.

## Current state

The single source of truth (`src/codescent/core/public_surface.py`):

```python
@dataclass(frozen=True, slots=True)
class SurfaceEntry:
    name: str
    stage: SurfaceStage      # MVP | POST_MVP
    group: str
    registered: bool

@dataclass(frozen=True, slots=True)
class PublicSurface:
    mcp_tools: tuple[SurfaceEntry, ...]
    cli_commands: tuple[SurfaceEntry, ...]

PUBLIC_SURFACE: Final[PublicSurface] = PublicSurface(mcp_tools=(...), cli_commands=(...))
REGISTERED_MCP_TOOL_NAMES: Final[frozenset[str]] = ...   # derived from PUBLIC_SURFACE
def registered_mcp_tool_names() -> frozenset[str]: ...
```

The runtime schema builder (`src/codescent/mcp/schema.py:91`) already produces
per-tool structured data: `build_schema()` returns entries shaped
`{name, group, params, response_keys}` (see `_tool_entry` at `:135`,
`_response_keys` at `:164`). `mcp/guide_tools.py` exposes `how_to_use()` and
`get_schema()` from these, and `scripts/prove_capability_guide.py` already
asserts the guide covers **every** registered tool — so the completeness
machinery exists; only a static markdown emitter is missing.

The **exact format the restored contract tests will require** (this is the
format the deleted `docs/mcp-tools.md` had — reconstructed from the test
assertions that plan 001 removed from `tests/docs/test_docs.py`): each tool gets

```markdown
### `tool_name`

- Group: <group>
- Purpose: <one-line description>
- Inputs: <params>
- Outputs: <response keys>
- Bounds: <bounded-output / source-read-only safety line>
- Example shape: <minimal example>
```

and the doc as a whole must contain the phrases `source-read-only`,
`bounded output`, `Inputs`, `Outputs`. The CLI reference must contain a
`` `<command>` `` mention for every `PUBLIC_SURFACE.cli_commands` entry with
`registered == True`, plus the line `reset requires --dry-run or --yes`, and
must **not** contain `serve --repo` or `codescent dashboard`.

(If plan 001 has landed, these specific tests were deleted there; you are
re-adding stronger, generation-backed versions.)

## Commands you will need

| Purpose | Command | Expected |
|---|---|---|
| Install | `uv sync` | exit 0 |
| Run generator | `uv run python scripts/gen_reference_docs.py` | writes docs/mcp-tools.md + docs/cli-reference.md |
| Check drift | `uv run python scripts/gen_reference_docs.py --check` | exit 0 clean / exit 1 on drift |
| Docs tests | `uv run pytest tests/docs -q` | pass |
| Full suite | `uv run pytest` | no new failures |
| Lint / types | `uv run ruff check . && uv run basedpyright` | clean |

## Scope

**In scope**:

- `scripts/gen_reference_docs.py` (create)
- `docs/mcp-tools.md`, `docs/cli-reference.md` (generated output — commit them)
- `tests/docs/test_docs.py` (re-add generation-backed coverage tests)
- `README.md` (re-add links to the two regenerated docs)
- `.github/workflows/ci.yml` (add a `--check` step — only if plan 003 landed)

**Out of scope**:

- Regenerating the *prose* docs that were intentionally removed and are not
  registry-derivable (getting-started, workflows, configuration, dashboard,
  evals, agent-routing, CHANGELOG) — those stay gone; this plan is only the two
  registry-derivable references.
- Changing the tool/CLI surface itself or `public_surface.py`.
- Reworking `get_schema`/`how_to_use` — reuse them, don't rewrite them.

## Git workflow

- Branch off `main`: `git switch -c advisor/008-registry-generated-reference-docs`.
- Commits: `feat(docs): generate mcp-tools + cli-reference from the surface registry`
  and `test(docs): restore reference coverage against generated docs`.
- Do NOT push or open a PR.

## Steps

### Step 1 (design — do first): map the data you have vs. the format you need

Read `src/codescent/mcp/schema.py` (`build_schema`, `_tool_entry`,
`_response_keys`), `src/codescent/core/public_surface.py` (`PUBLIC_SURFACE`,
`registered_mcp_tool_names`), and how tool `description=` strings are attached
in the `mcp/*_tools.py` `register_*` calls. Confirm you can obtain, per
registered tool: **group** (from `SurfaceEntry.group` / schema entry),
**purpose** (the tool's `description=` string), **inputs** (`params`),
**outputs** (`response_keys`). For anything the schema doesn't expose (e.g. a
per-tool "Bounds" line, an example), decide a deterministic default (a standard
safety sentence for Bounds; a minimal `{ "ok": true, ... }` example derived from
`response_keys`). Write down the mapping before coding. If a required field
(e.g. the description) is not reachable from `build_schema()` output, note where
it lives (the register functions) and plan to read it from there.

**Verify**: you can print the four fields for every registered tool, e.g. a
throwaway `uv run python -c "from codescent.mcp.schema import build_schema; ..."`.
Do not proceed until every `registered_mcp_tool_names()` entry has all four.

### Step 2: Write `scripts/gen_reference_docs.py`

The generator:

- Imports `build_schema()` (or the registry directly) and iterates
  `registered_mcp_tool_names()` in a deterministic (sorted or surface-declared)
  order.
- Emits `docs/mcp-tools.md`: a short header containing the phrases
  `source-read-only` and `bounded output`, then one `### \`name\`` section per
  tool with the exact `- Group:` / `- Purpose:` / `- Inputs:` / `- Outputs:` /
  `- Bounds:` / `- Example shape:` bullets. Group tools under their group
  headings if the old format did (match the contract test's parsing: it splits
  on `### \`name\``).
- Emits `docs/cli-reference.md`: one section per `PUBLIC_SURFACE.cli_commands`
  entry with `registered == True`, each mentioning `` `command` ``; include the
  literal line `reset requires --dry-run or --yes`; never emit `serve --repo`
  or `codescent dashboard`.
- Output must be **deterministic** (stable ordering, no timestamps) so `--check`
  can byte-compare.
- `--check` flag: regenerate into memory, compare to the on-disk files, print a
  diff and exit 1 if they differ; exit 0 if identical. Default (no flag) writes
  the files.

Follow the existing script conventions: `scripts/*.py` use `typer`, insert
`src` on `sys.path` (see `scripts/prove_capability_guide.py:19`), and are run
via `uv run python scripts/...`.

**Verify**: `uv run python scripts/gen_reference_docs.py` creates both files;
`uv run python scripts/gen_reference_docs.py --check` exits 0 immediately after.

### Step 3: Restore generation-backed contract tests

Re-add to `tests/docs/test_docs.py` (these replace what plan 001 removed):

- `test_reference_docs_are_up_to_date`: runs the generator's `--check` (import
  and call its check function directly, or `subprocess`/`CliRunner`) and asserts
  no drift. This is the durable guard — it fails if anyone edits the surface
  without regenerating.
- `test_mcp_reference_covers_registered_tools`: for every
  `registered_mcp_tool_names()`, assert `### \`name\`` and the six bullets are
  present in `docs/mcp-tools.md` (restore the deleted assertion, pointing at the
  now-generated file).
- `test_cli_reference_covers_registered_commands`: for every registered
  `cli_commands` entry, assert `` `command` `` appears; assert
  `reset requires --dry-run or --yes`, and absence of `serve --repo` /
  `codescent dashboard`.

**Verify**: `uv run pytest tests/docs -q` → pass, including the three re-added
tests.

### Step 4: Re-link the docs in README and confirm the dead-link guard

Add `docs/mcp-tools.md` and `docs/cli-reference.md` back to the README
Documentation section. Since plan 001 rewrote `test_documentation_map_links_exist`
into a live-link resolver, these new links must resolve — they will, because the
files now exist.

**Verify**: `uv run pytest tests/docs/test_docs.py::test_documentation_map_links_exist -q` → pass.

### Step 5: Wire `--check` into CI (only if plan 003 landed)

If `.github/workflows/ci.yml` exists, add a step after the tests:

```yaml
      - run: uv run python scripts/gen_reference_docs.py --check
```

so surface changes that forget to regenerate fail CI.

**Verify**: the step runs green locally (`uv run python scripts/gen_reference_docs.py --check` → exit 0). If plan 003 has not landed, skip this step and note it.

### Step 6: Full green

**Verify**:
- `uv run pytest` → no new failures.
- `uv run ruff check .` / `uv run ruff format --check .` / `uv run basedpyright` → clean.
- `git status` shows only in-scope files.

## Test plan

- Re-added tests in `tests/docs/test_docs.py`: `test_reference_docs_are_up_to_date`
  (the drift guard — the highest-value one), `test_mcp_reference_covers_registered_tools`,
  `test_cli_reference_covers_registered_commands`.
- The generator itself is exercised by the `--check` test; optionally add a unit
  test that generating twice is byte-identical (determinism).
- Verification: `uv run pytest tests/docs -q` → all pass; full `uv run pytest` →
  no new failures.

## Done criteria

ALL must hold:

- [ ] `scripts/gen_reference_docs.py` exists with a working `--check` mode.
- [ ] `docs/mcp-tools.md` and `docs/cli-reference.md` are generated and committed,
      and `--check` reports no drift immediately after generation.
- [ ] Every `registered_mcp_tool_names()` entry has a `### \`name\`` section with
      the six bullets in `docs/mcp-tools.md`.
- [ ] The three coverage/drift tests are present and pass.
- [ ] README links to both regenerated docs and the dead-link guard passes.
- [ ] `uv run pytest` no new failures; lint + types clean.
- [ ] `plans/README.md` status row for 008 updated.

## STOP conditions

Stop and report if:

- A tool's `description=` (Purpose) or `response_keys` (Outputs) cannot be
  obtained deterministically from the registry/schema for some tools — report
  which, rather than hardcoding descriptions (that reintroduces drift).
- The old doc format the contract tests expect cannot be reconstructed from
  available data (e.g. "Example shape" needs information not in the surface) —
  report it; a human should decide whether to add that data to the registry or
  relax the test.
- Generating twice is not byte-identical (nondeterministic ordering/whitespace)
  — fix determinism before wiring `--check`, or the CI gate will flap.

## Maintenance notes

- From now on, the reference docs are **build artifacts**: never hand-edit
  `docs/mcp-tools.md` / `docs/cli-reference.md` — change the surface and
  regenerate. The `--check` test enforces this. A reviewer seeing a manual edit
  to those files should reject it.
- When a new tool/CLI command is added to `public_surface.py`, the drift test
  fails until `gen_reference_docs.py` is re-run — that is the intended coupling.
- This closes the loop opened by plans 001/003: 001 removed the stale
  hand-doc tests, 003 gates the suite, and 008 makes the two registry-derivable
  docs self-maintaining so the rot cannot recur.
- Deferred: generating the prose docs (getting-started/workflows/etc.) is *not*
  in scope and likely never should be — those are genuine prose, not registry
  projections.
