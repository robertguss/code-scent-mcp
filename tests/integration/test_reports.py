from pathlib import Path

from codescent.core.models import FindingStatus
from codescent.services.code_health import CodeHealthService
from codescent.services.findings import FindingsService
from codescent.services.reports import ReportService


def test_report_service_returns_finding_detail_with_evidence_and_history(
    tmp_path: Path,
) -> None:
    repo = _repo_with_todo(tmp_path)
    scan = CodeHealthService(repo).scan()
    finding_id = next(
        item for item in scan.finding_ids if item.startswith("python.todo_cluster")
    )
    _ = FindingsService(repo).mark_finding(
        finding_id,
        FindingStatus.IN_PROGRESS,
        note="owner accepted",
    )

    detail = ReportService(repo).get_finding(finding_id)

    assert detail.finding_id == finding_id
    assert detail.rule_id == "python.todo_cluster"
    assert detail.status == FindingStatus.IN_PROGRESS.value
    assert detail.evidence["count"] == 3
    assert detail.status_history[-1]["event_type"] == "status_changed"
    assert detail.score_inputs["severity"] == "info"
    assert detail.score_inputs["confidence"] == 0.9
    assert "SECRET_SENTINEL" not in str(detail)


def _repo_with_todo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    source = repo / "src" / "pkg" / "config.py"
    source.parent.mkdir(parents=True)
    _ = source.write_text(
        """SECRET_SENTINEL = "do not leak"
STATUS = "pending-review"
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
