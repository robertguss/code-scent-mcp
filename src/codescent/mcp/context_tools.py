from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Final, TypedDict, cast

from codescent.core.paths import resolve_repo_root
from codescent.core.preservation import estimate_token_usage
from codescent.core.symbol_formatter import format_symbol_search_results
from codescent.services.context import (
    ContextService,
    GraphResultPayload,
    RelatedFilePayload,
    SymbolMatchPayload,
)
from codescent.services.result_store import JsonValue, ResultStoreService
from codescent.storage import RepositoryStorage, initialize_storage
from codescent.storage.repositories import SessionEventRepository, SessionEventWrite

if TYPE_CHECKING:
    from fastmcp import FastMCP

    from codescent.core.models import ResponseEnvelope

SAMPLE_FILE_LIMIT: Final = 20
SYMBOL_ENVELOPE_TOKEN_THRESHOLD: Final = 600
MAX_BROAD_QUERY_LENGTH: Final = 2


class FileContextToolPayload(TypedDict):
    ok: bool
    path: str
    summary: str
    symbols: tuple[str, ...]
    imports: tuple[str, ...]
    likely_tests: tuple[str, ...]
    related_files: tuple[str, ...]
    source_ranges: tuple[dict[str, str | int], ...]
    risk_notes: tuple[str, ...]
    next_tools: tuple[str, ...]


class FindSymbolToolPayload(TypedDict, total=False):
    ok: bool
    kind: str
    mode: str
    query: str
    summary: str
    items: tuple[object, ...]
    omitted_count: int
    original_result_id: str | None
    retrieval_available: bool
    retrieval_hints: tuple[str, ...]
    confidence: str
    warnings: tuple[str, ...]
    stats: dict[str, int | float] | None
    results: tuple[SymbolMatchPayload, ...]


class SymbolContextToolPayload(TypedDict):
    ok: bool
    symbol: SymbolMatchPayload
    likely_tests: tuple[str, ...]
    source_ranges: tuple[dict[str, str | int], ...]
    risk_notes: tuple[str, ...]


class GraphToolPayload(TypedDict):
    ok: bool
    query: str
    results: tuple[GraphResultPayload, ...]
    next_cursor: int | None


class RelatedFilesToolPayload(TypedDict):
    ok: bool
    path: str
    results: tuple[RelatedFilePayload, ...]
    next_cursor: int | None


def register_context_tools(mcp: FastMCP) -> None:
    _ = mcp.tool(
        description=(
            "Use CodeScent before reading a whole file. Returns bounded file "
            "context with summaries, likely tests, source ranges, and next tools."
        ),
    )(get_file_context)

    _ = mcp.tool(
        description=(
            "Use CodeScent before broad grep to find symbols by name or qualified "
            "name. Returns bounded matches with confidence and line ranges."
        ),
    )(find_symbol)

    _ = mcp.tool(
        description=(
            "Use CodeScent before reading callers or callees. Returns bounded "
            "symbol context with likely tests and source ranges, not whole files."
        ),
    )(get_symbol_context)

    _ = mcp.tool(
        description=(
            "Find bounded persisted references for a symbol or identifier with "
            "confidence labels."
        ),
    )(find_references)

    _ = mcp.tool(
        description=(
            "Find bounded persisted callers of a symbol or identifier with "
            "confidence labels."
        ),
    )(find_callers)

    _ = mcp.tool(
        description=(
            "Find bounded persisted callees from a symbol or function with "
            "confidence labels."
        ),
    )(find_callees)

    _ = mcp.tool(
        description=(
            "Find bounded related files with reasons from imports, tests, "
            "directory proximity, search similarity, and git history."
        ),
    )(get_related_files)


def get_file_context(path: str, repo: str = ".") -> FileContextToolPayload:
    payload = ContextService(repo).get_file_context(path)
    return {
        "ok": True,
        "path": payload["path"],
        "summary": payload["summary"],
        "symbols": payload["symbols"],
        "imports": payload["imports"],
        "likely_tests": payload["likely_tests"],
        "related_files": payload["related_files"],
        "source_ranges": payload["source_ranges"],
        "risk_notes": payload["risk_notes"],
        "next_tools": payload["next_tools"],
    }


def find_symbol(
    query: str,
    repo: str = ".",
    limit: int = SAMPLE_FILE_LIMIT,
    project_id: str | None = None,
    session_id: str | None = None,
) -> FindSymbolToolPayload:
    results = ContextService(repo).find_symbol(query, limit=limit)
    raw_payload = _symbol_raw_payload(query=query, limit=limit, results=results)
    raw_tokens = estimate_token_usage(json.dumps(raw_payload, sort_keys=True)).tokens
    _record_tool_called(
        repo=repo,
        project_id=project_id,
        session_id=session_id,
        query=query,
        result_count=len(results),
    )

    original_result_id: str | None = None
    if raw_tokens > SYMBOL_ENVELOPE_TOKEN_THRESHOLD:
        formatted_results = _symbol_format_results(query=query, results=results)
        preview_envelope = format_symbol_search_results(query, formatted_results)
        stored = ResultStoreService(repo).store_result(
            project_id=_project_id(repo, project_id),
            session_id=session_id,
            tool_name="find_symbol",
            input_payload={"query": query, "limit": limit},
            raw_result=cast("JsonValue", raw_payload),
            summary=preview_envelope,
            raw_token_estimate=raw_tokens,
            returned_token_estimate=estimate_token_usage(
                preview_envelope.model_dump_json(),
            ).tokens,
        )
        original_result_id = stored.id

    envelope = format_symbol_search_results(
        query,
        _symbol_format_results(query=query, results=results),
        options={"original_result_id": original_result_id},
    )
    returned_tokens = estimate_token_usage(envelope.model_dump_json()).tokens
    if original_result_id is not None:
        _record_large_result_summarized(
            repo=repo,
            project_id=project_id,
            session_id=session_id,
            result_id=original_result_id,
            query=query,
            raw_tokens=raw_tokens,
            returned_tokens=returned_tokens,
            result_count=len(results),
        )

    return {
        "ok": True,
        **_envelope_payload(envelope),
    }


