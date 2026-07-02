from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from codescent.core.json_decode import JsonObject, decode_json_object
from codescent.services.calibration import CalibrationService
from codescent.storage import RepositoryStorage, initialize_storage
from codescent.storage.repositories import FindingRepository, FindingRow

if TYPE_CHECKING:
    from pathlib import Path

    from codescent.services.calibration import RuleCalibration


@dataclass(frozen=True, slots=True)
class FindingDetail:
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


@dataclass(frozen=True, slots=True)
class ScoreExplanation:
    finding_id: str
    score_inputs: JsonObject
    reasons: tuple[str, ...]
    next_steps: tuple[str, ...]
    subjective: bool
    calibration: JsonObject


@dataclass(frozen=True, slots=True)
class ReportService:
    repo_root: Path | str

    def get_finding(self, finding_id: str) -> FindingDetail:
        finding = _repository(self.repo_root).get_finding(finding_id)
        evidence = decode_json_object(finding.evidence_json)
        return FindingDetail(
            finding_id=finding.id,
            rule_id=finding.rule_id,
            file_path=finding.file_path,
            severity=finding.severity,
            confidence=finding.confidence,
            confidence_tier=finding.confidence_tier,
            provenance=decode_json_object(finding.provenance_json),
            status=finding.status.value,
            title=finding.title,
            message=finding.message,
            evidence=evidence,
            suggested_action=finding.suggested_action,
            status_history=_status_history(finding),
            score_inputs=_score_inputs(finding),
        )

    def explain_score(self, finding_id: str) -> ScoreExplanation:
        finding = _repository(self.repo_root).get_finding(finding_id)
        calibration = CalibrationService(self.repo_root).adjusted_confidence(
            finding.rule_id,
        )
        return ScoreExplanation(
            finding_id=finding.id,
            score_inputs=_score_inputs(finding),
            reasons=_score_reasons(finding) + _calibration_reasons(calibration),
            next_steps=(
                finding.suggested_action,
                "Use explain_finding for evidence before editing source.",
            ),
            subjective=False,
            calibration=_calibration_block(calibration),
        )


def _repository(repo_root: Path | str) -> FindingRepository:
    state = initialize_storage(repo_root)
    return FindingRepository(RepositoryStorage(state))


def _status_history(finding: FindingRow) -> tuple[JsonObject, ...]:
    return tuple(
        {
            "event_type": event.event_type,
            "created_at": event.created_at,
            "details_json": event.details_json,
        }
        for event in finding.events
    )


def _score_inputs(finding: FindingRow) -> JsonObject:
    return {
        "severity": finding.severity,
        "confidence": finding.confidence,
        "status": finding.status.value,
        "rule_id": finding.rule_id,
    }


def _score_reasons(finding: FindingRow) -> tuple[str, ...]:
    return (
        f"severity={finding.severity} contributes deterministic priority",
        f"confidence={finding.confidence:.2f} comes from the rule result",
        f"status={finding.status.value} controls backlog ordering",
    )


def _calibration_block(calibration: RuleCalibration | None) -> JsonObject:
    if calibration is None:
        return {"calibrated": False, "sample_size": 0}
    return {
        "calibrated": calibration.calibrated,
        "base_confidence": calibration.base_confidence,
        "adjusted_confidence": calibration.adjusted_confidence,
        "accepted": calibration.accepted,
        "rejected": calibration.rejected,
        "sample_size": calibration.sample_size,
        "accept_rate": calibration.accept_rate,
    }


def _calibration_reasons(calibration: RuleCalibration | None) -> tuple[str, ...]:
    if calibration is None or not calibration.calibrated:
        return ()
    reason = "".join(
        (
            f"adjusted_confidence={calibration.adjusted_confidence:.2f} ",
            f"from this repo's {calibration.accepted}/{calibration.sample_size} ",
            "accept rate",
        ),
    )
    return (reason,)
