from __future__ import annotations

from typing import TYPE_CHECKING, Final, TypedDict, cast

from codescent.core.errors import CodeScentError, ErrorCode, ErrorSeverity
from codescent.core.json_decode import ProvenanceItem, decode_provenance
from codescent.core.models import FindingStatus
from codescent.core.paths import resolve_repo_root
from codescent.services.result_store import JsonValue, ResultStoreService

if TYPE_CHECKING:
    from collections.abc import Iterable

    from codescent.engine.rules.model import CodeHealthFinding
    from codescent.services.calibration import CalibrationReport
    from codescent.services.code_health import CodeHealthScanResult
    from codescent.services.improvement_plan import ImprovementCluster, ImprovementPlan
    from codescent.services.reports import FindingDetail, ScoreExplanation
    from codescent.storage.repositories import FindingRow

JsonScalar = str | int | float | bool | None
JsonObject = dict[str, JsonScalar]

# A single finding preview row, as returned inline by the list/aggregate tools.
# `provenance` is a small bounded dict (rule_id, language, resolution,
# symbol_resolved); every other value is a scalar.
FindingItem = dict[str, str | float | ProvenanceItem]

# Boundedness controls (see docs/ideas/boundedness-bug-fix.md). List/aggregate
# tools never return more than INLINE_ITEM_LIMIT items inline; the remainder is
# stored and reachable via retrieve_result. RULE_COUNT_LIMIT caps the rule
# histogram so the aggregate block itself stays small.
INLINE_ITEM_LIMIT: Final = 25
RULE_COUNT_LIMIT: Final = 20

_SEVERITY_RANK: Final[dict[str, int]] = {"error": 0, "warning": 1, "info": 2}


class BoundedListBase(TypedDict):
    ok: bool
    kind: str
    total_count: int
    severity_counts: dict[str, int]
    rule_counts: dict[str, int]
    items: tuple[FindingItem, ...]
    returned_count: int
    omitted_count: int
    result_id: str | None
    retrieval_available: bool
    retrieval_hints: tuple[str, ...]
    warnings: tuple[str, ...]
    next_tools: tuple[str, ...]


class ScanHealthToolPayload(BoundedListBase):
    status: str
    scan_id: str
    findings_created: int
    files_scanned: int
    findings_resolved: int
    rule_ids: tuple[str, ...]
    finding_ids: tuple[str, ...]


class RescanToolPayload(ScanHealthToolPayload):
    regressed_finding_ids: tuple[str, ...]
    regressed_count: int


class SmellReportToolPayload(BoundedListBase):
    open_count: int
    status_counts: dict[str, int]


class ListFindingsToolPayload(BoundedListBase):
    # Merged finding-list surface (U10): a status filter over one gated report,
    # carrying repo-wide lifecycle counts (the former progress view).
    status: str
    open_count: int
    status_counts: dict[str, int]


class BacklogToolPayload(BoundedListBase):
    open_count: int
    status_counts: dict[str, int]


class RegressionsToolPayload(BoundedListBase):
    count: int
    status_counts: dict[str, int]


class ImprovementClusterItem(TypedDict):
    theme: str
    rule_id: str
    scope: str
    size: int
    severity: str
    effort: str
    effort_points: float
    health_gain: float
    roi: float
    files: tuple[str, ...]
    finding_ids: tuple[str, ...]
    suggested_action: str


class ImprovementPlanToolPayload(TypedDict):
    ok: bool
    kind: str
    total_clusters: int
    total_findings: int
    clusters: tuple[ImprovementClusterItem, ...]
    returned_count: int
    omitted_count: int
    result_id: str | None
    retrieval_available: bool
    retrieval_hints: tuple[str, ...]
    warnings: tuple[str, ...]
    next_tools: tuple[str, ...]


class RuleCalibrationItem(TypedDict):
    rule_id: str
    base_confidence: float
    adjusted_confidence: float
    accepted: int
    rejected: int
    sample_size: int
    accept_rate: float | None
    calibrated: bool


