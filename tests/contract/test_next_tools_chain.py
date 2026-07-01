"""Connectivity test for the guided improvement loop (U4).

Fails if any of the six wired `next_tools` edges regress and the
`scan → next → plan → tests → verify → mark/record → rescan` spine stops
reaching its action tools.
"""

from __future__ import annotations

import json
from collections import deque
from typing import TYPE_CHECKING, Any, cast

import pytest
from fastmcp import Client
from mcp.types import ContentBlock, TextContent

from codescent.core.models import MaintainabilityThresholds, ProjectConfig
from codescent.core.public_surface import registered_mcp_tool_names
from codescent.mcp.server import mcp
from codescent.services.code_health import CodeHealthService
from codescent.services.config import ConfigService

if TYPE_CHECKING:
    from pathlib import Path

STRICT_CONFIG = ProjectConfig(thresholds=MaintainabilityThresholds.strict())

# Each of the six tools U4 wires and the exact tuple it must emit.
_EXPECTED: dict[str, tuple[str, ...]] = {
    "get_next_improvement": ("get_finding_context", "plan_refactor"),
    "plan_refactor": ("suggest_tests", "get_impact"),
    "suggest_tests": ("verify_change",),
    "verify_change": ("record_verification", "mark_finding"),
    "mark_finding": ("rescan", "get_next_improvement"),
    "record_verification": ("mark_finding",),
}


@pytest.mark.anyio
async def test_each_wired_tool_emits_its_next_tools(tmp_path: Path) -> None:
    repo = _repo_with_smell(tmp_path)
    finding_id = _todo_finding_id(repo)
    graph = await _collect_next_tools(repo, finding_id)

    for tool, expected in _EXPECTED.items():
        assert graph[tool] == expected, tool


@pytest.mark.anyio
async def test_bfs_from_scan_reaches_mark_and_record(tmp_path: Path) -> None:
    repo = _repo_with_smell(tmp_path)
    finding_id = _todo_finding_id(repo)
    graph = await _collect_next_tools(repo, finding_id)

    reachable = _bfs("scan_code_health", graph)

    assert "mark_finding" in reachable
    assert "record_verification" in reachable


@pytest.mark.anyio
async def test_every_next_tools_target_is_a_registered_tool(tmp_path: Path) -> None:
    repo = _repo_with_smell(tmp_path)
    finding_id = _todo_finding_id(repo)
    graph = await _collect_next_tools(repo, finding_id)
    registered = registered_mcp_tool_names()

    for source, targets in graph.items():
        for target in targets:
            # Deep-link forms carry a ``:arg`` suffix; the prefix must resolve.
            assert target.split(":", 1)[0] in registered, f"{source} -> {target}"


def _bfs(start: str, graph: dict[str, tuple[str, ...]]) -> set[str]:
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


async def _collect_next_tools(
    repo: Path,
    finding_id: str,
) -> dict[str, tuple[str, ...]]:
    """Call every loop tool live and read the next_tools tuple it emits."""
    calls: dict[str, dict[str, object]] = {
        "scan_code_health": {"repo": str(repo)},
        "get_smell_report": {"repo": str(repo)},
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
    graph: dict[str, tuple[str, ...]] = {}
    async with Client(mcp) as client:
        for tool, args in calls.items():
            result = await client.call_tool(tool, args)
            payload = _json(result.content)
            graph[tool] = tuple(cast("list[str]", payload.get("next_tools", ())))
    return graph


def _todo_finding_id(repo: Path) -> str:
    scan = CodeHealthService(repo).scan()
    return next(
        item for item in scan.finding_ids if item.startswith("python.todo_cluster")
    )


def _repo_with_smell(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    source = repo / "src" / "pkg" / "config.py"
    test = repo / "tests" / "test_config.py"
    source.parent.mkdir(parents=True)
    test.parent.mkdir()
    _ = source.write_text(
        'STATUS = "pending-review"\n'
        'OTHER_STATUS = "pending-review"\n'
        'THIRD_STATUS = "pending-review"\n\n\n'
        "def load_config() -> str:\n"
        "    # TODO: split config\n"
        "    # FIXME: preserve compatibility\n"
        "    # HACK: keep old queue name\n"
        "    return STATUS\n",
    )
    _ = test.write_text(
        "from pkg.config import load_config\n\n\n"
        "def test_load_config() -> None:\n"
        '    assert load_config() == "pending-review"\n',
    )
    ConfigService(repo).save(STRICT_CONFIG)
    return repo


def _json(content: list[ContentBlock]) -> dict[str, Any]:
    assert len(content) == 1
    first = content[0]
    assert isinstance(first, TextContent)
    parsed = cast("object", json.loads(first.text))
    assert isinstance(parsed, dict)
    return cast("dict[str, Any]", parsed)
