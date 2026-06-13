from __future__ import annotations

from typing import TYPE_CHECKING

from codescent.core.paths import resolve_repo_root
from codescent.services.session_stats import ContextStatsService

if TYPE_CHECKING:
    from fastmcp import FastMCP


def register_session_stats_tools(mcp: FastMCP) -> None:
    _ = mcp.tool(
        description=(
            "Use CodeScent to inspect bounded MCP context and token savings "
            "stats for a local agent session. This tool reads sanitized "
            ".codescent event data and never returns raw source, raw results, "
            "or full query payloads."
        ),
    )(context_stats)


def context_stats(
    session_id: str,
    repo: str = ".",
    project_id: str = "default",
) -> dict[str, object]:
    repo_root = resolve_repo_root(repo)
    stats = ContextStatsService(repo_root).context_stats(
        project_id=project_id,
        session_id=session_id,
    )
    return stats.to_payload()
