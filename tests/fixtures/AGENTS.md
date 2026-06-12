# FIXTURE GUIDANCE

## OVERVIEW

`tests/fixtures` contains checked-in analyzed repositories and storage seeds.
The fixture code is intentionally imperfect and must remain stable enough for
deterministic rules, evals, and docs tests.

## WHERE TO LOOK

| Task | Location | Notes |
| --- | --- | --- |
| Python smell fixture | `python-basic/` | Main repo used by CLI/MCP/eval smokes. |
| TS/React/Next fixture | `ts-react-next-basic/` | Parser/rules fixture inside this Python repo. |
| Storage migration seed | `storage/mvp_v2_schema.sql` | Compatibility input for migration tests. |
| Expected manifests | `../../evals/fixtures/` | Deterministic eval expectations. |
| Fixture validation | `test_python_basic_fixture.py`, `test_ts_react_next_fixture.py` | Proves fixture contents stay intentional. |

## CONVENTIONS

- Do not "clean up" fixture smells unless the corresponding expected manifests,
  rule tests, and docs are intentionally changing.
- `.codescent/` under a fixture is runtime state and may be deleted/rebuilt by
  smokes, evals, and tests.
- The TS/React/Next fixture is not a top-level app dependency. Its `package.json`
  scripts are fixture-local only.
- Keep fixture file paths stable when possible; many tests assert exact paths and
  finding contexts.

## ANTI-PATTERNS

- Do not treat fixture source as production code.
- Do not add generated dependency folders, build outputs, or caches here.
- Do not make fixture behavior depend on network access.
