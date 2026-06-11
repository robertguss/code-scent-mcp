from __future__ import annotations

from typing import TYPE_CHECKING, TypedDict

from codescent.core.models import FindingStatus
from codescent.services.code_health import CodeHealthScanResult, CodeHealthService
from codescent.services.findings import FindingsService
from codescent.services.reports import (
    FindingDetail,
    JsonObject,
    ReportService,
    ScoreExplanation,
)

if TYPE_CHECKING:
    from fastmcp import FastMCP

    from codescent.storage.repositories import FindingRow


class ScanHealthToolPayload(TypedDict):
    ok: bool
    status: str
    scan_id: str
    findings_created: int
    finding_ids: tuple[str, ...]
    rule_ids: tuple[str, ...]


class SmellReportToolPayload(TypedDict):
    ok: bool
    open_count: int
    status_counts: dict[str, int]
    findings: tuple[dict[str, str | float], ...]


class FindingDetailToolPayload(TypedDict):
    ok: bool
    finding_id: str
    rule_id: str
    file_path: str
    severity: str
    confidence: float
    status: str
    title: str
    message: str
    evidence: JsonObject
    suggested_action: str
    status_history: tuple[JsonObject, ...]
    score_inputs: JsonObject


class ScoreExplanationToolPayload(TypedDict):
    ok: bool
    finding_id: str
    score_inputs: JsonObject
    reasons: tuple[str, ...]
    next_steps: tuple[str, ...]
    subjective: bool


class NextImprovementToolPayload(TypedDict):
    ok: bool
    finding_id: str | None
    rule_id: str | None
    file_path: str | None
    suggested_action: str | None


class BacklogToolPayload(TypedDict):
    ok: bool
    open_count: int
    status_counts: dict[str, int]
    finding_ids: tuple[str, ...]


class ProgressToolPayload(TypedDict):
    ok: bool
    total_findings: int
    open_count: int
    resolved_count: int
    regressed_count: int
    status_counts: dict[str, int]


class RegressionsToolPayload(TypedDict):
    ok: bool
    count: int
    finding_ids: tuple[str, ...]


class MarkFindingToolPayload(TypedDict):
    ok: bool
    finding_id: str
    status: str


class RescanToolPayload(TypedDict):
    ok: bool
    status: str
    scan_id: str
    findings_created: int
    finding_ids: tuple[str, ...]
    rule_ids: tuple[str, ...]
    regressed_finding_ids: tuple[str, ...]


def register_finding_tools(mcp: FastMCP) -> None:
    _ = mcp.tool(
        description=(
            "Use CodeScent to run deterministic Python code-health scanning. "
            "Writes only local .codescent state and never edits source files."
        ),
    )(scan_code_health)
    _ = mcp.tool(
        description=(
            "Use CodeScent to read a structured smell report from local state. "
            "Read-only for source files."
        ),
    )(get_smell_report)
    _ = mcp.tool(
        description=(
            "Use CodeScent to read one finding with structured evidence, "
            "lifecycle history, and deterministic score inputs."
        ),
    )(get_finding)
    _ = mcp.tool(
        description=(
            "Use CodeScent to explain deterministic score inputs and ranking "
            "reasons for a finding. Does not use subjective LLM judgment."
        ),
    )(explain_score)
    _ = mcp.tool(
        description=(
            "Use CodeScent to choose the next deterministic improvement from "
            "open or regressed findings."
        ),
    )(get_next_improvement)
    _ = mcp.tool(
        description="Use CodeScent to read the deterministic finding backlog.",
    )(get_backlog)
    _ = mcp.tool(
        description="Use CodeScent to read deterministic finding progress counts.",
    )(get_progress)
    _ = mcp.tool(
        description="Use CodeScent to read regressed finding IDs after rescans.",
    )(get_regressions)
    _ = mcp.tool(
        description=(
            "Use CodeScent to update finding lifecycle status in .codescent. "
            "This never edits analyzed source files."
        ),
    )(mark_finding)
    _ = mcp.tool(
        description=(
            "Use CodeScent to rescan and compare finding lifecycle state. "
            "Writes only .codescent state."
        ),
    )(rescan)


def scan_code_health(repo: str = ".") -> ScanHealthToolPayload:
    return _scan_payload(CodeHealthService(repo).scan())


