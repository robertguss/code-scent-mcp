import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from codescent.storage import RepositoryStorage, initialize_storage
from codescent.storage.repositories import StoredResultCreate, StoredResultRepository


def test_stored_result_round_trips_json_and_counts(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    created_at = datetime(2026, 6, 13, 12, 0, tzinfo=UTC)

    created = repository.create_result(
        StoredResultCreate(
            project_id="project-alpha",
            session_id="session-1",
            tool_name="symbol_search",
            input_json=json.dumps({"query": "load_config"}, sort_keys=True),
            raw_result_json=json.dumps(
                {"matches": [{"path": "src/pkg/config.py", "line": 12}]},
                sort_keys=True,
            ),
            summary_json=json.dumps({"count": 1, "top_path": "src/pkg/config.py"}),
            content_type="application/json",
            raw_token_estimate=1800,
            returned_token_estimate=240,
            created_at=created_at,
            expires_at=created_at + timedelta(hours=1),
        ),
    )

    fetched = repository.get_result(created.id, now=created_at)
    counted_once = repository.increment_retrieval_count(created.id)
    counted_twice = repository.increment_retrieval_count(created.id)

    assert created.id.startswith("ctx_")
    assert len(created.id) == 20
    assert fetched == created
    assert json.loads(fetched.input_json) == {"query": "load_config"}
    assert json.loads(fetched.raw_result_json)["matches"][0]["line"] == 12
    assert json.loads(fetched.summary_json or "{}") == {
        "count": 1,
        "top_path": "src/pkg/config.py",
    }
    assert fetched.raw_token_estimate == 1800
    assert fetched.returned_token_estimate == 240
    assert fetched.retrieval_count == 0
    assert counted_once.retrieval_count == 1
    assert counted_twice.retrieval_count == 2


def test_expiry_cleanup_removes_only_expired_stored_results(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    state = initialize_storage(repo)
    repository = StoredResultRepository(RepositoryStorage(state))
    now = datetime(2026, 6, 13, 12, 0, tzinfo=UTC)
    expired = repository.create_result(
        _request(
            raw_result_json=json.dumps({"expired": True}),
            summary_json=json.dumps({"expired": True}),
            created_at=now - timedelta(hours=2),
            expires_at=now - timedelta(seconds=1),
        ),
    )
    active = repository.create_result(
        _request(
            raw_result_json=json.dumps({"active": True}),
            summary_json=json.dumps({"active": True}),
            created_at=now,
            expires_at=now + timedelta(hours=1),
        ),
    )
    no_expiry = repository.create_result(
        _request(
            raw_result_json=json.dumps({"expires": None}),
            summary_json=None,
            created_at=now,
            expires_at=None,
        ),
    )
    with RepositoryStorage(state).write_transaction() as connection:
        _ = connection.execute(
            """
            insert into session_events (
                id,
                project_id,
                session_id,
                event_type,
                tool_name,
                result_id,
                payload_json,
                created_at
            ) values (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "event-1",
                "project-alpha",
                "session-1",
                "stored_result_created",
                "symbol_search",
                expired.id,
                json.dumps({"expires_at": expired.expires_at}),
                now.isoformat(),
            ),
        )

    with pytest.raises(LookupError):
        _ = repository.get_result(expired.id, now=now)
    removed_count = repository.cleanup_expired(now=now)

    assert removed_count == 1
    assert repository.get_result(active.id, now=now).id == active.id
    assert repository.get_result(no_expiry.id, now=now).id == no_expiry.id
    with pytest.raises(LookupError):
        _ = repository.get_result(expired.id, include_expired=True)
    with RepositoryStorage(state).read_connection() as connection:
        session_event_rows: list[tuple[int]] = connection.execute(
            "select count(*) from session_events",
        ).fetchall()
    session_event_count = session_event_rows[0][0]
    assert session_event_count == 1


def test_lists_largest_and_recent_summarized_results(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    base = datetime(2026, 6, 13, 12, 0, tzinfo=UTC)
    small = repository.create_result(
        _request(
            raw_result_json=json.dumps({"name": "small"}),
            summary_json=json.dumps({"name": "small"}),
            token_estimates=(100, 20),
            created_at=base,
            expires_at=base + timedelta(hours=1),
        ),
    )
    large = repository.create_result(
        _request(
            raw_result_json=json.dumps({"name": "large"}),
            summary_json=json.dumps({"name": "large"}),
            token_estimates=(900, 60),
            created_at=base + timedelta(minutes=1),
            expires_at=base + timedelta(hours=1),
        ),
    )
    recent = repository.create_result(
        _request(
            raw_result_json=json.dumps({"name": "recent"}),
            summary_json=json.dumps({"name": "recent"}),
            token_estimates=(300, 30),
            created_at=base + timedelta(minutes=2),
            expires_at=base + timedelta(hours=1),
        ),
    )
    expired = repository.create_result(
        _request(
            raw_result_json=json.dumps({"name": "expired"}),
            summary_json=json.dumps({"name": "expired"}),
            token_estimates=(5000, 10),
            created_at=base + timedelta(minutes=3),
            expires_at=base + timedelta(minutes=4),
        ),
    )
    raw_only = repository.create_result(
        _request(
            raw_result_json=json.dumps({"name": "raw_only"}),
            summary_json=None,
            token_estimates=(6000, 0),
            created_at=base + timedelta(minutes=4),
            expires_at=base + timedelta(hours=1),
        ),
    )

    largest = repository.list_summarized_results(
        limit=3,
        order_by="largest",
        now=base + timedelta(minutes=5),
    )
    recent_results = repository.list_summarized_results(
        limit=3,
        order_by="recent",
        now=base + timedelta(minutes=5),
    )

    assert [row.id for row in largest] == [large.id, recent.id, small.id]
    assert [row.raw_token_estimate for row in largest] == [900, 300, 100]
    assert [row.id for row in recent_results] == [recent.id, large.id, small.id]
    assert expired.id not in {row.id for row in largest}
    assert raw_only.id not in {row.id for row in recent_results}


def _repository(tmp_path: Path) -> StoredResultRepository:
    repo = tmp_path / "repo"
    repo.mkdir()
    state = initialize_storage(repo)
    return StoredResultRepository(RepositoryStorage(state))


def _request(
    *,
    raw_result_json: str,
    summary_json: str | None,
    token_estimates: tuple[int, int] = (10, 5),
    created_at: datetime,
    expires_at: datetime | None,
) -> StoredResultCreate:
    return StoredResultCreate(
        project_id="project-alpha",
        session_id="session-1",
        tool_name="symbol_search",
        input_json=json.dumps({"query": "load_config"}, sort_keys=True),
        raw_result_json=raw_result_json,
        summary_json=summary_json,
        content_type="application/json",
        raw_token_estimate=token_estimates[0],
        returned_token_estimate=token_estimates[1],
        created_at=created_at,
        expires_at=expires_at,
    )
