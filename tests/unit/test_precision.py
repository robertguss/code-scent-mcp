from __future__ import annotations

import json

from codescent.core.models import FindingStatus
from codescent.services.precision import build_precision_report
from codescent.storage.repositories import FindingEventRow, FindingRow


def _event(status: FindingStatus, created_at: str) -> FindingEventRow:
    return FindingEventRow(
        event_type="status_changed",
        created_at=created_at,
        details_json=json.dumps({"status": status.value, "note": ""}),
    )


def _finding(
    rule_id: str,
    status: FindingStatus,
    *,
    finding_id: str,
    events: tuple[FindingEventRow, ...] = (),
) -> FindingRow:
    return FindingRow(
        id=finding_id,
        stable_key=f"{rule_id}:{finding_id}",
        rule_id=rule_id,
        file_path="src/pkg/a.py",
        severity="warning",
        confidence=0.9,
        status=status,
        title="t",
        message="m",
        evidence_json="{}",
        suggested_action="a",
        events=events,
    )


def test_per_rule_acceptance_precision_from_status_and_suppression() -> None:
    findings = (
        _finding("rule.a", FindingStatus.RESOLVED, finding_id="a1"),
        _finding("rule.a", FindingStatus.RESOLVED, finding_id="a2"),
        _finding("rule.a", FindingStatus.RESOLVED, finding_id="a3"),
        _finding("rule.a", FindingStatus.WONTFIX, finding_id="a4"),
        _finding("rule.b", FindingStatus.IGNORED, finding_id="b1"),
        _finding("rule.b", FindingStatus.IGNORED, finding_id="b2"),
        # Open finding has no verdict yet: its rule is excluded from the report.
        _finding("rule.c", FindingStatus.OPEN, finding_id="c1"),
    )

    report = build_precision_report(findings, {"rule.b": 1, "rule.d": 2})
    by_rule = {rule.rule_id: rule for rule in report.rules}

    assert set(by_rule) == {"rule.a", "rule.b", "rule.d"}
    assert by_rule["rule.a"].accepted == 3
    assert by_rule["rule.a"].dismissed == 1
    assert by_rule["rule.a"].acceptance_precision == 0.75
    assert by_rule["rule.b"].acceptance_precision == 0.0
    assert by_rule["rule.b"].suppression_candidates == 1
    # rule.d has no findings, only a suppression candidate.
    assert by_rule["rule.d"].sample_size == 0
    assert by_rule["rule.d"].acceptance_precision is None
    assert by_rule["rule.d"].suppression_candidates == 2
    # Overall: 3 accepted / 3 dismissed.
    assert report.accepted == 3
    assert report.dismissed == 3
    assert report.acceptance_precision == 0.5


def test_no_verdicts_yields_none_precision_and_no_rules() -> None:
    findings = (_finding("rule.a", FindingStatus.OPEN, finding_id="a1"),)

    report = build_precision_report(findings)

    assert report.rules == ()
    assert report.acceptance_precision is None
    assert report.trend == ()


def test_health_trend_points_are_ordered_and_cumulative() -> None:
    findings = (
        _finding(
            "rule.a",
            FindingStatus.RESOLVED,
            finding_id="a1",
            events=(_event(FindingStatus.RESOLVED, "2026-01-01T10:00:00+00:00"),),
        ),
        _finding(
            "rule.a",
            FindingStatus.WONTFIX,
            finding_id="a2",
            events=(_event(FindingStatus.WONTFIX, "2026-01-01T12:00:00+00:00"),),
        ),
        _finding(
            "rule.b",
            FindingStatus.RESOLVED,
            finding_id="b1",
            events=(_event(FindingStatus.RESOLVED, "2026-01-02T09:00:00+00:00"),),
        ),
    )

    trend = build_precision_report(findings).trend

    assert [point.date for point in trend] == ["2026-01-01", "2026-01-02"]
    assert (trend[0].accepted, trend[0].dismissed) == (1, 1)
    assert trend[0].acceptance_precision == 0.5
    assert (trend[1].accepted, trend[1].dismissed) == (2, 1)
    assert trend[1].acceptance_precision == 0.667


def test_trend_reopen_corrects_verdict_without_double_counting() -> None:
    findings = (
        _finding(
            "rule.a",
            FindingStatus.OPEN,
            finding_id="a1",
            events=(
                _event(FindingStatus.RESOLVED, "2026-01-01T10:00:00+00:00"),
                _event(FindingStatus.OPEN, "2026-01-02T10:00:00+00:00"),
            ),
        ),
    )

    report = build_precision_report(findings)

    assert [point.date for point in report.trend] == ["2026-01-01", "2026-01-02"]
    assert report.trend[0].acceptance_precision == 1.0
    assert (report.trend[1].accepted, report.trend[1].dismissed) == (0, 0)
    assert report.trend[1].acceptance_precision is None
    # Current status is OPEN, so no rule carries a verdict.
    assert report.rules == ()
