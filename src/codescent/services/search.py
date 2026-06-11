from __future__ import annotations

import hashlib
import re
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Final, TypedDict

from codescent.core.models import PageOptions
from codescent.core.paths import resolve_repo_root
from codescent.engine.inventory import build_file_inventory
from codescent.engine.search import rank_path
from codescent.services.git import detect_git_state, git_changed_paths
from codescent.storage import RepositoryStorage, initialize_storage

if TYPE_CHECKING:
    from pathlib import Path

DEFAULT_LIMIT: Final = 20
MAX_LIMIT: Final = 20
DEFAULT_LINE_BUDGET: Final = 3
MAX_LINE_BUDGET: Final = 20
CHANGED_FILE_BONUS: Final = 25.0
FRECENCY_BONUS_MULTIPLIER: Final = 30.0
TODO_MARKERS: Final[tuple[str, ...]] = ("TODO", "FIXME", "HACK")
TODO_PATTERN: Final = re.compile(r"\b(TODO|FIXME|HACK)\b:?\s*(.*)")
TEST_FILE_BONUS: Final = 40.0
TEST_NAME_BONUS: Final = 35.0
TEST_CONTENT_BONUS: Final = 20.0


class SearchResultPayload(TypedDict):
    path: str
    score: float
    reasons: tuple[str, ...]
    snippet: str | None


class TodoSearchResultPayload(TypedDict):
    path: str
    score: float
    reasons: tuple[str, ...]
    snippet: str
    marker: str
    line: int


class TestSearchResultPayload(TypedDict):
    path: str
    score: float
    reasons: tuple[str, ...]
    snippet: str | None


class SearchPagePayload(TypedDict):
    results: tuple[SearchResultPayload, ...]
    next_cursor: str | None


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
        changed_files = _changed_files(repo_root)
        frecency_scores = _frecency_scores(repo_root)
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
            frecency_score = frecency_scores.get(item.path, 0.0)
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
        selected = tuple(_sort_results(results)[page.offset : page.offset + page.limit])
        _record_frecency(repo_root, query, tuple(result["path"] for result in selected))
        return selected

    def search_files_page(
        self,
        query: str,
        *,
        limit: int = DEFAULT_LIMIT,
        cursor: str | None = None,
    ) -> SearchPagePayload:
        offset = _cursor_to_offset(cursor)
        results = self.search_files(query, limit=MAX_LIMIT, offset=0)
        return _page_results(results, limit=limit, offset=offset)

    def search_content(
        self,
        query: str,
        *,
        limit: int = DEFAULT_LIMIT,
        line_budget: int = DEFAULT_LINE_BUDGET,
        offset: int = 0,
    ) -> tuple[SearchResultPayload, ...]:
        repo_root = resolve_repo_root(self.repo_root)
        changed_files = _changed_files(repo_root)
        frecency_scores = _frecency_scores(repo_root)
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
                frecency_score = frecency_scores.get(item.path, 0.0)
                if frecency_score > 0:
                    score += min(frecency_score, 5.0) * FRECENCY_BONUS_MULTIPLIER
                    reasons = (*reasons, "frecency")
                results.append(
                    {
                        "path": item.path,
                        "score": score,
                        "reasons": reasons,
                        "snippet": _snippet(lines, line_number, line_budget),
                    },
                )

        page = PageOptions(limit=limit, offset=offset)
        selected = tuple(_sort_results(results)[page.offset : page.offset + page.limit])
        _record_frecency(repo_root, query, tuple(result["path"] for result in selected))
        return selected

    def search_content_page(
        self,
        query: str,
        *,
        limit: int = DEFAULT_LIMIT,
        cursor: str | None = None,
        line_budget: int = DEFAULT_LINE_BUDGET,
    ) -> SearchPagePayload:
        offset = _cursor_to_offset(cursor)
        results = self.search_content(
            query,
            limit=MAX_LIMIT,
            offset=0,
            line_budget=line_budget,
        )
        return _page_results(results, limit=limit, offset=offset)

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

    def search_changed_files(
        self,
        query: str = "",
        *,
        limit: int = DEFAULT_LIMIT,
    ) -> tuple[SearchResultPayload, ...]:
        repo_root = resolve_repo_root(self.repo_root)
        page = PageOptions(limit=limit)
        change_reasons = _changed_file_reasons(repo_root)
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
                reasons = _merge_reasons(rank.reasons, reasons)
            results.append(
                {
                    "path": item.path,
                    "score": score,
                    "reasons": reasons,
                    "snippet": None,
                },
            )

        return tuple(_sort_results(results)[: page.limit])

    def search_todos(
        self,
        query: str = "",
        *,
        limit: int = DEFAULT_LIMIT,
    ) -> tuple[TodoSearchResultPayload, ...]:
        repo_root = resolve_repo_root(self.repo_root)
        page = PageOptions(limit=limit)
        results: list[TodoSearchResultPayload] = []

        for item in build_file_inventory(repo_root):
            lines = (repo_root / item.path).read_text().splitlines()
            for line_number, line in enumerate(lines, start=1):
                marker_match = TODO_PATTERN.search(line)
                if marker_match is None:
                    continue
                if query and (
                    _match_text(item.path, query) is None
                    and _match_text(line, query) is None
                ):
                    continue
                marker = marker_match.group(1)
                results.append(
                    {
                        "path": item.path,
                        "score": _todo_score(item.path, line, marker, query),
                        "reasons": ("todo_marker", f"marker:{marker}"),
                        "snippet": line.strip(),
                        "marker": marker,
                        "line": line_number,
                    },
                )

        return tuple(_sort_todo_results(results)[: page.limit])

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
        page = PageOptions(limit=limit)
        terms = _test_search_terms(
            query=query,
            path=path,
            symbol=symbol,
            finding_id=finding_id,
        )
        results: list[TestSearchResultPayload] = []

        for item in build_file_inventory(repo_root):
            if not _is_test_path(item.path):
                continue
            lines = (repo_root / item.path).read_text().splitlines()
            score, reasons, snippet = _rank_test_file(item.path, lines, terms)
            if score <= 0:
                continue
            results.append(
                {
                    "path": item.path,
                    "score": score,
                    "reasons": reasons,
                    "snippet": snippet,
                },
            )

        return tuple(_sort_test_results(results)[: page.limit])


