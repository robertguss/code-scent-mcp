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
