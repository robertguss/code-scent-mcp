from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Final, TypedDict, cast

from codescent.core.defensive import coerce_int, resolve_query
from codescent.core.errors import CodeScentError, ErrorCode, ErrorSeverity
from codescent.core.fuzzy import nearest_matches
from codescent.core.paths import resolve_repo_root
from codescent.core.preservation import estimate_token_usage
from codescent.core.symbol_formatter import format_symbol_search_results
from codescent.mcp.finding_payloads import ok_envelope
from codescent.mcp.session_context import resolve_session_id
from codescent.services.cbm_backend import select_graph_backend
from codescent.services.context import (
    ContextService,
    GraphResultPayload,
    RelatedFilePayload,
    SymbolMatchPayload,
)
from codescent.services.freshness import (
    confidence_for_results,
    ensure_fresh_index,
    next_tools_with_refresh_recovery,
    warnings_for_results,
)
from codescent.services.result_store import JsonValue, ResultStoreService
from codescent.services.session_stats import record_backend_resolution
from codescent.services.symbols import read_persisted_file_paths
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
    related_files_next_cursor: int | None
    source_ranges: tuple[dict[str, str | int], ...]
    risk_notes: tuple[str, ...]
    next_tools: tuple[str, ...]
    warnings: tuple[str, ...]
    confidence: str
    index_fresh: bool
    index_was_stale: bool
    auto_refreshed: bool
    changed_files: tuple[str, ...]
    refresh_error: str | None


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
    next_tools: tuple[str, ...]
    index_fresh: bool
    index_was_stale: bool
    auto_refreshed: bool
    changed_files: tuple[str, ...]
    refresh_error: str | None
    stats: dict[str, int | float] | None
    results: tuple[SymbolMatchPayload, ...]


class SymbolContextToolPayload(TypedDict):
    ok: bool
    symbol: SymbolMatchPayload
    likely_tests: tuple[str, ...]
    source_ranges: tuple[dict[str, str | int], ...]
    risk_notes: tuple[str, ...]
    warnings: tuple[str, ...]
    confidence: str
    index_fresh: bool
    index_was_stale: bool
    auto_refreshed: bool
    changed_files: tuple[str, ...]
    refresh_error: str | None
    next_tools: tuple[str, ...]


class GraphToolPayload(TypedDict):
    ok: bool
    query: str
    results: tuple[GraphResultPayload, ...]
    next_cursor: int | None
    warnings: tuple[str, ...]
    confidence: str
    next_tools: tuple[str, ...]
    index_fresh: bool
    index_was_stale: bool
    auto_refreshed: bool
    changed_files: tuple[str, ...]
    refresh_error: str | None


class RelatedFilesToolPayload(TypedDict):
    ok: bool
    path: str
    results: tuple[RelatedFilePayload, ...]
    next_cursor: int | None
    warnings: tuple[str, ...]
    confidence: str
    next_tools: tuple[str, ...]
    index_fresh: bool
    index_was_stale: bool
    auto_refreshed: bool
    changed_files: tuple[str, ...]
    refresh_error: str | None


def register_context_tools(mcp: FastMCP) -> None:
    _ = mcp.tool(
        description=(
            "Bounded file context before reading a whole file: summary, "
            "symbols, imports, likely tests, source ranges, freshness metadata, "
            "warnings, confidence, and next tools. e.g. "
            "get_file_context(path='src/app/auth.py'). Read-only for source."
        ),
    )(get_file_context)

    _ = mcp.tool(
        description=(
            "Locate symbols by name or qualified name before a broad grep: "
            "bounded matches with confidence, warnings, freshness metadata, and "
            "line ranges. The qualified_name it returns feeds get_symbol_context. "
            "e.g. find_symbol(query='TaskBriefService'). Read-only for source."
        ),
    )(find_symbol)

    _ = mcp.tool(
        description=(
            "Bounded symbol context (likely tests and source ranges, not whole "
            "files) before reading callers or callees. Pass a qualified_name "
            "from find_symbol. e.g. get_symbol_context(qualified_name="
            "'codescent.services.task_brief.TaskBriefService'). Read-only for "
            "source."
        ),
    )(get_symbol_context)

    _ = mcp.tool(
        description=(
            "Bounded persisted references for a symbol or identifier, with "
            "confidence labels. e.g. find_references(query='resolve_repo_root'). "
            "Read-only for source."
        ),
    )(find_references)

    _ = mcp.tool(
        description=(
            "Bounded persisted callers of a symbol or identifier, with "
            "confidence labels. e.g. find_callers(query='build_guide'). "
            "Read-only for source."
        ),
    )(find_callers)

    _ = mcp.tool(
        description=(
            "Bounded persisted callees from a symbol or function, with "
            "confidence labels. e.g. find_callees(query='start_task'). "
            "Read-only for source."
        ),
    )(find_callees)

    _ = mcp.tool(
        description=(
            "Bounded related files with reasons drawn from imports, tests, "
            "directory proximity, search similarity, and git history. e.g. "
            "get_related_files(path='src/app/auth.py'). Read-only for source."
        ),
    )(get_related_files)


