from typing import ClassVar

import pytest
from fastmcp import Client
from mcp.types import ContentBlock, TextContent
from pydantic import BaseModel, ConfigDict

from codescent.mcp.finding_payloads import INLINE_ITEM_LIMIT
from codescent.mcp.server import mcp

ABSENT_POST_MVP_TOOL_NAMES = {
    "project_guidance",
    "project_learnings",
    "compress_generic_output",
    "retrieve_original_output",
}

MVP_TOOL_NAMES = {
    "get_repo_map",
    "get_repo_status",
    "start_task",
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
    "get_improvement_plan",
    "get_progress",
    "get_regressions",
    "get_impact",
    "get_next_improvement",
    "plan_refactor",
    "suggest_tests",
    "select_tests",
    "verify_change",
    "mark_finding",
    "record_verification",
    "rescan",
    "review_diff_risk",
    "get_changed_file_health",
    "retrieve_result",
    "context_stats",
}


class ToolScanPayload(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    ok: bool
    status: str
    finding_ids: tuple[str, ...]
    rule_ids: tuple[str, ...]
    total_count: int
    items: tuple[dict[str, str | float], ...]
    returned_count: int
    omitted_count: int
    retrieval_available: bool


class ToolReportPayload(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    ok: bool
    open_count: int
    total_count: int
    items: tuple[dict[str, str | float], ...]
    returned_count: int
    omitted_count: int
    result_id: str | None
    retrieval_available: bool


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
    assert "review_diff_risk" in tool_names
    assert "get_changed_file_health" in tool_names
    assert "retrieve_result" in tool_names
    assert "context_stats" in tool_names
    assert "record_verification" in tool_names
    assert "report" not in tool_names
    assert "reset" not in tool_names
    assert tool_names.isdisjoint(ABSENT_POST_MVP_TOOL_NAMES)


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
    # A size-independent rule so this stays stable regardless of threshold config.
    assert "python.dead_code_candidate" in scan.rule_ids
    # Boundedness: inline ids/items never exceed the cap, even if total is larger.
    assert len(scan.finding_ids) <= INLINE_ITEM_LIMIT
    assert len(scan.items) <= INLINE_ITEM_LIMIT
    assert scan.returned_count == len(scan.items)
    assert scan.omitted_count == max(0, scan.total_count - scan.returned_count)
    assert report.ok is True
    assert report.open_count >= 1
    assert len(report.items) <= INLINE_ITEM_LIMIT
    assert report.returned_count == len(report.items)
    assert report.omitted_count == max(0, report.total_count - report.returned_count)
    # When findings are omitted, a retrieval handle must be offered.
    assert report.retrieval_available == (report.omitted_count > 0)
    assert (report.result_id is not None) == (report.omitted_count > 0)
    assert set(report.items[0]) == {
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
