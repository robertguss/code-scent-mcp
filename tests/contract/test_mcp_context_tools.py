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
    } <= tool_names.keys()
    assert "find_references" not in tool_names
    assert "find_callers" not in tool_names
    assert "find_callees" not in tool_names
    assert "get_related_files" not in tool_names

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


def _text_content(content: list[ContentBlock]) -> str:
    assert len(content) == 1
    first = content[0]
    assert isinstance(first, TextContent)
    return first.text
