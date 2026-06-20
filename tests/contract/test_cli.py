import json
import shutil
from pathlib import Path

import pytest
from tests.contract.cli_payloads import (
    CiBaselinePayload,
    CiPayload,
    CiRatchetPayload,
    ConfigPayload,
    DoctorPayload,
    ErrorPayload,
    IndexPayload,
    InitPayload,
    ResetPayload,
    RulesPayload,
    ScanPayload,
    StatusPayload,
    WatchPayload,
)
from typer.testing import CliRunner

from codescent.cli.main import app
from codescent.core.models import MaintainabilityThresholds, ProjectConfig
from codescent.services.config import ConfigService

RUNNER = CliRunner()


def test_cli_help_lists_mvp_commands() -> None:
    result = RUNNER.invoke(app, ["--help"])

    assert result.exit_code == 0
    for command in ("init", "serve", "index", "scan", "status", "doctor"):
        assert command in result.output


def test_init_index_status_doctor_round_trip(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    source = repo / "src" / "app.py"
    source.parent.mkdir(parents=True)
    _ = source.write_text("value = 1\n")

    init_result = RUNNER.invoke(app, ["init", "--repo", str(repo), "--json"])
    index_result = RUNNER.invoke(app, ["index", "--repo", str(repo), "--json"])
    scan_result = RUNNER.invoke(app, ["scan", "--repo", str(repo), "--json"])
    status_result = RUNNER.invoke(app, ["status", "--repo", str(repo), "--json"])
    doctor_result = RUNNER.invoke(app, ["doctor", "--repo", str(repo), "--json"])

    assert init_result.exit_code == 0
    assert index_result.exit_code == 0
    assert scan_result.exit_code == 0
    assert status_result.exit_code == 0
    assert doctor_result.exit_code == 0

    init_payload = InitPayload.model_validate_json(init_result.output)
    index_payload = IndexPayload.model_validate_json(index_result.output)
    scan_payload = ScanPayload.model_validate_json(scan_result.output)
    status_payload = StatusPayload.model_validate_json(status_result.output)
    doctor_payload = DoctorPayload.model_validate_json(doctor_result.output)

    assert init_payload.state_dir.endswith(".codescent")
    assert index_payload.indexed_files == 1
    assert scan_payload.findings_created >= 0
    assert isinstance(scan_payload.rule_ids, tuple)
    assert status_payload.index_fresh is True
    assert status_payload.indexed_files == 1
    assert doctor_payload.ok is True
    assert doctor_payload.checks.database_ok is True
    assert doctor_payload.checks.config_ok is True


def test_report_findings_next_explain_and_export_commands(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    source = repo / "src" / "pkg" / "config.py"
    source.parent.mkdir(parents=True)
    _ = source.write_text(
        """STATUS = "pending-review"
OTHER_STATUS = "pending-review"
THIRD_STATUS = "pending-review"


def load_config() -> str:
    # TODO: split config
    # FIXME: preserve compatibility
    # HACK: keep old queue name
    return STATUS
""",
    )
    scan_result = RUNNER.invoke(app, ["scan", "--repo", str(repo), "--json"])
    scan_payload = ScanPayload.model_validate_json(scan_result.output)
    finding_id = scan_payload.finding_ids[0]

    report_result = RUNNER.invoke(
        app,
        ["report", "--repo", str(repo), "--format", "json"],
    )
    findings_result = RUNNER.invoke(app, ["findings", "--repo", str(repo), "--json"])
    next_result = RUNNER.invoke(app, ["next", "--repo", str(repo), "--json"])
    explain_result = RUNNER.invoke(
        app,
        ["explain", finding_id, "--repo", str(repo), "--json"],
    )
    export_result = RUNNER.invoke(
        app,
        ["export", "--repo", str(repo), "--format", "markdown"],
    )

    assert report_result.exit_code == 0
    assert findings_result.exit_code == 0
    assert next_result.exit_code == 0
    assert explain_result.exit_code == 0
    assert export_result.exit_code == 0
    assert "findings" in report_result.output
    assert finding_id in findings_result.output
    assert "suggested_action" in next_result.output
    assert "score_inputs" in explain_result.output
    assert "# CodeScent Report" in export_result.output


def test_config_command_reports_full_project_surface(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    state_dir = repo / ".codescent"
    state_dir.mkdir()
    _ = (state_dir / "config.toml").write_text(
        """
include = ["src", "tests"]
exclude = ["dist", "vendor"]
language_packs = ["python"]
framework_packs = ["react"]
rule_packs = ["python-maintainability"]

[commands]
test = ["pytest"]
typecheck = ["basedpyright"]
lint = ["ruff check ."]
build = ["python -m build"]

[token_budgets]
context = 4500
file = 600
dashboard = 12000

[privacy]
runtime_network = false
allow_llm_review = false
""",
    )

    result = RUNNER.invoke(app, ["config", "--repo", str(repo), "--json"])
    payload = ConfigPayload.model_validate_json(result.output)

    assert result.exit_code == 0
    assert payload.include == ("src", "tests")
    assert payload.exclude == ("dist", "vendor")
    assert payload.language_packs == ("python",)
    assert payload.framework_packs == ("react",)
    assert payload.rule_packs == ("python-maintainability",)
    assert payload.commands["test"] == ("pytest",)
    assert payload.token_budgets["context"] == 4500
    assert payload.privacy["runtime_network"] is False


def test_rules_watch_and_reset_are_safe_and_codescent_scoped(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    source = repo / "src" / "app.py"
    source.parent.mkdir(parents=True)
    _ = source.write_text("value = 1\n")
    nested_state_like_dir = repo / "src" / ".codescent"
    nested_state_like_dir.mkdir()
    nested_marker = nested_state_like_dir / "marker.txt"
    _ = nested_marker.write_text("not top-level runtime state\n")
    sibling_state_like_dir = repo / ".codescent-backup"
    sibling_state_like_dir.mkdir()
    sibling_marker = sibling_state_like_dir / "marker.txt"
    _ = sibling_marker.write_text("not reset target\n")
    _ = RUNNER.invoke(app, ["init", "--repo", str(repo), "--json"])

    rules_result = RUNNER.invoke(app, ["rules", "--repo", str(repo), "--json"])
    watch_result = RUNNER.invoke(
        app,
        ["watch", "--repo", str(repo), "--once", "--json"],
    )
    dry_run_result = RUNNER.invoke(
        app,
        ["reset", "--repo", str(repo), "--dry-run", "--json"],
    )
    reset_result = RUNNER.invoke(
        app,
        ["reset", "--repo", str(repo), "--yes", "--json"],
    )

    rules_payload = RulesPayload.model_validate_json(rules_result.output)
    watch_payload = WatchPayload.model_validate_json(watch_result.output)
    dry_run_payload = ResetPayload.model_validate_json(dry_run_result.output)
    reset_payload = ResetPayload.model_validate_json(reset_result.output)

    assert rules_result.exit_code == 0
    assert watch_result.exit_code == 0
    assert dry_run_result.exit_code == 0
    assert reset_result.exit_code == 0
    assert "python-maintainability" in rules_payload.enabled_rule_packs
    assert watch_payload.indexed_files == 1
    assert dry_run_payload.deleted is False
    assert reset_payload.deleted is True
    assert dry_run_payload.paths == (str(repo / ".codescent"),)
    assert reset_payload.paths == (str(repo / ".codescent"),)
    assert source.exists()
    assert nested_marker.read_text() == "not top-level runtime state\n"
    assert sibling_marker.read_text() == "not reset target\n"
    assert not (repo / ".codescent").exists()


def test_reset_requires_explicit_yes() -> None:
    help_result = RUNNER.invoke(app, ["--help"])
    reset_result = RUNNER.invoke(app, ["reset"])

    assert help_result.exit_code == 0
    assert "reset" in help_result.output
    assert reset_result.exit_code != 0


def test_ci_and_review_diff_emit_json_markdown_and_threshold_exit_codes() -> None:
    shutil.rmtree(
        Path("tests/fixtures/python-basic") / ".codescent",
        ignore_errors=True,
    )

    ci_result = RUNNER.invoke(
        app,
        [
            "ci",
            "--repo",
            "tests/fixtures/python-basic",
            "--format",
            "json",
            "--threshold",
            "warn",
        ],
    )
    review_result = RUNNER.invoke(
        app,
        [
            "review-diff",
            "--repo",
            "tests/fixtures/python-basic",
            "--format",
            "markdown",
        ],
    )

    payload = CiPayload.model_validate_json(ci_result.output)

    assert ci_result.exit_code == 1
    assert "ratchet_enabled" not in json.loads(ci_result.output)
    assert payload.ok is False
    assert payload.risk_level in {"medium", "high"}
    assert payload.changed_file_health
    assert payload.suggested_tests
    assert review_result.exit_code == 0
    assert "# CodeScent Diff Review" in review_result.output
    assert "Suggested tests" in review_result.output


def test_ci_update_baseline_and_ratchet_flags(tmp_path: Path) -> None:
    repo = _repo_with_related_test(tmp_path)
    # Strict thresholds so a small function trips a warning-level finding.
    ConfigService(repo).save(
        ProjectConfig(thresholds=MaintainabilityThresholds.strict()),
    )

    baseline_result = RUNNER.invoke(
        app,
        ["ci", "--repo", str(repo), "--format", "json", "--update-baseline"],
    )
    # Introduce a new large function (warning) absent from the baseline.
    body = "\n".join(f"    step_{index} = {index}" for index in range(30))
    _ = (repo / "src" / "pkg" / "config.py").write_text(
        f"def process() -> None:\n{body}\n",
    )
    default_result = RUNNER.invoke(
        app,
        ["ci", "--repo", str(repo), "--format", "json", "--threshold", "high"],
    )
    ratchet_result = RUNNER.invoke(
        app,
        [
            "ci",
            "--repo",
            str(repo),
            "--format",
            "json",
            "--threshold",
            "high",
            "--ratchet",
        ],
    )

    baseline_payload = CiBaselinePayload.model_validate_json(baseline_result.output)
    ratchet_payload = CiRatchetPayload.model_validate_json(ratchet_result.output)

    assert baseline_result.exit_code == 0
    assert baseline_payload.ok is True
    assert baseline_payload.files_recorded == 2
    assert baseline_payload.finding_count == 0
    # Without the ratchet, the new warning trips the absolute gate.
    assert default_result.exit_code == 1
    assert "ratchet_enabled" not in json.loads(default_result.output)
    # The ratchet fails specifically on the new finding.
    assert ratchet_result.exit_code == 1
    assert ratchet_payload.ratchet_enabled is True
    assert ratchet_payload.baseline_exists is True
    assert ratchet_payload.new_finding_count >= 1
    assert any(
        finding["rule_id"] == "python.large_function"
        for finding in ratchet_payload.new_findings
    )


def test_doctor_json_reports_invalid_repo_root(tmp_path: Path) -> None:
    missing = tmp_path / "missing"

    result = RUNNER.invoke(app, ["doctor", "--repo", str(missing), "--json"])
    payload = ErrorPayload.model_validate_json(result.output)

    assert result.exit_code == 1
    assert payload.code == "invalid_repo_root"


def test_doctor_does_not_create_missing_state(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()

    result = RUNNER.invoke(app, ["doctor", "--repo", str(repo), "--json"])
    payload = DoctorPayload.model_validate_json(result.output)

    assert result.exit_code == 0
    assert payload.ok is False
    assert payload.checks.database_ok is False
    assert not (repo / ".codescent").exists()


def test_serve_delegates_to_mcp_runner(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    def fake_run_mcp() -> None:
        calls.append("run")

    monkeypatch.setattr("codescent.cli.main.run_mcp", fake_run_mcp)

    result = RUNNER.invoke(app, ["serve"])

    assert result.exit_code == 0
    assert calls == ["run"]


def test_doctor_reports_mcp_availability(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _ = RUNNER.invoke(app, ["init", "--repo", str(repo), "--json"])
    monkeypatch.setattr(
        "codescent.cli.main.mcp_available",
        lambda: False,
        raising=False,
    )

    result = RUNNER.invoke(app, ["doctor", "--repo", str(repo), "--json"])
    payload = DoctorPayload.model_validate_json(result.output)

    assert result.exit_code == 0
    assert payload.ok is False
    assert payload.checks.mcp_available is False


def _repo_with_related_test(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    source = repo / "src" / "pkg" / "config.py"
    test = repo / "tests" / "test_config.py"
    source.parent.mkdir(parents=True)
    test.parent.mkdir(parents=True)
    _ = source.write_text(
        """def load_config() -> str:
    return "ok"
""",
    )
    _ = test.write_text(
        """from src.pkg.config import load_config


def test_load_config() -> None:
    assert load_config() == "ok"
""",
    )
    return repo
