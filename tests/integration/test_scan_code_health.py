import sqlite3
import subprocess
from contextlib import closing
from pathlib import Path
from typing import ClassVar

from pydantic import BaseModel, ConfigDict
from typer.testing import CliRunner

from codescent.cli.main import app
from codescent.core.models import MaintainabilityThresholds, ProjectConfig
from codescent.engine.rules.model import CodeHealthFinding
from codescent.services.code_health import CodeHealthService
from codescent.services.config import ConfigService


class ScanCliPayload(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    status: str
    findings_created: int
    rule_ids: tuple[str, ...]
    findings: tuple["ScanFindingPayload", ...]


class ScanFindingPayload(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    rule_id: str
    file_path: str
    stable_key: str


def test_scan_persists_run_and_findings(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    source = repo / "src" / "pkg" / "config.py"
    source.parent.mkdir(parents=True)
    _ = source.write_text(
        """STATUS = "pending-review"
OTHER_STATUS = "pending-review"
THIRD_STATUS = "pending-review"


def load_config() -> dict[str, str]:
    # TODO: split config
    # FIXME: preserve compatibility
    # HACK: keep old queue name
    return {"status": STATUS}
""",
    )
    ConfigService(repo).save(
        ProjectConfig(thresholds=MaintainabilityThresholds.strict()),
    )

    result = CliRunner().invoke(app, ["scan", "--repo", str(repo), "--json"])
    payload = ScanCliPayload.model_validate_json(result.output)

    assert result.exit_code == 0
    assert payload.status == "complete"
    assert payload.findings_created >= 2
    assert "python.todo_cluster" in payload.rule_ids
    assert "python.changed_source_without_related_test" in payload.rule_ids
    assert "python.dead_code_candidate" in payload.rule_ids
    assert "python.uncovered_symbol" not in payload.rule_ids
    assert all(finding.stable_key for finding in payload.findings)
    with closing(sqlite3.connect(repo / ".codescent" / "index.sqlite")) as connection:
        persisted_sql = "\n".join(connection.iterdump())

    assert 'INSERT INTO "scan_runs"' in persisted_sql
    assert "python.todo_cluster" in persisted_sql
    assert "python.duplicate_literal" in persisted_sql
    assert "python.changed_source_without_related_test" in persisted_sql
    assert "evidence_json" in persisted_sql


def test_changed_source_accepts_behavior_style_test_location(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    source = repo / "src" / "pkg" / "workflow.py"
    test_file = repo / "tests" / "integration" / "test_workflow.py"
    source.parent.mkdir(parents=True)
    test_file.parent.mkdir(parents=True)
    _ = source.write_text(
        """def build_daily_plan(name: str) -> str:
    return f'{name}: reconcile inbox'
""",
    )
    _ = test_file.write_text(
        """from src.pkg.workflow import build_daily_plan

def test_build_daily_plan() -> None:
    assert build_daily_plan('ana') == 'ana: reconcile inbox'
""",
    )
    _git(repo, "init")
    _git(repo, "config", "user.email", "qa@example.invalid")
    _git(repo, "config", "user.name", "QA")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "baseline")
    _ = source.write_text(
        """def build_daily_plan(name: str) -> str:
    return f'{name}: reconcile priority inbox'
""",
    )

    result = CliRunner().invoke(app, ["scan", "--repo", str(repo), "--json"])
    payload = ScanCliPayload.model_validate_json(result.output)
    changed_source_findings = {
        finding.file_path
        for finding in payload.findings
        if finding.rule_id == "python.changed_source_without_related_test"
    }

    assert result.exit_code == 0
    assert "src/pkg/workflow.py" not in changed_source_findings


def test_scan_adds_coverage_findings_when_report_present(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    source = repo / "src" / "pkg" / "workflow.py"
    source.parent.mkdir(parents=True)
    _ = source.write_text(
        """def build_daily_plan(name: str) -> str:
    normalized = name.strip()
    if normalized:
        return f"{normalized}: reconcile inbox"
    return "unknown: reconcile inbox"
""",
    )
    _ = (repo / "coverage.xml").write_text(
        """
        <coverage>
          <packages>
            <package name="pkg">
              <classes>
                <class filename="src/pkg/workflow.py">
                  <lines>
                    <line number="2" hits="0" />
                    <line number="4" hits="0" />
                  </lines>
                </class>
              </classes>
            </package>
          </packages>
        </coverage>
        """,
    )

    result = CliRunner().invoke(app, ["scan", "--repo", str(repo), "--json"])
    payload = ScanCliPayload.model_validate_json(result.output)
    coverage_findings = tuple(
        finding
        for finding in payload.findings
        if finding.rule_id == "python.uncovered_symbol"
    )

    assert result.exit_code == 0
    assert len(coverage_findings) == 1
    assert coverage_findings[0].file_path == "src/pkg/workflow.py"
    assert coverage_findings[0].stable_key.startswith("python.uncovered_symbol:")


def test_scan_uses_configured_coverage_path(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    source = repo / "src" / "pkg" / "workflow.py"
    config_path = repo / ".codescent" / "config.toml"
    report_path = repo / "reports" / "custom-coverage.xml"
    source.parent.mkdir(parents=True)
    config_path.parent.mkdir(parents=True)
    report_path.parent.mkdir(parents=True)
    _ = source.write_text(
        """def build_daily_plan(name: str) -> str:
    normalized = name.strip()
    return f"{normalized}: reconcile inbox"
""",
    )
    _ = config_path.write_text('coverage_path = "reports/custom-coverage.xml"\n')
    _ = report_path.write_text(
        """
        <coverage>
          <packages>
            <package name="pkg">
              <classes>
                <class filename="src/pkg/workflow.py">
                  <lines>
                    <line number="2" hits="0" />
                  </lines>
                </class>
              </classes>
            </package>
          </packages>
        </coverage>
        """,
    )

    result = CliRunner().invoke(app, ["scan", "--repo", str(repo), "--json"])
    payload = ScanCliPayload.model_validate_json(result.output)

    assert result.exit_code == 0
    assert "python.uncovered_symbol" in payload.rule_ids


def _noise_and_quality_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    (repo / "src" / "pkg").mkdir(parents=True)
    (repo / "tests").mkdir()
    (repo / "evals" / "precision_corpus" / "pkg").mkdir(parents=True)
    _ = (repo / "src" / "pkg" / "app.py").write_text(
        """\
STATUS = "pending-review"
OTHER = "pending-review"
THIRD = "pending-review"


def load() -> str:
    return STATUS
""",
    )
    _ = (repo / "tests" / "test_dupes.py").write_text(
        """\
STATUS = "pending-review"
OTHER = "pending-review"
THIRD = "pending-review"


def test_no_assertions() -> None:
    value = STATUS
    print(value)
""",
    )
    _ = (repo / "evals" / "precision_corpus" / "pkg" / "dupes.py").write_text(
        'A = "corpus-smell"\nB = "corpus-smell"\nC = "corpus-smell"\n',
    )
    ConfigService(repo).save(
        ProjectConfig(thresholds=MaintainabilityThresholds.strict()),
    )
    return repo


def _has_finding(
    findings: tuple[CodeHealthFinding, ...],
    rule_suffix: str,
    path_prefix: str,
) -> bool:
    return any(
        finding.rule_id.endswith(rule_suffix)
        and finding.file_path.startswith(path_prefix)
        for finding in findings
    )


def test_default_scan_suppresses_test_and_corpus_noise(tmp_path: Path) -> None:
    repo = _noise_and_quality_repo(tmp_path)

    active = CodeHealthService(repo).scan().active_findings

    # Structural noise dropped in test scope and across the corpus...
    assert not _has_finding(active, "duplicate_literal", "tests/")
    assert not any("precision_corpus/" in finding.file_path for finding in active)
    # ...but retained on real source, and test-quality rules still fire on tests.
    assert _has_finding(active, "duplicate_literal", "src/")
    assert _has_finding(active, "assertion_free_test", "tests/")


def test_scan_override_reincludes_suppressed_noise(tmp_path: Path) -> None:
    repo = _noise_and_quality_repo(tmp_path)

    active = (
        CodeHealthService(repo).scan(apply_default_suppression=False).active_findings
    )

    assert _has_finding(active, "duplicate_literal", "tests/")
    assert any("precision_corpus/" in finding.file_path for finding in active)


def _git(repo: Path, *args: str) -> None:
    _ = subprocess.run(["git", *args], cwd=repo, check=True)
