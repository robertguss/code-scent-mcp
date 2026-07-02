import json
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from typing import cast

import pytest

import codescent.services.findings as findings_module
from codescent.core.models import (
    FindingStatus,
    MaintainabilityThresholds,
    ProjectConfig,
)
from codescent.mcp.finding_tools import list_findings
from codescent.services.code_health import CodeHealthService
from codescent.services.config import ConfigService
from codescent.services.findings import (
    MAX_VERIFICATION_OUTPUT_SUMMARY_CHARS,
    FindingsService,
)
from codescent.services.improvement_plan import ImprovementPlanService
from codescent.storage import RepositoryStorage, initialize_storage
from codescent.storage.repositories import FindingRepository


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


def test_non_code_finding_persists_resolvable_file_path(tmp_path: Path) -> None:
    # Regression: generic-pack findings fire on non-indexed files (docs/.md,
    # .html, .json), which have no `files` row, so file_id persisted NULL and
    # file_path read back empty -- which then crashed the snippet tools. The
    # path is now stored on the finding row and round-trips through the DB.
    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    _ = (repo / "src" / "app.py").write_text("VALUE = 1\n")
    _ = (repo / "NOTES.md").write_text(
        "# notes\n" + "\n".join(f"line {index}" for index in range(400)),
    )
    ConfigService(repo).save(
        ProjectConfig(thresholds=MaintainabilityThresholds.strict()),
    )
    _ = CodeHealthService(repo).scan()

    repository = FindingRepository(RepositoryStorage(initialize_storage(repo)))
    generic = [
        finding
        for finding in repository.list_findings()
        if finding.rule_id.startswith("generic.")
    ]
    assert generic, "expected a generic-pack finding on the non-code file"
    assert all(finding.file_path for finding in generic), (
        "a non-code finding lost its file_path on the DB round-trip"
    )
    assert any(finding.file_path == "NOTES.md" for finding in generic)


