# Implementation Plan: CodeScent v2 Feature Roadmap

**Status:** Locked v1 (2026-06-15) **Scope:** Engineer-ready, multi-quarter plan
for the ten v2 features selected in the v2 brainstorm. Supersedes nothing;
extends `docs/prd.md`, `docs/architecture.md`, and `docs/mcp-tools.md`. Five
sign-off decisions locked on 2026-06-15 — see section "Locked Decisions" at the
bottom. **Constitution:** Local-first, source-read-only for analyzed source, no
runtime network for core paths, deterministic-first, bounded outputs,
service-thin-adapter pattern. Every section in this plan must respect those
invariants and the policies in `src/codescent/AGENTS.md`,
`src/codescent/services/AGENTS.md`, and `src/codescent/mcp/AGENTS.md`.

---

## 1. Sequencing and Dependency Graph

```text
                                       Phase A (Foundations)
                                       +-------------------------+
                                       | A1 Semantic Anchors     |
                                       | A2 Token Ledger v2      |
                                       | A3 Co-Change Hotspots   |
                                       +------------+------------+
                                                    |
                            +-----------------------+-----------------------+
                            |                       |                       |
                  Phase B (Agent Leverage)   Phase C (Code Intel)    feeds D
                  +----------------------+   +---------------------+
                  | B1 Investigation     |   | C1 Arch Fitness +   |
                  |    Macros            |   |    NL->Rule         |
                  | B2 Knowledge Cards   |   | C2 Public API       |
                  | B3 AST-Shape Dup +   |   |    Ledger           |
                  |    Slop Signatures   |   +---------+-----------+
                  +----------+-----------+             |
                             |                         |
                             +------------+------------+
                                          |
                              Phase D (Verification Headline)
                              +-----------------------------+
                              | D1 Test Impact + Mutation   |
                              | D2 Behavior-Preservation    |
                              |    Oracle (sandbox)         |
                              +-----------------------------+
```

Hard dependencies:

- **A1 Semantic Anchors** is a prerequisite for B2 (Cards), C2 (API Ledger
  diffing), and improves D2's diff stability. Build it first.
- **A2 Token Ledger v2** is the data substrate the adaptive defaults in B1 and
  D2 read from. Build before B/D.
- **A3 Co-Change Hotspots** is independent but feeds ranking in B1, C2, D2.
- **C2 Public API Ledger** consumes A1 anchors to keep contracts stable.
- **D2 Oracle** consumes A1 (anchored impact set), A2 (budget/telemetry), A3
  (risk scoring), C2 (API diff classification), and D1 (impact + mutation).

Soft dependencies are noted per feature.

## 2. Milestone Table

| Quarter | Phase | Features   | Headline outcome                                                            |
| ------- | ----- | ---------- | --------------------------------------------------------------------------- |
| Q1      | A     | A1, A2, A3 | Stable finding identity, measurable token savings, hotspot signal.          |
| Q2      | B     | B1, B2, B3 | Agents do fewer tool roundtrips, recall prior knowledge, catch AI slop.     |
| Q3      | C     | C1, C2     | Architecture is enforceable as findings; public API breakage is detectable. |
| Q4      | D     | D1, D2     | Agents get real verification evidence before edits land.                    |

Each feature ships when its **exit criteria** pass: contract test suite green,
schema migration green on a real `.codescent/` from the previous version,
evidence artifact written to `.omo/evidence/<task>.json`, public surface
registry updated, and documentation updated.

## 3. Cross-Cutting Standards

These apply to every feature in this plan.

### 3.1 Public surface lockstep

Any new MCP tool or CLI command **must** be added to
`src/codescent/core/public_surface.py` in the same PR that introduces the
implementation. `POST_MVP_MCP_TOOL_NAMES` and
`REGISTERED_POST_MVP_MCP_TOOL_NAMES` move together. Contract tests in
`tests/contract/test_public_surface_registry.py` and
`tests/contract/test_mcp_tool_surface.py` must stay green.

### 3.2 Storage migrations

Every new table or column lives in `src/codescent/storage/schema.py` as a new
entry in `MIGRATION_STATEMENTS` with a bumped `SCHEMA_VERSION`. Migrations are
forward-only, idempotent (`create table if not exists`), and tested against a
checked-in `.codescent/index.sqlite` snapshot from the previous version under
`tests/contract/migrations/`.

### 3.3 Service shape

New services live in `src/codescent/services/<name>.py` as a frozen dataclass
that accepts `repo_root: Path | str` and exposes typed dataclass returns. They
must not import `fastmcp` or `typer`. MCP wrappers live under
`src/codescent/mcp/<name>_tools.py` and are limited to a `register_*_tools`
function plus thin wrappers that return TypedDict payloads from
`finding_payloads.py`-style modules.

### 3.4 Tests

Every feature ships unit tests in `tests/unit/`, an integration test under
`tests/integration/`, a contract test under `tests/contract/`, and where it
expands the safety boundary, a runtime-safety assertion in
`tests/security/test_runtime_safety.py`.

### 3.5 Evidence artifacts

Each feature lands with a one-shot script under `scripts/` that writes a
deterministic JSON evidence artifact to `.omo/evidence/<task-id>.json`. The
script must work against `tests/fixtures/python-basic` with no network and exit
0 on success. Mirrors the pattern of `scripts/prove_source_read_only.py`.

### 3.6 Docs lockstep

Each feature updates: `docs/mcp-tools.md` (tool reference),
`docs/architecture.md` (if new service/engine module), `docs/cli-reference.md`
(if new command), and adds a workflow snippet to `docs/workflows.md` showing the
new tool in agent use.

---

# Phase A: Foundations

## A1. Semantic Anchors

### A1.1 Why

