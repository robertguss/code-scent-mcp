from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Final, cast

from codescent.core.errors import CodeScentError, ErrorCode, ErrorSeverity
from codescent.core.models import FindingStatus
from codescent.services.code_health import CodeHealthScanResult, CodeHealthService
from codescent.services.git import git_change_counts
from codescent.services.search_queries import is_test_path
from codescent.storage import RepositoryStorage, initialize_storage
from codescent.storage.repositories import (
    FindingEventRow,
    FindingRepository,
    FindingRow,
    VerificationRunRow,
)

MAX_VERIFICATION_OUTPUT_SUMMARY_CHARS: Final = 1000

# Structural / size rules whose "split / break up / flatten" action is nonsensical
# on a test file (R5): prioritization must not surface "split a test file" over
# real source work. Matched against the rule id's language-suffixed tail.
STRUCTURAL_RULE_SUFFIXES: Final = frozenset(
    {
        "large_file",
        "large_class",
        "large_function",
        "relative_large_file",
        "relative_large_class",
        "relative_large_function",
        "deep_nesting",
        "mixed_responsibilities",
        "structural_near_duplicate",
    },
)


def is_test_structural(rule_id: str, file_path: str) -> bool:
    """A structural/size finding on a test file — low-value to action (R5)."""
    if not is_test_path(file_path):
        return False
    return rule_id.rsplit(".", maxsplit=1)[-1] in STRUCTURAL_RULE_SUFFIXES


# Default finding-view gate (U1). Findings already carry two unused priority
# axes -- severity (info/warning/error) and confidence_tier (verified/heuristic).
# The default view surfaces the ACTIONABLE set (severity >= min OR verified tier)
# as the headline and relegates the info+heuristic mass to a bounded, opt-in
# tail. This is presentation only: finding_count and stored data are untouched,
# and include_all / a lower min_severity restores the full set.
SEVERITY_ORDER: Final[dict[str, int]] = {"info": 0, "warning": 1, "error": 2}
DEFAULT_MIN_SEVERITY: Final = "warning"
VALID_MIN_SEVERITIES: Final = ("info", "warning", "error")
_VERIFIED_TIER: Final = "verified"


@dataclass(frozen=True, slots=True)
class GatedFindings:
    """A severity/tier partition of one finding set (presentation only)."""

    headline: tuple[FindingRow, ...]
    deferred: tuple[FindingRow, ...]
    # True when nothing met the gate, so the full set is surfaced as the headline
    # rather than hiding everything (an info/heuristic-only repo still shows work).
    degraded: bool


def validate_min_severity(value: str) -> str:
    """Return ``value`` if it is a valid gate severity, else a recoverable error.

    Keeps the F1 contract green: an invalid ``min_severity`` yields an
    ``invalid_value`` error carrying ``valid_values`` rather than silently
    degrading, so an agent can self-correct.
    """
    if value not in VALID_MIN_SEVERITIES:
        raise CodeScentError(
            code=ErrorCode.INVALID_VALUE,
            message=f"Invalid min_severity {value!r}.",
            severity=ErrorSeverity.ERROR,
            details={"min_severity": value},
            recovery={
                "valid_values": list(VALID_MIN_SEVERITIES),
                "fix_hint": (
                    "Pass one of info, warning, or error, or set include_all=True."
                ),
            },
        )
    return value


def gate_findings(
    findings: tuple[FindingRow, ...],
    *,
    min_severity: str = DEFAULT_MIN_SEVERITY,
    include_all: bool = False,
) -> GatedFindings:
    """Split findings into the actionable headline and the info/heuristic tail.

    Actionable == severity at or above ``min_severity`` OR a verified-tier
    finding. ``include_all`` (or ``min_severity='info'``) puts everything in the
    headline. When no finding meets the gate the whole set becomes the headline
    with ``degraded=True`` so an info-only repo is never blanked out.
    """
    if include_all:
        return GatedFindings(headline=findings, deferred=(), degraded=False)
    threshold = SEVERITY_ORDER.get(min_severity, SEVERITY_ORDER[DEFAULT_MIN_SEVERITY])
    headline: list[FindingRow] = []
    deferred: list[FindingRow] = []
    for finding in findings:
        actionable = (
            SEVERITY_ORDER.get(finding.severity, 0) >= threshold
            or finding.confidence_tier == _VERIFIED_TIER
        )
        (headline if actionable else deferred).append(finding)
    if not headline:
        return GatedFindings(headline=findings, deferred=(), degraded=True)
    return GatedFindings(
        headline=tuple(headline),
        deferred=tuple(deferred),
        degraded=False,
    )


