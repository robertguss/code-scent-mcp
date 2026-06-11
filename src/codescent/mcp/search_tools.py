from __future__ import annotations

from typing import TYPE_CHECKING, Final, TypedDict

from codescent.services.search import SearchResultPayload, SearchService

if TYPE_CHECKING:
    from fastmcp import FastMCP

SAMPLE_FILE_LIMIT: Final = 20


class SearchToolPayload(TypedDict):
    ok: bool
    query: str
    limit: int
    results: tuple[SearchResultPayload, ...]


class MultiSearchToolPayload(TypedDict):
    ok: bool
    queries: tuple[str, ...]
    limit: int
    results: tuple[SearchResultPayload, ...]


def register_search_tools(mcp: FastMCP) -> None:
    _ = mcp.tool(
        description=(
            "Use CodeScent before broad grep or large reads to search paths with "
            "bounded results and ranking reasons. This read-only tool returns "
            "paths and reasons, never source content."
        ),
    )(search_files)

    _ = mcp.tool(
        description=(
            "Use CodeScent before broad grep or large reads to search content "
            "with bounded snippets and ranking reasons. This read-only tool "
            "returns capped snippets instead of full source files."
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


def search_files(
    query: str,
    repo: str = ".",
    limit: int = SAMPLE_FILE_LIMIT,
) -> SearchToolPayload:
    results = SearchService(repo).search_files(query, limit=limit)
    return {
        "ok": True,
        "query": query,
        "limit": min(max(limit, 1), SAMPLE_FILE_LIMIT),
        "results": results,
    }


def search_content(
    query: str,
    repo: str = ".",
    limit: int = SAMPLE_FILE_LIMIT,
) -> SearchToolPayload:
    results = SearchService(repo).search_content(query, limit=limit, line_budget=1)
    return {
        "ok": True,
        "query": query,
        "limit": min(max(limit, 1), SAMPLE_FILE_LIMIT),
        "results": results,
    }


def multi_search_content(
    queries: tuple[str, ...],
    repo: str = ".",
    limit: int = SAMPLE_FILE_LIMIT,
) -> MultiSearchToolPayload:
    results = SearchService(repo).multi_search_content(
        queries,
        limit=limit,
        line_budget=1,
    )
    return {
        "ok": True,
        "queries": queries,
        "limit": min(max(limit, 1), SAMPLE_FILE_LIMIT),
        "results": results,
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
        "results": results,
    }