class SuppressionCandidateItem(TypedDict):
    rule_id: str
    scope: str
    dismissals: int


class CalibrationToolPayload(TypedDict):
    ok: bool
    confidence_recalibration: bool
    learned_suppression: bool
    min_sample_size: int
    rules: tuple[RuleCalibrationItem, ...]
    suppression_candidates: tuple[SuppressionCandidateItem, ...]


class FindingDetailToolPayload(TypedDict):
    ok: bool
    finding_id: str
    rule_id: str
    file_path: str
    severity: str
    confidence: float
    confidence_tier: str
    provenance: JsonObject
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
    calibration: JsonObject


class NextImprovementToolPayload(TypedDict):
    ok: bool
    finding_id: str | None
    rule_id: str | None
    file_path: str | None
    suggested_action: str | None
    next_tools: tuple[str, ...]


class ProgressToolPayload(TypedDict):
    ok: bool
    total_findings: int
    open_count: int
    resolved_count: int
    regressed_count: int
    status_counts: dict[str, int]


class MarkFindingToolPayload(TypedDict):
    ok: bool
    finding_id: str
    status: str
    requested_status: str
    gated: bool
    message: str
    next_tools: tuple[str, ...]


class RecordVerificationToolPayload(TypedDict):
    ok: bool
    finding_id: str
    verification_id: int
    command: str
    exit_code: int
    output_summary: str
    output_truncated: bool
    next_tools: tuple[str, ...]


def severity_rank(severity: str) -> int:
    return _SEVERITY_RANK.get(severity, len(_SEVERITY_RANK))


def aggregate_counts(
    pairs: Iterable[tuple[str, str]],
) -> tuple[dict[str, int], dict[str, int]]:
    """Tally (severity, rule_id) pairs, returning severity and capped rule counts."""
    severity_counts: dict[str, int] = {}
    rule_counts: dict[str, int] = {}
    for severity, rule_id in pairs:
        severity_counts[severity] = severity_counts.get(severity, 0) + 1
        rule_counts[rule_id] = rule_counts.get(rule_id, 0) + 1
    ranked = sorted(rule_counts.items(), key=lambda item: (-item[1], item[0]))
    return severity_counts, dict(ranked[:RULE_COUNT_LIMIT])


def finding_payload(finding: FindingRow) -> FindingItem:
    return {
        "finding_id": finding.id,
        "rule_id": finding.rule_id,
        "file_path": finding.file_path,
        "severity": finding.severity,
        "confidence": finding.confidence,
        "confidence_tier": finding.confidence_tier,
        "provenance": decode_provenance(finding.provenance_json),
        "status": finding.status.value,
        "suggested_action": finding.suggested_action,
    }


def scan_finding_item(finding: CodeHealthFinding) -> FindingItem:
    return {
        "finding_id": finding.id,
        "rule_id": finding.rule_id,
        "file_path": finding.file_path,
        "severity": finding.severity,
        "confidence": finding.confidence,
        "confidence_tier": finding.confidence_tier,
        "provenance": dict(finding.provenance),
        "suggested_action": finding.suggested_action,
    }


