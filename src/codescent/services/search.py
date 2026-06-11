from __future__ import annotations

import sqlite3
from contextlib import closing
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final, TypedDict

from codescent.core.models import PageOptions
from codescent.core.paths import resolve_repo_root
from codescent.engine.inventory import build_file_inventory
from codescent.engine.search import rank_path

if TYPE_CHECKING:
    from pathlib import Path

DEFAULT_LIMIT: Final = 20
MAX_LIMIT: Final = 20
DEFAULT_LINE_BUDGET: Final = 3
MAX_LINE_BUDGET: Final = 20
CHANGED_FILE_BONUS: Final = 25.0


class SearchResultPayload(TypedDict):
    path: str
    score: float
    reasons: tuple[str, ...]
    snippet: str | None


@dataclass(frozen=True, slots=True)
class SearchService:
    repo_root: Path | str

    def search_files(
        self,
        query: str,
        *,
        limit: int = DEFAULT_LIMIT,
    ) -> tuple[SearchResultPayload, ...]:
        repo_root = resolve_repo_root(self.repo_root)
        changed_files = _changed_files(repo_root)
        results: list[SearchResultPayload] = []

        for item in build_file_inventory(repo_root):
            rank = rank_path(item.path, query)
            if rank is None:
                continue
            score = rank.score
            reasons = rank.reasons
            if item.path in changed_files:
                score += CHANGED_FILE_BONUS
                reasons = (*reasons, "changed_file")
            results.append(
                {
                    "path": item.path,
                    "score": score,
                    "reasons": reasons,
                    "snippet": None,
                },
            )

        return tuple(_sort_results(results)[: _clamp_limit(limit)])

    def search_content(
        self,
        query: str,
        *,
        limit: int = DEFAULT_LIMIT,
        line_budget: int = DEFAULT_LINE_BUDGET,
    ) -> tuple[SearchResultPayload, ...]:
        repo_root = resolve_repo_root(self.repo_root)
        changed_files = _changed_files(repo_root)
        results: list[SearchResultPayload] = []

        for item in build_file_inventory(repo_root):
            lines = (repo_root / item.path).read_text().splitlines()
            for line_number, line in enumerate(lines):
                if _match_text(line, query) is None:
                    continue
                score = 100.0
                reasons = ("content_match",)
                if item.path in changed_files:
                    score += CHANGED_FILE_BONUS
                    reasons = (*reasons, "changed_file")
                results.append(
                    {
                        "path": item.path,
                        "score": score,
                        "reasons": reasons,
                        "snippet": _snippet(lines, line_number, line_budget),
                    },
                )

        return tuple(_sort_results(results)[: _clamp_limit(limit)])

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
                query_reason = f"query:{query}"
                reasons = _merge_reasons(result["reasons"], (query_reason,))
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
                    "reasons": _merge_reasons(existing["reasons"], reasons),
                    "snippet": existing["snippet"] or result["snippet"],
                }

        return tuple(_sort_results(list(merged.values()))[: page.limit])


def _sort_results(
    results: list[SearchResultPayload],
) -> list[SearchResultPayload]:
    return sorted(results, key=lambda result: (-result["score"], result["path"]))


def _clamp_limit(limit: int) -> int:
    return min(max(limit, 1), MAX_LIMIT)


def _merge_reasons(
    current: tuple[str, ...],
    incoming: tuple[str, ...],
) -> tuple[str, ...]:
    return tuple(dict.fromkeys((*current, *incoming)))


def _clamp_line_budget(line_budget: int) -> int:
    return min(max(line_budget, 1), MAX_LINE_BUDGET)


def _match_text(line: str, query: str) -> str | None:
    if any(character.isupper() for character in query):
        if query in line:
            return line
        return None
    if query.lower() in line.lower():
        return line
    return None


def _snippet(lines: list[str], line_number: int, line_budget: int) -> str:
    budget = _clamp_line_budget(line_budget)
    start = max(line_number - (budget // 2), 0)
    selected = lines[start : start + budget]
    return "\n".join(line.strip() for line in selected)


def _changed_files(repo_root: Path) -> frozenset[str]:
    database_path = repo_root / ".codescent" / "index.sqlite"
    if not database_path.exists():
        return frozenset()
    inventory_hashes = {
        item.path: item.hash for item in build_file_inventory(repo_root)
    }
    stored_hashes = _stored_hashes(database_path)
    changed = {
        path
        for path, file_hash in inventory_hashes.items()
        if stored_hashes.get(path) != file_hash
    }
    changed.update(path for path in stored_hashes if path not in inventory_hashes)
    return frozenset(changed)


def _stored_hashes(database_path: Path) -> dict[str, str]:
    try:
        with closing(sqlite3.connect(database_path)) as connection:
            rows: list[tuple[str, str]] = connection.execute(
                "select path, hash from files",
            ).fetchall()
    except sqlite3.DatabaseError:
        return {}
    return dict(rows)
