"""End-to-end Phase-1 report test: all six dimensions + committed baseline (U8)."""

from __future__ import annotations

from pathlib import Path

import pytest

from codescent.evals.agent_ux import AgentUxReport, build_agent_ux_report
from codescent.evals.agent_ux.gate import find_regressions
from codescent.evals.agent_ux.tool_selection import load_selection_tasks

_EVALS_DIR = Path(__file__).resolve().parents[2] / "evals"
_TASKS_PATH = _EVALS_DIR / "tool_selection_tasks.json"
_BASELINES_PATH = _EVALS_DIR / "agent_ux_baselines.json"

_EXPECTED_DIMENSIONS = frozenset(
    {
        "manifest_token_cost",
        "error_recovery",
        "constraint_drop",
        "loop_connectivity",
        "envelope_conformance",
        "tool_selection",
    }
)


@pytest.mark.anyio
async def test_report_covers_all_six_dimensions() -> None:
    tasks = load_selection_tasks(_TASKS_PATH)
    report = await build_agent_ux_report(tasks=tasks)
    names = {dimension.name for dimension in report.dimensions}
    assert names == _EXPECTED_DIMENSIONS
    # Every emitted unit must be one the gate knows how to route (else it raises).
    assert {dimension.unit for dimension in report.dimensions} <= {
        "share",
        "tokens",
        "accuracy",
    }


@pytest.mark.anyio
async def test_committed_baseline_is_current() -> None:
    # The gate must be green against the checked-in baseline (no drift).
    tasks = load_selection_tasks(_TASKS_PATH)
    report = await build_agent_ux_report(tasks=tasks)
    baseline = AgentUxReport.model_validate_json(_BASELINES_PATH.read_text())
    assert find_regressions(report, baseline) == []
