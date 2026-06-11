from typing import ClassVar

import pytest
from fastmcp import Client
from mcp.types import ContentBlock, TextContent
from pydantic import BaseModel, ConfigDict

from codescent.mcp.server import mcp

MVP_TOOL_NAMES = {
    "get_repo_map",
    "get_repo_status",
    "search_files",
    "search_content",
    "multi_search_content",
    "search_changed_files",
    "search_todos",
    "search_tests",
    "find_references",
    "find_callers",
    "find_callees",
    "get_related_files",
    "find_symbol",
    "get_file_context",
    "get_symbol_context",
    "scan_code_health",
    "get_smell_report",
    "get_finding_context",
    "get_finding",
    "explain_score",
    "get_backlog",
    "get_progress",
    "get_regressions",
    "get_impact",
    "get_next_improvement",
    "plan_refactor",
    "suggest_tests",
    "verify_change",
    "mark_finding",
    "rescan",
}


class ToolScanPayload(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    ok: bool
    status: str
    finding_ids: tuple[str, ...]
    rule_ids: tuple[str, ...]


class ToolReportPayload(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    ok: bool
    open_count: int
    findings: tuple[dict[str, str | float], ...]


@pytest.mark.anyio
async def test_exact_mvp_tool_names() -> None:
    async with Client(mcp) as client:
        tools = await client.list_tools()

    assert {tool.name for tool in tools} == MVP_TOOL_NAMES


@pytest.mark.anyio
async def test_no_post_mvp_tools_exposed() -> None:
    async with Client(mcp) as client:
        tools = await client.list_tools()

    tool_names = {tool.name for tool in tools}
    assert "multi_search_content" in tool_names
    assert "search_changed_files" in tool_names
    assert "search_todos" in tool_names
    assert "search_tests" in tool_names
    assert "find_references" in tool_names
    assert "find_callers" in tool_names
    assert "find_callees" in tool_names
    assert "get_related_files" in tool_names
    assert "get_impact" in tool_names
    assert "verify_change" in tool_names
    assert "get_backlog" in tool_names
    assert "get_progress" in tool_names
    assert "get_regressions" in tool_names
    assert "report" not in tool_names
    assert "reset" not in tool_names


@pytest.mark.anyio
async def test_tool_outputs_match_bounded_schema_snapshots() -> None:
    async with Client(mcp) as client:
        scan_result = await client.call_tool(
            "scan_code_health",
            {"repo": "tests/fixtures/python-basic"},
        )
        report_result = await client.call_tool(
            "get_smell_report",
            {"repo": "tests/fixtures/python-basic"},
        )

    scan = ToolScanPayload.model_validate_json(_text_content(scan_result.content))
    report = ToolReportPayload.model_validate_json(_text_content(report_result.content))

    assert scan.ok is True
    assert scan.status == "complete"
    assert scan.finding_ids
    assert "python.large_function" in scan.rule_ids
    assert report.ok is True
    assert report.open_count >= 1
    assert set(report.findings[0]) == {
        "finding_id",
        "rule_id",
        "file_path",
        "severity",
        "confidence",
        "status",
        "suggested_action",
    }
    assert "source_ranges" not in report.model_dump_json()
    assert "source_content" not in report.model_dump_json()


def _text_content(content: list[ContentBlock]) -> str:
    assert len(content) == 1
    first = content[0]
    assert isinstance(first, TextContent)
    return first.text
