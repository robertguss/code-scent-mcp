from pathlib import Path

from codescent.services.context_optimization import ContextOptimizationService


def test_context_stats_reports_session_savings_and_top_tools(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    service = ContextOptimizationService(str(repo))

    stored = service.store_result(
        tool_name="search_content",
        session_id="sess_a",
        query="load_config",
        raw_payload={
            "items": (
                {
                    "path": "src/app.py",
                    "line": 3,
                    "symbol": "load_config",
                    "snippet": "def load_config(): pass",
                },
            ),
        },
        returned_payload={"summary": "1 match"},
    )
    _ = service.retrieve_result(stored.result_id, mode="summary")

    stats = service.context_stats(session_id="sess_a")

    assert stats["ok"] is True
    assert stats["session_id"] == "sess_a"
    assert stats["tool_calls"] == 1
    assert stats["summarized_results"] == 1
    assert stats["retrievals"] == 1
    assert stats["estimated_raw_tokens"] >= stats["estimated_returned_tokens"]
    assert stats["estimated_tokens_avoided"] >= 0
    assert stats["largest_summarized_results"] == (stored.result_id,)
    assert stats["most_used_tools"] == ("search_content",)


def test_context_stats_can_include_all_sessions(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    service = ContextOptimizationService(str(repo))

    _ = service.store_result(
        tool_name="find_symbol",
        session_id="sess_a",
        query="load_config",
        raw_payload={"items": ()},
        returned_payload={"summary": "none"},
    )
    _ = service.store_result(
        tool_name="search_tests",
        session_id="sess_b",
        query="load_config",
        raw_payload={"items": ()},
        returned_payload={"summary": "none"},
    )

    stats = service.context_stats(session_id=None)

    assert stats["ok"] is True
    assert stats["session_id"] is None
    assert stats["tool_calls"] == 2
    assert stats["summarized_results"] == 2
    assert stats["most_used_tools"] == ("find_symbol", "search_tests")
