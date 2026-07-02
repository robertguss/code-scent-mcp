from __future__ import annotations

from typing import TYPE_CHECKING, TypedDict, cast

from codescent.core.models import FindingStatus
from codescent.mcp.finding_payloads import (
    BacklogToolPayload,
    CalibrationToolPayload,
    FindingDetailToolPayload,
    ImprovementPlanToolPayload,
    MarkFindingToolPayload,
    NextImprovementToolPayload,
    ProgressToolPayload,
    RecordVerificationToolPayload,
    RegressionsToolPayload,
    RescanToolPayload,
    ScanHealthToolPayload,
    ScoreExplanationToolPayload,
    SmellReportToolPayload,
    aggregate_counts,
    bounded_finding_list,
    build_scan_envelope,
    calibration_payload,
    detail_payload,
    finding_payload,
    improvement_plan_payload,
    score_explanation_payload,
    severity_rank,
    status_from_string,
)
from codescent.services.calibration import CalibrationService
from codescent.services.code_health import CodeHealthService
from codescent.services.explain import ExplainService, FindingExplanation
from codescent.services.findings import (
    DEFAULT_MIN_SEVERITY,
    FindingsService,
    validate_min_severity,
)
from codescent.services.improvement_plan import ImprovementPlanService
from codescent.services.reports import ReportService

_BACKLOG_STATUSES = frozenset(
    {
        FindingStatus.OPEN,
        FindingStatus.IN_PROGRESS,
        FindingStatus.NEEDS_REVIEW,
        FindingStatus.REGRESSED,
    },
)


class ExplainFindingToolPayload(TypedDict):
    ok: bool
    finding_id: str
    rule_id: str
    file_path: str
    severity: str
    confidence_tier: str
    provenance: dict[str, str | int | float | bool | None]
    why: str
    evidence: dict[str, str | int | float | bool | None]
    fix: str
    snippet: dict[str, str | int]
    snippet_truncated: bool
    next_tools: tuple[str, ...]


if TYPE_CHECKING:
    from collections.abc import Iterable

    from fastmcp import FastMCP

    from codescent.mcp.finding_payloads import FindingItem
    from codescent.services.findings import SmellReport
    from codescent.storage.repositories import FindingRow


