"""Connectivity test for the guided improvement loop (originally U4).

Now scores the shared ``next_tools`` graph helpers in
``codescent.evals.agent_ux._graph`` -- the same collection + BFS the R3
loop-connectivity eval dimension uses (plan U5) -- so the audit's F6 spine
check lives in one place.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from fastmcp import Client

from codescent.core.public_surface import registered_mcp_tool_names
from codescent.evals.agent_ux._client import build_smelly_repo
from codescent.evals.agent_ux._graph import EXPECTED_EDGES, bfs, collect_next_tools
from codescent.mcp.server import mcp
from codescent.services.code_health import CodeHealthService

if TYPE_CHECKING:
    from pathlib import Path


async def _graph(repo: Path, finding_id: str) -> dict[str, tuple[str, ...]]:
    async with Client(mcp) as client:
        return await collect_next_tools(client, repo, finding_id)


def _todo_finding_id(repo: Path) -> str:
    scan = CodeHealthService(repo).scan()
    return next(
        item for item in scan.finding_ids if item.startswith("python.todo_cluster")
    )


@pytest.mark.anyio
async def test_each_wired_tool_emits_its_next_tools(tmp_path: Path) -> None:
    repo = build_smelly_repo(tmp_path)
    finding_id = _todo_finding_id(repo)
    graph = await _graph(repo, finding_id)

    for tool, expected in EXPECTED_EDGES.items():
        assert graph[tool] == expected, tool


@pytest.mark.anyio
async def test_bfs_from_scan_reaches_mark_and_record(tmp_path: Path) -> None:
    repo = build_smelly_repo(tmp_path)
    finding_id = _todo_finding_id(repo)
    graph = await _graph(repo, finding_id)

    reachable = bfs("scan_code_health", graph)

    assert "mark_finding" in reachable
    assert "record_verification" in reachable


@pytest.mark.anyio
async def test_every_next_tools_target_is_a_registered_tool(tmp_path: Path) -> None:
    repo = build_smelly_repo(tmp_path)
    finding_id = _todo_finding_id(repo)
    graph = await _graph(repo, finding_id)
    registered = registered_mcp_tool_names()

    for source, targets in graph.items():
        for target in targets:
            # Deep-link forms carry a ``:arg`` suffix; the prefix must resolve.
            assert target.split(":", 1)[0] in registered, f"{source} -> {target}"
