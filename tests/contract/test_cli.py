from pathlib import Path
from typing import ClassVar

import pytest
from pydantic import BaseModel, ConfigDict
from typer.testing import CliRunner

from codescent.cli.main import app

RUNNER = CliRunner()


class ScanPayload(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    findings_created: int
    rule_ids: tuple[str, ...]
    finding_ids: tuple[str, ...] = ()


class InitPayload(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    state_dir: str


class IndexPayload(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    indexed_files: int


class StatusPayload(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    index_fresh: bool
    indexed_files: int


class DoctorChecks(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    database_ok: bool
    config_ok: bool
    mcp_available: bool


class DoctorPayload(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    ok: bool
    checks: DoctorChecks


class ErrorPayload(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    code: str


class ConfigPayload(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    include: tuple[str, ...]
    exclude: tuple[str, ...]
    language_packs: tuple[str, ...]
    framework_packs: tuple[str, ...]
    rule_packs: tuple[str, ...]
    commands: dict[str, tuple[str, ...]]
    token_budgets: dict[str, int]
    privacy: dict[str, bool]


class RulesPayload(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    enabled_rule_packs: tuple[str, ...]
    disabled_rule_packs: tuple[str, ...]


class WatchPayload(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    indexed_files: int
    changed_files: tuple[str, ...]


class ResetPayload(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    deleted: bool
    paths: tuple[str, ...]


class CiPayload(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    ok: bool
    risk_level: str
    changed_file_health: tuple[dict[str, object], ...]
    suggested_tests: tuple[str, ...]


def _scan_payload(output: str) -> ScanPayload:
    return ScanPayload.model_validate_json(output)


def _init_payload(output: str) -> InitPayload:
    return InitPayload.model_validate_json(output)


def _index_payload(output: str) -> IndexPayload:
    return IndexPayload.model_validate_json(output)


def _status_payload(output: str) -> StatusPayload:
    return StatusPayload.model_validate_json(output)


def _doctor_payload(output: str) -> DoctorPayload:
    return DoctorPayload.model_validate_json(output)


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

    init_payload = _init_payload(init_result.output)
    index_payload = _index_payload(index_result.output)
    scan_payload = _scan_payload(scan_result.output)
    status_payload = _status_payload(status_result.output)
    doctor_payload = _doctor_payload(doctor_result.output)

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
    scan_payload = _scan_payload(scan_result.output)
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
    assert not (repo / ".codescent").exists()


def test_reset_requires_explicit_yes() -> None:
    help_result = RUNNER.invoke(app, ["--help"])
    reset_result = RUNNER.invoke(app, ["reset"])

    assert help_result.exit_code == 0
    assert "reset" in help_result.output
    assert reset_result.exit_code != 0


def test_ci_and_review_diff_emit_json_markdown_and_threshold_exit_codes() -> None:
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
    assert payload.ok is False
    assert payload.risk_level in {"medium", "high"}
    assert payload.changed_file_health
    assert payload.suggested_tests
    assert review_result.exit_code == 0
    assert "# CodeScent Diff Review" in review_result.output
    assert "Suggested tests" in review_result.output


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
    payload = _doctor_payload(result.output)

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
    payload = _doctor_payload(result.output)

    assert result.exit_code == 0
    assert payload.ok is False
    assert payload.checks.mcp_available is False