def get_file_context(
    path: str,
    repo: str = ".",
    related_cursor: int = 0,
) -> FileContextToolPayload:
    try:
        payload = ContextService(repo).get_file_context(
            path,
            related_cursor=coerce_int(related_cursor, default=0),
        )
    except LookupError as exc:
        # ``ContextService.get_file_context`` keeps raising ``LookupError`` so
        # best-effort enrichment callers (answer_pack, task_brief) still skip
        # unindexed paths; only the tool surface converts it to a recoverable
        # not-found with nearest-path suggestions (U2).
        raise _unknown_path_error(repo, path) from exc
    return {
        "ok": True,
        "path": payload["path"],
        "summary": payload["summary"],
        "symbols": payload["symbols"],
        "imports": payload["imports"],
        "likely_tests": payload["likely_tests"],
        "related_files": payload["related_files"],
        "related_files_next_cursor": payload["related_files_next_cursor"],
        "source_ranges": payload["source_ranges"],
        "risk_notes": payload["risk_notes"],
        "next_tools": payload["next_tools"],
        "warnings": payload["warnings"],
        "confidence": payload["confidence"],
        "index_fresh": payload["index_fresh"],
        "index_was_stale": payload["index_was_stale"],
        "auto_refreshed": payload["auto_refreshed"],
        "changed_files": payload["changed_files"],
        "refresh_error": payload["refresh_error"],
    }


def _unknown_path_error(repo: str, path: str) -> CodeScentError:
    suggestions = nearest_matches(path, read_persisted_file_paths(repo), limit=5)
    return CodeScentError(
        code=ErrorCode.NOT_FOUND,
        message=f"No indexed file at {path!r}.",
        severity=ErrorSeverity.ERROR,
        details={"path": path},
        recovery={
            "suggestions": list(suggestions),
            "fix_hint": "Get valid file paths from get_repo_map or search_files.",
        },
    )


