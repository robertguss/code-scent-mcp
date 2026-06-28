from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from codescent.core.paths import resolve_repo_root
from codescent.services.code_health import CodeHealthService
from codescent.services.refactor_planning import RefactorPlanningService
from codescent.services.search import SearchService
from codescent.services.verification import VerificationService
from codescent.storage import RepositoryStorage, initialize_storage
from codescent.storage.repositories import FindingRepository, FindingRow

if TYPE_CHECKING:
    from pathlib import Path

DEFAULT_CHANGED_FILE_LIMIT: Final = 20
HIGH_RISK_THRESHOLD: Final = 0.75
MEDIUM_RISK_THRESHOLD: Final = 0.4
_SEVERITY_ORDER: Final[dict[str, int]] = {"error": 0, "warning": 1, "info": 2}
_TIER_ORDER: Final[dict[str, int]] = {"verified": 0, "heuristic": 1}


@dataclass(frozen=True, slots=True)
class RiskFinding:
    finding_id: str
    rule_id: str
    file_path: str
    severity: str
    confidence: float
    confidence_tier: str
    status: str


@dataclass(frozen=True, slots=True)
class ChangedFileHealth:
    ok: bool
    path: str
    risk_score: float
    risk_level: str
    findings: tuple[RiskFinding, ...]
    suggested_tests: tuple[str, ...]
    recommended_commands: tuple[str, ...]
    risk_notes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class DiffRiskReport:
    changed_files: tuple[str, ...]
    risk_score: float
    risk_level: str
    findings: tuple[RiskFinding, ...]
    suggested_tests: tuple[str, ...]
    recommended_commands: tuple[str, ...]
    file_health: tuple[ChangedFileHealth, ...]


@dataclass(frozen=True, slots=True)
class RiskService:
    repo_root: Path | str

    def review_diff_risk(self) -> DiffRiskReport:
        changed_files = _changed_files(self.repo_root)
        _ensure_findings(self.repo_root)
        file_health = tuple(
            self._get_file_health(path, changed_files=changed_files)
            for path in changed_files
        )
        findings = rank_findings(
            _dedupe_findings(
                tuple(finding for health in file_health for finding in health.findings),
            ),
        )
        risk_score = _max_score(tuple(health.risk_score for health in file_health))
        return DiffRiskReport(
            changed_files=changed_files,
            risk_score=risk_score,
            risk_level=_risk_level(risk_score),
            findings=findings,
            suggested_tests=_dedupe(
                tuple(
                    test for health in file_health for test in health.suggested_tests
                ),
            ),
            recommended_commands=_dedupe(
                tuple(
                    command
                    for health in file_health
                    for command in health.recommended_commands
                ),
            ),
            file_health=file_health,
        )

    def get_changed_file_health(self, path: str) -> ChangedFileHealth:
        changed_files = _changed_files(self.repo_root)
        return self._get_file_health(path, changed_files=changed_files)

    def _get_file_health(
        self,
        path: str,
        *,
        changed_files: tuple[str, ...],
    ) -> ChangedFileHealth:
        is_changed = path in changed_files
        _ensure_findings(self.repo_root)
        findings = tuple(
            finding
            for finding in _repository(self.repo_root).list_findings()
            if finding.file_path == path
        )
        suggested = VerificationService(
            self.repo_root,
            auto_refresh=False,
        ).suggest_tests(path)
        impact = RefactorPlanningService(self.repo_root).get_impact(
            target=path,
            target_type="file",
        )
        risk_score = _file_risk_score(findings, impact.confidence)
        return ChangedFileHealth(
            ok=is_changed,
            path=path,
            risk_score=risk_score,
            risk_level=_risk_level(risk_score),
            findings=rank_findings(
                tuple(_risk_finding(finding) for finding in findings),
            ),
            suggested_tests=suggested.likely_tests,
            recommended_commands=suggested.commands,
            risk_notes=(
                _change_note(path, is_changed),
                *impact.risk_notes,
            ),
        )


def _changed_files(repo_root: Path | str) -> tuple[str, ...]:
    root = resolve_repo_root(repo_root)
    results = SearchService(root).search_changed_files(limit=DEFAULT_CHANGED_FILE_LIMIT)
    return tuple(result["path"] for result in results)


def _repository(repo_root: Path | str) -> FindingRepository:
    state = initialize_storage(repo_root)
    return FindingRepository(RepositoryStorage(state))


def _change_note(path: str, is_changed: bool) -> str:
    if is_changed:
        return f"changed file: {path}"
    return f"not currently changed: {path}"


def _ensure_findings(repo_root: Path | str) -> None:
    if _repository(repo_root).list_findings():
        return
    _ = CodeHealthService(repo_root).scan()


def _risk_finding(finding: FindingRow) -> RiskFinding:
    return RiskFinding(
        finding_id=finding.id,
        rule_id=finding.rule_id,
        file_path=finding.file_path,
        severity=finding.severity,
        confidence=finding.confidence,
        confidence_tier=finding.confidence_tier,
        status=finding.status.value,
    )


def rank_findings(findings: tuple[RiskFinding, ...]) -> tuple[RiskFinding, ...]:
    """Order findings by severity, then tier, then confidence, then id.

    Verified findings rank above heuristic ones at equal severity; the
    confidence-desc and id tie-breaks keep the order deterministic.
    """
    return tuple(
        sorted(
            findings,
            key=lambda finding: (
                _SEVERITY_ORDER.get(finding.severity, len(_SEVERITY_ORDER)),
                _TIER_ORDER.get(finding.confidence_tier, len(_TIER_ORDER)),
                -finding.confidence,
                finding.finding_id,
            ),
        ),
    )


def _file_risk_score(
    findings: tuple[FindingRow, ...],
    impact_confidence: float,
) -> float:
    if not findings:
        return min(impact_confidence * 0.5, 1.0)
    severity_score = max(_severity_score(finding.severity) for finding in findings)
    confidence_score = max(finding.confidence for finding in findings)
    return min(max(severity_score, confidence_score, impact_confidence), 1.0)


def _severity_score(severity: str) -> float:
    match severity:
        case "error":
            return 0.9
        case "warning":
            return 0.7
        case "info":
            return 0.3
        case _:
            return 0.2


def _risk_level(score: float) -> str:
    if score >= HIGH_RISK_THRESHOLD:
        return "high"
    if score >= MEDIUM_RISK_THRESHOLD:
        return "medium"
    return "low"


def _max_score(scores: tuple[float, ...]) -> float:
    if not scores:
        return 0.0
    return max(scores)


def _dedupe(items: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(item for item in items if item))


def _dedupe_findings(findings: tuple[RiskFinding, ...]) -> tuple[RiskFinding, ...]:
    deduped: dict[str, RiskFinding] = {}
    for finding in findings:
        deduped[finding.finding_id] = finding
    return tuple(deduped.values())
