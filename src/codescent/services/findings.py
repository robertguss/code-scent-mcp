from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Final, cast

from codescent.core.models import FindingStatus
from codescent.services.code_health import CodeHealthScanResult, CodeHealthService
from codescent.services.git import git_change_counts
from codescent.storage import RepositoryStorage, initialize_storage
from codescent.storage.repositories import (
    FindingEventRow,
    FindingRepository,
    FindingRow,
    VerificationRunRow,
)

MAX_VERIFICATION_OUTPUT_SUMMARY_CHARS: Final = 1000


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
class MarkFindingResult:
    finding: FindingRow
    requested_status: FindingStatus
    applied_status: FindingStatus
    gated: bool
    message: str

    @property
    def id(self) -> str:
        return self.finding.id

    @property
    def status(self) -> FindingStatus:
        return self.finding.status


@dataclass(frozen=True, slots=True)
class RecordedVerification:
    verification: VerificationRunRow
    output_truncated: bool

    @property
    def id(self) -> int:
        return self.verification.id

    @property
    def finding_id(self) -> str:
        return self.verification.finding_id

    @property
    def command(self) -> str:
        return self.verification.command

    @property
    def exit_code(self) -> int:
        return self.verification.exit_code

    @property
    def output_summary(self) -> str:
        return self.verification.output_summary


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
        change_counts = git_change_counts(Path(self.repo_root))
        actionable = (
            FindingStatus.REGRESSED,
            FindingStatus.NEEDS_REVIEW,
            FindingStatus.OPEN,
            FindingStatus.IN_PROGRESS,
        )
        ranked_findings = sorted(
            report.findings,
            key=lambda finding: _finding_priority(finding, change_counts),
        )
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
    ) -> MarkFindingResult:
        repository = _repository(self.repo_root)
        if status is FindingStatus.RESOLVED and not repository.has_passing_verification(
            finding_id
        ):
            message = "resolution requires a passing verification or a clean rescan"
            gated_note = _gated_resolution_note(note)
            finding = repository.update_status(
                finding_id,
                FindingStatus.NEEDS_REVIEW,
                note=gated_note,
            )
            return MarkFindingResult(
                finding=finding,
                requested_status=status,
                applied_status=FindingStatus.NEEDS_REVIEW,
                gated=True,
                message=message,
            )

        finding = repository.update_status(finding_id, status, note=note)
        return MarkFindingResult(
            finding=finding,
            requested_status=status,
            applied_status=finding.status,
            gated=False,
            message="",
        )

    def record_verification(
        self,
        finding_id: str,
        *,
        command: str,
        exit_code: int,
        output_summary: str,
    ) -> RecordedVerification:
        bounded_summary = output_summary[:MAX_VERIFICATION_OUTPUT_SUMMARY_CHARS]
        verification = _repository(self.repo_root).record_verification(
            finding_id,
            command=command,
            exit_code=exit_code,
            output_summary=bounded_summary,
        )
        return RecordedVerification(
            verification=verification,
            output_truncated=len(output_summary) > len(bounded_summary),
        )

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


def _gated_resolution_note(note: str) -> str:
    message = "resolution requires a passing verification or a clean rescan"
    if not note:
        return message
    return f"{message}; original note: {note}"


def _finding_priority(
    finding: FindingRow,
    change_counts: dict[str, int],
) -> tuple[int, int, int, str]:
    severity_rank = {"warning": 0, "error": 0, "info": 1}.get(finding.severity, 2)
    rule_rank = {
        "python.changed_source_without_related_test": 9,
        "python.missing_nearby_test": 8,
    }.get(finding.rule_id, 0)
    return (
        severity_rank,
        rule_rank,
        -_hotspot_score(finding, change_counts),
        finding.id,
    )


def _hotspot_score(finding: FindingRow, change_counts: dict[str, int]) -> int:
    churn = change_counts.get(finding.file_path, 0)
    if churn <= 0:
        return 0
    return churn * _evidence_line_count(finding.evidence_json)


def _evidence_line_count(evidence_json: str) -> int:
    try:
        raw_evidence = cast("object", json.loads(evidence_json))
    except json.JSONDecodeError:
        return 0
    if not isinstance(raw_evidence, dict):
        return 0

    evidence = cast("dict[str, object]", raw_evidence)
    line_count = evidence.get("line_count")
    if isinstance(line_count, bool) or not isinstance(line_count, int):
        return 0
    return max(line_count, 0)
