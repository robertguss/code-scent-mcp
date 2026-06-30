from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from codescent.core.models import PageOptions
from codescent.core.paths import resolve_repo_root
from codescent.engine.inventory import build_file_inventory
from codescent.engine.search import rank_path
from codescent.services.config import ConfigService
from codescent.services.fff_backend import select_search_backend
from codescent.services.quality_signals import quality_annotation_for
from codescent.services.search_queries import (
    TestSearchRequest,
    search_tests_for_repo,
    search_todos_for_repo,
)
from codescent.services.search_run import (
    RetrievalContext,
    build_constraint_filter,
    content_results,
    content_results_for_queries,
    file_results,
)
from codescent.services.search_support import (
    CHANGED_FILE_BONUS,
    DEFAULT_LIMIT,
    DEFAULT_LINE_BUDGET,
    MAX_LIMIT,
    SearchPagePayload,
    SearchResultPayload,
    TestSearchResultPayload,
    TodoSearchResultPayload,
    changed_file_reasons,
    cursor_to_offset,
    merge_reasons,
    page_results,
    ranking_signals_for,
    record_frecency,
    sort_results,
)

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

    from codescent.engine.search import PathQuality
    from codescent.services.fff_backend import FffClient


def _annotate_quality(
    results: tuple[SearchResultPayload, ...],
    quality: Mapping[str, PathQuality],
) -> tuple[SearchResultPayload, ...]:
    """Attach the bounded inline quality annotation to each result."""
    for result in results:
        annotation = quality_annotation_for(result["path"], quality)
        if annotation is not None:
            result["quality"] = annotation
    return results


