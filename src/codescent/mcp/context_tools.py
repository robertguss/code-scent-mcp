from __future__ import annotations

from typing import TYPE_CHECKING, Final, TypedDict

from codescent.services.context import (
    ContextService,
    GraphResultPayload,
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


class FindSymbolToolPayload(TypedDict):
    ok: bool
    query: str
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
) -> FindSymbolToolPayload:
    return {
        "ok": True,
        "query": query,
        "results": ContextService(repo).find_symbol(query, limit=limit),
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
