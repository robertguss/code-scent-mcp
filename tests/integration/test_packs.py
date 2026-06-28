from pathlib import Path

from codescent.core.models import MaintainabilityThresholds, ProjectConfig
from codescent.engine.packs import build_pack_registry
from codescent.services.code_health import CodeHealthService
from codescent.services.config import ConfigService
from codescent.services.repo_index import RepoIndexService


def test_python_pack_registers_parser_rules_and_context_without_behavior_regression(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    source = repo / "src" / "pkg" / "workflow.py"
    source.parent.mkdir(parents=True)
    _ = source.write_text(
        """def process() -> None:
    step_0 = 0
    step_1 = 1
    step_2 = 2
    step_3 = 3
    step_4 = 4
    step_5 = 5
    step_6 = 6
    step_7 = 7
    step_8 = 8
    step_9 = 9
    step_10 = 10
    step_11 = 11
    step_12 = 12
    step_13 = 13
    step_14 = 14
    step_15 = 15
    step_16 = 16
    step_17 = 17
    step_18 = 18
    step_19 = 19
    step_20 = 20
    step_21 = 21
    step_22 = 22
    step_23 = 23
    step_24 = 24
""",
    )

    registry = build_pack_registry(
        ProjectConfig(thresholds=MaintainabilityThresholds.strict()),
    )

    assert tuple(pack.name for pack in registry.language_packs) == (
        "python",
        "typescript",
        "go",
    )
    assert tuple(pack.name for pack in registry.rule_packs) == (
        "architecture",
        "knowledge-silo",
        "python-maintainability",
        "ts-react-next",
        "go-maintainability",
    )
    assert registry.parser_for_language("python") is not None
    assert registry.parser_for_language("typescript") is not None
    assert registry.parser_for_language("go") is not None

    ConfigService(repo).save(
        ProjectConfig(thresholds=MaintainabilityThresholds.strict()),
    )
    index_result = RepoIndexService(repo).index_repo()
    scan_result = CodeHealthService(repo).scan()

    assert index_result.indexed_files == 1
    assert "python.large_function" in scan_result.rule_ids

    config_path = repo / ".codescent" / "config.toml"
    config_path.parent.mkdir(exist_ok=True)
    _ = config_path.write_text(
        """language_packs = []
rule_packs = []
""",
    )

    disabled_index = RepoIndexService(repo).index_repo()
    disabled_scan = CodeHealthService(repo).scan()
    disabled_registry = build_pack_registry(
        ProjectConfig(language_packs=(), rule_packs=()),
    )

    assert disabled_index.indexed_files == 1
    assert disabled_registry.parser_for_language("python") is None
    assert disabled_scan.rule_ids == ()
