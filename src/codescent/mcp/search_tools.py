from __future__ import annotations

from typing import TYPE_CHECKING, Final, TypedDict

from codescent.services.freshness import confidence_for_results, warnings_for_results
from codescent.services.search import SearchService
from codescent.services.search_support import SearchResultPayload  # noqa: TC001

if TYPE_CHECKING:
    from fastmcp import FastMCP

SAMPLE_FILE_LIMIT: Final = 20


class TodoSearchResultPayload(TypedDict):
    path: str
    score: float
    reasons: tuple[str, ...]
    snippet: str
    marker: str
    line: int


class TestSearchResultPayload(TypedDict):
    path: str
    score: float
    reasons: tuple[str, ...]
    snippet: str | None


class AdvisoryToolFields(TypedDict):
    warnings: tuple[str, ...]
    confidence: str
    next_tools: tuple[str, ...]


class SearchToolPayload(TypedDict):
    ok: bool
    query: str
    limit: int
    next_cursor: str | None
    results: tuple[SearchResultPayload, ...]
    warnings: tuple[str, ...]
    confidence: str
    next_tools: tuple[str, ...]


class MultiSearchToolPayload(TypedDict):
    ok: bool
    queries: tuple[str, ...]
    limit: int
    results: tuple[SearchResultPayload, ...]
    warnings: tuple[str, ...]
    confidence: str
    next_tools: tuple[str, ...]


class TodoSearchToolPayload(TypedDict):
    ok: bool
    query: str
    limit: int
    results: tuple[TodoSearchResultPayload, ...]
    warnings: tuple[str, ...]
    confidence: str
    next_tools: tuple[str, ...]


class TestSearchToolPayload(TypedDict):
    ok: bool
    query: str
    path: str | None
    symbol: str | None
    finding_id: str | None
    limit: int
    results: tuple[TestSearchResultPayload, ...]
    warnings: tuple[str, ...]
    confidence: str
    next_tools: tuple[str, ...]


def register_search_tools(mcp: FastMCP) -> None:
    _ = mcp.tool(
        description=(
            "Use CodeScent before broad grep or large reads to search paths with "
            "bounded results and ranking reasons. This read-only tool returns "
            "paths, reasons, confidence, and warnings, never source content."
        ),
    )(search_files)

    _ = mcp.tool(
        description=(
            "Use CodeScent before broad grep or large reads to search content "
            "with bounded results and ranking reasons. This read-only tool "
            "collapses each match to its enclosing function/class signature "
            "(confidence exact for Python, heuristic for TS/JS) instead of raw "
            "lines; pass expand=True for the full per-line snippets."
        ),
    )(search_content)

    _ = mcp.tool(
        description=(
            "Use CodeScent to search multiple content queries with bounded, "
            "deduped snippets and query-level ranking reasons."
        ),
    )(multi_search_content)

    _ = mcp.tool(
        description=(
            "Use CodeScent to list changed files from git status and local "
            "index drift with bounded ranking reasons. This read-only tool "
            "excludes CodeScent runtime state and generated paths."
        ),
    )(search_changed_files)

    _ = mcp.tool(
        description=(
            "Use CodeScent to find TODO, FIXME, and HACK comments with bounded "
            "one-line snippets, marker grouping, and ranking reasons."
        ),
    )(search_todos)

    _ = mcp.tool(
        description=(
            "Use CodeScent to find likely tests for a query, file path, symbol, "
            "or finding id with bounded ranking reasons."
        ),
    )(search_tests)


def search_files(
    query: str,
    repo: str = ".",
    limit: int = SAMPLE_FILE_LIMIT,
    cursor: str | None = None,
) -> SearchToolPayload:
    page = SearchService(repo).search_files_page(query, limit=limit, cursor=cursor)
    return {
        "ok": True,
        "query": query,
        "limit": min(max(limit, 1), SAMPLE_FILE_LIMIT),
        "next_cursor": page["next_cursor"],
        "results": page["results"],
        **_advisory_fields(
            has_results=bool(page["results"]),
            result_kind="file paths",
            next_tools=("search_content", "get_repo_map"),
        ),
    }


