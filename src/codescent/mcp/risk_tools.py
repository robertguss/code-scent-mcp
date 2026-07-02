from __future__ import annotations

from typing import TYPE_CHECKING, TypedDict, cast

from codescent.mcp.finding_payloads import ok_envelope
from codescent.services.risk import (
    ChangedFileHealth,
    DiffRiskReport,
    RiskFinding,
    RiskService,
)

if TYPE_CHECKING:
    from fastmcp import FastMCP


class RiskFindingToolPayload(TypedDict):
    finding_id: str
    rule_id: str
    file_path: str
    severity: str
    confidence: float
    status: str


class ChangedFileHealthToolPayload(TypedDict):
    ok: bool
    file_ok: bool
    path: str
    risk_score: float
    risk_level: str
    finding_ids: tuple[str, ...]
    findings: tuple[RiskFindingToolPayload, ...]
    suggested_tests: tuple[str, ...]
    recommended_commands: tuple[str, ...]
    risk_notes: tuple[str, ...]
    next_tools: tuple[str, ...]


class DiffRiskToolPayload(TypedDict):
    ok: bool
    changed_files: tuple[str, ...]
    risk_score: float
    risk_level: str
    findings: tuple[RiskFindingToolPayload, ...]
    suggested_tests: tuple[str, ...]
    recommended_commands: tuple[str, ...]
    file_health: tuple[ChangedFileHealthToolPayload, ...]
    next_tools: tuple[str, ...]


def register_risk_tools(mcp: FastMCP) -> None:
    _ = mcp.tool(
        description=(
            "Review local changed-file risk: findings, impact, and recommended "
            "verification. No GitHub or network. e.g. review_diff_risk(repo='.')."
        ),
    )(review_diff_risk)
    _ = mcp.tool(
        description=(
            "Inspect one locally changed file: findings, risk notes, likely "
            "tests, and recommended commands. Pass a repo-relative path. e.g. "
            "get_changed_file_health(path='src/app/auth.py')."
        ),
    )(get_changed_file_health)


def review_diff_risk(repo: str = ".") -> DiffRiskToolPayload:
    return _diff_risk_payload(RiskService(repo).review_diff_risk())


def get_changed_file_health(
    path: str,
    repo: str = ".",
) -> ChangedFileHealthToolPayload:
    return _changed_file_health_payload(
        RiskService(repo).get_changed_file_health(path),
    )


def _diff_risk_payload(report: DiffRiskReport) -> DiffRiskToolPayload:
    envelope = ok_envelope(
        next_tools=("get_changed_file_health", "select_tests", "scan_code_health"),
        changed_files=report.changed_files,
        risk_score=report.risk_score,
        risk_level=report.risk_level,
        findings=tuple(_finding_payload(finding) for finding in report.findings),
        suggested_tests=report.suggested_tests,
        recommended_commands=report.recommended_commands,
        file_health=tuple(
            _changed_file_health_payload(health) for health in report.file_health
        ),
    )
    return cast("DiffRiskToolPayload", cast("object", envelope))


def _changed_file_health_payload(
    health: ChangedFileHealth,
) -> ChangedFileHealthToolPayload:
    # ok is transport success (the call ran); the domain verdict (whether the
    # file had resolvable health data) is its own file_ok field (U4).
    envelope = ok_envelope(
        next_tools=("review_diff_risk", "select_tests"),
        file_ok=health.ok,
        path=health.path,
        risk_score=health.risk_score,
        risk_level=health.risk_level,
        finding_ids=tuple(finding.finding_id for finding in health.findings),
        findings=tuple(_finding_payload(finding) for finding in health.findings),
        suggested_tests=health.suggested_tests,
        recommended_commands=health.recommended_commands,
        risk_notes=health.risk_notes,
    )
    return cast("ChangedFileHealthToolPayload", cast("object", envelope))


def _finding_payload(finding: RiskFinding) -> RiskFindingToolPayload:
    return {
        "finding_id": finding.finding_id,
        "rule_id": finding.rule_id,
        "file_path": finding.file_path,
        "severity": finding.severity,
        "confidence": finding.confidence,
        "status": finding.status,
    }
