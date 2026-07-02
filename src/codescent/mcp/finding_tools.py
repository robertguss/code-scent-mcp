from __future__ import annotations

from typing import TYPE_CHECKING, TypedDict, cast

from codescent.core.errors import CodeScentError, ErrorCode, ErrorSeverity
from codescent.core.models import FindingStatus
from codescent.mcp.finding_payloads import (
    CalibrationToolPayload,
    FindingDetailToolPayload,
    ImprovementPlanToolPayload,
    ListFindingsToolPayload,
    MarkFindingToolPayload,
    NextImprovementToolPayload,
    RecordVerificationToolPayload,
    RescanToolPayload,
    ScanHealthToolPayload,
    ScoreExplanationToolPayload,
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

# U11: explain_finding(view="context") reuses the planning-group context view.
# planning_tools imports only services, so this stays acyclic.
from codescent.mcp.planning_tools import (
    FindingContextToolPayload,
    get_finding_context,
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

# list_findings status routing (U10): None == no lifecycle filter (all findings).
_LIST_STATUS_FILTERS: dict[str, frozenset[FindingStatus] | None] = {
    "all": None,
    "open": frozenset({FindingStatus.OPEN}),
    "backlog": _BACKLOG_STATUSES,
    "regressed": frozenset({FindingStatus.REGRESSED}),
}
VALID_LIST_STATUSES: tuple[str, ...] = tuple(_LIST_STATUS_FILTERS)


def _validate_list_status(value: str) -> str:
    """Return ``value`` if it is a valid list_findings status, else recover.

    Mirrors validate_min_severity: an unknown status yields a recoverable
    invalid_value error carrying valid_values (keeps the R2 contract green).
    """
    if value not in _LIST_STATUS_FILTERS:
        raise CodeScentError(
            code=ErrorCode.INVALID_VALUE,
            message=f"Invalid finding status filter {value!r}.",
            severity=ErrorSeverity.ERROR,
            details={"status": value},
            recovery={
                "valid_values": list(VALID_LIST_STATUSES),
                "fix_hint": "Pass one of all, open, backlog, or regressed.",
            },
        )
    return value


# explain_finding view routing (U11): default "fix" == the current fix-ready
# explanation; the other views subsume get_finding / explain_score /
# get_finding_context.
VALID_EXPLAIN_VIEWS: tuple[str, ...] = ("fix", "summary", "score", "context")


def _validate_explain_view(value: str) -> str:
    if value not in VALID_EXPLAIN_VIEWS:
        raise CodeScentError(
            code=ErrorCode.INVALID_VALUE,
            message=f"Invalid explain view {value!r}.",
            severity=ErrorSeverity.ERROR,
            details={"view": value},
            recovery={
                "valid_values": list(VALID_EXPLAIN_VIEWS),
                "fix_hint": "Pass one of fix, summary, score, or context.",
            },
        )
    return value


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


# U11: explain_finding returns one of four shapes, selected by ``view``.
ExplainFindingResult = (
    ExplainFindingToolPayload
    | FindingDetailToolPayload
    | ScoreExplanationToolPayload
    | FindingContextToolPayload
)


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
            "The finding list from local .codescent state, filtered by status: "
            "'all' (default; every finding + lifecycle counts), 'open', "
            "'backlog' (open/in-progress/needs-review/regressed), or 'regressed'. "
            "Leads with the actionable set (warning+ severity or verified tier); "
            "the info/heuristic mass is a counted, opt-in tail -- pass "
            "include_all=True or min_severity='info' for the full set. Bounded "
            "inline items with a ctx_ result id when omitted; lifecycle counts "
            "ride every response. e.g. list_findings(repo='.', status='backlog'). "
            "Read-only for source."
        ),
    )(list_findings)
    _ = mcp.tool(
        description=(
            "Explain a finding, selected by view (all read-only, all bounded): "
            "'fix' (default) is the fix-ready explanation -- why it matters, the "
            "suggested fix, and a bounded source snippet; 'summary' is the finding "
            "in full (structured evidence + lifecycle history); 'score' is the "
            "deterministic ranking inputs, no LLM judgment; 'context' is the "
            "bounded refactor context before reading whole files. Pass a "
            "finding_id from get_next_improvement or list_findings. e.g. "
            "explain_finding(finding_id='python.dead_code_candidate:9f0a...', "
            "view='context')."
        ),
    )(explain_finding)
    _ = mcp.tool(
        description=(
            "Pick the next deterministic improvement from open or regressed "
            "findings; returns a finding_id that feeds explain_finding, "
            "plan_refactor, and mark_finding. e.g. "
            "get_next_improvement(repo='.')."
        ),
    )(get_next_improvement)
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
            "Update a finding's lifecycle status in .codescent; never edits "
            "source. Pass a finding_id from get_next_improvement or list_findings "
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
            "list_findings. e.g. record_verification(finding_id='...', "
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
        next_tools=("get_next_improvement", "list_findings"),
    )
    return cast("ScanHealthToolPayload", cast("object", envelope))


