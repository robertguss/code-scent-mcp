from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
AGENT_TASK = ROOT / "evals" / "agent_task.md"
RUNBOOK = ROOT / "scripts" / "run_agent_eval.md"

REQUIRED_TOOL_CALLS = {
    "scan_code_health",
    "get_next_improvement",
    "explain_finding",
    "plan_refactor",
    "suggest_tests",
    "rescan",
    "mark_finding",
}


def test_agent_eval_spec_has_required_steps_and_pass_fail() -> None:
    agent_task = AGENT_TASK.read_text()
    runbook = RUNBOOK.read_text()
    combined = f"{agent_task}\n{runbook}".lower()

    for tool_name in REQUIRED_TOOL_CALLS:
        assert tool_name in combined

    assert "tests/fixtures/python-basic" in combined
    assert ".omo/evidence/final-agent-eval-transcript.md" in combined
    assert "pass criteria" in combined
    assert "fail criteria" in combined
    assert "no external hosted llm" in combined
    assert "broad shell grep" in combined
    assert "primary discovery" in combined
    assert "artifact-backed transcript" in combined
