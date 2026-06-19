import sqlite3
from contextlib import closing
from pathlib import Path

import pytest

from codescent.storage import RepositoryStorage, initialize_storage
from codescent.storage.repositories import (
    SessionEventRepository,
    SessionEventWrite,
    StoredResultCreate,
    StoredResultRepository,
)
from codescent.storage.schema import SCHEMA_VERSION


def test_migrates_mvp_schema_to_latest_without_data_loss(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    state_dir = repo / ".codescent"
    database_path = state_dir / "index.sqlite"
    repo.mkdir()
    state_dir.mkdir()
    _ = (repo / "app.py").write_text("value = 1\n")
    _ = (state_dir / "config.toml").write_text("[project]\nschema_version = 2\n")
    _create_mvp_v4_database(database_path)

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
        assert (
            _single_value(connection, "select provider from subjective_findings")
            == "fake"
        )
        for statement in (
            "select 1 from call_edges limit 0",
            "select 1 from health_baseline limit 0",
            "select 1 from symbol_references limit 0",
            "select 1 from session_events limit 0",
            "select 1 from stored_results limit 0",
            "select 1 from verification_runs limit 0",
        ):
            cursor = connection.execute(statement)
            assert cursor.description is not None
        assert _health_baseline_columns(connection) == {
            "id": "integer",
            "file_path": "text",
            "finding_count": "integer",
            "created_at": "text",
        }
        assert _verification_run_columns(connection) == {
            "id": "integer",
            "finding_id": "text",
            "command": "text",
            "exit_code": "integer",
            "output_summary": "text",
            "created_at": "text",
        }

    storage = RepositoryStorage(state)
    with pytest.raises(sqlite3.IntegrityError):
        _insert_duplicate_health_baseline(storage)

    result = StoredResultRepository(storage).create_result(
        StoredResultCreate(
            project_id="project-alpha",
            session_id="session-1",
            tool_name="symbol_search",
            input_json='{"query":"load_config"}',
            raw_result_json='{"results":[{"path":"app.py"}]}',
            summary_json='{"count":1}',
            content_type="application/json",
            raw_token_estimate=42,
            returned_token_estimate=7,
            created_at=None,
            expires_at=None,
        ),
    )
    event = SessionEventRepository(storage).record_event(
        SessionEventWrite(
            project_id="project-alpha",
            session_id="session-1",
            event_type="large_result_summarized",
            tool_name="symbol_search",
            result_id=result.id,
            payload={"query": "load_config", "raw_tokens": 42},
            created_at="2026-06-13T12:00:00+00:00",
        ),
    )

    assert result.id.startswith("ctx_")
    assert event.payload == {
        "query_fingerprint": "sha256:1be0f95493281d6c",
        "raw_tokens": 42,
    }


def test_reconciles_stored_results_missing_project_id_column(tmp_path: Path) -> None:
    # Regression: a database whose `stored_results` table predates the
    # `project_id` column (the column was added to migration 5's create
    # statement after the table already existed) was stuck — store_result
    # raised "table stored_results has no column named project_id" because
    # create-table-if-not-exists never alters and there is no column migration.
    repo = tmp_path / "repo"
    state_dir = repo / ".codescent"
    database_path = state_dir / "index.sqlite"
    repo.mkdir()
    state_dir.mkdir()
    _ = (repo / "app.py").write_text("value = 1\n")
    _ = (state_dir / "config.toml").write_text(
        f"[project]\nschema_version = {SCHEMA_VERSION}\n",
    )
    _create_database_with_legacy_stored_results(database_path)

    state = initialize_storage(repo)

    storage = RepositoryStorage(state)
    with RepositoryStorage(state).read_connection() as connection:
        assert "project_id" in _table_columns(connection, "stored_results")

    # The previously stuck write now succeeds.
    result = StoredResultRepository(storage).create_result(
        StoredResultCreate(
            project_id="project-alpha",
            session_id="session-1",
            tool_name="get_smell_report",
            input_json='{"repo":"."}',
            raw_result_json='{"items":[]}',
            summary_json=None,
            content_type="application/json",
            raw_token_estimate=1,
            returned_token_estimate=1,
            created_at=None,
            expires_at=None,
        ),
    )
    assert result.id.startswith("ctx_")

    # The pre-existing legacy row survives, back-filled with the default.
    with RepositoryStorage(state).read_connection() as connection:
        legacy_project_id = _single_value(
            connection,
            "select project_id from stored_results where id = 'ctx_legacy0000000'",
        )
    assert legacy_project_id == ""


def _create_database_with_legacy_stored_results(database_path: Path) -> None:
    # A stored_results table in its pre-project_id shape, marked at the current
    # schema version so migrate() runs no create/alter for it on its own.
    with closing(sqlite3.connect(database_path)) as connection:
        _ = connection.execute(
            """
            create table stored_results (
                id text primary key,
                session_id text,
                tool_name text not null,
                input_json text not null,
                raw_result_json text not null,
                summary_json text,
                content_type text,
                raw_token_estimate integer,
                returned_token_estimate integer,
                created_at text not null,
                expires_at text,
                retrieval_count integer not null default 0
            )
            """,
        )
        _ = connection.execute(
            """
            insert into stored_results (
                id, tool_name, input_json, raw_result_json, created_at
            ) values ('ctx_legacy0000000', 'get_smell_report', '{}', '{}', 'now')
            """,
        )
        _ = connection.execute(f"pragma user_version = {SCHEMA_VERSION}")
        connection.commit()


def _table_columns(connection: sqlite3.Connection, table: str) -> set[str]:
    rows: list[tuple[str]] = connection.execute(
        "select name from pragma_table_info(?)",
        (table,),
    ).fetchall()
    return {row[0] for row in rows}


def _create_mvp_v4_database(database_path: Path) -> None:
    schema_sql = Path("tests/fixtures/storage/mvp_v4_schema.sql").read_text()
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


def _health_baseline_columns(connection: sqlite3.Connection) -> dict[str, str]:
    rows: list[tuple[int, str, str, int, str | None, int]] = connection.execute(
        "pragma table_info(health_baseline)",
    ).fetchall()
    return {row[1]: row[2].lower() for row in rows}


def _verification_run_columns(connection: sqlite3.Connection) -> dict[str, str]:
    rows: list[tuple[int, str, str, int, str | None, int]] = connection.execute(
        "pragma table_info(verification_runs)",
    ).fetchall()
    return {row[1]: row[2].lower() for row in rows}


def _insert_duplicate_health_baseline(storage: RepositoryStorage) -> None:
    with storage.write_transaction() as connection:
        _ = connection.execute(
            """
            insert into health_baseline (
                file_path,
                finding_count,
                created_at
            ) values ('app.py', 1, 'now')
            """,
        )
        _ = connection.execute(
            """
            insert into health_baseline (
                file_path,
                finding_count,
                created_at
            ) values ('app.py', 2, 'later')
            """,
        )


def _single_value(connection: sqlite3.Connection, query: str) -> str:
    rows: list[tuple[str]] = connection.execute(query).fetchall()
    return rows[0][0]
