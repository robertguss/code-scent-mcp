# CodeScent MCP Plan Interview Draft

## Request

- User asked to read all docs under `docs/`, use `omo:ulw-plan`, and create a
  plan to build the MCP server.
- User requested clarifying questions until 95% confidence, one question at a
  time.
- Planner scope: read/search/run read-only analysis, write only `.omo/drafts/*`
  and, after explicit approval, `.omo/plans/*`.

## Files read

- `docs/prd.md` fully read: 1,527 lines.
- `docs/architecture.md` fully read: 1,172 lines.
- `.prettierrc` read.
- `omo:ulw-plan` skill and `references/full-workflow.md` read.

## Workspace facts

- Current cwd: `/Users/robertguss/Projects/startups/code-scent-mcp`.
- No `.git` repository here: `git status --short` failed with
  `fatal: not a git repository`.
- No nested `AGENTS.md` found under this repo.
- No implementation scaffold found: no `pyproject.toml`, `src/`, `tests/`,
  package metadata, or lockfile.
- Existing files before planner draft: `.prettierrc`, `docs/prd.md`,
  `docs/architecture.md`.
- `.omo/drafts/` created for planning notes only.

## Current tool/environment facts

- `uv` exists at `/opt/homebrew/bin/uv`.
- `python3` exists at `/opt/homebrew/bin/python3`; version output was
  `Python 3.14.5`.
- `pytest` exists from `/Users/robertguss/.browser-use-env/bin/pytest`.
- `ruff` exists at `/Users/robertguss/.local/bin/ruff`.
- `pyright` was not found in the quick command check.

## External/current docs check

- Context7 resolved FastMCP to `/prefecthq/fastmcp`.
- Current FastMCP docs confirm Python server setup with
  `from fastmcp import FastMCP`, `mcp = FastMCP(name=...)`, `@mcp.tool`,
  `mcp.run()` default local/stdio usage, and `fastmcp.Client(server)` for
  in-memory testing.

## Product facts from docs

- Product is local, open-source, MCP-first codebase improvement server for AI
  coding agents.
- Core goals: local index, structured code intelligence, fast search,
  deterministic code-health findings, token-efficient context, refactor
  planning, verification guidance, persistent backlog.
- Non-goals include hosted SaaS, IDE replacement, cloud indexing, sending source
  to remote services by default, and automatic whole-repo rewrites.
- Recommended initial stack: Python, FastMCP, Typer or Click, SQLite, parser
  adapters, TS/JS/TSX/JSX first.
- Architecture requires FastMCP as thin adapter over internal services, not the
  application architecture.
- Local persistence target: `.codescent/index.sqlite`, `.codescent/config.toml`,
  cache, logs.
- Read-only by default means product must not edit source in early versions;
  docs still require persistence/finding lifecycle operations.
- MVP tools listed in PRD: `get_repo_map`, `get_repo_status`, `search_files`,
  `search_content`, `find_symbol`, `get_file_context`, `get_symbol_context`,
  `scan_code_health`, `get_smell_report`, `get_finding_context`,
  `get_next_improvement`, `plan_refactor`, `suggest_tests`, `mark_finding`,
  `rescan`.
- MVP CLI commands listed: `codescent init`, `serve`, `index`, `scan`, `status`,
  `doctor`.
- First milestone: in a TypeScript/React repo, MCP-connected agent can get repo
  map, search, identify top smell, retrieve bounded context, get safe refactor
  plan, identify tests, and rescan after change.

## Subagent findings integrated

- Repo surface lane: workspace is a planning shell; implementation starts with
  scaffold creation; no git/package/source/tests/AGENTS present.
- Test/package lane: use small Python package, SQLite-backed core, thin
  FastMCP/CLI adapters, tests for repo discovery, persistence, MCP
  registration/read-only behavior, bounded search; suggested uv, pytest, ruff,
  optional pyright/mypy.
- Ambiguity lane: key unresolved user decisions are plan scope, project
  identity/license, dependency posture, write/execution boundary, real TS/React
  acceptance target, and performance envelope.

## Recommended defaults unless user says otherwise

- Scope: complete MVP vertical loop through finding context/refactor
  planning/rescan; later roadmap phases out of scope.
