from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Literal, cast

from codescent.core.paths import resolve_repo_root
from codescent.core.preservation import estimate_token_usage
from codescent.mcp.session_context import resolve_session_id
from codescent.services.result_store import (
    DEFAULT_RETRIEVE_LIMIT,
    ResultStoreError,
    ResultStoreService,
    RetrieveMode,
)
from codescent.storage import RepositoryStorage, initialize_storage
from codescent.storage.repositories import SessionEventRepository, SessionEventWrite

if TYPE_CHECKING:
    from fastmcp import FastMCP

ResultMode = Literal["exact", "summary", "filtered", "sample"]
ResultToolPayload = dict[str, object]


def register_result_tools(mcp: FastMCP) -> None:
    _ = mcp.tool(
        description=(
            "Retrieve a stored CodeScent result by its opaque ctx_ result id "
            "without rerunning searches: mode selects exact, summary, filtered, "
            "or sample, and output is bounded by limit. The result_id is minted "
            "by tools like answer_pack, get_backlog, and get_smell_report when "
            "they omit items. e.g. retrieve_result(result_id='ctx_ab12...', "
            "mode='summary')."
        ),
    )(retrieve_result)


def retrieve_result(  # noqa: PLR0913 - MCP tool exposes distinct filters.
    result_id: str,
    repo: str = ".",
    query: str | None = None,
    file: str | None = None,
    symbol: str | None = None,
    limit: int = DEFAULT_RETRIEVE_LIMIT,
    mode: ResultMode = "exact",
    project_id: str | None = None,
    session_id: str | None = None,
) -> ResultToolPayload:
    try:
        payload = ResultStoreService(repo).retrieve_result(
            result_id,
            mode=_retrieve_mode(mode),
            limit=limit,
            query=query,
            file=file,
            symbol=symbol,
        )
        _record_result_retrieved(
            repo=repo,
            project_id=project_id,
            session_id=session_id,
            result_id=result_id,
            mode=mode,
            limit=limit,
            query=query,
            file=file,
            symbol=symbol,
            payload=cast("ResultToolPayload", cast("object", payload)),
        )
        return cast("ResultToolPayload", cast("object", payload))
    except ResultStoreError as exc:
        return cast("ResultToolPayload", cast("object", exc.to_payload()))


def _retrieve_mode(mode: ResultMode) -> RetrieveMode:
    return mode


def _record_result_retrieved(  # noqa: PLR0913 - Mirrors MCP tool parameters.
    *,
    repo: str,
    project_id: str | None,
    session_id: str | None,
    result_id: str,
    mode: ResultMode,
    limit: int,
    query: str | None,
    file: str | None,
    symbol: str | None,
    payload: ResultToolPayload,
) -> None:
    returned_tokens = estimate_token_usage(
        json.dumps(payload, sort_keys=True, default=str),
    ).tokens
    items = payload.get("items")
    warnings = payload.get("warnings")
    _record_session_event(
        repo=repo,
        event=SessionEventWrite(
            project_id=_project_id(repo, project_id),
            session_id=resolve_session_id(session_id),
            event_type="result_retrieved",
            tool_name="retrieve_result",
            result_id=result_id,
            payload={
                "input": {
                    "mode": mode,
                    "limit": limit,
                    "query_filter": query is not None,
                    "file_filter": file is not None,
                    "symbol_filter": symbol is not None,
                },
                "returned_tokens": returned_tokens,
                "result_count": _collection_length(items),
                "warning_count": _collection_length(warnings),
                "exact_requested": mode == "exact",
            },
        ),
    )


def _collection_length(value: object) -> int:
    if isinstance(value, tuple):
        return len(cast("tuple[object, ...]", value))
    if isinstance(value, list):
        return len(cast("list[object]", value))
    return 0


def _project_id(repo: str, project_id: str | None) -> str:
    if project_id is not None:
        return project_id
    return f"repo:{resolve_repo_root(repo).as_posix()}"


def _record_session_event(*, repo: str, event: SessionEventWrite) -> None:
    state = initialize_storage(Path(repo))
    repository = SessionEventRepository(RepositoryStorage(state))
    _ = repository.record_event(event)
