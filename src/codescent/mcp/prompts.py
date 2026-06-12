from __future__ import annotations

from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from fastmcp import FastMCP

SAFETY_TEXT: Final = (
    "Do not edit source automatically. "
    "Do not override local safety constraints. "
    "Use CodeScent tools before broad file reads. "
    "Do not execute target project commands unless the user explicitly asks."
)


def register_prompts(mcp: FastMCP) -> None:
    _ = mcp.prompt(
        name="safe_refactor_finding",
        description="Plan a bounded, reversible refactor for one finding.",
    )(safe_refactor_finding)
    _ = mcp.prompt(
        name="investigate_symbol_before_editing",
        description="Investigate a symbol with bounded context before editing.",
    )(investigate_symbol_before_editing)
    _ = mcp.prompt(
        name="add_characterization_tests",
        description="Identify missing characterization tests before risky work.",
    )(add_characterization_tests)
    _ = mcp.prompt(
        name="review_changed_files_for_slop",
        description="Review changed files for deterministic slop signals.",
    )(review_changed_files_for_slop)
    _ = mcp.prompt(
        name="verify_risky_refactor",
        description="Recommend verification for a risky refactor without execution.",
    )(verify_risky_refactor)
    _ = mcp.prompt(
        name="improve_code_health",
        description="Improve code health without broad rewrites.",
    )(improve_code_health)


def safe_refactor_finding(repo: str, finding_id: str) -> str:
    return _prompt_text(
        "Safe refactor one finding",
        (
            f"Repository: {repo}",
            f"Finding id: {finding_id}",
            "Call get_finding_context, plan_refactor, get_impact, and suggest_tests.",
            "Make the smallest behavior-preserving change and keep fallback simple.",
        ),
    )


def investigate_symbol_before_editing(repo: str, symbol: str) -> str:
    return _prompt_text(
        "Investigate symbol before editing",
        (
            f"Repository: {repo}",
            f"Symbol: {symbol}",
            "Call find_symbol, get_symbol_context, references, callers, and callees.",
            "Summarize impact before proposing an edit.",
        ),
    )


def add_characterization_tests(repo: str, path: str) -> str:
    return _prompt_text(
        "Add characterization tests",
        (
            f"Repository: {repo}",
            f"Path: {path}",
            "Call search_tests and get_file_context before reading broad source.",
            "Pin current behavior with exact inputs and assertions before changes.",
        ),
    )


def review_changed_files_for_slop(repo: str) -> str:
    return _prompt_text(
        "Review changed files for slop",
        (
            f"Repository: {repo}",
            "Call search_changed_files and review_diff_risk.",
            "Report deterministic evidence only; do not invent subjective findings.",
        ),
    )


def verify_risky_refactor(repo: str, finding_id: str) -> str:
    return _prompt_text(
        "Verify risky refactor",
        (
            f"Repository: {repo}",
            f"Finding id: {finding_id}",
            "Call verify_change and get_impact.",
            "Recommend commands and missing characterization tests without execution.",
        ),
    )


def improve_code_health(repo: str) -> str:
    return _prompt_text(
        "Improve code health",
        (
            f"Repository: {repo}",
            "Call scan_code_health, get_next_improvement, and get_backlog.",
            "Prefer one small improvement over broad rewrites.",
        ),
    )


def _prompt_text(title: str, lines: tuple[str, ...]) -> str:
    return "\n".join((title, SAFETY_TEXT, *lines))
