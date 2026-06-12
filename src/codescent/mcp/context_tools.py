from __future__ import annotations

from typing import TYPE_CHECKING, Final, Literal, NotRequired, TypedDict

from codescent.mcp.envelopes import envelope_for_graph_results, envelope_for_symbols
from codescent.services.context import (
    ContextService,
    GraphResultPayload,
    RelatedFilePayload,
    SymbolMatchPayload,
)

if TYPE_CHECKING:
    from fastmcp import FastMCP

SAMPLE_FILE_LIMIT: Final = 20


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


class RetrievalHintPayload(TypedDict):
    mode: Literal["exact", "summary", "filtered", "sample"]
    description: str


class FindSymbolToolPayload(TypedDict):
    ok: bool
    query: str
    results: tuple[SymbolMatchPayload, ...]
    kind: NotRequired[str]
    mode: NotRequired[str]
    summary: NotRequired[str]
    omitted_count: NotRequired[int]
    original_result_id: NotRequired[str | None]
    retrieval_available: NotRequired[bool]
    retrieval_hints: NotRequired[tuple[RetrievalHintPayload, ...]]
    confidence: NotRequired[str]
    warnings: NotRequired[tuple[str, ...]]


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
    kind: NotRequired[str]
    mode: NotRequired[str]
    summary: NotRequired[str]
    omitted_count: NotRequired[int]
    original_result_id: NotRequired[str | None]
    retrieval_available: NotRequired[bool]
    retrieval_hints: NotRequired[tuple[RetrievalHintPayload, ...]]
    confidence: NotRequired[str]
    warnings: NotRequired[tuple[str, ...]]


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
    session_id: str | None = None,
) -> FindSymbolToolPayload:
    results = ContextService(repo).find_symbol(query, limit=limit)
    envelope = envelope_for_symbols(
        {
            "tool_name": "find_symbol",
            "repo": repo,
            "session_id": session_id,
            "query": query,
        },
        results,
    )
    return {
        "ok": True,
        "query": query,
        "results": results,
        **envelope,
    }


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
    session_id: str | None = None,
) -> GraphToolPayload:
    payload = ContextService(repo).find_references(
        query,
        limit=limit,
        cursor=cursor,
    )
    envelope = envelope_for_graph_results(
        {
            "tool_name": "find_references",
            "repo": repo,
            "session_id": session_id,
            "query": query,
        },
        payload["results"],
    )
    return {
        "ok": True,
        "query": payload["query"],
        "results": payload["results"],
        "next_cursor": payload["next_cursor"],
        **envelope,
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