def _status_counts(rows: Iterable[FindingRow]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for finding in rows:
        counts[finding.status.value] = counts.get(finding.status.value, 0) + 1
    return counts


def _headline_then_tail(rows: Iterable[FindingRow]) -> tuple[FindingItem, ...]:
    ordered = sorted(
        rows,
        key=lambda finding: (severity_rank(finding.severity), finding.id),
    )
    return tuple(finding_payload(finding) for finding in ordered)


def _gate_extra(report: SmellReport) -> dict[str, object]:
    """Surface the default-gate state so an agent can opt into the full set."""
    deferred = len(report.deferred)
    notes: list[str] = []
    if deferred > 0:
        notes.append(
            (
                f"{deferred} lower-severity info/heuristic finding(s) hidden by "
                "the default gate; call with include_all=True or "
                "min_severity='info' to include them."
            ),
        )
    if report.degraded:
        notes.append(
            (
                "No actionable (warning+ or verified-tier) findings; showing the "
                "full set by lowest severity."
            ),
        )
    return {
        "min_severity": report.min_severity,
        "include_all": report.include_all,
        "deferred_count": deferred,
        "gate_degraded": report.degraded,
        "gate_notes": tuple(notes),
    }


def register_finding_tools(mcp: FastMCP) -> None:
    _ = mcp.tool(
        description=(
            "Deterministic first-run, full Python code-health scan; writes only "
            "local .codescent state and never edits source. Use scan_code_health "
            "for the initial scan, then rescan afterwards to compare lifecycle "
            "state against the baseline. e.g. scan_code_health(repo='.')."
        ),
    )(scan_code_health)
    _ = mcp.tool(
        description=(
            "Structured smell report read from local .codescent state. Leads with "
            "the actionable set (warning+ severity or verified-tier findings); the "
            "info/heuristic mass is a counted, opt-in tail -- pass include_all=True "
            "or min_severity='info' for the full set. Bounded inline items with a "
            "ctx_ result id when omitted; total finding_count is unchanged. e.g. "
            "get_smell_report(repo='.'). Read-only for source."
        ),
    )(get_smell_report)
    _ = mcp.tool(
        description=(
            "One finding in full: structured evidence, lifecycle history, and "
            "deterministic score inputs. Pass a finding_id from "
            "get_next_improvement or get_backlog. e.g. "
            "get_finding(finding_id='python.large_file:cf58...'). Read-only for "
            "source."
        ),
    )(get_finding)
    _ = mcp.tool(
        description=(
            "Deterministic score inputs and ranking reasons for a finding, no "
            "subjective LLM judgment. Pass a finding_id from get_next_improvement "
            "or get_backlog. e.g. "
            "explain_score(finding_id='python.long_function:ab12...')."
        ),
    )(explain_score)
    _ = mcp.tool(
        description=(
            "One fix-ready explanation of a finding: why it matters (message + "
            "evidence), the suggested fix, and a bounded source snippet (never "
            "an unbounded dump). Pass a finding_id from get_next_improvement or "
            "get_backlog. e.g. "
            "explain_finding(finding_id='python.dead_code_candidate:9f0a...')."
        ),
    )(explain_finding)
    _ = mcp.tool(
        description=(
            "Pick the next deterministic improvement from open or regressed "
            "findings; returns a finding_id that feeds get_finding, "
            "explain_finding, plan_refactor, and mark_finding. e.g. "
            "get_next_improvement(repo='.')."
        ),
    )(get_next_improvement)
    _ = mcp.tool(
        description=(
            "Deterministic finding backlog (open, in-progress, needs-review, "
            "regressed) ranked by severity. Leads with the actionable set by "
            "default; pass include_all=True or min_severity='info' for the full "
            "backlog. Bounded inline items with a ctx_ result id when items are "
            "omitted. Source of finding_ids for get_finding, plan_refactor, and "
            "mark_finding. e.g. get_backlog(repo='.')."
        ),
    )(get_backlog)
    _ = mcp.tool(
        description=(
            "Turn the finding backlog into a deterministic, ROI-ordered plan: "
            "findings clustered by theme with effort and health-gain estimates. "
            "Bounded output. e.g. get_improvement_plan(repo='.')."
        ),
    )(get_improvement_plan)
    _ = mcp.tool(
        description=(
            "Adaptive per-rule confidence calibration derived from this repo's "
            "own resolve/wontfix verdicts, plus learned suppression candidates. "
            "Deterministic, read-only. e.g. get_calibration(repo='.')."
        ),
    )(get_calibration)
    _ = mcp.tool(
        description=(
            "Deterministic finding progress counts by lifecycle status. e.g. "
            "get_progress(repo='.')."
        ),
    )(get_progress)
    _ = mcp.tool(
        description=(
            "Regressed finding ids surfaced after a rescan, ranked by severity, "
            "bounded. e.g. get_regressions(repo='.')."
        ),
    )(get_regressions)
    _ = mcp.tool(
        description=(
            "Update a finding's lifecycle status in .codescent; never edits "
            "source. Pass a finding_id from get_next_improvement or get_backlog "
            "and a status of open, in_progress, resolved, deferred, wontfix, "
            "ignored, regressed, needs_review, or suppressed. e.g. "
            "mark_finding(finding_id='python.large_file:cf58...', "
            "status='resolved')."
        ),
    )(mark_finding)
    _ = mcp.tool(
        description=(
            "Record a caller-supplied verification result for a finding: stores "
            "the command, exit code, and a bounded output summary; never "
            "executes commands. Pass a finding_id from get_next_improvement or "
            "get_backlog. e.g. record_verification(finding_id='...', "
            "command='pytest', exit_code=0, output_summary='42 passed')."
        ),
    )(record_verification)
    _ = mcp.tool(
        description=(
            "Rescan and compare finding lifecycle state against the prior "
            "baseline; writes only .codescent state. Use rescan after an initial "
            "scan_code_health to detect resolved and regressed findings. e.g. "
            "rescan(repo='.')."
        ),
    )(rescan)


def scan_code_health(repo: str = ".") -> ScanHealthToolPayload:
    scan = CodeHealthService(repo).scan()
    envelope = build_scan_envelope(
        scan,
        repo=repo,
        next_tools=("get_next_improvement", "get_smell_report"),
    )
    return cast("ScanHealthToolPayload", cast("object", envelope))


def get_smell_report(
    repo: str = ".",
    min_severity: str = DEFAULT_MIN_SEVERITY,
    include_all: bool = False,
) -> SmellReportToolPayload:
    min_severity = validate_min_severity(min_severity)
    report = FindingsService(repo).get_smell_report(
        min_severity=min_severity,
        include_all=include_all,
    )
    # Lead with the gated actionable headline, then the info/heuristic tail;
    # counts stay over the FULL set so finding totals are unchanged, and the
    # tail is still inline-or-offloaded via bounded_finding_list (never dropped).
    records = _headline_then_tail(report.headline) + _headline_then_tail(
        report.deferred,
    )
    severity_counts, rule_counts = aggregate_counts(
        (finding.severity, finding.rule_id) for finding in report.findings
    )
    aggregates: dict[str, object] = {
        "open_count": report.open_count,
        "total_count": len(report.findings),
        "status_counts": report.status_counts,
        "severity_counts": severity_counts,
        "rule_counts": rule_counts,
    }
    envelope = bounded_finding_list(
        kind="smell_report",
        repo=repo,
        tool_name="get_smell_report",
        records=records,
        aggregates=aggregates,
        next_tools=("get_next_improvement", "plan_refactor", "retrieve_result"),
        extra=_gate_extra(report),
    )
    return cast("SmellReportToolPayload", cast("object", envelope))


def get_finding(finding_id: str, repo: str = ".") -> FindingDetailToolPayload:
    return detail_payload(ReportService(repo).get_finding(finding_id))


def explain_score(
    finding_id: str,
    repo: str = ".",
) -> ScoreExplanationToolPayload:
    return score_explanation_payload(ReportService(repo).explain_score(finding_id))


def explain_finding(finding_id: str, repo: str = ".") -> ExplainFindingToolPayload:
    return _explain_payload(ExplainService(repo).explain_finding(finding_id))


def _explain_payload(explanation: FindingExplanation) -> ExplainFindingToolPayload:
    return {
        "ok": True,
        "finding_id": explanation.finding_id,
        "rule_id": explanation.rule_id,
        "file_path": explanation.file_path,
        "severity": explanation.severity,
        "confidence_tier": explanation.confidence_tier,
        "provenance": explanation.provenance,
        "why": explanation.why,
        "evidence": explanation.evidence,
        "fix": explanation.fix,
        "snippet": explanation.snippet,
        "snippet_truncated": explanation.snippet_truncated,
        "next_tools": explanation.next_tools,
    }


def get_next_improvement(
    repo: str = ".",
    min_severity: str = DEFAULT_MIN_SEVERITY,
    include_all: bool = False,
) -> NextImprovementToolPayload:
    min_severity = validate_min_severity(min_severity)
    finding = FindingsService(repo).get_next_improvement(
        min_severity=min_severity,
        include_all=include_all,
    )
    if finding is None:
        return {
            "ok": True,
            "finding_id": None,
            "rule_id": None,
            "file_path": None,
            "suggested_action": None,
            "next_tools": (),
        }
    return {
        "ok": True,
        "finding_id": finding.id,
        "rule_id": finding.rule_id,
        "file_path": finding.file_path,
        "suggested_action": finding.suggested_action,
        "next_tools": ("get_finding_context", "plan_refactor"),
    }


def get_backlog(
    repo: str = ".",
    min_severity: str = DEFAULT_MIN_SEVERITY,
    include_all: bool = False,
) -> BacklogToolPayload:
    min_severity = validate_min_severity(min_severity)
    report = FindingsService(repo).get_smell_report(
        min_severity=min_severity,
        include_all=include_all,
    )
    # Inherit the default gate at the shared choke: lead with the actionable
    # headline, then the info/heuristic tail; every backlog item is still
    # inline-or-offloaded (the gate reorders, it does not drop).
    headline_rows = [
        finding for finding in report.headline if finding.status in _BACKLOG_STATUSES
    ]
    deferred_rows = [
        finding for finding in report.deferred if finding.status in _BACKLOG_STATUSES
    ]
    rows = headline_rows + deferred_rows
    records = _headline_then_tail(headline_rows) + _headline_then_tail(deferred_rows)
    severity_counts, rule_counts = aggregate_counts(
        (finding.severity, finding.rule_id) for finding in rows
    )
    aggregates: dict[str, object] = {
        "open_count": len(rows),
        "total_count": len(rows),
        "status_counts": _status_counts(rows),
        "severity_counts": severity_counts,
        "rule_counts": rule_counts,
    }
    envelope = bounded_finding_list(
        kind="backlog",
        repo=repo,
        tool_name="get_backlog",
        records=records,
        aggregates=aggregates,
        next_tools=("get_next_improvement", "retrieve_result"),
        extra=_gate_extra(report),
    )
    return cast("BacklogToolPayload", cast("object", envelope))


def get_improvement_plan(
    repo: str = ".",
    min_severity: str = DEFAULT_MIN_SEVERITY,
    include_all: bool = False,
) -> ImprovementPlanToolPayload:
    min_severity = validate_min_severity(min_severity)
    plan = ImprovementPlanService(repo).get_improvement_plan(
        min_severity=min_severity,
        include_all=include_all,
    )
    envelope = improvement_plan_payload(plan, repo=repo)
    return cast("ImprovementPlanToolPayload", cast("object", envelope))


def get_calibration(repo: str = ".") -> CalibrationToolPayload:
    return calibration_payload(CalibrationService(repo).get_calibration())


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
    report = FindingsService(repo).get_smell_report()
    rows = sorted(
        (
            finding
            for finding in report.findings
            if finding.status is FindingStatus.REGRESSED
        ),
        key=lambda finding: (severity_rank(finding.severity), finding.id),
    )
    records = tuple(finding_payload(finding) for finding in rows)
    severity_counts, rule_counts = aggregate_counts(
        (finding.severity, finding.rule_id) for finding in rows
    )
    aggregates: dict[str, object] = {
        "count": len(rows),
        "total_count": len(rows),
        "status_counts": _status_counts(rows),
        "severity_counts": severity_counts,
        "rule_counts": rule_counts,
    }
    envelope = bounded_finding_list(
        kind="regressions",
        repo=repo,
        tool_name="get_regressions",
        records=records,
        aggregates=aggregates,
        next_tools=("get_next_improvement", "retrieve_result"),
    )
    return cast("RegressionsToolPayload", cast("object", envelope))


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
        "next_tools": ("rescan", "get_next_improvement"),
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
        "next_tools": ("mark_finding",),
    }


def rescan(repo: str = ".") -> RescanToolPayload:
    result = FindingsService(repo).rescan()
    envelope = build_scan_envelope(
        result.scan,
        repo=repo,
        next_tools=("get_next_improvement", "get_smell_report"),
        regressed_finding_ids=result.regressed_finding_ids,
    )
    return cast("RescanToolPayload", cast("object", envelope))
