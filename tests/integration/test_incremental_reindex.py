from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, cast

from typer.testing import CliRunner

from codescent.cli.main import app
from codescent.services.repo_index import RepoIndexService
from codescent.storage import RepositoryStorage, initialize_storage

if TYPE_CHECKING:
    from pathlib import Path

    from _pytest.logging import LogCaptureFixture

logger = logging.getLogger(__name__)
RUNNER = CliRunner()

FilesRow = tuple[str, str, str, int, int, int, int]
SymbolRow = tuple[str, str, str, str, int, int, float]
ImportRow = tuple[str, str, str | None, float]
RefRow = tuple[str, str, int, int, float]
CallRow = tuple[str, str, int, float]
Snapshot = tuple[
    list[FilesRow],
    list[SymbolRow],
    list[ImportRow],
    list[RefRow],
    list[CallRow],
]

APP_PY = """from helper import send


def run() -> None:
    send()
"""
APP_PY_V2 = """from helper import send


def run() -> None:
    send()
    send()
"""
HELPER_PY = """def helper_fn() -> int:
    return 1
"""
GONE_PY = """def gone() -> int:
    return 0
"""


def _snapshot(repo: Path) -> Snapshot:
    """Content-keyed index snapshot (excludes volatile id/timestamp/git_status)."""
    state = initialize_storage(repo)
    with RepositoryStorage(state).read_connection() as connection:
        files: list[FilesRow] = connection.execute(
            """
            select path, language, hash, size_bytes, line_count,
                   is_generated, is_test
            from files
            order by path
            """,
        ).fetchall()
        symbols: list[SymbolRow] = connection.execute(
            """
            select f.path, s.name, s.qualified_name, s.kind,
                   s.start_line, s.end_line, s.confidence
            from symbols s join files f on f.id = s.file_id
            order by f.path, s.qualified_name, s.start_line
            """,
        ).fetchall()
        imports: list[ImportRow] = connection.execute(
            """
            select f.path, i.imported_path, i.imported_symbol, i.confidence
            from imports i join files f on f.id = i.source_file_id
            order by f.path, i.imported_path, i.imported_symbol
            """,
        ).fetchall()
        refs: list[RefRow] = connection.execute(
            """
            select f.path, r.reference_text, r.start_line, r.end_line, r.confidence
            from symbol_references r join files f on f.id = r.source_file_id
            order by f.path, r.reference_text, r.start_line
            """,
        ).fetchall()
        calls: list[CallRow] = connection.execute(
            """
            select f.path, c.call_text, c.start_line, c.confidence
            from call_edges c join files f on f.id = c.source_file_id
            order by f.path, c.call_text, c.start_line
            """,
        ).fetchall()
    return (files, symbols, imports, refs, calls)


def _orphan_count(repo: Path) -> int:
    state = initialize_storage(repo)
    with RepositoryStorage(state).read_connection() as connection:
        row = cast(
            "tuple[int]",
            connection.execute(
                """
                select
                  (select count(*) from symbols
                     where file_id not in (select id from files))
                  + (select count(*) from imports
                       where source_file_id not in (select id from files))
                  + (select count(*) from symbol_references
                       where source_file_id not in (select id from files))
                  + (select count(*) from call_edges
                       where source_file_id not in (select id from files))
                """,
            ).fetchone(),
        )
    return row[0]


def _seed_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    src = repo / "src"
    src.mkdir(parents=True)
    _ = (src / "app.py").write_text(APP_PY)
    _ = (src / "helper.py").write_text(HELPER_PY)
    _ = (src / "gone.py").write_text(GONE_PY)
    return repo


def test_modify_one_file_reprocesses_only_it(tmp_path: Path) -> None:
    repo = _seed_repo(tmp_path)
    _ = RepoIndexService(repo).index_repo(full=True)

    _ = (repo / "src" / "app.py").write_text(APP_PY_V2)
    result = RepoIndexService(repo).index_repo()

    assert result.changed_files == ("src/app.py",)
    assert result.reindexed_files == 1
    assert result.deleted_files == ()
    assert result.full is False


def test_no_op_reindex_has_empty_delta(tmp_path: Path) -> None:
    repo = _seed_repo(tmp_path)
    _ = RepoIndexService(repo).index_repo(full=True)

    result = RepoIndexService(repo).index_repo()

    assert result.changed_files == ()
    assert result.reindexed_files == 0
    assert result.deleted_files == ()


def test_deleted_file_is_removed_with_cascade(tmp_path: Path) -> None:
    repo = _seed_repo(tmp_path)
    _ = RepoIndexService(repo).index_repo(full=True)

    (repo / "src" / "gone.py").unlink()
    result = RepoIndexService(repo).index_repo()

    assert result.deleted_files == ("src/gone.py",)
    assert result.reindexed_files == 0
    files, *_ = _snapshot(repo)
    assert all(row[0] != "src/gone.py" for row in files)
    # FK on-delete-cascade must leave no orphan graph rows behind.
    assert _orphan_count(repo) == 0


def test_full_flag_reprocesses_every_file(tmp_path: Path) -> None:
    repo = _seed_repo(tmp_path)
    _ = RepoIndexService(repo).index_repo()

    result = RepoIndexService(repo).index_repo(full=True)

    assert result.full is True
    assert result.reindexed_files == result.indexed_files == 3


def test_cli_full_flag_reports_full_mode(tmp_path: Path) -> None:
    repo = _seed_repo(tmp_path)
    invocation = RUNNER.invoke(
        app,
        ["index", "--repo", str(repo), "--full", "--json"],
    )

    assert invocation.exit_code == 0
    payload = cast("dict[str, object]", json.loads(invocation.output))
    assert payload["full"] is True
    assert payload["reindexed_files"] == payload["indexed_files"] == 3


def test_incremental_equals_full_e2e(
    tmp_path: Path,
    caplog: LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO)
    repo = _seed_repo(tmp_path)

    baseline = RepoIndexService(repo).index_repo(full=True)
    logger.info(
        "baseline full index: indexed=%d reprocessed=%d",
        baseline.indexed_files,
        baseline.reindexed_files,
    )

    # Mutate N=3 files: modify one, add one, delete one.
    _ = (repo / "src" / "app.py").write_text(APP_PY_V2)
    _ = (repo / "src" / "added.py").write_text("X = 1\n")
    (repo / "src" / "gone.py").unlink()

    incremental = RepoIndexService(repo).index_repo()
    logger.info(
        "incremental reindex: changed=%s deleted=%s reprocessed=%d",
        incremental.changed_files,
        incremental.deleted_files,
        incremental.reindexed_files,
    )
    snapshot_incremental = _snapshot(repo)

    fresh_full = RepoIndexService(repo).index_repo(full=True)
    logger.info("fresh full reindex: reprocessed=%d", fresh_full.reindexed_files)
    snapshot_full = _snapshot(repo)

    # Only the changed/added files were reprocessed; deleted file gone.
    assert set(incremental.changed_files) == {"src/app.py", "src/added.py"}
    assert incremental.reindexed_files == len(incremental.changed_files) == 2
    assert incremental.deleted_files == ("src/gone.py",)
    # The incremental index is byte-for-byte equivalent to a fresh full reindex.
    assert snapshot_incremental == snapshot_full
    assert _orphan_count(repo) == 0
    messages = [record.getMessage() for record in caplog.records]
    assert any("incremental reindex" in message for message in messages)
