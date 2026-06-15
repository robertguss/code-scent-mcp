import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast

import pytest

from codescent.core.errors import CodeScentError, ErrorCode
from codescent.storage import RepositoryStorage, initialize_storage
from codescent.storage.repositories import StoredResultCreate, StoredResultRepository
from codescent.storage.schema import SCHEMA_VERSION


def test_init_creates_codescent_state_only(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    source = repo / "src" / "app.py"
    source.parent.mkdir(parents=True)
    _ = source.write_text("value = 1\n")

    state = initialize_storage(repo)

    assert state.state_dir == repo / ".codescent"
    assert sorted(path.relative_to(repo).as_posix() for path in repo.rglob("*")) == [
        ".codescent",
        ".codescent/config.toml",
        ".codescent/index.sqlite",
        "src",
        "src/app.py",
    ]
    assert state.database_path.is_file()
    assert state.config_path.read_text() == (
        f"[project]\nschema_version = {SCHEMA_VERSION}\n"
    )
    with RepositoryStorage(state).read_connection() as connection:
        for statement in (
            "select 1 from stored_results limit 0",
            "select 1 from session_events limit 0",
        ):
            cursor = connection.execute(statement)
            assert cursor.description is not None


def test_schema_migration_idempotent(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()

    first = initialize_storage(repo)
    second = initialize_storage(repo)

    assert first == second
    with RepositoryStorage(second).read_connection() as connection:
        for statement in (
            "select 1 from chunks limit 0",
            "select 1 from eval_runs limit 0",
            "select 1 from files limit 0",
            "select 1 from frecency_signals limit 0",
            "select 1 from finding_events limit 0",
            "select 1 from findings limit 0",
            "select 1 from imports limit 0",
            "select 1 from scan_runs limit 0",
            "select 1 from schema_version limit 0",
            "select 1 from suggested_verifications limit 0",
            "select 1 from session_events limit 0",
            "select 1 from stored_results limit 0",
            "select 1 from symbols limit 0",
            "select 1 from telemetry limit 0",
            "select 1 from verification_runs limit 0",
        ):
            cursor = connection.execute(statement)
            assert cursor.description is not None


def test_stored_results_survive_repository_restart_until_ttl(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    state = initialize_storage(repo)
    created_at = datetime(2026, 6, 13, 12, 0, tzinfo=UTC)
    original_repository = StoredResultRepository(RepositoryStorage(state))
    created = original_repository.create_result(
        StoredResultCreate(
            project_id="project-alpha",
            session_id="session-1",
            tool_name="symbol_search",
            input_json=json.dumps({"query": "load_config"}, sort_keys=True),
            raw_result_json=json.dumps(
                {"results": [{"path": "src/app.py", "name": "load_config"}]},
                sort_keys=True,
            ),
            summary_json=json.dumps({"count": 1}, sort_keys=True),
            content_type="application/json",
            raw_token_estimate=120,
            returned_token_estimate=20,
            created_at=created_at,
            expires_at=created_at + timedelta(hours=1),
        ),
    )

    restarted_repository = StoredResultRepository(RepositoryStorage(state))
    retrieved = restarted_repository.get_result(
        created.id,
        now=created_at + timedelta(minutes=5),
    )

    assert retrieved.id == created.id
    assert json.loads(retrieved.raw_result_json) == {
        "results": [{"name": "load_config", "path": "src/app.py"}],
    }
    assert retrieved.retrieval_count == 0


def test_stored_result_ttl_expiry_and_cleanup_use_injected_now(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    state = initialize_storage(repo)
    repository = StoredResultRepository(RepositoryStorage(state))
    now = datetime(2026, 6, 13, 12, 0, tzinfo=UTC)
    expired = repository.create_result(
        _stored_result_request(
            raw_result_json=json.dumps({"expired": True}, sort_keys=True),
            created_at=now - timedelta(hours=2),
            expires_at=now,
        ),
    )
    active = repository.create_result(
        _stored_result_request(
            raw_result_json=json.dumps({"active": True}, sort_keys=True),
            created_at=now,
            expires_at=now + timedelta(seconds=1),
        ),
    )

    with pytest.raises(LookupError):
        _ = repository.get_result(expired.id, now=now)
    assert repository.get_result(expired.id, include_expired=True).id == expired.id
    assert repository.get_result(active.id, now=now).id == active.id

    removed_count = repository.cleanup_expired(now=now)

    assert removed_count == 1
    with pytest.raises(LookupError):
        _ = repository.get_result(expired.id, include_expired=True)
    assert repository.get_result(active.id, now=now).id == active.id


def test_stored_result_accepts_oversized_json_payload_without_source_mutation(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    source = repo / "src" / "app.py"
    source.parent.mkdir(parents=True)
    _ = source.write_text("value = 1\n")
    source_before = source.read_text()
    state = initialize_storage(repo)
    repository = StoredResultRepository(RepositoryStorage(state))
    created_at = datetime(2026, 6, 13, 12, 0, tzinfo=UTC)
    large_payload = {
        "results": [
            {
                "path": "src/app.py",
                "name": f"Symbol{index}",
                "snippet": "x" * 200,
            }
            for index in range(150)
        ],
    }
    raw_result_json = json.dumps(large_payload, sort_keys=True)
    created = repository.create_result(
        _stored_result_request(
            raw_result_json=raw_result_json,
            created_at=created_at,
            expires_at=created_at + timedelta(hours=1),
        ),
    )

    retrieved = StoredResultRepository(RepositoryStorage(state)).get_result(
        created.id,
        now=created_at,
    )

    assert retrieved.raw_result_json == raw_result_json
    retrieved_payload = cast("dict[str, object]", json.loads(retrieved.raw_result_json))
    retrieved_results = cast("list[object]", retrieved_payload["results"])
    assert len(retrieved_results) == 150
    assert source.read_text() == source_before


def test_concurrent_writer_returns_structured_error(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    state = initialize_storage(repo)
    storage = RepositoryStorage(state)

    with storage.write_transaction() as connection:
        cursor = connection.execute("select 1")
        assert cursor.description is not None
        with (
            pytest.raises(CodeScentError) as error,
            RepositoryStorage(
                state,
            ).write_transaction(),
        ):
            pass

    assert error.value.code is ErrorCode.CONCURRENT_WRITE
    assert error.value.to_payload()["code"] == "concurrent_write"


def test_concurrent_writer_error_survives_outer_context(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    state = initialize_storage(repo)
    storage = RepositoryStorage(state)

    with (
        pytest.raises(CodeScentError) as error,
        storage.write_transaction(),
        RepositoryStorage(state).write_transaction(),
    ):
        pass

    assert error.value.code is ErrorCode.CONCURRENT_WRITE


def _stored_result_request(
    *,
    raw_result_json: str,
    created_at: datetime,
    expires_at: datetime | None,
) -> StoredResultCreate:
    return StoredResultCreate(
        project_id="project-alpha",
        session_id="session-1",
        tool_name="symbol_search",
        input_json=json.dumps({"query": "load_config"}, sort_keys=True),
        raw_result_json=raw_result_json,
        summary_json=json.dumps({"count": 1}, sort_keys=True),
        content_type="application/json",
        raw_token_estimate=1000,
        returned_token_estimate=100,
        created_at=created_at,
        expires_at=expires_at,
    )
