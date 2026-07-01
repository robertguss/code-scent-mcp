"""Tests for the R1 tool-selection selector infra (plan U7)."""

from __future__ import annotations

import os

import pytest

from codescent.evals.agent_ux.models import ToolInfo
from codescent.evals.agent_ux.tool_selection import (
    HeuristicToolSelector,
    LiveModelToolSelector,
    SelectionTask,
    score_tool_selection,
)


def _manifest() -> list[ToolInfo]:
    return [
        ToolInfo(
            name="search_content",
            description="Search file contents for a string across the repo.",
            input_schema_json="{}",
        ),
        ToolInfo(
            name="get_finding",
            description="Get the details of a code-health finding by its id.",
            input_schema_json="{}",
        ),
    ]


def test_heuristic_picks_the_matching_tool() -> None:
    chosen = HeuristicToolSelector().select(
        "search file contents for the string TODO", _manifest()
    )
    assert chosen == "search_content"


def test_heuristic_scores_on_a_mutated_surface() -> None:
    # Unlike a recorded replay, the proxy still works when the surface changes.
    mutated = [
        ToolInfo(
            name="find_text",
            description="Search file contents.",
            input_schema_json="{}",
        )
    ]
    assert HeuristicToolSelector().select("search contents", mutated) == "find_text"


def test_score_tool_selection_computes_accuracy() -> None:
    tasks = [
        SelectionTask(
            task="search file contents for TODO",
            intended_tool="search_content",
            cluster="search",
        ),
        SelectionTask(
            task="get the finding details by id",
            intended_tool="get_finding",
            cluster="health",
        ),
    ]
    dimension = score_tool_selection(HeuristicToolSelector(), tasks, _manifest())
    assert dimension.name == "tool_selection"
    assert dimension.unit == "accuracy"
    assert dimension.total == 2
    assert 0.0 <= dimension.value <= 1.0


def test_live_model_selector_delegates_to_the_seam() -> None:
    class _FakeModel:
        def choose_tool(self, task: str, manifest: list[ToolInfo]) -> str:
            _ = (task, manifest)
            return "get_finding"

    selector = LiveModelToolSelector(_FakeModel())
    assert selector.select("anything", _manifest()) == "get_finding"


@pytest.mark.live_model
def test_live_model_smoke_is_opt_in() -> None:
    if not os.getenv("CODESCENT_LIVE_MODEL"):
        pytest.skip("live-model credentials not set")
    pytest.skip(
        "live-model provider wiring is deferred to the owner (see Open Questions)"
    )
