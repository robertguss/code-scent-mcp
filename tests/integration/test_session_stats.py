import json
import socket
from pathlib import Path

import pytest

from codescent.services.session_stats import (
    ContextStatsService,
    record_backend_resolution,
)
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


def _record_backend_events(
    repo: Path,
    *,
    session_id: str,
    backends: tuple[str, ...],
) -> None:
    state = initialize_storage(repo)
    events = SessionEventRepository(RepositoryStorage(state))
    for index, backend_name in enumerate(backends):
        _ = events.record_event(
            SessionEventWrite(
                project_id="project-a",
                session_id=session_id,
                event_type="structural_backend_resolved",
                payload={"backend_name": backend_name},
                created_at=f"2026-06-13T00:00:0{index}+00:00",
            ),
        )


def test_context_stats_reports_cbm_backend_split(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _record_backend_events(repo, session_id="cbm", backends=("cbm", "cbm"))

    stats = ContextStatsService(repo).context_stats(
        project_id="project-a",
        session_id="cbm",
    )

    assert stats.backend_resolutions == 2
    assert stats.cbm_resolutions == 2
    assert stats.to_payload()["cbm_present_rate"] == 1.0


def test_context_stats_reports_native_fallback(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _record_backend_events(repo, session_id="native", backends=("native", "native"))

    stats = ContextStatsService(repo).context_stats(
        project_id="project-a",
        session_id="native",
    )

    assert stats.backend_resolutions == 2
    assert stats.cbm_resolutions == 0
    assert stats.to_payload()["cbm_present_rate"] == 0.0


def test_context_stats_mixed_backend_rate(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _record_backend_events(repo, session_id="mix", backends=("cbm", "native", "cbm"))

    stats = ContextStatsService(repo).context_stats(
        project_id="project-a",
        session_id="mix",
    )

    assert stats.backend_resolutions == 3
    assert stats.cbm_resolutions == 2
    # Same float division the payload runs -> exact, no approx needed.
    assert stats.to_payload()["cbm_present_rate"] == 2 / 3


def test_context_stats_excludes_non_structural_sessions_from_rate(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    state = initialize_storage(repo)
    events = SessionEventRepository(RepositoryStorage(state))
    _ = events.record_event(
        SessionEventWrite(
            project_id="project-a",
            session_id="quiet",
            event_type="tool_called",
            tool_name="find_symbol",
            payload={"query": "x", "broad_query": False},
        ),
    )

    stats = ContextStatsService(repo).context_stats(
        project_id="project-a",
        session_id="quiet",
    )

    # No structural resolution -> zero denominator, rate is a well-defined 0.0.
    assert stats.backend_resolutions == 0
    assert stats.to_payload()["cbm_present_rate"] == 0.0


def test_record_backend_resolution_helper_is_sanitized(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    record_backend_resolution(
        repo_root=repo,
        project_id="project-a",
        session_id="seam",
        backend_name="cbm",
    )

    state = initialize_storage(repo)
    events = SessionEventRepository(RepositoryStorage(state))
    stored = events.list_events(
        project_id="project-a",
        session_id="seam",
        limit=10,
    )

    assert len(stored) == 1
    # Only the low-cardinality backend slug is stored -- no source, no paths.
    assert stored[0].payload == {"backend_name": "cbm"}


def test_cbm_optional_decision_note_is_discoverable() -> None:
    adr = Path("docs/decisions/0001-cbm-optional-by-default.md")
    assert adr.exists()
    text = adr.read_text()

    # Decision + the four-part rationale + a concrete revisit threshold (R11/R12).
    assert "cbm remains optional" in text.lower()
    for keyword in ("Latency", "Identity", "Native path", "release cadence"):
        assert keyword in text
    assert "85%" in text
    assert "cbm_present_rate" in text
    # Discoverable from the README documentation index.
    assert (
        "docs/decisions/0001-cbm-optional-by-default.md"
        in Path("README.md").read_text()
    )
