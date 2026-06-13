from pathlib import Path
from typing import ClassVar

import pytest
from fastmcp import Client
from mcp.types import ContentBlock, TextContent
from pydantic import BaseModel, ConfigDict

from codescent.mcp.server import mcp
from codescent.services.result_store import ResultStoreService
from codescent.services.session_stats import ContextStatsService


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


class SymbolEnvelopePayload(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    ok: bool
    kind: str
    mode: str
    summary: str
    items: tuple[dict[str, object], ...]
    omitted_count: int
    original_result_id: str | None = None
    retrieval_available: bool
    retrieval_hints: tuple[str, ...]
    warnings: tuple[str, ...]
    stats: dict[str, int | float]


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


@pytest.mark.anyio
async def test_find_symbol_large_result_returns_stored_summary_envelope(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    _write_many_symbol_repo(repo, count=20)

    async with Client(mcp) as client:
        result = await client.call_tool(
            "find_symbol",
            {
                "repo": str(repo),
                "query": "handler",
                "limit": 20,
                "project_id": "project-symbols",
                "session_id": "session-symbols",
            },
        )

    payload = SymbolEnvelopePayload.model_validate_json(_text_content(result.content))
    assert payload.ok is True
    assert payload.kind == "symbol_search"
    assert payload.mode == "summarized"
    assert payload.original_result_id is not None
    assert payload.original_result_id.startswith("ctx_")
    assert payload.omitted_count > 0
    assert payload.retrieval_available is True
    assert any("retrieve_result" in hint for hint in payload.retrieval_hints)
    assert payload.stats["total_results"] == 20

    stored = ResultStoreService(repo).retrieve_result(
        payload.original_result_id,
        mode="exact",
        limit=25,
    )
    stats = ContextStatsService(repo).context_stats(
        project_id="project-symbols",
        session_id="session-symbols",
    )
    assert len(stored["items"]) == 20
    assert stats.tool_calls == 1
    assert stats.summarized_results == 1
    assert stats.estimated_tokens_avoided > 0


@pytest.mark.anyio
async def test_find_symbol_small_result_is_exact_without_omission_warning(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    _write_many_symbol_repo(repo, count=1)

    async with Client(mcp) as client:
        result = await client.call_tool(
            "find_symbol",
            {"repo": str(repo), "query": "handler_0", "limit": 20},
        )

    payload = SymbolEnvelopePayload.model_validate_json(_text_content(result.content))

    assert payload.ok is True
    assert payload.mode == "exact"
    assert payload.omitted_count == 0
    assert payload.original_result_id is None
    assert payload.retrieval_available is False
    assert payload.retrieval_hints == ()
    assert payload.warnings == ()
    assert payload.stats["total_results"] == 1


def _text_content(content: list[ContentBlock]) -> str:
    assert len(content) == 1
    first = content[0]
    assert isinstance(first, TextContent)
    return first.text


def _write_many_symbol_repo(repo: Path, *, count: int) -> None:
    source = repo / "src" / "many.py"
    source.parent.mkdir(parents=True)
    _ = source.write_text(
        "\n".join(
            f"def handler_{index}() -> int:\n    return {index}\n"
            for index in range(count)
        ),
    )
