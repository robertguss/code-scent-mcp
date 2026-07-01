from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import pytest

from codescent.services.result_store import (
    ResultStoreError,
    ResultStoreService,
    StoredResultErrorPayload,
)

if TYPE_CHECKING:
    from pathlib import Path

    from codescent.storage.repositories import StoredResultRow


def test_retrieves_stored_result_after_service_restart(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    created_at = datetime(2026, 6, 13, 12, 0, tzinfo=UTC)
    service = ResultStoreService(repo)
    stored = service.store_result(
        project_id="project-alpha",
        session_id="session-1",
        tool_name="symbol_search",
        input_payload={"query": "UserService"},
        raw_result={
            "results": [
                {
                    "type": "symbol",
                    "path": "src/users.py",
                    "name": "UserService",
                    "snippet": "class UserService: ...",
                },
            ],
        },
        summary={"items": [{"type": "summary", "count": 1}]},
        created_at=created_at,
        expires_at=created_at + timedelta(hours=1),
    )

    restarted_service = ResultStoreService(repo)
    retrieved = restarted_service.retrieve_result(
        stored.id,
        mode="exact",
        limit=10,
        now=created_at + timedelta(minutes=5),
    )

    assert retrieved["result_id"] == stored.id
    assert retrieved["mode"] == "exact"
    assert retrieved["items"] == (
        {
            "type": "symbol",
            "path": "src/users.py",
            "name": "UserService",
            "snippet": "class UserService: ...",
        },
    )
    assert (
        restarted_service.repository.get_result(
            stored.id,
            now=created_at + timedelta(minutes=5),
        ).retrieval_count
        == 1
    )


def test_exact_retrieval_is_bounded_with_partial_warning(tmp_path: Path) -> None:
    service = _service(tmp_path)
    stored = _store_many(service, count=5)

    retrieved = service.retrieve_result(stored.id, mode="exact", limit=2)

    assert retrieved["mode"] == "summary"
    assert len(retrieved["items"]) == 2
    assert retrieved["remaining_count"] == 3
    assert retrieved["omitted_count"] == 3
    assert retrieved["warnings"] == (
        "exact result exceeded limit; returning bounded partial payload",
    )
    assert retrieved["retrieval_hints"] == (
        f"retrieve_result(result_id='{stored.id}', mode='exact', limit=100)",
    )


def test_summary_filtered_and_sample_modes_use_only_stored_json(tmp_path: Path) -> None:
    service = _service(tmp_path)
    stored = service.store_result(
        project_id="project-alpha",
        tool_name="symbol_search",
        input_payload={"query": "UserService"},
        raw_result={
            "results": [
                {
                    "type": "definition",
                    "path": "src/users.py",
                    "name": "UserService",
                    "snippet": "class UserService: ...",
                },
                {
                    "type": "reference",
                    "path": "tests/test_users.py",
                    "reference_text": "UserService",
                    "snippet": "service = UserService()",
                },
                {
                    "type": "reference",
                    "path": "docs/users.md",
                    "reference_text": "UserService docs",
                    "snippet": "UserService docs",
                },
            ],
        },
        summary={"items": [{"type": "summary", "count": 3}]},
    )

    summary = service.retrieve_result(stored.id, mode="summary", limit=5)
    filtered = service.retrieve_result(
        stored.id,
        mode="filtered",
        query="service =",
        file="tests/test_users.py",
        symbol="UserService",
        result_type="reference",
        limit=5,
    )
    sampled = service.retrieve_result(stored.id, mode="sample", limit=2)

    assert summary["items"] == ({"type": "summary", "count": 3},)
    assert filtered["items"] == (
        {
            "type": "reference",
            "path": "tests/test_users.py",
            "reference_text": "UserService",
            "snippet": "service = UserService()",
        },
    )
    assert sampled["items"] == (
        {
            "type": "definition",
            "path": "src/users.py",
            "name": "UserService",
            "snippet": "class UserService: ...",
        },
        {
            "type": "reference",
            "path": "docs/users.md",
            "reference_text": "UserService docs",
            "snippet": "UserService docs",
        },
    )


def test_invalid_missing_and_expired_ids_return_parseable_errors(
    tmp_path: Path,
) -> None:
    service = _service(tmp_path)
    now = datetime(2026, 6, 13, 12, 0, tzinfo=UTC)
    expired = service.store_result(
        project_id="project-alpha",
        tool_name="symbol_search",
        input_payload={"query": "old"},
        raw_result={"results": []},
        created_at=now - timedelta(hours=2),
        expires_at=now - timedelta(minutes=1),
    )

    invalid = _error_payload(service, "result-1")
    missing = _error_payload(service, "ctx_0000000000000000", now=now)
    expired_payload = _error_payload(service, expired.id, now=now)

    assert invalid == {
        "kind": "result_store_error",
        "code": "invalid_result_id",
        "message": "Result ID must be an opaque ctx_ identifier.",
        "result_id": "result-1",
        "retryable": False,
        "ok": False,
        "recoverable": False,
        "data": {"result_id": "result-1", "retryable": False},
    }
    assert missing["code"] == "missing_result"
    assert missing["message"] == "Stored result ID was not found."
    assert expired_payload["code"] == "expired_result"
    assert expired_payload["message"] == (
        "Stored result is expired and cannot be retrieved."
    )
    assert "Traceback" not in str(missing)


def _service(tmp_path: Path) -> ResultStoreService:
    repo = tmp_path / "repo"
    repo.mkdir()
    return ResultStoreService(repo)


def _store_many(service: ResultStoreService, *, count: int) -> StoredResultRow:
    return service.store_result(
        project_id="project-alpha",
        tool_name="symbol_search",
        input_payload={"query": "many"},
        raw_result={
            "results": [
                {"type": "symbol", "path": f"src/{index}.py", "name": f"S{index}"}
                for index in range(count)
            ],
        },
        summary={"items": [{"type": "summary", "count": count}]},
    )


def _error_payload(
    service: ResultStoreService,
    result_id: str,
    *,
    now: datetime | None = None,
) -> StoredResultErrorPayload:
    with pytest.raises(ResultStoreError) as exc_info:
        _ = service.retrieve_result(result_id, now=now)
    return exc_info.value.to_payload()
