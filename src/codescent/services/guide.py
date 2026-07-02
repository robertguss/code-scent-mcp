"""Deterministic capability-and-workflow guide for CodeScent.

The guide is generated dynamically from ``core.public_surface`` so the set of
documented tools can never drift from the registered MCP surface. It contains no
analyzed source content: only the recommended workflow, the registered tools
grouped by job, and the runtime safety boundaries.
"""

from __future__ import annotations

from typing import Final, TypedDict

from codescent.core.public_surface import (
    PUBLIC_SURFACE,
    registered_mcp_tool_names,
)

# ponytail: per-group cap is a safety ceiling, not a real limit. The largest
# current group has ~13 tools; if a single group ever exceeds this the contract
# test (guide tool set == registered set) fails on purpose so a human restructures.
MAX_TOOLS_PER_GROUP: Final = 50

SERVER_NAME: Final = "CodeScent"

SUMMARY: Final = (
    "CodeScent is a local, read-only, MCP-first code-health server. Follow the "
    "workflow below and reach for each tool group by job. Every tool is local, "
    "deterministic, bounded, and never edits analyzed source."
)


class GuideWorkflowStep(TypedDict):
    step: int
    action: str
    tools: tuple[str, ...]


class GuideToolGroup(TypedDict):
    group: str
    reach_for_when: str
    tools: tuple[str, ...]
    omitted_count: int


class GuidePayload(TypedDict):
    ok: bool
    server: str
    summary: str
    workflow: tuple[GuideWorkflowStep, ...]
    tool_groups: tuple[GuideToolGroup, ...]
    safety_boundaries: tuple[str, ...]
    tool_count: int


WORKFLOW: Final[tuple[GuideWorkflowStep, ...]] = (
    {
        "step": 1,
        "action": "Initialize CodeScent state for the repo (run the `init` CLI once).",
        "tools": (),
    },
    {
        "step": 2,
        "action": (
            "Index the repo so context tools have data (run the `index` CLI; MCP "
            "context tools also auto-refresh a stale index)."
        ),
        "tools": ("get_repo_map", "get_repo_status"),
    },
    {
        "step": 3,
        "action": "Scan for deterministic code-health findings.",
        "tools": ("scan_code_health",),
    },
    {
        "step": 4,
        "action": "Pick the next finding to work on.",
        "tools": ("get_next_improvement", "list_findings"),
    },
    {
        "step": 5,
        "action": "Gather bounded context for the chosen finding.",
        "tools": ("explain_finding", "get_symbol_context"),
    },
    {
        "step": 6,
        "action": "Plan a safe, reversible refactor.",
        "tools": ("plan_refactor", "get_impact"),
    },
    {
        "step": 7,
        "action": "Identify the tests to run for the change.",
        "tools": ("suggest_tests", "select_tests"),
    },
    {
        "step": 8,
        "action": (
            "Verify the change (you run the commands; CodeScent records the "
            "caller-supplied result and never executes anything)."
        ),
        "tools": ("verify_change", "verify_refactor", "record_verification"),
    },
    {
        "step": 9,
        "action": "Mark the finding's lifecycle status and rescan to confirm.",
        "tools": ("mark_finding", "rescan"),
    },
)

SAFETY_BOUNDARIES: Final[tuple[str, ...]] = (
    "Analyzed source files are read-only; CodeScent never edits your source.",
    "No runtime network access; all analysis is local and deterministic.",
    "Writes are confined to the .codescent/ state directory in the analyzed repo.",
    (
        "Output is bounded by default; large result sets are summarized and "
        "retrievable by id."
    ),
    "CodeScent never executes commands; verification results are caller-supplied.",
)

_GROUP_ORDER: Final[tuple[str, ...]] = (
    "repository",
    "search",
    "context",
    "health",
    "planning",
    "risk",
    "guidance",
)

_GROUP_PURPOSES: Final[dict[str, str]] = {
    "repository": "Reach for these to orient: repo map, status, and task briefs.",
    "search": (
        "Reach for these to find files, content, TODOs, and tests without broad reads."
    ),
    "context": (
        "Reach for these to pull bounded context: symbols, references, "
        "callers/callees, and related files."
    ),
    "health": (
        "Reach for these to scan, prioritize, mark, and track code-health findings."
    ),
    "planning": (
        "Reach for these to plan a refactor: finding context, impact, tests, and "
        "verification."
    ),
    "risk": (
        "Reach for these to assess the risk and health of changed files before review."
    ),
    "guidance": "Reach for these to learn what CodeScent can do and how to drive it.",
}

_DEFAULT_GROUP_PURPOSE: Final = "Reach for these CodeScent tools for this job."


def _group_sort_key(group: str) -> tuple[int, str]:
    try:
        return (_GROUP_ORDER.index(group), group)
    except ValueError:
        return (len(_GROUP_ORDER), group)


def build_guide() -> GuidePayload:
    """Render the bounded capability guide from the registered MCP surface.

    Pure and deterministic: the same registered surface always yields the same
    guide. The tool list is derived from ``registered_mcp_tool_names()`` at call
    time, never hardcoded, so new tools appear here with no edit to this module.
    """
    registered = registered_mcp_tool_names()
    names_by_group: dict[str, list[str]] = {}
    for entry in PUBLIC_SURFACE.mcp_tools:
        if entry.name in registered:
            names_by_group.setdefault(entry.group, []).append(entry.name)

    tool_groups: list[GuideToolGroup] = []
    for group in sorted(names_by_group, key=_group_sort_key):
        names = sorted(names_by_group[group])
        shown = names[:MAX_TOOLS_PER_GROUP]
        tool_groups.append(
            {
                "group": group,
                "reach_for_when": _GROUP_PURPOSES.get(group, _DEFAULT_GROUP_PURPOSE),
                "tools": tuple(shown),
                "omitted_count": len(names) - len(shown),
            },
        )

    return {
        "ok": True,
        "server": SERVER_NAME,
        "summary": SUMMARY,
        "workflow": WORKFLOW,
        "tool_groups": tuple(tool_groups),
        "safety_boundaries": SAFETY_BOUNDARIES,
        "tool_count": len(registered),
    }
