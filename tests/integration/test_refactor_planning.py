from pathlib import Path

from codescent.core.models import MaintainabilityThresholds, ProjectConfig
from codescent.services.code_health import CodeHealthService
from codescent.services.config import ConfigService
from codescent.services.explain import ExplainService
from codescent.services.refactor_planning import RefactorPlanningService
from codescent.storage import RepositoryStorage, initialize_storage
from codescent.storage.repositories import FindingRepository


def test_snippet_tools_degrade_on_non_indexed_finding(tmp_path: Path) -> None:
    # Regression: explain_finding / get_finding_context / plan_refactor crashed
    # with a non-recoverable internal error for findings on non-indexed files
    # (get_file_context / source_range raise on a path absent from the index).
    # They must degrade gracefully instead.
    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    _ = (repo / "src" / "app.py").write_text("VALUE = 1\n")
    _ = (repo / "NOTES.md").write_text(
        "# notes\n" + "\n".join(f"line {index}" for index in range(400)),
    )
    ConfigService(repo).save(
        ProjectConfig(thresholds=MaintainabilityThresholds.strict()),
    )
    _ = CodeHealthService(repo).scan()
    repository = FindingRepository(RepositoryStorage(initialize_storage(repo)))
    generic = next(
        finding
        for finding in repository.list_findings()
        if finding.rule_id.startswith("generic.")
    )

    planning = RefactorPlanningService(repo)
    # None of these raise -- each returns a usable, degraded result.
    assert ExplainService(repo).explain_finding(generic.id).finding_id == generic.id
    context = planning.get_finding_context(generic.id)
    assert context.finding_id == generic.id
    assert planning.plan_refactor(generic.id).goal
    assert planning.suggest_tests(generic.id).commands
    assert planning.get_impact(finding_id=generic.id).target == generic.id


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
    ConfigService(repo).save(
        ProjectConfig(thresholds=MaintainabilityThresholds.strict()),
    )
    return repo
