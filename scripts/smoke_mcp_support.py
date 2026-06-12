from __future__ import annotations

import shutil
import sys
from pathlib import Path
from typing import Final

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from codescent.services.repo_index import RepoIndexService

FULL_LOOP_TOOLS: Final[tuple[str, ...]] = (
    "scan_code_health",
    "get_next_improvement",
    "get_finding_context",
    "plan_refactor",
    "suggest_tests",
    "rescan",
    "mark_finding",
)
EXPANDED_TOOL_SETS: Final[dict[tuple[str, ...], tuple[str, ...]]] = {
    ("full_loop",): FULL_LOOP_TOOLS,
    ("search_expansion",): ("multi_search_content:pending-review,workflow",),
    ("search_changed",): ("search_changed_files",),
    ("search_todos_tests",): ("search_todos:config", "search_tests:workflow"),
    ("search_frecency",): (
        "search_files:workflow",
        "search_files:workflow",
        "search_content:pending-review",
    ),
    ("graph_context",): (
        "find_references:print",
        "find_callers:print",
        "find_callees:build_daily_plan",
    ),
    ("related_files",): ("get_related_files:src/acme_tasks/workflow.py",),
    ("impact",): ("scan_code_health", "get_impact"),
    ("finding_detail",): ("scan_code_health", "get_finding"),
    ("explain_score",): ("scan_code_health", "explain_score"),
    ("backlog_progress",): (
        "scan_code_health",
        "get_backlog",
        "mark_finding_resolved",
        "rescan",
        "get_progress",
        "get_regressions",
    ),
    ("verify_change",): ("scan_code_health", "verify_change"),
    ("diff_risk",): ("review_diff_risk",),
    ("prompts",): ("prompts",),
}


def expanded_tools(tools: tuple[str, ...]) -> tuple[str, ...]:
    return EXPANDED_TOOL_SETS.get(tools, tools)


def prepare_repo_for_tools(repo: Path, tools: tuple[str, ...]) -> None:
    if tools in {("full_loop",), ("search_changed",), ("diff_risk",)}:
        shutil.rmtree(repo / ".codescent", ignore_errors=True)
    if tools == ("graph_context",):
        shutil.rmtree(repo / ".codescent", ignore_errors=True)
        _ = RepoIndexService(repo).index_repo()