def _sort_results(
    results: list[SearchResultPayload],
) -> list[SearchResultPayload]:
    return sorted(results, key=lambda result: (-result["score"], result["path"]))


def _sort_todo_results(
    results: list[TodoSearchResultPayload],
) -> list[TodoSearchResultPayload]:
    return sorted(
        results,
        key=lambda result: (-result["score"], result["path"], result["line"]),
    )


def _sort_test_results(
    results: list[TestSearchResultPayload],
) -> list[TestSearchResultPayload]:
    return sorted(results, key=lambda result: (-result["score"], result["path"]))


def _page_results(
    results: tuple[SearchResultPayload, ...],
    *,
    limit: int,
    offset: int,
) -> SearchPagePayload:
    page = PageOptions(limit=limit, offset=offset)
    selected = results[page.offset : page.offset + page.limit]
    next_offset = page.offset + len(selected)
    next_cursor = str(next_offset) if next_offset < len(results) else None
    return {"results": selected, "next_cursor": next_cursor}


def _cursor_to_offset(cursor: str | None) -> int:
    if cursor is None or cursor == "":
        return 0
    try:
        return max(int(cursor), 0)
    except ValueError:
        return 0


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


def _todo_score(path: str, line: str, marker: str, query: str) -> float:
    marker_boost = {
        "FIXME": 12.0,
        "TODO": 10.0,
        "HACK": 8.0,
    }[marker]
    score = 80.0 + marker_boost
    if query and _match_text(path, query) is not None:
        score += 15.0
    if query and _match_text(line, query) is not None:
        score += 20.0
    return score


def _is_test_path(path: str) -> bool:
    name = path.rsplit("/", maxsplit=1)[-1]
    return (
        path.startswith("tests/")
        or name.startswith("test_")
        or name.endswith("_test.py")
    )


def _test_search_terms(
    *,
    query: str,
    path: str | None,
    symbol: str | None,
    finding_id: str | None,
) -> tuple[str, ...]:
    terms: list[str] = []
    for value in (query, path, symbol, finding_id):
        if value is None:
            continue
        terms.extend(_split_test_terms(value))
    return tuple(dict.fromkeys(term for term in terms if term))


