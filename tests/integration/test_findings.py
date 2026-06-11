import sqlite3
from contextlib import closing
from pathlib import Path

from codescent.core.models import FindingStatus
from codescent.services.code_health import CodeHealthService
from codescent.services.findings import FindingsService


def test_mark_finding_persists_status(tmp_path: Path) -> None:
    repo = _repo_with_todo(tmp_path)
    scan = CodeHealthService(repo).scan()
    finding_id = scan.finding_ids[0]

    marked = FindingsService(repo).mark_finding(
        finding_id,
        FindingStatus.IN_PROGRESS,
        note="owner accepted",
    )
    report = FindingsService(repo).get_smell_report()

    assert marked.status is FindingStatus.IN_PROGRESS
    assert report.open_count == scan.findings_created - 1
    assert report.status_counts[FindingStatus.IN_PROGRESS.value] == 1
    assert report.findings[0].events[-1].event_type == "status_changed"


def test_rescan_preserves_resolved_or_marks_regressed(tmp_path: Path) -> None:
    repo = _repo_with_todo(tmp_path)
    scan = CodeHealthService(repo).scan()
    finding_id = scan.finding_ids[0]
    service = FindingsService(repo)

    _ = service.mark_finding(finding_id, FindingStatus.RESOLVED, note="fixed")
    rescan = service.rescan()
    report = service.get_smell_report()

    assert rescan.status == "complete"
    assert finding_id in rescan.regressed_finding_ids
    regressed = next(finding for finding in report.findings if finding.id == finding_id)
    assert regressed.status is FindingStatus.REGRESSED
    assert regressed.events[-1].event_type == "regressed"


def test_regressed_finding_clears_resolved_timestamp(tmp_path: Path) -> None:
    repo = _repo_with_todo(tmp_path)
    scan = CodeHealthService(repo).scan()
    finding_id = scan.finding_ids[0]
    service = FindingsService(repo)

    _ = service.mark_finding(finding_id, FindingStatus.RESOLVED, note="fixed")
    before = _finding_lifecycle(repo, finding_id)
    _ = service.rescan()
    after = _finding_lifecycle(repo, finding_id)

    assert before == (FindingStatus.RESOLVED.value, True)
    assert after == (FindingStatus.REGRESSED.value, False)


def test_rescan_marks_absent_open_findings_resolved(tmp_path: Path) -> None:
    repo = _repo_with_todo(tmp_path)
    source = repo / "src" / "pkg" / "config.py"
    initial_scan = CodeHealthService(repo).scan()

    _ = source.write_text(
        """def load_config() -> str:
    return "ok"
""",
    )
    rescan = FindingsService(repo).rescan()
    report = FindingsService(repo).get_smell_report()
    resolved_rule_ids = {
        finding.rule_id
        for finding in report.findings
        if finding.status is FindingStatus.RESOLVED
    }
    original_rule_ids = {
        finding.rule_id
        for finding in initial_scan.findings
        if finding.rule_id != "python.changed_source_without_related_test"
    }
    resolved_ids = {
        finding.id
        for finding in report.findings
        if finding.status is FindingStatus.RESOLVED
    }

    assert rescan.scan.findings_resolved == 2
    assert original_rule_ids == resolved_rule_ids
    assert len(resolved_ids) == 2


def test_rescan_preserves_file_paths_for_existing_findings(tmp_path: Path) -> None:
    repo = _repo_with_todo(tmp_path)
    _ = CodeHealthService(repo).scan()

    _ = FindingsService(repo).rescan()
    report = FindingsService(repo).get_smell_report()
    todo = next(
        finding
        for finding in report.findings
        if finding.rule_id == "python.todo_cluster"
    )

    assert todo.file_path == "src/pkg/config.py"


def _repo_with_todo(tmp_path: Path) -> Path:
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
""",
    )
    return repo


def _finding_lifecycle(repo: Path, finding_id: str) -> tuple[str, bool]:
    with closing(sqlite3.connect(repo / ".codescent" / "index.sqlite")) as connection:
        rows: list[tuple[str, str | None]] = connection.execute(
            "select status, resolved_at from findings where id = ?",
            (finding_id,),
        ).fetchall()
    assert len(rows) == 1
    row = rows[0]
    return (row[0], row[1] is not None)
