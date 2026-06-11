# CodeScent Agent Eval Task

## Objective

Use CodeScent against `tests/fixtures/python-basic` to complete one scripted
improvement loop from discovery through rescan evidence. This gate is local and
does not require any external hosted LLM.

## Required Tool Sequence

The transcript must show these CodeScent MCP tool calls in order:

1. `scan_code_health` on `tests/fixtures/python-basic`.
2. `get_next_improvement` to select one fixture finding.
3. `get_finding_context` for the selected finding.
4. `plan_refactor` for a behavior-preserving change plan.
5. `suggest_tests` for verification commands.
6. `rescan` after the agent has described the planned change outcome.
7. `mark_finding` only when the transcript includes the rescan result and the
   selected status transition.

The agent may use `get_repo_status`, `search_files`, `search_content`,
`find_symbol`, `get_file_context`, or `get_symbol_context` as supporting calls.
Broad shell grep must not be the primary discovery mechanism.

## Transcript Artifact

Write the artifact-backed transcript to
`.omo/evidence/final-agent-eval-transcript.md`. The transcript must include:

- the exact repo path;
- each CodeScent tool call name;
- the selected finding ID and rule ID;
- the bounded context returned for the finding;
- the safe refactor plan and explicit non-goals;
- suggested verification commands from `suggest_tests`;
- the `rescan` result;
- the `mark_finding` status and reason;
- source-read-only confirmation, allowing only `.codescent/` runtime state.

## Pass Criteria

Pass criteria:

- all required CodeScent tool calls are present in the transcript;
- the selected finding comes from `scan_code_health` or `get_next_improvement`;
- `get_finding_context` is used before `plan_refactor`;
- `suggest_tests` is called before the final status decision;
- `rescan` evidence is present before `mark_finding`;
- the transcript is artifact-backed and stored at
  `.omo/evidence/final-agent-eval-transcript.md`;
- no external hosted LLM is required;
- broad shell grep is not used as primary discovery;
- the analyzed source files remain unchanged except CodeScent-owned
  `.codescent/` state.

## Fail Criteria

Fail criteria:

- missing any required CodeScent tool call;
- selecting a finding through broad shell grep as primary discovery;
- producing a plan without finding context;
- marking a finding without rescan evidence;
- editing analyzed source as part of the eval gate;
- requiring a hosted LLM, cloud service, dashboard, or CI system;
- storing no artifact-backed transcript.
