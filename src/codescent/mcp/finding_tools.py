from __future__ import annotations

from typing import TYPE_CHECKING

from codescent.mcp.finding_payloads import (
    BacklogToolPayload,
    FindingDetailToolPayload,
    MarkFindingToolPayload,
    NextImprovementToolPayload,
    ProgressToolPayload,
    RecordVerificationToolPayload,
    RegressionsToolPayload,
    RescanToolPayload,
    ScanHealthToolPayload,
    ScoreExplanationToolPayload,
    SmellReportToolPayload,
    detail_payload,
    finding_payload,
    scan_payload,
    score_explanation_payload,
    status_from_string,
)
from codescent.services.code_health import CodeHealthService
from codescent.services.findings import FindingsService
from codescent.services.reports import ReportService

if TYPE_CHECKING:
    from fastmcp import FastMCP


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
            "Use CodeScent to record a caller-supplied verification result "
            "for a finding. CodeScent stores the command, exit code, and a "
            "bounded output summary; it never executes commands."
        ),
    )(record_verification)
    _ = mcp.tool(
        description=(
            "Use CodeScent to rescan and compare finding lifecycle state. "
            "Writes only .codescent state."
        ),
    )(rescan)


def scan_code_health(repo: str = ".") -> ScanHealthToolPayload:
    return scan_payload(CodeHealthService(repo).scan())


def get_smell_report(repo: str = ".") -> SmellReportToolPayload:
    report = FindingsService(repo).get_smell_report()
    return {
        "ok": True,
        "open_count": report.open_count,
        "status_counts": report.status_counts,
        "findings": tuple(finding_payload(finding) for finding in report.findings),
    }


def get_finding(finding_id: str, repo: str = ".") -> FindingDetailToolPayload:
    return detail_payload(ReportService(repo).get_finding(finding_id))


def explain_score(
    finding_id: str,
    repo: str = ".",
) -> ScoreExplanationToolPayload:
    return score_explanation_payload(ReportService(repo).explain_score(finding_id))


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
    result = FindingsService(repo).mark_finding(
        finding_id,
        status_from_string(status),
        note=note,
    )
    return {
        "ok": True,
        "finding_id": result.id,
        "status": result.applied_status.value,
        "requested_status": result.requested_status.value,
        "gated": result.gated,
        "message": result.message,
    }


def record_verification(
    finding_id: str,
    command: str,
    exit_code: int,
    output_summary: str,
    repo: str = ".",
) -> RecordVerificationToolPayload:
    verification = FindingsService(repo).record_verification(
        finding_id,
        command=command,
        exit_code=exit_code,
        output_summary=output_summary,
    )
    return {
        "ok": True,
        "finding_id": verification.finding_id,
        "verification_id": verification.id,
        "command": verification.command,
        "exit_code": verification.exit_code,
        "output_summary": verification.output_summary,
        "output_truncated": verification.output_truncated,
    }


def rescan(repo: str = ".") -> RescanToolPayload:
    result = FindingsService(repo).rescan()
    payload = scan_payload(result.scan)
    return {
        **payload,
        "regressed_finding_ids": result.regressed_finding_ids,
    }
