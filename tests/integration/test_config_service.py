from pathlib import Path

from codescent.core.models import (
    ArchitectureRule,
    ArchitectureRules,
    MaintainabilityThresholds,
    ProjectConfig,
)
from codescent.services.config import ConfigService


def test_save_round_trips_all_config_sections(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    config = ProjectConfig(
        coverage_path="reports/coverage.xml",
        architecture=ArchitectureRules(
            rules=(ArchitectureRule(layer="src/a", forbidden_imports=("b",)),),
        ),
        thresholds=MaintainabilityThresholds.strict(),
    )

    ConfigService(repo).save(config)
    loaded = ConfigService(repo).load()

    # save() must not silently drop sections it does not specifically set.
    assert loaded.coverage_path == "reports/coverage.xml"
    assert loaded.architecture.rules == config.architecture.rules
    assert loaded.thresholds.large_file_lines == 70
    assert loaded.token_budgets.context == config.token_budgets.context


def test_config_service_loads_default_coverage_path(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()

    config = ConfigService(repo).load()

    assert config.coverage_path == "coverage.xml"


def test_config_service_loads_custom_coverage_path(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    config_path = repo / ".codescent" / "config.toml"
    config_path.parent.mkdir(parents=True)
    _ = config_path.write_text('coverage_path = "reports/coverage.xml"\n')

    config = ConfigService(repo).load()

    assert config.coverage_path == "reports/coverage.xml"


def test_config_service_loads_architecture_rules(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    config_path = repo / ".codescent" / "config.toml"
    config_path.parent.mkdir(parents=True)
    _ = config_path.write_text(
        """[architecture]
rules = [{ layer = "src/app/services", forbidden_imports = ["app.cli"] }]
""",
    )

    config = ConfigService(repo).load()

    assert len(config.architecture.rules) == 1
    rule = config.architecture.rules[0]
    assert rule.layer == "src/app/services"
    assert rule.forbidden_imports == ("app.cli",)


def test_save_rule_packs_preserves_architecture_rules(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    config_path = repo / ".codescent" / "config.toml"
    config_path.parent.mkdir(parents=True)
    _ = config_path.write_text(
        """rule_packs = ["python-maintainability"]

[architecture]
rules = [{ layer = "src/app/services", forbidden_imports = ["app.cli"] }]
""",
    )

    config = ConfigService(repo).save_rule_packs(("ts-react-next",))
    reloaded = ConfigService(repo).load()
    config_text = config_path.read_text()

    assert config.rule_packs == ("ts-react-next",)
    assert reloaded.rule_packs == ("ts-react-next",)
    assert len(reloaded.architecture.rules) == 1
    assert reloaded.architecture.rules[0].forbidden_imports == ("app.cli",)
    assert "[architecture]" in config_text
    assert 'layer = "src/app/services"' in config_text
