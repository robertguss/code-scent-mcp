from pathlib import Path

from codescent.services.code_health import CodeHealthService
from codescent.services.refactor_planning import RefactorPlanningService


def test_finding_context_is_minimal_and_actionable(tmp_path: Path) -> None:
    repo = _repo_with_smell(tmp_path)
    scan = CodeHealthService(repo).scan()
    finding_id = _finding_id_for_rule(scan.finding_ids, "python.todo_cluster")

    context = RefactorPlanningService(repo).get_finding_context(finding_id)

    assert context.finding_id == finding_id
    assert context.rule_id == "python.todo_cluster"
    assert context.affected_files == ("src/pkg/config.py",)
    assert context.relevant_tests == ("tests/test_config.py",)
    assert context.source_ranges
    assert context.next_tools == ("plan_refactor", "suggest_tests")
    assert "SECRET_SENTINEL" not in context.summary


def test_plan_refactor_has_required_fields(tmp_path: Path) -> None:
    repo = _repo_with_smell(tmp_path)
    scan = CodeHealthService(repo).scan()
    finding_id = _finding_id_for_rule(scan.finding_ids, "python.duplicate_literal")

    plan = RefactorPlanningService(repo).plan_refactor(finding_id)

    assert plan.goal.startswith("Address python.duplicate_literal")
    assert plan.non_goals
    assert plan.affected_files == ("src/pkg/config.py",)
    assert "pkg.config.load_config" in plan.relevant_symbols
    assert plan.risk
    assert plan.steps
    assert plan.fallback
    assert plan.expected_behavior_preservation
    assert plan.verification_recommendations


def test_suggest_tests_recommends_without_execution(tmp_path: Path) -> None:
    repo = _repo_with_smell(tmp_path)
    scan = CodeHealthService(repo).scan()
    finding_id = _finding_id_for_rule(scan.finding_ids, "python.todo_cluster")

    suggested = RefactorPlanningService(repo).suggest_tests(finding_id)

    assert suggested.commands == ("pytest tests/test_config.py",)
    assert suggested.likely_tests == ("tests/test_config.py",)
    assert suggested.executes_in_v1 is False
    assert not (repo / ".pytest_cache").exists()


def _finding_id_for_rule(finding_ids: tuple[str, ...], rule_id: str) -> str:
    return next(
        finding_id for finding_id in finding_ids if finding_id.startswith(rule_id)
    )


def _repo_with_smell(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    source = repo / "src" / "pkg" / "config.py"
    test = repo / "tests" / "test_config.py"
    source.parent.mkdir(parents=True)
    test.parent.mkdir()
    _ = source.write_text(
        """SECRET_SENTINEL = "do not leak"
STATUS = "pending-review"
OTHER_STATUS = "pending-review"
THIRD_STATUS = "pending-review"


def load_config() -> str:
    # TODO: split config
    # FIXME: preserve compatibility
    # HACK: keep old queue name
    return STATUS
""",
    )
    _ = test.write_text(
        """from pkg.config import load_config


def test_load_config() -> None:
    assert load_config() == "pending-review"
""",
    )
    return repo
