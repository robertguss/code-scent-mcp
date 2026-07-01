"""R1 tool-selection dimension: the one model-driven dimension (plan U7).

The default suite scores tool-selection with an offline heuristic proxy
(rapidfuzz over descriptions) that runs on any surface and gates nothing. The
authoritative score comes from a live model, reached through the narrow
:class:`ModelClient` seam, run only at milestones (U8 baseline, U16 acceptance)
behind the ``live_model`` pytest marker and a credentials check.

This module is the one place in the suite allowed to reach a network model, and
only via the opt-in ``LiveModelToolSelector``. It must never be imported by
``deterministic.py`` or the default ``--check`` -- that boundary keeps the
deterministic floor compliant with the repo's no-network invariant.
``RecordedToolSelector`` was dropped in review: a replay is valid only for the
surface hash it was recorded on, so every phase-two merge invalidates it, and
the heuristic proxy already fills the offline slot.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, ClassVar, Protocol, cast, runtime_checkable

from pydantic import BaseModel, ConfigDict

from codescent.core.fuzzy import nearest_matches
from codescent.evals.agent_ux.models import DimensionResult, ToolInfo

if TYPE_CHECKING:
    from pathlib import Path


class SelectionTask(BaseModel):
    """One labelled tool-selection case: a task string and its intended tool.

    ``confusable_with`` records the tools the merge should disambiguate -- the
    labels are the phase-two disambiguation spec.
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    task: str
    intended_tool: str
    cluster: str
    confusable_with: tuple[str, ...] = ()


@runtime_checkable
class ToolSelector(Protocol):
    """Chooses the tool an agent should call for a task, given the manifest."""

    def select(self, task: str, manifest: list[ToolInfo]) -> str: ...


@runtime_checkable
class ModelClient(Protocol):
    """The seam a live model is reached through (owner-wired: hosted or local)."""

    def choose_tool(self, task: str, manifest: list[ToolInfo]) -> str: ...


class HeuristicToolSelector:
    """Offline, deterministic proxy: pick the tool whose text best matches.

    Non-authoritative -- a rapidfuzz overlap of the task against each tool's
    name and description. It scores on *any* surface (unlike a recorded replay),
    so it survives every phase-two merge and keeps the default suite green.
    """

    def select(self, task: str, manifest: list[ToolInfo]) -> str:
        # Reuse the repo's canonical "did you mean" scorer (rapidfuzz
        # partial_ratio) so the proxy ranks like the rest of the surface does.
        by_haystack = {
            f"{tool.name} {tool.description}".lower(): tool.name for tool in manifest
        }
        matches = nearest_matches(task.lower(), by_haystack, limit=1, threshold=0.0)
        return by_haystack[matches[0]] if matches else ""


class LiveModelToolSelector:
    """Authoritative selector: delegate to a live model via the seam.

    Opt-in only (``live_model`` marker + credentials). Constructed with an
    owner-provided :class:`ModelClient`; this class adds no network code itself.
    """

    def __init__(self, model: ModelClient) -> None:
        """Wrap an owner-provided model seam."""
        self._model: ModelClient = model

    def select(self, task: str, manifest: list[ToolInfo]) -> str:
        return self._model.choose_tool(task, manifest)


def load_selection_tasks(path: Path) -> list[SelectionTask]:
    """Load the labelled task set (the disambiguation spec) from JSON."""
    raw = cast("object", json.loads(path.read_text(encoding="utf-8")))
    if not isinstance(raw, list):
        msg = "tool_selection_tasks.json must be a JSON array"
        raise TypeError(msg)
    return [SelectionTask.model_validate(item) for item in cast("list[object]", raw)]


def score_tool_selection(
    selector: ToolSelector,
    tasks: list[SelectionTask],
    manifest: list[ToolInfo],
) -> DimensionResult:
    """Score R1: the share of tasks where ``selector`` picks the intended tool."""
    passed = 0
    notes: list[str] = []
    for task in tasks:
        chosen = selector.select(task.task, manifest)
        if chosen == task.intended_tool:
            passed += 1
        else:
            notes.append(
                f"{task.task[:40]!r}: chose {chosen}, wanted {task.intended_tool}"
            )
    total = len(tasks)
    return DimensionResult(
        name="tool_selection",
        value=passed / total if total else 0.0,
        unit="accuracy",
        passed=passed,
        total=total,
        notes=tuple(notes),
    )
