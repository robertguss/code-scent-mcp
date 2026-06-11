from pathlib import Path

from scripts.smoke_lx_data_lake import (
    LX_REQUIRED_EXCLUDES,
    build_smoke_plan,
)


def test_lx_smoke_uses_required_exclusions(tmp_path: Path) -> None:
    repo = tmp_path / "lx_data_lake"
    plan = build_smoke_plan(repo)

    required = {
        ".env",
        ".git",
        ".venv",
        "__pycache__",
        ".ruff_cache",
        ".pytest_cache",
        "data",
        "archive",
        ".codescent",
    }

    assert required <= set(LX_REQUIRED_EXCLUDES)
    assert plan.repo == repo
    assert plan.excluded_paths == tuple(sorted(required))
    assert plan.tool_calls == (
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
        "plan_refactor",
        "suggest_tests",
        "rescan",
    )
