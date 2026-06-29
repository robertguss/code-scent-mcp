from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from codescent.core.paths import normalize_repo_path, resolve_repo_root
from codescent.core.token_estimate import estimate_tokens
from codescent.services.answer_pack_support import (
    RELATED_FILE_CAP,
    SEED_FILE_LIMIT,
    SYMBOL_CAP,
    TOP_FILE_CAP,
    AnswerPack,
    Contributors,
    dedupe_cap,
    dedupe_symbols,
    fit_budget,
    in_scope_findings,
    related_neighbors,
    serialize_answer_pack,
    serialize_contributors,
    store_full,
    to_pack,
)
from codescent.services.context import ContextService
from codescent.services.search import SearchService

if TYPE_CHECKING:
    from pathlib import Path

__all__ = [
    "RELATED_FILE_CAP",
    "AnswerPack",
    "AnswerPackService",
    "serialize_answer_pack",
]


@dataclass(frozen=True, slots=True)
class AnswerPackService:
    repo_root: Path | str

    def answer_pack(
        self,
        query: str,
        *,
        focus_path: str | None = None,
        budget: int | None = None,
    ) -> AnswerPack:
        repo_root = resolve_repo_root(self.repo_root)
        context = ContextService(repo_root)
        parts = self._compose(repo_root, context, query, focus_path)
        full_tokens = estimate_tokens(serialize_contributors(query, parts))
        if budget is not None and full_tokens > budget:
            result_id = store_full(repo_root, query, parts, full_tokens)
            fit_budget(query, parts, budget, full_tokens=full_tokens)
            return to_pack(query, parts, result_id=result_id, truncated=True)
        return to_pack(
            query,
            parts,
            result_id=None,
            truncated=False,
            precomputed_tokens=full_tokens,
        )

    def _compose(
        self,
        repo_root: Path,
        context: ContextService,
        query: str,
        focus_path: str | None,
    ) -> Contributors:
        search = SearchService(repo_root)
        top_files = self._top_files(repo_root, search, query, focus_path)
        symbols = context.find_symbol(query, limit=SYMBOL_CAP) if query.strip() else ()
        related_tests, related_files = related_neighbors(context, top_files)
        return Contributors(
            top_files=list(top_files),
            key_symbols=list(dedupe_symbols(symbols)),
            related_tests=list(related_tests),
            findings=list(in_scope_findings(repo_root, set(top_files))),
            related_files=list(related_files),
        )

    def _top_files(
        self,
        repo_root: Path,
        search: SearchService,
        query: str,
        focus_path: str | None,
    ) -> tuple[str, ...]:
        if focus_path is not None:
            target = normalize_repo_path(repo_root, focus_path)
            return (target.relative_to(repo_root).as_posix(),)
        if not query.strip():
            return ()
        file_hits = search.search_files(query, limit=SEED_FILE_LIMIT)
        content_hits = search.search_content(query, limit=SEED_FILE_LIMIT)
        return dedupe_cap(
            (
                *(hit["path"] for hit in file_hits),
                *(hit["path"] for hit in content_hits),
            ),
            TOP_FILE_CAP,
        )
