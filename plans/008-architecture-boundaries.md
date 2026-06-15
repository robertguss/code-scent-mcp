# Plan 008: Enforce architecture boundary constraints from config

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving on. If a
> STOP condition occurs, stop and report — do not improvise. When done, update
> the status row for this plan in `plans/README.md`.
>
> **Drift check (run first)**:
> `git diff --stat 40cbf50..HEAD -- src/codescent/core/models.py src/codescent/engine/rules src/codescent/engine/packs.py src/codescent/services/code_health.py tests plans/README.md`
> If any in-scope file changed, compare excerpts against live code; on a
> mismatch, treat it as a STOP condition.

## Status

- **Priority**: P1
- **Effort**: M
- **Risk**: MED
- **Depends on**: none
- **Category**: direction (new deterministic rule) / tech-debt guardrail
- **Planned at**: commit `40cbf50`, 2026-06-15

## Why this matters

AI agents routinely create spaghetti by importing across layers to make
something work (e.g. a `services` module importing `cli`, or `engine` importing
`dashboard`). CodeScent already extracts imports per file but enforces no
intended architecture. Letting a maintainer declare forbidden layer dependencies
in config and flagging violations deterministically turns the tribal knowledge
in this repo's own `AGENTS.md` ("Do not import FastMCP or Typer in services")
into an enforced, evidence-backed finding. This is the highest- leverage way to
keep an AI-maintained codebase structurally sound.

## Current state

- Config is a frozen Pydantic model. New config sections go here:

```python
# src/codescent/core/models.py:78-92
class ProjectConfig(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)
    include: tuple[str, ...] = (".",)
    ...
    rule_packs: tuple[str, ...] = ("python-maintainability", "ts-react-next")
    commands: CommandHints = Field(default_factory=CommandHints)
    token_budgets: TokenBudgets = Field(default_factory=TokenBudgets)
    privacy: PrivacySettings = Field(default_factory=PrivacySettings)
    llm: LlmSettings | None = None
```

- Rules emit `CodeHealthFinding` via `build_finding(FindingSpec(...))`:

```python
# src/codescent/engine/rules/python.py:59-74  (pattern to copy)
    build_finding(
        FindingSpec(
            rule_id="python.large_file",
            title="Large Python file",
            message=f"{parsed.path} has {line_count} lines.",
            file_path=parsed.path,
            symbol=None,
            severity="warning",
            confidence=0.9,
            evidence={"line_count": line_count, "threshold": LARGE_FILE_LINES},
            suggested_action="Split cohesive responsibilities into smaller modules.",
        ),
    )
```

- The Python parser exposes imports already; each `ParsedImport` has `.module`
  (e.g. `"codescent.services.git"` or relative `".context"`) and `.name`:

```python
# src/codescent/engine/parsers/python.py:54-67
@dataclass(frozen=True, slots=True)
class ParsedImport:
    module: str
    name: str | None
    line: int
    confidence: float
```

- Rule packs are wired through `build_pack_registry` →
  `registry.scan_rule_packs(root)` (see `src/codescent/engine/packs.py:62-66`
  and `109-127`). The scan loop is in
  `src/codescent/services/code_health.py:40-50`.

Repo conventions: strict typing; preserve unknown TOML on config save (see
`src/codescent/services/config.py` `save_rule_packs`); separate deterministic
findings; no network.

## Commands you will need

| Purpose       | Command                                             | Expected |
| ------------- | --------------------------------------------------- | -------- |
| Focused tests | `uv run pytest tests -k "boundary or architecture"` | exit 0   |
| Full tests    | `uv run pytest`                                     | exit 0   |
| Lint          | `uv run ruff check .`                               | exit 0   |
| Format        | `uv run ruff format --check .`                      | exit 0   |
| Typecheck     | `uv run basedpyright`                               | exit 0   |

## Scope

**In scope**:

- `src/codescent/core/models.py` — add an `ArchitectureRules` model + field on
  `ProjectConfig`.
- `src/codescent/engine/rules/architecture.py` (create) — the boundary scanner.
- `src/codescent/engine/packs.py` — register an `architecture` rule pack.
- `src/codescent/services/config.py` — round-trip the new config section
  (preserve raw TOML).
- `tests/unit/` and/or `tests/integration/` — boundary rule tests.
- `docs/configuration.md` — document the new section (1 short block).
- `plans/README.md` status row.

**Out of scope**:

- Do NOT auto-fix imports or edit analyzed source.
- Do NOT change existing rule IDs or finding shapes.
- Do NOT make the rule run when no architecture rules are configured (must be
  zero findings and near-zero cost by default — opt-in).
- `tests/fixtures/` source.

## Git workflow

- Branch: `advisor/008-architecture-boundaries`. Conventional commits. No push.

## Steps

### Step 1: Add the config model

In `src/codescent/core/models.py`, add (place near the other settings models):

