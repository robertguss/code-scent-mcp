from __future__ import annotations

from typing import TYPE_CHECKING

from codescent.core.paths import resolve_repo_root
from codescent.mcp.session_context import resolve_session_id
from codescent.services.session_stats import ContextStatsService

if TYPE_CHECKING:
    from fastmcp import FastMCP


def register_session_stats_tools(mcp: FastMCP) -> None:
    _ = mcp.tool(
        description=(
            "Bounded MCP context and token-savings stats for a local agent "
            "session; reads sanitized .codescent event data and never returns "
            "raw source, raw results, or full query payloads. e.g. "
            "context_stats(session_id='default')."
        ),
    )(context_stats)


def context_stats(
    session_id: str = "",
    repo: str = ".",
    project_id: str | None = None,
) -> dict[str, object]:
    # Default to the live server session and the repo-derived project id -- the
    # same identity the tool-call emitters key events under -- so a caller that
    # passes nothing still reads its own activity instead of an empty "default"
    # bucket. Explicit arguments are honored.
    repo_root = resolve_repo_root(repo)
    resolved_project_id = project_id or f"repo:{repo_root.as_posix()}"
    stats = ContextStatsService(repo_root).context_stats(
        project_id=resolved_project_id,
        session_id=resolve_session_id(session_id),
    )
    return stats.to_payload()
