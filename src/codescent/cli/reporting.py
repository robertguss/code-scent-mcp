from __future__ import annotations

import json
from typing import TYPE_CHECKING, Annotated, NotRequired, TypedDict

import typer

from codescent.services.ci import (
    BaselineUpdateResult,
    ChangedFileSummary,
    CiReport,
    CiService,
)
from codescent.services.findings import FindingsService
from codescent.services.reports import ReportService
from codescent.services.subjective_review import (
    SubjectiveReviewService,
    subjective_findings_payload,
)

if TYPE_CHECKING:
    from codescent.storage.repositories import FindingRow

INVALID_FORMAT_MESSAGE = "format must be json or markdown"


class CliReportPayload(TypedDict):
    open_count: int
    status_counts: dict[str, int]
    findings: list[dict[str, str | float]]
    subjective_findings: list[dict[str, str | float | bool]]
    subjective_provider: str | None
    privacy_notice: str | None


class ChangedFileHealthPayload(TypedDict):
    path: str
    risk_level: str
    risk_score: float
    finding_count: int
    baseline_count: NotRequired[int | None]
    regressed: NotRequired[bool]


class NewFindingPayload(TypedDict):
    stable_key: str
    rule_id: str
    file_path: str
    severity: str


class CiReportPayload(TypedDict):
    ok: bool
    risk_level: str
    finding_count: int
    changed_file_health: list[ChangedFileHealthPayload]
    suggested_tests: list[str]
    recommended_commands: list[str]
    ratchet_enabled: NotRequired[bool]
    ratchet_regressions: NotRequired[list[ChangedFileHealthPayload]]
    baseline_exists: NotRequired[bool]
    baseline_stale: NotRequired[bool]
    base_ref: NotRequired[str]
    net_health_delta: NotRequired[int]
    new_finding_count: NotRequired[int]
    resolved_count: NotRequired[int]
    new_findings: NotRequired[list[NewFindingPayload]]


class CiBaselineUpdatePayload(TypedDict):
    ok: bool
    files_recorded: int
    finding_count: int


def register_reporting_commands(app: typer.Typer) -> None:
    _ = app.command()(report)
    _ = app.command()(export)
    _ = app.command()(findings)
    _ = app.command(name="next")(next_improvement)
    _ = app.command()(explain)
    _ = app.command()(ci)
    _ = app.command(name="review-diff")(review_diff)


def report(
    repo: Annotated[str, typer.Option("--repo", help="Repository root.")] = ".",
    format_name: Annotated[
        str,
        typer.Option("--format", help="Output format: json or markdown."),
    ] = "json",
    include_subjective: Annotated[
        bool,
        typer.Option("--include-subjective", help="Include opt-in subjective review."),
    ] = False,
    provider: Annotated[
        str,
        typer.Option("--provider", help="Subjective review provider."),
    ] = "fake",
) -> None:
    report_data = FindingsService(repo).get_smell_report()
    subjective = SubjectiveReviewService(repo).review(
        provider_name=provider,
        allow_subjective=include_subjective,
    )
    payload: CliReportPayload = {
        "open_count": report_data.open_count,
        "status_counts": report_data.status_counts,
        "findings": [_finding_row_payload(finding) for finding in report_data.findings],
        "subjective_findings": subjective_findings_payload(
            subjective.subjective_findings,
        ),
        "subjective_provider": subjective.provider,
        "privacy_notice": subjective.privacy_notice,
    }
    _emit_report_payload(payload, format_name)


def export(
    repo: Annotated[str, typer.Option("--repo", help="Repository root.")] = ".",
    format_name: Annotated[
        str,
        typer.Option("--format", help="Output format: json or markdown."),
    ] = "json",
) -> None:
    report_data = FindingsService(repo).get_smell_report()
    payload: CliReportPayload = {
        "open_count": report_data.open_count,
        "status_counts": report_data.status_counts,
        "findings": [_finding_row_payload(finding) for finding in report_data.findings],
        "subjective_findings": [],
        "subjective_provider": None,
        "privacy_notice": None,
    }
    _emit_report_payload(payload, format_name)