```python
class ArchitectureRule(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)
    # A layer is matched by path prefix, e.g. "src/codescent/services".
    layer: str
    # Path-prefix or dotted-module prefixes this layer must NOT import.
    forbidden_imports: tuple[str, ...] = ()


class ArchitectureRules(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)
    rules: tuple[ArchitectureRule, ...] = ()
```

Add to `ProjectConfig`:
`architecture: ArchitectureRules = Field(default_factory=ArchitectureRules)`.

### Step 2: Write the boundary scanner

Create `src/codescent/engine/rules/architecture.py` with:

```python
def scan_architecture(
    root: Path | str,
    *,
    config: ProjectConfig | None = None,
) -> tuple[CodeHealthFinding, ...]:
    ...
```

Logic (mirror `scan_python_health`'s structure in
`engine/rules/python.py:31-50`):

- If `config.architecture.rules` is empty, return `()` immediately.
- Iterate `build_file_inventory(repo_root, config=...)`; for python files,
  `parse_python_file(...)`.
- For each `rule` whose `layer` is a path prefix of the file's path, check every
  `ParsedImport.module`. A violation = the import's module (normalized) starts
  with any string in `rule.forbidden_imports`. Normalize dotted modules
  (`codescent.cli.main`) and treat a forbidden entry like `codescent.cli` as a
  dotted-prefix match.
- Emit a `build_finding` with `rule_id="architecture.boundary_violation"`,
  `severity="warning"`, `confidence=0.95`, `symbol=None`,
  `evidence={"layer": rule.layer, "imported": module, "line": import.line}`,
  `suggested_action="Remove the cross-layer import or move the shared code to an allowed layer."`

Note on `evidence` typing: `FindingSpec.evidence` is
`dict[str, int | float | str | bool]` (see `engine/rules/model.py:6`). Keep
values to those scalar types.

### Step 3: Register the rule pack

In `src/codescent/engine/packs.py`, add an `architecture` rule pack that runs
`scan_architecture`. Gate it so it is always safe to run (it self-disables when
no rules are configured). Add it to the default `rule_packs` OR run it
unconditionally inside the scan — choose the always-run-but-self-disable path so
existing config files keep working. Follow the `_rule_packs` /
`_scan_python_health` pattern at `packs.py:109-134`.

### Step 4: Round-trip config

In `src/codescent/services/config.py`, ensure loading parses the
`[architecture]`/`rules` section into the model (Pydantic `model_validate`
already does this via `_parse_config`). If you add a save path for architecture
rules, preserve unknown TOML exactly like `save_rule_packs` does. (If you do not
add a save path, no change needed here — verify load works via a test.)

**Verify**: `uv run pytest tests -k architecture` → exit 0 after Step 5.

### Step 5: Tests

- Unit test `scan_architecture` directly: build a temp repo with
  `src/app/services/x.py` importing `app.cli.main`, a config with a rule
  `layer="src/app/services", forbidden_imports=("app.cli",)`, assert one
  `architecture.boundary_violation` finding with the right evidence.
- Negative test: same repo, empty `architecture.rules` → zero findings.
- Use the inventory/temp-repo idiom from existing rule tests under `tests/`.

**Verify**: `uv run pytest`, `ruff check .`, `ruff format --check .`,
`basedpyright` → all exit 0.

### Step 6: Document

Add a short `[architecture]` example to `docs/configuration.md`.

## Test plan

- `scan_architecture` violation detected; evidence has `layer`, `imported`,
  `line`.
- Self-disables with empty config (zero findings, no crash).
- Config load parses the new section.
- Verification: `uv run pytest` → all pass.

## Done criteria

- [ ] New rule `architecture.boundary_violation` exists and only fires when
      configured.
- [ ] Default behavior (no `[architecture]` config) produces zero new findings.
- [ ] `uv run pytest`, `ruff check`, `ruff format --check`, `basedpyright`
      exit 0.
- [ ] `docs/configuration.md` documents the section.
- [ ] No analyzed source edited; `tests/fixtures/` untouched.
- [ ] `plans/README.md` status row for 008 updated.

## STOP conditions

Stop and report if:

- Adding `architecture.boundary_violation` requires registering a new MCP tool
  or changing `core/public_surface.py` (it should not — findings flow through
  the existing scan/report tools).
- Module-prefix matching is ambiguous for relative imports (`.context`) in a way
  that produces false positives — report the cases rather than guessing.
- Verification fails twice after a reasonable fix.

## Maintenance notes

- Consider seeding this repo's own `.codescent/config.toml` with the rules from
  `services/AGENTS.md` ("no FastMCP/Typer in services") as dogfooding — but do
  that in a follow-up, not this plan.
- Reviewers should confirm the rule is opt-in and cheap when unconfigured.
- TS/React layer rules can reuse the same config; only the import extraction
  differs (future plan).
