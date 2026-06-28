from __future__ import annotations

from typing import TYPE_CHECKING

from typer.testing import CliRunner

from codescent.cli.main import app
from codescent.core.models import FindingStatus
from codescent.dashboard.server import start_dashboard_server
from codescent.services.code_health import CodeHealthService
from codescent.services.findings import FindingsService
from tests.integration.dashboard_http import get_json
from tests.precision_payloads import PrecisionPayload

if TYPE_CHECKING:
    from pathlib import Path

RUNNER = CliRunner()

_ACCEPTED_RULES = (
    "python.changed_source_without_related_test",
    "python.dead_code_candidate",
)
_DISMISSED_RULE = "python.duplicate_literal"


def _check(label: str, *, expected: object, found: object) -> None:
    print(f"[precision-e2e] {label}: expected={expected!r} found={found!r}")  # noqa: T201
    assert found == expected, f"{label}: expected {expected!r}, found {found!r}"


def test_precision_e2e_cli_and_dashboard_agree(tmp_path: Path) -> None:
    repo = _seed_accept_dismiss(tmp_path)
    print(f"[precision-e2e] seeded repo at {repo}")  # noqa: T201

    cli_result = RUNNER.invoke(
        app,
        ["precision", "--repo", str(repo), "--format", "json"],
    )
    assert cli_result.exit_code == 0, cli_result.output
    cli = PrecisionPayload.model_validate_json(cli_result.output)

    server = start_dashboard_server(repo, port=0)
    try:
        print(f"[precision-e2e] dashboard bound at {server.base_url}")  # noqa: T201
        assert server.host == "127.0.0.1"
        api = PrecisionPayload.model_validate(
            get_json(f"{server.base_url}/api/precision").payload,
        )
    finally:
        server.shutdown()

    # Overall acceptance precision: 2 accepted / 1 dismissed.
    _check("cli accepted", expected=2, found=cli.accepted)
    _check("cli dismissed", expected=1, found=cli.dismissed)
    _check("cli acceptance_precision", expected=0.667, found=cli.acceptance_precision)

    # The dashboard API must agree with the CLI on every metric.
    _check("api==cli accepted", expected=cli.accepted, found=api.accepted)
    _check("api==cli dismissed", expected=cli.dismissed, found=api.dismissed)
    _check("api==cli sample_size", expected=cli.sample_size, found=api.sample_size)
    _check(
        "api==cli acceptance_precision",
        expected=cli.acceptance_precision,
        found=api.acceptance_precision,
    )

    _check(
        f"per-rule precision {_DISMISSED_RULE}",
        expected=0.0,
        found=cli.rule(_DISMISSED_RULE).acceptance_precision,
    )
    for rule_id in _ACCEPTED_RULES:
        _check(
            f"per-rule precision {rule_id}",
            expected=1.0,
            found=cli.rule(rule_id).acceptance_precision,
        )
        _check(
            f"api==cli per-rule {rule_id}",
            expected=cli.rule(rule_id).acceptance_precision,
            found=api.rule(rule_id).acceptance_precision,
        )

    _check("trend final accepted", expected=2, found=cli.trend[-1].accepted)
    _check("trend final dismissed", expected=1, found=cli.trend[-1].dismissed)
    print("[precision-e2e] all assertions passed")  # noqa: T201


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