def search_content(
    query: str,
    repo: str = ".",
    limit: int = SAMPLE_FILE_LIMIT,
    cursor: str | None = None,
    expand: bool = False,
) -> SearchToolPayload:
    page = SearchService(repo).search_content_page(
        query,
        limit=limit,
        cursor=cursor,
        line_budget=1,
        expand=expand,
    )
    return {
        "ok": True,
        "query": query,
        "limit": min(max(limit, 1), SAMPLE_FILE_LIMIT),
        "next_cursor": page["next_cursor"],
        "results": page["results"],
        **_advisory_fields(
            has_results=bool(page["results"]),
            result_kind="content matches",
            next_tools=("search_files", "get_repo_map"),
        ),
    }


def multi_search_content(
    queries: tuple[str, ...],
    repo: str = ".",
    limit: int = SAMPLE_FILE_LIMIT,
    expand: bool = False,
) -> MultiSearchToolPayload:
    results = SearchService(repo).multi_search_content(
        queries,
        limit=limit,
        line_budget=1,
        expand=expand,
    )
    return {
        "ok": True,
        "queries": queries,
        "limit": min(max(limit, 1), SAMPLE_FILE_LIMIT),
        "results": results,
        **_advisory_fields(
            has_results=bool(results),
            result_kind="content matches",
            next_tools=("search_files", "search_content", "get_repo_map"),
        ),
    }


def search_changed_files(
    query: str = "",
    repo: str = ".",
    limit: int = SAMPLE_FILE_LIMIT,
) -> SearchToolPayload:
    results = SearchService(repo).search_changed_files(query, limit=limit)
    return {
        "ok": True,
        "query": query,
        "limit": min(max(limit, 1), SAMPLE_FILE_LIMIT),
        "next_cursor": None,
        "results": results,
        **_advisory_fields(
            has_results=bool(results),
            result_kind="changed files",
            next_tools=("get_repo_status", "get_repo_map"),
        ),
    }


def search_todos(
    query: str = "",
    repo: str = ".",
    limit: int = SAMPLE_FILE_LIMIT,
) -> TodoSearchToolPayload:
    results = SearchService(repo).search_todos(query, limit=limit)
    return {
        "ok": True,
        "query": query,
        "limit": min(max(limit, 1), SAMPLE_FILE_LIMIT),
        "results": results,
        **_advisory_fields(
            has_results=bool(results),
            result_kind="todo markers",
            next_tools=("search_content", "search_files"),
        ),
    }


def search_tests(  # noqa: PLR0913 - MCP tool exposes distinct target inputs.
    query: str = "",
    repo: str = ".",
    path: str | None = None,
    symbol: str | None = None,
    finding_id: str | None = None,
    limit: int = SAMPLE_FILE_LIMIT,
) -> TestSearchToolPayload:
    results = SearchService(repo).search_tests(
        query,
        path=path,
        symbol=symbol,
        finding_id=finding_id,
        limit=limit,
    )
    return {
        "ok": True,
        "query": query,
        "path": path,
        "symbol": symbol,
        "finding_id": finding_id,
        "limit": min(max(limit, 1), SAMPLE_FILE_LIMIT),
        "results": results,
        **_advisory_fields(
            has_results=bool(results),
            result_kind="likely tests",
            next_tools=("select_tests", "search_files", "search_content"),
        ),
    }


def _advisory_fields(
    *,
    has_results: bool,
    result_kind: str,
    next_tools: tuple[str, ...],
) -> AdvisoryToolFields:
    return {
        "warnings": warnings_for_results(
            has_results=has_results,
            result_kind=result_kind,
        ),
        "confidence": confidence_for_results(has_results=has_results),
        "next_tools": next_tools,
    }