- Identity: CodeScent / `codescent` package / `codescent` CLI / MIT license.
- Dependencies: local-only OSS deps acceptable; Typer, stdlib sqlite3, Pydantic
  if useful, RapidFuzz for ranking, tree-sitter-based parsing for TS/JS/TSX/JSX,
  pytest/ruff/pyright for QA.
- Write boundary: V1 writes only `.codescent/`, never edits source; verification
  recommends commands only and may record results later.
- Acceptance target: deterministic fixture `tests/fixtures/ts-react-basic`; ask
  user for a real TS/React repo before final milestone acceptance if desired.
- Performance: small-to-medium repos up to 25k included text files, default skip
  binary/minified/vendor/lock/build artifacts, target first index under roughly
  60s on modern laptop as reported metric not hard failure.

## First question

Need resolve plan scope first: Phase 1 only vs complete MVP loop vs whole
roadmap.

Answer received:

- User agrees with recommended scope.
- Plan should cover the complete MVP vertical loop through
  scan/findings/context/refactor-plan/rescan.
- Later roadmap phases remain explicit non-goals.

## Remaining material decisions

- Dependency posture.
- Write/execution boundary.
- Acceptance target for real TS/React smoke validation.
- Performance envelope.

## Second question

Need resolve project identity/license because it affects package metadata, CLI
command, README/license tasks, and install docs.

Answer received:

- Product name: CodeScent.
- Python package name: `codescent`.
- CLI command: `codescent`.
- License: MIT.

## Third question

Need resolve dependency posture because it affects scaffold, parser/search
choices, and QA tooling.

Answer received:

- Local-only open-source dependencies are acceptable for the MVP.
- Native/parser packages are acceptable for TypeScript/TSX analysis.
- Recommended dependency direction remains: `fastmcp`, `typer`, `pydantic`,
  `rapidfuzz`, tree-sitter-based TS/JS parsing, `pytest`, `ruff`, `pyright`, and
  stdlib `sqlite3`.

Follow-up raised by user:

- Whether the MVP should target one language or multiple languages.

Answer received:

- User prefers Python-first because Python is the language they are using most
  these days.
- Plan should target one ecosystem deeply for MVP, but use parser/rule seams so
  later ecosystems can be added.
- MVP language scope changes from docs' recommended TypeScript/JavaScript/React
  starting point to Python-first.
- TypeScript/JavaScript/React/Next.js becomes a later language/framework pack,
  not MVP scope.

## Fourth question

Need resolve V1 write/execution boundary because docs say read-only by default
but also require local persistence, `mark_finding`, and `rescan`.

Answer received:

- Read-only by default means no source-code edits.
- V1 may write CodeScent-owned local state under `.codescent/`.
- Allowed V1 writes include `.codescent/config.toml`, `.codescent/index.sqlite`,
  cache/logs, scan runs, and finding state.
- V1 verification should recommend commands rather than execute them.

## Fifth question

Need resolve MVP acceptance target because docs require proving the loop in a
real ecosystem, and the language target is now Python-first.

Answer received:

- MVP validation should use a deterministic Python fixture repo for repeatable
  automated acceptance.
- Plan should include `tests/fixtures/python-basic`.
- Plan should also require one named real Python repo smoke target before
  declaring the MVP milestone complete.

## Sixth question

Need resolve V1 performance envelope because docs flag performance risk but do
not define repo scale.

Answer received:

- V1 should optimize for small-to-medium Python repos.
- Target scale is up to roughly 25k included text files.
- Default exclusions should include `.git`, `.venv`, `__pycache__`,
  `.mypy_cache`, `.ruff_cache`, `dist`, `build`, coverage,
  lock/vendor/generated/binary/minified artifacts.
- First index target is roughly 60 seconds on a modern laptop.
- Index timing should be reported as telemetry rather than a hard failing gate.

Additional requirement raised by user:

- The plan must include evals and define how CodeScent will be measured.
- Evals should be considered part of the MVP planning surface.

## Seventh question

Need resolve eval scope because the user explicitly added measurement/evals as
an MVP concern.

Answer received:

- MVP should include both deterministic offline evals and an agent-in-the-loop
  eval.
- Deterministic evals should be lightweight and repeatable against fixture
  repos.
- Agent-in-the-loop eval should be a milestone gate/manual QA scenario where a
  coding agent uses CodeScent to complete a scripted improvement task.
- Evals should measure retrieval quality, context efficiency, finding quality,
  workflow success, safety, and performance.

