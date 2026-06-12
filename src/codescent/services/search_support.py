from __future__ import annotations

import hashlib
import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Final, TypedDict

from codescent.core.models import PageOptions
from codescent.engine.inventory import build_file_inventory
from codescent.services.config import ConfigService
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


def sort_results(
    results: list[SearchResultPayload],
) -> list[SearchResultPayload]:
    return sorted(results, key=lambda result: (-result["score"], result["path"]))


def page_results(
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


def cursor_to_offset(cursor: str | None) -> int:
    if cursor is None or cursor == "":
        return 0
    try:
        return max(int(cursor), 0)
    except ValueError:
        return 0


def merge_reasons(
    current: tuple[str, ...],
    incoming: tuple[str, ...],
) -> tuple[str, ...]:
    return tuple(dict.fromkeys((*current, *incoming)))


def match_text(line: str, query: str) -> str | None:
    if any(character.isupper() for character in query):
        if query in line:
            return line
        return None
    if query.lower() in line.lower():
        return line
    return None


def snippet(lines: list[str], line_number: int, line_budget: int) -> str:
    budget = min(max(line_budget, 1), MAX_LINE_BUDGET)
    start = max(line_number - (budget // 2), 0)
    selected = lines[start : start + budget]
    return "\n".join(line.strip() for line in selected)


def frecency_scores(repo_root: Path) -> dict[str, float]:
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


def record_frecency(
    repo_root: Path,
    query: str,
    paths: tuple[str, ...],
) -> None:
    if not paths:
        return
    signal = query_signal(query)
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


def query_signal(query: str) -> str:
    digest = hashlib.sha256(query.encode("utf-8")).hexdigest()
    return f"search:{digest}"


def changed_files(repo_root: Path) -> frozenset[str]:
    return frozenset(changed_file_reasons(repo_root))


def changed_file_reasons(repo_root: Path) -> dict[str, tuple[str, ...]]:
    config = ConfigService(repo_root).load()
    inventory_hashes = {
        item.path: item.hash for item in build_file_inventory(repo_root, config=config)
    }
    inventory_paths = frozenset(inventory_hashes)
    git_paths = git_changed_paths(repo_root) & inventory_paths
    index_paths = index_changed_files(
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


def index_changed_files(
    repo_root: Path,
    inventory_hashes: dict[str, str],
    *,
    include_unindexed: bool,
) -> frozenset[str]:
    database_path = repo_root / ".codescent" / "index.sqlite"
    if not database_path.exists():
        return frozenset(inventory_hashes) if include_unindexed else frozenset()
    stored_hashes = stored_hashes_for(database_path)
    if not stored_hashes:
        return frozenset(inventory_hashes) if include_unindexed else frozenset()
    changed = {
        path
        for path, file_hash in inventory_hashes.items()
        if stored_hashes.get(path) != file_hash
    }
    changed.update(path for path in stored_hashes if path not in inventory_hashes)
    return frozenset(changed)


def stored_hashes_for(database_path: Path) -> dict[str, str]:
    try:
        with closing(sqlite3.connect(database_path)) as connection:
            rows: list[tuple[str, str]] = connection.execute(
                "select path, hash from files",
            ).fetchall()
    except sqlite3.DatabaseError:
        return {}
    return dict(rows)
