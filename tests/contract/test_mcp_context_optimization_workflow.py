from __future__ import annotations

import json
from typing import TYPE_CHECKING, ClassVar, cast

import pytest
from fastmcp import Client
from mcp.types import ContentBlock, TextContent
from pydantic import BaseModel, ConfigDict, Field

from codescent.mcp.server import mcp

if TYPE_CHECKING:
    from pathlib import Path


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


class RetrievedResultPayload(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    kind: str
    result_id: str
    mode: str
    summary: str
    items: tuple[dict[str, object], ...]
    remaining_count: int
    warnings: tuple[str, ...]


class ResultStoreErrorPayload(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    kind: str
    code: str
    message: str
    result_id: str
    retryable: bool


class MetricItem(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    tool: str
    raw_tokens: int = Field(ge=0)
    returned_tokens: int = Field(ge=0)
    query_fingerprint: str
    input_fingerprint: str


class RepeatedQueryItem(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    tool: str
    input_fingerprint: str
    count: int = Field(ge=2)


class WarningItem(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    warning_code: str
    count: int = Field(ge=1)


class ContextStatsPayload(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    session_id: str
    tool_calls: int = Field(ge=0)
    summarized_results: int = Field(ge=0)
    retrievals: int = Field(ge=0)
    estimated_raw_tokens: int = Field(ge=0)
    estimated_returned_tokens: int = Field(ge=0)
    estimated_tokens_avoided: int = Field(ge=0)
    largest_summarized_results: tuple[MetricItem, ...]
    most_used_tools: tuple[str, ...]
    repeated_broad_queries: tuple[RepeatedQueryItem, ...]
    warnings: tuple[WarningItem, ...]


@pytest.mark.anyio
async def test_mcp_context_optimization_workflow_round_trip(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _write_symbol_repo(repo, count=20)
    project_id = "task-17-project"
    session_id = "task-17-session"

    async with Client(mcp) as client:
        symbol_result = await client.call_tool(
            "find_symbol",
            {
                "repo": str(repo),
                "query": "handler",
                "limit": 20,
                "project_id": project_id,
                "session_id": session_id,
            },
        )
        symbol_payload = SymbolEnvelopePayload.model_validate_json(
            _text_content(symbol_result.content),
        )
        result_id = symbol_payload.original_result_id
        assert result_id is not None

        retrieved_result = await client.call_tool(
            "retrieve_result",
            {
                "repo": str(repo),
                "project_id": project_id,
                "session_id": session_id,
                "result_id": result_id,
                "mode": "filtered",
                "query": "handler_12",
                "file": "src/many.py",
                "symbol": "handler_12",
                "limit": 5,
            },
        )
        stats_result = await client.call_tool(
            "context_stats",
            {
                "repo": str(repo),
                "project_id": project_id,
                "session_id": session_id,
            },
        )

    retrieved = RetrievedResultPayload.model_validate_json(
        _text_content(retrieved_result.content),
    )
    stats = ContextStatsPayload.model_validate_json(_text_content(stats_result.content))

    assert symbol_payload.ok is True
    assert symbol_payload.kind == "symbol_search"
    assert symbol_payload.mode == "summarized"
    assert result_id.startswith("ctx_")
    assert symbol_payload.retrieval_available is True
    assert symbol_payload.omitted_count > 0
    assert symbol_payload.stats["total_results"] == 20
    assert any("retrieve_result" in hint for hint in symbol_payload.retrieval_hints)

    assert retrieved.kind == "retrieved_result"
    assert retrieved.result_id == result_id
    assert retrieved.mode == "filtered"
    assert retrieved.remaining_count == 0
    assert retrieved.warnings == ()
    assert len(retrieved.items) == 1
    assert retrieved.items[0]["name"] == "handler_12"
    assert retrieved.items[0]["path"] == "src/many.py"

    assert stats.session_id == session_id
    assert stats.tool_calls >= 1
    assert stats.summarized_results >= 1
    assert stats.retrievals >= 1
    assert stats.estimated_raw_tokens > 0
    assert stats.estimated_returned_tokens > 0
    assert stats.estimated_tokens_avoided > 0
    assert stats.largest_summarized_results[0].tool == "find_symbol"
    assert stats.largest_summarized_results[0].raw_tokens > 0
    assert stats.largest_summarized_results[0].returned_tokens > 0
    assert "find_symbol" in stats.most_used_tools


@pytest.mark.anyio
async def test_mcp_context_optimization_negative_paths_are_deterministic(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()

    async with Client(mcp) as client:
        missing_result = await client.call_tool(
            "retrieve_result",
            {
                "repo": str(repo),
                "result_id": "ctx_0000000000000000",
                "project_id": "task-17-project",
                "session_id": "task-17-negative-session",
            },
        )
        empty_stats_result = await client.call_tool(
            "context_stats",
            {
                "repo": str(repo),
                "project_id": "task-17-project",
                "session_id": "task-17-empty-session",
            },
        )

    missing_json = _text_content(missing_result.content)
    missing = ResultStoreErrorPayload.model_validate_json(missing_json)
    empty_stats = ContextStatsPayload.model_validate_json(
        _text_content(empty_stats_result.content),
    )

    assert missing.kind == "result_store_error"
    assert missing.code == "missing_result"
    assert missing.result_id == "ctx_0000000000000000"
    assert missing.retryable is False
    assert "Traceback" not in missing_json

    assert empty_stats.session_id == "task-17-empty-session"
    assert empty_stats.tool_calls == 0
    assert empty_stats.summarized_results == 0
    assert empty_stats.retrievals == 0
    assert empty_stats.estimated_raw_tokens == 0
    assert empty_stats.estimated_returned_tokens == 0
    assert empty_stats.estimated_tokens_avoided == 0
    assert empty_stats.largest_summarized_results == ()
    assert empty_stats.most_used_tools == ()
    assert empty_stats.repeated_broad_queries == ()
    assert empty_stats.warnings == ()


def _write_symbol_repo(repo: Path, *, count: int) -> None:
    source = repo / "src" / "many.py"
    source.parent.mkdir(parents=True)
    _ = source.write_text(
        "\n".join(
            f"def handler_{index}() -> int:\n    return {index}\n"
            for index in range(count)
        ),
    )


def _text_content(content: list[ContentBlock]) -> str:
    assert len(content) == 1
    first = content[0]
    assert isinstance(first, TextContent)
    text = first.text
    parsed = cast("object", json.loads(text))
    assert isinstance(parsed, dict)
    return text
