from pathlib import Path

from codescent.services.code_health import CodeHealthService
from codescent.services.task_brief import TaskBriefService


def test_task_brief_aggregates_focus_path_context_and_findings(
    tmp_path: Path,
) -> None:
    repo = _repo_with_task_target(tmp_path)
    _ = CodeHealthService(repo).scan()

    brief = TaskBriefService(repo).start_task(
        "do thing",
        focus_path="src/app/x.py",
    )

    assert brief.query == "do thing"
    assert "src/app/x.py" in brief.relevant_files
    assert "app.x.do_thing" in brief.relevant_symbols
    assert brief.related_tests == ("tests/test_x.py",)
    assert any(
        finding["file_path"] == "src/app/x.py" for finding in brief.open_findings
    )
    assert all(
        set(finding) == {"id", "rule_id", "file_path", "severity"}
        for finding in brief.open_findings
    )
    assert brief.index_fresh is True
    assert brief.index_was_stale is False
    assert brief.auto_refreshed is False
    assert brief.changed_files == ()
    assert brief.refresh_error is None
    assert brief.warnings == ()
    assert brief.confidence == "high"
    assert "get_symbol_context:app.x.do_thing" in brief.next_tools
    assert any(tool.startswith("explain_finding:") for tool in brief.next_tools)
    assert "select_tests" in brief.next_tools
    assert "TODO" not in str(brief)
    assert len(brief.relevant_files) <= 8
    assert len(brief.relevant_symbols) <= 12
    assert len(brief.related_tests) <= 8
    assert len(brief.open_findings) <= 10


def test_task_brief_can_seed_from_focus_symbol(tmp_path: Path) -> None:
    repo = _repo_with_task_target(tmp_path)
    _ = CodeHealthService(repo).scan()

    brief = TaskBriefService(repo).start_task(
        "ignored",
        focus_symbol="do_thing",
    )

    assert "src/app/x.py" in brief.relevant_files
    assert "app.x.do_thing" in brief.relevant_symbols
    assert brief.related_tests == ("tests/test_x.py",)


def test_task_brief_can_seed_from_query_search(tmp_path: Path) -> None:
    repo = _repo_with_task_target(tmp_path)
    _ = CodeHealthService(repo).scan()

    brief = TaskBriefService(repo).start_task("do_thing")

    assert "src/app/x.py" in brief.relevant_files
    assert "app.x.do_thing" in brief.relevant_symbols
    assert "tests/test_x.py" in brief.related_tests


def test_task_brief_auto_refreshes_unindexed_repo(tmp_path: Path) -> None:
    repo = _repo_with_task_target(tmp_path)

    brief = TaskBriefService(repo).start_task("do_thing")

    assert brief.index_fresh is True
    assert brief.index_was_stale is True
    assert brief.auto_refreshed is True
    assert brief.refresh_error is None
    assert set(brief.changed_files) == {"src/app/x.py", "tests/test_x.py"}
    assert "src/app/x.py" in brief.relevant_files
    assert "app.x.do_thing" in brief.relevant_symbols
    assert "tests/test_x.py" in brief.related_tests
    assert brief.confidence == "medium"
    assert any("automatically refreshed" in warning for warning in brief.warnings)


def test_task_brief_empty_query_has_bounded_fallback(tmp_path: Path) -> None:
    repo = _repo_with_task_target(tmp_path)

    brief = TaskBriefService(repo).start_task("")

    assert brief.relevant_files == ()
    assert brief.relevant_symbols == ()
    assert brief.related_tests == ()
    assert brief.open_findings == ()
    assert brief.index_fresh is True
    assert brief.index_was_stale is True
    assert brief.auto_refreshed is True
    assert brief.confidence == "low"
    assert any("no task brief context found" in warning for warning in brief.warnings)
    assert brief.next_tools == (
        "select_tests",
        "search_files",
        "search_content",
        "get_repo_map",
    )


def _repo_with_task_target(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    source = repo / "src" / "app" / "x.py"
    test = repo / "tests" / "test_x.py"
    source.parent.mkdir(parents=True)
    test.parent.mkdir()
    _ = source.write_text(
        """def do_thing() -> str:
    # TODO: split orchestration
    # FIXME: keep compatibility
    # HACK: preserve old behavior
    return "done"
""",
    )
    _ = test.write_text(
        """from app.x import do_thing


def test_do_thing() -> None:
    assert do_thing() == "done"
""",
    )
    return repo