def bounded_finding_list(  # noqa: PLR0913
    *,
    kind: str,
    repo: str,
    tool_name: str,
    records: tuple[FindingItem, ...],
    aggregates: dict[str, object],
    next_tools: tuple[str, ...],
    extra: dict[str, object] | None = None,
    limit: int = INLINE_ITEM_LIMIT,
) -> dict[str, object]:
    """Build a bounded envelope: <= limit items inline, the rest behind a result_id.

    Reuses the same ResultStoreService / retrieve_result machinery that
    find_symbol uses, so the full collection is never dropped — only paged.
    """
    total = len(records)
    items = records[:limit]
    omitted = max(0, total - limit)
    result_id: str | None = None
    retrieval_hints: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    if omitted > 0:
        raw_result = cast(
            "JsonValue",
            {
                "kind": kind,
                "items": [dict(record) for record in records],
                **aggregates,
            },
        )
        stored = ResultStoreService(repo).store_result(
            project_id=_store_project_id(repo),
            tool_name=tool_name,
            input_payload={"repo": repo},
            raw_result=raw_result,
        )
        result_id = stored.id
        retrieval_hints = (
            f"retrieve_result(result_id='{result_id}', mode='exact', limit=100)",
            f"retrieve_result(result_id='{result_id}', mode='filtered', file='<path>')",
            f"retrieve_result(result_id='{result_id}', mode='summary')",
        )
        warnings = (
            "".join(
                (
                    f"{omitted} of {total} {kind} items omitted from inline output; ",
                    "call retrieve_result with the result_id to page the full set.",
                ),
            ),
        )
    envelope: dict[str, object] = {
        "ok": True,
        "kind": kind,
        **aggregates,
        "items": items,
        "returned_count": len(items),
        "omitted_count": omitted,
        "result_id": result_id,
        "retrieval_available": result_id is not None,
        "retrieval_hints": retrieval_hints,
        "warnings": warnings,
        "next_tools": next_tools,
    }
    if extra is not None:
        envelope.update(extra)
    return envelope


def calibration_payload(report: CalibrationReport) -> CalibrationToolPayload:
    return {
        "ok": True,
        "confidence_recalibration": report.confidence_recalibration,
        "learned_suppression": report.learned_suppression,
        "min_sample_size": report.min_sample_size,
        "rules": tuple(
            {
                "rule_id": rule.rule_id,
                "base_confidence": rule.base_confidence,
                "adjusted_confidence": rule.adjusted_confidence,
                "accepted": rule.accepted,
                "rejected": rule.rejected,
                "sample_size": rule.sample_size,
                "accept_rate": rule.accept_rate,
                "calibrated": rule.calibrated,
            }
            for rule in report.rules
        ),
        "suppression_candidates": tuple(
            {
                "rule_id": candidate.rule_id,
                "scope": candidate.scope,
                "dismissals": candidate.dismissals,
            }
            for candidate in report.suppression_candidates
        ),
    }


def cluster_item(cluster: ImprovementCluster) -> ImprovementClusterItem:
    return {
        "theme": cluster.theme,
        "rule_id": cluster.rule_id,
        "scope": cluster.scope,
        "size": cluster.size,
        "severity": cluster.severity,
        "effort": cluster.effort,
        "effort_points": cluster.effort_points,
        "health_gain": cluster.health_gain,
        "roi": cluster.roi,
        "files": cluster.files,
        "finding_ids": cluster.finding_ids,
        "suggested_action": cluster.suggested_action,
    }


def improvement_plan_payload(
    plan: ImprovementPlan,
    *,
    repo: str,
    limit: int = INLINE_ITEM_LIMIT,
) -> dict[str, object]:
    items = tuple(cluster_item(cluster) for cluster in plan.clusters)
    visible = items[:limit]
    omitted = max(0, len(items) - limit)
    result_id: str | None = None
    retrieval_hints: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    if omitted > 0:
        raw_result = cast(
            "JsonValue",
            {
                "kind": "improvement_plan",
                "items": [dict(item) for item in items],
                "total_clusters": plan.total_clusters,
                "total_findings": plan.total_findings,
            },
        )
        stored = ResultStoreService(repo).store_result(
            project_id=_store_project_id(repo),
            tool_name="get_improvement_plan",
            input_payload={"repo": repo},
            raw_result=raw_result,
        )
        result_id = stored.id
        retrieval_hints = (
            f"retrieve_result(result_id='{result_id}', mode='exact', limit=100)",
            f"retrieve_result(result_id='{result_id}', mode='summary')",
        )
        warnings = (
            "".join(
                (
                    f"{omitted} of {len(items)} clusters omitted from inline output; ",
                    "call retrieve_result with the result_id to page the full plan.",
                ),
            ),
        )
    return {
        "ok": True,
        "kind": "improvement_plan",
        "total_clusters": plan.total_clusters,
        "total_findings": plan.total_findings,
        "clusters": visible,
        "returned_count": len(visible),
        "omitted_count": omitted,
        "result_id": result_id,
        "retrieval_available": result_id is not None,
        "retrieval_hints": retrieval_hints,
        "warnings": warnings,
        "next_tools": ("explain_finding", "plan_refactor", "get_next_improvement"),
    }


