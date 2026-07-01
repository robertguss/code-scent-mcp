"""Agent-experience eval suite (plan units U1-U8).

Six dimensions score the MCP surface for how well a coding agent can drive it:
tool-selection (R1), error-recovery (R2), guided-loop connectivity (R3),
envelope conformance (R4), constraint-drop detection (R5), and manifest token
cost (R6). R2-R6 are deterministic and network-free and form the phase-two
per-cluster gate; R1 uses an offline heuristic proxy by default and an opt-in
live model at milestones (added by U7/U8).

``build_agent_ux_report`` assembles a full deterministic run over a
self-contained fixture; ``evals/run_agent_ux.py`` is the CLI + gate around it.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

from fastmcp import Client

from codescent.evals.agent_ux._client import (
    build_smelly_repo,
    call_tool_json,
    list_tools_manifest,
)
from codescent.evals.agent_ux.deterministic import run_deterministic_dimensions
from codescent.evals.agent_ux.models import (
    AgentUxReport,
    BreakdownEntry,
    DimensionResult,
    ToolInfo,
)
from codescent.evals.agent_ux.tool_selection import (
    HeuristicToolSelector,
    score_tool_selection,
)
from codescent.mcp.server import mcp

if TYPE_CHECKING:
    from collections.abc import Sequence

    from codescent.evals.agent_ux.tool_selection import SelectionTask, ToolSelector

__all__ = [
    "AgentUxReport",
    "BreakdownEntry",
    "DimensionResult",
    "ToolInfo",
    "build_agent_ux_report",
    "build_smelly_repo",
    "call_tool_json",
    "list_tools_manifest",
]


async def build_agent_ux_report(
    *,
    selector: ToolSelector | None = None,
    tasks: Sequence[SelectionTask] = (),
) -> AgentUxReport:
    """Run every dimension against a fresh fixture and assemble the report.

    Builds a deterministic smelly repo in a temp dir, scans it, and scores the
    deterministic dimensions (R2-R6) over one in-memory ``Client(mcp)`` session
    -- mirroring the copy-to-scratch, rebuild-cold recipe the token-efficiency
    benchmark uses. When ``tasks`` are supplied, R1 tool-selection is appended,
    scored by ``selector`` (default: the offline heuristic proxy). Passing no
    ``tasks`` yields the deterministic-only report the harness tests use.

    Args:
        selector: The R1 selector; defaults to ``HeuristicToolSelector``.
        tasks: The labelled tool-selection task set; empty skips R1.

    Returns:
        The assembled agent-experience report for the current surface.
    """
    with tempfile.TemporaryDirectory() as scratch:
        repo = build_smelly_repo(Path(scratch))
        async with Client(mcp) as client:
            manifest = await list_tools_manifest(client)
            dimensions = list(await run_deterministic_dimensions(client, repo))
        if tasks:
            chosen = selector if selector is not None else HeuristicToolSelector()
            dimensions.append(score_tool_selection(chosen, list(tasks), manifest))
        return AgentUxReport(
            repo="agent-ux-fixture",
            surface_tool_count=len(manifest),
            dimensions=tuple(dimensions),
        )
