from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from codescent.core.models import FindingStatus
from codescent.services.code_health import CodeHealthScanResult, CodeHealthService
from codescent.storage import RepositoryStorage, initialize_storage
from codescent.storage.repositories import (
    FindingEventRow,
    FindingRepository,
    FindingRow,
)

if TYPE_CHECKING:
    from pathlib import Path


@dataclass(frozen=True, slots=True)
class SmellReport:
    findings: tuple[FindingRow, ...]
    open_count: int
    status_counts: dict[str, int]


@dataclass(frozen=True, slots=True)
class BacklogReport:
    open_count: int
    status_counts: dict[str, int]
    finding_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ProgressReport:
    total_findings: int
    open_count: int
    resolved_count: int
    regressed_count: int
    status_counts: dict[str, int]


@dataclass(frozen=True, slots=True)
class RegressionReport:
    finding_ids: tuple[str, ...]
    count: int


@dataclass(frozen=True, slots=True)
class RescanResult:
    status: str
    scan: CodeHealthScanResult
    regressed_finding_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class FindingsService:
    repo_root: Path | str

    def get_smell_report(self) -> SmellReport:
        findings = _repository(self.repo_root).list_findings()
        counts: dict[str, int] = {}
        for finding in findings:
            counts[finding.status.value] = counts.get(finding.status.value, 0) + 1
        return SmellReport(
            findings=findings,
            open_count=counts.get(FindingStatus.OPEN.value, 0),
            status_counts=counts,
        )

    def get_next_improvement(self) -> FindingRow | None:
        report = self.get_smell_report()
        actionable = (
            FindingStatus.REGRESSED,
            FindingStatus.NEEDS_REVIEW,
            FindingStatus.OPEN,
            FindingStatus.IN_PROGRESS,
        )
        ranked_findings = sorted(report.findings, key=_finding_priority)
        for status in actionable:
            for finding in ranked_findings:
                if finding.status is status:
                    return finding
        return None

    def get_backlog(self) -> BacklogReport:
        report = self.get_smell_report()
        actionable_statuses = {
            FindingStatus.OPEN,
            FindingStatus.IN_PROGRESS,
            FindingStatus.NEEDS_REVIEW,
            FindingStatus.REGRESSED,
        }
        finding_ids = tuple(
            finding.id
            for finding in report.findings
            if finding.status in actionable_statuses
        )
        return BacklogReport(
            open_count=len(finding_ids),
            status_counts=report.status_counts,
            finding_ids=finding_ids,
        )

    def get_progress(self) -> ProgressReport:
        report = self.get_smell_report()
        return ProgressReport(
            total_findings=len(report.findings),
            open_count=report.status_counts.get(FindingStatus.OPEN.value, 0),
            resolved_count=report.status_counts.get(FindingStatus.RESOLVED.value, 0),
            regressed_count=report.status_counts.get(FindingStatus.REGRESSED.value, 0),
            status_counts=report.status_counts,
        )

    def get_regressions(self) -> RegressionReport:
        report = self.get_smell_report()
        finding_ids = tuple(
            finding.id
            for finding in report.findings
            if finding.status is FindingStatus.REGRESSED
        )
        return RegressionReport(finding_ids=finding_ids, count=len(finding_ids))

    def mark_finding(
        self,
        finding_id: str,
        status: FindingStatus,
        *,
        note: str = "",
    ) -> FindingRow:
        return _repository(self.repo_root).update_status(finding_id, status, note=note)

    def rescan(self) -> RescanResult:
        scan = CodeHealthService(self.repo_root).scan()
        report = self.get_smell_report()
        regressed = tuple(
            finding.id
            for finding in report.findings
            if finding.status is FindingStatus.REGRESSED
        )
        return RescanResult(
            status="complete",
            scan=scan,
            regressed_finding_ids=regressed,
        )


def finding_events_payload(events: tuple[FindingEventRow, ...]) -> tuple[str, ...]:
    return tuple(event.event_type for event in events)


def _repository(repo_root: Path | str) -> FindingRepository:
    state = initialize_storage(repo_root)
    return FindingRepository(RepositoryStorage(state))


def _finding_priority(finding: FindingRow) -> tuple[int, int, str]:
    severity_rank = {"warning": 0, "error": 0, "info": 1}.get(finding.severity, 2)
    rule_rank = {
        "python.changed_source_without_related_test": 9,
        "python.missing_nearby_test": 8,
    }.get(finding.rule_id, 0)
    return (severity_rank, rule_rank, finding.id)
