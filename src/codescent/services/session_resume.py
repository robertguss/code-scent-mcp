"""Post-compaction session brief: reconstruct "where was I, what's next".

The mirror of ``task_brief.start_task``. ``start_task`` orients a *fresh* task
from a query; ``resume_task`` reconstructs an *in-flight* one purely from
persisted state after an agent loses its in-memory context (e.g. a compaction).
It is a deterministic router over already-persisted data (findings, the
verification ledger, the health-ratchet baseline, and sanitized session events)
and adds no new storage. No analyzed source content is read or returned.

ponytail: session_events are sanitized (fingerprints + metrics only -- no file
paths or finding ids), so the in-flight finding and recently-touched files are
reconstructed from the findings table + verification ledger, not from events.
Events contribute only the recent tool trail. If event granularity ever grows
to carry finding ids, prefer them here for tighter "where was I" fidelity.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final, TypedDict

from codescent.core.models import FindingStatus
from codescent.storage import RepositoryStorage, initialize_storage
from codescent.storage.repositories import FindingRepository, SessionEventRepository

if TYPE_CHECKING:
    from collections.abc import Iterable
    from pathlib import Path

    from codescent.storage.repositories import (
        FindingRow,
        SessionEventRow,
        VerificationRunRow,
    )

ACTIVE_FINDING_LIMIT: Final = 10
VERIFIED_FINDING_LIMIT: Final = 10
TOUCHED_FILE_LIMIT: Final = 8
RECENT_TOOL_LIMIT: Final = 8
NEXT_TOOL_LIMIT: Final = 6
RECENT_EVENT_LIMIT: Final = 500

# In-flight statuses (the agent was mid-work) rank ahead of the plain OPEN
# backlog when choosing what to resume.
_IN_FLIGHT_STATUSES: Final = (
    FindingStatus.IN_PROGRESS,
    FindingStatus.REGRESSED,
    FindingStatus.NEEDS_REVIEW,
)
_ACTIONABLE_STATUSES: Final = frozenset({*_IN_FLIGHT_STATUSES, FindingStatus.OPEN})
_STATUS_RANK: Final = {status: rank for rank, status in enumerate(_IN_FLIGHT_STATUSES)}

STATUS_NOTHING_IN_PROGRESS: Final = "nothing_in_progress"
STATUS_IN_PROGRESS: Final = "in_progress"
STATUS_VERIFIED_UNRESOLVED: Final = "verified_unresolved"


class RatchetStatus(TypedDict):
    baseline_accepted: bool
    baseline_finding_count: int


@dataclass(frozen=True, slots=True)
class ResumeBrief:
    session_id: str
    status: str
    summary: str
    active_findings: tuple[dict[str, str], ...]
    verified_findings: tuple[dict[str, str], ...]
    recently_touched_files: tuple[str, ...]
    recent_tools: tuple[str, ...]
    ratchet: RatchetStatus
    next_tools: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SessionResumeService:
    repo_root: Path | str

    def resume_task(self, *, project_id: str, session_id: str) -> ResumeBrief:
        storage = RepositoryStorage(initialize_storage(self.repo_root))
        findings_repo = FindingRepository(storage)
        events_repo = SessionEventRepository(storage)

        findings = findings_repo.list_findings()
        # ponytail: one verification-runs query per finding (N+1). Findings are a
        # small local backlog, so this is fine; add a bulk read if it ever grows.
        runs_by_finding = {
            finding.id: findings_repo.list_verification_runs(finding.id)
            for finding in findings
        }
        last_activity = {
            finding.id: _last_activity_at(finding, runs_by_finding[finding.id])
            for finding in findings
        }
        verified_ids = {
            finding.id
            for finding in findings
            if any(run.exit_code == 0 for run in runs_by_finding[finding.id])
        }

        active = _active_findings(findings, last_activity)
        verified = _verified_findings(findings, runs_by_finding)
        touched = _recently_touched_files(findings, last_activity)
        recent_tools = _recent_tools(
            events_repo.list_events(
                project_id=project_id,
                session_id=session_id,
                limit=RECENT_EVENT_LIMIT,
            ),
        )
        status, summary, next_tools = _recommend(active, verified_ids)

        return ResumeBrief(
            session_id=session_id,
            status=status,
            summary=summary,
            active_findings=active,
            verified_findings=verified,
            recently_touched_files=touched,
            recent_tools=recent_tools,
            ratchet=_ratchet_status(storage),
            next_tools=next_tools,
        )


def _last_activity_at(
    finding: FindingRow,
    runs: tuple[VerificationRunRow, ...],
) -> str:
    """Most recent activity timestamp ('' if the finding was never acted on).

    New findings get no finding_event on first scan, so an empty value means the
    finding is untouched backlog rather than in-flight work.
    """
    stamps = [event.created_at for event in finding.events]
    stamps.extend(run.created_at for run in runs)
    return max(stamps, default="")


def _active_findings(
    findings: tuple[FindingRow, ...],
    last_activity: dict[str, str],
) -> tuple[dict[str, str], ...]:
    actionable = [f for f in findings if f.status in _ACTIONABLE_STATUSES]
    # Stable, composed sorts (lowest priority first): id, recency desc, status.
    actionable.sort(key=lambda f: f.id)
    actionable.sort(key=lambda f: last_activity[f.id], reverse=True)
    actionable.sort(key=lambda f: _STATUS_RANK.get(f.status, len(_STATUS_RANK)))
    return tuple(_finding_payload(f) for f in actionable[:ACTIVE_FINDING_LIMIT])


def _verified_findings(
    findings: tuple[FindingRow, ...],
    runs_by_finding: dict[str, tuple[VerificationRunRow, ...]],
) -> tuple[dict[str, str], ...]:
    verified: list[tuple[str, dict[str, str]]] = []
    for finding in findings:
        passing = [run for run in runs_by_finding[finding.id] if run.exit_code == 0]
        if not passing:
            continue
        latest = max(passing, key=lambda run: (run.created_at, run.id))
        verified.append(
            (
                latest.created_at,
                {
                    "finding_id": finding.id,
                    "command": latest.command,
                    "verified_at": latest.created_at,
                    "status": finding.status.value,
                },
            ),
        )
    verified.sort(key=lambda item: item[0], reverse=True)
    return tuple(payload for _stamp, payload in verified[:VERIFIED_FINDING_LIMIT])


def _recently_touched_files(
    findings: tuple[FindingRow, ...],
    last_activity: dict[str, str],
) -> tuple[str, ...]:
    touched = [f for f in findings if last_activity[f.id]]
    touched.sort(key=lambda f: f.id)
    touched.sort(key=lambda f: last_activity[f.id], reverse=True)
    return _dedupe_cap(
        (f.file_path for f in touched if f.file_path),
        TOUCHED_FILE_LIMIT,
    )


def _recent_tools(events: tuple[SessionEventRow, ...]) -> tuple[str, ...]:
    # Events arrive oldest-first; reverse for most-recent-first, dedupe, cap.
    names = [
        event.tool_name
        for event in events
        if event.event_type == "tool_called" and event.tool_name is not None
    ]
    return _dedupe_cap(reversed(names), RECENT_TOOL_LIMIT)


def _recommend(
    active: tuple[dict[str, str], ...],
    verified_ids: set[str],
) -> tuple[str, str, tuple[str, ...]]:
    if not active:
        return (
            STATUS_NOTHING_IN_PROGRESS,
            "No in-flight findings; start a fresh task or pick the next improvement.",
            ("start_task", "get_next_improvement", "scan_code_health"),
        )

    top = active[0]
    finding_id = top["id"]
    if finding_id in verified_ids:
        return (
            STATUS_VERIFIED_UNRESOLVED,
            (
                f"Finding {finding_id} ({top['rule_id']}) has a passing "
                "verification but is not resolved; mark it resolved."
            ),
            _dedupe_cap(
                (f"mark_finding:{finding_id}", f"get_finding_context:{finding_id}"),
                NEXT_TOOL_LIMIT,
            ),
        )

    return (
        STATUS_IN_PROGRESS,
        (
            f"Resume finding {finding_id} ({top['rule_id']}) in "
            f"{top['file_path']}: reload its context, then verify."
        ),
        _dedupe_cap(
            (
                f"get_finding_context:{finding_id}",
                f"plan_refactor:{finding_id}",
                "record_verification",
            ),
            NEXT_TOOL_LIMIT,
        ),
    )


def _ratchet_status(storage: RepositoryStorage) -> RatchetStatus:
    # ponytail: read the persisted baseline directly rather than running the full
    # CiService (which needs a git diff). Resume only reports the ratchet's resting
    # state, not a live regression check.
    with storage.read_connection() as connection:
        accepted = bool(
            connection.execute("select 1 from baseline_meta limit 1").fetchall(),
        )
        count_rows: list[tuple[int]] = connection.execute(
            "select count(*) from finding_baseline",
        ).fetchall()
    return {
        "baseline_accepted": accepted,
        "baseline_finding_count": count_rows[0][0] if count_rows else 0,
    }


def _finding_payload(finding: FindingRow) -> dict[str, str]:
    return {
        "id": finding.id,
        "rule_id": finding.rule_id,
        "file_path": finding.file_path,
        "severity": finding.severity,
        "status": finding.status.value,
    }


def _dedupe_cap(items: Iterable[str], limit: int) -> tuple[str, ...]:
    deduped: list[str] = []
    seen: set[str] = set()
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        deduped.append(item)
        if len(deduped) >= limit:
            break
    return tuple(deduped)
