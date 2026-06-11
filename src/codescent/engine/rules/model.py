from __future__ import annotations

import hashlib
from dataclasses import dataclass

type EvidenceValue = int | float | str | bool


@dataclass(frozen=True, slots=True)
class CodeHealthFinding:
    id: str
    stable_key: str
    rule_id: str
    title: str
    message: str
    file_path: str
    symbol: str | None
    severity: str
    confidence: float
    evidence: dict[str, EvidenceValue]
    suggested_action: str


@dataclass(frozen=True, slots=True)
class FindingSpec:
    rule_id: str
    title: str
    message: str
    file_path: str
    symbol: str | None
    severity: str
    confidence: float
    evidence: dict[str, EvidenceValue]
    suggested_action: str


def build_finding(spec: FindingSpec) -> CodeHealthFinding:
    stable_key = _stable_key(spec.rule_id, spec.file_path, spec.symbol, spec.evidence)
    return CodeHealthFinding(
        id=stable_key,
        stable_key=stable_key,
        rule_id=spec.rule_id,
        title=spec.title,
        message=spec.message,
        file_path=spec.file_path,
        symbol=spec.symbol,
        severity=spec.severity,
        confidence=spec.confidence,
        evidence=spec.evidence,
        suggested_action=spec.suggested_action,
    )


def _stable_key(
    rule_id: str,
    file_path: str,
    symbol: str | None,
    evidence: dict[str, EvidenceValue],
) -> str:
    fingerprint = "|".join(
        f"{key}={value}"
        for key, value in sorted(evidence.items())
        if key not in {"line_count", "count", "threshold", "depth", "import_count"}
    )
    raw = f"{rule_id}|{file_path}|{symbol or ''}|{fingerprint}"
    digest = hashlib.sha256(raw.encode()).hexdigest()[:12]
    return f"{rule_id}:{digest}"
