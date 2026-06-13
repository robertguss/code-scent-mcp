from __future__ import annotations

import json
from typing import TYPE_CHECKING, ClassVar, cast

import pytest
from fastmcp import Client
from mcp.types import ContentBlock, TextContent
from pydantic import BaseModel, ConfigDict

from codescent.mcp.server import mcp
from codescent.services.result_store import ResultStoreService
from codescent.services.session_stats import ContextStatsService
from codescent.storage import RepositoryStorage, initialize_storage
from codescent.storage.repositories import SessionEventRepository

if TYPE_CHECKING:
    from pathlib import Path


class RetrievedResultModel(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    kind: str
    result_id: str
    mode: str
    summary: str
    items: tuple[dict[str, object], ...]
    remaining_count: int
    warnings: tuple[str, ...]


class ResultStoreErrorModel(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    kind: str
    code: str
    message: str
    result_id: str
    retryable: bool


@pytest.mark.anyio
async def test_retrieve_result_exact_summary_filtered_and_sample_modes(
    tmp_path: Path,
) -> None:
    stored_id = _store_symbol_results(tmp_path)

    async with Client(mcp) as client:
        exact_result = await client.call_tool(
            "retrieve_result",
            {"repo": str(tmp_path), "result_id": stored_id, "mode": "exact"},
        )
        summary_result = await client.call_tool(
            "retrieve_result",
            {"repo": str(tmp_path), "result_id": stored_id, "mode": "summary"},
        )
        filtered_result = await client.call_tool(
            "retrieve_result",
            {
                "repo": str(tmp_path),
                "result_id": stored_id,
                "mode": "filtered",
                "query": "service =",
                "file": "tests/test_users.py",
                "symbol": "UserService",
                "limit": 5,
            },
        )
        sample_result = await client.call_tool(
            "retrieve_result",
            {
                "repo": str(tmp_path),
                "result_id": stored_id,
                "mode": "sample",
                "limit": 2,
            },
        )

    exact = RetrievedResultModel.model_validate_json(
        _text_content(exact_result.content),
    )
    summary = RetrievedResultModel.model_validate_json(
        _text_content(summary_result.content),
    )
    filtered = RetrievedResultModel.model_validate_json(
        _text_content(filtered_result.content),
    )
    sample = RetrievedResultModel.model_validate_json(
        _text_content(sample_result.content),
    )

    assert exact.kind == "retrieved_result"
    assert exact.result_id == stored_id
    assert exact.mode == "exact"
    assert [item["path"] for item in exact.items] == [
        "src/users.py",
        "tests/test_users.py",
        "docs/users.md",
    ]
    assert summary.mode == "summary"
    assert summary.items == ({"type": "summary", "count": 3},)
    assert filtered.mode == "filtered"
    assert filtered.items == (
        {
            "type": "reference",
            "path": "tests/test_users.py",
            "reference_text": "UserService",
            "snippet": "service = UserService()",
        },
    )
    assert filtered.remaining_count == 0
    assert filtered.warnings == ()
    assert sample.mode == "sample"
    assert [item["path"] for item in sample.items] == ["src/users.py", "docs/users.md"]


@pytest.mark.anyio
async def test_retrieve_result_missing_and_invalid_ids_return_json_errors(
    tmp_path: Path,
) -> None:
    async with Client(mcp) as client:
        missing_result = await client.call_tool(
            "retrieve_result",
            {"repo": str(tmp_path), "result_id": "ctx_0000000000000000"},
        )
        invalid_result = await client.call_tool(
            "retrieve_result",
            {"repo": str(tmp_path), "result_id": "result-1"},
        )

    missing = ResultStoreErrorModel.model_validate_json(
        _text_content(missing_result.content),
    )
    invalid = ResultStoreErrorModel.model_validate_json(
        _text_content(invalid_result.content),
    )
    combined = f"{missing.model_dump_json()} {invalid.model_dump_json()}"

    assert missing.kind == "result_store_error"
    assert missing.code == "missing_result"
    assert missing.result_id == "ctx_0000000000000000"
    assert missing.retryable is False
    assert invalid.kind == "result_store_error"
    assert invalid.code == "invalid_result_id"
    assert invalid.message == "Result ID must be an opaque ctx_ identifier."
    assert "Traceback" not in combined


@pytest.mark.anyio
async def test_retrieve_result_records_sanitized_retrieval_events(
    tmp_path: Path,
) -> None:
    stored_id = _store_symbol_results(tmp_path)
    project_id = "project-alpha"
    session_id = "session-telemetry"

    async with Client(mcp) as client:
        retrieved_result = await client.call_tool(
            "retrieve_result",
            {
                "repo": str(tmp_path),
                "project_id": project_id,
                "session_id": session_id,
                "result_id": stored_id,
                "mode": "filtered",
                "query": "service =",
                "file": "tests/test_users.py",
                "symbol": "UserService",
                "limit": 5,
            },
        )
        missing_result = await client.call_tool(
            "retrieve_result",
            {
                "repo": str(tmp_path),
                "project_id": project_id,
                "session_id": session_id,
                "result_id": "ctx_0000000000000000",
            },
        )

    retrieved = RetrievedResultModel.model_validate_json(
        _text_content(retrieved_result.content),
    )
    missing = ResultStoreErrorModel.model_validate_json(
        _text_content(missing_result.content),
    )
    stats = ContextStatsService(tmp_path).context_stats(
        project_id=project_id,
        session_id=session_id,
    )
    events = SessionEventRepository(
        RepositoryStorage(initialize_storage(tmp_path)),
    ).list_events(project_id=project_id, session_id=session_id)
    event_payload_json = json.dumps([event.payload for event in events], sort_keys=True)

    assert retrieved.kind == "retrieved_result"
    assert missing.kind == "result_store_error"
    assert missing.code == "missing_result"
    assert stats.retrievals == 1
    assert len(events) == 1
    assert events[0].event_type == "result_retrieved"
    assert events[0].tool_name == "retrieve_result"
    assert events[0].result_id == stored_id
    assert set(events[0].payload) == {
        "exact_requested",
        "input_fingerprint",
        "result_count",
        "returned_tokens",
        "warning_count",
    }
    assert events[0].payload["result_count"] == 1
    assert "service =" not in event_payload_json
    assert "tests/test_users.py" not in event_payload_json
    assert "UserService" not in event_payload_json
    assert "service = UserService()" not in event_payload_json
    assert "snippet" not in event_payload_json
    assert "source_content" not in event_payload_json
    assert "Traceback" not in missing.model_dump_json()


def _store_symbol_results(repo: Path) -> str:
    stored = ResultStoreService(repo).store_result(
        project_id="project-alpha",
        tool_name="symbol_search",
        input_payload={"query": "UserService"},
        raw_result={
            "results": [
                {
                    "type": "definition",
                    "path": "src/users.py",
                    "name": "UserService",
                    "snippet": "class UserService: ...",
                },
                {
                    "type": "reference",
                    "path": "tests/test_users.py",
                    "reference_text": "UserService",
                    "snippet": "service = UserService()",
                },
                {
                    "type": "reference",
                    "path": "docs/users.md",
                    "reference_text": "UserService docs",
                    "snippet": "UserService docs",
                },
            ],
        },
        summary={"items": [{"type": "summary", "count": 3}]},
    )
    return stored.id


def _text_content(content: list[ContentBlock]) -> str:
    assert len(content) == 1
    first = content[0]
    assert isinstance(first, TextContent)
    text = first.text
    parsed = cast("object", json.loads(text))
    assert isinstance(parsed, dict)
    return text