def test_finding_repository_records_verification_runs(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    finding_id = "needs-evidence"
    _seed_open_finding(
        repo,
        SeedFinding(
            finding_id=finding_id,
            rule_id="python.todo_cluster",
            file_path="src/pkg/config.py",
            severity="warning",
            line_count=10,
        ),
    )
    repository = FindingRepository(RepositoryStorage(initialize_storage(repo)))

    failed = repository.record_verification(
        finding_id,
        command="uv run pytest tests/unit/test_config.py",
        exit_code=1,
        output_summary="1 failed",
    )
    passing_after_failure = repository.has_passing_verification(finding_id)
    passed = repository.record_verification(
        finding_id,
        command="uv run pytest tests/unit/test_config.py",
        exit_code=0,
        output_summary="1 passed",
    )
    runs = repository.list_verification_runs(finding_id)

    assert passing_after_failure is False
    assert repository.has_passing_verification(finding_id) is True
    assert runs == (failed, passed)
    assert runs[0].output_summary == "1 failed"
    assert runs[1].exit_code == 0
    assert all(run.created_at for run in runs)


def test_mark_finding_gates_resolved_without_verification(tmp_path: Path) -> None:
    repo = _repo_with_todo(tmp_path)
    scan = CodeHealthService(repo).scan()
    finding_id = scan.finding_ids[0]
    service = FindingsService(repo)

    marked = service.mark_finding(
        finding_id,
        FindingStatus.RESOLVED,
        note="fixed locally",
    )
    detail = service.get_smell_report().findings[0]
    event_details = cast(
        "dict[str, str]",
        json.loads(detail.events[-1].details_json),
    )

    assert marked.gated is True
    assert marked.requested_status is FindingStatus.RESOLVED
    assert marked.applied_status is FindingStatus.NEEDS_REVIEW
    assert marked.status is FindingStatus.NEEDS_REVIEW
    assert "passing verification" in marked.message
    assert event_details["status"] == FindingStatus.NEEDS_REVIEW.value
    assert "fixed locally" in event_details["note"]


def test_mark_finding_allows_resolved_with_passing_verification(
    tmp_path: Path,
) -> None:
    repo = _repo_with_todo(tmp_path)
    scan = CodeHealthService(repo).scan()
    finding_id = scan.finding_ids[0]
    _record_passing_verification(repo, finding_id)

    marked = FindingsService(repo).mark_finding(
        finding_id,
        FindingStatus.RESOLVED,
        note="verified",
    )

    assert marked.gated is False
    assert marked.requested_status is FindingStatus.RESOLVED
    assert marked.applied_status is FindingStatus.RESOLVED
    assert _finding_lifecycle(repo, finding_id) == (FindingStatus.RESOLVED.value, True)


def test_record_verification_bounds_summary_and_enables_resolution(
    tmp_path: Path,
) -> None:
    repo = _repo_with_todo(tmp_path)
    scan = CodeHealthService(repo).scan()
    finding_id = scan.finding_ids[0]
    service = FindingsService(repo)
    output_summary = "x" * (MAX_VERIFICATION_OUTPUT_SUMMARY_CHARS + 25)

    recorded = service.record_verification(
        finding_id,
        command="uv run pytest tests/integration/test_findings.py",
        exit_code=0,
        output_summary=output_summary,
    )
    marked = service.mark_finding(
        finding_id,
        FindingStatus.RESOLVED,
        note="verified",
    )
    runs = FindingRepository(
        RepositoryStorage(initialize_storage(repo)),
    ).list_verification_runs(finding_id)

    assert recorded.output_truncated is True
    assert len(recorded.output_summary) == MAX_VERIFICATION_OUTPUT_SUMMARY_CHARS
    assert runs == (recorded.verification,)
    assert marked.gated is False
    assert marked.status is FindingStatus.RESOLVED


def test_rescan_preserves_resolved_or_marks_regressed(tmp_path: Path) -> None:
    repo = _repo_with_todo(tmp_path)
    scan = CodeHealthService(repo).scan()
    finding_id = scan.finding_ids[0]
    service = FindingsService(repo)
    _record_passing_verification(repo, finding_id)

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
    _record_passing_verification(repo, finding_id)

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

CONFIG = load_config()
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


def test_backlog_progress_and_regressions_survive_rescan(tmp_path: Path) -> None:
    repo = _repo_with_todo(tmp_path)
    scan = CodeHealthService(repo).scan()
    finding_id = scan.finding_ids[0]
    service = FindingsService(repo)
    _record_passing_verification(repo, finding_id)

    _ = service.mark_finding(finding_id, FindingStatus.RESOLVED, note="fixed")
    rescan = service.rescan()
    backlog = service.get_backlog()
    progress = service.get_progress()
    regressions = service.get_regressions()

    assert finding_id in rescan.regressed_finding_ids
    assert finding_id in regressions.finding_ids
    assert backlog.status_counts[FindingStatus.REGRESSED.value] == 1
    assert progress.total_findings == scan.findings_created
    assert progress.resolved_count == 1
    assert progress.regressed_count == 1


def test_next_improvement_uses_hotspot_tiebreak(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = tmp_path / "repo"
    _seed_open_finding(
        repo,
        SeedFinding(
            finding_id="cold",
            rule_id="python.todo_cluster",
            file_path="src/cold.py",
            severity="info",
            line_count=200,
        ),
    )
    _seed_open_finding(
        repo,
        SeedFinding(
            finding_id="hot",
            rule_id="python.todo_cluster",
            file_path="src/hot.py",
            severity="info",
            line_count=25,
        ),
    )

    def change_counts(_repo_root: Path) -> dict[str, int]:
        return {"src/cold.py": 1, "src/hot.py": 10}

    monkeypatch.setattr(
        findings_module,
        "git_change_counts",
        change_counts,
    )

    next_improvement = FindingsService(repo).get_next_improvement()

    assert next_improvement is not None
    assert next_improvement.id == "hot"


def test_next_improvement_preserves_severity_and_rule_priority(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = tmp_path / "repo"
    _seed_open_finding(
        repo,
        SeedFinding(
            finding_id="hot-info",
            rule_id="python.todo_cluster",
            file_path="src/hot_info.py",
            severity="info",
            line_count=100,
        ),
    )
    _seed_open_finding(
        repo,
        SeedFinding(
            finding_id="cold-warning",
            rule_id="python.todo_cluster",
            file_path="src/cold_warning.py",
            severity="warning",
            line_count=1,
        ),
    )

    def severity_change_counts(_repo_root: Path) -> dict[str, int]:
        return {"src/hot_info.py": 100, "src/cold_warning.py": 1}

    monkeypatch.setattr(
        findings_module,
        "git_change_counts",
        severity_change_counts,
    )

    severity_next = FindingsService(repo).get_next_improvement()

    assert severity_next is not None
    assert severity_next.id == "cold-warning"

    repo = tmp_path / "rule-repo"
    _seed_open_finding(
        repo,
        SeedFinding(
            finding_id="hot-lower-rule",
            rule_id="python.changed_source_without_related_test",
            file_path="src/hot_lower_rule.py",
            severity="info",
            line_count=100,
        ),
    )
    _seed_open_finding(
        repo,
        SeedFinding(
            finding_id="cold-higher-rule",
            rule_id="python.todo_cluster",
            file_path="src/cold_higher_rule.py",
            severity="info",
            line_count=1,
        ),
    )

    def rule_change_counts(_repo_root: Path) -> dict[str, int]:
        return {
            "src/hot_lower_rule.py": 100,
            "src/cold_higher_rule.py": 1,
        }

    monkeypatch.setattr(
        findings_module,
        "git_change_counts",
        rule_change_counts,
    )

    rule_next = FindingsService(repo).get_next_improvement()

    assert rule_next is not None
    assert rule_next.id == "cold-higher-rule"


def test_next_improvement_prefers_source_over_test_structural(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _seed_open_finding(
        repo,
        SeedFinding(
            finding_id="src-large",
            rule_id="python.large_file",
            file_path="src/big.py",
            severity="warning",
            line_count=200,
        ),
    )
    _seed_open_finding(
        repo,
        SeedFinding(
            finding_id="test-large",
            rule_id="python.large_file",
            file_path="tests/test_big.py",
            severity="warning",
            line_count=400,
        ),
    )

    next_improvement = FindingsService(repo).get_next_improvement()

    assert next_improvement is not None
    assert next_improvement.id == "src-large"


def test_next_improvement_empty_when_only_test_structural(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _seed_open_finding(
        repo,
        SeedFinding(
            finding_id="test-large",
            rule_id="python.large_file",
            file_path="tests/test_big.py",
            severity="warning",
            line_count=400,
        ),
    )

    assert FindingsService(repo).get_next_improvement() is None


def test_next_improvement_agrees_with_improvement_plan_top_item(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    _seed_open_finding(
        repo,
        SeedFinding(
            finding_id="src-dup",
            rule_id="python.duplicate_literal",
            file_path="src/pkg/config.py",
            severity="warning",
            line_count=50,
        ),
    )
    _seed_open_finding(
        repo,
        SeedFinding(
            finding_id="test-large",
            rule_id="python.large_file",
            file_path="tests/test_big.py",
            severity="warning",
            line_count=400,
        ),
    )

    next_improvement = FindingsService(repo).get_next_improvement()
    plan = ImprovementPlanService(repo).get_improvement_plan()

    assert next_improvement is not None
    # get_next_improvement and the plan's top ROI cluster agree on the item...
    assert next_improvement.id in plan.clusters[0].finding_ids
    # ...and the structural test cluster is deprioritized to the bottom.
    assert plan.clusters[-1].rule_id == "python.large_file"
    assert plan.clusters[-1].scope.startswith("tests")


@dataclass(frozen=True, slots=True)
class SeedFinding:
    finding_id: str
    rule_id: str
    file_path: str
    severity: str
    line_count: int


def test_backlog_status_counts_describe_only_the_returned_rows(tmp_path: Path) -> None:
    repo = _repo_with_todo(tmp_path)
    scan = CodeHealthService(repo).scan()
    _ = FindingsService(repo).mark_finding(
        scan.finding_ids[0],
        FindingStatus.WONTFIX,
    )

    payload = list_findings(str(repo), status="backlog")

    # wontfix is filtered out of the backlog, so it must not be counted in the
    # payload's status_counts (which describe only the matched rows).
    assert "wontfix" not in payload["status_counts"]
    assert sum(payload["status_counts"].values()) == payload["total_count"]


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

CONFIG = load_config()
""",
    )
    ConfigService(repo).save(
        ProjectConfig(thresholds=MaintainabilityThresholds.strict()),
    )
    return repo


def _seed_open_finding(
    repo: Path,
    finding: SeedFinding,
) -> None:
    repo.mkdir(parents=True, exist_ok=True)
    state = initialize_storage(repo)
    storage = RepositoryStorage(state)
    with storage.write_transaction() as connection:
        _ = connection.execute(
            """
            insert or ignore into scan_runs (
                id,
                started_at,
                completed_at,
                index_version,
                rule_version,
                files_scanned,
                findings_created,
                findings_resolved,
                status
            ) values ('scan', '2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z',
                1, 'test', 0, 0, 0, 'complete')
            """,
        )
        cursor = connection.execute(
            """
            insert into files (
                path,
                language,
                hash,
                size_bytes,
                line_count,
                is_generated,
                is_test
            ) values (?, 'python', ?, 1, ?, 0, 0)
            """,
            (finding.file_path, finding.finding_id, finding.line_count),
        )
        file_id = cursor.lastrowid
        _ = connection.execute(
            """
            insert into findings (
                id,
                stable_key,
                rule_id,
                file_id,
                severity,
                confidence,
                status,
                title,
                message,
                evidence_json,
                suggested_action,
                first_seen_scan_id,
                last_seen_scan_id
            ) values (?, ?, ?, ?, ?, 0.8, 'open', ?, ?, ?, '', 'scan', 'scan')
            """,
            (
                finding.finding_id,
                f"{finding.rule_id}:{finding.file_path}:{finding.finding_id}",
                finding.rule_id,
                file_id,
                finding.severity,
                finding.finding_id,
                finding.finding_id,
                json.dumps({"line_count": finding.line_count}),
            ),
        )


def _finding_lifecycle(repo: Path, finding_id: str) -> tuple[str, bool]:
    with closing(sqlite3.connect(repo / ".codescent" / "index.sqlite")) as connection:
        rows: list[tuple[str, str | None]] = connection.execute(
            "select status, resolved_at from findings where id = ?",
            (finding_id,),
        ).fetchall()
    assert len(rows) == 1
    row = rows[0]
    return (row[0], row[1] is not None)


def _record_passing_verification(repo: Path, finding_id: str) -> None:
    repository = FindingRepository(RepositoryStorage(initialize_storage(repo)))
    _ = repository.record_verification(
        finding_id,
        command="uv run pytest tests/integration/test_findings.py",
        exit_code=0,
        output_summary="focused tests passed",
    )
