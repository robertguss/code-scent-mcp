from __future__ import annotations

from typing import TYPE_CHECKING

from codescent.core.models import FindingStatus
from codescent.dashboard.server import start_dashboard_server
from codescent.services.code_health import CodeHealthService
from codescent.services.findings import FindingsService
from tests.integration.dashboard_http import get_json
from tests.precision_payloads import PrecisionPayload

if TYPE_CHECKING:
    from pathlib import Path

_ACCEPTED_RULES = (
    "python.changed_source_without_related_test",
    "python.dead_code_candidate",
)
_DISMISSED_RULE = "python.duplicate_literal"


def test_precision_api_returns_per_rule_precision_and_trend(tmp_path: Path) -> None:
    repo = _seed_accept_dismiss(tmp_path)

    server = start_dashboard_server(repo, port=0)
    try:
        precision = get_json(f"{server.base_url}/api/precision")
        exports = get_json(f"{server.base_url}/api/exports")
    finally:
        server.shutdown()

    assert precision.status == 200
    assert precision.content_type.startswith("application/json")
    assert precision.payload["read_only"] is True

    payload = PrecisionPayload.model_validate(precision.payload)
    assert payload.accepted == 2
    assert payload.dismissed == 1
    assert payload.acceptance_precision == 0.667
    assert payload.rule(_DISMISSED_RULE).acceptance_precision == 0.0
    for rule_id in _ACCEPTED_RULES:
        assert payload.rule(rule_id).acceptance_precision == 1.0
    assert payload.trend
    assert payload.trend[-1].accepted == 2
    assert payload.trend[-1].dismissed == 1

    routes = exports.payload["routes"]
    assert isinstance(routes, list)
    assert "/api/precision" in routes


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
