# python-import-cycle fixture

Intentionally flawed fixture: `acme_cycle.alpha -> acme_cycle.beta ->
acme_cycle.gamma -> acme_cycle.alpha` form a deliberate import cycle for the
`python.import_cycle` rule. Do NOT "fix" the cycle — see `tests/fixtures/AGENTS.md`.
Expectation manifest: `evals/fixtures/python-import-cycle.expected.json`.
