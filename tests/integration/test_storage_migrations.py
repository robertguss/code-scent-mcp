import sqlite3
from contextlib import closing
from pathlib import Path

from codescent.storage import RepositoryStorage, initialize_storage
from codescent.storage.schema import SCHEMA_VERSION


def test_migrates_mvp_schema_to_latest_without_data_loss(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    state_dir = repo / ".codescent"
    database_path = state_dir / "index.sqlite"
    repo.mkdir()
    state_dir.mkdir()
    _ = (repo / "app.py").write_text("value = 1\n")
    _ = (state_dir / "config.toml").write_text("[project]\nschema_version = 2\n")
    _create_mvp_v2_database(database_path)

    state = initialize_storage(repo)

    assert SCHEMA_VERSION > 2
    assert state.config_path.read_text() == (
        f"[project]\nschema_version = {SCHEMA_VERSION}\n"
    )
    with RepositoryStorage(state).read_connection() as connection:
        assert _pragma_user_version(connection) == SCHEMA_VERSION
        assert _schema_version(connection) == SCHEMA_VERSION
        assert _single_value(connection, "select path from files") == "app.py"
        assert (
            _single_value(connection, "select qualified_name from symbols")
            == "app.load_config"
        )
        assert (
            _single_value(connection, "select title from findings")
            == "Keep config small"
        )
        for statement in (
            "select 1 from call_edges limit 0",
            "select 1 from symbol_references limit 0",
        ):
            cursor = connection.execute(statement)
            assert cursor.description is not None


def _create_mvp_v2_database(database_path: Path) -> None:
    schema_sql = Path("tests/fixtures/storage/mvp_v2_schema.sql").read_text()
    with closing(sqlite3.connect(database_path)) as connection:
        _ = connection.executescript(schema_sql)
        _ = connection.execute(
            """
            insert into files (
                id,
                path,
                language,
                hash,
                size_bytes,
                line_count,
                git_status,
                is_generated,
                is_test,
                last_indexed_at
            ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (1, "app.py", "python", "hash-v2", 10, 1, "clean", 0, 0, "now"),
        )
        _ = connection.execute(
            """
            insert into symbols (
                id,
                file_id,
                name,
                qualified_name,
                kind,
                signature,
                start_line,
                end_line,
                exported,
                confidence
            ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                1,
                1,
                "load_config",
                "app.load_config",
                "function",
                None,
                1,
                1,
                0,
                1.0,
            ),
        )
        _ = connection.execute(
            """
            insert into scan_runs (
                id,
                started_at,
                completed_at,
                index_version,
                rule_version,
                files_scanned,
                findings_created,
                findings_resolved,
                status
            ) values ('scan-v2', 'now', 'now', 2, 'python-v1', 1, 1, 0, 'completed')
            """,
        )
        _ = connection.execute(
            """
            insert into findings (
                id,
                stable_key,
                rule_id,
                file_id,
                symbol_id,
                severity,
                confidence,
                status,
                title,
                message,
                evidence_json,
                suggested_action,
                first_seen_scan_id,
                last_seen_scan_id,
                resolved_at
            ) values (
                'finding-v2',
                'python:no-large-config:app.py',
                'python.no_large_config',
                1,
                1,
                'medium',
                0.8,
                'open',
                'Keep config small',
                'Split config constants.',
                '{}',
                'Extract a loader.',
                'scan-v2',
                'scan-v2',
                null
            )
            """,
        )
        connection.commit()


def _pragma_user_version(connection: sqlite3.Connection) -> int:
    rows: list[tuple[int]] = connection.execute("pragma user_version").fetchall()
    return rows[0][0]


def _schema_version(connection: sqlite3.Connection) -> int:
    rows: list[tuple[int]] = connection.execute(
        "select version from schema_version",
    ).fetchall()
    return rows[0][0]


def _single_value(connection: sqlite3.Connection, query: str) -> str:
    rows: list[tuple[str]] = connection.execute(query).fetchall()
    return rows[0][0]