def _split_test_terms(value: str) -> tuple[str, ...]:
    normalized = value.replace("\\", "/").replace(":", "/")
    parts = re.split(r"[^A-Za-z0-9_]+", normalized)
    terms: list[str] = []
    for part in parts:
        if not part or part in {"src", "tests", "test", "py", "python"}:
            continue
        terms.append(part)
        if "_" in part:
            terms.extend(piece for piece in part.split("_") if piece)
    return tuple(terms)


def _rank_test_file(
    path: str,
    lines: list[str],
    terms: tuple[str, ...],
) -> tuple[float, tuple[str, ...], str | None]:
    score = TEST_FILE_BONUS
    reasons: list[str] = ["likely_test"]
    snippet: str | None = None
    if not terms:
        return score, tuple(reasons), snippet

    content = "\n".join(lines)
    for term in terms:
        if _match_text(path, term) is not None:
            score += TEST_NAME_BONUS
            reasons.append("path_match")
        line_match = _first_matching_line(lines, term)
        if line_match is not None:
            score += TEST_CONTENT_BONUS
            reasons.append("content_match")
            if snippet is None:
                snippet = line_match
        if _match_text(content, term) is not None and _looks_like_symbol(term):
            score += TEST_CONTENT_BONUS
            reasons.append("symbol_match")

    return score, _merge_reasons(tuple(reasons), ()), snippet


def _first_matching_line(lines: list[str], term: str) -> str | None:
    for line in lines:
        if _match_text(line, term) is not None:
            return line.strip()
    return None


def _looks_like_symbol(term: str) -> bool:
    return "_" in term or term.isidentifier()


def _frecency_scores(repo_root: Path) -> dict[str, float]:
    database_path = repo_root / ".codescent" / "index.sqlite"
    if not database_path.exists():
        return {}
    try:
        with closing(sqlite3.connect(database_path)) as connection:
            rows: list[tuple[str, float]] = connection.execute(
                (
                    "select path, coalesce(sum(weight), 0) "
                    "from frecency_signals group by path"
                ),
            ).fetchall()
    except sqlite3.DatabaseError:
        return {}
    return dict(rows)


def _record_frecency(
    repo_root: Path,
    query: str,
    paths: tuple[str, ...],
) -> None:
    if not paths:
        return
    signal = _query_signal(query)
    updated_at = datetime.now(UTC).isoformat()
    state = initialize_storage(repo_root)
    with RepositoryStorage(state).write_transaction() as connection:
        for path in paths:
            _ = connection.execute(
                """
                insert into frecency_signals (path, signal, weight, updated_at)
                values (?, ?, ?, ?)
                """,
                (path, signal, 1.0, updated_at),
            )


def _query_signal(query: str) -> str:
    digest = hashlib.sha256(query.encode("utf-8")).hexdigest()
    return f"search:{digest}"


def _changed_files(repo_root: Path) -> frozenset[str]:
    return frozenset(_changed_file_reasons(repo_root))


def _changed_file_reasons(repo_root: Path) -> dict[str, tuple[str, ...]]:
    inventory_hashes = {
        item.path: item.hash for item in build_file_inventory(repo_root)
    }
    inventory_paths = frozenset(inventory_hashes)
    git_paths = git_changed_paths(repo_root) & inventory_paths
    index_paths = _index_changed_files(
        repo_root,
        inventory_hashes,
        include_unindexed=not detect_git_state(repo_root).available,
    )
    reasons: dict[str, tuple[str, ...]] = {}
    for path in sorted(git_paths | index_paths):
        path_reasons = ["changed_file"]
        if path in git_paths:
            path_reasons.append("git_changed")
        if path in index_paths:
            path_reasons.append("index_changed")
        reasons[path] = tuple(path_reasons)
    return reasons


def _index_changed_files(
    repo_root: Path,
    inventory_hashes: dict[str, str],
    *,
    include_unindexed: bool,
) -> frozenset[str]:
    database_path = repo_root / ".codescent" / "index.sqlite"
    if not database_path.exists():
        return frozenset(inventory_hashes) if include_unindexed else frozenset()
    stored_hashes = _stored_hashes(database_path)
    if not stored_hashes:
        return frozenset(inventory_hashes) if include_unindexed else frozenset()
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