@dataclass(frozen=True, slots=True)
class SearchService:
    repo_root: Path | str
    # Optional pre-built fff engine (tests). Routed through
    # ``select_search_backend`` so an unhealthy client falls back to native; the
    # default (``None``) detects fff and returns native when it is absent.
    fff_client: FffClient | None = None

    def _backend(self, repo_root: Path) -> FffClient | None:
        return select_search_backend(repo_root, client=self.fff_client)

    def search_files(
        self,
        query: str,
        *,
        limit: int = DEFAULT_LIMIT,
        offset: int = 0,
        constraints: str = "",
    ) -> tuple[SearchResultPayload, ...]:
        repo_root = resolve_repo_root(self.repo_root)
        context = RetrievalContext(
            repo_root=repo_root,
            config=ConfigService(repo_root).load(),
            signals=ranking_signals_for(repo_root),
            allow=build_constraint_filter(repo_root, constraints),
        )
        results = file_results(context, query, backend=self._backend(repo_root))
        page = PageOptions(limit=limit, offset=offset)
        selected = tuple(sort_results(results)[page.offset : page.offset + page.limit])
        record_frecency(repo_root, query, tuple(result["path"] for result in selected))
        return _annotate_quality(selected, context.signals.quality)

    def search_files_page(
        self,
        query: str,
        *,
        limit: int = DEFAULT_LIMIT,
        cursor: str | None = None,
        constraints: str = "",
    ) -> SearchPagePayload:
        offset = cursor_to_offset(cursor)
        results = self.search_files(
            query, limit=MAX_LIMIT, offset=0, constraints=constraints
        )
        return page_results(results, limit=limit, offset=offset)

    def search_content(  # noqa: PLR0913 - additive constraints prefilter knob.
        self,
        query: str,
        *,
        limit: int = DEFAULT_LIMIT,
        line_budget: int = DEFAULT_LINE_BUDGET,
        offset: int = 0,
        expand: bool = False,
        constraints: str = "",
    ) -> tuple[SearchResultPayload, ...]:
        repo_root = resolve_repo_root(self.repo_root)
        context = RetrievalContext(
            repo_root=repo_root,
            config=ConfigService(repo_root).load(),
            signals=ranking_signals_for(repo_root),
            allow=build_constraint_filter(repo_root, constraints),
        )
        results = content_results(
            context,
            query,
            backend=self._backend(repo_root),
            line_budget=line_budget,
            expand=expand,
        )
        page = PageOptions(limit=limit, offset=offset)
        selected = tuple(sort_results(results)[page.offset : page.offset + page.limit])
        record_frecency(repo_root, query, tuple(result["path"] for result in selected))
        return _annotate_quality(selected, context.signals.quality)

    def search_content_page(  # noqa: PLR0913 - additive constraints prefilter knob.
        self,
        query: str,
        *,
        limit: int = DEFAULT_LIMIT,
        cursor: str | None = None,
        line_budget: int = DEFAULT_LINE_BUDGET,
        expand: bool = False,
        constraints: str = "",
    ) -> SearchPagePayload:
        offset = cursor_to_offset(cursor)
        results = self.search_content(
            query,
            limit=MAX_LIMIT,
            offset=0,
            line_budget=line_budget,
            expand=expand,
            constraints=constraints,
        )
        return page_results(results, limit=limit, offset=offset)

    def multi_search_content(
        self,
        queries: tuple[str, ...],
        *,
        limit: int = DEFAULT_LIMIT,
        line_budget: int = DEFAULT_LINE_BUDGET,
        expand: bool = False,
        constraints: str = "",
    ) -> tuple[SearchResultPayload, ...]:
        if not queries:
            return ()

        repo_root = resolve_repo_root(self.repo_root)
        context = RetrievalContext(
            repo_root=repo_root,
            config=ConfigService(repo_root).load(),
            signals=ranking_signals_for(repo_root),
            allow=build_constraint_filter(repo_root, constraints),
        )
        per_query = content_results_for_queries(
            context,
            queries,
            backend=self._backend(repo_root),
            line_budget=line_budget,
            expand=expand,
        )

        merged: dict[str, SearchResultPayload] = {}
        for query, results in per_query.items():
            for result in results:
                reasons = merge_reasons(result["reasons"], (f"query:{query}",))
                existing = merged.get(result["path"])
                if existing is None:
                    merged[result["path"]] = {**result, "reasons": reasons}
                    continue
                merged[result["path"]] = {
                    "path": result["path"],
                    "score": max(existing["score"], result["score"]),
                    "reasons": merge_reasons(existing["reasons"], reasons),
                    "snippet": existing["snippet"] or result["snippet"],
                    "symbol": existing["symbol"] or result["symbol"],
                }

        selected = tuple(sort_results(list(merged.values()))[:limit])
        for query in queries:
            query_paths = tuple(
                result["path"]
                for result in selected
                if f"query:{query}" in result["reasons"]
            )
            record_frecency(repo_root, query, query_paths)
        return _annotate_quality(selected, context.signals.quality)

    def search_changed_files(
        self,
        query: str = "",
        *,
        limit: int = DEFAULT_LIMIT,
    ) -> tuple[SearchResultPayload, ...]:
        repo_root = resolve_repo_root(self.repo_root)
        config = ConfigService(repo_root).load()
        page = PageOptions(limit=limit)
        change_reasons = changed_file_reasons(repo_root)
        results: list[SearchResultPayload] = []

        for item in build_file_inventory(repo_root, config=config):
            reasons = change_reasons.get(item.path)
            if reasons is None:
                continue
            score = 100.0
            if query:
                rank = rank_path(item.path, query)
                if rank is None:
                    continue
                score = rank.score + CHANGED_FILE_BONUS
                reasons = merge_reasons(rank.reasons, reasons)
            results.append(
                {
                    "path": item.path,
                    "score": score,
                    "reasons": reasons,
                    "snippet": None,
                    "symbol": None,
                },
            )

        return tuple(sort_results(results)[: page.limit])

    def search_todos(
        self,
        query: str = "",
        *,
        limit: int = DEFAULT_LIMIT,
    ) -> tuple[TodoSearchResultPayload, ...]:
        repo_root = resolve_repo_root(self.repo_root)
        config = ConfigService(repo_root).load()
        return search_todos_for_repo(repo_root, query, limit=limit, config=config)

    def search_tests(
        self,
        query: str = "",
        *,
        path: str | None = None,
        symbol: str | None = None,
        finding_id: str | None = None,
        limit: int = DEFAULT_LIMIT,
    ) -> tuple[TestSearchResultPayload, ...]:
        repo_root = resolve_repo_root(self.repo_root)
        request = TestSearchRequest(
            query=query,
            path=path,
            symbol=symbol,
            finding_id=finding_id,
            limit=limit,
        )
        config = ConfigService(repo_root).load()
        return search_tests_for_repo(repo_root, request, config=config)
