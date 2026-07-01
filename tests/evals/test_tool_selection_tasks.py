"""Validate the committed R1 tool-selection task set (plan U8)."""

from __future__ import annotations

from pathlib import Path

from codescent.core.public_surface import registered_mcp_tool_names
from codescent.evals.agent_ux.tool_selection import load_selection_tasks

_TASKS_PATH = (
    Path(__file__).resolve().parents[2] / "evals" / "tool_selection_tasks.json"
)
_MIN_TASKS = 12


def test_task_set_is_well_formed_and_registered() -> None:
    tasks = load_selection_tasks(_TASKS_PATH)
    registered = registered_mcp_tool_names()

    assert len(tasks) >= _MIN_TASKS
    for task in tasks:
        assert task.cluster, task.task
        assert task.intended_tool in registered, task.intended_tool
        for confusable in task.confusable_with:
            assert confusable in registered, confusable


def test_intended_tools_are_distinct_enough_to_measure() -> None:
    # A task set that all points at one tool would score nothing meaningful.
    tasks = load_selection_tasks(_TASKS_PATH)
    intended = {task.intended_tool for task in tasks}
    assert len(intended) >= _MIN_TASKS