def find_symbol(  # noqa: PLR0913 - additive defensive alias for sloppy inputs.
    query: str = "",
    repo: str = ".",
    limit: int = SAMPLE_FILE_LIMIT,
    project_id: str | None = None,
    session_id: str | None = None,
    pattern: str | None = None,
) -> FindSymbolToolPayload:
    query = resolve_query(query, pattern)
    limit = coerce_int(limit, default=SAMPLE_FILE_LIMIT)
    repo_root = resolve_repo_root(repo)
    freshness = ensure_fresh_index(repo_root)
    results = ContextService(repo_root).find_symbol(query, limit=limit)
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

    payload = _envelope_payload(envelope)

    return {
        "ok": True,
        **payload,
        "warnings": (
            *payload.get("warnings", ()),
            *warnings_for_results(
                has_results=bool(results),
                result_kind="symbols",
                freshness=freshness,
            ),
        ),
        "confidence": confidence_for_results(
            has_results=bool(results),
            freshness=freshness,
        ),
        "next_tools": next_tools_with_refresh_recovery(
            ("search_files", "search_content", "get_repo_map"),
            freshness,
        ),
        "index_fresh": freshness.index_fresh,
        "index_was_stale": freshness.index_was_stale,
        "auto_refreshed": freshness.auto_refreshed,
        "changed_files": freshness.changed_files,
        "refresh_error": freshness.refresh_error,
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
    _record_session_event(
        repo=repo,
        event=SessionEventWrite(
            project_id=_project_id(repo, project_id),
            session_id=resolve_session_id(session_id),
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
    _record_session_event(
        repo=repo,
        event=SessionEventWrite(
            project_id=_project_id(repo, project_id),
            session_id=resolve_session_id(session_id),
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


def _record_backend_resolved(
    *,
    repo: str,
    project_id: str | None,
    session_id: str | None,
) -> None:
    # W3 signal (R11/R12): record whether this structural call resolved cbm or
    # native, so context_stats can report the cbm-present rate. Resolution is the
    # same cheap check the service makes (shutil.which when cbm is absent); the
    # ponytail double-resolve avoids leaking the backend into the tool payload.
    repo_root = resolve_repo_root(repo)
    record_backend_resolution(
        repo_root=repo_root,
        project_id=_project_id(repo, project_id),
        session_id=resolve_session_id(session_id),
        backend_name=select_graph_backend(repo_root).name(),
    )


def get_symbol_context(
    qualified_name: str,
    repo: str = ".",
) -> SymbolContextToolPayload:
    payload = ContextService(repo).get_symbol_context(qualified_name)
    envelope = ok_envelope(
        next_tools=("explain_finding", "find_references", "plan_refactor"),
        symbol=payload["symbol"],
        likely_tests=payload["likely_tests"],
        source_ranges=payload["source_ranges"],
        risk_notes=payload["risk_notes"],
        warnings=payload["warnings"],
        confidence=payload["confidence"],
        index_fresh=payload["index_fresh"],
        index_was_stale=payload["index_was_stale"],
        auto_refreshed=payload["auto_refreshed"],
        changed_files=payload["changed_files"],
        refresh_error=payload["refresh_error"],
    )
    return cast("SymbolContextToolPayload", cast("object", envelope))


def find_references(
    query: str,
    repo: str = ".",
    limit: int = SAMPLE_FILE_LIMIT,
    cursor: int = 0,
) -> GraphToolPayload:
    limit = coerce_int(limit, default=SAMPLE_FILE_LIMIT)
    cursor = coerce_int(cursor, default=0)
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
        "warnings": payload["warnings"],
        "confidence": payload["confidence"],
        "next_tools": payload["next_tools"],
        "index_fresh": payload["index_fresh"],
        "index_was_stale": payload["index_was_stale"],
        "auto_refreshed": payload["auto_refreshed"],
        "changed_files": payload["changed_files"],
        "refresh_error": payload["refresh_error"],
    }


def find_callers(  # noqa: PLR0913 - additive optional session-telemetry kwargs.
    query: str,
    repo: str = ".",
    limit: int = SAMPLE_FILE_LIMIT,
    cursor: int = 0,
    project_id: str | None = None,
    session_id: str | None = None,
) -> GraphToolPayload:
    limit = coerce_int(limit, default=SAMPLE_FILE_LIMIT)
    cursor = coerce_int(cursor, default=0)
    _record_backend_resolved(repo=repo, project_id=project_id, session_id=session_id)
    payload = ContextService(repo).find_callers(query, limit=limit, cursor=cursor)
    return {
        "ok": True,
        "query": payload["query"],
        "results": payload["results"],
        "next_cursor": payload["next_cursor"],
        "warnings": payload["warnings"],
        "confidence": payload["confidence"],
        "next_tools": payload["next_tools"],
        "index_fresh": payload["index_fresh"],
        "index_was_stale": payload["index_was_stale"],
        "auto_refreshed": payload["auto_refreshed"],
        "changed_files": payload["changed_files"],
        "refresh_error": payload["refresh_error"],
    }


def find_callees(  # noqa: PLR0913 - additive optional session-telemetry kwargs.
    query: str,
    repo: str = ".",
    limit: int = SAMPLE_FILE_LIMIT,
    cursor: int = 0,
    project_id: str | None = None,
    session_id: str | None = None,
) -> GraphToolPayload:
    limit = coerce_int(limit, default=SAMPLE_FILE_LIMIT)
    cursor = coerce_int(cursor, default=0)
    _record_backend_resolved(repo=repo, project_id=project_id, session_id=session_id)
    payload = ContextService(repo).find_callees(query, limit=limit, cursor=cursor)
    return {
        "ok": True,
        "query": payload["query"],
        "results": payload["results"],
        "next_cursor": payload["next_cursor"],
        "warnings": payload["warnings"],
        "confidence": payload["confidence"],
        "next_tools": payload["next_tools"],
        "index_fresh": payload["index_fresh"],
        "index_was_stale": payload["index_was_stale"],
        "auto_refreshed": payload["auto_refreshed"],
        "changed_files": payload["changed_files"],
        "refresh_error": payload["refresh_error"],
    }


def get_related_files(
    path: str,
    repo: str = ".",
    limit: int = SAMPLE_FILE_LIMIT,
    cursor: int = 0,
) -> RelatedFilesToolPayload:
    limit = coerce_int(limit, default=SAMPLE_FILE_LIMIT)
    cursor = coerce_int(cursor, default=0)
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
        "warnings": payload["warnings"],
        "confidence": payload["confidence"],
        "next_tools": payload["next_tools"],
        "index_fresh": payload["index_fresh"],
        "index_was_stale": payload["index_was_stale"],
        "auto_refreshed": payload["auto_refreshed"],
        "changed_files": payload["changed_files"],
        "refresh_error": payload["refresh_error"],
    }
