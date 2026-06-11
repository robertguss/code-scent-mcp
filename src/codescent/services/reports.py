from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, TypeGuard, cast

from codescent.storage import RepositoryStorage, initialize_storage
from codescent.storage.repositories import FindingRepository, FindingRow

if TYPE_CHECKING:
    from pathlib import Path

JsonScalar = str | int | float | bool | None
JsonObject = dict[str, JsonScalar]


@dataclass(frozen=True, slots=True)
class FindingDetail:
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


@dataclass(frozen=True, slots=True)
class ReportService:
    repo_root: Path | str

    def get_finding(self, finding_id: str) -> FindingDetail:
        finding = _repository(self.repo_root).get_finding(finding_id)
        evidence = _json_object(finding.evidence_json)
        return FindingDetail(
            finding_id=finding.id,
            rule_id=finding.rule_id,
            file_path=finding.file_path,
            severity=finding.severity,
            confidence=finding.confidence,
            status=finding.status.value,
            title=finding.title,
            message=finding.message,
            evidence=evidence,
            suggested_action=finding.suggested_action,
            status_history=_status_history(finding),
            score_inputs=_score_inputs(finding),
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


def _json_object(raw: str) -> JsonObject:
    parsed = cast("object", json.loads(raw))
    if not isinstance(parsed, dict):
        return {}
    items = cast("dict[object, object]", parsed)
    return {
        str(key): value
        for key, value in items.items()
        if _is_json_scalar(value)
    }


def _is_json_scalar(value: object) -> TypeGuard[JsonScalar]:
    return isinstance(value, str | int | float | bool | type(None))
