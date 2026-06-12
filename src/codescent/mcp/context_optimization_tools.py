from __future__ import annotations

from typing import TYPE_CHECKING, NotRequired, TypedDict

from codescent.services.context_optimization import (
    ContextOptimizationService,
    ResultPayload,
)

if TYPE_CHECKING:
    from fastmcp import FastMCP


class RetrieveResultToolPayload(TypedDict):
    ok: bool
    result_id: str
    mode: str
    session_id: str
    payload: ResultPayload
    error_code: NotRequired[str]
    warnings: tuple[str, ...]
    query: str | None
    file: str | None
    symbol: str | None
    limit: int
    repo: str


class ContextStatsToolPayload(TypedDict):
    ok: bool
    session_id: str | None
    repo: str
    tool_calls: int
    summarized_results: int
    retrievals: int
    estimated_raw_tokens: int
    estimated_returned_tokens: int
    estimated_tokens_avoided: int
    largest_summarized_results: tuple[str, ...]
    most_used_tools: tuple[str, ...]
    warnings: tuple[str, ...]


def register_context_optimization_tools(mcp: FastMCP) -> None:
    _ = mcp.tool(
        description=(
            "Use CodeScent to retrieve a previously summarized local result by "
            "opaque result id. This tool is source-read-only for analyzed files "
            "and returns bounded payloads."
        ),
    )(retrieve_result)

    _ = mcp.tool(
        description=(
            "Use CodeScent to inspect local context savings statistics for "
            "summarized results and retrievals without returning source content."
        ),
    )(context_stats)


def retrieve_result(  # noqa: PLR0913 - MCP tool exposes filter parameters.
    result_id: str,
    repo: str = ".",
    query: str | None = None,
    file: str | None = None,
    symbol: str | None = None,
    session_id: str | None = None,
    limit: int = 50,
    mode: str = "exact",
) -> RetrieveResultToolPayload:
    bounded_limit = min(max(limit, 1), 50)
    payload = ContextOptimizationService(repo).retrieve_result(
        result_id,
        mode=mode,
        query=query,
        file=file,
        symbol=symbol,
        session_id=session_id,
        limit=bounded_limit,
    )
    return {
        **payload,
        "query": query,
        "file": file,
        "symbol": symbol,
        "limit": bounded_limit,
        "repo": repo,
    }


def context_stats(
    repo: str = ".",
    session_id: str | None = None,
) -> ContextStatsToolPayload:
    payload = ContextOptimizationService(repo).context_stats(session_id=session_id)
    return {
        **payload,
        "repo": repo,
    }
