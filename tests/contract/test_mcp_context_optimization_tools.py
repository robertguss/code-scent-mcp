from pathlib import Path
from typing import ClassVar

import pytest
from fastmcp import Client
from mcp.types import ContentBlock, TextContent
from pydantic import BaseModel, ConfigDict

from codescent.mcp.server import mcp
from codescent.services.context_optimization import ContextOptimizationService


class RetrievedItem(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    path: str | None = None
    line: int | None = None
    symbol: str | None = None
    snippet: str | None = None


class RetrievedPayload(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    items: tuple[RetrievedItem, ...]


class RetrieveResultToolPayload(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    ok: bool
    result_id: str
    mode: str
    session_id: str
    payload: RetrievedPayload
    error_code: str | None = None
    warnings: tuple[str, ...]


class ContextStatsToolPayload(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    ok: bool
    session_id: str | None
    repo: str
    tool_calls: int
    summarized_results: int
    retrievals: int
    estimated_raw_tokens: int
    estimated_returned_tokens: int
    estimated_tokens_avoided: int
    largest_summarized_results: tuple[str, ...]
    most_used_tools: tuple[str, ...]
    warnings: tuple[str, ...]


@pytest.mark.anyio
async def test_retrieve_result_mcp_returns_stored_filtered_payload(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    service = ContextOptimizationService(str(repo))
    stored = service.store_result(
        tool_name="find_references",
        session_id="sess_mcp",
        query="load_config",
        raw_payload={
            "items": (
                {
                    "path": "src/app.py",
                    "line": 3,
                    "symbol": "load_config",
                    "snippet": "def load_config(): pass",
                },
                {
                    "path": "src/other.py",
                    "line": 8,
                    "symbol": "load_config",
                    "snippet": "load_config()",
                },
            ),
        },
        returned_payload={"summary": "2 references"},
    )

    async with Client(mcp) as client:
        result = await client.call_tool(
            "retrieve_result",
            {
                "repo": str(repo),
                "result_id": stored.result_id,
                "mode": "filtered",
                "file": "src/app.py",
                "symbol": "load_config",
                "limit": 1,
            },
        )

    payload = RetrieveResultToolPayload.model_validate_json(
        _text_content(result.content),
    )

    assert payload.ok is True
    assert payload.result_id == stored.result_id
    assert payload.mode == "filtered"
    assert payload.session_id == "sess_mcp"
    assert tuple(item.path for item in payload.payload.items) == ("src/app.py",)
    assert payload.error_code is None
    assert payload.warnings == ()


@pytest.mark.anyio
async def test_context_stats_mcp_reports_real_session_counts(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    service = ContextOptimizationService(str(repo))
    stored = service.store_result(
        tool_name="search_content",
        session_id="sess_mcp",
        query="load_config",
        raw_payload={
            "items": (
                {
                    "path": "src/app.py",
                    "line": 3,
                    "symbol": "load_config",
                    "snippet": "def load_config(): pass",
                },
            ),
        },
        returned_payload={"summary": "1 match"},
    )
    _ = service.retrieve_result(stored.result_id, mode="summary")

    async with Client(mcp) as client:
        result = await client.call_tool(
            "context_stats",
            {"repo": str(repo), "session_id": "sess_mcp"},
        )

    payload = ContextStatsToolPayload.model_validate_json(
        _text_content(result.content),
    )

    assert payload.ok is True
    assert payload.session_id == "sess_mcp"
    assert payload.tool_calls == 1
    assert payload.summarized_results == 1
    assert payload.retrievals == 1
    assert payload.largest_summarized_results == (stored.result_id,)
    assert payload.most_used_tools == ("search_content",)
    assert payload.warnings == ()


def _text_content(content: list[ContentBlock]) -> str:
    assert len(content) == 1
    first = content[0]
    assert isinstance(first, TextContent)
    return first.text
