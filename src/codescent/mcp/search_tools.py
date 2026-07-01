from __future__ import annotations

from typing import TYPE_CHECKING, Final, TypedDict

from codescent.core.defensive import coerce_int, or_empty, resolve_query
from codescent.core.public_surface import normalize_output_mode
from codescent.engine.search.constraints import constraint_warnings
from codescent.services.freshness import confidence_for_results, warnings_for_results
from codescent.services.search import SearchService
from codescent.services.search_support import SearchPagePayload, SearchResultPayload

if TYPE_CHECKING:
    from fastmcp import FastMCP

    from codescent.core.public_surface import OutputMode

SAMPLE_FILE_LIMIT: Final = 20

# A well-formed empty page for the graceful 0-result fallback: a malformed search
# input degrades to this bounded result instead of raising.
_EMPTY_PAGE: Final[SearchPagePayload] = {"results": (), "next_cursor": None}


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
    constraint_warnings: tuple[str, ...]


class FileResultPayload(TypedDict):
    # output_mode="files": distinct locations only, no snippets/symbols.
    path: str


class UsageResultPayload(TypedDict):
    # output_mode="usage": minimal reference-style match sites for impact scans.
    path: str
    line: int | None
    symbol: str | None


class MatchCountPayload(TypedDict):
    # output_mode="count": a tally instead of content.
    total_matches: int
    file_count: int


# One result field across every output mode; each mode emits a homogeneous tuple.
SearchResultItem = SearchResultPayload | FileResultPayload | UsageResultPayload


class SearchToolPayload(TypedDict):
    ok: bool
    query: str
    limit: int
    output_mode: str
    next_cursor: str | None
    results: tuple[SearchResultItem, ...]
    count: MatchCountPayload | None
    warnings: tuple[str, ...]
    confidence: str
    next_tools: tuple[str, ...]
    constraint_warnings: tuple[str, ...]


class MultiSearchToolPayload(TypedDict):
    ok: bool
    queries: tuple[str, ...]
    limit: int
    output_mode: str
    results: tuple[SearchResultItem, ...]
    count: MatchCountPayload | None
    warnings: tuple[str, ...]
    confidence: str
    next_tools: tuple[str, ...]
    constraint_warnings: tuple[str, ...]


