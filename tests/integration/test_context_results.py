from pathlib import Path

from codescent.services.context_optimization import (
    ContextOptimizationService,
    ResultPayload,
)
from codescent.storage import RepositoryStorage, initialize_storage


def test_retrieve_result_returns_exact_payload_when_result_exists(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    service = ContextOptimizationService(str(repo))
    payload: ResultPayload = {
        "items": (
            {
                "path": "src/app.py",
                "line": 3,
                "symbol": "load_config",
                "snippet": "def load_config(): pass",
            },
        ),
    }

    stored = service.store_result(
        tool_name="search_content",
        session_id=None,
        query="load_config",
        raw_payload=payload,
        returned_payload={"summary": "1 match"},
    )
    retrieved = service.retrieve_result(stored.result_id, mode="exact")

    assert retrieved["ok"] is True
    assert retrieved["result_id"] == stored.result_id
    assert retrieved["mode"] == "exact"
    assert retrieved["payload"] == payload
    assert retrieved["session_id"] == "sess_default"


def test_retrieve_result_filters_by_file_symbol_and_limit(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    service = ContextOptimizationService(str(repo))
    payload: ResultPayload = {
        "items": (
            {
                "path": "src/app.py",
                "line": 3,
                "symbol": "load_config",
                "snippet": "def load_config(): pass",
            },
            {
                "path": "src/other.py",
                "line": 8,
                "symbol": "load_config",
                "snippet": "load_config()",
            },
        ),
    }

    stored = service.store_result(
        tool_name="find_references",
        session_id="sess_custom",
        query="load_config",
        raw_payload=payload,
        returned_payload={"summary": "2 references"},
    )
    retrieved = service.retrieve_result(
        stored.result_id,
        mode="filtered",
        file="src/app.py",
        symbol="load_config",
        session_id="sess_custom",
        limit=1,
    )

    assert retrieved["ok"] is True
    assert retrieved["mode"] == "filtered"
    assert retrieved["payload"] == {
        "items": (
            {
                "path": "src/app.py",
                "line": 3,
                "symbol": "load_config",
                "snippet": "def load_config(): pass",
            },
        ),
    }


def test_retrieve_result_returns_structured_not_found_for_missing_id(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    service = ContextOptimizationService(str(repo))

    retrieved = service.retrieve_result("ctx_missing", mode="exact")

    assert retrieved["ok"] is False
    assert retrieved["result_id"] == "ctx_missing"
    assert retrieved.get("error_code") == "result_not_found"
    assert retrieved["payload"] == {"items": ()}


def test_context_result_storage_cleans_expired_rows_before_insert(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    state = initialize_storage(repo)
    service = ContextOptimizationService(str(repo))

    with RepositoryStorage(state).write_transaction() as connection:
        _ = connection.execute(
            """
            insert into stored_results (
                id,
                tool_name,
                session_id,
                query,
                raw_payload_json,
                returned_payload_json,
                raw_token_estimate,
                returned_token_estimate,
                created_at,
                expires_at,
                retrieval_count
            ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "ctx_expired",
                "search_content",
                "sess_default",
                "old",
                '{"items":[]}',
                '{"summary":"old"}',
                10,
                5,
                "2000-01-01T00:00:00+00:00",
                "2000-01-01T00:00:01+00:00",
                0,
            ),
        )

    _ = service.store_result(
        tool_name="search_content",
        session_id=None,
        query="new",
        raw_payload={"items": ()},
        returned_payload={"summary": "new"},
    )

    with RepositoryStorage(state).read_connection() as connection:
        rows: list[tuple[str]] = connection.execute(
            "select id from stored_results where id = 'ctx_expired'",
        ).fetchall()
    assert rows == []
