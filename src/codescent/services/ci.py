from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from codescent.services.code_health import CodeHealthService
from codescent.services.risk import RiskService
from codescent.storage import RepositoryStorage, initialize_storage

if TYPE_CHECKING:
    from pathlib import Path

    from codescent.engine.rules.model import CodeHealthFinding


@dataclass(frozen=True, slots=True)
class ChangedFileSummary:
    path: str
    risk_level: str
    risk_score: float
    finding_count: int
    baseline_count: int | None = None
    regressed: bool = False


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


@dataclass(frozen=True, slots=True)
class BaselineUpdateResult:
    files_recorded: int
    finding_count: int


@dataclass(frozen=True, slots=True)
class CiService:
    repo_root: Path | str

    def run(self, *, threshold: str, ratchet: bool = False) -> CiReport:
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
        return CiReport(
            ok=_passes(threshold, risk_level) and not ratchet_regressions,
            risk_level=risk_level,
            finding_count=scan.findings_created,
            changed_file_health=changed_file_health,
            suggested_tests=diff_risk.suggested_tests or ("pytest",),
            recommended_commands=diff_risk.recommended_commands or ("pytest",),
            ratchet_enabled=ratchet,
            ratchet_regressions=ratchet_regressions,
        )

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
