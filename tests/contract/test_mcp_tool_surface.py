from typing import ClassVar

import pytest
from fastmcp import Client
from mcp.types import ContentBlock, TextContent
from pydantic import BaseModel, ConfigDict

from codescent.core.models import FindingStatus
from codescent.mcp.finding_payloads import INLINE_ITEM_LIMIT
from codescent.mcp.server import mcp

# Each id/name consumer must name where its required id/name comes from; the
# value is the set of acceptable source phrases (any one suffices). Asserted on
# this subset only, per the plan, to avoid brittle whole-surface matching.
ID_SOURCE_REQUIREMENTS: dict[str, tuple[str, ...]] = {
    "get_finding": ("get_next_improvement", "list_findings"),
    "get_symbol_context": ("find_symbol",),
    "plan_refactor": ("get_next_improvement", "list_findings"),
    "get_impact": ("find_symbol", "get_next_improvement", "list_findings"),
    "mark_finding": ("get_next_improvement", "list_findings"),
    "retrieve_result": ("answer_pack", "list_findings"),
}

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
    "resume_task",
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
    "list_findings",
    "get_finding_context",
    "get_finding",
    "explain_score",
    "explain_finding",
    "get_improvement_plan",
    "get_calibration",
    "get_impact",
    "get_next_improvement",
    "plan_refactor",
    "suggest_tests",
    "select_tests",
    "verify_change",
    "verify_refactor",
    "mark_finding",
    "record_verification",
    "rescan",
    "review_diff_risk",
    "get_changed_file_health",
    "retrieve_result",
    "context_stats",
    "how_to_use",
    "refactor_preflight",
    "subjective_review",
    "answer_pack",
    "get_architecture",
    "get_schema",
}


class ToolScanPayload(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    ok: bool
    status: str
    finding_ids: tuple[str, ...]
    rule_ids: tuple[str, ...]
    total_count: int
    items: tuple[dict[str, object], ...]
    returned_count: int
    omitted_count: int
    retrieval_available: bool


class ToolReportPayload(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    ok: bool
    open_count: int
    total_count: int
    items: tuple[dict[str, object], ...]
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
    assert "verify_refactor" in tool_names
    assert "review_diff_risk" in tool_names
    assert "get_changed_file_health" in tool_names
    assert "retrieve_result" in tool_names
    assert "context_stats" in tool_names
    assert "list_findings" in tool_names
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
            "list_findings",
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
        "confidence_tier",
        "provenance",
        "status",
        "suggested_action",
    }
    assert "source_ranges" not in report.model_dump_json()
    assert "source_content" not in report.model_dump_json()


@pytest.mark.anyio
async def test_no_description_leads_with_use_codescent() -> None:
    async with Client(mcp) as client:
        tools = await client.list_tools()

    offenders = [
        tool.name
        for tool in tools
        if (tool.description or "").startswith("Use CodeScent")
    ]
    assert offenders == []


@pytest.mark.anyio
async def test_every_description_is_non_empty() -> None:
    async with Client(mcp) as client:
        tools = await client.list_tools()

    for tool in tools:
        assert (tool.description or "").strip(), tool.name


@pytest.mark.anyio
async def test_enum_params_are_enumerated_inline() -> None:
    descriptions = await _descriptions()

    mark = descriptions["mark_finding"]
    for status in FindingStatus:
        assert status.value in mark, status.value

    impact = descriptions["get_impact"]
    for target_type in ("file", "symbol", "finding"):
        assert target_type in impact, target_type


@pytest.mark.anyio
async def test_id_consumers_name_where_the_id_comes_from() -> None:
    descriptions = await _descriptions()

    for tool, sources in ID_SOURCE_REQUIREMENTS.items():
        description = descriptions[tool]
        assert any(source in description for source in sources), tool


@pytest.mark.anyio
async def test_id_consumers_carry_a_concrete_example() -> None:
    descriptions = await _descriptions()

    for tool in ID_SOURCE_REQUIREMENTS:
        assert "e.g." in descriptions[tool].lower(), tool


@pytest.mark.anyio
async def test_confusable_pairs_carry_a_prefer_sibling_steer() -> None:
    descriptions = await _descriptions()

    assert "answer_pack" in descriptions["start_task"]
    assert "start_task" in descriptions["answer_pack"]
    assert "rescan" in descriptions["scan_code_health"]
    assert "scan_code_health" in descriptions["rescan"]


async def _descriptions() -> dict[str, str]:
    async with Client(mcp) as client:
        tools = await client.list_tools()
    return {tool.name: tool.description or "" for tool in tools}


def _text_content(content: list[ContentBlock]) -> str:
    assert len(content) == 1
    first = content[0]
    assert isinstance(first, TextContent)
    return first.text
