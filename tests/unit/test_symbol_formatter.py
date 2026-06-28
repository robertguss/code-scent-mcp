from __future__ import annotations

from typing import cast

from codescent.core.models import EnvelopeMode
from codescent.core.symbol_formatter import (
    SymbolGroupPayload,
    format_symbol_search_results,
)
from tests.fixtures.headroom_influence_fixtures import build_symbol_search_fixtures


def test_empty_symbol_results_are_exact_without_retrieval_metadata() -> None:
    fixtures = build_symbol_search_fixtures()

    envelope = format_symbol_search_results("build_task", fixtures["empty"])

    assert envelope.kind == "symbol_search"
    assert envelope.mode is EnvelopeMode.EXACT
    assert envelope.items == ()
    assert envelope.omitted_count == 0
    assert envelope.original_result_id is None
    assert envelope.retrieval_available is False
    assert envelope.retrieval_hints == ()
    assert envelope.warnings == ()
    assert envelope.stats == {
        "total_results": 0,
        "returned_results": 0,
        "groups_returned": 0,
    }


def test_large_symbol_results_are_grouped_bounded_and_retrievable() -> None:
    fixtures = build_symbol_search_fixtures()

    envelope = format_symbol_search_results(
        "build_task",
        fixtures["large_exact_matches"],
        options={"original_result_id": "stored-symbols-1"},
    )

    assert envelope.mode is EnvelopeMode.SUMMARIZED
    assert envelope.omitted_count == 12
    assert envelope.original_result_id == "stored-symbols-1"
    assert envelope.retrieval_available is True
    assert envelope.retrieval_hints == (
        "Refine symbol query 'build_task' or request a narrower limit/cursor window.",
        "Use retrieve_result('stored-symbols-1') for full results.",
    )
    assert envelope.warnings == ()
    assert envelope.stats is not None
    assert envelope.stats["total_results"] == 24
    assert envelope.stats["returned_results"] == 12
    assert envelope.stats["total_groups"] == 6
    assert envelope.stats["groups_returned"] == 6

    groups = cast("tuple[SymbolGroupPayload, ...]", envelope.items)
    assert len(groups) == 6
    assert all(group["match_type"] == "exact" for group in groups)
    assert all(group["role"] == "definition" for group in groups)
    assert all(group["symbol_types"] for group in groups)
    assert all(len(group["items"]) == 2 for group in groups)

    first_item = groups[0]["items"][0]
    assert first_item == {
        "name": "build_task_0_0",
        "qualified_name": "acme.pipeline.module_00.build_task_0_0",
        "path": "src/acme/pipeline/module_00.py",
        "line": 10,
        "end_line": 12,
        "kind": "function",
        "score": 1.0,
        "rank_reason": "exact definition match for 'build_task' with score=1.00",
        "snippet": "def build_task_0_0() -> None: ...",
    }


def test_mixed_symbols_sort_exact_definition_before_partial_references() -> None:
    fixtures = build_symbol_search_fixtures()

    envelope = format_symbol_search_results(
        "build_daily_plan",
        fixtures["mixed_definition_reference"],
    )

    assert envelope.mode is EnvelopeMode.EXACT
    assert envelope.omitted_count == 0
    assert envelope.warnings == ()
    groups = cast("tuple[SymbolGroupPayload, ...]", envelope.items)

    assert [group["match_type"] for group in groups] == [
        "exact",
        "partial",
        "partial",
    ]
    assert [group["role"] for group in groups] == [
        "definition",
        "reference",
        "reference",
    ]
    assert groups[0]["kind"] == "function"
    assert groups[0]["items"][0]["name"] == "build_daily_plan"
    assert groups[1]["items"][0]["path"] == "tests/test_workflow.py"


def test_missing_semantic_classification_warns_without_inventing_data() -> None:
    envelope = format_symbol_search_results(
        "build_daily_plan",
        (
            {
                "name": "build_daily_plan",
                "qualified_name": "acme_tasks.workflow.build_daily_plan",
                "path": "src/acme_tasks/workflow.py",
                "start_line": 12,
                "end_line": 26,
                "confidence": 0.91,
            },
        ),
        options={"cursor": 20, "next_cursor": 40},
    )

    assert envelope.mode is EnvelopeMode.EXACT
    assert envelope.warnings == (
        "semantic classification missing: match_type; grouped under 'unknown'",
        "semantic classification missing: role; grouped under 'unknown'",
        "semantic classification missing: kind; grouped under 'unknown'",
    )
    assert envelope.stats is not None
    assert envelope.stats["cursor"] == 20
    assert envelope.stats["next_cursor"] == 40
    groups = cast("tuple[SymbolGroupPayload, ...]", envelope.items)
    assert groups[0]["match_type"] == "unknown"
    assert groups[0]["role"] == "unknown"
    assert groups[0]["kind"] == "unknown"
    assert groups[0]["items"][0]["line"] == 12
