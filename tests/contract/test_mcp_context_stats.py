import json
from pathlib import Path
from typing import ClassVar, cast

import pytest
from fastmcp import Client
from mcp.types import ContentBlock, TextContent
from pydantic import BaseModel, ConfigDict, Field

from codescent.mcp.server import mcp
from codescent.storage import RepositoryStorage, initialize_storage
from codescent.storage.repositories import SessionEventRepository, SessionEventWrite

SENTINEL_TEXT = "SECRET_CONTEXT_STATS_SENTINEL"


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
async def test_context_stats_empty_session_returns_zero_payload(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()

    async with Client(mcp) as client:
        result = await client.call_tool(
            "context_stats",
            {
                "repo": str(repo),
                "project_id": "project-a",
                "session_id": "empty-session",
            },
        )

    payload = ContextStatsPayload.model_validate_json(_text_content(result.content))

    assert payload.session_id == "empty-session"
    assert payload.tool_calls == 0
    assert payload.summarized_results == 0
    assert payload.retrievals == 0
    assert payload.estimated_raw_tokens == 0
    assert payload.estimated_returned_tokens == 0
    assert payload.estimated_tokens_avoided == 0
    assert payload.largest_summarized_results == ()
    assert payload.most_used_tools == ()
    assert payload.repeated_broad_queries == ()
    assert payload.warnings == ()


@pytest.mark.anyio
async def test_context_stats_returns_bounded_sanitized_session_stats(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _seed_events(repo)

    async with Client(mcp) as client:
        result = await client.call_tool(
            "context_stats",
            {
                "repo": str(repo),
                "project_id": "project-a",
                "session_id": "session-a",
            },
        )

    payload_json = _text_content(result.content)
    payload = ContextStatsPayload.model_validate_json(payload_json)

    assert payload.session_id == "session-a"
    assert payload.tool_calls == 4
    assert payload.summarized_results == 2
    assert payload.retrievals == 1
    assert payload.estimated_raw_tokens == 67400
    assert payload.estimated_returned_tokens == 4900
    assert payload.estimated_tokens_avoided == 62500
    assert payload.most_used_tools == (
        "repo_summary",
        "search_content",
        "symbol_search",
    )
    assert tuple(item.tool for item in payload.largest_summarized_results) == (
        "symbol_search",
        "search_content",
    )
    assert payload.largest_summarized_results[0].raw_tokens == 42000
    assert payload.largest_summarized_results[0].returned_tokens == 2100
    assert payload.repeated_broad_queries[0].tool == "repo_summary"
    assert payload.repeated_broad_queries[0].count == 2
    assert payload.warnings == (WarningItem(warning_code="broad_query", count=2),)
    assert SENTINEL_TEXT not in payload_json
    assert "UserService" not in payload_json
    assert "raw_result" not in payload_json
    assert "source_content" not in payload_json
    assert len(payload_json) < 5000


@pytest.mark.anyio
async def test_mcp_lists_context_stats_as_bounded_stats_tool() -> None:
    async with Client(mcp) as client:
        tools = await client.list_tools()

    tool = {item.name: item for item in tools}["context_stats"]
    description = tool.description or ""

    assert "MCP context and token-savings stats" in description
    assert "sanitized .codescent event data" in description
    assert "never returns raw source" in description


def _seed_events(repo: Path) -> None:
    state = initialize_storage(repo)
    events = SessionEventRepository(RepositoryStorage(state))
    writes = (
        SessionEventWrite(
            project_id="project-a",
            session_id="session-a",
            event_type="tool_called",
            tool_name="repo_summary",
            payload={"query": f"all files {SENTINEL_TEXT}", "broad_query": True},
            created_at="2026-06-13T00:00:00+00:00",
        ),
        SessionEventWrite(
            project_id="project-a",
            session_id="session-a",
            event_type="tool_called",
            tool_name="repo_summary",
            payload={"query": f"all files {SENTINEL_TEXT}", "broad_query": True},
            created_at="2026-06-13T00:00:01+00:00",
        ),
        SessionEventWrite(
            project_id="project-a",
            session_id="session-a",
            event_type="tool_called",
            tool_name="symbol_search",
            payload={"query": "UserService", "broad_query": False},
            created_at="2026-06-13T00:00:02+00:00",
        ),
        SessionEventWrite(
            project_id="project-a",
            session_id="session-a",
            event_type="tool_called",
            tool_name="search_content",
            payload={"query": SENTINEL_TEXT, "broad_query": False},
            created_at="2026-06-13T00:00:03+00:00",
        ),
        SessionEventWrite(
            project_id="project-a",
            session_id="session-a",
            event_type="large_result_summarized",
            tool_name="symbol_search",
            result_id="ctx_1",
            payload={
                "query": "UserService",
                "raw_tokens": 42000,
                "returned_tokens": 2100,
                "raw_result": f"source body {SENTINEL_TEXT}",
            },
            created_at="2026-06-13T00:00:04+00:00",
        ),
        SessionEventWrite(
            project_id="project-a",
            session_id="session-a",
            event_type="large_result_summarized",
            tool_name="search_content",
            result_id="ctx_2",
            payload={
                "query": SENTINEL_TEXT,
                "source_content": f"def leaked(): return {SENTINEL_TEXT!r}",
                "raw_tokens": 25000,
                "returned_tokens": 2400,
            },
            created_at="2026-06-13T00:00:05+00:00",
        ),
        SessionEventWrite(
            project_id="project-a",
            session_id="session-a",
            event_type="result_retrieved",
            tool_name="retrieve_result",
            result_id="ctx_1",
            payload={"raw_tokens": 400, "returned_tokens": 400},
            created_at="2026-06-13T00:00:06+00:00",
        ),
        SessionEventWrite(
            project_id="project-a",
            session_id="session-a",
            event_type="server_warning_returned",
            tool_name="repo_summary",
            payload={"warning_code": "Broad Query", "warning_count": 2},
            created_at="2026-06-13T00:00:07+00:00",
        ),
    )
    for event in writes:
        _ = events.record_event(event)


def _text_content(content: list[ContentBlock]) -> str:
    assert len(content) == 1
    first = content[0]
    assert isinstance(first, TextContent)
    text = first.text
    parsed = cast("object", json.loads(text))
    assert isinstance(parsed, dict)
    return text
