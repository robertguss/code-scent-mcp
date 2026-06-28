from __future__ import annotations

from typing import TYPE_CHECKING

from codescent.services.guide import GuidePayload, build_guide

if TYPE_CHECKING:
    from fastmcp import FastMCP

GUIDE_RESOURCE_URI = "codescent://guide"

_TOOL_DESCRIPTION = (
    "Use CodeScent to learn what it can do and how to drive it: the recommended "
    "workflow, every registered tool grouped by job with a one-line reach-for, "
    "and the runtime safety boundaries. Deterministic, bounded, and reads no "
    "analyzed source."
)


def register_guide_tools(mcp: FastMCP) -> None:
    _ = mcp.tool(description=_TOOL_DESCRIPTION)(how_to_use)
    _ = mcp.resource(
        GUIDE_RESOURCE_URI,
        name="codescent_guide",
        description="CodeScent capability and workflow guide.",
        mime_type="application/json",
    )(codescent_guide)


def how_to_use() -> GuidePayload:
    return build_guide()


def codescent_guide() -> GuidePayload:
    return build_guide()
