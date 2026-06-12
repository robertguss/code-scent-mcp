from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from codescent.core.models import PageOptions
from codescent.core.paths import resolve_repo_root
from codescent.engine.inventory import build_file_inventory
from codescent.engine.search import rank_path
from codescent.services.search_queries import (
    TestSearchRequest,
    search_tests_for_repo,
    search_todos_for_repo,
)
from codescent.services.search_support import (
    CHANGED_FILE_BONUS,
    DEFAULT_LIMIT,
    DEFAULT_LINE_BUDGET,
    FRECENCY_BONUS_MULTIPLIER,
    MAX_LIMIT,
    SearchPagePayload,
    SearchResultPayload,
    TestSearchResultPayload,
    TodoSearchResultPayload,
    changed_file_reasons,
    changed_files,
    cursor_to_offset,
    frecency_scores,
    match_text,
    merge_reasons,
    page_results,
    record_frecency,
    snippet,
    sort_results,
)

if TYPE_CHECKING:
    from pathlib import Path


@dataclass(frozen=True, slots=True)
class SearchService:
    repo_root: Path | str

    def search_files(
        self,
        query: str,
        *,
        limit: int = DEFAULT_LIMIT,
        offset: int = 0,
    ) -> tuple[SearchResultPayload, ...]:
        repo_root = resolve_repo_root(self.repo_root)
        changed = changed_files(repo_root)
        frecency = frecency_scores(repo_root)
        results: list[SearchResultPayload] = []

        for item in build_file_inventory(repo_root):
            rank = rank_path(item.path, query)
            if rank is None:
                continue
            score = rank.score
            reasons = rank.reasons
            if item.path in changed:
                score += CHANGED_FILE_BONUS
                reasons = (*reasons, "changed_file")
            frecency_score = frecency.get(item.path, 0.0)
            if frecency_score > 0:
                score += min(frecency_score, 5.0) * FRECENCY_BONUS_MULTIPLIER
                reasons = (*reasons, "frecency")
            results.append(
                {
                    "path": item.path,
                    "score": score,
                    "reasons": reasons,
                    "snippet": None,
                },
            )

        page = PageOptions(limit=limit, offset=offset)
        selected = tuple(sort_results(results)[page.offset : page.offset + page.limit])
        record_frecency(repo_root, query, tuple(result["path"] for result in selected))
        return selected

    def search_files_page(
        self,
        query: str,
        *,
        limit: int = DEFAULT_LIMIT,
        cursor: str | None = None,
    ) -> SearchPagePayload:
        offset = cursor_to_offset(cursor)
        results = self.search_files(query, limit=MAX_LIMIT, offset=0)
        return page_results(results, limit=limit, offset=offset)

    def search_content(
        self,
        query: str,
        *,
        limit: int = DEFAULT_LIMIT,
        line_budget: int = DEFAULT_LINE_BUDGET,
        offset: int = 0,
    ) -> tuple[SearchResultPayload, ...]:
        repo_root = resolve_repo_root(self.repo_root)
        changed = changed_files(repo_root)
        frecency = frecency_scores(repo_root)
        results: list[SearchResultPayload] = []

        for item in build_file_inventory(repo_root):
            lines = (repo_root / item.path).read_text().splitlines()
            for line_number, line in enumerate(lines):
                if match_text(line, query) is None:
                    continue
                score = 100.0
                reasons = ("content_match",)
                if item.path in changed:
                    score += CHANGED_FILE_BONUS
                    reasons = (*reasons, "changed_file")
                frecency_score = frecency.get(item.path, 0.0)
                if frecency_score > 0:
                    score += min(frecency_score, 5.0) * FRECENCY_BONUS_MULTIPLIER
                    reasons = (*reasons, "frecency")
                results.append(
                    {
                        "path": item.path,
                        "score": score,
                        "reasons": reasons,
                        "snippet": snippet(lines, line_number, line_budget),
                    },
                )

        page = PageOptions(limit=limit, offset=offset)
        selected = tuple(sort_results(results)[page.offset : page.offset + page.limit])
        record_frecency(repo_root, query, tuple(result["path"] for result in selected))
        return selected

    def search_content_page(
        self,
        query: str,
        *,
        limit: int = DEFAULT_LIMIT,
        cursor: str | None = None,
        line_budget: int = DEFAULT_LINE_BUDGET,
    ) -> SearchPagePayload:
        offset = cursor_to_offset(cursor)
        results = self.search_content(
            query,
            limit=MAX_LIMIT,
            offset=0,
            line_budget=line_budget,
        )
        return page_results(results, limit=limit, offset=offset)

    def multi_search_content(
        self,
        queries: tuple[str, ...],
        *,
        limit: int = DEFAULT_LIMIT,
        line_budget: int = DEFAULT_LINE_BUDGET,
    ) -> tuple[SearchResultPayload, ...]:
        page = PageOptions(limit=limit)
        merged: dict[str, SearchResultPayload] = {}
        for query in queries:
            for result in self.search_content(
                query,
                limit=MAX_LIMIT,
                line_budget=line_budget,
            ):
                existing = merged.get(result["path"])
                reasons = merge_reasons(result["reasons"], (f"query:{query}",))
                if existing is None:
                    merged[result["path"]] = {
                        "path": result["path"],
                        "score": result["score"],
                        "reasons": reasons,
                        "snippet": result["snippet"],
                    }
                    continue
                merged[result["path"]] = {
                    "path": existing["path"],
                    "score": max(existing["score"], result["score"]),
                    "reasons": merge_reasons(existing["reasons"], reasons),
                    "snippet": existing["snippet"] or result["snippet"],
                }

        return tuple(sort_results(list(merged.values()))[: page.limit])

    def search_changed_files(
        self,
        query: str = "",
        *,
        limit: int = DEFAULT_LIMIT,
    ) -> tuple[SearchResultPayload, ...]:
        repo_root = resolve_repo_root(self.repo_root)
        page = PageOptions(limit=limit)
        change_reasons = changed_file_reasons(repo_root)
        results: list[SearchResultPayload] = []

        for item in build_file_inventory(repo_root):
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
        return search_todos_for_repo(repo_root, query, limit=limit)

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
        return search_tests_for_repo(repo_root, request)
