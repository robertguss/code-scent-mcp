import sqlite3
from contextlib import closing
from pathlib import Path

from codescent.services.ci import ChangedFileSummary, CiService


def test_update_baseline_records_per_file_finding_counts(tmp_path: Path) -> None:
    repo = _repo_with_related_test(tmp_path)

    result = CiService(str(repo)).update_baseline()

    assert result.files_recorded == 2
    assert result.finding_count == 0
    assert _baseline_rows(repo) == (
        ("src/pkg/config.py", 0),
        ("tests/test_config.py", 0),
    )


def test_ratchet_flags_only_files_worse_than_baseline(tmp_path: Path) -> None:
    repo = _repo_with_related_test(tmp_path)
    service = CiService(str(repo))
    _ = service.update_baseline()

    _ = (repo / "src" / "pkg" / "config.py").write_text(_source_with_debt())

    default_report = service.run(threshold="high")
    ratchet_report = service.run(threshold="high", ratchet=True)

    assert default_report.ok is True
    assert default_report.ratchet_enabled is False
    assert default_report.ratchet_regressions == ()
    assert ratchet_report.ok is False
    assert ratchet_report.ratchet_enabled is True
    assert tuple(item.path for item in ratchet_report.ratchet_regressions) == (
        "src/pkg/config.py",
    )
    regression = ratchet_report.ratchet_regressions[0]
    assert regression.baseline_count == 0
    assert regression.finding_count > regression.baseline_count
    assert regression.regressed is True


def test_ratchet_allows_files_at_or_below_baseline(tmp_path: Path) -> None:
    repo = _repo_with_related_test(tmp_path)
    source = repo / "src" / "pkg" / "config.py"
    _ = source.write_text(_source_with_debt())
    service = CiService(str(repo))
    baseline = service.update_baseline()

    equal_report = service.run(threshold="high", ratchet=True)
    assert baseline.finding_count > 0
    assert equal_report.ok is True
    assert equal_report.ratchet_regressions == ()
    debt_summary = _summary_for(equal_report.changed_file_health, "src/pkg/config.py")
    assert debt_summary.baseline_count == debt_summary.finding_count
    assert debt_summary.regressed is False

    _ = source.write_text(
        """def load_config() -> str:
    return "ok"
""",
    )

    below_report = service.run(threshold="high", ratchet=True)
    assert below_report.ok is True
    assert below_report.ratchet_regressions == ()


def _repo_with_related_test(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    source = repo / "src" / "pkg" / "config.py"
    test = repo / "tests" / "test_config.py"
    source.parent.mkdir(parents=True)
    test.parent.mkdir(parents=True)
    _ = source.write_text(
        """def load_config() -> str:
    return "ok"
""",
    )
    _ = test.write_text(
        """from src.pkg.config import load_config


def test_load_config() -> None:
    assert load_config() == "ok"
""",
    )
    return repo


def _source_with_debt() -> str:
    return """STATUS = "pending-review"


def load_config() -> str:
    # TODO: split config
    # FIXME: preserve compatibility
    # HACK: keep old queue name
    return STATUS
"""


def _summary_for(
    summaries: tuple[ChangedFileSummary, ...],
    path: str,
) -> ChangedFileSummary:
    return next(summary for summary in summaries if summary.path == path)


def _baseline_rows(repo: Path) -> tuple[tuple[str, int], ...]:
    with closing(sqlite3.connect(repo / ".codescent" / "index.sqlite")) as connection:
        rows: list[tuple[str, int]] = connection.execute(
            """
            select file_path, finding_count
            from health_baseline
            order by file_path
            """,
        ).fetchall()
    return tuple(rows)