def _symbol_raw_payload(
    *,
    query: str,
    limit: int,
    results: tuple[SymbolMatchPayload, ...],
) -> dict[str, JsonValue]:
    payload = {
        "query": query,
        "limit": limit,
        "results": [dict(result) for result in results],
    }
    return cast("dict[str, JsonValue]", cast("object", payload))


def _symbol_format_results(
    *,
    query: str,
    results: tuple[SymbolMatchPayload, ...],
) -> tuple[dict[str, object], ...]:
    folded_query = query.casefold()
    return tuple(
        {
            **dict(result),
            "match_type": _symbol_match_type(folded_query, result),
            "role": "definition",
            "score": result["confidence"],
        }
        for result in results
    )


def _symbol_match_type(folded_query: str, result: SymbolMatchPayload) -> str:
    if folded_query in {result["name"].casefold(), result["qualified_name"].casefold()}:
        return "exact"
    return "partial"


def _envelope_payload(envelope: ResponseEnvelope) -> FindSymbolToolPayload:
    return cast(
        "FindSymbolToolPayload",
        cast("object", envelope.model_dump(mode="python")),
    )


def _project_id(repo: str, project_id: str | None) -> str:
    if project_id is not None:
        return project_id
    return f"repo:{resolve_repo_root(repo).as_posix()}"


def _record_tool_called(
    *,
    repo: str,
    project_id: str | None,
    session_id: str | None,
    query: str,
    result_count: int,
) -> None:
    if session_id is None:
        return
    _record_session_event(
        repo=repo,
        event=SessionEventWrite(
            project_id=_project_id(repo, project_id),
            session_id=session_id,
            event_type="tool_called",
            tool_name="find_symbol",
            payload={
                "query": query,
                "result_count": result_count,
                "broad_query": len(query.strip()) <= MAX_BROAD_QUERY_LENGTH,
            },
        ),
    )


def _record_large_result_summarized(  # noqa: PLR0913
    *,
    repo: str,
    project_id: str | None,
    session_id: str | None,
    result_id: str,
    query: str,
    raw_tokens: int,
    returned_tokens: int,
    result_count: int,
) -> None:
    if session_id is None:
        return
    _record_session_event(
        repo=repo,
        event=SessionEventWrite(
            project_id=_project_id(repo, project_id),
            session_id=session_id,
            event_type="large_result_summarized",
            tool_name="find_symbol",
            result_id=result_id,
            payload={
                "query": query,
                "raw_tokens": raw_tokens,
                "returned_tokens": returned_tokens,
                "result_count": result_count,
            },
        ),
    )


def _record_session_event(*, repo: str, event: SessionEventWrite) -> None:
    state = initialize_storage(Path(repo))
    repository = SessionEventRepository(RepositoryStorage(state))
    _ = repository.record_event(event)


def get_symbol_context(
    qualified_name: str,
    repo: str = ".",
) -> SymbolContextToolPayload:
    payload = ContextService(repo).get_symbol_context(qualified_name)
    return {
        "ok": True,
        "symbol": payload["symbol"],
        "likely_tests": payload["likely_tests"],
        "source_ranges": payload["source_ranges"],
        "risk_notes": payload["risk_notes"],
    }


def find_references(
    query: str,
    repo: str = ".",
    limit: int = SAMPLE_FILE_LIMIT,
    cursor: int = 0,
) -> GraphToolPayload:
    payload = ContextService(repo).find_references(
        query,
        limit=limit,
        cursor=cursor,
    )
    return {
        "ok": True,
        "query": payload["query"],
        "results": payload["results"],
        "next_cursor": payload["next_cursor"],
    }


def find_callers(
    query: str,
    repo: str = ".",
    limit: int = SAMPLE_FILE_LIMIT,
    cursor: int = 0,
) -> GraphToolPayload:
    payload = ContextService(repo).find_callers(query, limit=limit, cursor=cursor)
    return {
        "ok": True,
        "query": payload["query"],
        "results": payload["results"],
        "next_cursor": payload["next_cursor"],
    }


def find_callees(
    query: str,
    repo: str = ".",
    limit: int = SAMPLE_FILE_LIMIT,
    cursor: int = 0,
) -> GraphToolPayload:
    payload = ContextService(repo).find_callees(query, limit=limit, cursor=cursor)
    return {
        "ok": True,
        "query": payload["query"],
        "results": payload["results"],
        "next_cursor": payload["next_cursor"],
    }


def get_related_files(
    path: str,
    repo: str = ".",
    limit: int = SAMPLE_FILE_LIMIT,
    cursor: int = 0,
) -> RelatedFilesToolPayload:
    payload = ContextService(repo).get_related_files(
        path,
        limit=limit,
        cursor=cursor,
    )
    return {
        "ok": True,
        "path": payload["path"],
        "results": payload["results"],
        "next_cursor": payload["next_cursor"],
    }
