from dataclasses import dataclass
from enum import StrEnum
from typing import Final, Literal, cast, get_args

# Output shape requested from the bounded search/grep tools.
# `content` is the collapse-aware default; the others trade content for a
# cheaper shape (paths, a tally, or minimal match sites). Part of the tool
# contract, so it lives in the public surface registry.
OutputMode = Literal["content", "files", "count", "usage"]
SEARCH_OUTPUT_MODES: Final[frozenset[str]] = frozenset(get_args(OutputMode))


def normalize_output_mode(value: str) -> OutputMode:
    """Map a requested output mode to a known mode, degrading unknowns.

    Args:
        value: The requested output mode (possibly an unrecognized string).

    Returns:
        The matching :data:`OutputMode`, or ``"content"`` when ``value`` is not
        a recognized mode (defensive parsing rather than a hard failure).
    """
    if value in SEARCH_OUTPUT_MODES:
        return cast("OutputMode", value)
    return "content"


class SurfaceStage(StrEnum):
    MVP = "mvp"
    POST_MVP = "post_mvp"


@dataclass(frozen=True, slots=True)
class SurfaceEntry:
    name: str
    stage: SurfaceStage
    group: str
    registered: bool


@dataclass(frozen=True, slots=True)
class PublicSurface:
    mcp_tools: tuple[SurfaceEntry, ...]
    cli_commands: tuple[SurfaceEntry, ...]


def _mvp_entry(name: str, group: str) -> SurfaceEntry:
    return SurfaceEntry(
        name=name,
        stage=SurfaceStage.MVP,
        group=group,
        registered=True,
    )


def _registered_post_mvp_entry(name: str, group: str) -> SurfaceEntry:
    return SurfaceEntry(
        name=name,
        stage=SurfaceStage.POST_MVP,
        group=group,
        registered=True,
    )


def _registered_post_mvp_cli_entry(name: str, group: str) -> SurfaceEntry:
    return SurfaceEntry(
        name=name,
        stage=SurfaceStage.POST_MVP,
        group=group,
        registered=True,
    )


# The MVP / POST_MVP / REGISTERED_POST_MVP / REGISTERED frozensets are derived
# from PUBLIC_SURFACE below (the single source of truth) -- see the derivations
# right after the tuple definition. Adding a tool to PUBLIC_SURFACE updates all
# of them with no second structure to hand-maintain (F8).

# Tool names deliberately ABSENT from the runtime surface: proposed-then-cut or
# merged-away tools. The dangling-reference guard (R14) treats any of these
# appearing in next_tools targets, prompt bodies, tool-description prose, or the
# eval seed docs as a hard build failure. A surface merge that removes a tool
# moves its name here; that single frozenset edit is the source of truth the
# guard keys on, so no shim is needed for the hard break.
ABSENT_MCP_TOOL_NAMES: Final[frozenset[str]] = frozenset(
    {
        "project_guidance",
        "project_learnings",
        "compress_generic_output",
        "retrieve_original_output",
        # Merged into list_findings(status=) (P2.1 / U10).
        "get_smell_report",
        "get_backlog",
        "get_regressions",
        "get_progress",
        # Merged into explain_finding(view=) (P2.2 / U11).
        "get_finding",
        "explain_score",
        "get_finding_context",
    },
)

MVP_CLI_COMMAND_NAMES: Final[frozenset[str]] = frozenset(
    {"init", "serve", "index", "scan", "status", "doctor"},
)

POST_MVP_CLI_COMMAND_NAMES: Final[frozenset[str]] = frozenset(
    {
        "report",
        "reset",
        "watch",
        "findings",
        "next",
        "explain",
        "export",
        "config",
        "rules",
        "ci",
        "review-diff",
    },
)

