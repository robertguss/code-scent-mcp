from pathlib import Path
from typing import ClassVar

import pytest
from fastmcp import Client
from mcp.types import ContentBlock, TextContent
from pydantic import BaseModel, ConfigDict, Field

from codescent.mcp.server import mcp


class ToolSearchResult(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    path: str
    score: float = Field(ge=0)
    reasons: tuple[str, ...]
    snippet: str | None = None


class SearchToolPayload(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    ok: bool
    query: str
    limit: int = Field(ge=1, le=20)
    results: tuple[ToolSearchResult, ...]


class MultiSearchToolPayload(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    ok: bool
    queries: tuple[str, ...]
    limit: int = Field(ge=1, le=20)
    results: tuple[ToolSearchResult, ...]


class ChangedSearchToolPayload(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    ok: bool
    query: str
    limit: int = Field(ge=1, le=20)
    results: tuple[ToolSearchResult, ...]


@pytest.mark.anyio
async def test_search_tools_include_ranking_reasons(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    source = repo / "src" / "app.py"
    source.parent.mkdir(parents=True)
    _ = source.write_text("def run() -> None:\n    # TODO: handle billing\n    pass\n")

    async with Client(mcp) as client:
        tools = await client.list_tools()
        file_result = await client.call_tool(
            "search_files",
            {"repo": str(repo), "query": "ap", "limit": 20},
        )
        content_result = await client.call_tool(
            "search_content",
            {"repo": str(repo), "query": "TODO", "limit": 20},
        )

    tool_names = {tool.name: tool for tool in tools}
    assert {"search_files", "search_content"} <= tool_names.keys()
    assert "multi_search_content" in tool_names
    assert "search_changed_files" in tool_names
    assert "search_todos" not in tool_names
    assert "search_tests" not in tool_names
    assert "ranking reasons" in (tool_names["search_files"].description or "")
    assert "bounded" in (tool_names["search_content"].description or "")

    file_payload = SearchToolPayload.model_validate_json(
        _text_content(file_result.content),
    )
    content_payload = SearchToolPayload.model_validate_json(
        _text_content(content_result.content),
    )

    assert file_payload.ok is True
    assert file_payload.results[0].path == "src/app.py"
    assert file_payload.results[0].reasons
    assert content_payload.ok is True
    assert content_payload.results[0].path == "src/app.py"
    assert "content_match" in content_payload.results[0].reasons
    assert content_payload.results[0].snippet == "# TODO: handle billing"


@pytest.mark.anyio
async def test_multi_search_content_merges_and_dedupes_bounded_results(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    billing = repo / "src" / "billing.py"
    workflow = repo / "src" / "workflow.py"
    billing.parent.mkdir(parents=True)
    _ = billing.write_text("TODO: reconcile billing\nbilling_total = 10\n")
    _ = workflow.write_text("TODO: route workflow\nworkflow_state = 'billing'\n")

    async with Client(mcp) as client:
        result = await client.call_tool(
            "multi_search_content",
            {
                "repo": str(repo),
                "queries": ["TODO", "billing"],
                "limit": 5,
            },
        )

    payload = MultiSearchToolPayload.model_validate_json(_text_content(result.content))
    paths = tuple(item.path for item in payload.results)

    assert payload.ok is True
    assert payload.queries == ("TODO", "billing")
    assert paths == tuple(dict.fromkeys(paths))
    assert set(paths) == {"src/billing.py", "src/workflow.py"}
    assert all(item.snippet is not None for item in payload.results)
    assert all("query:TODO" in item.reasons for item in payload.results)
    assert "query:billing" in payload.results[0].reasons


@pytest.mark.anyio
async def test_search_changed_files_returns_bounded_changed_paths(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    source = repo / "src" / "app.py"
    ignored = repo / ".codescent" / "state.py"
    source.parent.mkdir(parents=True)
    ignored.parent.mkdir()
    _ = source.write_text("value = 1\n")
    _ = ignored.write_text("ignored = True\n")

    async with Client(mcp) as client:
        result = await client.call_tool(
            "search_changed_files",
            {"repo": str(repo), "limit": 99},
        )

    payload = ChangedSearchToolPayload.model_validate_json(
        _text_content(result.content),
    )

    assert payload.ok is True
    assert payload.query == ""
    assert payload.limit == 20
    assert tuple(item.path for item in payload.results) == ("src/app.py",)
    assert "changed_file" in payload.results[0].reasons
    assert all(".codescent" not in item.path for item in payload.results)


def _text_content(content: list[ContentBlock]) -> str:
    assert len(content) == 1
    first = content[0]
    assert isinstance(first, TextContent)
    return first.text
