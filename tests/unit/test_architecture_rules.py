from pathlib import Path

from codescent.core.models import ArchitectureRule, ArchitectureRules, ProjectConfig
from codescent.engine.packs import build_pack_registry
from codescent.engine.rules.architecture import (
    MAX_ARCHITECTURE_FINDINGS,
    scan_architecture,
)


def test_scan_architecture_is_noop_without_rules(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    source = repo / "src" / "app" / "services" / "workflow.py"
    source.parent.mkdir(parents=True)
    _ = source.write_text("from app.cli.main import run\n")

    assert scan_architecture(repo) == ()


def test_scan_architecture_finds_configured_boundary_violation(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    source = repo / "src" / "app" / "services" / "workflow.py"
    source.parent.mkdir(parents=True)
    _ = source.write_text("from app.cli.main import run\n")
    config = ProjectConfig(
        architecture=ArchitectureRules(
            rules=(
                ArchitectureRule(
                    layer="src/app/services",
                    forbidden_imports=("app.cli",),
                ),
            ),
        ),
    )

    findings = scan_architecture(repo, config=config)

    assert len(findings) == 1
    finding = findings[0]
    assert finding.rule_id == "architecture.boundary_violation"
    assert finding.file_path == "src/app/services/workflow.py"
    assert finding.severity == "warning"
    assert finding.confidence == 0.95
    assert finding.evidence == {
        "layer": "src/app/services",
        "imported": "app.cli.main",
        "line": 1,
    }


def test_scan_architecture_resolves_relative_imports(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    source = repo / "src" / "app" / "services" / "workflow.py"
    source.parent.mkdir(parents=True)
    _ = source.write_text("from ..cli.main import run\n")
    config = ProjectConfig(
        architecture=ArchitectureRules(
            rules=(
                ArchitectureRule(
                    layer="src/app/services",
                    forbidden_imports=("app.cli",),
                ),
            ),
        ),
    )

    findings = scan_architecture(repo, config=config)

    assert len(findings) == 1
    assert findings[0].evidence["imported"] == "app.cli.main"


def test_scan_architecture_allows_non_forbidden_imports(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    source = repo / "src" / "app" / "services" / "workflow.py"
    source.parent.mkdir(parents=True)
    _ = source.write_text("from app.shared.helpers import normalize\n")
    config = ProjectConfig(
        architecture=ArchitectureRules(
            rules=(
                ArchitectureRule(
                    layer="src/app/services",
                    forbidden_imports=("app.cli",),
                ),
            ),
        ),
    )

    assert scan_architecture(repo, config=config) == ()


def test_scan_architecture_bounds_findings_deterministically(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    services = repo / "src" / "app" / "services"
    services.mkdir(parents=True)
    for index in range(MAX_ARCHITECTURE_FINDINGS + 5):
        _ = (services / f"workflow_{index:03}.py").write_text(
            "from app.cli.main import run\n",
        )
    config = ProjectConfig(
        architecture=ArchitectureRules(
            rules=(
                ArchitectureRule(
                    layer="src/app/services",
                    forbidden_imports=("app.cli",),
                ),
            ),
        ),
    )

    first = scan_architecture(repo, config=config)
    second = scan_architecture(repo, config=config)

    assert len(first) == MAX_ARCHITECTURE_FINDINGS
    assert tuple(finding.stable_key for finding in first) == tuple(
        finding.stable_key for finding in second
    )
    assert first[0].file_path == "src/app/services/workflow_000.py"
    assert first[-1].file_path == "src/app/services/workflow_099.py"
    assert all(
        set(finding.evidence) == {"layer", "imported", "line"} for finding in first
    )


def test_architecture_pack_runs_configured_rules(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    source = repo / "src" / "app" / "services" / "workflow.py"
    source.parent.mkdir(parents=True)
    _ = source.write_text("from app.cli.main import run\n")
    config = ProjectConfig(
        rule_packs=(),
        architecture=ArchitectureRules(
            rules=(
                ArchitectureRule(
                    layer="src/app/services",
                    forbidden_imports=("app.cli",),
                ),
            ),
        ),
    )
    registry = build_pack_registry(config)

    findings = registry.scan_rule_packs(repo)

    # knowledge-silo and generic are always-on like architecture. knowledge-silo
    # self-disables here (the tmp repo has no git history) and generic only fires
    # on files outside the specific packs' suffixes, so neither adds findings.
    assert tuple(pack.name for pack in registry.rule_packs) == (
        "architecture",
        "knowledge-silo",
        "generic",
    )
    assert [finding.rule_id for finding in findings] == [
        "architecture.boundary_violation",
    ]
