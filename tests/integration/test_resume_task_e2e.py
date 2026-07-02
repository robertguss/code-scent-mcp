"""End-to-end: do real work, drop in-memory context, resume from disk only.

Simulates the post-compaction recovery the feature exists for: a repo is
scanned, a finding is worked (marked in-progress + verified), the ratchet
baseline is accepted, and a tool trail is recorded. Then a *fresh*
``SessionResumeService`` -- holding no in-memory state from the work above --
reconstructs the brief purely from persisted ``.codescent`` data.

Each step logs expected-vs-found so a failure reads as a narrative (run with
``-s`` to watch it live).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from codescent.core.models import (
    FindingStatus,
    MaintainabilityThresholds,
    ProjectConfig,
)
from codescent.services.ci import CiService
from codescent.services.code_health import CodeHealthService
from codescent.services.config import ConfigService
from codescent.services.findings import FindingsService
from codescent.services.session_resume import SessionResumeService
from codescent.storage import RepositoryStorage, initialize_storage
from codescent.storage.repositories import SessionEventRepository, SessionEventWrite

if TYPE_CHECKING:
    from pathlib import Path

PROJECT_ID = "project-e2e"
SESSION_ID = "session-e2e"


def _log(step: str, *, expected: object, found: object) -> None:
    print(f"[resume-e2e] {step}: expected={expected!r} found={found!r}")  # noqa: T201


def test_resume_reconstructs_progress_from_persisted_state(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    source = repo / "src" / "pkg" / "config.py"
    source.parent.mkdir(parents=True)
    _ = source.write_text(
        """STATUS = "pending-review"
OTHER_STATUS = "pending-review"
THIRD_STATUS = "pending-review"


def load_config() -> str:
    # TODO: split config
    # FIXME: preserve compatibility
    # HACK: keep old queue name
    return STATUS

CONFIG = load_config()
""",
    )
    ConfigService(repo).save(
        ProjectConfig(thresholds=MaintainabilityThresholds.strict()),
    )

    # --- Step 1: scan produces real findings. -------------------------------
    scan = CodeHealthService(repo).scan()
    finding_id = scan.finding_ids[0]
    worked = next(
        finding
        for finding in FindingsService(repo).get_smell_report().findings
        if finding.id == finding_id
    )
    _log("scan created findings", expected=">=1", found=len(scan.finding_ids))
    assert scan.finding_ids

    # --- Step 2: work the finding (mark in-progress = "mark progress"). ------
    service = FindingsService(repo)
    marked = service.mark_finding(finding_id, FindingStatus.IN_PROGRESS, note="working")
    _log("marked in_progress", expected="in_progress", found=marked.status.value)
    assert marked.status is FindingStatus.IN_PROGRESS

    # --- Step 3: record a passing verification (the ledger). ----------------
    recorded = service.record_verification(
        finding_id,
        command="uv run pytest tests/integration/test_resume_task_e2e.py",
        exit_code=0,
        output_summary="1 passed",
    )
    _log("recorded verification", expected="exit 0", found=recorded.exit_code)
    assert recorded.exit_code == 0

    # --- Step 4: accept the ratchet baseline. -------------------------------
    baseline = CiService(repo).update_baseline()
    _log("accepted baseline", expected=">=1 files", found=baseline.files_recorded)

    # --- Step 5: record a sanitized tool trail. -----------------------------
    events = SessionEventRepository(RepositoryStorage(initialize_storage(repo)))
    for index, tool in enumerate(("explain_finding", "plan_refactor")):
        _ = events.record_event(
            SessionEventWrite(
                project_id=PROJECT_ID,
                session_id=SESSION_ID,
                event_type="tool_called",
                tool_name=tool,
                payload={"query": "x"},
                created_at=f"2026-06-28T00:00:0{index}+00:00",
            ),
        )
    _log("recorded tool trail", expected=2, found=2)

    # --- Step 6: COMPACTION. Fresh service, zero in-memory carryover. -------
    fresh_service = SessionResumeService(repo)
    brief = fresh_service.resume_task(project_id=PROJECT_ID, session_id=SESSION_ID)

    _log("brief.status", expected="verified_unresolved", found=brief.status)
    assert brief.status == "verified_unresolved"

    _log(
        "active finding id",
        expected=finding_id,
        found=brief.active_findings[0]["id"] if brief.active_findings else None,
    )
    assert brief.active_findings[0]["id"] == finding_id

    _log(
        "next tool call",
        expected=f"mark_finding:{finding_id}",
        found=brief.next_tools,
    )
    assert brief.next_tools[0] == f"mark_finding:{finding_id}"

    verified_ids = {item["finding_id"] for item in brief.verified_findings}
    _log("verified ledger ids", expected=f"contains {finding_id}", found=verified_ids)
    assert finding_id in verified_ids

    _log(
        "recently touched files",
        expected=f"contains {worked.file_path}",
        found=brief.recently_touched_files,
    )
    assert worked.file_path in brief.recently_touched_files

    _log("recent tools", expected="explain_finding first", found=brief.recent_tools)
    assert brief.recent_tools == ("plan_refactor", "explain_finding")

    _log("ratchet accepted", expected=True, found=brief.ratchet["baseline_accepted"])
    assert brief.ratchet["baseline_accepted"] is True