class TodoSearchToolPayload(TypedDict):
    ok: bool
    query: str
    limit: int
    results: tuple[TodoSearchResultPayload, ...]
    warnings: tuple[str, ...]
    confidence: str
    next_tools: tuple[str, ...]
    constraint_warnings: tuple[str, ...]


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
    constraint_warnings: tuple[str, ...]


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
            "with bounded results and ranking reasons. Collapses each match to "
            "its enclosing function/class signature (exact for Python, heuristic "
            "for TS/JS); pass expand=True for full lines. output_mode picks the "
            "shape: content (default), files, count, or usage. constraints (see "
            "get_schema) prefilters candidates, e.g. 'src/ *.py git:modified'."
        ),
    )(search_content)

    _ = mcp.tool(
        description=(
            "Use CodeScent to search multiple content queries with bounded, "
            "deduped snippets and query-level ranking reasons. output_mode picks "
            "the shape: content, files, count, or usage."
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


def search_files(  # noqa: PLR0913 - additive defensive alias for sloppy inputs.
    query: str = "",
    repo: str = ".",
    limit: int = SAMPLE_FILE_LIMIT,
    cursor: str | None = None,
    output_mode: str = "content",
    pattern: str | None = None,
    constraints: str = "",
) -> SearchToolPayload:
    query = resolve_query(query, pattern)
    limit = coerce_int(limit, default=SAMPLE_FILE_LIMIT)
    mode = normalize_output_mode(output_mode)
    # ponytail: file results carry no symbol/line, so usage has nothing to show;
    # degrade it to content rather than emit null-filled usage sites.
    if mode == "usage":
        mode = "content"
    page = or_empty(
        lambda: SearchService(repo).search_files_page(
            query, limit=limit, cursor=cursor, constraints=constraints
        ),
        _EMPTY_PAGE,
    )
    matches = page["results"]
    results, count = _shape_results(matches, mode)
    return {
        "ok": True,
        "query": query,
        "limit": min(max(limit, 1), SAMPLE_FILE_LIMIT),
        "output_mode": mode,
        "next_cursor": page["next_cursor"],
        "results": results,
        "count": count,
        **_advisory_fields(
            has_results=bool(matches),
            result_kind="file paths",
            next_tools=("search_content", "get_repo_map"),
            current_tool="search_files",
            constraints=constraints,
        ),
    }


def search_content(  # noqa: PLR0913 - MCP tool exposes orthogonal shape toggles.
    query: str = "",
    repo: str = ".",
    limit: int = SAMPLE_FILE_LIMIT,
    cursor: str | None = None,
    expand: bool = False,
    output_mode: str = "content",
    pattern: str | None = None,
    constraints: str = "",
) -> SearchToolPayload:
    query = resolve_query(query, pattern)
    limit = coerce_int(limit, default=SAMPLE_FILE_LIMIT)
    mode = normalize_output_mode(output_mode)
    page = or_empty(
        lambda: SearchService(repo).search_content_page(
            query,
            limit=limit,
            cursor=cursor,
            line_budget=1,
            expand=expand,
            constraints=constraints,
        ),
        _EMPTY_PAGE,
    )
    matches = page["results"]
    results, count = _shape_results(matches, mode)
    return {
        "ok": True,
        "query": query,
        "limit": min(max(limit, 1), SAMPLE_FILE_LIMIT),
        "output_mode": mode,
        "next_cursor": page["next_cursor"],
        "results": results,
        "count": count,
        **_advisory_fields(
            has_results=bool(matches),
            result_kind="content matches",
            next_tools=("search_files", "get_repo_map"),
            current_tool="search_content",
            constraints=constraints,
        ),
    }


def multi_search_content(  # noqa: PLR0913 - additive constraints prefilter knob.
    queries: tuple[str, ...],
    repo: str = ".",
    limit: int = SAMPLE_FILE_LIMIT,
    expand: bool = False,
    output_mode: str = "content",
    constraints: str = "",
) -> MultiSearchToolPayload:
    limit = coerce_int(limit, default=SAMPLE_FILE_LIMIT)
    mode = normalize_output_mode(output_mode)
    matches = or_empty(
        lambda: SearchService(repo).multi_search_content(
            queries,
            limit=limit,
            line_budget=1,
            expand=expand,
            constraints=constraints,
        ),
        (),
    )
    results, count = _shape_results(matches, mode)
    return {
        "ok": True,
        "queries": queries,
        "limit": min(max(limit, 1), SAMPLE_FILE_LIMIT),
        "output_mode": mode,
        "results": results,
        "count": count,
        **_advisory_fields(
            has_results=bool(matches),
            result_kind="content matches",
            next_tools=("search_files", "search_content", "get_repo_map"),
            current_tool="multi_search_content",
            constraints=constraints,
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
        "output_mode": "content",
        "next_cursor": None,
        "results": results,
        "count": None,
        **_advisory_fields(
            has_results=bool(results),
            result_kind="changed files",
            next_tools=("get_repo_status", "get_repo_map"),
            current_tool="search_changed_files",
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
            current_tool="search_todos",
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
            current_tool="search_tests",
        ),
    }


def _shape_results(
    matches: tuple[SearchResultPayload, ...],
    mode: OutputMode,
) -> tuple[tuple[SearchResultItem, ...], MatchCountPayload | None]:
    """Reshape collapse-aware content matches into the requested output mode.

    Args:
        matches: The bounded, collapse-aware content results from the service.
        mode: The normalized output mode controlling the payload shape.

    Returns:
        A ``(results, count)`` pair: ``count`` is populated only for the
        ``count`` mode, and ``results`` is empty there.
    """
    if mode == "files":
        return _distinct_files(matches), None
    if mode == "count":
        return (), _match_count(matches)
    if mode == "usage":
        return _usage_sites(matches), None
    return matches, None


def _distinct_files(
    matches: tuple[SearchResultPayload, ...],
) -> tuple[FileResultPayload, ...]:
    paths = dict.fromkeys(match["path"] for match in matches)
    return tuple({"path": path} for path in paths)


def _usage_sites(
    matches: tuple[SearchResultPayload, ...],
) -> tuple[UsageResultPayload, ...]:
    sites: list[UsageResultPayload] = []
    for match in matches:
        symbol = match["symbol"]
        if symbol is None:
            sites.append({"path": match["path"], "line": None, "symbol": None})
            continue
        sites.append(
            {
                "path": match["path"],
                "line": symbol["start_line"],
                "symbol": symbol["name"],
            },
        )
    return tuple(sites)


def _match_count(matches: tuple[SearchResultPayload, ...]) -> MatchCountPayload:
    # ponytail: bounded to the top-N page (MAX_LIMIT=20); the tally reflects the
    # returned window, not the whole repo. Raise the service cap if true totals
    # are needed. Collapsed hits carry match_count; module-level hits count as 1.
    total = 0
    files: set[str] = set()
    for match in matches:
        files.add(match["path"])
        symbol = match["symbol"]
        total += symbol["match_count"] if symbol is not None else 1
    return {"total_matches": total, "file_count": len(files)}


def _advisory_fields(
    *,
    has_results: bool,
    result_kind: str,
    next_tools: tuple[str, ...],
    current_tool: str,
    constraints: str = "",
) -> AdvisoryToolFields:
    dropped = constraint_warnings(constraints)
    return {
        "warnings": warnings_for_results(
            has_results=has_results,
            result_kind=result_kind,
            current_tool=current_tool,
        ),
        "confidence": confidence_for_results(
            has_results=has_results,
            constraint_dropped=bool(dropped),
        ),
        "next_tools": next_tools,
        "constraint_warnings": dropped,
    }
