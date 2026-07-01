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
from codescent.mcp.server import mcp

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


async def build_agent_ux_report() -> AgentUxReport:
    """Run every deterministic dimension against a fresh fixture and assemble it.

    Builds a deterministic smelly repo in a temp dir, scans it, and scores the
    deterministic dimensions (R2-R6) over one in-memory ``Client(mcp)`` session
    -- mirroring the copy-to-scratch, rebuild-cold recipe the token-efficiency
    benchmark uses. R1 (tool-selection) is scored separately by U7/U8 because it
    needs the labelled task set.

    Returns:
        The assembled agent-experience report for the current surface.
    """
    with tempfile.TemporaryDirectory() as scratch:
        repo = build_smelly_repo(Path(scratch))
        async with Client(mcp) as client:
            manifest = await list_tools_manifest(client)
            dimensions = await run_deterministic_dimensions(client, repo)
        return AgentUxReport(
            repo="agent-ux-fixture",
            surface_tool_count=len(manifest),
            dimensions=tuple(dimensions),
        )