## Mandatory Metis gap analysis after approval

Metis found issues that the final plan must address:

- Add an explicit approved override from docs' TypeScript/React recommendation
  to Python-first MVP.
- Define read-only as never editing analyzed source while allowing only
  CodeScent-owned `.codescent/` writes.
- Limit MVP CLI commands to `init`, `serve`, `index`, `scan`, `status`,
  `doctor`; leave `report` and `reset` post-MVP.
- Choose and document Python parser strategy.
- Keep MVP tool scope to the approved vertical loop and exclude adjacent tools
  such as `find_references`, `get_impact`, `verify_change`, reports, prompts,
  backlog views, CI, dashboard, and subjective LLM review unless needed as
  internal helpers.
- Clarify runtime read-only applies to target repositories being analyzed;
  implementation work may scaffold this repo.
- Clarify V1 does not execute target project test/lint/build commands; `doctor`
  may run internal diagnostics such as config, DB, FastMCP, and dependency
  checks.
- Define agent-in-the-loop eval pass/fail behavior.
- Ask user for the named real Python repo smoke target.
- Include error shapes, stdio/no-auth transport, SQLite
  locking/migrations/recovery, stable finding IDs, repository
  boundary/path/symlink rules, Python/runtime/dependency versions, test
  strategy, eval metrics, scaffold-from-zero, non-git degradation, no TS/React
  scope creep, `.codescent` exclusion, and runtime no-network policy.

Planner-resolved defaults for the final plan:

- Parser strategy: start with stdlib `ast` plus `tokenize`/line-range helpers
  for Python MVP to minimize native-parser risk; add parser adapter seams so
  `libcst`, tree-sitter, and other language packs can be added later. Use
  confidence fields for anything heuristic.
- Runtime support target: Python 3.12+ in `pyproject.toml`; verify locally with
  available Python, but do not rely on 3.14-only behavior.
- Package manager: `uv` with `pyproject.toml` and `uv.lock`.
- CLI framework: Typer.
- Model validation/config: Pydantic where useful.
- Search ranking: RapidFuzz for fuzzy matching.
- MCP transport: local stdio only for V1; no auth, HTTP, or SSE.
- Stable finding key:
  `rule_id + normalized relative path + optional qualified symbol + normalized evidence fingerprint`.
- SQLite writes: use transactions, schema version table, one writer policy, busy
  timeout, safe rebuild path for corrupt indexes.
- Repository boundary: normalize paths, reject path traversal, do not follow
  symlinks outside root, exclude `.codescent` and configured
  generated/vendor/cache paths by default.
- V1 eval agent: use the active coding-agent surface by default; pass requires
  transcript/evidence that the agent used CodeScent MCP tools to identify one
  fixture finding, retrieve context, produce a safe plan, and rescan/confirm
  status without direct broad shell search standing in for the tool.

## Real Python repo smoke target assessment

User proposed `/Users/robertguss/Projects/wts-lx/lx_data_lake`.

Assessment:

- Good real smoke candidate.
- It is a real Git repo with `pyproject.toml`, `uv.lock`, `src/`, `tests/`,
  `AGENTS.md`, and `LEARNINGS.md`.
- Local instructions were read: `AGENTS.md` requires reading `LEARNINGS.md`;
  `LEARNINGS.md` was read.
- It has 112 Python files and 1,437 total files before broad exclusions.
- With smoke exclusions for `.git`, `.venv`, `__pycache__`, `.ruff_cache`,
  `.pytest_cache`, `archive`, `data`, and `docs`, it has 93 Python files and 174
  total files.
- It is representative for Python MVP: Typer CLI, Pydantic settings, DuckDB/ETL
  modules, tests, Python 3.12 tooling, large modules, and real source/test
  relationships.
- It has a large `data/` directory (about 4.2G) and `.env`, so the smoke must
  explicitly validate default boundary/exclusion behavior and must not read
  secrets or large data.
- Git status has unrelated untracked files: `.agents/skills/improve/`,
  `mise.toml`, `skills-lock.json`; CodeScent smoke must be read-only and must
  not alter them.

Decision:

- Use `/Users/robertguss/Projects/wts-lx/lx_data_lake` as the required real
  Python repo smoke target.
- Smoke acceptance must confirm `.env`, `data/`, `.venv/`, cache dirs, archive,
  `.git`, and `.codescent/` are excluded by default.
