from __future__ import annotations

from typing import TYPE_CHECKING, NotRequired, TypedDict

from codescent.services.context_optimization import (
    ContextEnvelope,
    ContextOptimizationService,
    ResultPayload,
    summarize_result,
)
from codescent.services.context_optimization_models import ResultItem

if TYPE_CHECKING:
    from codescent.services.context_support import (
        GraphResultPayload,
        SymbolMatchPayload,
    )
    from codescent.services.search_support import (
        SearchResultPayload,
        TestSearchResultPayload,
    )


class EnvelopeOptions(TypedDict):
    tool_name: str
    repo: str
    session_id: NotRequired[str | None]
    query: NotRequired[str | None]


def envelope_for_search_results(
    options: EnvelopeOptions,
    results: tuple[SearchResultPayload, ...],
) -> ContextEnvelope:
    items = tuple(
        _search_result_item(result["path"], result["score"], result["snippet"])
        for result in results
    )
    return envelope_for_items(options, {"items": items}, len(results))


def envelope_for_test_results(
    options: EnvelopeOptions,
    results: tuple[TestSearchResultPayload, ...],
) -> ContextEnvelope:
    items = tuple(
        _search_result_item(result["path"], result["score"], result["snippet"])
        for result in results
    )
    return envelope_for_items(options, {"items": items}, len(results))


def envelope_for_symbols(
    options: EnvelopeOptions,
    results: tuple[SymbolMatchPayload, ...],
) -> ContextEnvelope:
    items = tuple(
        ResultItem(
            path=result["path"],
            symbol=result["qualified_name"],
            start_line=result["start_line"],
            confidence=result["confidence"],
        )
        for result in results
    )
    return envelope_for_items(options, {"items": items}, len(results))


def envelope_for_graph_results(
    options: EnvelopeOptions,
    results: tuple[GraphResultPayload, ...],
) -> ContextEnvelope:
    items = tuple(
        ResultItem(
            path=result["path"],
            text=result["text"],
            start_line=result["start_line"],
            confidence=result["confidence"],
            certainty=result["certainty"],
            caller=result["caller"] or "",
        )
        for result in results
    )
    return envelope_for_items(options, {"items": items}, len(results))


def envelope_for_items(
    options: EnvelopeOptions,
    payload: ResultPayload,
    returned_limit: int,
) -> ContextEnvelope:
    stored = ContextOptimizationService(options["repo"]).store_result(
        tool_name=options["tool_name"],
        session_id=options.get("session_id"),
        query=options.get("query"),
        raw_payload=payload,
        returned_payload={"summary": f"{len(payload['items'])} stored items"},
    )
    return summarize_result(
        kind=options["tool_name"],
        result_id=stored.result_id,
        payload=payload,
        returned_limit=returned_limit,
    )


def _search_result_item(
    path: str,
    score: float,
    snippet: str | None,
) -> ResultItem:
    item = ResultItem(path=path, score=score)
    if snippet is not None:
        item["snippet"] = snippet
    return item
