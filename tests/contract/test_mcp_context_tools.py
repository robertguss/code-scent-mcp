from typing import ClassVar

import pytest
from fastmcp import Client
from mcp.types import ContentBlock, TextContent
from pydantic import BaseModel, ConfigDict

from codescent.mcp.server import mcp


class ContextToolPayload(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    ok: bool
    summary: str | None = None
    source_ranges: tuple[dict[str, str | int], ...] = ()
    likely_tests: tuple[str, ...] = ()
    next_tools: tuple[str, ...] = ()


class GraphResultPayload(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    text: str
    path: str
    start_line: int
    confidence: float
    certainty: str
    caller: str | None = None


class GraphToolPayload(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    ok: bool
    query: str
    results: tuple[GraphResultPayload, ...]
    next_cursor: int | None = None
    kind: str | None = None
    mode: str | None = None
    original_result_id: str | None = None
    retrieval_available: bool | None = None


class FindSymbolToolPayload(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    ok: bool
    query: str
    results: tuple[dict[str, str | int | float], ...]
    kind: str | None = None
    mode: str | None = None
    original_result_id: str | None = None
    retrieval_available: bool | None = None


@pytest.mark.anyio
async def test_context_tools_do_not_dump_whole_files() -> None:
    async with Client(mcp) as client:
        tools = await client.list_tools()
        file_context = await client.call_tool(
            "get_file_context",
            {
                "repo": "tests/fixtures/python-basic",
                "path": "src/acme_tasks/workflow.py",
            },
        )
        symbol_context = await client.call_tool(
            "get_symbol_context",
            {
                "repo": "tests/fixtures/python-basic",
                "qualified_name": "acme_tasks.workflow.build_daily_plan",
            },
        )

    tool_names = {tool.name: tool for tool in tools}
    assert {
        "find_symbol",
        "get_file_context",
        "get_symbol_context",
        "find_references",
        "find_callers",
        "find_callees",
        "get_related_files",
    } <= tool_names.keys()

    file_payload = ContextToolPayload.model_validate_json(
        _text_content(file_context.content),
    )
    symbol_payload = ContextToolPayload.model_validate_json(
        _text_content(symbol_context.content),
    )
    combined = f"{file_payload.model_dump_json()} {symbol_payload.model_dump_json()}"

    assert file_payload.ok is True
    assert symbol_payload.ok is True
    assert file_payload.source_ranges
    assert symbol_payload.likely_tests == ("tests/test_workflow.py",)
    assert "archive completed tickets" not in combined
    assert "close empty work queues" not in combined


@pytest.mark.anyio
async def test_reference_graph_tools_return_bounded_graph_results() -> None:
    async with Client(mcp) as client:
        reference_result = await client.call_tool(
            "find_references",
            {
                "repo": "tests/fixtures/python-basic",
                "query": "print",
                "limit": 2,
            },
        )
        callers_result = await client.call_tool(
            "find_callers",
            {
                "repo": "tests/fixtures/python-basic",
                "query": "print",
                "limit": 2,
            },
        )
        callees_result = await client.call_tool(
            "find_callees",
            {
                "repo": "tests/fixtures/python-basic",
                "query": "build_daily_plan",
                "limit": 2,
            },
        )

    references = GraphToolPayload.model_validate_json(
        _text_content(reference_result.content),
    )
    callers = GraphToolPayload.model_validate_json(
        _text_content(callers_result.content),
    )
    callees = GraphToolPayload.model_validate_json(
        _text_content(callees_result.content),
    )
    combined = (
        f"{references.model_dump_json()} "
        f"{callers.model_dump_json()} "
        f"{callees.model_dump_json()}"
    )

    assert references.ok is True
    assert callers.ok is True
    assert callees.ok is True
    assert 0 < len(references.results) <= 2
    assert 0 < len(callers.results) <= 2
    assert 0 < len(callees.results) <= 2
    assert all(result.confidence <= 1 for result in references.results)
    assert all(
        result.certainty in {"low", "medium", "high"} for result in callers.results
    )
    assert any(result.caller is not None for result in callers.results)
    assert all(result.path.endswith(".py") for result in callees.results)
    assert "archive completed tickets" not in combined
    assert "source_content" not in combined
    assert references.kind == "find_references"
    assert references.mode == "summary"
    assert references.original_result_id is not None
    assert references.original_result_id.startswith("ctx_")
    assert references.retrieval_available is True


@pytest.mark.anyio
async def test_find_symbol_returns_retrievable_handle() -> None:
    async with Client(mcp) as client:
        symbol_result = await client.call_tool(
            "find_symbol",
            {
                "repo": "tests/fixtures/python-basic",
                "query": "build_daily_plan",
                "limit": 1,
            },
        )

    symbol_payload = FindSymbolToolPayload.model_validate_json(
        _text_content(symbol_result.content),
    )

    assert symbol_payload.ok is True
    assert symbol_payload.kind == "find_symbol"
    assert symbol_payload.mode == "summary"
    assert symbol_payload.original_result_id is not None
    assert symbol_payload.original_result_id.startswith("ctx_")
    assert symbol_payload.retrieval_available is True


def _text_content(content: list[ContentBlock]) -> str:
    assert len(content) == 1
    first = content[0]
    assert isinstance(first, TextContent)
    return first.text
