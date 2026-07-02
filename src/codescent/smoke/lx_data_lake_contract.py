from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from pathlib import Path

type JsonValue = (
    None | bool | int | float | str | list["JsonValue"] | dict[str, "JsonValue"]
)

LX_REQUIRED_EXCLUDES: Final = (
    ".codescent",
    ".env",
    ".git",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "archive",
    "data",
)

SMOKE_TOOL_CALLS: Final = (
    "get_repo_map",
    "get_repo_status",
    "search_files",
    "search_content",
    "find_symbol",
    "get_file_context",
    "get_symbol_context",
    "scan_code_health",
    "list_findings",
    "get_finding_context",
    "plan_refactor",
    "suggest_tests",
    "rescan",
)


@dataclass(frozen=True, slots=True)
class SmokePlan:
    repo: Path
    excluded_paths: tuple[str, ...]
    tool_calls: tuple[str, ...]


def build_smoke_plan(repo: Path) -> SmokePlan:
    return SmokePlan(
        repo=repo,
        excluded_paths=tuple(sorted(LX_REQUIRED_EXCLUDES)),
        tool_calls=SMOKE_TOOL_CALLS,
    )
