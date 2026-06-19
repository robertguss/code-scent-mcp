from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Final

from codescent.services.code_health import CodeHealthService
from codescent.services.config import ConfigService
from codescent.services.git import git_changed_paths_since
from codescent.services.risk import RiskService
from codescent.storage import RepositoryStorage, initialize_storage

if TYPE_CHECKING:
    from codescent.engine.rules.model import CodeHealthFinding

_SEVERITY_RANK: Final[dict[str, int]] = {"error": 0, "warning": 1, "info": 2}
_NEW_FINDING_REPORT_LIMIT: Final = 50

# This rule is a transient diff signal (it depends on the index's changed-file
# state), not a stable code-health finding, so it would churn the ratchet's
# new/resolved sets between scans. Keep it out of the baseline comparison.
_RATCHET_EXCLUDED_RULE_IDS: Final = frozenset(
    {"python.changed_source_without_related_test"},
)


@dataclass(frozen=True, slots=True)
class ChangedFileSummary:
    path: str
    risk_level: str
    risk_score: float
    finding_count: int
    baseline_count: int | None = None
    regressed: bool = False


@dataclass(frozen=True, slots=True)
class NewFindingSummary:
    stable_key: str
    rule_id: str
    file_path: str
    severity: str


@dataclass(frozen=True, slots=True)
class CiReport:
    ok: bool
    risk_level: str
    finding_count: int
    changed_file_health: tuple[ChangedFileSummary, ...]
    suggested_tests: tuple[str, ...]
    recommended_commands: tuple[str, ...]
    ratchet_enabled: bool = False
    ratchet_regressions: tuple[ChangedFileSummary, ...] = ()
    baseline_exists: bool = True
    base_ref: str = ""
    new_findings: tuple[NewFindingSummary, ...] = ()
    new_finding_count: int = 0
    resolved_count: int = 0


@dataclass(frozen=True, slots=True)
class BaselineUpdateResult:
    files_recorded: int
    finding_count: int


@dataclass(frozen=True, slots=True)
class CiService:
    repo_root: Path | str

    def run(
        self,
        *,
        threshold: str,
        ratchet: bool = False,
        base_ref: str = "",
    ) -> CiReport:
        scan = CodeHealthService(self.repo_root).scan()
        diff_risk = RiskService(self.repo_root).review_diff_risk()
        risk_level = _scan_risk_level(
            tuple(finding.severity for finding in scan.findings),
        )
        baseline_counts = _baseline_counts(self.repo_root) if ratchet else None
        changed_file_health = _health_from_scan(
            scan.findings,
            baseline_counts=baseline_counts,
        )
        ratchet_regressions = (
            tuple(item for item in changed_file_health if item.regressed)
            if ratchet
            else ()
        )

        new_findings: tuple[NewFindingSummary, ...] = ()
        resolved_count = 0
        blocking_new = False
        baseline_exists = True
        if ratchet:
            ratchet_config = ConfigService(self.repo_root).load().ratchet
            base_ref = base_ref or ratchet_config.base_ref
            baseline_exists = _baseline_exists(self.repo_root)
            if baseline_exists:
                new_findings, resolved_count = self._new_and_resolved(
                    scan.findings,
                    base_ref=base_ref,
                )
                blocking_new = _has_blocking_new(
                    new_findings,
                    ratchet_config.fail_on_new_severity,
                )

        # In ratchet mode the gate is *new* debt only — the pre-existing
        # backlog (and the absolute risk level it drives) must not fail CI, which
        # is the whole point of the ratchet. The count-based regressions remain
        # for display only. With no accepted baseline the ratchet is a no-op
        # (it recommends accepting a baseline rather than failing).
        ok = not blocking_new if ratchet else _passes(threshold, risk_level)
        return CiReport(
            ok=ok,
            risk_level=risk_level,
            finding_count=scan.findings_created,
            changed_file_health=changed_file_health,
            suggested_tests=diff_risk.suggested_tests or ("pytest",),
            recommended_commands=diff_risk.recommended_commands or ("pytest",),
            ratchet_enabled=ratchet,
            ratchet_regressions=ratchet_regressions,
            baseline_exists=baseline_exists if ratchet else True,
            base_ref=base_ref,
            new_findings=new_findings[:_NEW_FINDING_REPORT_LIMIT],
            new_finding_count=len(new_findings),
            resolved_count=resolved_count,
        )

    def _new_and_resolved(
        self,
        findings: tuple[CodeHealthFinding, ...],
        *,
        base_ref: str,
    ) -> tuple[tuple[NewFindingSummary, ...], int]:
        baseline_keys = _baseline_stable_keys(self.repo_root)
        ratchet_findings = _ratchet_findings(findings)
        in_scope = _scope_findings(self.repo_root, ratchet_findings, base_ref)
        new_findings = tuple(
            NewFindingSummary(
                stable_key=finding.stable_key,
                rule_id=finding.rule_id,
                file_path=finding.file_path,
                severity=finding.severity,
            )
            for finding in in_scope
            if finding.stable_key not in baseline_keys
        )
        current_keys = {finding.stable_key for finding in ratchet_findings}
        resolved_count = sum(1 for key in baseline_keys if key not in current_keys)
        return new_findings, resolved_count

    def update_baseline(self) -> BaselineUpdateResult:
        scan = CodeHealthService(self.repo_root).scan()
        state = initialize_storage(self.repo_root)
        counts = _finding_counts(scan.findings)
        now = datetime.now(UTC).isoformat()
        with RepositoryStorage(state).write_transaction() as connection:
            file_rows: list[tuple[str]] = connection.execute(
                "select path from files order by path",
            ).fetchall()
            _ = connection.execute("delete from health_baseline")
            _ = connection.executemany(
                """
                insert into health_baseline (
                    file_path,
                    finding_count,
                    created_at
                ) values (?, ?, ?)
                """,
                ((path, counts.get(path, 0), now) for (path,) in file_rows),
            )
            _ = connection.execute("delete from finding_baseline")
            _ = connection.executemany(
                """
                insert into finding_baseline (
                    stable_key,
                    rule_id,
                    file_path,
                    severity,
                    created_at
                ) values (?, ?, ?, ?, ?)
                """,
                (
                    (
                        finding.stable_key,
                        finding.rule_id,
                        finding.file_path,
                        finding.severity,
                        now,
                    )
                    for finding in _ratchet_findings(scan.findings)
                ),
            )
        return BaselineUpdateResult(
            files_recorded=len(file_rows),
            finding_count=sum(counts.values()),
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
    *,
    baseline_counts: dict[str, int] | None = None,
) -> tuple[ChangedFileSummary, ...]:
    counts = _finding_counts(findings)
    return tuple(
        ChangedFileSummary(
            path=path,
            risk_level="high",
            risk_score=0.7,
            finding_count=count,
            baseline_count=_baseline_count(baseline_counts, path),
            regressed=_regressed_against_baseline(baseline_counts, path, count),
        )
        for path, count in sorted(counts.items())
    )