def findings(
    repo: Annotated[str, typer.Option("--repo", help="Repository root.")] = ".",
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Print JSON findings."),
    ] = False,
) -> None:
    rows = FindingsService(repo).get_smell_report().findings
    payload = {"findings": [_finding_row_payload(finding) for finding in rows]}
    if json_output:
        typer.echo(json.dumps(payload))
        return
    for finding in payload["findings"]:
        typer.echo(f"{finding['finding_id']} {finding['rule_id']}")


def next_improvement(
    repo: Annotated[str, typer.Option("--repo", help="Repository root.")] = ".",
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Print JSON next improvement."),
    ] = False,
) -> None:
    finding = FindingsService(repo).get_next_improvement()
    payload = None if finding is None else _finding_row_payload(finding)
    if json_output:
        typer.echo(json.dumps({"finding": payload}))
        return
    typer.echo("No findings" if payload is None else payload["finding_id"])


def explain(
    finding_id: str,
    repo: Annotated[str, typer.Option("--repo", help="Repository root.")] = ".",
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Print JSON score explanation."),
    ] = False,
) -> None:
    explanation = ReportService(repo).explain_score(finding_id)
    payload = {
        "finding_id": explanation.finding_id,
        "score_inputs": explanation.score_inputs,
        "reasons": list(explanation.reasons),
        "next_steps": list(explanation.next_steps),
        "subjective": explanation.subjective,
    }
    if json_output:
        typer.echo(json.dumps(payload))
        return
    typer.echo("\n".join(explanation.reasons))


def ci(  # noqa: PLR0913 - CLI command exposes distinct options.
    repo: Annotated[str, typer.Option("--repo", help="Repository root.")] = ".",
    format_name: Annotated[
        str,
        typer.Option("--format", help="Output format: json or markdown."),
    ] = "json",
    threshold: Annotated[
        str,
        typer.Option("--threshold", help="Fail at risk threshold: warn or high."),
    ] = "high",
    ratchet: Annotated[
        bool,
        typer.Option(
            "--ratchet/--no-ratchet",
            help="Fail only on new findings versus the accepted baseline.",
        ),
    ] = False,
    base: Annotated[
        str,
        typer.Option(
            "--base",
            help="Scope the ratchet to files changed since this git ref.",
        ),
    ] = "",
    update_baseline: Annotated[
        bool,
        typer.Option(
            "--update-baseline",
            help="Accept the current findings as the CI baseline.",
        ),
    ] = False,
) -> None:
    service = CiService(repo)
    if update_baseline:
        result = service.update_baseline()
        _emit_ci_baseline_update(result, format_name)
        return

    report_data = service.run(threshold=threshold, ratchet=ratchet, base_ref=base)
    _emit_ci_report(report_data, format_name)
    if not report_data.ok:
        raise typer.Exit(1)


def review_diff(
    repo: Annotated[str, typer.Option("--repo", help="Repository root.")] = ".",
    format_name: Annotated[
        str,
        typer.Option("--format", help="Output format: json or markdown."),
    ] = "json",
) -> None:
    report_data = CiService(repo).run(threshold="high")
    _emit_ci_report(report_data, format_name)


def _finding_row_payload(finding: FindingRow) -> dict[str, str | float]:
    return {
        "finding_id": finding.id,
        "rule_id": finding.rule_id,
        "file_path": finding.file_path,
        "severity": finding.severity,
        "confidence": finding.confidence,
        "status": finding.status.value,
        "suggested_action": finding.suggested_action,
    }


def _emit_report_payload(payload: CliReportPayload, format_name: str) -> None:
    if format_name == "json":
        typer.echo(json.dumps(payload))
        return
    if format_name == "markdown":
        typer.echo(_markdown_report(payload))
        return
    raise typer.BadParameter(INVALID_FORMAT_MESSAGE)