def get_smell_report(repo: str = ".") -> SmellReportToolPayload:
    report = FindingsService(repo).get_smell_report()
    return {
        "ok": True,
        "open_count": report.open_count,
        "status_counts": report.status_counts,
        "findings": tuple(_finding_payload(finding) for finding in report.findings),
    }


def get_finding(finding_id: str, repo: str = ".") -> FindingDetailToolPayload:
    return _detail_payload(ReportService(repo).get_finding(finding_id))


def explain_score(
    finding_id: str,
    repo: str = ".",
) -> ScoreExplanationToolPayload:
    return _score_explanation_payload(ReportService(repo).explain_score(finding_id))


def get_next_improvement(repo: str = ".") -> NextImprovementToolPayload:
    finding = FindingsService(repo).get_next_improvement()
    if finding is None:
        return {
            "ok": True,
            "finding_id": None,
            "rule_id": None,
            "file_path": None,
            "suggested_action": None,
        }
    return {
        "ok": True,
        "finding_id": finding.id,
        "rule_id": finding.rule_id,
        "file_path": finding.file_path,
        "suggested_action": finding.suggested_action,
    }


def get_backlog(repo: str = ".") -> BacklogToolPayload:
    backlog = FindingsService(repo).get_backlog()
    return {
        "ok": True,
        "open_count": backlog.open_count,
        "status_counts": backlog.status_counts,
        "finding_ids": backlog.finding_ids,
    }


def get_progress(repo: str = ".") -> ProgressToolPayload:
    progress = FindingsService(repo).get_progress()
    return {
        "ok": True,
        "total_findings": progress.total_findings,
        "open_count": progress.open_count,
        "resolved_count": progress.resolved_count,
        "regressed_count": progress.regressed_count,
        "status_counts": progress.status_counts,
    }


def get_regressions(repo: str = ".") -> RegressionsToolPayload:
    regressions = FindingsService(repo).get_regressions()
    return {
        "ok": True,
        "count": regressions.count,
        "finding_ids": regressions.finding_ids,
    }


def mark_finding(
    finding_id: str,
    status: str,
    repo: str = ".",
    note: str = "",
) -> MarkFindingToolPayload:
    finding = FindingsService(repo).mark_finding(
        finding_id,
        FindingStatus(status),
        note=note,
    )
    return {"ok": True, "finding_id": finding.id, "status": finding.status.value}


def rescan(repo: str = ".") -> RescanToolPayload:
    result = FindingsService(repo).rescan()
    payload = _scan_payload(result.scan)
    return {
        **payload,
        "regressed_finding_ids": result.regressed_finding_ids,
    }


def _scan_payload(scan: CodeHealthScanResult) -> ScanHealthToolPayload:
    return {
        "ok": True,
        "status": "complete",
        "scan_id": scan.scan_id,
        "findings_created": scan.findings_created,
        "finding_ids": scan.finding_ids,
        "rule_ids": scan.rule_ids,
    }


def _finding_payload(finding: FindingRow) -> dict[str, str | float]:
    return {
        "finding_id": finding.id,
        "rule_id": finding.rule_id,
        "file_path": finding.file_path,
        "severity": finding.severity,
        "confidence": finding.confidence,
        "status": finding.status.value,
        "suggested_action": finding.suggested_action,
    }


def _detail_payload(detail: FindingDetail) -> FindingDetailToolPayload:
    return {
        "ok": True,
        "finding_id": detail.finding_id,
        "rule_id": detail.rule_id,
        "file_path": detail.file_path,
        "severity": detail.severity,
        "confidence": detail.confidence,
        "status": detail.status,
        "title": detail.title,
        "message": detail.message,
        "evidence": detail.evidence,
        "suggested_action": detail.suggested_action,
        "status_history": detail.status_history,
        "score_inputs": detail.score_inputs,
    }


def _score_explanation_payload(
    explanation: ScoreExplanation,
) -> ScoreExplanationToolPayload:
    return {
        "ok": True,
        "finding_id": explanation.finding_id,
        "score_inputs": explanation.score_inputs,
        "reasons": explanation.reasons,
        "next_steps": explanation.next_steps,
        "subjective": explanation.subjective,
    }
