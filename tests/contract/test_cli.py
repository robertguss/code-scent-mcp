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


def test_reset_not_exposed() -> None:
    help_result = RUNNER.invoke(app, ["--help"])
    reset_result = RUNNER.invoke(app, ["reset"])

    assert help_result.exit_code == 0
    assert "reset" not in help_result.output
    assert reset_result.exit_code != 0


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