Solves architecture risk 16.3 in `docs/architecture.md` ("Poor Finding
Stability"). Today, a finding's identity is derived from path + line numbers
inside `stable_key`. A trivial reformat shifts every finding ID, breaking
`mark_finding`, breaking `retrieve_result` citations, and confusing rescan diff.
Semantic anchors fix this once for every downstream feature.

### A1.2 Anchor schema

A **SemanticAnchor** identifies a code location independently of line numbers:

```python
@dataclass(frozen=True, slots=True)
class SemanticAnchor:
    file_path: str
    node_path: tuple[str, ...]
    node_kind: str
    structural_hash: str
    name_hash: str
    schema_version: int = 1
```

- `node_path` is the AST ancestor chain from module root, e.g.
  `("ClassDef:Foo", "FunctionDef:bar", "If:cond_0")`.
- `structural_hash` is a SHA-1 over the AST shape with identifiers erased and
  literals bucketed (`STRING`, `INT`, `FLOAT`, etc.). Tolerant to renames and
  string changes, sensitive to logic changes.
- `name_hash` is a SHA-1 over the original identifier names; used to
  disambiguate same-shape siblings.

Canonical string form for storage and citation:
`anchor:v1:<file_path>#<node_path_joined>@<structural_hash[:12]>:<name_hash[:8]>`

### A1.3 Engine module

New: `src/codescent/engine/anchors/__init__.py` New:
`src/codescent/engine/anchors/python.py` New:
`src/codescent/engine/anchors/resolver.py`

Public functions:

```python
def compute_anchors_for_file(
    repo_root: Path, file_path: str
) -> tuple[AnchoredNode, ...]: ...

def compute_anchor_for_symbol(
    repo_root: Path, file_path: str, qualified_name: str
) -> SemanticAnchor: ...

def resolve_anchor(
    repo_root: Path, anchor: SemanticAnchor
) -> ResolvedLocation | None: ...

def serialize(anchor: SemanticAnchor) -> str: ...
def deserialize(text: str) -> SemanticAnchor: ...
```

`ResolvedLocation` returns current `start_line`, `end_line`, and a `drift_kind`
of `exact | moved | structurally_changed | missing`.

Resolution algorithm (in order):

1. Exact match by `node_path + structural_hash + name_hash` -> `exact`.
2. Same `node_path` + matching `structural_hash` -> `moved`.
3. Same `node_path` + matching `name_hash` only -> `structurally_changed`.
4. Same `name_hash` anywhere in file -> `moved` (different node_path).
5. None -> `missing`.

### A1.4 Storage migration (v6)

Add to `MIGRATION_STATEMENTS[6]`:

```sql
create table if not exists semantic_anchors (
    id integer primary key,
    file_id integer not null references files(id) on delete cascade,
    symbol_id integer references symbols(id) on delete set null,
    node_path text not null,
    node_kind text not null,
    structural_hash text not null,
    name_hash text not null,
    schema_version integer not null default 1,
    last_indexed_at text not null
);
create index if not exists semantic_anchors_file_idx
    on semantic_anchors(file_id, structural_hash);
create index if not exists semantic_anchors_name_idx
    on semantic_anchors(name_hash);

alter table findings add column anchor_text text;
alter table chunks add column anchor_text text;
```

`stable_key` generation in `engine/rules/model.py` `build_finding` switches to
prefer an anchor when one is computable for the finding's target symbol, with
fallback to today's path+rule_id+evidence-hash key. Backfill on first scan
post-migration.

### A1.5 MCP surface changes

- New:
  `resolve_anchor(anchor_text: str, repo: str = ".") -> ResolveAnchorPayload`
  returns `{ok, file_path, start_line, end_line, drift_kind, anchor_text_now}`.
- Augment: `get_finding`, `get_finding_context`, `mark_finding`,
  `retrieve_result` payloads gain an `anchor` field (string form) where
  applicable. `mark_finding` accepts `finding_id` OR `anchor_text`.

Register in `src/codescent/mcp/context_tools.py`. Add `resolve_anchor` to
`POST_MVP_MCP_TOOL_NAMES` and `REGISTERED_POST_MVP_MCP_TOOL_NAMES`.

### A1.6 Tests

- `tests/unit/test_anchors_python.py`: round-trip serialize/deserialize;
  whitespace edit -> `exact`; rename function -> `moved`; flip operator ->
  `structurally_changed`; delete -> `missing`.
- `tests/integration/test_anchor_repository.py`: SQLite round-trip; backfill
  preserves existing finding IDs (old keys mapped to new anchors via migration
  helper).
- `tests/contract/test_mcp_resolve_anchor.py`: payload shape, bounded output,
  error envelope when input is malformed.
- `tests/contract/migrations/test_v5_to_v6.py`: applies migration to a
  checked-in snapshot, asserts row counts unchanged, finding IDs stable.

### A1.7 Evidence

`scripts/prove_anchor_stability.py` -> `.omo/evidence/a1-anchor-stability.json`

Scenario: scan `tests/fixtures/python-basic`, mutate one file by reformatting
(black -> 2-space) and by renaming a non-finding function, rescan, and assert:
all anchored findings retained the same `finding_id`, all line numbers
re-resolved correctly, `drift_kind` distribution matches expectations.

### A1.8 Effort and risks

- Effort: **M** (2 engineers, ~3 weeks).
- Risks: (a) ast nodes that lack stable ordering (e.g. `if/elif` collapse) ->
  add a sibling-index suffix to `node_path`; (b) backfill on huge repos may be
  slow -> stream by file with progress reporting; (c) TS adapter parity is out
  of scope for v1 of this feature -> Python-only, register adapter interface so
  TS can land later.

---

## A2. Token Economy Ledger v2 + Adaptive Budgets

### A2.1 Why

`services/session_stats.py` already records summarization events. The ledger
extends it from "what happened" to "what was it worth" and uses the data to
self-tune default limits so the system gets cheaper over time. Makes the PRD's
central value proposition (token efficiency) provable to users.

### A2.2 Schema migration (v7)

```sql
create table if not exists tool_call_outcomes (
    id integer primary key,
    project_id text not null,
    session_id text not null,
    tool_call_id text not null,
    tool_name text not null,
    input_fingerprint text not null,
    input_tokens integer not null default 0,
    output_tokens integer not null default 0,
    naive_baseline_tokens integer,
    referenced_by_later_call integer not null default 0,
    preceded_finding_status_change integer not null default 0,
    created_at text not null
);
create index if not exists tool_call_outcomes_project_idx
    on tool_call_outcomes(project_id, tool_name, created_at);

create table if not exists tool_budget_overrides (
    project_id text not null,
    tool_name text not null,
    parameter_name text not null,
    value_json text not null,
    reason text not null,
    updated_at text not null,
    primary key (project_id, tool_name, parameter_name)
);
```

### A2.3 Service

New: `src/codescent/services/token_ledger.py`

```python
@dataclass(frozen=True, slots=True)
class ToolCallOutcome:
    tool_call_id: str
    tool_name: str
    input_tokens: int
    output_tokens: int
    naive_baseline_tokens: int | None
    referenced_by_later_call: bool
    preceded_finding_status_change: bool

@dataclass(frozen=True, slots=True)
class TokenLedgerService:
    repo_root: Path | str

    def record_outcome(self, *, project_id: str, session_id: str,
                       outcome: ToolCallOutcome) -> None: ...

    def tool_roi(self, *, project_id: str,
                 window_days: int = 30) -> tuple[ToolRoiRow, ...]: ...

    def token_savings(self, *, project_id: str,
                      window_days: int = 30) -> TokenSavings: ...

    def recommend_budget(self, *, project_id: str, tool_name: str,
                         parameter_name: str) -> BudgetRecommendation: ...
```

Naive-baseline computation lives in `src/codescent/engine/token/baseline.py`:

- `search_*`: `estimate_naive_grep_tokens(query, repo_root)` (size of files that
  would match a recursive grep).
- `get_file_context`, `get_symbol_context`: file token estimate from byte size.
- `find_*` / context graph tools: 0 baseline (no naive equivalent).

The adaptive defaults read `tool_budget_overrides` at tool entry via a
`load_effective_limit(tool, parameter, default)` helper imported by each MCP
adapter. A `recommend_budget` heuristic triggers when the median `output_tokens`
exceeds the parameter's effective value with `referenced_by_later_call=False`
over the last N calls.

### A2.4 MCP surface

- New: `get_token_savings(window_days: int = 30, repo: str = ".")`
- New: `get_tool_roi(window_days: int = 30, repo: str = ".")`
- Augment: `context_stats` payload gains `naive_baseline_tokens_sum`,
  `referenced_ratio`, `outcome_correlation` block.

**Locked: `recommend_budget` is advisory-only forever.** Adaptive
recommendations are surfaced but never auto-applied. The CLI command
`codescent budgets apply --dry-run|--yes` is the _only_ path that writes
`tool_budget_overrides`. There will be no `auto_apply_recommendations`
project-config flag, ever. CI users can pipe `--yes` after review. Rationale:
determinism is the product's identity, and silent default-shrinking would make
the same bounded tool call return different results across runs.

MCP tools never change agent-visible parameter behavior except by reading the
explicit `tool_budget_overrides` table written by the CLI.

### A2.5 Tests

- Unit: ROI math, baseline estimator across tool types, budget recommendation
  triggering thresholds.
- Integration: replay a recorded session JSONL into the ledger, assert
  aggregates.
- Contract: `get_token_savings` and `get_tool_roi` payload shapes; budget
  override application via CLI.

### A2.6 Evidence

`scripts/measure_token_savings.py` -> `.omo/evidence/a2-token-savings.json` Runs
the smoke MCP flow against `tests/fixtures/python-basic`, records every call's
input/output tokens and naive baseline, prints `tokens_avoided_total` and
per-tool ROI. The smoke script in `scripts/smoke_mcp.py` is the model; this
script reuses it as a callable.

### A2.7 Effort and risks

- Effort: **S-M** (1 engineer, ~2 weeks).
- Risks: token-estimation drift between providers — keep estimator pluggable;
  outcome correlation (`preceded_finding_status_change`) is best effort and
  clearly labeled as such in payloads.

---

## A3. Co-Change Hotspot Graph

### A3.1 Why

Empirical hotspot scoring (Tornhill) is the strongest single signal for "where
should I focus first". Cheap to compute from local git; no other agent-facing
MCP product exposes it. Lifts ranking quality for `get_next_improvement`,
`get_related_files`, and `review_diff_risk` with near-zero new infrastructure.

### A3.2 Schema migration (v8)

```sql
create table if not exists git_commit_files (
    commit_sha text not null,
    file_path text not null,
    additions integer not null default 0,
    deletions integer not null default 0,
    committed_at text not null,
    primary key (commit_sha, file_path)
);
create index if not exists git_commit_files_file_idx
    on git_commit_files(file_path);

create table if not exists cochange_edges (
    file_a text not null,
    file_b text not null,
    cochange_count integer not null,
    last_cochange_at text not null,
    refreshed_at text not null,
    primary key (file_a, file_b)
);

create table if not exists hotspot_scores (
    file_path text primary key,
    churn_count integer not null,
    avg_complexity real not null,
    open_finding_count integer not null,
    hotspot_score real not null,
    computed_at text not null,
    head_sha text not null
);
```

### A3.3 Engine

New: `src/codescent/engine/git/cochange.py`

```python
def import_git_log(repo_root: Path, *, max_commits: int = 5000) -> int: ...

def rebuild_cochange_edges(repo_root: Path, *,
                           min_pair_count: int = 2,
                           max_files_per_commit: int = 50) -> int: ...

def compute_hotspots(repo_root: Path) -> tuple[HotspotRow, ...]: ...
```

`hotspot_score = log1p(churn_count) * avg_cognitive_complexity * (1 + log1p(open_finding_count))`.
Bounded to `[0, 100]` for stable ranking.

`max_files_per_commit` excludes mega-merge commits that would create
combinatorial pair explosions. Cap reads stdin from `git log --name-only` once,
in a single pass, no network.

### A3.4 Service and MCP surface

New: `src/codescent/services/hotspots.py` with `HotspotService(repo_root)`.

- New MCP tool: `get_hotspots(limit: int = 20, repo: str = ".")` ->
  `{ok, hotspots: [{path, hotspot_score, churn_count, open_finding_count, reasons: ["high churn", "high complexity", "open findings"]}], head_sha, computed_at}`
- New MCP tool: `get_cochanges(path: str, limit: int = 20, repo: str = ".")`
- Hook into existing services: `services/findings.py::get_next_improvement`
  multiplies finding rank by `1 + hotspot_score/100` for the finding's file;
  `services/context.py::get_related_files` adds co-change neighbors with reason
  `"co-changed in N commits"`; `services/risk.py` adds hotspot as a diff-risk
  factor.

Register in `src/codescent/mcp/repo_tools.py` (orientation-style).

### A3.5 Refresh policy

Co-change tables refresh on `codescent index --git` (new flag) or automatically
when `HEAD` differs from `hotspot_scores.head_sha`. Single write transaction.
Bounded reads.

### A3.6 Tests

- Unit: synthetic commit log -> deterministic edges, deterministic scores.
- Integration: real fixture repo with seeded git history; verify hotspot
  ordering and ranking lift in `get_next_improvement`.
- Contract: bounded MCP payloads; pagination on `get_hotspots`.
- Security: runtime safety test confirms `import_git_log` only calls `git`
  binary, no network.

### A3.7 Evidence

`scripts/prove_hotspot_ranking_lift.py` ->
`.omo/evidence/a3-hotspot-ranking.json` Compares `get_next_improvement` order
before and after enabling co-change scoring on a fixture; asserts that
hotspot-flagged files rise.

### A3.8 Effort and risks

- Effort: **S** (1 engineer, ~1.5 weeks).
- Risks: false coupling from formatter-style mega-commits — mitigated by
  `max_files_per_commit`; renames lose history — call
  `git log --follow --name-only` per file path on demand for hot files only.

---

# Phase B: Agent Leverage

## B1. Investigation Macros

### B1.1 Why

Today an agent investigating one symbol calls `find_symbol`, then
`get_symbol_context`, then `find_callers`, then `find_references`, then
`search_tests`, then `get_impact`. That is six roundtrips, six envelopes, six
chances to overflow. Server-side macros collapse them to one call, encode
investigative _doctrine_ (the right order), and reuse already-shipped services.
Highest leverage-per-LOC feature in this plan.

### B1.2 Macro definitions

A **Playbook** is a TOML file describing an ordered list of internal service
calls and merge rules:

```toml
# .codescent/playbooks/prep_to_edit.toml
name = "prep_to_edit"
description = "Investigate a symbol thoroughly before editing it."
target = "symbol"          # symbol | file | finding | diff

[[step]]
service = "context.find_symbol"
args.limit = 3

[[step]]
service = "context.get_symbol_context"
fan_out_from = "symbol_match.qualified_name"
join_as = "primary_context"

[[step]]
service = "context.find_callers"
fan_out_from = "primary_context.symbol"
join_as = "callers"

[[step]]
service = "search.search_tests"
fan_out_from = "primary_context.file_path"
join_as = "tests"

[[step]]
service = "planning.get_impact"
fan_out_from = "primary_context.symbol"
join_as = "impact"

[merge]
budget_tokens = 4000
deduplicate_files = true
include_anchors = true
```

Three built-in playbooks ship in `src/codescent/playbooks/`:

- `prep_to_edit.toml` — symbol target, full doctrine above.
- `understand_module.toml` — file/dir target; repo map slice + symbol list +
  cochange neighbors + related tests + finding summary.
- `pre_pr_review.toml` — diff target; combines `review_diff_risk`,
  `get_changed_file_health`, API ledger diff (when C2 ships), hotspot
  intersection.

User playbooks may live in `<repo>/.codescent/playbooks/`.

### B1.3 Engine

New: `src/codescent/engine/macros/runner.py`

```python
@dataclass(frozen=True, slots=True)
class MacroRunner:
    repo_root: Path | str
    playbook: Playbook
    token_budget: int

    def run(self, target: MacroTarget) -> MacroReport: ...
```

`MacroReport` is a bounded structured payload containing per-step results plus a
`summary` block and a `next_tools` field. Each step result is itself a small
envelope with `{step, ok, items, omitted_count}`.

Step execution is sequential (deterministic order matters), but each step's
fan-out runs concurrently bounded to N=4 with `asyncio` since all underlying
services are sync — wrap with `asyncio.to_thread`. Hard wall clock budget of
3000 ms by default.

### B1.4 Service and MCP surface

New: `src/codescent/services/macros.py` with `MacroService(repo_root)`.

MCP wrappers (one per built-in macro, plus a generic):

- `prep_to_edit(symbol: str, repo: str = ".") -> MacroReportPayload`
- `understand_module(path: str, repo: str = ".") -> MacroReportPayload`
- `pre_pr_review(repo: str = ".") -> MacroReportPayload`
- `run_playbook(playbook: str, target: dict, repo: str = ".")`

Register in `src/codescent/mcp/macros_tools.py`. Add all four to public surface
registry under group `macros`.

### B1.5 Tests

- Unit: playbook parser; fan-out join semantics; budget enforcement (oversized
  step result is summarized, not truncated silently).
- Integration: each built-in macro runs against `tests/fixtures/python-basic`
  and returns deterministic bounded payload.
- Contract: payload shape; playbook validation errors return structured
  envelopes; unknown playbook -> error envelope, not exception.

### B1.6 Evidence

`scripts/measure_macro_token_savings.py` ->
`.omo/evidence/b1-macro-savings.json` Runs the equivalent sequence of low-level
tool calls, then runs the macro, compares total input + output tokens. Asserts
macro reduces tokens by >=40% on the fixture.

### B1.7 Effort and risks

- Effort: **S-M** (1 engineer, ~2 weeks).
- Risks: prompt/tool name collisions if too many macros are registered -> cap
  built-ins at 3-5, custom playbooks expose only `run_playbook`; macros can hide
  non-determinism behind a thick API — mitigation: every macro payload includes
  a `steps_executed` block that lists each underlying tool call and its envelope
  so audits are still possible.

---

## B2. Compaction-Resilient Knowledge Cards

### B2.1 Why

Agents re-derive the same understanding of a subsystem every session because
chat context gets compacted. Cards give the agent code-grounded persistent
memory that self-invalidates when the underlying code changes (via A1 anchors).
Solves cross-session continuity without leaving the deterministic substrate.

### B2.2 Schema migration (v9)

```sql
create table if not exists knowledge_cards (
    id text primary key,
    project_id text not null,
    subject_kind text not null,         -- file | symbol | concept
    subject_anchor text,                -- semantic anchor string, nullable for concept
    subject_label text not null,
    title text not null,
    body_markdown text not null,
    evidence_json text not null,
    code_hash_at_write text,            -- file hash if subject_kind=file/symbol
    freshness text not null,            -- fresh | stale | invalidated
    author_session text,
    created_at text not null,
    last_verified_at text not null
);
create index if not exists knowledge_cards_subject_idx
    on knowledge_cards(subject_kind, subject_label);
create index if not exists knowledge_cards_freshness_idx
    on knowledge_cards(freshness);
```

Bounds: each card body <= 4 KB; evidence JSON <= 8 KB; max 500 cards per project
(oldest stale cards evicted first). All limits configurable via `[cards]`
section in project config.

### B2.3 Service

New: `src/codescent/services/cards.py`

```python
@dataclass(frozen=True, slots=True)
class CardsService:
    repo_root: Path | str

    def store_card(self, *, subject: CardSubject, title: str,
                   body_markdown: str, evidence: CardEvidence) -> Card: ...

    def recall_cards(self, *, query: str | None = None,
                     subject_label: str | None = None,
                     freshness: tuple[Freshness, ...] = ("fresh",),
                     limit: int = 10) -> tuple[Card, ...]: ...

    def invalidate_card(self, card_id: str, reason: str) -> Card: ...

    def refresh_freshness(self) -> FreshnessRefreshReport: ...
```

`refresh_freshness` runs on every successful scan: for each anchored card,
re-resolve the anchor (A1), compare current file/symbol hash to
`code_hash_at_write`, mark `stale` if changed, `invalidated` if
`drift_kind = missing`. Concept cards (no anchor) stay `fresh` until manually
invalidated.

### B2.4 MCP surface

- `store_card(subject_kind, subject_label, title, body_markdown, evidence_json, repo)`
- `recall_cards(query, subject_label, freshness, limit, repo)`
- `invalidate_card(card_id, reason, repo)`
- `refresh_card_freshness(repo)` (also called as a side effect of rescan)

Register in `src/codescent/mcp/cards_tools.py`. Add to public surface group
`memory`.

**Locked: `codescent cards reset` CLI ships with B2.** CLI-only (no MCP surface
for destructive ops, matching the existing `codescent reset` pattern). Gated
`--dry-run|--yes`. Subcommands:

- `codescent cards reset --dry-run|--yes` — drop all cards for the project.
- `codescent cards reset --freshness=stale,invalidated --yes` — purge only
  non-fresh cards.
- `codescent cards reset --older-than=30d --yes` — purge by age.

Rationale: a brand-new persistent store needs a recovery path. Keeping reset out
of MCP and behind explicit human consent matches `codescent reset` and keeps
agents from accidentally nuking memory. Add `cards` to
`POST_MVP_CLI_COMMAND_NAMES` in `core/public_surface.py`.

### B2.5 Search integration

`services/search.py::search_content` gets an additional ranking signal: matching
card bodies appear in a separate `cards` block in the envelope, clearly labeled,
with their own freshness annotation. Cards never replace source results — they
augment them.

### B2.6 Tests

- Unit: freshness state machine; eviction; body/evidence bounds.
- Integration: write a card anchored to a function, modify the function,
  refresh, assert card becomes stale.
- Contract: payload shapes; recall pagination; concept-card path (no anchor).
- Security: confirm card writes only touch `.codescent/`.

### B2.7 Evidence

`scripts/prove_card_lifecycle.py` -> `.omo/evidence/b2-card-lifecycle.json`
Writes a card, edits the underlying file, re-runs `refresh_freshness`, asserts
the card transitioned `fresh -> stale` and that `recall_cards` filters
correctly.

### B2.8 Effort and risks

- Effort: **M** (1 engineer, ~2.5 weeks).
- Risks: cards drift into ungrounded chat memory — mitigation: every card
  _requires_ `evidence` (anchors, file paths, or finding IDs), and tools refuse
  to store cards without evidence; cards become a janky note system —
  mitigation: hard caps on count and size, evidence-driven freshness, no
  search-quality dependency on cards.

---

## B3. AST-Shape Duplication + Slop Signature Pack

### B3.1 Why

Catches duplication that text-based detectors miss (variable-renamed copy-paste)
and ships the PRD's "suspicious AI slop pattern" promise as deterministic,
evidence-backed findings. Pure compute over the existing AST extractor; no new
dependencies.

### B3.2 Algorithm

For each function, method, and class:

1. Normalize the AST: rename identifiers to type+ordinal (`name_0`,
   `name_1`...), bucket literals (`STR`, `INT(>0)`, `INT(0)`, `FLOAT`, `NONE`,
   `TRUE`, `FALSE`).
2. Compute a structural hash over the normalized AST.
3. Group symbols by structural hash, filter to clusters with `count >= 2` and
   `min_lines >= 5`.
4. Compute a similarity score within near-clusters using normalized-AST
   tree-edit distance bounded to depth 3.

Output: `duplication_clusters` with
`{cluster_id, structural_hash, members: [anchor], total_lines, suggested_action}`.

### B3.3 Slop signature pack

New rule pack: `src/codescent/engine/rules/slop_signatures.py`

Initial deterministic signatures (each is an AST predicate, not a regex):

| Rule ID                           | Pattern                                                                                                          |
| --------------------------------- | ---------------------------------------------------------------------------------------------------------------- |
| `slop.empty_try_except`           | `try: ... except: pass` or `except Exception: pass`.                                                             |
| `slop.noop_facade_class`          | class with no methods and a single `__init__` that only assigns parameters.                                      |
| `slop.factory_of_factory`         | function whose body is exactly `return <Class>()` and `<Class>` is itself defined in same file with no behavior. |
| `slop.single_method_class`        | class with a single non-dunder method that takes no captured state.                                              |
| `slop.dead_default_optional`      | `Optional[X] = None` parameter never compared to `None` and never re-assigned in body.                           |
| `slop.redundant_alias_import`     | `from x import y as y` style.                                                                                    |
| `slop.suppressed_noqa_cluster`    | >=3 lines in a function with `# noqa` ignoring same rule.                                                        |
| `slop.over_abstracted_interface`  | abstract method with a single concrete implementation in same package.                                           |
| `slop.echo_logging`               | `logging.X("X")` where the string equals the call site function name.                                            |
| `slop.placeholder_implementation` | function body is `pass`, `...`, `raise NotImplementedError` only, and the function is referenced elsewhere.      |

Each rule emits a `CodeHealthFinding` with `severity=info|warning`,
`confidence=0.7-0.95`, anchored via A1.

### B3.4 Engine module

New: `src/codescent/engine/duplication/ast_shape.py`

```python
def compute_structural_hash(node: ast.AST) -> str: ...

def cluster_duplicates(parsed_files: Iterable[ParsedPythonFile], *,
                       min_lines: int = 5) -> tuple[DuplicateCluster, ...]: ...
```

Wired into `services/code_health.py::scan` as an additional finding source,
producing `python.duplicate_ast_cluster` findings with cluster evidence.

### B3.5 Tests

- Unit: each signature with positive and negative fixtures; normalization
  invariants (`a = 1` vs `b = 2` produce same hash but `a = 1` vs `a = []` do
  not).
- Integration: scan a fixture with seeded duplicates and slop, assert expected
  rule fires.
- Contract: bounded output; cluster member count caps.

### B3.6 Evidence

`scripts/prove_slop_detection.py` -> `.omo/evidence/b3-slop-detection.json` Runs
the new rules over a curated fixture `tests/fixtures/python-slop/` (new) that
demonstrates each signature, asserts 1:1 finding-to-fixture coverage.

### B3.7 Effort and risks

- Effort: **M** (1 engineer, ~2.5 weeks).
- Risks: false positives on legitimate facades — every rule emits with
  `confidence < 1.0` and links to docstring guidance; clustering blowup on
  generated code — exclude `is_generated` files from clustering.

---

# Phase C: Code Intelligence Depth

## C1. Architectural Fitness Functions + NL->Rule Compiler

### C1.1 Why

Agents are notoriously bad at respecting unwritten architecture. Make the
architecture writable, queryable through `scan_code_health`, and enforceable in
CI. The NL->rule compiler lets developers describe a constraint in English
without learning a DSL.

### C1.2 Architecture config

New file at `<repo>/.codescent/architecture.toml`:

```toml
[layers]
domain   = ["src/myapp/domain/**"]
services = ["src/myapp/services/**"]
web      = ["src/myapp/web/**"]
storage  = ["src/myapp/storage/**"]

[[layer_rule]]
name = "domain has no outward imports"
layer = "domain"
forbid_imports_from = ["services", "web", "storage"]
severity = "error"

[[layer_rule]]
name = "web cannot import storage directly"
forbid_imports = [{ from = "web", to = "storage" }]
severity = "warning"

[[naming_rule]]
name = "service classes end with Service"
applies_to = "src/myapp/services/**/*.py"
pattern = { kind = "class", suffix = "Service" }

[[complexity_rule]]
name = "services stay simple"
applies_to = "src/myapp/services/**/*.py"
max_cognitive_complexity_per_function = 15

[[public_api_rule]]
name = "domain exports listed allow-list"
applies_to_file = "src/myapp/domain/__init__.py"
exports_must_include = ["User", "Order", "Cart"]
```

Schema is validated by a new Pydantic model in
`src/codescent/core/architecture_config.py`. Missing file is not an error — the
rule pack is simply skipped.

### C1.3 Rule pack

New: `src/codescent/engine/rules/architecture.py`

Reads `architecture.toml`, evaluates each rule against the indexed import graph
and symbol table, emits findings:

- `architecture.layer_violation`
- `architecture.naming_violation`
- `architecture.complexity_violation`
- `architecture.public_api_violation`

Each finding's evidence cites the source file path, target file path, and the
relevant rule name from the config.

### C1.4 NL->rule compiler

**Locked: ships in Q3 with C1.** Without the compiler, C1 forces every user to
learn the architecture TOML schema before they can author a single rule, which
kills adoption. The compiler is the lowest-cost piece of C1 (no LLM, no network,
~15 regex-style sentence templates) and it is the most natural
agent-authored-rules surface — exactly on-brand for an MCP-first product. Safety
is contained because the compiler returns _candidates only_; it never writes
`architecture.toml` itself.

New: `src/codescent/services/architecture_compiler.py`

Template-driven (no LLM). Recognizes ~15 sentence patterns:

- "<X> may not import from <Y>" -> `forbid_imports`
- "<X> classes must end with <Suffix>" -> `naming_rule`
- "<X> must not exceed complexity <N>" -> `complexity_rule`
- "<file> must export <names>" -> `public_api_rule`

Returns a previewed TOML snippet plus a dry-run match count
(`would_match: N files`). Never writes the TOML directly — agent or human copies
the snippet. When multiple templates match a single sentence, all candidates are
returned and the caller picks one — no implicit disambiguation.

### C1.5 Surface

- New CLI: `codescent architecture compile "<sentence>"` -> prints the candidate
  TOML rule and dry-run match count.
- New CLI: `codescent architecture check` -> runs only the architecture rule
  pack and prints a human-readable report.
- New MCP tool: `architecture_compile(sentence: str, repo: str = ".")` for
  agent-driven rule authoring.
- New MCP tool: `architecture_violations(limit: int = 50, repo: str = ".")`
  returns architecture-only findings.

### C1.6 Tests

- Unit: each rule type with positive/negative cases; config schema validation;
  NL compiler covers each pattern with at least three phrasings.
- Integration: fixture repo with intentional layer violations.
- Contract: MCP payload shapes; CLI exit codes (non-zero on
  `--fail-on-violation`).

### C1.7 Evidence

`scripts/prove_architecture_enforcement.py` ->
`.omo/evidence/c1-architecture.json` Loads a fixture with seeded violations and
a hand-written `architecture.toml`, asserts each expected finding appears.

### C1.8 Effort and risks

- Effort: **M** (1 engineer, ~3 weeks).
- Risks: TOML schema bloat — keep additive; NL compiler ambiguity — when
  multiple templates match, return all candidates and require user choice; glob
  expansion on huge repos — reuse existing inventory walker.

---

## C2. Public API Ledger

### C2.1 Why

Agents reflexively break public APIs because they only see the function they're
editing. A snapshot-and-diff of every module's exported surface catches
signature, exception, and return-type breakage _before_ the change lands. Pairs
with A1 anchors for stability across formatting.

### C2.2 Schema migration (v10)

```sql
create table if not exists api_snapshots (
    id text primary key,                -- ULID
    head_sha text not null,
    created_at text not null
);

create table if not exists api_symbols (
    snapshot_id text not null references api_snapshots(id) on delete cascade,
    file_path text not null,
    qualified_name text not null,
    kind text not null,                 -- function | class | method | constant
    signature text not null,
    return_type text,
    exceptions_json text not null,      -- list[str]
    decorators_json text not null,
    anchor_text text,
    visibility text not null,           -- public | private | dunder
    primary key (snapshot_id, qualified_name)
);
```

### C2.3 Engine

New: `src/codescent/engine/api/extractor.py`

```python
def extract_public_api(
    parsed_files: Iterable[ParsedPythonFile]
) -> tuple[ApiSymbol, ...]: ...

def diff_api(before: tuple[ApiSymbol, ...],
             after: tuple[ApiSymbol, ...]) -> ApiDiff: ...
```

Visibility: leading underscore -> `private`; dunder -> `dunder`; else `public`.
`from x import y` re-exports counted as public surface of the re-exporting
module.

`ApiDiff` categorizes each change as one of:

- `removed` (highest severity)
- `signature_changed` (param added, removed, reordered, type changed)
- `return_type_narrowed`
- `return_type_widened`
- `exception_added` (callers must now handle a new exception)
- `exception_removed`
- `decorator_changed` (e.g. `@staticmethod` added)
- `added` (informational)

### C2.4 Service and MCP surface

New: `src/codescent/services/api_ledger.py`

```python
@dataclass(frozen=True, slots=True)
class ApiLedgerService:
    repo_root: Path | str

    def snapshot(self, *, head_sha: str | None = None) -> ApiSnapshotRow: ...

    def diff(self, *, since: str = "HEAD~1") -> ApiDiff: ...

    def find_callers_of_removed(self, diff: ApiDiff) -> tuple[CallerRow, ...]:
        ...
```

- New MCP tool: `get_api_changes(since: str = "HEAD~1", repo: str = ".")`
- New MCP tool: `get_breaking_callers(since: str = "HEAD~1", repo: str = ".")`
  -> for each removed/signature-changed export, returns the in-repo call sites
  that would break.
- Hook: `services/risk.py::review_diff_risk` includes a `breaking_api_changes`
  block in its payload.

**Locked: `get_breaking_callers` returns direct callers only in v1.** Payload
includes a top-level `transitive: false` field and reserves a `transitive`
parameter slot in the tool signature for v2:

```python
def get_breaking_callers(
    since: str = "HEAD~1",
    transitive: bool = False,   # reserved; must be False in v1
    repo: str = ".",
) -> BreakingCallersPayload: ...
```

If `transitive=True` is passed in v1, return a structured warning envelope
(`warning_code = "transitive_not_implemented_in_v1"`). Rationale: direct callers
are bounded `O(call_edges lookup)` and easy to explain in evidence; transitive
expansion is unbounded on hub modules and would routinely blow the envelope's
token budget. Agents needing transitive breakage today can iterate one hop at a
time by calling `get_breaking_callers` on each direct caller.

New deterministic finding rules in `src/codescent/engine/rules/api_breakage.py`,
fired during scan when a fresh diff against `HEAD~1` shows breakage:

- `api.removed_public_symbol`
- `api.breaking_signature_change`
- `api.widened_exception_set`

### C2.5 Tests

- Unit: extractor classification; diff categorization for each change type;
  re-export handling.
- Integration: snapshot fixture, mutate, diff, assert each category fires.
- Contract: bounded payloads; missing-`HEAD~1` returns warning envelope, not
  exception.

### C2.6 Evidence

`scripts/prove_api_diff.py` -> `.omo/evidence/c2-api-diff.json` Scenario:
snapshot a fixture, apply a curated breaking change, diff, assert expected
categories and breaking caller list.

### C2.7 Effort and risks

- Effort: **M** (1 engineer, ~3 weeks).
- Risks: dynamic Python (decorators that change signatures) — record raw
  signature and a `dynamic: true` flag; reads `git show HEAD~1` for the previous
  state — gated behind a "git available" check, no network.

---

# Phase D: Verification Headline

## D1. Test Impact + Mutation-Light

### D1.1 Why

"Which tests should I run?" answered by call-graph traversal in milliseconds.
"Do those tests actually have teeth?" answered by a handful of fast mutations.
Pairs directly with D2 to give agents a real verification answer before changes
land.

### D1.2 Test impact

New: `src/codescent/services/test_impact.py`

```python
@dataclass(frozen=True, slots=True)
class TestImpactService:
    repo_root: Path | str

    def impact_for_symbols(
        self, qualified_names: Sequence[str]
    ) -> TestImpactReport: ...

    def impact_for_diff(
        self, *, since: str = "HEAD"
    ) -> TestImpactReport: ...
```

`TestImpactReport` contains `relevant_tests: tuple[TestRef, ...]` with each test
annotated by a confidence (`exact_call`, `references_module`, `colocated`).
Traverses the existing `call_edges` and `symbol_references` tables — no new
storage needed.

### D1.3 Mutation-light engine

New: `src/codescent/engine/mutation/mini_mutators.py`

Mutators (each is an AST transformation, applied to one node at a time):

| Mutator             | Transform                                           |
| ------------------- | --------------------------------------------------- |
| `bool_flip`         | `True` <-> `False`                                  |
| `compare_op_swap`   | `<` <-> `<=`, `>` <-> `>=`, `==` <-> `!=`           |
| `arith_swap`        | `+` <-> `-`, `*` <-> `/`                            |
| `bound_off_by_one`  | `range(n)` -> `range(n - 1)`                        |
| `return_constant`   | replace function body with `return 0` (last resort) |
| `drop_early_return` | remove guard-style `if cond: return`                |
| `negate_condition`  | `if cond` -> `if not cond`                          |

Each mutator emits at most one mutation per AST node per run.

New: `src/codescent/services/mutation_light.py`

```python
@dataclass(frozen=True, slots=True)
class MutationLightService:
    repo_root: Path | str

    def score_symbol(
        self, qualified_name: str, *,
        max_mutations: int = 20,
        wall_clock_seconds: float = 30.0,
    ) -> MutationScore: ...
```

`MutationScore`:
`{mutations_run, killed, survived, survival_rate, survivor_examples: tuple[MutationDetail, ...]}`.

Mutations run inside an ephemeral worktree (shared sandbox harness with D2, see
D2.3). Only the tests returned by `TestImpactService.impact_for_symbols` are
executed. Wall-clock and mutation count caps are hard.

### D1.4 MCP surface

- New: `get_test_impact(symbols: list[str] = [], since: str = "", repo)`
- New: `score_test_strength(symbol: str, repo: str = ".")` (opt-in heavy)

`score_test_strength` is gated behind
`[verification].mutation_light_enabled = true` in project config. Default off.

### D1.5 Tests

- Unit: each mutator (positive/negative transformation behavior).
- Integration: fixture with strong tests + fixture with weak tests, assert
  survival rate differs.
- Contract: payload shapes; gating works; wall-clock cap honored.
- Security: confirm mutations only touch ephemeral worktree, never repo.

### D1.6 Evidence

`scripts/prove_mutation_detection.py` ->
`.omo/evidence/d1-mutation-detection.json` Runs against a fixture symbol with
two test suites (weak vs. strong), asserts strong suite kills >=90% of mutations
and weak suite kills <=30%.

### D1.7 Effort and risks

- Effort: **M** (2 engineers, ~3 weeks; can parallel with D2 sandbox work).
- Risks: mutation runs longer than budget — hard cap and progress reporting;
  flaky tests inflate survival rate — flag any test that fails on the unchanged
  baseline and exclude it from scoring with a `flaky_test_excluded` warning.

---

## D2. Behavior-Preservation Oracle (Sandbox `try_change`)

### D2.1 Why

The single biggest missing primitive in agentic coding: `verify_change` today
returns _recommendations_, not evidence. The Oracle takes a proposed change,
applies it to an ephemeral git worktree (analyzed repo stays read-only), runs
the right tests, and returns structured pass/fail evidence. Combined with D1,
this is the safety harness CodeScent has been building toward.

### D2.2 Opt-in only

The Oracle ships **off by default** and only activates when project config
explicitly opts in:

```toml
[verification]
sandbox_enabled = true
sandbox_dir = ".codescent/sandbox"
allowed_commands = ["pytest", "uv run pytest", "ruff check .",
                    "uv run basedpyright"]
wall_clock_seconds = 180
max_diff_lines = 2000
```

`allowed_commands` is an exact-prefix allow-list. Any other command is refused
with a structured error. No shell metacharacters allowed. Environment variables
sanitized (`PATH` only).

**Locked: Python-only in v1. No TS/React parity.** Rationale: D2 is already the
single highest-risk capability in CodeScent's history (subprocess execution);
adding TS parity in v1 would double the safety surface by forcing decisions
about npm/pnpm/yarn variance, jest/vitest fragmentation, tsconfig discovery,
node version pinning, and the security implications of node's broader
native-module ecosystem — all before the Python path has proven itself. The
`engine/sandbox/worktree.py` harness is intentionally language-agnostic (git
worktree + allow-listed commands + sanitized env), so TS support lands cleanly
in v3 by extending `allowed_commands` defaults and adding a TS-aware impact-set
resolver. v1 refuses to run when the project's `language_packs` contains
`typescript` and `sandbox_enabled = true` without an explicit
`verification.python_only_acknowledged = true` flag in the project config — this
prevents silent partial coverage.

### D2.3 Sandbox harness

New: `src/codescent/engine/sandbox/worktree.py`

```python
@dataclass(frozen=True, slots=True)
class SandboxWorktree:
    sandbox_root: Path
    commit_sha: str

    def __enter__(self) -> "SandboxWorktree": ...
    def __exit__(self, *exc) -> None: ...

    def apply_unified_diff(self, diff_text: str) -> AppliedDiffReport: ...
    def apply_codemod(self, codemod: CodemodSpec) -> AppliedDiffReport: ...

    def run_command(self, command: str, *,
                    timeout_seconds: float) -> CommandResult: ...
```

Implementation:

1. `git worktree add --detach .codescent/sandbox/<id> HEAD`
2. Apply the diff via `git apply --index --whitespace=nowarn` inside the
   worktree.
3. Run only allow-listed commands with `subprocess.run`, `cwd=` set to the
   worktree, `env` sanitized, `timeout=` from config.
4. On exit, `git worktree remove --force .codescent/sandbox/<id>`.

The sandbox lives under `.codescent/sandbox/` so it is automatically excluded
from indexing and is removed by `codescent reset`.

### D2.4 Service

New: `src/codescent/services/oracle.py`

```python
@dataclass(frozen=True, slots=True)
class BehaviorReport:
    sandbox_id: str
    applied: bool
    diff_summary: DiffSummary
    impact_set: tuple[str, ...]
    tests: TestSummary               # passed, failed, skipped, duration
    typecheck: CommandSummary | None
    lint: CommandSummary | None
    new_findings: tuple[FindingRef, ...]
    resolved_findings: tuple[FindingRef, ...]
    api_diff: ApiDiff | None         # from C2 when available
    confidence: float                # 0..1, lower if impact set is wide
    warnings: tuple[str, ...]

@dataclass(frozen=True, slots=True)
class OracleService:
    repo_root: Path | str

    def try_change(self, *, diff_text: str | None = None,
                   codemod: CodemodSpec | None = None,
                   finding_id: str | None = None,
                   token_budget: int = 6000) -> BehaviorReport: ...
```

Flow:

1. Refuse if `sandbox_enabled = false` or diff exceeds `max_diff_lines`.
2. Compute the impact set via D1 `TestImpactService` (over the _applied_
   worktree's symbols).
3. Open `SandboxWorktree`, apply diff, run scoped test command from
   `commands.test`, then typecheck, then lint, each under wall-clock budget.
4. Compare scan results before and after to detect `new_findings` and
   `resolved_findings`.
5. If C2 available, include `api_diff`.
6. Return `BehaviorReport`. Worktree is cleaned up on every code path.

### D2.5 MCP surface

- New MCP tool:
  `try_change(diff_text: str = "", finding_id: str = "", repo: str = ".") -> TryChangeToolPayload`
- New MCP tool: `try_codemod(codemod_json: str, repo: str = ".")` (codemod spec
  deferred to v2 of this feature; v1 is unified-diff input).
- Augment: `verify_change` (existing) gains a `sandbox_report` field when
  sandbox is enabled. When sandbox is disabled, behavior is unchanged.

Register in `src/codescent/mcp/oracle_tools.py`. Add to public surface group
`planning`.

### D2.6 Tests

- Unit: command allow-list parser (must reject path traversal, env mutation,
  shell metacharacters, unknown binaries); diff applier; impact set computation.
- Integration: apply a green diff, expect `tests.failed = 0`; apply a red diff,
  expect `tests.failed > 0`; apply a diff that exceeds `max_diff_lines` and
  assert refusal envelope; apply a diff that introduces a new finding and assert
  `new_findings` is populated.
- Contract: payload shapes; sandbox cleanup verified after every test (no
  leftover `.codescent/sandbox/*` directories).
- Security: extensive runtime safety tests in
  `tests/security/test_runtime_safety.py`: command allow-list enforcement, no
  network access during command execution, sandbox path cannot escape
  `.codescent/sandbox`, original worktree files are byte-identical before and
  after.

### D2.7 Evidence

`scripts/prove_oracle_behavior.py` -> `.omo/evidence/d2-oracle.json` Three
scenarios:

1. **Green path**: apply a refactor that preserves behavior, assert
   `tests.failed == 0`, `new_findings = ()`.
2. **Red path**: apply a behavior-changing edit, assert `tests.failed > 0` and
   `BehaviorReport.applied is True`.
3. **Containment proof**: verify byte-identity of every file in the repo root
   (excluding `.codescent/`) before and after the run.

All three are written to a single JSON artifact for audit.

### D2.8 Effort and risks

- Effort: **L** (2 engineers, ~5 weeks).
- Risks: subprocess execution is the highest-risk new capability in CodeScent's
  history — mitigated by opt-in config, exact-prefix allow-list, sanitized env,
  hard wall-clock, security test suite, and updated `prove_source_read_only.py`
  that verifies repo bytes unchanged even when sandbox runs; flaky tests cause
  noisy reports — re-run failed tests once with a flake annotation; sandbox
  creation is slow on big repos — keep a warm pool of pre-created worktrees
  behind a feature flag (`sandbox_pool_size = 0` by default).

---

# Cross-Cutting Deliverables

## CC1. Documentation updates

For each feature, the same PR that lands the code must update:

| Doc                     | What to add                                                  |
| ----------------------- | ------------------------------------------------------------ |
| `docs/mcp-tools.md`     | One reference entry per new tool with shape and bounds.      |
| `docs/architecture.md`  | Service and engine module additions in section 7/8.          |
| `docs/cli-reference.md` | New CLI commands.                                            |
| `docs/workflows.md`     | One snippet showing the new tool in agent use.               |
| `docs/prd.md`           | Add feature to "Phased Roadmap" with explicit phase mapping. |

## CC2. Contract test updates

Each feature must extend:

- `tests/contract/test_public_surface_registry.py` — assert new tool/CLI appears
  with correct stage/group.
- `tests/contract/test_mcp_tool_surface.py` — assert tool descriptions contain
  the required safety wording ("Writes only local .codescent state", "Read-only
  for source files", etc.).
- `tests/contract/test_mcp_<group>_tools.py` — payload shape contract.

## CC3. AGENTS.md updates

When a feature adds a new top-level module (e.g. `services/cards.py`,
`engine/sandbox/`, `engine/macros/`), update the relevant `AGENTS.md` table.

## CC4. Schema migration policy

- One migration per feature. Never combine.
- Migration adds new tables or new columns only. No destructive changes.
- Every migration ships with a test under
  `tests/contract/migrations/test_v<N>_to_v<N+1>.py` that loads a pre-migration
  snapshot and asserts post-migration invariants.

## CC5. Public surface stage transitions

All new MCP tools enter as `POST_MVP_MCP_TOOL_NAMES` registered entries. None
are added to `MVP_MCP_TOOL_NAMES`. CLI commands follow the same pattern.

## CC6. Read-only proof must keep passing

`scripts/prove_source_read_only.py` is extended whenever the public MCP surface
changes. After D2 lands, the script also asserts that the Oracle sandbox leaves
analyzed source bytes unchanged.

## CC7. Telemetry

All new services that produce findings or measurable agent value must emit a
structured event to `session_events` via existing `SessionEventRepository`. This
is what makes A2's ROI numbers meaningful.

---

# Risk Summary

| Risk                                                      | Severity | Mitigation                                                                                |
| --------------------------------------------------------- | -------- | ----------------------------------------------------------------------------------------- |
| Sandbox subprocess broadens attack surface (D2)           | High     | Opt-in, exact-prefix allow-list, sanitized env, security test suite, byte-identity proof. |
| Anchor migration produces unstable IDs on real repos (A1) | High     | Backfill behind a feature flag, before/after stable_key comparison test on real fixtures. |
| Macros hide tool calls and undermine determinism (B1)     | Med      | Every macro payload includes `steps_executed` audit block.                                |
| Mutation runs blow time budget (D1)                       | Med      | Hard caps, gated opt-in, flaky test exclusion.                                            |
| Architecture rules become a bikeshed (C1)                 | Med      | Ship with three sensible defaults; rules are additive, not enforced unless declared.      |
| API ledger noisy on dynamic Python (C2)                   | Med      | `dynamic: true` flag; lower severity for dynamic-flagged diffs.                           |
| Card store rots into ungrounded notes (B2)                | Low      | Evidence required; freshness state machine; eviction caps.                                |
| Co-change skew from mega-merges (A3)                      | Low      | `max_files_per_commit` cap on edge creation.                                              |
| Token ledger estimates are wrong by provider (A2)         | Low      | Pluggable estimator, clearly labeled estimate, never billed as truth.                     |
| Slop signatures false-positive on legitimate facades (B3) | Low      | Lower confidence on subjective rules; per-rule disable in config.                         |

---

# Locked Decisions

Locked 2026-06-15. Each decision is folded into the relevant feature section
above; this is the canonical short-form record.

| ID   | Question                                                       | Decision                                                                                                                             | Rationale                                                                                                                                                                                                                                                               |
| ---- | -------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| LD-1 | D2 sandbox: TS/React parity in v1?                             | **No — Python-only in v1.** TS follows in v3.                                                                                        | D2 is the highest-risk new capability; doubling the safety surface before Python is proven is unjustified. The harness is language-agnostic so TS is a clean additive follow-up. Guarded by `verification.python_only_acknowledged` to prevent silent partial coverage. |
| LD-2 | C1: ship NL->rule compiler with C1 or defer?                   | **Ship with C1.**                                                                                                                    | Without the compiler, C1 forces every user to learn the TOML schema before authoring a single rule, killing adoption. Compiler is the cheapest piece (no LLM, no network, ~15 templates) and returns _candidates only_ — no auto-apply, so the risk is bounded.         |
| LD-3 | B2: admin reset path in v1?                                    | **Yes — `codescent cards reset` CLI ships with B2.** CLI-only, gated `--dry-run\|--yes`.                                             | A new persistent store without a recovery path is a bad failure mode. Mirrors the existing `codescent reset` pattern. CLI-only (not MCP) keeps destructive ops out of agent reach.                                                                                      |
| LD-4 | A2: can `recommend_budget` auto-apply via project-config flag? | **No — strictly CLI-gated forever.** No `auto_apply` flag will ever exist.                                                           | Determinism is the product's identity. Silent default-shrinking would make the same bounded tool call return different results across runs and create an un-debuggable test surface. CI users can pipe `--yes` after review.                                            |
| LD-5 | C2: `get_breaking_callers` transitive or direct in v1?         | **Direct only.** `transitive` parameter slot reserved for v2; passing `transitive=True` in v1 returns a structured warning envelope. | Direct callers are bounded `O(call_edges)` and explainable in evidence. Transitive is unbounded on hub modules and would routinely blow the envelope's token budget. Agents needing more can iterate one hop at a time.                                                 |

## What changes downstream of these decisions

- **D2 Q4 scope**: Python parser/test runner only. TS sandbox added to a v3
  roadmap doc when the time comes.
- **C1 Q3 scope**: includes `architecture_compile` MCP tool, the
  `codescent architecture compile` CLI subcommand, and the
  `services/architecture_compiler.py` service module.
- **B2 Q2 scope**: includes `codescent cards reset` CLI subcommand plus `cards`
  entry in `POST_MVP_CLI_COMMAND_NAMES`.
- **A2 Q1 scope**: ships `codescent budgets apply --dry-run|--yes` as the sole
  write path; no project-config auto-apply flag is added to `ProjectConfig` in
  `core/models.py`.
- **C2 Q3 scope**: `get_breaking_callers` signature includes
  `transitive: bool = False` parameter; v1 unconditionally refuses
  `transitive=True` with `warning_code = "transitive_not_implemented_in_v1"`.

## v3 backlog (deferred by these decisions)

These items are explicitly out of scope for this plan and queued for a future v3
roadmap:

- TS/React sandbox parity for D2 (new `engine/sandbox/typescript.py` impact
  resolver, TS-aware `allowed_commands` defaults, pnpm/yarn/bun support).
- Transitive `get_breaking_callers` with bounded BFS depth and an envelope
  truncation strategy.
- LLM-assisted NL->rule expansion for ambiguous sentences not covered by the C1
  template set.

Nothing else in this plan is gated on these v3 items. Everything in sections 1
through D2.8 is buildable as written.
