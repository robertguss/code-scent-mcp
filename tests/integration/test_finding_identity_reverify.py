"""U24 .2/.3 -- fingerprint re-verification and edit-stable identity end-to-end.

.2: when a finding's stable_key persists but its evidence fingerprint (symbol
    body) changes, prior verification is invalidated; an unchanged fingerprint
    preserves it.
.3: a pure line shift preserves the finding's identity AND keeps the verification
    ledger + ratchet baseline attached (exercises the dead_code start_line/
    end_line position-key fix).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from codescent.core.models import MaintainabilityThresholds, ProjectConfig
from codescent.services.ci import CiService
from codescent.services.code_health import CodeHealthService
from codescent.services.config import ConfigService
from codescent.storage import RepositoryStorage, initialize_storage
from codescent.storage.repositories import FindingRepository

if TYPE_CHECKING:
    from pathlib import Path

    from codescent.engine.rules.model import CodeHealthFinding

STRICT = ProjectConfig(thresholds=MaintainabilityThresholds.strict())


def _repo(tmp_path: Path, source: str, *, name: str = "config.py") -> Path:
    repo = tmp_path / "repo"
    module = repo / "src" / "pkg" / name
    module.parent.mkdir(parents=True, exist_ok=True)
    _ = module.write_text(source)
    ConfigService(repo).save(STRICT)
    return repo


def _function_module(name: str, body_lines: int) -> str:
    body = "\n".join(f"    step_{index} = {index}" for index in range(body_lines))
    return f"def {name}() -> None:\n{body}\n"


def _repository(repo: Path) -> FindingRepository:
    return FindingRepository(RepositoryStorage(initialize_storage(repo)))


def _finding(
    findings: tuple[CodeHealthFinding, ...],
    rule_id: str,
    symbol: str | None = None,
) -> CodeHealthFinding:
    return next(
        finding
        for finding in findings
        if finding.rule_id == rule_id and (symbol is None or finding.symbol == symbol)
    )


def _baseline_keys(repo: Path) -> set[str]:
    state = initialize_storage(repo)
    with RepositoryStorage(state).read_connection() as connection:
        rows: list[tuple[str]] = connection.execute(
            "select stable_key from finding_baseline",
        ).fetchall()
    return {row[0] for row in rows}


def _has_stale_event(repo: Path, finding_id: str) -> bool:
    state = initialize_storage(repo)
    with RepositoryStorage(state).read_connection() as connection:
        rows: list[tuple[int]] = connection.execute(
            """
            select 1 from finding_events
            where finding_id = ? and event_type = 'verification_stale'
            """,
            (finding_id,),
        ).fetchall()
    return bool(rows)


def test_body_change_invalidates_recorded_verification(tmp_path: Path) -> None:
    repo = _repo(tmp_path, _function_module("process", 30))
    scan = CodeHealthService(repo).scan()
    finding_id = _finding(scan.findings, "python.large_function").id
    repository = _repository(repo)
    _ = repository.record_verification(
        finding_id,
        command="uv run pytest",
        exit_code=0,
        output_summary="passed",
    )
    assert repository.has_passing_verification(finding_id) is True

    # Grow the body: line_count changes (still over threshold). Identity holds
    # (line_count is excluded from stable_key) but the body genuinely changed.
    _ = (repo / "src" / "pkg" / "config.py").write_text(_function_module("process", 40))
    rescan = CodeHealthService(repo).scan()

    assert _finding(rescan.findings, "python.large_function").id == finding_id
    assert repository.has_passing_verification(finding_id) is False
    assert repository.list_verification_runs(finding_id) == ()
    assert _has_stale_event(repo, finding_id) is True


def test_unchanged_body_preserves_recorded_verification(tmp_path: Path) -> None:
    repo = _repo(tmp_path, _function_module("process", 30))
    scan = CodeHealthService(repo).scan()
    finding_id = _finding(scan.findings, "python.large_function").id
    repository = _repository(repo)
    _ = repository.record_verification(
        finding_id,
        command="uv run pytest",
        exit_code=0,
        output_summary="passed",
    )

    # Rescan with no edit at all.
    _ = CodeHealthService(repo).scan()

    assert repository.has_passing_verification(finding_id) is True
    assert _has_stale_event(repo, finding_id) is False


def test_identity_ledger_and_ratchet_survive_line_shift(tmp_path: Path) -> None:
    repo = _repo(
        tmp_path,
        "def orphaned_helper(values):\n    return sum(values)\n",
        name="util.py",
    )
    symbol = "pkg.util.orphaned_helper"
    scan = CodeHealthService(repo).scan()
    id_before = _finding(scan.findings, "python.dead_code_candidate", symbol).id
    repository = _repository(repo)
    _ = repository.record_verification(
        id_before,
        command="uv run pytest",
        exit_code=0,
        output_summary="reviewed: truly unreferenced",
    )
    _ = CiService(repo).update_baseline()
    assert id_before in _baseline_keys(repo)

    # Pure line shift: insert blank lines ABOVE the symbol.
    util = repo / "src" / "pkg" / "util.py"
    _ = util.write_text("\n\n\n\n\n" + util.read_text())

    report = CiService(repo).run(threshold="high", ratchet=True)
    dead_after = _finding(report.findings, "python.dead_code_candidate", symbol)
    id_after = dead_after.id

    stable = id_before == id_after
    # required id-before/id-after logging for the e2e
    print(f"[U24] before={id_before} after={id_after} stable={stable}")  # noqa: T201

    # Identity survived the line shift (the start_line/end_line fix).
    assert id_after == id_before
    # Verification ledger stayed attached.
    assert repository.has_passing_verification(id_after) is True
    # Ratchet baseline still covers it; the line shift produced no new finding.
    assert id_after in _baseline_keys(repo)
    assert id_after not in {summary.stable_key for summary in report.new_findings}
    assert report.new_finding_count == 0
    assert _has_stale_event(repo, id_after) is False
