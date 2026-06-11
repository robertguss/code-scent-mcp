from pathlib import Path

import pytest

from codescent.core.errors import CodeScentError, ErrorCode
from codescent.storage import RepositoryStorage, initialize_storage
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
            "select 1 from symbols limit 0",
            "select 1 from telemetry limit 0",
        ):
            cursor = connection.execute(statement)
            assert cursor.description is not None


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