PUBLIC_SURFACE: Final[PublicSurface] = PublicSurface(
    mcp_tools=(
        _mvp_entry("get_repo_map", "repository"),
        _mvp_entry("get_repo_status", "repository"),
        _mvp_entry("search_files", "search"),
        _mvp_entry("search_content", "search"),
        _mvp_entry("find_symbol", "context"),
        _mvp_entry("get_file_context", "context"),
        _mvp_entry("get_symbol_context", "context"),
        _mvp_entry("scan_code_health", "health"),
        _mvp_entry("list_findings", "health"),
        _mvp_entry("get_next_improvement", "health"),
        _mvp_entry("plan_refactor", "planning"),
        _mvp_entry("suggest_tests", "planning"),
        _mvp_entry("mark_finding", "health"),
        _mvp_entry("rescan", "health"),
        _registered_post_mvp_entry("multi_search_content", "search"),
        _registered_post_mvp_entry("search_changed_files", "search"),
        _registered_post_mvp_entry("search_todos", "search"),
        _registered_post_mvp_entry("search_tests", "search"),
        _registered_post_mvp_entry("find_references", "context"),
        _registered_post_mvp_entry("find_callers", "context"),
        _registered_post_mvp_entry("find_callees", "context"),
        _registered_post_mvp_entry("get_related_files", "context"),
        _registered_post_mvp_entry("get_impact", "planning"),
        _registered_post_mvp_entry("verify_change", "planning"),
        _registered_post_mvp_entry("verify_refactor", "planning"),
        _registered_post_mvp_entry("get_improvement_plan", "health"),
        _registered_post_mvp_entry("get_calibration", "health"),
        _registered_post_mvp_entry("review_diff_risk", "risk"),
        _registered_post_mvp_entry("get_changed_file_health", "risk"),
        _registered_post_mvp_entry("retrieve_result", "context"),
        _registered_post_mvp_entry("context_stats", "health"),
        _registered_post_mvp_entry("select_tests", "planning"),
        _registered_post_mvp_entry("start_task", "repository"),
        _registered_post_mvp_entry("record_verification", "health"),
        _registered_post_mvp_entry("how_to_use", "guidance"),
        _registered_post_mvp_entry("resume_task", "repository"),
        _registered_post_mvp_entry("refactor_preflight", "planning"),
        _registered_post_mvp_entry("explain_finding", "planning"),
        _registered_post_mvp_entry("subjective_review", "health"),
        _registered_post_mvp_entry("answer_pack", "repository"),
        _registered_post_mvp_entry("get_architecture", "repository"),
        _registered_post_mvp_entry("get_schema", "guidance"),
    ),
    cli_commands=(
        _mvp_entry("init", "repository"),
        _mvp_entry("serve", "mcp"),
        _mvp_entry("index", "repository"),
        _mvp_entry("scan", "health"),
        _mvp_entry("status", "repository"),
        _mvp_entry("doctor", "diagnostics"),
        _registered_post_mvp_cli_entry("report", "reports"),
        _registered_post_mvp_cli_entry("reset", "repository"),
        _registered_post_mvp_cli_entry("watch", "repository"),
        _registered_post_mvp_cli_entry("findings", "health"),
        _registered_post_mvp_cli_entry("next", "health"),
        _registered_post_mvp_cli_entry("explain", "health"),
        _registered_post_mvp_cli_entry("export", "reports"),
        _registered_post_mvp_cli_entry("config", "configuration"),
        _registered_post_mvp_cli_entry("rules", "configuration"),
        _registered_post_mvp_cli_entry("ci", "ci"),
        _registered_post_mvp_cli_entry("review-diff", "ci"),
    ),
)


def _mcp_names(
    *,
    stage: SurfaceStage,
    registered: bool | None = None,
) -> frozenset[str]:
    return frozenset(
        entry.name
        for entry in PUBLIC_SURFACE.mcp_tools
        if entry.stage is stage
        and (registered is None or entry.registered is registered)
    )


# Derived from PUBLIC_SURFACE (single source of truth). Every PUBLIC_SURFACE
# entry is registered=True today, so POST_MVP == REGISTERED_POST_MVP and there
# is no separate LOCKED set (it was provably empty -- deleted with F8).
MVP_MCP_TOOL_NAMES: Final[frozenset[str]] = _mcp_names(stage=SurfaceStage.MVP)
POST_MVP_MCP_TOOL_NAMES: Final[frozenset[str]] = _mcp_names(stage=SurfaceStage.POST_MVP)
REGISTERED_POST_MVP_MCP_TOOL_NAMES: Final[frozenset[str]] = _mcp_names(
    stage=SurfaceStage.POST_MVP,
    registered=True,
)
REGISTERED_MCP_TOOL_NAMES: Final[frozenset[str]] = (
    MVP_MCP_TOOL_NAMES | REGISTERED_POST_MVP_MCP_TOOL_NAMES
)


def registered_mcp_tool_names() -> frozenset[str]:
    return frozenset(
        entry.name for entry in PUBLIC_SURFACE.mcp_tools if entry.registered
    )


def known_mcp_tool_names() -> frozenset[str]:
    """Every tool name the codebase might mention: live or removed.

    The dangling-reference guard scans prose for tokens in this vocabulary and
    asserts each resolves to a *registered* tool -- so a name that has moved to
    the absent split is flagged wherever it still appears.
    """
    return registered_mcp_tool_names() | ABSENT_MCP_TOOL_NAMES
