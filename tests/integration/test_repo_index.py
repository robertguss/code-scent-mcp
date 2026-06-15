import subprocess
from pathlib import Path
from shutil import which

from codescent.services.repo_index import RepoIndexService
from codescent.services.status import RepoStatusService
from codescent.services.symbols import (
    read_persisted_file_symbols,
    read_persisted_symbol,
    read_persisted_symbols,
)
from codescent.storage import RepositoryStorage, initialize_storage


def test_index_persists_files_and_freshness(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    source = repo / "src" / "app.py"
    source.parent.mkdir(parents=True)
    _ = source.write_text("value = 1\n")
    _ = initialize_storage(repo)

    result = RepoIndexService(repo).index_repo()
    status = RepoStatusService(repo).get_status()

    assert result.indexed_files == 1
    assert result.changed_files == ("src/app.py",)
    assert status.index_fresh is True
    assert status.indexed_files == 1
    fresh_status = RepoStatusService(repo).get_status()

    assert fresh_status.indexed_files == 1
    assert result.file_hashes["src/app.py"]


def test_reindex_marks_changed_files(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    source = repo / "src" / "app.py"
    source.parent.mkdir(parents=True)
    _ = source.write_text("value = 1\n")
    _ = RepoIndexService(repo).index_repo()

    _ = source.write_text("value = 2\n")
    result = RepoIndexService(repo).index_repo()
    status = RepoStatusService(repo).get_status()

    assert result.changed_files == ("src/app.py",)
    assert status.index_fresh is True
    assert status.changed_files == ()


def test_deleted_indexed_file_is_reported_stale(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    source = repo / "src" / "app.py"
    source.parent.mkdir(parents=True)
    _ = source.write_text("value = 1\n")
    _ = RepoIndexService(repo).index_repo()

    source.unlink()
    status = RepoStatusService(repo).get_status()

    assert status.index_fresh is False
    assert status.changed_files == ("src/app.py",)


def test_non_git_repo_degrades_cleanly(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    source = repo / "src" / "app.py"
    source.parent.mkdir(parents=True)
    _ = source.write_text("value = 1\n")

    result = RepoIndexService(repo).index_repo()
    status = RepoStatusService(repo).get_status()

    assert result.git_available is False
    assert status.git_available is False
    assert status.git_status == "not_git"
    assert status.database_ok is True


def test_status_counts_open_findings(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    source = repo / "src" / "app.py"
    source.parent.mkdir(parents=True)
    _ = source.write_text("value = 1\n")
    _ = RepoIndexService(repo).index_repo()
    state = initialize_storage(repo)
    with RepositoryStorage(state).write_transaction() as connection:
        _ = connection.execute(
            """
            insert into findings (
                id, stable_key, rule_id, severity, confidence, status,
                title, message, evidence_json
            )
            values (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "finding-1",
                "stable-1",
                "python.test",
                "medium",
                0.9,
                "open",
                "Finding",
                "Message",
                "{}",
            ),
        )

    status = RepoStatusService(repo).get_status()

    assert status.finding_count == 1


def test_git_repo_reports_dirty_status(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    git_path = which("git")
    assert git_path is not None
    source = repo / "src" / "app.py"
    source.parent.mkdir(parents=True)
    _ = source.write_text("value = 1\n")
    _ = subprocess.run([git_path, "init"], cwd=repo, check=True, capture_output=True)
    _ = subprocess.run(
        [git_path, "add", "."], cwd=repo, check=True, capture_output=True
    )
    _ = subprocess.run(
        [git_path, "commit", "-m", "initial"],
        cwd=repo,
        check=True,
        capture_output=True,
        env={
            "GIT_AUTHOR_NAME": "CodeScent",
            "GIT_AUTHOR_EMAIL": "codescent@example.test",
            "GIT_COMMITTER_NAME": "CodeScent",
            "GIT_COMMITTER_EMAIL": "codescent@example.test",
        },
    )

    _ = RepoIndexService(repo).index_repo()
    clean = RepoStatusService(repo).get_status()
    _ = source.write_text("value = 2\n")
    dirty = RepoStatusService(repo).get_status()

    assert clean.git_available is True
    assert clean.git_status == "clean"
    assert dirty.git_status == "dirty"


def test_index_persists_references_and_call_edges_with_confidence(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    source = repo / "src" / "app.py"
    source.parent.mkdir(parents=True)
    _ = source.write_text(
        """from helper import send_event

def process_order() -> None:
    send_event()
    print("done")
""",
    )

    _ = RepoIndexService(repo).index_repo()
    state = initialize_storage(repo)
    with RepositoryStorage(state).read_connection() as connection:
        reference_rows: list[tuple[str, int, float]] = connection.execute(
            """
            select reference_text, start_line, confidence
            from symbol_references
            order by reference_text
            """,
        ).fetchall()
        call_rows: list[tuple[str, int, float]] = connection.execute(
            """
            select call_text, start_line, confidence
            from call_edges
            order by call_text
            """,
        ).fetchall()
        import_rows: list[tuple[str, str | None, float]] = connection.execute(
            """
            select imported_path, imported_symbol, confidence
            from imports
            order by imported_path, imported_symbol
            """,
        ).fetchall()

    assert ("print", 5, 0.4) in reference_rows
    assert ("send_event", 4, 0.4) in reference_rows
    assert ("print", 5, 0.4) in call_rows
    assert ("send_event", 4, 0.4) in call_rows
    assert ("helper", "send_event", 1.0) in import_rows


def test_persisted_symbol_readers_return_context_payload_fields(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    source = repo / "src" / "app.py"
    source.parent.mkdir(parents=True)
    _ = source.write_text(
        """def run() -> str:
    return "ok"
""",
    )

    _ = RepoIndexService(repo).index_repo()
    expected = {
        "name": "run",
        "qualified_name": "app.run",
        "kind": "function",
        "path": "src/app.py",
        "start_line": 1,
        "end_line": 2,
        "confidence": 1.0,
    }

    assert read_persisted_symbols(repo, "run") == (expected,)
    assert read_persisted_symbol(repo, "app.run") == expected
    assert read_persisted_file_symbols(repo, "src/app.py") == (expected,)
