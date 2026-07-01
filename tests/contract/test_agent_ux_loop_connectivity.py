"""Tests for the R3 loop-connectivity dimension (plan U5, covers AE3)."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from fastmcp import Client

from codescent.evals.agent_ux import build_smelly_repo, call_tool_json
from codescent.evals.agent_ux._graph import bfs
from codescent.evals.agent_ux.deterministic import loop_connectivity
from codescent.mcp.server import mcp

if TYPE_CHECKING:
    from pathlib import Path


@pytest.mark.anyio
async def test_loop_connectivity_scores_connected(tmp_path: Path) -> None:
    repo = build_smelly_repo(tmp_path)
    async with Client(mcp) as client:
        _ = await call_tool_json(client, "scan_code_health", {"repo": str(repo)})
        dimension = await loop_connectivity(client, repo)
    assert dimension.name == "loop_connectivity"
    assert dimension.value == 1.0  # AE3: the spine connects at baseline
    assert dimension.notes == ()


def test_bfs_reaches_action_tools_through_synthetic_spine() -> None:
    graph = {
        "scan_code_health": ("get_next_improvement",),
        "get_next_improvement": ("plan_refactor",),
        "plan_refactor": ("mark_finding",),
    }
    reachable = bfs("scan_code_health", graph)
    assert "mark_finding" in reachable


def test_bfs_stops_at_a_dead_end() -> None:
    # A synthetic spine that dead-ends before the action tools is not connected.
    graph: dict[str, tuple[str, ...]] = {
        "scan_code_health": ("get_next_improvement",),
        "get_next_improvement": (),
    }
    reachable = bfs("scan_code_health", graph)
    assert "mark_finding" not in reachable


def test_bfs_strips_deep_link_arg() -> None:
    graph = {"answer_pack": ("get_symbol_context:pkg.config.load_config",)}
    reachable = bfs("answer_pack", graph)
    assert "get_symbol_context" in reachable
