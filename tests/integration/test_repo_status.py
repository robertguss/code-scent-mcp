"""get_repo_status: coordinated reads + honest stale-path wording (bead P3.5 / U5).

Reads go through the RepositoryStorage reader lock (no raw sqlite3 in the
transport layer); the unresolved-finding signal keys on an empty file_path (not
file_id) and its warning no longer conflates itself with index freshness.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from codescent.mcp.repo_tools import get_repo_status
from codescent.services.code_health import CodeHealthService
from codescent.storage import RepositoryStorage, state_for
from codescent.storage.repositories import FindingRepository, IndexStatusRepository

if TYPE_CHECKING:
    from pathlib import Path


def _repo_with_findings(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    (repo / "pkg").mkdir(parents=True)
    body = "\n".join(f"    x{i} = {i}" for i in range(60))
    source = f"def big() -> int:\n{body}\n    return 0\n"
    _ = (repo / "pkg" / "mod.py").write_text(source)
    _ = CodeHealthService(repo).scan()
    return repo


def test_no_database_reports_zeros_without_warnings(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()

    status = get_repo_status(str(repo))

    assert status["ok"] is True
    assert status["database_ok"] is False
    assert status["indexed_files"] == 0
    assert status["finding_count"] == 0
    assert status["unresolved_finding_count"] == 0
    assert status["warnings"] == ()


def test_scanned_repo_is_clean_with_resolvable_paths(tmp_path: Path) -> None:
    repo = _repo_with_findings(tmp_path)

    status = get_repo_status(str(repo))

    assert status["database_ok"] is True
    assert status["indexed_files"] >= 1
    assert status["finding_count"] >= 1
    # Freshly scanned findings all carry a file_path -> none unresolved.
    assert status["unresolved_finding_count"] == 0
    assert status["index_fresh"] is True
    assert status["warnings"] == ()


def test_unresolved_keys_on_empty_file_path_not_file_id(tmp_path: Path) -> None:
    repo = _repo_with_findings(tmp_path)
    storage = RepositoryStorage(state_for(repo))
    ids = [row.id for row in FindingRepository(storage).list_findings()]
    assert len(ids) >= 2

    with storage.write_transaction() as connection:
        # One finding loses its persisted path (predates the file_path fix).
        _ = connection.execute(
            "update findings set file_path = '', status = 'open' where id = ?",
            (ids[0],),
        )
        # Another keeps its path but has no file row (a by-design doc/generic
        # finding) -- it must NOT be flagged.
        _ = connection.execute(
            "update findings set file_id = null, status = 'open' where id = ?",
            (ids[1],),
        )

    assert IndexStatusRepository(storage).unresolved_finding_count() == 1


def test_stale_path_warning_wording_is_honest_and_independent(tmp_path: Path) -> None:
    repo = _repo_with_findings(tmp_path)
    storage = RepositoryStorage(state_for(repo))
    ids = [row.id for row in FindingRepository(storage).list_findings()]
    with storage.write_transaction() as connection:
        _ = connection.execute(
            "update findings set file_path = '', status = 'open' where id = ?",
            (ids[0],),
        )

    status = get_repo_status(str(repo))

    assert status["unresolved_finding_count"] == 1
    warning = status["warnings"][0]
    # The misleading "(stale index)" wording is gone; the message names the
    # real cause and the fix.
    assert "stale index" not in warning
    assert "rescan" in warning.lower()
    # The warning and index_fresh are independent: the index is still fresh
    # even though these paths need re-persisting.
    assert status["index_fresh"] is True
