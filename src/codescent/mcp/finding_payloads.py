from __future__ import annotations

from typing import TYPE_CHECKING, TypedDict

from codescent.core.models import FindingStatus

if TYPE_CHECKING:
    from codescent.services.code_health import CodeHealthScanResult
    from codescent.services.reports import FindingDetail, ScoreExplanation
    from codescent.storage.repositories import FindingRow

JsonScalar = str | int | float | bool | None
JsonObject = dict[str, JsonScalar]


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
    requested_status: str
    gated: bool
    message: str


class RecordVerificationToolPayload(TypedDict):
    ok: bool
    finding_id: str
    verification_id: int
    command: str
    exit_code: int
    output_summary: str
    output_truncated: bool


class RescanToolPayload(TypedDict):
    ok: bool
    status: str
    scan_id: str
    findings_created: int
    finding_ids: tuple[str, ...]
    rule_ids: tuple[str, ...]
    regressed_finding_ids: tuple[str, ...]


def scan_payload(scan: CodeHealthScanResult) -> ScanHealthToolPayload:
    return {
        "ok": True,
        "status": "complete",
        "scan_id": scan.scan_id,
        "findings_created": scan.findings_created,
        "finding_ids": scan.finding_ids,
        "rule_ids": scan.rule_ids,
    }


def finding_payload(finding: FindingRow) -> dict[str, str | float]:
    return {
        "finding_id": finding.id,
        "rule_id": finding.rule_id,
        "file_path": finding.file_path,
        "severity": finding.severity,
        "confidence": finding.confidence,
        "status": finding.status.value,
        "suggested_action": finding.suggested_action,
    }


def detail_payload(detail: FindingDetail) -> FindingDetailToolPayload:
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
    }


def status_from_string(status: str) -> FindingStatus:
    return FindingStatus(status)