def build_scan_envelope(
    scan: CodeHealthScanResult,
    *,
    repo: str,
    next_tools: tuple[str, ...],
    regressed_finding_ids: tuple[str, ...] | None = None,
) -> dict[str, object]:
    is_rescan = regressed_finding_ids is not None
    kind = "rescan" if is_rescan else "scan"
    tool_name = "rescan" if is_rescan else "scan_code_health"
    ordered = sorted(
        scan.findings,
        key=lambda finding: (severity_rank(finding.severity), finding.id),
    )
    records = tuple(scan_finding_item(finding) for finding in ordered)
    severity_counts, rule_counts = aggregate_counts(
        (finding.severity, finding.rule_id) for finding in scan.findings
    )
    aggregates: dict[str, object] = {
        "status": "complete",
        "scan_id": scan.scan_id,
        "findings_created": scan.findings_created,
        "files_scanned": scan.files_scanned,
        "findings_resolved": scan.findings_resolved,
        "total_count": len(scan.findings),
        "severity_counts": severity_counts,
        "rule_counts": rule_counts,
        "rule_ids": scan.rule_ids,
        "finding_ids": tuple(finding.id for finding in ordered[:INLINE_ITEM_LIMIT]),
    }
    extra: dict[str, object] | None = None
    if regressed_finding_ids is not None:
        # Report the full regressed set: unlike the scan items it is not stored
        # behind a result_id, so truncating it would silently drop regressions a
        # watcher cannot recover. Ids are cheap and regressions are a focused set.
        extra = {
            "regressed_finding_ids": regressed_finding_ids,
            "regressed_count": len(regressed_finding_ids),
        }
    return bounded_finding_list(
        kind=kind,
        repo=repo,
        tool_name=tool_name,
        records=records,
        aggregates=aggregates,
        next_tools=next_tools,
        extra=extra,
    )


def _store_project_id(repo: str) -> str:
    return f"repo:{resolve_repo_root(repo).as_posix()}"


def detail_payload(detail: FindingDetail) -> FindingDetailToolPayload:
    return {
        "ok": True,
        "finding_id": detail.finding_id,
        "rule_id": detail.rule_id,
        "file_path": detail.file_path,
        "severity": detail.severity,
        "confidence": detail.confidence,
        "confidence_tier": detail.confidence_tier,
        "provenance": detail.provenance,
        "status": detail.status,
        "title": detail.title,
        "message": detail.message,
        "evidence": detail.evidence,
        "suggested_action": detail.suggested_action,
        "status_history": detail.status_history,
        "score_inputs": detail.score_inputs,
    }


def score_explanation_payload(
    explanation: ScoreExplanation,
) -> ScoreExplanationToolPayload:
    return {
        "ok": True,
        "finding_id": explanation.finding_id,
        "score_inputs": explanation.score_inputs,
        "reasons": explanation.reasons,
        "next_steps": explanation.next_steps,
        "subjective": explanation.subjective,
        "calibration": explanation.calibration,
    }


def status_from_string(status: str) -> FindingStatus:
    try:
        return FindingStatus(status)
    except ValueError as exc:
        valid_values = [member.value for member in FindingStatus]
        raise CodeScentError(
            code=ErrorCode.INVALID_VALUE,
            message=f"Invalid finding status {status!r}.",
            severity=ErrorSeverity.ERROR,
            details={"status": status},
            recovery={
                "valid_values": valid_values,
                "fix_hint": "Pass one of the valid FindingStatus values.",
            },
        ) from exc
