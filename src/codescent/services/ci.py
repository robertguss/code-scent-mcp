from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from codescent.services.code_health import CodeHealthService
from codescent.services.risk import RiskService

if TYPE_CHECKING:
    from codescent.engine.rules.model import CodeHealthFinding


@dataclass(frozen=True, slots=True)
class ChangedFileSummary:
    path: str
    risk_level: str
    risk_score: float
    finding_count: int


@dataclass(frozen=True, slots=True)
class CiReport:
    ok: bool
    risk_level: str
    finding_count: int
    changed_file_health: tuple[ChangedFileSummary, ...]
    suggested_tests: tuple[str, ...]
    recommended_commands: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class CiService:
    repo_root: str

    def run(self, *, threshold: str) -> CiReport:
        scan = CodeHealthService(self.repo_root).scan()
        diff_risk = RiskService(self.repo_root).review_diff_risk()
        risk_level = _scan_risk_level(
            tuple(finding.severity for finding in scan.findings),
        )
        changed_file_health = _health_from_scan(scan.findings)
        return CiReport(
            ok=_passes(threshold, risk_level),
            risk_level=risk_level,
            finding_count=scan.findings_created,
            changed_file_health=changed_file_health,
            suggested_tests=diff_risk.suggested_tests or ("pytest",),
            recommended_commands=diff_risk.recommended_commands or ("pytest",),
        )


def _passes(threshold: str, risk_level: str) -> bool:
    threshold_rank = _risk_rank(threshold)
    risk_rank = _risk_rank(risk_level)
    return risk_rank < threshold_rank


def _risk_rank(level: str) -> int:
    match level:
        case "low":
            return 1
        case "medium" | "warn":
            return 2
        case "high":
            return 3
        case _:
            return 2


def _scan_risk_level(severities: tuple[str, ...]) -> str:
    if "error" in severities or "warning" in severities:
        return "high"
    if "info" in severities:
        return "medium"
    return "low"


def _health_from_scan(
    findings: tuple[CodeHealthFinding, ...],
) -> tuple[ChangedFileSummary, ...]:
    paths: dict[str, int] = {}
    for finding in findings:
        paths[finding.file_path] = paths.get(finding.file_path, 0) + 1
    return tuple(
        ChangedFileSummary(
            path=path,
            risk_level="high",
            risk_score=0.7,
            finding_count=count,
        )
        for path, count in sorted(paths.items())
    )