def _finding_counts(findings: tuple[CodeHealthFinding, ...]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for finding in findings:
        counts[finding.file_path] = counts.get(finding.file_path, 0) + 1
    return counts


def _baseline_counts(repo_root: Path | str) -> dict[str, int]:
    state = initialize_storage(repo_root)
    with RepositoryStorage(state).read_connection() as connection:
        rows: list[tuple[str, int]] = connection.execute(
            "select file_path, finding_count from health_baseline",
        ).fetchall()
    return dict(rows)


def _baseline_exists(repo_root: Path | str) -> bool:
    state = initialize_storage(repo_root)
    with RepositoryStorage(state).read_connection() as connection:
        rows: list[tuple[int]] = connection.execute(
            "select 1 from health_baseline limit 1",
        ).fetchall()
    return bool(rows)


def _baseline_stable_keys(repo_root: Path | str) -> frozenset[str]:
    state = initialize_storage(repo_root)
    with RepositoryStorage(state).read_connection() as connection:
        rows: list[tuple[str]] = connection.execute(
            "select stable_key from finding_baseline",
        ).fetchall()
    return frozenset(key for (key,) in rows)


def _scope_findings(
    repo_root: Path | str,
    findings: tuple[CodeHealthFinding, ...],
    base_ref: str,
) -> tuple[CodeHealthFinding, ...]:
    if not base_ref:
        return findings
    changed = git_changed_paths_since(Path(repo_root), base_ref)
    if changed is None:
        # Diff could not be computed; fall back to whole-repo scoping rather
        # than silently treating nothing as changed.
        return findings
    return tuple(finding for finding in findings if finding.file_path in changed)


def _has_blocking_new(
    new_findings: tuple[NewFindingSummary, ...],
    fail_on_new_severity: str,
) -> bool:
    threshold_rank = _severity_rank(fail_on_new_severity)
    return any(
        _severity_rank(finding.severity) <= threshold_rank for finding in new_findings
    )


def _severity_rank(severity: str) -> int:
    return _SEVERITY_RANK.get(severity, _SEVERITY_RANK["info"])


def _ratchet_findings(
    findings: tuple[CodeHealthFinding, ...],
) -> tuple[CodeHealthFinding, ...]:
    return tuple(
        finding
        for finding in findings
        if finding.rule_id not in _RATCHET_EXCLUDED_RULE_IDS
    )


def _baseline_count(baseline_counts: dict[str, int] | None, path: str) -> int | None:
    if baseline_counts is None:
        return None
    return baseline_counts.get(path, 0)


def _regressed_against_baseline(
    baseline_counts: dict[str, int] | None,
    path: str,
    finding_count: int,
) -> bool:
    baseline_count = _baseline_count(baseline_counts, path)
    return baseline_count is not None and finding_count > baseline_count