def list_findings(
    repo: str = ".",
    status: str = "all",
    min_severity: str = DEFAULT_MIN_SEVERITY,
    include_all: bool = False,
) -> ListFindingsToolPayload:
    """Merged finding list (U10): one status filter over one gated report.

    Subsumes the former get_smell_report/get_backlog/get_regressions/
    get_progress: ``status`` routes the finding set, and repo-wide lifecycle
    counts (the progress view) ride every response. Leads with the gated
    actionable headline, then the info/heuristic tail; counts and the full set
    stay reachable (presentation-only gate).
    """
    status = _validate_list_status(status)
    min_severity = validate_min_severity(min_severity)
    report = FindingsService(repo).get_smell_report(
        min_severity=min_severity,
        include_all=include_all,
    )
    statuses = _LIST_STATUS_FILTERS[status]

    def _keep(finding: FindingRow) -> bool:
        return statuses is None or finding.status in statuses

    headline = [finding for finding in report.headline if _keep(finding)]
    deferred = [finding for finding in report.deferred if _keep(finding)]
    matched = [finding for finding in report.findings if _keep(finding)]
    envelope = _finding_list_envelope(
        repo,
        status=status,
        report=report,
        headline=headline,
        deferred=deferred,
        matched=matched,
    )
    return cast("ListFindingsToolPayload", cast("object", envelope))


def _finding_list_envelope(  # noqa: PLR0913 - keyword-only presentation inputs.
    repo: str,
    *,
    status: str,
    report: SmellReport,
    headline: list[FindingRow],
    deferred: list[FindingRow],
    matched: list[FindingRow],
) -> dict[str, object]:
    records = _headline_then_tail(headline) + _headline_then_tail(deferred)
    severity_counts, rule_counts = aggregate_counts(
        (finding.severity, finding.rule_id) for finding in matched
    )
    # Lifecycle counts describe the matched set, so sum == total_count. For
    # status="all" this is the repo-wide progress view (subsuming get_progress);
    # a filtered status describes only its rows.
    status_counts = _status_counts(matched)
    aggregates: dict[str, object] = {
        "status": status,
        "open_count": status_counts.get(FindingStatus.OPEN.value, 0),
        "total_count": len(matched),
        "status_counts": status_counts,
        "severity_counts": severity_counts,
        "rule_counts": rule_counts,
    }
    return bounded_finding_list(
        kind="finding_list",
        repo=repo,
        tool_name="list_findings",
        records=records,
        aggregates=aggregates,
        next_tools=("get_next_improvement", "plan_refactor", "retrieve_result"),
        extra=_gate_extra(report),
    )


def explain_finding(
    finding_id: str,
    repo: str = ".",
    view: str = "fix",
) -> ExplainFindingResult:
    """Merged finding explanation (U11): one view selector over four code paths.

    Subsumes the former get_finding/explain_score/get_finding_context. ``view``
    routes to that tool's payload; default "fix" == the prior explain_finding
    (why + evidence + fix + bounded snippet). "summary" is the full finding
    detail, "score" the deterministic ranking inputs, "context" the bounded
    refactor context.
    """
    view = _validate_explain_view(view)
    if view == "summary":
        return detail_payload(ReportService(repo).get_finding(finding_id))
    if view == "score":
        return score_explanation_payload(ReportService(repo).explain_score(finding_id))
    if view == "context":
        return get_finding_context(finding_id, repo)
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
        "next_tools": ("explain_finding", "plan_refactor"),
    }


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
        next_tools=("get_next_improvement", "list_findings"),
        regressed_finding_ids=result.regressed_finding_ids,
    )
    return cast("RescanToolPayload", cast("object", envelope))
