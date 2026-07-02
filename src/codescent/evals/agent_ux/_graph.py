"""Shared ``next_tools`` graph collection + BFS for the guided loop (plan U5).

Lifts the audit's F6 connectivity logic out of
``tests/contract/test_next_tools_chain.py`` so both that contract test and the
R3 loop-connectivity eval dimension score the same live graph. Deterministic
and network-free -- it drives only the in-memory client.
"""

from __future__ import annotations

from collections import deque
from typing import TYPE_CHECKING, cast

from codescent.evals.agent_ux._client import call_tool_json

if TYPE_CHECKING:
    from pathlib import Path

    from fastmcp import Client
    from fastmcp.client.transports import FastMCPTransport

# The exact next_tools tuple each spine tool must emit (the audit's F6 spec).
EXPECTED_EDGES: dict[str, tuple[str, ...]] = {
    "get_next_improvement": ("get_finding_context", "plan_refactor"),
    "plan_refactor": ("suggest_tests", "get_impact"),
    "suggest_tests": ("verify_change",),
    "verify_change": ("record_verification", "mark_finding"),
    "mark_finding": ("rescan", "get_next_improvement"),
    "record_verification": ("mark_finding",),
}


def _loop_calls(repo: Path, finding_id: str) -> dict[str, dict[str, object]]:
    """The live call for every spine tool, keyed by tool name."""
    return {
        "scan_code_health": {"repo": str(repo)},
        "list_findings": {"repo": str(repo)},
        "get_next_improvement": {"repo": str(repo)},
        "get_finding_context": {"repo": str(repo), "finding_id": finding_id},
        "plan_refactor": {"repo": str(repo), "finding_id": finding_id},
        "suggest_tests": {"repo": str(repo), "finding_id": finding_id},
        "verify_change": {"repo": str(repo), "finding_id": finding_id},
        "get_impact": {"repo": str(repo), "finding_id": finding_id},
        "record_verification": {
            "repo": str(repo),
            "finding_id": finding_id,
            "command": "uv run pytest",
            "exit_code": 0,
            "output_summary": "ok",
        },
        "mark_finding": {
            "repo": str(repo),
            "finding_id": finding_id,
            "status": "in_progress",
        },
        "rescan": {"repo": str(repo)},
    }


async def collect_next_tools(
    client: Client[FastMCPTransport],
    repo: Path,
    finding_id: str,
) -> dict[str, tuple[str, ...]]:
    """Call every spine tool live and read the ``next_tools`` tuple it emits."""
    graph: dict[str, tuple[str, ...]] = {}
    for tool, args in _loop_calls(repo, finding_id).items():
        payload = await call_tool_json(client, tool, args)
        raw = payload.get("next_tools", ())
        targets: tuple[str, ...] = ()
        if isinstance(raw, list):
            targets = tuple(
                item for item in cast("list[object]", raw) if isinstance(item, str)
            )
        graph[tool] = targets
    return graph


def bfs(start: str, graph: dict[str, tuple[str, ...]]) -> set[str]:
    """Return every tool reachable from ``start``, stripping ``:arg`` deep-links."""
    seen: set[str] = {start}
    queue: deque[str] = deque([start])
    while queue:
        current = queue.popleft()
        for target in graph.get(current, ()):
            tool = target.split(":", 1)[0]
            if tool not in seen:
                seen.add(tool)
                queue.append(tool)
    return seen
