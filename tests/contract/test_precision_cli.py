from __future__ import annotations

from typing import TYPE_CHECKING

from typer.testing import CliRunner

from codescent.cli.main import app
from codescent.core.models import FindingStatus
from codescent.services.code_health import CodeHealthService
from codescent.services.findings import FindingsService
from tests.precision_payloads import PrecisionPayload

if TYPE_CHECKING:
    from pathlib import Path

RUNNER = CliRunner()

_ACCEPTED_RULES = (
    "python.changed_source_without_related_test",
    "python.dead_code_candidate",
)
_DISMISSED_RULE = "python.duplicate_literal"


def test_precision_command_emits_json_per_rule_and_trend(tmp_path: Path) -> None:
    repo = _seed_accept_dismiss(tmp_path)

    result = RUNNER.invoke(app, ["precision", "--repo", str(repo), "--format", "json"])

    assert result.exit_code == 0
    payload = PrecisionPayload.model_validate_json(result.output)
    assert payload.accepted == 2
    assert payload.dismissed == 1
    assert payload.acceptance_precision == 0.667

    assert payload.rule(_DISMISSED_RULE).acceptance_precision == 0.0
    for rule_id in _ACCEPTED_RULES:
        assert payload.rule(rule_id).acceptance_precision == 1.0
    assert payload.trend[-1].accepted == 2
    assert payload.trend[-1].dismissed == 1


def test_precision_command_emits_markdown(tmp_path: Path) -> None:
    repo = _seed_accept_dismiss(tmp_path)

    result = RUNNER.invoke(
        app,
        ["precision", "--repo", str(repo), "--format", "markdown"],
    )

    assert result.exit_code == 0
    assert "# CodeScent Acceptance Precision" in result.output
    assert _DISMISSED_RULE in result.output
    assert "Health trend" in result.output


def _seed_accept_dismiss(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    source = repo / "src" / "pkg" / "config.py"
    source.parent.mkdir(parents=True)
    _ = source.write_text(
        """STATUS = "pending-review"
OTHER_STATUS = "pending-review"
THIRD_STATUS = "pending-review"
FOURTH_STATUS = "pending-review"


def load_config() -> str:
    return STATUS
""",
    )
    _ = CodeHealthService(repo).scan()
    service = FindingsService(repo)
    by_rule = {f.rule_id: f for f in service.get_smell_report().findings}
    for rule_id in _ACCEPTED_RULES:
        finding_id = by_rule[rule_id].id
        _ = service.record_verification(
            finding_id,
            command="pytest",
            exit_code=0,
            output_summary="ok",
        )
        _ = service.mark_finding(finding_id, FindingStatus.RESOLVED, note="fixed")
    _ = service.mark_finding(
        by_rule[_DISMISSED_RULE].id,
        FindingStatus.WONTFIX,
        note="acknowledged",
    )
    return repo
