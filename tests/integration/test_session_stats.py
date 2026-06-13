import json
import socket
from pathlib import Path

import pytest

from codescent.services.session_stats import ContextStatsService
from codescent.storage import RepositoryStorage, initialize_storage
from codescent.storage.repositories import SessionEventRepository, SessionEventWrite

SENTINEL_TEXT = "SECRET_SOURCE_SENTINEL"


def test_context_stats_aggregates_bounded_session_events(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    state = initialize_storage(repo)
    events = SessionEventRepository(RepositoryStorage(state))

    _ = events.record_event(
        SessionEventWrite(
            project_id="project-a",
            session_id="session-a",
            event_type="tool_called",
            tool_name="repo_summary",
            payload={"query": "all files", "broad_query": True},
            created_at="2026-06-13T00:00:00+00:00",
        )
    )
    _ = events.record_event(
        SessionEventWrite(
            project_id="project-a",
            session_id="session-a",
            event_type="tool_called",
            tool_name="repo_summary",
            payload={"query": "all files", "broad_query": True},
            created_at="2026-06-13T00:00:01+00:00",
        )
    )
    _ = events.record_event(
        SessionEventWrite(
            project_id="project-a",
            session_id="session-a",
            event_type="tool_called",
            tool_name="symbol_search",
            payload={"query": "UserService", "broad_query": False},
            created_at="2026-06-13T00:00:02+00:00",
        )
    )
    _ = events.record_event(
        SessionEventWrite(
            project_id="project-a",
            session_id="session-a",
            event_type="large_result_summarized",
            tool_name="symbol_search",
            result_id="ctx_1",
            payload={
                "query": "UserService",
                "raw_tokens": 42000,
                "returned_tokens": 2100,
                "raw_result": SENTINEL_TEXT,
            },
            created_at="2026-06-13T00:00:03+00:00",
        )
    )
    _ = events.record_event(
        SessionEventWrite(
            project_id="project-a",
            session_id="session-a",
            event_type="result_retrieved",
            tool_name="retrieve_result",
            result_id="ctx_1",
            payload={"raw_tokens": 100, "returned_tokens": 100},
            created_at="2026-06-13T00:00:04+00:00",
        )
    )
    _ = events.record_event(
        SessionEventWrite(
            project_id="project-a",
            session_id="session-a",
            event_type="agent_requested_exact_large_result",
            tool_name="symbol_search",
            result_id="ctx_2",
            payload={"raw_tokens": 5000, "returned_tokens": 5000},
            created_at="2026-06-13T00:00:05+00:00",
        )
    )
    _ = events.record_event(
        SessionEventWrite(
            project_id="project-a",
            session_id="session-a",
            event_type="server_warning_returned",
            tool_name="repo_summary",
            payload={"warning_code": "Broad Query", "warning_count": 2},
            created_at="2026-06-13T00:00:06+00:00",
        )
    )

    stats = ContextStatsService(repo).context_stats(
        project_id="project-a",
        session_id="session-a",
    )

    assert stats.tool_calls == 3
    assert stats.summarized_results == 1
    assert stats.retrievals == 1
    assert stats.estimated_raw_tokens == 47100
    assert stats.estimated_returned_tokens == 7200
    assert stats.estimated_tokens_avoided == 39900
    assert stats.most_used_tools == ("repo_summary", "symbol_search")
    assert stats.largest_summarized_results == (
        {
            "tool": "symbol_search",
            "query_fingerprint": stats.largest_summarized_results[0][
                "query_fingerprint"
            ],
            "input_fingerprint": stats.largest_summarized_results[0][
                "input_fingerprint"
            ],
            "raw_tokens": 42000,
            "returned_tokens": 2100,
        },
    )
    assert stats.repeated_broad_queries == (
        {
            "tool": "repo_summary",
            "input_fingerprint": stats.repeated_broad_queries[0]["input_fingerprint"],
            "count": 2,
        },
    )
    assert stats.warnings == ({"warning_code": "broad_query", "count": 2},)
    payload_json = json.dumps(stats.to_payload(), sort_keys=True)
    assert SENTINEL_TEXT not in payload_json
    assert "UserService" not in payload_json


def test_context_stats_empty_session_returns_zero_values(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()

    stats = ContextStatsService(repo).context_stats(
        project_id="project-a",
        session_id="missing-session",
    )

    assert stats.session_id == "missing-session"
    assert stats.tool_calls == 0
    assert stats.summarized_results == 0
    assert stats.retrievals == 0
    assert stats.estimated_raw_tokens == 0
    assert stats.estimated_returned_tokens == 0
    assert stats.estimated_tokens_avoided == 0
    assert stats.largest_summarized_results == ()
    assert stats.most_used_tools == ()
    assert stats.repeated_broad_queries == ()
    assert stats.warnings == ()


def test_session_event_payloads_persist_fingerprints_not_source(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attempts: list[str] = []

    def blocked_socket(*args: object, **kwargs: object) -> socket.socket:
        _ = args, kwargs
        attempts.append("socket")
        message = "network disabled"
        raise AssertionError(message)

    monkeypatch.setattr(socket, "socket", blocked_socket)
    repo = tmp_path / "repo"
    repo.mkdir()
    state = initialize_storage(repo)
    repository = SessionEventRepository(RepositoryStorage(state))

    event = repository.record_event(
        SessionEventWrite(
            project_id="project-a",
            session_id="session-private",
            event_type="large_result_summarized",
            tool_name="search_content",
            result_id="ctx_private",
            payload={
                "query": f"find {SENTINEL_TEXT}",
                "input_json": {"pattern": SENTINEL_TEXT},
                "raw_result": f"source body {SENTINEL_TEXT}",
                "source_content": f"def leaked(): return {SENTINEL_TEXT!r}",
                "raw_tokens": 9000,
                "returned_tokens": 300,
            },
        )
    )

    with RepositoryStorage(state).read_connection() as connection:
        persisted_rows: list[tuple[str | None]] = connection.execute(
            "select payload_json from session_events",
        ).fetchall()
    persisted_payload_json = persisted_rows[0][0] or ""
    stats = ContextStatsService(repo).context_stats(
        project_id="project-a",
        session_id="session-private",
    )
    stats_payload_json = json.dumps(stats.to_payload(), sort_keys=True)

    query_fingerprint = event.payload["query_fingerprint"]
    input_fingerprint = event.payload["input_fingerprint"]
    assert isinstance(query_fingerprint, str)
    assert isinstance(input_fingerprint, str)
    assert query_fingerprint.startswith("sha256:")
    assert input_fingerprint.startswith("sha256:")
    assert event.payload["raw_tokens"] == 9000
    assert SENTINEL_TEXT not in persisted_payload_json
    assert SENTINEL_TEXT not in stats_payload_json
    assert "source_content" not in persisted_payload_json
    assert "raw_result" not in persisted_payload_json
    assert attempts == []
