"""Unit tests for the deterministic resume-task session brief."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING

from codescent.core.models import FindingStatus
from codescent.services.session_resume import (
    ACTIVE_FINDING_LIMIT,
    RECENT_TOOL_LIMIT,
    TOUCHED_FILE_LIMIT,
    VERIFIED_FINDING_LIMIT,
    SessionResumeService,
)
from codescent.storage import RepositoryStorage, initialize_storage
from codescent.storage.repositories import (
    FindingRepository,
    SessionEventRepository,
    SessionEventWrite,
)

if TYPE_CHECKING:
    from pathlib import Path

PROJECT_ID = "project-a"
SESSION_ID = "session-a"


@dataclass(frozen=True, slots=True)
class SeedFinding:
    finding_id: str
    rule_id: str
    file_path: str
    severity: str
    status: str


def _seed_finding(repo: Path, seed: SeedFinding) -> None:
    repo.mkdir(parents=True, exist_ok=True)
    storage = RepositoryStorage(initialize_storage(repo))
    with storage.write_transaction() as connection:
        _ = connection.execute(
            """
            insert or ignore into scan_runs (
                id, started_at, completed_at, index_version, rule_version,
                files_scanned, findings_created, findings_resolved, status
            ) values ('scan', '2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z',
                1, 'test', 0, 0, 0, 'complete')
            """,
        )
        cursor = connection.execute(
            """
            insert into files (
                path, language, hash, size_bytes, line_count, is_generated, is_test
            ) values (?, 'python', ?, 1, 10, 0, 0)
            """,
            (seed.file_path, seed.finding_id),
        )
        file_id = cursor.lastrowid
        _ = connection.execute(
            """
            insert into findings (
                id, stable_key, rule_id, file_id, severity, confidence, status,
                title, message, evidence_json, suggested_action,
                first_seen_scan_id, last_seen_scan_id
            ) values (?, ?, ?, ?, ?, 0.8, ?, ?, '', '{}', '', 'scan', 'scan')
            """,
            (
                seed.finding_id,
                f"{seed.rule_id}:{seed.file_path}:{seed.finding_id}",
                seed.rule_id,
                file_id,
                seed.severity,
                seed.status,
                seed.finding_id,
            ),
        )


def _touch(repo: Path, finding_id: str, status: FindingStatus) -> None:
    """Record a status change so the finding shows real session activity."""
    _ = FindingRepository(RepositoryStorage(initialize_storage(repo))).update_status(
        finding_id,
        status,
        note="resumed work",
    )


def _verify(repo: Path, finding_id: str, *, exit_code: int = 0) -> None:
    _ = FindingRepository(
        RepositoryStorage(initialize_storage(repo))
    ).record_verification(
        finding_id,
        command="uv run pytest tests/unit/test_x.py",
        exit_code=exit_code,
        output_summary="1 passed" if exit_code == 0 else "1 failed",
    )


def _tool_event(repo: Path, tool_name: str, when: str) -> None:
    _ = SessionEventRepository(
        RepositoryStorage(initialize_storage(repo))
    ).record_event(
        SessionEventWrite(
            project_id=PROJECT_ID,
            session_id=SESSION_ID,
            event_type="tool_called",
            tool_name=tool_name,
            payload={"query": "x"},
            created_at=when,
        ),
    )


def test_brief_reconstructs_in_flight_work_and_ledger(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _seed_finding(
        repo,
        SeedFinding(
            finding_id="fix-me",
            rule_id="python.todo_cluster",
            file_path="src/a.py",
            severity="warning",
            status=FindingStatus.OPEN.value,
        ),
    )
    _seed_finding(
        repo,
        SeedFinding(
            finding_id="done-pending",
            rule_id="python.dead_code_candidate",
            file_path="src/b.py",
            severity="info",
            status=FindingStatus.OPEN.value,
        ),
    )
    _touch(repo, "fix-me", FindingStatus.IN_PROGRESS)  # in-flight, not verified
    _verify(repo, "done-pending", exit_code=0)  # verified via the ledger
    _tool_event(repo, "plan_refactor", "2026-06-13T00:00:00+00:00")
    _tool_event(repo, "get_finding_context", "2026-06-13T00:00:01+00:00")

    brief = SessionResumeService(repo).resume_task(
        project_id=PROJECT_ID,
        session_id=SESSION_ID,
    )

    # In-flight finding ranks ahead of plain backlog and drives the brief.
    assert brief.active_findings[0]["id"] == "fix-me"
    assert brief.active_findings[0]["status"] == FindingStatus.IN_PROGRESS.value
    assert brief.status == "in_progress"
    assert brief.next_tools[0] == "get_finding_context:fix-me"
    assert "fix-me" in brief.summary
    # The verification ledger surfaces what's already proven.
    assert brief.verified_findings[0]["finding_id"] == "done-pending"
    assert brief.verified_findings[0]["command"].startswith("uv run pytest")
    # Recently touched files come from findings/ledger activity (both touched).
    assert set(brief.recently_touched_files) == {"src/a.py", "src/b.py"}
    # Recent tool trail is most-recent-first from sanitized session events.
    assert brief.recent_tools == ("get_finding_context", "plan_refactor")
    # No baseline accepted yet.
    assert brief.ratchet == {"baseline_accepted": False, "baseline_finding_count": 0}


def test_verified_open_finding_recommends_marking_resolved(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _seed_finding(
        repo,
        SeedFinding(
            finding_id="ready",
            rule_id="python.todo_cluster",
            file_path="src/ready.py",
            severity="warning",
            status=FindingStatus.OPEN.value,
        ),
    )
    _verify(repo, "ready", exit_code=0)

    brief = SessionResumeService(repo).resume_task(
        project_id=PROJECT_ID,
        session_id=SESSION_ID,
    )

    assert brief.status == "verified_unresolved"
    assert brief.next_tools[0] == "mark_finding:ready"
    assert "ready" in brief.summary


def test_empty_state_is_graceful(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()

    brief = SessionResumeService(repo).resume_task(
        project_id=PROJECT_ID,
        session_id="missing-session",
    )

    assert brief.session_id == "missing-session"
    assert brief.status == "nothing_in_progress"
    assert brief.active_findings == ()
    assert brief.verified_findings == ()
    assert brief.recently_touched_files == ()
    assert brief.recent_tools == ()
    assert brief.summary
    assert brief.next_tools == (
        "start_task",
        "get_next_improvement",
        "scan_code_health",
    )


def test_brief_is_bounded(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    overflow = ACTIVE_FINDING_LIMIT + VERIFIED_FINDING_LIMIT + 5
    for index in range(overflow):
        finding_id = f"f{index:02d}"
        _seed_finding(
            repo,
            SeedFinding(
                finding_id=finding_id,
                rule_id="python.todo_cluster",
                file_path=f"src/file_{index:02d}.py",
                severity="warning",
                status=FindingStatus.OPEN.value,
            ),
        )
        _verify(repo, finding_id, exit_code=0)  # touched + verified
        _tool_event(repo, f"tool_{index:02d}", f"2026-06-13T00:00:{index:02d}+00:00")

    brief = SessionResumeService(repo).resume_task(
        project_id=PROJECT_ID,
        session_id=SESSION_ID,
    )

    assert len(brief.active_findings) == ACTIVE_FINDING_LIMIT
    assert len(brief.verified_findings) == VERIFIED_FINDING_LIMIT
    assert len(brief.recently_touched_files) == TOUCHED_FILE_LIMIT
    assert len(brief.recent_tools) == RECENT_TOOL_LIMIT
    assert len(brief.next_tools) <= 6


def test_brief_reads_only_persisted_state_no_source(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _seed_finding(
        repo,
        SeedFinding(
            finding_id="leak-check",
            rule_id="python.todo_cluster",
            file_path="src/secret.py",
            severity="warning",
            status=FindingStatus.OPEN.value,
        ),
    )
    _touch(repo, "leak-check", FindingStatus.IN_PROGRESS)

    brief = SessionResumeService(repo).resume_task(
        project_id=PROJECT_ID,
        session_id=SESSION_ID,
    )
    serialized = json.dumps(
        {
            "active_findings": brief.active_findings,
            "verified_findings": brief.verified_findings,
            "recently_touched_files": brief.recently_touched_files,
        },
    )

    # Paths are fine; source content/ranges must never appear.
    assert "source_content" not in serialized
    assert "source_ranges" not in serialized
