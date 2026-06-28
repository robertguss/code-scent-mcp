from dataclasses import dataclass
from enum import StrEnum
from typing import Final


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


MVP_MCP_TOOL_NAMES: Final[frozenset[str]] = frozenset(
    {
        "get_repo_map",
        "get_repo_status",
        "search_files",
        "search_content",
        "find_symbol",
        "get_file_context",
        "get_symbol_context",
        "scan_code_health",
        "get_smell_report",
        "get_finding_context",
        "get_next_improvement",
        "plan_refactor",
        "suggest_tests",
        "mark_finding",
        "rescan",
    },
)

POST_MVP_MCP_TOOL_NAMES: Final[frozenset[str]] = frozenset(
    {
        "multi_search_content",
        "search_changed_files",
        "search_todos",
        "search_tests",
        "find_references",
        "find_callers",
        "find_callees",
        "get_related_files",
        "get_impact",
        "get_finding",
        "explain_score",
        "verify_change",
        "verify_refactor",
        "get_backlog",
        "get_improvement_plan",
        "get_calibration",
        "get_progress",
        "get_regressions",
        "review_diff_risk",
        "get_changed_file_health",
        "retrieve_result",
        "context_stats",
        "select_tests",
        "start_task",
        "record_verification",
        "how_to_use",
        "resume_task",
        "refactor_preflight",
    },
)

REGISTERED_POST_MVP_MCP_TOOL_NAMES: Final[frozenset[str]] = frozenset(
    {
        "find_callees",
        "find_callers",
        "find_references",
        "explain_score",
        "get_finding",
        "get_impact",
        "verify_refactor",
        "get_backlog",
        "get_improvement_plan",
        "get_calibration",
        "get_progress",
        "get_regressions",
        "get_related_files",
        "multi_search_content",
        "search_changed_files",
        "search_tests",
        "search_todos",
        "verify_change",
        "review_diff_risk",
        "get_changed_file_health",
        "retrieve_result",
        "context_stats",
        "select_tests",
        "start_task",
        "record_verification",
        "how_to_use",
        "resume_task",
        "refactor_preflight",
    },
)

REGISTERED_MCP_TOOL_NAMES: Final[frozenset[str]] = (
    MVP_MCP_TOOL_NAMES | REGISTERED_POST_MVP_MCP_TOOL_NAMES
)

LOCKED_POST_MVP_MCP_TOOL_NAMES: Final[frozenset[str]] = (
    POST_MVP_MCP_TOOL_NAMES - REGISTERED_POST_MVP_MCP_TOOL_NAMES
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
        _mvp_entry("get_smell_report", "health"),
        _mvp_entry("get_finding_context", "planning"),
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
        _registered_post_mvp_entry("get_finding", "health"),
        _registered_post_mvp_entry("explain_score", "health"),
        _registered_post_mvp_entry("verify_change", "planning"),
        _registered_post_mvp_entry("verify_refactor", "planning"),
        _registered_post_mvp_entry("get_backlog", "health"),
        _registered_post_mvp_entry("get_improvement_plan", "health"),
        _registered_post_mvp_entry("get_calibration", "health"),
        _registered_post_mvp_entry("get_progress", "health"),
        _registered_post_mvp_entry("get_regressions", "health"),
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


def registered_mcp_tool_names() -> frozenset[str]:
    return frozenset(
        entry.name for entry in PUBLIC_SURFACE.mcp_tools if entry.registered
    )


def locked_mcp_tool_names() -> frozenset[str]:
    return frozenset(
        entry.name for entry in PUBLIC_SURFACE.mcp_tools if not entry.registered
    )