def _markdown_report(payload: CliReportPayload) -> str:
    lines = ["# CodeScent Report", ""]
    findings_payload = payload["findings"]
    lines.append(f"Findings: {len(findings_payload)}")
    lines.extend(
        f"- {finding['finding_id']}: {finding['rule_id']}"
        for finding in findings_payload
    )
    return "\n".join(lines)


def _emit_ci_report(report_data: CiReport, format_name: str) -> None:
    payload = _ci_payload(report_data)
    if format_name == "json":
        typer.echo(json.dumps(payload))
        return
    if format_name == "markdown":
        typer.echo(_ci_markdown(payload))
        return
    raise typer.BadParameter(INVALID_FORMAT_MESSAGE)


def _ci_payload(report_data: CiReport) -> CiReportPayload:
    payload: CiReportPayload = {
        "ok": report_data.ok,
        "risk_level": report_data.risk_level,
        "finding_count": report_data.finding_count,
        "changed_file_health": [
            _changed_file_health_payload(
                health,
                include_ratchet=report_data.ratchet_enabled,
            )
            for health in report_data.changed_file_health
        ],
        "suggested_tests": list(report_data.suggested_tests),
        "recommended_commands": list(report_data.recommended_commands),
    }
    if report_data.ratchet_enabled:
        payload["ratchet_enabled"] = True
        payload["ratchet_regressions"] = [
            _changed_file_health_payload(health, include_ratchet=True)
            for health in report_data.ratchet_regressions
        ]
        payload["baseline_exists"] = report_data.baseline_exists
        payload["baseline_stale"] = report_data.baseline_stale
        payload["base_ref"] = report_data.base_ref
        payload["net_health_delta"] = report_data.net_health_delta
        payload["new_finding_count"] = report_data.new_finding_count
        payload["resolved_count"] = report_data.resolved_count
        payload["new_findings"] = [
            {
                "stable_key": finding.stable_key,
                "rule_id": finding.rule_id,
                "file_path": finding.file_path,
                "severity": finding.severity,
            }
            for finding in report_data.new_findings
        ]
    return payload


def _changed_file_health_payload(
    health: ChangedFileSummary,
    *,
    include_ratchet: bool,
) -> ChangedFileHealthPayload:
    payload: ChangedFileHealthPayload = {
        "path": health.path,
        "risk_level": health.risk_level,
        "risk_score": health.risk_score,
        "finding_count": health.finding_count,
    }
    if include_ratchet:
        payload["baseline_count"] = health.baseline_count
        payload["regressed"] = health.regressed
    return payload


def _emit_ci_baseline_update(
    result: BaselineUpdateResult,
    format_name: str,
) -> None:
    payload: CiBaselineUpdatePayload = {
        "ok": True,
        "files_recorded": result.files_recorded,
        "finding_count": result.finding_count,
    }
    if format_name == "json":
        typer.echo(json.dumps(payload))
        return
    if format_name == "markdown":
        typer.echo(_ci_baseline_markdown(payload))
        return
    raise typer.BadParameter(INVALID_FORMAT_MESSAGE)


def _ci_baseline_markdown(payload: CiBaselineUpdatePayload) -> str:
    return "\n".join(
        (
            "# CodeScent CI Baseline",
            "",
            f"Files recorded: {payload['files_recorded']}",
            f"Findings: {payload['finding_count']}",
        ),
    )


def _ci_markdown(payload: CiReportPayload) -> str:
    lines = [
        "# CodeScent Diff Review",
        "",
        f"Risk: {payload['risk_level']}",
        f"Findings: {payload['finding_count']}",
        "",
        "## Changed-file health",
    ]
    lines.extend(
        f"- {item['path']}: {item['risk_level']}"
        for item in payload["changed_file_health"]
    )
    lines.extend(("", "## Suggested tests"))
    lines.extend(f"- {test}" for test in payload["suggested_tests"])
    return "\n".join(lines)
