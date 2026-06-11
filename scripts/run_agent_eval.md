# Running The Agent Eval

## Setup

Run the gate from the repository root:

```bash
uv run codescent init --repo tests/fixtures/python-basic
uv run codescent index --repo tests/fixtures/python-basic
uv run codescent scan --repo tests/fixtures/python-basic
```

Start the local MCP server with stdio transport:

```bash
uv run codescent serve
```

The evaluator may connect any local coding agent to that stdio server. The gate
has no external hosted LLM requirement; a human-driven local transcript is also
acceptable when it records the same tool calls and artifacts.

## Transcript Checklist

Record the transcript at `.omo/evidence/final-agent-eval-transcript.md` with
these sections:

1. Repo: `tests/fixtures/python-basic`.
2. Discovery: `scan_code_health` and `get_next_improvement`.
3. Context: `get_finding_context` for the chosen finding.
4. Plan: `plan_refactor` with non-goals and risks.
5. Verification: `suggest_tests`.
6. Rescan: `rescan`.
7. Lifecycle: `mark_finding`.
8. Safety: source-read-only confirmation.

Supporting calls may include `get_repo_status`, `search_files`,
`search_content`, `find_symbol`, `get_file_context`, and `get_symbol_context`.
Do not use broad shell grep as primary discovery.

## Pass Criteria

Pass criteria:

- transcript is artifact-backed;
- transcript names every required CodeScent tool call;
- finding selection starts from CodeScent scan or next-improvement output;
- context precedes planning;
- suggested verification precedes final status;
- rescan precedes `mark_finding`;
- source-read-only behavior is recorded;
- no external hosted LLM or network service is required.

## Fail Criteria

Fail criteria:

- missing transcript file;
- missing required CodeScent tool call;
- broad shell grep is primary discovery;
- no finding context before planning;
- no `suggest_tests` before the final status decision;
- no `rescan` before `mark_finding`;
- analyzed source files changed during the gate;
- the run depends on a hosted LLM, cloud dashboard, or CI service.
