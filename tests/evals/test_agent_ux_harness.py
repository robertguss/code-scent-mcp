"""Harness tests for the agent-experience eval suite scaffolding (plan U1)."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from fastmcp import Client

from codescent.evals.agent_ux import (
    build_agent_ux_report,
    build_smelly_repo,
    call_tool_json,
    list_tools_manifest,
)
from codescent.mcp.server import mcp

if TYPE_CHECKING:
    from pathlib import Path

_EXPECTED_TOOL_COUNT = 42  # P2.1+P2.2: finding tools merged away.


@pytest.mark.anyio
async def test_call_tool_json_returns_parsed_payload(tmp_path: Path) -> None:
    repo = build_smelly_repo(tmp_path)
    async with Client(mcp) as client:
        payload = await call_tool_json(client, "get_repo_status", {"repo": str(repo)})
    assert isinstance(payload, dict)
    assert payload.get("ok") is not False  # a success payload, not the error envelope


@pytest.mark.anyio
async def test_call_tool_json_returns_error_envelope_not_raise() -> None:
    async with Client(mcp) as client:
        payload = await call_tool_json(
            client, "get_repo_status", {"repo": "/no/such/dir/codescent-xyz"}
        )
    assert payload["ok"] is False
    assert payload["recoverable"] is True


@pytest.mark.anyio
async def test_list_tools_manifest_covers_the_surface() -> None:
    async with Client(mcp) as client:
        manifest = await list_tools_manifest(client)
    assert len(manifest) == _EXPECTED_TOOL_COUNT
    assert all(tool.description for tool in manifest)
    assert all(tool.input_schema_json for tool in manifest)


@pytest.mark.anyio
async def test_build_smelly_repo_is_scannable(tmp_path: Path) -> None:
    repo = build_smelly_repo(tmp_path)
    async with Client(mcp) as client:
        scan = await call_tool_json(client, "scan_code_health", {"repo": str(repo)})
    assert scan.get("finding_ids")


@pytest.mark.anyio
async def test_build_agent_ux_report_reports_surface() -> None:
    report = await build_agent_ux_report()
    assert report.surface_tool_count == _EXPECTED_TOOL_COUNT
    assert isinstance(report.dimensions, tuple)  # dimensions grow as U2-U6 land