@dataclass(frozen=True, slots=True)
class SmellReport:
    findings: tuple[FindingRow, ...]
    open_count: int
    status_counts: dict[str, int]
    # The default severity/tier gate applied to ``findings`` (U1). ``headline``
    # is the actionable set every default view leads with; ``deferred`` is the
    # bounded info/heuristic tail; ``degraded`` marks an info-only fallback.
    # ``findings`` stays the FULL set so counts are unchanged.
    headline: tuple[FindingRow, ...] = ()
    deferred: tuple[FindingRow, ...] = ()
    degraded: bool = False
    min_severity: str = DEFAULT_MIN_SEVERITY
    include_all: bool = False


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

    def get_smell_report(
        self,
        *,
        min_severity: str = DEFAULT_MIN_SEVERITY,
        include_all: bool = False,
    ) -> SmellReport:
        findings = _repository(self.repo_root).list_findings()
        counts: dict[str, int] = {}
        for finding in findings:
            counts[finding.status.value] = counts.get(finding.status.value, 0) + 1
        gated = gate_findings(
            findings,
            min_severity=min_severity,
            include_all=include_all,
        )
        return SmellReport(
            findings=findings,
            open_count=counts.get(FindingStatus.OPEN.value, 0),
            status_counts=counts,
            headline=gated.headline,
            deferred=gated.deferred,
            degraded=gated.degraded,
            min_severity=min_severity,
            include_all=include_all,
        )

    def get_next_improvement(
        self,
        *,
        min_severity: str = DEFAULT_MIN_SEVERITY,
        include_all: bool = False,
    ) -> FindingRow | None:
        report = self.get_smell_report(
            min_severity=min_severity,
            include_all=include_all,
        )
        change_counts = git_change_counts(Path(self.repo_root))
        actionable = (
            FindingStatus.REGRESSED,
            FindingStatus.NEEDS_REVIEW,
            FindingStatus.OPEN,
            FindingStatus.IN_PROGRESS,
        )
        # Select from the gated headline: the severity/tier gate is now the
        # default recommendation filter, not just a tiebreak. The headline
        # degrades to the full set when nothing is actionable, so an info-only
        # repo still yields a next improvement.
        ranked_findings = sorted(
            report.headline,
            key=lambda finding: _finding_priority(finding, change_counts),
        )
        for status in actionable:
            for finding in ranked_findings:
                # Never recommend "split a test file": structural findings on
                # test paths are excluded outright, so when they are the only
                # candidates the next improvement is empty rather than nonsense.
                if finding.status is status and not is_test_structural(
                    finding.rule_id,
                    finding.file_path,
                ):
                    return finding
        return None

    def get_backlog(
        self,
        *,
        min_severity: str = DEFAULT_MIN_SEVERITY,
        include_all: bool = False,
    ) -> BacklogReport:
        report = self.get_smell_report(
            min_severity=min_severity,
            include_all=include_all,
        )
        actionable_statuses = {
            FindingStatus.OPEN,
            FindingStatus.IN_PROGRESS,
            FindingStatus.NEEDS_REVIEW,
            FindingStatus.REGRESSED,
        }

        def _ids(rows: tuple[FindingRow, ...]) -> tuple[str, ...]:
            return tuple(
                finding.id
                for finding in rows
                if finding.status in actionable_statuses
            )

        # Inherit the default gate at the same choke: the backlog leads with the
        # actionable headline, then the info/heuristic tail. Every backlog id is
        # still present (count unchanged) -- the gate reorders, it does not drop.
        finding_ids = _ids(report.headline) + _ids(report.deferred)
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
) -> tuple[int, int, int, int, str]:
    # Structural findings on test paths sort below every real finding (R5) while
    # leaving source-finding order untouched (all source findings score 0 here).
    test_structural_rank = (
        1 if is_test_structural(finding.rule_id, finding.file_path) else 0
    )
    severity_rank = {"warning": 0, "error": 0, "info": 1}.get(finding.severity, 2)
    rule_rank = {
        "python.changed_source_without_related_test": 9,
        "python.missing_nearby_test": 8,
    }.get(finding.rule_id, 0)
    return (
        test_structural_rank,
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
